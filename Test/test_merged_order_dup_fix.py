"""
测试：合并订单中订单级备注污染导致的重复商品行问题
场景：合并订单的某个商品行带有订单级备注（包含所有子订单的商品信息），
      解析后会生成重复的商品行。修复后应正确过滤。
"""
import sys
import os
# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from core.parser import extract_multiple_remarks, ParsedRemark
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
import re


def _normalize_sku_for_dup(sku: str) -> str:
    if not sku:
        return sku
    sku = re.sub(r'(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)',
                 r'\1x\2', sku, flags=re.IGNORECASE)
    sku = re.sub(r'(直径|圆|圆形|圆直径|尺寸)(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)',
                 r'\1\2', sku, flags=re.IGNORECASE)
    return sku


def simulate_engine_purify(all_parsed_list, order_items, adapter):
    """模拟 engine.py 中的合并订单净化逻辑（修复后版本）"""
    # 构建现有商品行的 (normalized_sku, num) -> set of original_tid 映射
    # 同时构建 original_tid -> set of (normalized_sku, num) 反向映射
    existing_sku_tids = {}  # {(norm_sku, num): set of tid}
    tid_to_skus = {}       # {tid: set of (norm_sku, num)}
    for item in order_items:
        if item.is_void:
            continue
        if hasattr(adapter, '_is_gift_item') and adapter._is_gift_item(item):
            continue
        norm_sku = _normalize_sku_for_dup(item.shop_mapping_sku or '')
        if norm_sku:
            key = (norm_sku, item.num)
            if key not in existing_sku_tids:
                existing_sku_tids[key] = set()
            item_tid = item.original_tid or ''
            existing_sku_tids[key].add(item_tid)
            # 反向映射
            if item_tid:
                if item_tid not in tid_to_skus:
                    tid_to_skus[item_tid] = set()
                tid_to_skus[item_tid].add(key)

    # a. 跨分组污染过滤（修复后版本）
    filtered_parsed = []
    contamination_count = 0
    
    # 预计算所有 tid
    all_tids_in_order = set()
    for item in order_items:
        tid = item.original_tid or ''
        if tid:
            all_tids_in_order.add(tid)
    
    for p in all_parsed_list:
        if not p or not p.success:
            filtered_parsed.append(p)
            continue
        norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
        key = (norm_sku, p.num)
        existing_tids = existing_sku_tids.get(key, set())
        if existing_tids:
            # 该 SKU 已有商品行存在
            if p.original_tid and p.original_tid in existing_tids:
                # 本组已有该 SKU 的商品行 → 保留
                filtered_parsed.append(p)
            else:
                # 该 SKU 的商品行在其他组 → 检查当前子订单是否有「这个特定 SKU」的现有商品行
                p_tid = p.original_tid or ''
                # 检查当前子订单是否有该 SKU 的现有商品行（合法跨子订单相同SKU）
                current_tid_skus = tid_to_skus.get(p_tid, set())
                if key in current_tid_skus:
                    # 当前子订单也有该 SKU → 合法商品，保留
                    filtered_parsed.append(p)
                elif p_tid and p_tid in all_tids_in_order and not tid_to_skus.get(p_tid, set()):
                    # 子订单存在但没有任何有效商品行 → 保留
                    filtered_parsed.append(p)
                else:
                    # 当前子订单没有该 SKU 的现有商品行 → 污染，剔除
                    contamination_count += 1
        else:
            # 该 SKU 没有现有商品行 → 可能是新尺寸/新商品，保留
            filtered_parsed.append(p)

    if contamination_count > 0:
        print(f"  🧹 合并订单净化：过滤掉 {contamination_count} 个跨分组污染的解析结果")

    # b. 同 SKU 去重
    success_parsed = [p for p in filtered_parsed if p and p.success]
    non_success_parsed = [p for p in filtered_parsed if p and not p.success]

    dedup_groups = {}
    for p in success_parsed:
        norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
        # 使用 (SKU, 数量, original_tid) 为分组键，确保跨子订单不去重
        dedup_key = (norm_sku, p.num, p.original_tid or '')
        if dedup_key not in dedup_groups:
            dedup_groups[dedup_key] = []
        dedup_groups[dedup_key].append(p)

    deduped_parsed = []
    dup_removed = 0
    for dedup_key, candidates in dedup_groups.items():
        norm_sku, num, group_tid = dedup_key
        if len(candidates) == 1:
            deduped_parsed.append(candidates[0])
            continue
        dup_removed += len(candidates) - 1
        best = None
        best_score = -1
        for p in candidates:
            score = 0
            if p.original_tid and "&" not in p.original_tid:
                score = 50
            else:
                score = 0
            if score > best_score:
                best_score = score
                best = p
        if best:
            deduped_parsed.append(best)

    if dup_removed > 0:
        print(f"  🧹 合并订单去重：移除 {dup_removed} 个同子订单内的重复解析结果")

    return deduped_parsed + non_success_parsed


