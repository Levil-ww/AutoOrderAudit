import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.parser import extract_multiple_remarks, parse_remark, _extract_multiple_gifts
from adapters.fangguo.adapter import FangguoAdapter
from core.adapter_base import Order, OrderItem

print("=" * 60)
print("测试商品行和赠品行去重逻辑")
print("=" * 60)

print("\n--- 测试1: 商品行去重 - 相同规格重复出现 ---")
remark_dup_product = "定制吸水皮革素花牡丹;74x173cm-1张，定制吸水皮革素花牡丹;74x173cm-1张"
parsed_list = extract_multiple_remarks(remark_dup_product)
print(f"备注: {remark_dup_product}")
print(f"解析结果数量: {len(parsed_list)}")
for i, p in enumerate(parsed_list):
    print(f"  [{i}] sku='{p.shop_mapping_sku}', num={p.num}, success={p.success}")
expected_num = 2
actual_num = parsed_list[0].num if parsed_list else 0
print(f"期望数量: {expected_num}, 实际数量: {actual_num}")
print(f"测试结果: {'✅ 通过' if len(parsed_list) == 1 and actual_num == expected_num else '❌ 失败'}")

print("\n--- 测试2: 商品行去重 - 不同规格不合并 ---")
remark_diff_product = "定制吸水皮革素花牡丹;74x173cm-1张，定制吸水皮革克罗印花;60x200cm-1张"
parsed_list = extract_multiple_remarks(remark_diff_product)
print(f"备注: {remark_diff_product}")
print(f"解析结果数量: {len(parsed_list)}")
for i, p in enumerate(parsed_list):
    print(f"  [{i}] sku='{p.shop_mapping_sku}', num={p.num}")
print(f"测试结果: {'✅ 通过' if len(parsed_list) == 2 else '❌ 失败'}")

print("\n--- 测试3: 赠品行去重 - 相同赠品重复出现 ---")
remark_dup_gift = "定制吸水皮革素花牡丹;74x173cm-1张，送圆垫-1张，送圆垫-1张"
parsed_list = extract_multiple_remarks(remark_dup_gift)
print(f"备注: {remark_dup_gift}")
if parsed_list:
    gifts = parsed_list[0].gifts
    print(f"提取的赠品列表: {gifts}")
    print(f"测试结果: {'✅ 通过' if len(gifts) == 1 else '❌ 失败'}")
else:
    print("❌ 解析失败")

print("\n--- 测试4: 赠品行去重 - 不同赠品不合并 ---")
remark_diff_gift = "定制吸水皮革素花牡丹;74x173cm-1张，送圆垫-1张，送方垫-1张"
parsed_list = extract_multiple_remarks(remark_diff_gift)
print(f"备注: {remark_diff_gift}")
if parsed_list:
    gifts = parsed_list[0].gifts
    print(f"提取的赠品列表: {gifts}")
    print(f"测试结果: {'✅ 通过' if len(gifts) == 2 else '❌ 失败'}")
else:
    print("❌ 解析失败")

print("\n--- 测试5: 适配器级赠品行去重 ---")
adapter = FangguoAdapter()
item = OrderItem(id="test", order_id="test", oid="test", num=1)
order = Order(trade_id="test", tid="test", shop_remark="送圆垫-1张，送圆垫-2张", items=[item])

parsed_list = extract_multiple_remarks(order.shop_remark)
effective_list = [p for p in parsed_list if p.success or p.gifts]

all_gifts = []
for p in effective_list:
    if p.gifts:
        all_gifts.extend(p.gifts)
    elif p.gift_name and p.gift_num > 0:
        all_gifts.append((p.gift_name, p.gift_num))

unique_gifts = {}
for gift_name, gift_num in all_gifts:
    if gift_name in unique_gifts:
        unique_gifts[gift_name] += gift_num
    else:
        unique_gifts[gift_name] = gift_num
all_gifts = [(name, num) for name, num in unique_gifts.items()]

