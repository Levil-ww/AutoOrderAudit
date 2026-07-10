from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter

adapter = FangguoAdapter()

order = Order(
    id='123',
    trade_id='6954358067748672742',
    tid='6954358067748672742',
    factory_id=1,
    store_name='测试店铺',
)

item = OrderItem(
    id='item1',
    order_id='6954358067748672742',
    oid='6954358067748672742',
    title='商品1',
    num=1,
    price=100.0,
)

gift_item = adapter._build_gift_item(item, order, '吸水皮革', '赠品', 1)

print('=' * 80)
print('赠品行编码')
print('=' * 80)
print(f'shopMappingSku: {gift_item.get("shopMappingSku")}')
print(f'num: {gift_item.get("num")}')