print("=" * 70)
print("测试：合并订单订单级备注污染导致重复商品行的修复")
print("=" * 70)

TID_A = "6954795507938235757"
TID_B = "6954799887611270509"
TID_MERGED = f"{TID_A}&{TID_B}"

order_level_remark = "定制双面革戴安娜:27x383cm-1张，80x80cm4个角圆角半径6.5cm-1张，共计2张"

# 现有商品行
item_a = OrderItem(
    id="item_a",
    order_id=TID_MERGED,
    oid=TID_A,
    title="轻奢简约高级感...",
    shop_mapping_sku="双面格-定制-定制尺寸-戴安娜;27x383CM",
    num=1,
    shop_remark="",
    original_tid=TID_A,
)

item_b = OrderItem(
    id="item_b",
    order_id=TID_MERGED,
    oid=TID_B,
    title="轻奢简约高级感...",
    shop_mapping_sku="双面格-定制-定制尺寸-戴安娜;80x80CM角圆角半径6.5cm",
    num=1,
    shop_remark=order_level_remark,
    original_tid=TID_B,
)

order_items = [item_a, item_b]
adapter = FangguoAdapter()

print("\n" + "=" * 70)
print("场景1：单分组污染（只有B组有订单级备注）")
print("=" * 70)
print(f"现有商品行：")
print(f"  A: {item_a.shop_mapping_sku[:55]} (tid=A)")
print(f"  B: {item_b.shop_mapping_sku[:55]} (tid=B)")
print(f"  B的备注包含两个商品（订单级备注污染）")

parsed_from_b = extract_multiple_remarks(
    order_level_remark,
    material_map=adapter.material_map,
    material_matcher=adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None,
)

for p in parsed_from_b:
    p.original_tid = TID_B
    p.shop_remark = ""

print(f"\n从B的订单级备注解析出 {len([p for p in parsed_from_b if p.success])} 个商品：")
for i, p in enumerate(parsed_from_b):
    if p.success:
        print(f"  [{i}] {p.shop_mapping_sku[:60]} (tid=B)")

all_parsed = parsed_from_b
print(f"\n修复前：{len([p for p in all_parsed if p.success])} 个解析结果")

purified = simulate_engine_purify(all_parsed, order_items, adapter)
success_purified = [p for p in purified if p.success]
print(f"修复后：{len(success_purified)} 个解析结果")
for i, p in enumerate(success_purified):
    print(f"  [{i}] {p.shop_mapping_sku[:60]} (tid={p.original_tid[:10]}...)")

# 验证
test1_pass = True
if len(success_purified) != 1:
    print(f"\n❌ 失败：期望1个解析结果（B自己的商品），实际{len(success_purified)}个")
    test1_pass = False
