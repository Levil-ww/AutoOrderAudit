import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.engine import AutoAuditEngine
from core.parser import extract_multiple_remarks


def test_user_scenario_merged():
    """
    复现用户场景：合并订单（不同original_tid）
    - 子订单A：1个正常商品行
    - 子订单B：1个补差价行
    - 订单备注有3条定制信息

    问题：补差价行被当作独立分组，其shop_remark为空 -> 被改为不打印
    而备注中的3条定制信息全部用于正常商品行 -> 导致生成2个新行
    """
    print('=' * 80)
    print('复现用户场景：合并订单 + 补差价行 + 3条定制信息')
    print('=' * 80)

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)

    remark = "定制吸水皮革蔓生花;25x45cm-1张，42x80cm-1张，花满金陵;55x59cm-1张，共3张"

    order = Order(
        id='test',
        trade_id='5125967175853010934',
        tid='5125967175853010934',
        shop_remark=remark,
    )

    # 正常商品行（子订单A）
    order.items.append(OrderItem(
        id='item1',
        order_id='5125967175853010934',
        oid='5125967175853010934',
        title='DMF厨房台面专用沥水垫硅藻泥洗手池水槽边吸水垫长条灶台隔热垫',
        num=1,
        price=100.0,
        shop_mapping_sku='吸水皮革-定制-定制尺寸-蔓生花;25x45CM',
        shop_remark=remark,
        original_tid='5125967175853010934_1',
        raw={
            "materialCode": "吸水皮革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "蔓生花;25x45CM",
        },
    ))

    # 补差价行（子订单B）
    order.items.append(OrderItem(
        id='item2',
        order_id='5125967175853010934',
        oid='5125967175853010934',
        title='DMF 补运费专拍 补差价专拍 少几元拍几个',
        num=1,
        price=1.0,
        shop_mapping_sku='定制-定制-补差价-不打印',
        shop_remark='',  # 补差价行备注为空
        original_tid='5125967175853010934_2',
        raw={
            "materialCode": "",
            "modelCode": "",
            "colorCode": "",
            "pictureCode": "",
        },
    ))

    print(f"订单备注: '{remark}'")
    print(f"商品行1: original_tid={order.items[0].original_tid}, SKU={order.items[0].shop_mapping_sku}")
    print(f"商品行2: original_tid={order.items[1].original_tid}, SKU={order.items[1].shop_mapping_sku}, remark='{order.items[1].shop_remark}'")
    print()

    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    engine._process_order(order)

    print()
    print(f"统计: {engine.stats}")


def test_user_scenario_normal():
    """
    复现用户场景：普通订单（相同original_tid）
    """
    print('=' * 80)
    print('复现用户场景：普通订单 + 补差价行 + 3条定制信息')
    print('=' * 80)

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)

    remark = "定制吸水皮革蔓生花;25x45cm-1张，42x80cm-1张，花满金陵;55x59cm-1张，共3张"

    order = Order(
        id='test',
        trade_id='5125967175853010934',
        tid='5125967175853010934',
        shop_remark=remark,
    )

    order.items.append(OrderItem(
        id='item1',
        order_id='5125967175853010934',
        oid='5125967175853010934',
        title='DMF厨房台面专用沥水垫硅藻泥洗手池水槽边吸水垫长条灶台隔热垫',
        num=1,
        price=100.0,
        shop_mapping_sku='吸水皮革-定制-定制尺寸-蔓生花;25x45CM',
        original_tid='5125967175853010934',
        raw={
            "materialCode": "吸水皮革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "蔓生花;25x45CM",
        },
    ))

    order.items.append(OrderItem(
        id='item2',
        order_id='5125967175853010934',
        oid='5125967175853010934',
        title='DMF 补运费专拍 补差价专拍 少几元拍几个',
        num=1,
        price=1.0,
        shop_mapping_sku='定制-定制-补差价-不打印',
        original_tid='5125967175853010934',
        raw={
            "materialCode": "",
            "modelCode": "",
            "colorCode": "",
            "pictureCode": "",
        },
    ))

    print(f"订单备注: '{remark}'")
    print(f"商品行1: original_tid={order.items[0].original_tid}, SKU={order.items[0].shop_mapping_sku}")
    print(f"商品行2: original_tid={order.items[1].original_tid}, SKU={order.items[1].shop_mapping_sku}")
    print()

    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    engine._process_order(order)

    print()
    print(f"统计: {engine.stats}")


if __name__ == '__main__':
    test_user_scenario_merged()
    print()
    print()
    test_user_scenario_normal()
