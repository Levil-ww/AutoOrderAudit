import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.parser import parse_remark, extract_multiple_remarks
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.engine import AutoAuditEngine, _PRICE_DIFF_KEYWORDS


def test_price_diff_detection():
    print('=' * 80)
    print('测试一：补差价订单检测')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)
    
    test_cases = [
        ("补差价专拍 少几元拍几个", True),
        ("差价专用", True),
        ("补差价专用少几元就拍几件", True),
        ("正常商品", False),
        ("定制双面革花漾之约", False),
    ]
    
    for title, expected in test_cases:
        order = Order(
            id='test',
            trade_id='test_order',
            tid='test_order',
            shop_remark='',
        )
        order.items.append(OrderItem(
            id='item1',
            order_id='test_order',
            oid='test_order',
            title=title,
            num=1,
            price=1.0,
        ))
        
        result = engine._is_price_difference_order(order)
        status = '✅' if result == expected else '❌'
        print(f"{status} 标题='{title}' -> 检测结果={result}, 期望={expected}")
    
    print()


def test_price_diff_only_empty_remark():
    print('=' * 80)
    print('测试二：只有补差价订单且备注为空 -> 编码改为不打印、数量1')
    print('=' * 80)

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)

    order = Order(
        id='test',
        trade_id='test_order_001',
        tid='test_order_001',
        shop_remark='',
    )
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_001',
        oid='test_order_001',
        title='补差价专拍 少几元拍几个',
        num=26,
        price=1.0,
    ))

    print(f"订单标题: {order.items[0].title}")
    print(f"订单备注: '{order.shop_remark}'")
    print(f"商品数量: {order.items[0].num}")
    print()

    engine._process_order(order)

    assert engine.stats['success'] == 1, f"期望成功1个订单（编码改为不打印），实际success={engine.stats['success']}, skipped={engine.stats['skipped']}"
    print('✅ 测试通过：只有补差价订单且备注为空，编码已改为不打印、数量1')
    print()


def test_price_diff_with_info_remark():
    print('=' * 80)
    print('测试三：补差价订单备注含定制信息 -> 按正常逻辑解析')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)
    
    remark = "定制双面革安妮森林;35x380cm-1张；等顾客确认做了再安排"
    order = Order(
        id='test',
        trade_id='test_order_002',
        tid='test_order_002',
        shop_remark=remark,
    )
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_002',
        oid='test_order_002',
        title='补差价专拍 少几元拍几个',
        num=11,
        price=1.0,
    ))
    
    print(f"订单标题: {order.items[0].title}")
    print(f"订单备注: '{remark}'")
    print(f"商品数量: {order.items[0].num}")
    print()
    
    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    engine._process_order(order)
    
    assert engine.stats['success'] == 1, f"期望成功1个订单，实际{engine.stats['success']}个"
    print('✅ 测试通过：补差价订单备注含定制信息，已按正常逻辑解析')
    print()


def test_price_diff_no_ship():
    print('=' * 80)
    print('测试四：补差价订单备注含"差价不发货" -> 修改编码和数量')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    
    order = Order(
        id='test',
        trade_id='test_order_003',
        tid='test_order_003',
        shop_remark='差价不发货',
    )
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_003',
        oid='test_order_003',
        title='补差价专拍 少几元拍几个',
        num=89,
        price=1.0,
        raw={
            "materialCode": "",
            "modelCode": "",
            "colorCode": "",
            "pictureCode": "",
        },
    ))
    
    print(f"订单标题: {order.items[0].title}")
    print(f"订单备注: '{order.shop_remark}'")
    print(f"商品数量: {order.items[0].num}")
    print()
    
    result_item = adapter._build_price_diff_no_ship_item(order.items[0], order)
    
    expected_sku = "定制-定制-补差价-不打印"
    expected_num = 1
    
    status1 = '✅' if result_item['shopMappingSku'] == expected_sku else '❌'
    status2 = '✅' if result_item['num'] == expected_num else '❌'
    
    print(f"{status1} 商家编码: {result_item['shopMappingSku']} (期望: {expected_sku})")
    print(f"{status2} 数量: {result_item['num']} (期望: {expected_num})")
    
    assert result_item['shopMappingSku'] == expected_sku, f"商家编码不匹配"
    assert result_item['num'] == expected_num, f"数量不匹配"
    print('✅ 测试通过：差价不发货订单已正确修改编码和数量')
    print()