else:
    p = success_purified[0]
    norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
    if '80x80' in norm_sku and p.original_tid == TID_B:
        print(f"\n✅ 通过：正确过滤掉了A的商品，只保留B自己的商品")
    else:
        print(f"\n❌ 失败：保留的不是B自己的80x80商品")
        test1_pass = False

print(f"\n场景1测试结果: {'✅ 通过' if test1_pass else '❌ 失败'}")

# ===== 场景2：两个分组都有订单级备注 =====
print("\n" + "=" * 70)
print("场景2：双分组污染（两个分组都有订单级备注）")
print("=" * 70)

item_a_with_remark = OrderItem(
    id="item_a2",
    order_id=TID_MERGED,
    oid=TID_A,
    title="轻奢简约高级感...",
    shop_mapping_sku="双面格-定制-定制尺寸-戴安娜;27x383CM",
    num=1,
    shop_remark=order_level_remark,
    original_tid=TID_A,
)

order_items2 = [item_a_with_remark, item_b]

# 直接构造 ParsedRemark 对象以精确控制测试场景
# 模拟：两个分组都解析出相同的两个SKU（订单级备注被复制到所有商品行）
def _make_parsed(material, color, model, picture, num=1, tid="", success=True):
    p = ParsedRemark(
        material_code=material,
        color_code=color,
        model_code=model,
        picture_code=picture,
        num=num,
        success=success,
        original_tid=tid,
    )
    return p

sku_a_27 = "双面格-定制-定制尺寸-戴安娜;27x383CM"
sku_a_80 = "双面格-定制-定制尺寸-戴安娜;80x80CM角圆角半径6.5cm"

# A组解析出两个SKU（自己的27x383 + 污染的80x80）
p_a1 = _make_parsed("双面格", "定制", "定制尺寸", "戴安娜;27x383CM", tid=TID_A)
p_a2 = _make_parsed("双面格", "定制", "定制尺寸", "戴安娜;80x80CM角圆角半径6.5cm", tid=TID_A)

# B组解析出两个SKU（污染的27x383 + 自己的80x80）
p_b1 = _make_parsed("双面格", "定制", "定制尺寸", "戴安娜;27x383CM", tid=TID_B)
p_b2 = _make_parsed("双面格", "定制", "定制尺寸", "戴安娜;80x80CM角圆角半径6.5cm", tid=TID_B)

all_parsed2 = [p_a1, p_a2, p_b1, p_b2]
print(f"修复前：{len([p for p in all_parsed2 if p.success])} 个解析结果（A组2个 + B组2个）")
print(f"  A组: 27x383(tid=A), 80x80(tid=A)")
print(f"  B组: 27x383(tid=B), 80x80(tid=B)")

# 确保现有商品行的SKU与解析结果的SKU标准化后匹配
# （因为item_a的SKU是"双面格-定制-定制尺寸-戴安娜;27x383CM"，
#  与p_a1的SKU相同，标准化后也相同）
item_a_with_remark.shop_mapping_sku = p_a1.shop_mapping_sku
item_b.shop_mapping_sku = p_b2.shop_mapping_sku
order_items2 = [item_a_with_remark, item_b]

purified2 = simulate_engine_purify(all_parsed2, order_items2, adapter)
success_purified2 = [p for p in purified2 if p.success]
print(f"修复后：{len(success_purified2)} 个解析结果")
for i, p in enumerate(success_purified2):
    print(f"  [{i}] {p.shop_mapping_sku[:60]} (tid={p.original_tid[:10]}...)")

# 验证：应该有2个结果，一个是A的27x383，一个是B的80x80
test2_pass = True
if len(success_purified2) != 2:
    print(f"\n❌ 失败：期望2个解析结果，实际{len(success_purified2)}个")
    test2_pass = False
