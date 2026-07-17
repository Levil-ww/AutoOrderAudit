import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from adapters.fangguo.adapter import FangguoAdapter
from core.adapter_base import Order, OrderItem
from core.parser import ParsedRemark

adapter = FangguoAdapter()
order = Order(trade_id='test', tid='test', shop_remark='')
item = OrderItem(id='item1', order_id='test', oid='test', num=1)

parsed = ParsedRemark(
    material_code='双面革',
    color_code='定制',
    model_code='定制尺寸',
    picture_code='测试',
    num=1,
    success=True,
)

print('=' * 60)
print('测试：新建商品行 type 字段')
print('=' * 60)

new_item = adapter._build_new_item(order, parsed)
print(f'\n_build_new_item type: {new_item["type"]}')
assert new_item['type'] == 1, f'期望 type=1，实际 type={new_item["type"]}'

default_item = adapter._build_default_item(order, parsed)
print(f'_build_default_item type: {default_item["type"]}')
assert default_item['type'] == 1, f'期望 type=1，实际 type={default_item["type"]}'

print()
print('=' * 60)
print('测试：赠品行 type 字段')
print('=' * 60)

gift_new = adapter._build_gift_item(item, order, '吸水皮革', '圆垫', 1, is_new=True)
print(f'\ngift is_new=True type: {gift_new["type"]}')
assert gift_new['type'] == 1, f'期望 type=1，实际 type={gift_new["type"]}'

gift_update = adapter._build_gift_item(item, order, '吸水皮革', '圆垫', 1, is_new=False)
print(f'gift is_new=False type: {gift_update["type"]}')
assert gift_update['type'] == 0, f'期望 type=0，实际 type={gift_update["type"]}'

print()
print('=' * 60)
print('测试：更新现有商品行 type 字段（应保持为0）')
print('=' * 60)

order_item = adapter._build_order_item(item, order, parsed)
print(f'\n_build_order_item (update existing) type: {order_item["type"]}')
assert order_item['type'] == 0, f'期望 type=0，实际 type={order_item["type"]}'

print()
print('=' * 60)
print('所有测试通过！✅')
print('=' * 60)
