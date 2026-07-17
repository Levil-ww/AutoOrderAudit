import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.parser import _extract_gift, _extract_multiple_gifts, parse_remark, extract_multiple_remarks
from adapters.fangguo.adapter import FangguoAdapter
from core.adapter_base import Order, OrderItem

print("=" * 60)
print("测试多赠品解析逻辑")
print("=" * 60)

test_cases = [
    ("送防滑垫一张", [("防滑垫", 1)]),
    ("送沥水垫25cm-1张", [("沥水垫25cm", 1)]),
    ("送防滑垫一张，送抹布一块", [("防滑垫", 1), ("抹布", 1)]),
    ("正常发，送赠品圆垫-2张，赠品方垫-1张", [("圆垫", 2), ("方垫", 1)]),
    ("赠品：防滑垫", [("防滑垫", 1)]),
    ("附赠收纳袋", [("收纳袋", 1)]),
    ("小垫子总共送2个", [("小垫子", 2)]),
    ("总共送2个小垫子", [("小垫子", 2)]),
    ("定制双面革花漾之约;35.5x124cm-1张，送沥水垫25cm-1张", [("沥水垫25cm", 1)]),
    ("定制吸水皮革素花牡丹;74x173cm-1张 赠品换赠品沥水垫方垫30x50cm-1张", [("沥水垫方垫30x50cm", 1)]),
    ("送随机赠品-2张", [("随机赠品", 2)]),
    ("送圆垫*1", [("圆垫", 1)]),
    ("送方垫一张", [("方垫", 1)]),
    ("送赠品一张", []),
]

print("\n--- 测试 _extract_multiple_gifts ---")
all_pass = True
for remark, expected in test_cases:
    gifts = _extract_multiple_gifts(remark)
    status = '✅' if gifts == expected else '❌'
    if gifts != expected:
        all_pass = False
    print(f'{status} 备注: {remark[:50]}')
    print(f'    提取结果: {gifts}')
    print(f'    期望结果: {expected}')
    print()

print("\n--- 测试用户问题场景：正常发，送赠品圆垫-2张，赠品方垫-1张 ---")
remark_problem = "正常发，送赠品圆垫-2张，赠品方垫-1张"
gifts = _extract_multiple_gifts(remark_problem)
print(f"备注: {remark_problem}")
print(f"提取的赠品列表: {gifts}")
print(f"期望: [('圆垫', 2), ('方垫', 1)]")
print(f"测试结果: {'✅ 通过' if gifts == [('圆垫', 2), ('方垫', 1)] else '❌ 失败'}")

print("\n--- 测试 parse_remark 中的多赠品 ---")
parsed = parse_remark(remark_problem)
print(f"备注: {remark_problem}")
print(f"gift_name: '{parsed.gift_name}', gift_num: {parsed.gift_num}")
print(f"gifts: {parsed.gifts}")
print(f"测试结果: {'✅ 通过' if parsed.gifts == [('圆垫', 2), ('方垫', 1)] else '❌ 失败'}")

print("\n--- 测试 extract_multiple_remarks 中的多赠品 ---")
parsed_list = extract_multiple_remarks(remark_problem)
print(f"备注: {remark_problem}")
print(f"返回 {len(parsed_list)} 个解析结果")
for i, p in enumerate(parsed_list):
    print(f"  [{i}] gift_name='{p.gift_name}', gift_num={p.gift_num}, gifts={p.gifts}")
if parsed_list:
    has_correct_gifts = parsed_list[0].gifts == [('圆垫', 2), ('方垫', 1)]
    print(f"测试结果: {'✅ 通过' if has_correct_gifts else '❌ 失败'}")

print("\n--- 测试带商品信息的多赠品场景 ---")
remark_with_product = "定制吸水皮革克罗印花;60x200cm-1张，正常发，送赠品圆垫-2张，赠品方垫-1张"
parsed_with_product = parse_remark(remark_with_product)
print(f"备注: {remark_with_product[:60]}...")
print(f"success: {parsed_with_product.success}")
print(f"material_code: {parsed_with_product.material_code}")
print(f"model_code: {parsed_with_product.model_code}")
print(f"picture_code: {parsed_with_product.picture_code}")
print(f"gifts: {parsed_with_product.gifts}")
expected_gifts = [('圆垫', 2), ('方垫', 1)]
print(f"测试结果: {'✅ 通过' if parsed_with_product.gifts == expected_gifts else '❌ 失败'}")

print("\n--- 测试 adapter _build_gift_item 对不同赠品的编码生成 ---")
adapter = FangguoAdapter()
item = OrderItem(id="test", order_id="test", oid="test", num=1)
order = Order(trade_id="test", tid="test", shop_remark=remark_problem, items=[item])

test_gifts = [("圆垫", 2), ("方垫", 1)]
for gift_name, gift_num in test_gifts:
    gift_item = adapter._build_gift_item(item, order, "吸水皮革", gift_name, gift_num, is_new=True)
    print(f"\n赠品: {gift_name} x {gift_num}")
    print(f"  shopMappingSku: {gift_item['shopMappingSku']}")
    print(f"  modelCode: {gift_item['modelCode']}")
    print(f"  pictureCode: {gift_item['pictureCode']}")
    print(f"  num: {gift_item['num']}")

print("\n" + "=" * 60)
print("测试完成")
print(f"整体结果: {'✅ 全部通过' if all_pass else '❌ 存在失败'}")
print("=" * 60)