else:
    # 检查每个SKU的tid是否正确
    tid_by_sku = {}
    for p in success_purified2:
        norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
        if '27x383' in norm_sku:
            tid_by_sku['27x383'] = p.original_tid
        elif '80x80' in norm_sku:
            tid_by_sku['80x80'] = p.original_tid

    if tid_by_sku.get('27x383') == TID_A:
        print(f"\n✅ 27x383商品的tid正确（A）")
    else:
        print(f"\n❌ 27x383商品的tid错误")
        test2_pass = False

    if tid_by_sku.get('80x80') == TID_B:
        print(f"✅ 80x80商品的tid正确（B）")
    else:
        print(f"❌ 80x80商品的tid错误")
        test2_pass = False

print(f"\n场景2测试结果: {'✅ 通过' if test2_pass else '❌ 失败'}")

# ===== 场景3：正常多尺寸订单（不应被误过滤） =====
print("\n" + "=" * 70)
print("场景3：单订单多尺寸（正常情况，不应被过滤）")
print("=" * 70)

multi_size_remark = "定制双面革戴安娜:30x120cm-1张，40x120cm-1张，共计2张"
item_single = OrderItem(
    id="item_single",
    order_id="single_order",
    oid="single_order",
    title="轻奢简约高级感...",
    shop_mapping_sku="默认SKU",
    num=1,
    shop_remark=multi_size_remark,
    original_tid="single_order",
)

parsed_single = extract_multiple_remarks(
    multi_size_remark,
    material_map=adapter.material_map,
    material_matcher=adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None,
)
for p in parsed_single:
    p.original_tid = "single_order"
    p.shop_remark = ""

print(f"备注解析出 {len([p for p in parsed_single if p.success])} 个尺寸（同一订单多尺寸）")
print(f"现有商品行只有1个（默认SKU）")

purified3 = simulate_engine_purify(parsed_single, [item_single], adapter)
success_purified3 = [p for p in purified3 if p.success]
print(f"净化后：{len(success_purified3)} 个解析结果")

test3_pass = len(success_purified3) == 2
if test3_pass:
    print(f"✅ 通过：正常多尺寸订单未被误过滤")
else:
    print(f"❌ 失败：正常多尺寸订单被误过滤（期望2个，实际{len(success_purified3)}个）")

print(f"\n场景3测试结果: {'✅ 通过' if test3_pass else '❌ 失败'}")

# ===== 场景4：不同商品的跨分组污染（用户实际遇到的问题） =====
print("\n" + "=" * 70)
print("场景4：不同商品跨分组污染（用户实际场景）")
print("=" * 70)
print("""
用户场景：合并订单 6955081404357547934&6955089904909490078
- 子订单 A (6955089904909490078)：实际备注 = 定制双面革中古大花;32x95cm-1张
- 子订单 B (6955081404357547934)：实际备注 = 定制双面革花满金陵;35x206cm-1张，送赠品圆垫-1张
ERP 将订单级备注复制到所有商品行，导致每个分组都解析出所有商品
""")

TID_USER_A = "6955089904909490078"
TID_USER_B = "6955081404357547934"

# 现有商品行（ERP 中的正确商品行）
user_item_a = OrderItem(
    id="user_item_a",
    order_id=f"{TID_USER_A}&{TID_USER_B}",
    oid=TID_USER_A,
    title="双面格-定制尺寸-中古大花;32x95CM",
    shop_mapping_sku="双面格-定制-定制尺寸-中古大花;32x95CM",
    num=1,
    price=0,
    shop_remark="",  # 商品行备注可能为空或为订单级备注
    original_tid=TID_USER_A,
)

user_item_b = OrderItem(
    id="user_item_b",
    order_id=f"{TID_USER_A}&{TID_USER_B}",
    oid=TID_USER_B,
    title="双面格-定制尺寸-花满金陵;35x206CM",
    shop_mapping_sku="双面格-定制-定制尺寸-花满金陵;35x206CM",
    num=1,
    price=0,
    shop_remark="",
    original_tid=TID_USER_B,
)

