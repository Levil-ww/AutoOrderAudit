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

print('=' * 80)
print('测试赠品编码逻辑')
print('=' * 80)

test_cases = [
    ('圆垫', 2),
    ('方垫', 3),
    ('赠品圆垫一张', 1),
    ('送方垫两个', 2),
    ('普通赠品', 1),
]

for gift_name, gift_num in test_cases:
    gift_item = adapter._build_gift_item(item, order, '吸水皮革', gift_name, gift_num)
    print(f'\n赠品名称: "{gift_name}" x {gift_num}')
    print(f'shopMappingSku: {gift_item.get("shopMappingSku")}')
    print(f'materialCode: {gift_item.get("materialCode")}')
    print(f'modelCode: {gift_item.get("modelCode")}')
    print(f'colorCode: {gift_item.get("colorCode")}')
    print(f'pictureCode: {gift_item.get("pictureCode")}')
    print(f'giftCodeName: {gift_item.get("giftCodeName")}')
    print(f'filmGiftCode: {gift_item.get("filmGiftCode")}')
    print(f'filmGiftNum: {gift_item.get("filmGiftNum")}')

print('\n' + '=' * 80)
print('预期结果验证')
print('=' * 80)
print('包含"圆垫"的赠品:')
print('  shopMappingSku 应包含: 吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方')
print('\n包含"方垫"的赠品:')
print('  shopMappingSku 应包含: 吸水皮革-标准-30x50-随机发；30x50')
print('\n其他赠品(默认):')
print('  shopMappingSku 应包含: 吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方')