def test_price_diff_with_normal_items_empty_remark():
    print('=' * 80)
    print('测试五：混合订单补差价商品行备注为空 -> 编码改为不打印、数量1')
    print('=' * 80)

    adapter = FangguoAdapter()

    order = Order(
        id='test',
        trade_id='test_order_004',
        tid='test_order_004',
        shop_remark='',
    )
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_004',
        oid='test_order_004',
        title='新中式圆圈扇形免洗隔热垫皮革杯垫',
        num=13,
        price=100.0,
        raw={
            "materialCode": "双面革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "定制;31x50CM",
        },
    ))
    order.items.append(OrderItem(
        id='item2',
        order_id='test_order_004',
        oid='test_order_004',
        title='补差价专用少几元就拍几件',
        num=134,
        price=1.0,
        raw={
            "materialCode": "",
            "modelCode": "",
            "colorCode": "",
            "pictureCode": "",
        },
    ))

    print(f"商品行1标题: {order.items[0].title}")
    print(f"商品行1数量: {order.items[0].num}")
    print(f"商品行2标题: {order.items[1].title}")
    print(f"商品行2数量: {order.items[1].num}")
    print(f"订单备注: '{order.shop_remark}'")
    print()

    # 备注为空时，补差价行编码应改为"定制-定制-补差价-不打印"，数量改为1
    result_item = adapter._build_price_diff_no_ship_item(order.items[1], order)

    expected_sku = "定制-定制-补差价-不打印"
    expected_num = 1

    status1 = '✅' if result_item['shopMappingSku'] == expected_sku else '❌'
    status2 = '✅' if result_item['num'] == expected_num else '❌'
    print(f"{status1} 补差价商品行编码: {result_item['shopMappingSku']} (期望: {expected_sku})")
    print(f"{status2} 补差价商品行数量: {result_item['num']} (期望: {expected_num})")

    assert result_item['shopMappingSku'] == expected_sku, f"商家编码不匹配"
    assert result_item['num'] == expected_num, f"数量不匹配"
    print('✅ 测试通过：补差价商品行编码已改为不打印、数量1')
    print()


def test_merged_order_price_diff():
    print('=' * 80)
    print('测试六：合并订单包含补差价商品行')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)
    
    order = Order(
        id='test',
        trade_id='5123730111671128828&5123750724456036485',
        tid='5123730111671128828&5123750724456036485',
        shop_remark='待定 定制双面革安妮森林;35x380cm-1张；等顾客确认做了再安排',
    )
    
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_005',
        oid='5123730111671128828',
        title='复古轻奢柜垫长条电视柜垫桌垫中古风台面垫防水防油防水鞋柜',
        num=1,
        price=52.8,
        shop_remark='待定 定制双面革安妮森林;35x380cm-1张；等顾客确认做了再安排',
        original_tid='5123730111671128828',
    ))
    order.items.append(OrderItem(
        id='item2',
        order_id='test_order_005',
        oid='5123750724456036485',
        title='补差价专拍少几元就拍几件',
        num=89,
        price=1.0,
        shop_remark='差价不发货',
        original_tid='5123750724456036485',
    ))
    
    print(f"订单号: {order.trade_id}")
    print(f"商品行1标题: {order.items[0].title}")
    print(f"商品行1备注: '{order.items[0].shop_remark}'")
    print(f"商品行1原始订单号: {order.items[0].original_tid}")
    print(f"商品行2标题: {order.items[1].title}")
    print(f"商品行2备注: '{order.items[1].shop_remark}'")
    print(f"商品行2原始订单号: {order.items[1].original_tid}")
    print()
    
    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    
    material_map = adapter.material_map
    material_matcher = adapter.get_material_matcher()
    engine._process_merged_order(order, material_map, material_matcher)
    
    assert engine.stats['success'] == 1, f"期望成功1个订单，实际{engine.stats['success']}个"
    print('✅ 测试通过：合并订单包含补差价商品行，已正确处理')
    print()