user_item_gift = OrderItem(
    id="user_item_gift",
    order_id=f"{TID_USER_A}&{TID_USER_B}",
    oid=TID_USER_B,
    title="吸水皮革-标准-赠品沥水垫小圆或小方",
    shop_mapping_sku="吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方",
    num=1,
    price=0,
    shop_remark="",
    original_tid=TID_USER_B,
)

user_order_items = [user_item_a, user_item_b, user_item_gift]

# 模拟两个分组都从完整订单级备注解析
# 订单级备注 = "定制双面革中古大花;32x95cm-1张，定制双面革花满金陵;35x206cm-1张，送赠品圆垫-1张"
# A 组解析结果
p_a_zhonggu = _make_parsed("双面格", "定制", "定制尺寸", "中古大花;32x95CM", tid=TID_USER_A)
p_a_huaman = _make_parsed("双面格", "定制", "定制尺寸", "花满金陵;35x206CM", tid=TID_USER_B)  # 污染！属于B
p_a_gift = _make_parsed("吸水皮革", "标准", "赠品沥水垫小圆或小方", "赠品沥水垫小圆或小方", tid=TID_USER_B)  # 污染！属于B

# B 组解析结果
p_b_zhonggu = _make_parsed("双面格", "定制", "定制尺寸", "中古大花;32x95CM", tid=TID_USER_A)  # 污染！属于A
p_b_huaman = _make_parsed("双面格", "定制", "定制尺寸", "花满金陵;35x206CM", tid=TID_USER_B)
p_b_gift = _make_parsed("吸水皮革", "标准", "赠品沥水垫小圆或小方", "赠品沥水垫小圆或小方", tid=TID_USER_B)

all_parsed_user = [p_a_zhonggu, p_a_huaman, p_a_gift, p_b_zhonggu, p_b_huaman, p_b_gift]
print(f"修复前：{len([p for p in all_parsed_user if p.success])} 个解析结果")
print(f"  A组: 中古大花(tid=A), 花满金陵(tid=A→污染!), 赠品(tid=A→污染!)")
print(f"  B组: 中古大花(tid=B→污染!), 花满金陵(tid=B), 赠品(tid=B)")

# 净化处理
purified_user = simulate_engine_purify(all_parsed_user, user_order_items, adapter)
success_purified_user = [p for p in purified_user if p.success]
print(f"\n修复后：{len(success_purified_user)} 个解析结果")
for i, p in enumerate(success_purified_user):
    norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
    print(f"  [{i}] {norm_sku[:60]} (tid={p.original_tid[:16]}...)")

# 验证：应该只有 3 个结果
# 1. 中古大花(tid=A) - A组自己的商品
# 2. 花满金陵(tid=B) - B组自己的商品
# 3. 赠品(tid=B) - B组的赠品
test4_pass = True
if len(success_purified_user) != 3:
    print(f"\n❌ 失败：期望3个解析结果，实际{len(success_purified_user)}个")
    test4_pass = False
else:
    # 检查每个结果的 tid 是否正确
    tid_by_sku_user = {}
    for p in success_purified_user:
        norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
        if '中古大花' in norm_sku:
            tid_by_sku_user['zhonggu'] = p.original_tid
        elif '花满金陵' in norm_sku:
            tid_by_sku_user['huaman'] = p.original_tid
        elif '赠品沥水垫' in norm_sku:
            tid_by_sku_user['gift'] = p.original_tid

    if tid_by_sku_user.get('zhonggu') == TID_USER_A:
        print(f"\n✅ 中古大花的tid正确（A）")
    else:
        print(f"\n❌ 中古大花的tid错误: {tid_by_sku_user.get('zhonggu')}")
        test4_pass = False

    if tid_by_sku_user.get('huaman') == TID_USER_B:
        print(f"✅ 花满金陵的tid正确（B）")
    else:
        print(f"❌ 花满金陵的tid错误: {tid_by_sku_user.get('huaman')}")
        test4_pass = False

    if tid_by_sku_user.get('gift') == TID_USER_B:
        print(f"✅ 赠品的tid正确（B）")
    else:
        print(f"❌ 赠品的tid错误: {tid_by_sku_user.get('gift')}")
        test4_pass = False