print(f"原始赠品列表: [('圆垫', 1), ('圆垫', 2)]")
print(f"去重后赠品列表: {all_gifts}")
print(f"测试结果: {'✅ 通过' if all_gifts == [('圆垫', 3)] else '❌ 失败'}")

print("\n--- 测试6: 合并订单场景下的赠品处理（按子订单分组）---")
remark_merged = "订单A:定制吸水皮革素花牡丹;74x173cm-1张，送圆垫-1张&订单B:定制吸水皮革素花牡丹;74x173cm-1张，送圆垫-1张"
print(f"合并订单备注: {remark_merged}")
print("说明：两个子订单各有相同的赠品'圆垫'，应该分别创建2个赠品行，而不是合并为1个")

parts = remark_merged.split("&")
all_parsed = []
for i, part in enumerate(parts):
    parsed = extract_multiple_remarks(part)
    # 模拟 engine.py 的处理：为每个解析结果设置 original_tid
    for p in parsed:
        p.original_tid = f"订单{i+1}" if i == 0 else f"订单{i+1}"
    all_parsed.extend(parsed)

print(f"每个子订单解析结果:")
for i, p in enumerate(all_parsed):
    print(f"  [{i}] sku='{p.shop_mapping_sku[:30]}', num={p.num}, gifts={p.gifts}, original_tid='{p.original_tid}'")

# 模拟 adapter.py 的赠品分组逻辑
gifts_by_tid = {}
for p in all_parsed:
    if p.gifts:
        tid = p.original_tid or ""
        if tid not in gifts_by_tid:
            gifts_by_tid[tid] = {'gifts': [], 'material_code': '', 'shop_remark': ''}
        gifts_by_tid[tid]['gifts'].extend(p.gifts)
        if p.material_code:
            gifts_by_tid[tid]['material_code'] = p.material_code
        if p.shop_remark:
            gifts_by_tid[tid]['shop_remark'] = p.shop_remark

# 收集所有赠品（按子订单分组去重后）
all_gifts = []
for tid, gift_info in gifts_by_tid.items():
    # 每个子订单内部去重
    unique_gifts = {}
    for gift_name, gift_num in gift_info['gifts']:
        if gift_name in unique_gifts:
            unique_gifts[gift_name] += gift_num
        else:
            unique_gifts[gift_name] = gift_num
    for name, num in unique_gifts.items():
        all_gifts.append((name, num, tid))

print(f"按子订单分组后的赠品列表: {all_gifts}")
print(f"期望结果: [('圆垫', 1, '订单1'), ('圆垫', 1, '订单2')] - 两个独立的赠品行")

# 验证：应该是2个赠品行，每个子订单各1个
expected_gifts = [('圆垫', 1, '订单1'), ('圆垫', 1, '订单2')]
test_pass = len(all_gifts) == 2
for expected_name, expected_num, expected_tid in expected_gifts:
    found = False
    for name, num, tid in all_gifts:
        if name == expected_name and num == expected_num and tid == expected_tid:
            found = True
            break
    if not found:
        test_pass = False
        break

print(f"测试结果: {'✅ 通过' if test_pass else '❌ 失败'}")

print("\n--- 测试7: 同一子订单内的赠品合并 ---")
remark_same_order = "定制吸水皮革素花牡丹;74x173cm-2张，送圆垫-1张，送圆垫-1张"
print(f"备注: {remark_same_order}")
print("说明：同一订单内有2个相同的赠品，应该合并为1个赠品行（数量为2）")

parsed_list = extract_multiple_remarks(remark_same_order)
if parsed_list:
    gifts = parsed_list[0].gifts
    print(f"提取的赠品列表: {gifts}")
    print(f"期望结果: [('圆垫', 2)]")
    print(f"测试结果: {'✅ 通过' if gifts == [('圆垫', 2)] else '❌ 失败'}")
else:
    print("❌ 解析失败")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)