import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from adapters.fangguo.adapter import FangguoAdapter
from core.adapter_base import Order, OrderItem
from core.parser import ParsedRemark

adapter = FangguoAdapter()
order = Order(trade_id='test', tid='test', shop_remark='')
item = OrderItem(id='item1', order_id='test', oid='test', num=1)

print("=" * 60)
print("测试：新建商品行（手工单）的商家编码红色标记")
print("=" * 60)

parsed = ParsedRemark(
    material_code='双面革',
    color_code='定制',
    model_code='定制尺寸',
    picture_code='戴安娜;58x81.5CM',
    num=1,
    success=True,
)

new_item = adapter._build_new_item(order, parsed)
print(f"\n新建商品行 shopMappingSku: {new_item['shopMappingSku']}")

print("\n" + "=" * 60)
print("测试：新建赠品行的商家编码红色标记")
print("=" * 60)

gift_item_new = adapter._build_gift_item(item, order, '吸水皮革', '圆垫', 1, is_new=True)
print(f"\n新建赠品行(is_new=True) shopMappingSku: {gift_item_new['shopMappingSku']}")

gift_item_update = adapter._build_gift_item(item, order, '吸水皮革', '圆垫', 1, is_new=False)
print(f"更新赠品行(is_new=False) shopMappingSku: {gift_item_update['shopMappingSku']}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)