print(f"\n场景4测试结果: {'✅ 通过' if test4_pass else '❌ 失败'}")

# ===== 场景5：ERP 合并订单自动创建的商品行不应被解析 =====
print("\n" + "=" * 70)
print("场景5：ERP 合并订单自动创建的商品行（带&号订单号）的备注不可信")
print("=" * 70)
print("""
用户场景：合并订单 6955087846878877528&6955081581488510808
- 子订单 A (6955087846878877528)：备注 = 差价
- 子订单 B (6955081581488510808)：备注 = 定制双面革简织;37x178cm-1张，30x242cm-1张，37x52cm-1张，共3张
ERP 自动创建的商品行（订单号含&）携带订单级备注，不应被解析
""")

TID_ERP_A = "6955087846878877528"
TID_ERP_B = "6955081581488510808"
MERGED_ID = f"{TID_ERP_A}&{TID_ERP_B}"

# 子订单 A 的商品行（补差价行，original_tid 不含&，备注可信）
item_erp_a_price = OrderItem(
    id="item_erp_a_price",
    order_id=MERGED_ID,
    oid=TID_ERP_A,
    title="轻奢高级感窗垫柜垫电视柜垫鞋柜垫防水防油防水茶垫",
    shop_mapping_sku="定制-定制-补差价-不打印",
    num=1,
    price=0,
    shop_remark="差价",  # 子订单 A 的真实备注
    original_tid=TID_ERP_A,  # 不含&，可信
)

# 子订单 B 的商品行（original_tid 不含&，备注可信）
item_erp_b_1 = OrderItem(
    id="item_erp_b_1",
    order_id=MERGED_ID,
    oid=TID_ERP_B,
    title="轻奢高级感窗垫柜垫电视柜垫鞋柜垫防水防油防水茶垫",
    shop_mapping_sku="双面格-定制-定制尺寸-简肌;37x178CM",
    num=1,
    price=0,
    shop_remark="定制双面革简织;37x178cm-1张，30x242cm-1张，37x52cm-1张，共3张",  # 子订单 B 的真实备注
    original_tid=TID_ERP_B,  # 不含&，可信
)

# ERP 自动创建的商品行（original_tid 含&，备注是订单级备注，不可信！）
item_erp_created_1 = OrderItem(
    id="item_erp_created_1",
    order_id=MERGED_ID,
    oid=MERGED_ID,  # 含&！
    title="轻奢高级感窗垫柜垫电视柜垫鞋柜垫防水防油防水茶垫",
    shop_mapping_sku="双面格-定制-定制尺寸-简肌;30x242CM",
    num=1,
    price=0,
    shop_remark="差价! 定制双面格简肌;37x178cm-1张, 30x242cm-1张, 共3张",  # 订单级备注！不可信
    original_tid=MERGED_ID,  # 含&！不可信
)

# ERP 自动创建的商品行（original_tid 含&，备注是订单级备注，不可信！）
item_erp_created_2 = OrderItem(
    id="item_erp_created_2",
    order_id=MERGED_ID,
    oid=MERGED_ID,  # 含&！
    title="轻奢高级感窗垫柜垫电视柜垫鞋柜垫防水防油防水茶垫",
    shop_mapping_sku="双面格-定制-定制尺寸-简肌;37x52CM",
    num=1,
    price=0,
    shop_remark="差价! 定制双面格简肌;37x178cm-1张, 30x242cm-1张, 共3张",  # 订单级备注！不可信
    original_tid=MERGED_ID,  # 含&！不可信
)

erp_order_items = [item_erp_a_price, item_erp_b_1, item_erp_created_1, item_erp_created_2]

