import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from io import StringIO
import unittest.mock

from core.parser import parse_remark, extract_multiple_remarks
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter


def test_skip_if_already_correct():
    """测试：当商品编码已正确时，程序跳过修改"""
    print('=' * 80)
    print('测试：编码已正确时跳过修改')
    print('=' * 80)
    
    remark = "定制双面革花漾之约;60x120cm裁剪有图-1张"
    
    adapter = FangguoAdapter()
    material_map = adapter.material_map
    material_matcher = adapter.get_material_matcher()
    
    parsed_list = extract_multiple_remarks(remark, material_map=material_map, material_matcher=material_matcher)
    
    if not parsed_list:
        print('❌ 解析失败，无法进行测试')
        return False
    
    expected_sku = parsed_list[0].shop_mapping_sku
    print(f'期望编码: {expected_sku}')
    
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
        shop_mapping_sku=expected_sku,
    )
    
    order.items.append(item1)
    
    captured_output = StringIO()
    with unittest.mock.patch('sys.stdout', new=captured_output):
        ok = adapter.update_merchant_code(order, parsed_list[0], parsed_list, [])
    
    output = captured_output.getvalue()
    
    print(f'\n返回值: {ok}')
    print(f'\n输出内容:')
    print(output)
    
    if ok == True and '编码已正确，跳过修改' in output:
        print('\n✅ 测试通过：编码已正确时，程序跳过修改')
        return True
    else:
        print('\n❌ 测试失败：编码已正确但未跳过修改')
        return False


def test_modify_if_incorrect():
    """测试：当商品编码不正确时，程序执行修改"""
    print('\n' + '=' * 80)
    print('测试：编码不正确时执行修改')
    print('=' * 80)
    
    remark = "定制双面革花漾之约;60x120cm裁剪有图-1张"
    
    adapter = FangguoAdapter()
    material_map = adapter.material_map
    material_matcher = adapter.get_material_matcher()
    
    parsed_list = extract_multiple_remarks(remark, material_map=material_map, material_matcher=material_matcher)
    
    if not parsed_list:
        print('❌ 解析失败，无法进行测试')
        return False
    
    expected_sku = parsed_list[0].shop_mapping_sku
    print(f'期望编码: {expected_sku}')
    
    order = Order(
        id='123',
        trade_id='test_order_002',
        tid='test_order_002',
        shop_remark=remark,
        factory_id=1,
        store_name='测试店铺',
    )
    
    item1 = OrderItem(
        id='item1',
        order_id='test_order_002',
        oid='test_order_002',
        title='商品1',
        num=1,
        price=100.0,
        shop_mapping_sku='错误的编码-标准-标准-标准',
    )
    
    order.items.append(item1)
    
    captured_output = StringIO()
    with unittest.mock.patch('sys.stdout', new=captured_output):
        ok = adapter.update_merchant_code(order, parsed_list[0], parsed_list, [])
    
    output = captured_output.getvalue()
    
    print(f'\n返回值: {ok}')
    print(f'\n输出内容:')
    print(output)
    
    if ok != True or '编码已正确，跳过修改' not in output:
        print('\n✅ 测试通过：编码不正确时，程序执行修改')
        return True
    else:
        print('\n❌ 测试失败：编码不正确但被跳过')
        return False


if __name__ == '__main__':
    result1 = test_skip_if_already_correct()
    result2 = test_modify_if_incorrect()
    
    print('\n' + '=' * 80)
    if result1 and result2:
        print('🎉 所有测试通过！')
    else:
        print('❌ 部分测试失败')
    print('=' * 80)