"""
测试：分析订单备注是否会错误地修改补差价订单行

订单结构：
- 商品行1：2025新款入户门地垫皮革轻奢高级法式过门房门门厅客厅内
  - 规格: 100*140cm（米白/方形）
  - 当前编码: 镜面皮革-标准-100x140-果美方形;100x140
  
- 商品行2（补差价）：DMF新客运营专拍补差专拍少拍少几个
  - 规格: 136x139cm（方形）
  - 当前编码: 镜面皮革-定制-尺寸-果美（方形）;136x139CM

- 订单级备注: "老客加送苹果凳, 136x139, m-1级，皮做法"
"""

import sys
sys.path.insert(0, '.')

from core.parser import parse_remark, extract_multiple_remarks
from core.adapter_base import Order, OrderItem
from adapters.fangguo.config import MATERIAL_MAP

# 1. 分析备注解析结果
remark = "老客加送苹果凳, 136x139, m-1级，皮做法"
print("=" * 60)
print("【Step 1】备注解析分析")
print("=" * 60)
print(f"订单级备注: {remark}")

# 调用解析函数
parsed_list = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

print(f"\n解析结果数量: {len(parsed_list)}")
for i, p in enumerate(parsed_list):
    print(f"\n解析结果 {i+1}:")
    print(f"  success: {p.success}")
    print(f"  material_code: '{p.material_code}'")
    print(f"  color_code: '{p.color_code}'")
    print(f"  model_code: '{p.model_code}'")
    print(f"  picture_code: '{p.picture_code}'")
    print(f"  num: {p.num}")
    print(f"  SKU: {p.shop_mapping_sku}")
    print(f"  gift_name: '{p.gift_name}'")
    print(f"  gift_num: {p.gift_num}")
    print(f"  gifts: {p.gifts}")
    print(f"  is_stock: {p.is_stock}")

# 2. 分析补差价商品行识别
print("\n" + "=" * 60)
print("【Step 2】补差价商品行识别分析")
print("=" * 60)

# 创建模拟订单
order = Order(
    id="test_001",
    trade_id="3314126571001442",
    shop_remark=remark,
    tid="3314126571001442",
)

# 商品行1：正常商品
item1 = OrderItem(
    id="item_1",
    order_id="test_001",
    title="2025新款入户门地垫皮革轻奢高级法式过门房门门厅客厅内",
    shop_mapping_sku="镜面皮革-标准-100x140-果美方形;100x140",
    num=1,
    price=138.33,
    is_void=False,
    original_tid="sub_order_1",
)

# 商品行2：补差价商品
item2 = OrderItem(
    id="item_2",
    order_id="test_001",
    title="DMF新客运营专拍补差专拍少拍少几个",
    shop_mapping_sku="镜面皮革-定制-尺寸-果美（方形）;136x139CM",
    num=1,
    price=9.67,
    is_void=False,
    original_tid="sub_order_2",
)

order.items = [item1, item2]

# 模拟补差价商品行检测
_PRICE_DIFF_KEYWORDS = ["补差价专拍", "差价专用", "少几元拍几个"]

def _is_price_difference_item(item):
    if item.title:
        for keyword in _PRICE_DIFF_KEYWORDS:
            if keyword in item.title:
                return True
    sku = item.shop_mapping_sku or ''
    import re
    clean_sku = re.sub(r'<[^>]+>', '', sku)
    if clean_sku == '定制-定制-补差价-不打印':
        return True
    remark_item = item.shop_remark or ''
    stripped = remark_item.strip()
    if stripped in ('差价', '补差价', '补的差价'):
        return True
    if '差价不发货' in remark_item or '不打印' in remark_item or '不用发' in remark_item:
        return True
    return False

print(f"\n商品行1: '{item1.title[:30]}...'")
print(f"  _is_price_difference_item: {_is_price_difference_item(item1)}")

print(f"\n商品行2: '{item2.title[:30]}...'")
print(f"  _is_price_difference_item: {_is_price_difference_item(item2)}")
print(f"  标题中是否包含补差价关键词:")
for kw in _PRICE_DIFF_KEYWORDS:
    print(f"    '{kw}' in title: {kw in item2.title}")

# 3. 分析订单处理流程
print("\n" + "=" * 60)
print("【Step 3】订单处理流程分析")
print("=" * 60)

# 检查是否为补差价订单
is_price_diff_order = any(_is_price_difference_item(item) for item in order.items)
print(f"\n订单是否被识别为补差价订单: {is_price_diff_order}")