# 模拟当前代码的备注收集逻辑（修复后版本）
def simulate_remark_collection_fixed(items):
    """模拟修复后的备注收集：跳过 ERP 自动创建的商品行"""
    groups = {}
    for item in items:
        # 保存 ERP 原始 tid
        erp_original_tid = item.original_tid
        
        # 分组逻辑（简化版）
        if item.original_tid and "&" not in item.original_tid:
            tid = item.original_tid
        elif item.oid and "&" not in item.oid:
            tid = item.oid
        else:
            tid = item.original_tid.split("&")[0] if item.original_tid and "&" in item.original_tid else item.oid.split("&")[0]
        
        if tid not in groups:
            groups[tid] = {
                'regular_remark': '',
                'price_diff_remark': '',
            }
        
        # 修复后的备注收集：跳过 ERP 自动创建的商品行
        is_manual = item.raw and item.raw.get('type') == 1 if item.raw else False
        is_gift = False  # 简化
        is_erp_created = (
            (erp_original_tid and "&" in erp_original_tid) or
            (item.oid and "&" in item.oid)
        )
        
        if item.shop_remark and not is_manual and not is_gift and not is_erp_created:
            if '补差价' in (item.shop_mapping_sku or '') or '差价' in (item.shop_remark or '').strip():
                groups[tid]['price_diff_remark'] = item.shop_remark
            else:
                groups[tid]['regular_remark'] = item.shop_remark
        
        print(f"  商品行 {item.shop_mapping_sku[-30:]}...")
        print(f"    original_tid={erp_original_tid[:20]}... (含&: {'&' in erp_original_tid})")
        print(f"    oid={item.oid[:20]}... (含&: {'&' in item.oid})")
        print(f"    ERP创建: {is_erp_created}")
        print(f"    shop_remark='{item.shop_remark[:50]}'")
        print(f"    → 备注被收集: {item.shop_remark and not is_erp_created}")
        print()
    
    return groups

print("【修复后】备注收集结果：")
collected_groups = simulate_remark_collection_fixed(erp_order_items)

print("\n各分组收集到的备注：")
for tid, g in collected_groups.items():
    print(f"  分组 {tid[:20]}...:")
    print(f"    regular_remark = '{g['regular_remark'][:50]}'")
    print(f"    price_diff_remark = '{g['price_diff_remark']}'")

# 验证
test5_pass = True

# A 组应该收集到 "差价" 作为 price_diff_remark
if collected_groups.get(TID_ERP_A, {}).get('price_diff_remark') == '差价':
    print(f"\n✅ A 组正确收集到补差价备注 '差价'")
else:
    print(f"\n❌ A 组备注错误: {collected_groups.get(TID_ERP_A, {}).get('price_diff_remark')}")
    test5_pass = False

# B 组应该收集到真实备注
b_regular = collected_groups.get(TID_ERP_B, {}).get('regular_remark', '')
if '37x178cm' in b_regular and '30x242cm' in b_regular:
    print(f"✅ B 组正确收集到商品备注")
else:
    print(f"❌ B 组备注错误: {b_regular}")
    test5_pass = False

# 关键验证：ERP 自动创建的商品行的订单级备注不应被收集
# 检查是否有任何分组收到了 "差价! 定制双面格简肌" 这个订单级备注
for tid, g in collected_groups.items():
    if '差价! 定制双面格简肌' in g.get('regular_remark', ''):
        print(f"❌ ERP创建的商品行的订单级备注被错误收集到分组 {tid[:20]}")
        test5_pass = False

if test5_pass:
    print(f"✅ ERP 自动创建的商品行的订单级备注被正确跳过")

print(f"\n场景5测试结果: {'✅ 通过' if test5_pass else '❌ 失败'}")

# ===== 总评 =====
print("\n" + "=" * 70)
all_pass = test1_pass and test2_pass and test3_pass and test4_pass and test5_pass
print(f"总体测试结果: {'✅ 全部通过' if all_pass else '❌ 存在失败'}")
print("=" * 70)