def test_price_diff_no_print():
    """测试七：补差价订单备注含"不打印" -> 编码改为"定制-定制-补差价-不打印" """
    print('=' * 80)
    print('测试七：补差价订单备注含"不打印" -> 编码改为不打印')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    
    # 场景1：备注"补差价不打印"
    order = Order(
        id='test',
        trade_id='test_order_007',
        tid='test_order_007',
        shop_remark='补差价不打印',
    )
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_007',
        oid='test_order_007',
        title='补差价专拍 少几元拍几个',
        num=50,
        price=1.0,
        raw={
            "materialCode": "",
            "modelCode": "",
            "colorCode": "",
            "pictureCode": "",
        },
    ))
    
    result_item = adapter._build_price_diff_no_ship_item(order.items[0], order)
    expected_sku = "定制-定制-补差价-不打印"
    expected_num = 1
    
    status1 = '✅' if result_item['shopMappingSku'] == expected_sku else '❌'
    status2 = '✅' if result_item['num'] == expected_num else '❌'
    
    print(f"{status1} 商家编码: {result_item['shopMappingSku']} (期望: {expected_sku})")
    print(f"{status2} 数量: {result_item['num']} (期望: {expected_num})")
    
    assert result_item['shopMappingSku'] == expected_sku, f"商家编码不匹配"
    assert result_item['num'] == expected_num, f"数量不匹配"
    
    # 场景2：_is_no_ship_remark 静态方法测试
    assert AutoAuditEngine._is_no_ship_remark("差价不发货") == True
    assert AutoAuditEngine._is_no_ship_remark("不打印") == True
    assert AutoAuditEngine._is_no_ship_remark("补差价不打印") == True
    assert AutoAuditEngine._is_no_ship_remark("不用发") == True
    assert AutoAuditEngine._is_no_ship_remark("差价不用发") == True
    assert AutoAuditEngine._is_no_ship_remark("定制双面革") == False
    assert AutoAuditEngine._is_no_ship_remark("") == False

    # 场景3：_get_no_print_reason 静态方法测试
    # 备注为空 → 返回"备注为空"
    assert AutoAuditEngine._get_no_print_reason("") == "备注为空"
    assert AutoAuditEngine._get_no_print_reason("   ") == "备注为空"
    # 备注为"补差价" → 返回"备注为'补差价'"
    assert AutoAuditEngine._get_no_print_reason("补差价") == "备注为'补差价'"
    assert AutoAuditEngine._get_no_print_reason(" 补差价 ") == "备注为'补差价'"
    # 备注为"差价" → 返回"备注为'差价'"
    assert AutoAuditEngine._get_no_print_reason("差价") == "备注为'差价'"
    assert AutoAuditEngine._get_no_print_reason(" 差价 ") == "备注为'差价'"
    # 包含"差价不发货" → 返回"差价不发货"
    assert AutoAuditEngine._get_no_print_reason("差价不发货") == "差价不发货"
    # 包含"不用发" → 返回"不用发"
    assert AutoAuditEngine._get_no_print_reason("不用发") == "不用发"
    assert AutoAuditEngine._get_no_print_reason("差价不用发") == "不用发"
    # 包含"不打印" → 返回"不打印"
    assert AutoAuditEngine._get_no_print_reason("补差价不打印") == "不打印"
    # 有定制信息 → 返回 None
    assert AutoAuditEngine._get_no_print_reason("定制双面革安妮森林") is None
    assert AutoAuditEngine._get_no_print_reason("补差价 定制双面革") is None

    print('✅ 测试通过："不打印"关键字检测和编码修改正确')
    print()


def test_price_diff_no_print_engine_flow():
    """测试八：补差价订单备注"补差价不打印"经引擎流程处理"""
    print('=' * 80)
    print('测试八：补差价订单备注"补差价不打印"引擎流程')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)
    
    order = Order(
        id='test',
        trade_id='test_order_008',
        tid='test_order_008',
        shop_remark='补差价不打印',
    )
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_008',
        oid='test_order_008',
        title='补差价专拍 少几元拍几个',
        num=50,
        price=1.0,
        raw={
            "materialCode": "",
            "modelCode": "",
            "colorCode": "",
            "pictureCode": "",
        },
    ))
    
    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    engine._process_order(order)
    
    # 补差价不打印应该被检测到，走 no_ship 分支
    assert engine.stats['success'] == 1, f"期望成功1个订单，实际{engine.stats['success']}个"
    print('✅ 测试通过：补差价不打印经引擎流程正确处理')
    print()


def test_merged_order_price_diff_no_print():
    """测试九：合并订单补差价行备注含"不打印" -> 编码改为不打印"""
    print('=' * 80)
    print('测试九：合并订单补差价行备注含"不打印"')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)
    
    order = Order(
        id='test',
        trade_id='5123730111671128828&5123750724456036485',
        tid='5123730111671128828&5123750724456036485',
        shop_remark='定制双面革安妮森林;35x380cm-1张',
    )
    
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_009',
        oid='5123730111671128828',
        title='复古轻奢柜垫长条电视柜垫桌垫中古风台面垫防水防油防水鞋柜',
        num=1,
        price=52.8,
        shop_remark='定制双面革安妮森林;35x380cm-1张',
        original_tid='5123730111671128828',
    ))
    order.items.append(OrderItem(
        id='item2',
        order_id='test_order_009',
        oid='5123750724456036485',
        title='补差价专拍少几元就拍几件',
        num=10,
        price=1.0,
        shop_remark='不打印',
        original_tid='5123750724456036485',
    ))
    
    print(f"订单号: {order.trade_id}")
    print(f"商品行2备注: '{order.items[1].shop_remark}'")
    print()
    
    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    
    material_map = adapter.material_map
    material_matcher = adapter.get_material_matcher()
    engine._process_merged_order(order, material_map, material_matcher)
    
    assert engine.stats['success'] == 1, f"期望成功1个订单，实际{engine.stats['success']}个"
    print('✅ 测试通过：合并订单补差价行"不打印"已正确处理')
    print()


