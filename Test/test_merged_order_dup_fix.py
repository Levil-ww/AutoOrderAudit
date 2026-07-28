"""
测试：合并订单中订单级备注污染导致的重复商品行问题
场景：合并订单的某个商品行带有订单级备注（包含所有子订单的商品信息），
      解析后会生成重复的商品行。修复后应正确过滤。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

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
    """模拟 engine.py 中的合并订单净化逻辑"""
    # 构建现有商品行的 (normalized_sku, num) -> set of original_tid 映射
    existing_sku_tids = {}
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
            existing_sku_tids[key].add(item.original_tid or '')

    # a. 跨分组污染过滤
    filtered_parsed = []
    contamination_count = 0
    for p in all_parsed_list:
        if not p or not p.success:
            filtered_parsed.append(p)
            continue
        norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
        key = (norm_sku, p.num)
        existing_tids = existing_sku_tids.get(key, set())
        if existing_tids:
            if p.original_tid and p.original_tid in existing_tids:
                filtered_parsed.append(p)
            else:
                contamination_count += 1
        else:
            filtered_parsed.append(p)

    if contamination_count > 0:
        print(f"  🧹 合并订单净化：过滤掉 {contamination_count} 个跨分组污染的解析结果")

    # b. 同 SKU 去重
    success_parsed = [p for p in filtered_parsed if p and p.success]
    non_success_parsed = [p for p in filtered_parsed if p and not p.success]

    dedup_groups = {}
    for p in success_parsed:
        norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
        key = (norm_sku, p.num)
        if key not in dedup_groups:
            dedup_groups[key] = []
        dedup_groups[key].append(p)

    deduped_parsed = []
    dup_removed = 0
    for key, candidates in dedup_groups.items():
        if len(candidates) == 1:
            deduped_parsed.append(candidates[0])
            continue
        dup_removed += len(candidates) - 1
        best = None
        best_score = -1
        expected_tids = existing_sku_tids.get(key, set())
        expected_tid = next(iter(expected_tids)) if expected_tids else ''
        for p in candidates:
            score = 0
            if expected_tid and p.original_tid == expected_tid:
                score = 100
            elif p.original_tid and "&" not in p.original_tid:
                score = 50
            else:
                score = 0
            if score > best_score:
                best_score = score
                best = p
        if best:
            deduped_parsed.append(best)

    if dup_removed > 0:
        print(f"  🧹 合并订单去重：移除 {dup_removed} 个重复解析结果")

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

# ===== 总评 =====
print("\n" + "=" * 70)
all_pass = test1_pass and test2_pass and test3_pass
print(f"总体测试结果: {'✅ 全部通过' if all_pass else '❌ 存在失败'}")
print("=" * 70)
