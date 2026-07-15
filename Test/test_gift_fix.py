import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.parser import parse_remark, extract_multiple_remarks, _extract_gift
from adapters.fangguo.adapter import FangguoAdapter
from core.adapter_base import Order, OrderItem

print("=" * 60)
print("测试问题1：送随机赠品-2张")
print("=" * 60)

remark1 = "定制双面革中古大花;36x162cm-1张，36x314cm-1张，21.5x55cm-1张，56x155cm-1张，共计4张，送随机赠品-2张"

gift_name, gift_num = _extract_gift(remark1)
print(f"_extract_gift 结果: gift_name='{gift_name}', gift_num={gift_num}")

parsed_list1 = extract_multiple_remarks(remark1)
print(f"\nextract_multiple_remarks 返回 {len(parsed_list1)} 个解析结果:")
for i, p in enumerate(parsed_list1):
    print(f"  [{i}] shop_mapping_sku={p.shop_mapping_sku}, gift_name='{p.gift_name}', gift_num={p.gift_num}")

adapter = FangguoAdapter()
item = OrderItem(id="test", order_id="test", oid="test", num=1)
order = Order(trade_id="test", tid="test", shop_remark=remark1, items=[item])

if gift_name and gift_num > 0:
    gift_item = adapter._build_gift_item(item, order, "双面革", gift_name, gift_num)
    print(f"\n生成的赠品行编码:")
    print(f"  shopMappingSku: {gift_item['shopMappingSku']}")
    print(f"  filmGiftCode: {gift_item['filmGiftCode']}")
    print(f"  modelCode: {gift_item['modelCode']}")
    print(f"  pictureCode: {gift_item['pictureCode']}")

print("\n" + "=" * 60)
print("测试问题2：赠品换赠品沥水垫方垫30x50cm-1张")
print("=" * 60)

remark2 = "定制吸水皮革素花牡丹;74x173cm-1张  赠品换赠品沥水垫方垫30x50cm-1张"

gift_name2, gift_num2 = _extract_gift(remark2)
print(f"_extract_gift 结果: gift_name='{gift_name2}', gift_num={gift_num2}")

parsed_list2 = extract_multiple_remarks(remark2)
print(f"\nextract_multiple_remarks 返回 {len(parsed_list2)} 个解析结果:")
for i, p in enumerate(parsed_list2):
    print(f"  [{i}] shop_mapping_sku={p.shop_mapping_sku}, gift_name='{p.gift_name}', gift_num={p.gift_num}")

order2 = Order(trade_id="test2", tid="test2", shop_remark=remark2, items=[item])

if gift_name2 and gift_num2 > 0:
    gift_item2 = adapter._build_gift_item(item, order2, "吸水皮革", gift_name2, gift_num2)
    print(f"\n生成的赠品行编码:")
    print(f"  shopMappingSku: {gift_item2['shopMappingSku']}")
    print(f"  filmGiftCode: {gift_item2['filmGiftCode']}")
    print(f"  modelCode: {gift_item2['modelCode']}")
    print(f"  pictureCode: {gift_item2['pictureCode']}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)