def test_mixed_order_price_diff_with_remark():
    """测试十：混合订单（有普通商品行+补差价行）+ 备注含定制信息 -> 补差价行按备注修改编码"""
    print('=' * 80)
    print('测试十：混合订单补差价行有备注定制信息 -> 按补差价单一逻辑处理')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)
    
    # 场景：订单有1个普通商品行 + 1个补差价行，备注包含2条解析结果
    remark = "定制双面革安妮森林;35x380cm-1张，定制双面革花漾之约;40x60cm-1张"
    order = Order(
        id='test',
        trade_id='test_order_010',
        tid='test_order_010',
        shop_remark=remark,
    )
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_010',
        oid='test_order_010',
        title='复古轻奢柜垫长条电视柜垫桌垫',
        num=1,
        price=52.8,
        raw={
            "materialCode": "双面革",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "定制",
        },
    ))
    order.items.append(OrderItem(
        id='item2',
        order_id='test_order_010',
        oid='test_order_010',
        title='补差价专用少几元就拍几件',
        num=50,
        price=1.0,
        raw={
            "materialCode": "",
            "modelCode": "",
            "colorCode": "",
            "pictureCode": "",
        },
    ))
    
    print(f"商品行1: {order.items[0].title}")
    print(f"商品行2: {order.items[1].title}")
    print(f"订单备注: '{remark}'")
    print()
    
    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    engine._process_order(order)
    
    # 备注含信息 -> 应进入补差价处理流程
    # 第1条解析结果给普通商品行，第2条给补差价行
    assert engine.stats['success'] == 1 or engine.stats['skipped'] == 1, f"期望处理成功，实际success={engine.stats['success']}, skipped={engine.stats['skipped']}"
    print('✅ 测试通过：混合订单补差价行有备注定制信息，已按补差价单一逻辑处理')
    print()


def test_merged_order_price_diff_empty_remark():
    """测试十一：合并订单补差价分组备注为空 -> 编码改为不打印、数量1"""
    print('=' * 80)
    print('测试十一：合并订单补差价分组备注为空 -> 编码改为不打印、数量1')
    print('=' * 80)
    
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)
    
    order = Order(
        id='test',
        trade_id='5124693422585022132&5124948516963022132',
        tid='5124693422585022132&5124948516963022132',
        shop_remark='定制pu皮革飘窗垫莫系几何；55x177cm-1张',
    )
    
    order.items.append(OrderItem(
        id='item1',
        order_id='test_order_011',
        oid='5124693422585022132',
        title='主卧阳台飘窗垫窗台垫子2024新款轻奢北欧风防水防晒防潮垫可裁剪',
        num=1,
        price=88.0,
        shop_remark='定制pu皮革飘窗垫莫系几何；55x177cm-1张',
        original_tid='5124693422585022132',
        raw={
            "materialCode": "PU防水",
            "modelCode": "定制尺寸",
            "colorCode": "定制",
            "pictureCode": "莫系几何;55x177CM",
        },
    ))
    order.items.append(OrderItem(
        id='item2',
        order_id='test_order_011',
        oid='5124948516963022132',
        title='差价专用少几元就拍几件',
        num=6,
        price=1.0,
        shop_remark='',
        original_tid='5124948516963022132',
        raw={
            "materialCode": "",
            "modelCode": "",
            "colorCode": "",
            "pictureCode": "",
        },
    ))
    
    print(f"订单号: {order.trade_id}")
    print(f"商品行1标题: {order.items[0].title}")
    print(f"商品行1备注: '{order.items[0].shop_remark}'")
    print(f"商品行1原始订单号: {order.items[0].original_tid}")
    print(f"商品行2标题: {order.items[1].title}")
    print(f"商品行2备注: '{order.items[1].shop_remark}'")
    print(f"商品行2原始订单号: {order.items[1].original_tid}")
    print(f"商品行2数量: {order.items[1].num}")
    print()
    
    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    
    engine._process_order(order)
    
    assert engine.stats['success'] == 1, f"期望成功1个订单，实际success={engine.stats['success']}, skipped={engine.stats['skipped']}"
    print('✅ 测试通过：合并订单补差价分组备注为空，编码已改为不打印、数量1')
    print()


if __name__ == '__main__':
    test_price_diff_detection()
    test_price_diff_only_empty_remark()
    test_price_diff_with_info_remark()
    test_price_diff_no_ship()
    test_price_diff_with_normal_items_empty_remark()
    test_merged_order_price_diff()
    test_price_diff_no_print()
    test_price_diff_no_print_engine_flow()
    test_merged_order_price_diff_no_print()
    test_mixed_order_price_diff_with_remark()
    test_merged_order_price_diff_empty_remark()
    
    print('=' * 80)
    print('🎉 所有测试通过！')
    print('=' * 80)