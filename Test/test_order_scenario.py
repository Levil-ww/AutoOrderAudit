import sys
sys.path.insert(0, 'd:\AutoOrderAudit')

from core.parser import parse_remark, extract_multiple_remarks
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter

remark = "定制双面革花漾之约;60x120cm裁剪有图-1张，直径60cm-1张，共2张，送赠品圆垫-1张，赠品方垫-1张"

print('=' * 80)
print('测试订单备注解析')
print('=' * 80)
print(f'备注原文: {remark}')
print()

adapter = FangguoAdapter()
material_map = adapter.material_map
material_matcher = adapter.get_material_matcher()

parsed_list = extract_multiple_remarks(remark, material_map=material_map, material_matcher=material_matcher)

print('=' * 80)
print('解析结果')
print('=' * 80)
for i, parsed in enumerate(parsed_list):
    print(f'\n商品{i+1}:')
    print(f'  success: {parsed.success}')
    print(f'  material_code: {parsed.material_code}')
    print(f'  color_code: {parsed.color_code}')
    print(f'  model_code: {parsed.model_code}')
    print(f'  picture_code: {parsed.picture_code}')
    print(f'  num: {parsed.num}')
    print(f'  shop_mapping_sku: {parsed.shop_mapping_sku}')
    print(f'  gift_name: "{parsed.gift_name}"')
    print(f'  gift_num: {parsed.gift_num}')

print()
print('=' * 80)
print('赠品处理模拟')
print('=' * 80)

order = Order(
    id='123',
    trade_id='test_order_001',
    tid='test_order_001',
    shop_remark=remark,
    factory_id=1,
    store_name='测试店铺',
)

item1 = OrderItem(
    id='item1',
    order_id='test_order_001',
    oid='test_order_001',
    title='商品1',
    num=1,
    price=100.0,
)

item2 = OrderItem(
    id='item2',
    order_id='test_order_001',
    oid='test_order_001',
    title='商品2',
    num=1,
    price=100.0,
)

order.items.append(item1)
order.items.append(item2)

for parsed in parsed_list:
    if parsed.gift_name and parsed.gift_num > 0:
        print(f'\n赠品名称: "{parsed.gift_name}" x {parsed.gift_num}')
        gift_item = adapter._build_gift_item(item1, order, parsed.material_code, parsed.gift_name, parsed.gift_num)
        print(f'  shopMappingSku: {gift_item.get("shopMappingSku")}')
        print(f'  materialCode: {gift_item.get("materialCode")}')
        print(f'  modelCode: {gift_item.get("modelCode")}')
        print(f'  colorCode: {gift_item.get("colorCode")}')
        print(f'  pictureCode: {gift_item.get("pictureCode")}')
        print(f'  filmGiftNum: {gift_item.get("filmGiftNum")}')