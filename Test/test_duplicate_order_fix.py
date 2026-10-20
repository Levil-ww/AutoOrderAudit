import sys
import re
sys.path.insert(0, 'd:\\AutoOrderAudit')

from io import StringIO
import unittest.mock
import pytest

from core.parser import parse_remark, extract_multiple_remarks
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter


def _clean_sku(sku: str) -> str:
    """清理SKU中的HTML标签"""
    return re.sub(r'<[^>]+>', '', sku or '')



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

def test_duplicate_items_should_clean_and_save(offline_save_product):
    """测试：当订单存在重复商品行时，清理重复行后保存"""
    print('=' * 80)
    print('测试：重复商品行场景 - 清理后保存')
    print('=' * 80)
    
    remark = "定制双面格蔓生花;27.5x79.5cm裁剪有图-1张"
    
    adapter = FangguoAdapter()
    material_map = adapter.material_map
    material_matcher = adapter.get_material_matcher()
    
    parsed_list = extract_multiple_remarks(remark, material_map=material_map, material_matcher=material_matcher)
    
    if not parsed_list or not parsed_list[0].success:
        print('❌ 解析失败，无法进行测试')
        assert False, '解析失败'

    expected_sku = parsed_list[0].shop_mapping_sku
    expected_num = parsed_list[0].num
    print(f'期望编码: {expected_sku}')
    print(f'期望数量: {expected_num}')
    
    # 模拟订单中有2个相同编码的商品行（重复场景）
    order = Order(
        id='123',
        trade_id='test_order_duplicate',
        tid='test_order_duplicate',
        shop_remark=remark,
        factory_id=1,
        store_name='测试店铺',
    )
    
    # 第一个商品行（正确编码）
    item1 = OrderItem(
        id='item1',
        order_id='test_order_duplicate',
        oid='test_order_duplicate',
        title='商品1',
        num=expected_num,
        price=100.0,
        shop_mapping_sku=expected_sku,
    )
    
    # 第二个商品行（重复的正确编码 - 模拟程序第一次运行后创建的手工单）
    item2 = OrderItem(
        id='item2',
        order_id='test_order_duplicate',
        oid='test_order_duplicate',
        title='商品1',
        num=expected_num,
        price=100.0,
        shop_mapping_sku=expected_sku,
    )
    
    order.items.append(item1)
    order.items.append(item2)
    
    print(f'订单商品行数: {len(order.items)}')
    print(f'解析结果数: {len(parsed_list)}')
    print(f'有效商品行数(排除赠品/补差价): {len([i for i in order.items if not adapter._is_gift_item(i) and not adapter._is_price_difference_item(i) and not i.is_void])}')
    
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
    removed = [item for item in payload["orderItems"] if item.get("cancelStatus")]
    assert len(active) == 1
    assert _clean_sku(active[0]["shopMappingSku"]) == expected_sku
    assert active[0]["num"] == expected_num
    assert {item["id"] for item in removed} == {item.id for item in order.items} - {active[0]["id"]}
    assert len(removed) == 1
    assert payload["totalCount"] == 1


