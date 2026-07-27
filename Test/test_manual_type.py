import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from adapters.fangguo.adapter import FangguoAdapter
from core.adapter_base import Order, OrderItem
from core.parser import ParsedRemark


@pytest.fixture
def adapter():
    return FangguoAdapter()


@pytest.fixture
def base_order():
    return Order(trade_id='test', tid='test', shop_remark='')


@pytest.fixture
def parsed():
    return ParsedRemark(
        material_code='双面革',
        color_code='定制',
        model_code='定制尺寸',
        picture_code='测试',
        num=1,
        success=True,
    )


def test_build_new_item_type(adapter, base_order, parsed):
    new_item = adapter._build_new_item(base_order, parsed)
    assert new_item['type'] == 1


def test_build_new_item_reuses_template_sku_ids(adapter, base_order, parsed):
    template_item = OrderItem(
        id='item-template',
        order_id='test',
        oid='test',
        num=1,
        original_sku_id='sku-template',
        original_goods_id='goods-template',
    )
    new_item = adapter._build_new_item(base_order, parsed, template_item=template_item)
    assert new_item['originalSkuId'] == 'sku-template'
    assert new_item['originalGoodsId'] == 'goods-template'


def test_build_default_item_type(adapter, base_order, parsed):
    default_item = adapter._build_default_item(base_order, parsed)
    assert default_item['type'] == 1


def test_build_gift_item_type(adapter, base_order):
    item = OrderItem(id='item1', order_id='test', oid='test', num=1)
    gift_new = adapter._build_gift_item(item, base_order, '吸水皮革', '圆垫', 1, is_new=True)
    gift_update = adapter._build_gift_item(item, base_order, '吸水皮革', '圆垫', 1, is_new=False)
    assert gift_new['type'] == 1
    assert gift_update['type'] == 0


def test_build_order_item_keeps_existing_type(adapter, base_order, parsed):
    item = OrderItem(id='item1', order_id='test', oid='test', num=1)
    order_item = adapter._build_order_item(item, base_order, parsed)
    assert order_item['type'] == 0


def test_build_new_item_has_empty_shop_remark(adapter, base_order, parsed):
    """新建手工单不应携带 parsed.shop_remark 中的子订单备注"""
    parsed.shop_remark = "这是子订单级备注，不应出现在手工单上"
    new_item = adapter._build_new_item(base_order, parsed)
    assert new_item['shopRemark'] == ""


def test_build_default_item_has_empty_shop_remark(adapter, base_order, parsed):
    """_build_default_item 生成的手工单也不应携带备注"""
    parsed.shop_remark = "这是子订单级备注，不应出现在手工单上"
    default_item = adapter._build_default_item(base_order, parsed)
    assert default_item['shopRemark'] == ""
