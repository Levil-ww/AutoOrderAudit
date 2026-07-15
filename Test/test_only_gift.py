import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.parser import extract_multiple_remarks, _extract_gift
from adapters.fangguo.adapter import FangguoAdapter
from core.adapter_base import Order, OrderItem

print("=" * 60)
print("测试：仅含赠品说明的备注")
print("=" * 60)

remark1 = "送赠品圆垫-1张"
print(f"\n备注: '{remark1}'")

gift_name, gift_num = _extract_gift(remark1)
print(f"_extract_gift 结果: gift_name='{gift_name}', gift_num={gift_num}")

parsed_list1 = extract_multiple_remarks(remark1)
print(f"extract_multiple_remarks 返回 {len(parsed_list1)} 个解析结果:")
for i, p in enumerate(parsed_list1):
    print(f"  [{i}] success={p.success}, gift_name='{p.gift_name}', gift_num={p.gift_num}, material_code='{p.material_code}'")

print("\n" + "=" * 60)
print("测试：仅赠品场景下的赠品行构建")
print("=" * 60)

adapter = FangguoAdapter()
item = OrderItem(id="test", order_id="test", oid="test", num=1, shop_mapping_sku="原有商品编码")
order = Order(trade_id="test", tid="test", shop_remark=remark1, items=[item])

parsed = parsed_list1[0]
if parsed.gift_name and parsed.gift_num > 0:
    gift_item = adapter._build_gift_item(item, order, "吸水皮革", parsed.gift_name, parsed.gift_num)
    print(f"\n生成的赠品行编码:")
    print(f"  shopMappingSku: {gift_item['shopMappingSku']}")
    print(f"  filmGiftCode: '{gift_item['filmGiftCode']}'")
    print(f"  filmGiftNum: {gift_item['filmGiftNum']}")
    print(f"  modelCode: {gift_item['modelCode']}")
    print(f"  pictureCode: {gift_item['pictureCode']}")
    print(f"  title: '{gift_item['title']}'")
    print(f"  num: {gift_item['num']}")

print("\n" + "=" * 60)
print("测试：含定制信息和赠品的备注（确保原有逻辑不变）")
print("=" * 60)

remark2 = "定制吸水皮革素花牡丹;74x173cm-1张，送赠品圆垫-1张"
print(f"\n备注: '{remark2}'")

parsed_list2 = extract_multiple_remarks(remark2)
print(f"extract_multiple_remarks 返回 {len(parsed_list2)} 个解析结果:")
for i, p in enumerate(parsed_list2):
    print(f"  [{i}] success={p.success}, shop_mapping_sku={p.shop_mapping_sku}, gift_name='{p.gift_name}', gift_num={p.gift_num}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)