def test_normal_single_item_should_skip(offline_save_product):
    """测试：正常单个商品行场景 - 应该跳过修改"""
    print('\n' + '=' * 80)
    print('测试：正常单个商品行场景 - 应该跳过修改')
    print('=' * 80)
    
    remark = "定制双面革花漾之约;60x120cm裁剪有图-1张"
    
    adapter = FangguoAdapter()
    material_map = adapter.material_map
    material_matcher = adapter.get_material_matcher()
    
    parsed_list = extract_multiple_remarks(remark, material_map=material_map, material_matcher=material_matcher)
    
    if not parsed_list or not parsed_list[0].success:
        print('❌ 解析失败，无法进行测试')
        assert False, '解析失败'

    expected_sku = parsed_list[0].shop_mapping_sku
    expected_num = parsed_list[0].num
    print(f'期望编码: {expected_sku}')
    
    order = Order(
        id='123',
        trade_id='test_order_normal',
        tid='test_order_normal',
        shop_remark=remark,
        factory_id=1,
        store_name='测试店铺',
    )
    
    item1 = OrderItem(
        id='item1',
        order_id='test_order_normal',
        oid='test_order_normal',
        title='商品1',
        num=expected_num,
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


def test_multiple_same_sku_should_clean_and_save(offline_save_product):
    """测试：多个相同SKU的商品行 - 应该清理后保存
    
    场景：程序第一次运行后，订单中已有正确编码的商品行，
    第二次运行应保留一条有效商品行，将多余行作废后保存。
    """
    print('\n' + '=' * 80)
    print('测试：多个相同SKU场景 - 清理后保存')
    print('=' * 80)
    
    remark = "定制双面革克罗印花;60x200cm裁剪有图-1张"
    
    adapter = FangguoAdapter()
    material_map = adapter.material_map
    material_matcher = adapter.get_material_matcher()
    
    parsed_list = extract_multiple_remarks(remark, material_map=material_map, material_matcher=material_matcher)
    
    if not parsed_list or not parsed_list[0].success:
        print('❌ 解析失败，无法进行测试')
        assert False, '解析失败'

    expected_sku = parsed_list[0].shop_mapping_sku
    expected_num = parsed_list[0].num
    print(f'期望编码: {expected_sku}')
    print(f'期望数量: {expected_num}')
    
    # 模拟订单中有3个相同编码的商品行（模拟多次运行后）
    # 每个商品行的编码和数量都与期望一致
    order = Order(
        id='123',
        trade_id='test_order_multi',
        tid='test_order_multi',
        shop_remark=remark,
        factory_id=1,
        store_name='测试店铺',
    )
    
    for i in range(3):
        item = OrderItem(
            id=f'item{i+1}',
            order_id='test_order_multi',
            oid='test_order_multi',
            title=f'商品{i+1}',
            num=expected_num,  # 每个商品行数量与期望一致
            price=100.0,
            shop_mapping_sku=expected_sku,  # 每个商品行编码与期望一致
        )
        order.items.append(item)
    
    print(f'订单商品行数: {len(order.items)}')
    print(f'解析结果数: {len(parsed_list)}')
    print(f'有效商品行数(排除赠品/补差价): {len([i for i in order.items if not adapter._is_gift_item(i) and not adapter._is_price_difference_item(i) and not i.is_void])}')
    print(f'期望SKU集合: {set((p.shop_mapping_sku, p.num) for p in parsed_list)}')
    print(f'当前SKU集合: {set((_clean_sku(i.shop_mapping_sku), i.num) for i in order.items if not adapter._is_gift_item(i) and not adapter._is_price_difference_item(i) and not i.is_void and i.shop_mapping_sku)}')
    
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
    removed = [item for item in payload["orderItems"] if item.get("cancelStatus")]
    assert len(active) == 1
    assert _clean_sku(active[0]["shopMappingSku"]) == expected_sku
    assert active[0]["num"] == expected_num
    assert {item["id"] for item in removed} == {item.id for item in order.items} - {active[0]["id"]}
    assert len(removed) == 2
    assert payload["totalCount"] == 1


def test_incorrect_sku_should_modify(offline_save_product):
    """测试：不正确的SKU - 应该执行修改"""
    print('\n' + '=' * 80)
    print('测试：不正确SKU场景 - 应该执行修改')
    print('=' * 80)
    
    remark = "定制双面革花漾之约;60x120cm裁剪有图-1张"
    
    adapter = FangguoAdapter()
    material_map = adapter.material_map
    material_matcher = adapter.get_material_matcher()
    
    parsed_list = extract_multiple_remarks(remark, material_map=material_map, material_matcher=material_matcher)
    
    if not parsed_list or not parsed_list[0].success:
        print('❌ 解析失败，无法进行测试')
        assert False, '解析失败'

    expected_sku = parsed_list[0].shop_mapping_sku
    print(f'期望编码: {expected_sku}')
    
    order = Order(
        id='123',
        trade_id='test_order_incorrect',
        tid='test_order_incorrect',
        shop_remark=remark,
        factory_id=1,
        store_name='测试店铺',
    )
    
    item1 = OrderItem(
        id='item1',
        order_id='test_order_incorrect',
        oid='test_order_incorrect',
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
    
    # 不正确的SKU应该执行修改，而不是跳过
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
