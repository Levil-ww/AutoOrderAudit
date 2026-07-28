import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from unittest.mock import MagicMock, patch
from core.adapter_base import Order, OrderItem
from core import ParsedRemark
from adapters.fangguo.adapter import FangguoAdapter


def test_manual_item_with_red_tag_not_duplicated():
    """
    测试：已存在的手工单行（shopMappingSku 带 <font color="red"> 标签）
    应被正确识别为已存在，不会重复创建新的手工单行。
    """
    print('=' * 80)
    print('测试：手工单行 HTML 红色标签不导致重复创建')
    print('=' * 80)

    adapter = FangguoAdapter()

    order = Order(
        id='test_order_001',
        trade_id='test_order_001',
        tid='test_order_001',
        shop_remark='定制吸水皮革暗纹蔷薇:55x99cm-1张, 60x72cm-1张, 55x115cm-1张',
    )

    order.items.append(OrderItem(
        id='item_orig',
        order_id='test_order_001',
        oid='test_order_001',
        title='美式厨房台面沥水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-暗纹蔷薇;55x99CM',
        num=1,
        price=142.2,
        raw={
            "materialCode": "吸水皮革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "暗纹蔷薇;55x99CM",
        },
    ))

    order.items.append(OrderItem(
        id='item_manual_1',
        order_id='test_order_001',
        oid='test_order_001',
        title='美式厨房台面沥水垫',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-暗纹蔷薇;60x72CM</font>',
        num=1,
        price=0,
        raw={
            "materialCode": "吸水皮革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "暗纹蔷薇;60x72CM",
            "type": 1,
        },
    ))

    order.items.append(OrderItem(
        id='item_manual_2',
        order_id='test_order_001',
        oid='test_order_001',
        title='美式厨房台面沥水垫',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-暗纹蔷薇;55x115CM</font>',
        num=1,
        price=0,
        raw={
            "materialCode": "吸水皮革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "暗纹蔷薇;55x115CM",
            "type": 1,
        },
    ))

    parsed_list = [
        ParsedRemark(
            material_code='吸水皮革', color_code='定制', model_code='定制尺寸',
            picture_code='暗纹蔷薇;55x99CM',
            num=1, success=True,
        ),
        ParsedRemark(
            material_code='吸水皮革', color_code='定制', model_code='定制尺寸',
            picture_code='暗纹蔷薇;60x72CM',
            num=1, success=True,
        ),
        ParsedRemark(
            material_code='吸水皮革', color_code='定制', model_code='定制尺寸',
            picture_code='暗纹蔷薇;55x115CM',
            num=1, success=True,
        ),
    ]

    with patch.object(adapter._session, 'post', return_value=MagicMock()) as mock_post:
        mock_post.return_value.json.return_value = {"code": 0, "data": True, "msg": ""}
        mock_post.return_value.raise_for_status = MagicMock()

        result = adapter.update_merchant_code(
            order,
            parsed=parsed_list[0],
            parsed_list=parsed_list,
        )

        assert result is True, f"期望返回 True，实际返回 {result}"
        mock_post.assert_not_called()

    print('通过：带 HTML 红色标签的手工单行被正确识别，未重复创建')
    print()


def test_manual_item_red_tag_sku_matching():
    """
    测试：按 SKU 匹配商品行时，也能正确清理 HTML 标签。
    """
    print('=' * 80)
    print('测试：按 SKU 匹配时清理 HTML 标签')
    print('=' * 80)

    adapter = FangguoAdapter()

    order = Order(
        id='test_order_002',
        trade_id='test_order_002',
        tid='test_order_002',
        shop_remark='定制吸水皮革暗纹蔷薇;55x99cm-1张, 60x72cm-1张',
    )

    order.items.append(OrderItem(
        id='item_orig',
        order_id='test_order_002',
        oid='test_order_002',
        title='美式厨房台面沥水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-暗纹蔷薇;55x99CM',
        num=1,
        price=142.2,
        raw={
            "materialCode": "吸水皮革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "暗纹蔷薇;55x99CM",
        },
    ))

    order.items.append(OrderItem(
        id='item_manual',
        order_id='test_order_002',
        oid='test_order_002',
        title='美式厨房台面沥水垫',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-暗纹蔷薇;60x72CM</font>',
        num=1,
        price=0,
        raw={
            "materialCode": "吸水皮革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "暗纹蔷薇;60x72CM",
            "type": 1,
        },
    ))

    parsed_list = [
        ParsedRemark(
            material_code='吸水皮革', color_code='定制', model_code='定制尺寸',
            picture_code='暗纹蔷薇;55x99CM',
            num=1, success=True,
        ),
        ParsedRemark(
            material_code='吸水皮革', color_code='定制', model_code='定制尺寸',
            picture_code='暗纹蔷薇;60x72CM',
            num=1, success=True,
        ),
    ]

    with patch.object(adapter._session, 'post', return_value=MagicMock()) as mock_post:
        mock_post.return_value.json.return_value = {"code": 0, "data": True, "msg": ""}
        mock_post.return_value.raise_for_status = MagicMock()

        result = adapter.update_merchant_code(
            order,
            parsed=parsed_list[0],
            parsed_list=parsed_list,
        )

        assert result is True, f"期望返回 True，实际返回 {result}"
        mock_post.assert_not_called()

    print('通过：按 SKU 匹配时正确清理 HTML 标签，未重复创建')
    print()


if __name__ == '__main__':
    test_manual_item_with_red_tag_not_duplicated()
    test_manual_item_red_tag_sku_matching()
    print('=' * 80)
    print('所有 HTML 红色标签测试通过！')
    print('=' * 80)