# 如果是补差价订单，分析 Scene 3 处理逻辑
if is_price_diff_order:
    print("\n进入 _process_price_difference_order 处理...")
    
    price_diff_items = [item for item in order.items if _is_price_difference_item(item)]
    only_price_diff = len(price_diff_items) == len(order.items)
    
    print(f"  补差价商品行数量: {len(price_diff_items)}")
    print(f"  是否只有补差价行: {only_price_diff}")
    
    # 场景1检查
    def _get_no_print_reason(remark):
        stripped = remark.strip()
        if not stripped:
            return "备注为空"
        if stripped == "补差价" or stripped == "差价":
            return f"备注为'{stripped}'"
        if "差价不发货" in remark:
            return "差价不发货"
        if "不用发" in remark:
            return "不用发"
        if "不打印" in remark:
            return "不打印"
        return None
    
    no_print_reason = _get_no_print_reason(remark)
    print(f"  场景1(不打印原因): {no_print_reason}")
    
    if no_print_reason:
        print("  → 将补差价行编码改为 '定制-定制-补差价-不打印'")
    elif only_price_diff and remark.strip():
        print("  → 场景2: 仅有补差价行+备注含信息 → 按正常解析处理")
    elif remark.strip():
        print("  → 场景3: 混合订单（普通行+补差价行）+备注非空")
        
        # 解析备注
        successful_parsed = [p for p in parsed_list if p.success]
        print(f"    成功解析的商品条目数: {len(successful_parsed)}")
        
        # 统计普通商品行数量
        regular_item_count = sum(
            1 for item in order.items
            if not _is_price_difference_item(item) and not item.is_void
        )
        print(f"    普通商品行数量: {regular_item_count}")
        
        # 计算额外解析结果
        extra_parsed = successful_parsed[regular_item_count:] if len(successful_parsed) > regular_item_count else []
        print(f"    分配给补差价行的额外解析结果数: {len(extra_parsed)}")
        
        if extra_parsed:
            print(f"    ⚠️  有 {len(extra_parsed)} 条解析结果将分配给补差价行！")
            for ep in extra_parsed:
                print(f"      - SKU: {ep.shop_mapping_sku}")
                print(f"      - 这将修改补差价行的编码！")
        else:
            print(f"    ✓ 无额外解析结果，补差价行将改为 '不打印'")

# 4. 核心问题分析
print("\n" + "=" * 60)
print("【Step 4】核心问题分析")
print("=" * 60)

print("""
问题场景：
- 订单包含1个商品行 + 1个补差价行
- 订单级备注: "老客加送苹果凳, 136x139, m-1级，皮做法"
- 备注中包含尺寸 "136x139"，恰好与补差价行的尺寸一致

关键分析点：
1. 备注中的 "136x139" 会被解析器识别为尺寸
2. 但备注中没有材质信息（如"镜面皮革"、"双面革"等）
3. 因此解析器无法成功解析（material_code 为空）
4. 最终结果：解析失败，successful_parsed 为空

结论：
- 当前备注无法被成功解析（缺少材质信息）
- 商品行1不会被修改 ✓
- 补差价行将被改为 "定制-定制-补差价-不打印"

潜在风险场景：
如果备注中包含材质信息，例如：
"镜面皮革, 老客加送苹果凳, 136x139, m-1级，皮做法"

此时解析器会：
1. 检测到 "镜面皮革" 材质
2. 提取尺寸 "136x139"
3. 成功解析为: 镜面皮革-标准-136x139-xxx;136x139

处理逻辑：
- 普通商品行数量: 1 (item1)
- 成功解析数: 1
- extra_parsed = successful_parsed[1:] = [] (空)
- 解析结果将分配给商品行1 ✓ (正确)
- 补差价行改为 "不打印" ✓ (正确)

但如果备注包含两个尺寸：
"镜面皮革, 100x140, 老客加送苹果凳, 136x139, m-1级"

此时解析器可能产生2个解析结果：
- 解析结果1: 100x140
- 解析结果2: 136x139

处理逻辑：
- 普通商品行数量: 1
- 成功解析数: 2
- extra_parsed = [解析结果2]
- ⚠️ 解析结果2 (136x139) 将分配给补差价行！
- 补差价行被错误地修改为商品编码！
""")

# 5. 最终结论
print("\n" + "=" * 60)
print("【Step 5】最终结论")
print("=" * 60)

successful_count = len([p for p in parsed_list if p.success])
print(f"\n当前备注解析结果:")
print(f"  - 成功解析: {successful_count} 条")
print(f"  - 解析失败: {len(parsed_list) - successful_count} 条")

if successful_count == 0:
    print("\n✓ 当前备注因缺少材质信息无法成功解析")
    print("✓ 商品行不会被错误修改")
    print("✓ 补差价行将被正确处理为'不打印'")
    print("\n但存在以下风险：")
    print("⚠️ 如果备注后续补充了材质信息，可能导致：")
    print("   - 解析出的尺寸(136x139)被误判为补差价行的尺寸")
    print("   - 在多尺寸场景下，补差价行可能被错误修改")
else:
    print("\n⚠️ 备注解析成功！")
    print("  需要检查解析结果是否会被错误分配给补差价行")

print("\n" + "=" * 60)
print("分析完成")
print("=" * 60)
