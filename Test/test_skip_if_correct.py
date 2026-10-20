import re
import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from io import StringIO
import unittest.mock
import pytest

from core.parser import parse_remark, extract_multiple_remarks
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter



@pytest.fixture(autouse=True)
def offline_save_product(monkeypatch):
    """仅 mock 商品保存接口；断言其他请求，禁止测试访问真实 ERP。"""
    from adapters.fangguo.config import API_SAVE_PRODUCT
    response = unittest.mock.Mock()
    response.json.return_value = {"code": 0, "data": True}

    def save(url, **kwargs):
        assert url == API_SAVE_PRODUCT
        return response

    post = unittest.mock.Mock(side_effect=save)
    monkeypatch.setattr("requests.sessions.Session.post", post)
    return post

def test_skip_if_already_correct(offline_save_product):
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
        assert False, '解析失败'

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
    
    assert ok is True
    assert '编码已正确，跳过修改' in output
    offline_save_product.assert_not_called()


def test_modify_if_incorrect(offline_save_product):
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
        assert False, '解析失败'

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
    
    assert ok is True
    offline_save_product.assert_called_once()
    payload = offline_save_product.call_args.kwargs["json"]
    active = [item for item in payload["orderItems"] if not item.get("cancelStatus") and not item.get("discardStatus")]
    assert len(active) == 1
    assert active[0]["id"] == "item1"
    assert re.sub(r'<[^>]+>', '', active[0]["shopMappingSku"]) == expected_sku
    assert active[0]["num"] == 1


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
