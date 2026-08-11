"""
测试：合并订单中 ERP 自动关联备注导致赠品行重复问题

场景（用户截图场景）：
- 合并订单: 6928601810063031567&6928604049951915279
- 子订单1 (6928601810063031567): 备注 "定制双面革安妮森林;35x320cm-1张，赠品圆垫-1张"
- 子订单2 (6928604049951915279): 备注 "补差价"

问题：
1. 程序为子订单1创建赠品行（圆垫 x1）
2. ERP 保存时自动将订单级备注关联到新赠品行
3. 程序再次运行时，ERP 可能创建了额外的重复赠品行
4. 这些重复赠品行带有订单级备注（含"赠品圆垫-1张"）
5. 程序没有去重这些重复赠品行，导致出现4-6行都是相同的赠品行

本测试模拟：
- 已有1个正确的商品行 + 1个正确的赠品行（首次处理结果）
- ERP 额外创建了1-2个重复赠品行（带有订单级备注的 shop_remark）
- 期望程序去重这些重复赠品行，只保留1个正确的赠品行
"""
import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.engine import AutoAuditEngine
from unittest.mock import MagicMock


def make_raw(item_id, sku, num, type_val=0, title='', tid='', oid='', film_gift_code='', price=100, shop_remark=''):
    return {
        'id': item_id,
        'orderId': '6928601810063031567&6928604049951915279',
        'sysOid': f's{item_id}',
        'oid': oid or f'o{item_id}',
        'tid': tid or f't{item_id}',
        'title': title,
        'skuPropertiesName': '',
        'shopMappingSku': sku,
        'originalSkuId': '',
        'originalGoodsId': '',
        'merchandisePicPath': '',
        'num': num,
        'price': price,
        'type': type_val,
        'shopRemark': shop_remark,
        'filmGiftCode': film_gift_code,
    }


def test_gift_dedup_with_erp_created_duplicates():
    """
    测试：ERP 创建的重复赠品行应该被自动去重
    
    场景：
    - 子订单1有1个商品行 + 1个赠品行（正确的）
    - ERP 额外创建了2个重复赠品行（因为订单级备注被关联）
    - 总共3个赠品行（都有相同SKU和数量）
    - 期望：程序处理后只保留1个赠品行
    """
    print("=" * 80)
    print("测试：ERP 创建的重复赠品行去重")
    print("=" * 80)

    adapter = FangguoAdapter()

    tid1 = '6928601810063031567'
    tid2 = '6928604049951915279'
    merged_tid = f'{tid1}&{tid2}'

    # 子订单1的备注（含赠品信息）
    remark_tid1 = "定制双面革安妮森林;35x320cm-1张，赠品圆垫-1张"
    # 子订单2的备注（补差价）
    remark_tid2 = "补差价"

    # 订单级备注（包含两个子订单的信息）
    order_remark = remark_tid1 + "，" + remark_tid2

    order = Order(
        id='test_gift_dup',
        trade_id=tid1,
        tid=merged_tid,
        shop_remark=order_remark,
    )

    # ========== 子订单1 ==========
    # 商品行 - 双面格定制安妮森林 35x320CM
    order.items.append(OrderItem(
        id='item_prod_1',
        order_id=tid1,
        oid=f'oid_{tid1}',
        title='双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
        shop_mapping_sku='双面格-定制-定制尺寸-安妮森林;35x320CM',
        num=1,
        price=1.0,
        shop_remark=remark_tid1,  # 子订单1的备注
        original_tid=tid1,
        raw=make_raw('item_prod_1', '双面格-定制-定制尺寸-安妮森林;35x320CM', 1, 0,
                     '双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
                     tid=tid1, oid=f'oid_{tid1}', price=1, shop_remark=remark_tid1),
    ))

    # 赠品行1 - 正确的赠品行（首次创建的）
    order.items.append(OrderItem(
        id='item_gift_1',
        order_id=tid1,
        oid=f'gift_oid_1_{tid1}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark='',  # 正确的赠品行没有 shop_remark
        original_tid=tid1,
        raw=make_raw('item_gift_1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid1, oid=f'gift_oid_1_{tid1}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0),
    ))

    # 赠品行2 - ERP 创建的重复赠品行（带有订单级备注的 shop_remark）
    order.items.append(OrderItem(
        id='item_gift_dup_1',
        order_id=tid1,
        oid=f'gift_oid_dup_1_{tid1}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark=order_remark,  # ERP 自动关联的订单级备注！
        original_tid=tid1,  # 同一个子订单号
        raw=make_raw('item_gift_dup_1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid1, oid=f'gift_oid_dup_1_{tid1}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0,
                     shop_remark=order_remark),  # ERP 自动关联的订单级备注
    ))

    # 赠品行3 - 另一个 ERP 创建的重复赠品行
    order.items.append(OrderItem(
        id='item_gift_dup_2',
        order_id=tid1,
        oid=f'gift_oid_dup_2_{tid1}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark=order_remark,  # ERP 自动关联的订单级备注！
        original_tid=tid1,  # 同一个子订单号
        raw=make_raw('item_gift_dup_2', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid1, oid=f'gift_oid_dup_2_{tid1}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0,
                     shop_remark=order_remark),
    ))

    # ========== 子订单2（补差价）==========
    order.items.append(OrderItem(
        id='item_prod_2',
        order_id=tid2,
        oid=f'oid_{tid2}',
        title='双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
        shop_mapping_sku='定制-定制-补差价-不打印',
        num=1,
        price=1.0,
        shop_remark=remark_tid2,  # "补差价"
        original_tid=tid2,
        raw=make_raw('item_prod_2', '定制-定制-补差价-不打印', 1, 0,
                     '双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
                     tid=tid2, oid=f'oid_{tid2}', price=1, shop_remark=remark_tid2),
    ))

    print(f"\n订单: trade_id={order.trade_id}, tid={order.tid}")
    print(f"订单级备注: '{order.shop_remark}'")
    print(f"\n商品行 ({len(order.items)} 个):")
    for i, item in enumerate(order.items):
        is_gift = adapter._is_gift_item(item)
        print(f"  [{i}] id={item.id}, tid={item.original_tid}, SKU={item.shop_mapping_sku[:50]}, "
              f"num={item.num}, price={item.price}, is_gift={is_gift}")
        if is_gift:
            print(f"       shop_remark='{item.shop_remark[:60]}' (长度={len(item.shop_remark)})")

    # 模拟解析结果
    from core.parser import extract_multiple_remarks

    # 子订单1解析 - 有赠品圆垫
    parsed_1 = extract_multiple_remarks(
        remark_tid1,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None,
    )
    for p in parsed_1:
        p.original_tid = tid1
        p.shop_remark = remark_tid1

    # 子订单2解析 - 补差价（无商品解析）
    parsed_2 = extract_multiple_remarks(
        remark_tid2,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None,
    )
    for p in parsed_2:
        p.original_tid = tid2
        p.shop_remark = remark_tid2

    parsed_list = parsed_1 + parsed_2

    print(f"\n解析结果 ({len(parsed_list)} 个):")
    for i, p in enumerate(parsed_list):
        gift_info = f", gift_name={p.gift_name}, gift_num={p.gift_num}" if p.gift_name else f", gifts={p.gifts if p.gifts else '无'}"
        print(f"  [{i}] SKU={p.shop_mapping_sku}, tid={p.original_tid[-6:]}{gift_info}, success={p.success}")

    # Mock API 调用
    captured = {}
    def mock_post(url, json=None, timeout=None):
        captured['payload'] = json
        captured['url'] = url
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
        return resp

    adapter._session.post = mock_post

    # 准备 price_diff_updates
    price_diff_updates = [{
        'tid': tid2,
        'items': [order.items[4]],  # 补差价商品行
        'remark': remark_tid2,
        'ship': False,
    }]

    result = adapter.update_merchant_code(
        order,
        parsed_list[0] if parsed_list else None,
        parsed_list,
        price_diff_updates,
        gift_no_ship_tids=[],
    )

    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])

    print(f"\n结果: {result}")
    print(f"提交的 orderItems ({len(all_items)} 个):")
    for i, it in enumerate(all_items):
        is_void = it.get('cancelStatus') or it.get('discardStatus')
        flag = '🗑️作废' if is_void else '✅有效'
        clean_sku = (it.get('shopMappingSku', '') or '').replace('<font color="red">', '').replace('</font>', '')
        origin_trade = str(it.get('originTradeId', ''))
        oid_str = str(it.get('oid', ''))
        print(f"  [{i}] {flag} id={str(it.get('id',''))[:20]}, originTradeId={origin_trade[-10:]}, "
              f"SKU={clean_sku[:60]}, num={it.get('num')}")

    # 分析结果
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]

    active_gift_items = []
    for it in active_items:
        clean_sku = (it.get('shopMappingSku', '') or '').replace('<font color="red">', '').replace('</font>', '')
        if '赠品' in clean_sku or '沥水垫小圆或小方' in clean_sku:
            active_gift_items.append(it)

    active_prod_items = []
    for it in active_items:
        clean_sku = (it.get('shopMappingSku', '') or '').replace('<font color="red">', '').replace('</font>', '')
        if '赠品' not in clean_sku and '补差价' not in clean_sku:
            active_prod_items.append(it)

    active_price_diff_items = []
    for it in active_items:
        clean_sku = (it.get('shopMappingSku', '') or '').replace('<font color="red">', '').replace('</font>', '')
        if '补差价' in clean_sku:
            active_price_diff_items.append(it)

    print(f"\n=== 结果分析 ===")
    print(f"  有效商品行: {len(active_items)} 个")
    print(f"    - 普通商品行: {len(active_prod_items)} 个")
    print(f"    - 赠品行: {len(active_gift_items)} 个")
    print(f"    - 补差价行: {len(active_price_diff_items)} 个")
    print(f"  作废商品行: {len(void_items)} 个")

    # 关键断言
    print(f"\n=== 断言验证 ===")
    all_pass = True

    # 1. 应该只有1个赠品行（重复的应该被去重）
    expected_gift_count = 1
    actual_gift_count = len(active_gift_items)
    print(f"\n【检查1】赠品行数量：期望={expected_gift_count}，实际={actual_gift_count}")
    if actual_gift_count == expected_gift_count:
        print("  ✅ 通过：只有1个赠品行（重复的已被去重）")
    else:
        print(f"  ❌ 失败：有 {actual_gift_count} 个赠品行（期望只有1个）")
        if actual_gift_count > expected_gift_count:
            print(f"     这说明程序没有去重 ERP 创建的重复赠品行")
        all_pass = False

    # 2. 普通商品行数量正确
    print(f"\n【检查2】普通商品行数量：期望=1，实际={len(active_prod_items)}")
    if len(active_prod_items) == 1:
        print("  ✅ 通过")
    else:
        print("  ❌ 失败")
        all_pass = False

    # 3. 补差价行数量正确
    print(f"\n【检查3】补差价行数量：期望=1，实际={len(active_price_diff_items)}")
    if len(active_price_diff_items) == 1:
        print("  ✅ 通过")
    else:
        print("  ❌ 失败")
        all_pass = False

    # 4. 检查赠品行的 shop_remark 不应包含订单级备注
    if active_gift_items:
        gift_item = active_gift_items[0]
        gift_remark = gift_item.get('shopRemark', '') or ''
        # 赠品行的 shop_remark 不应该包含订单级备注中的赠品信息
        if '赠品' in gift_remark or '圆垫' in gift_remark:
            print(f"\n【检查4】⚠️ 赠品行 shop_remark 包含订单级备注: '{gift_remark[:60]}'")
            print(f"     这可能导致下次运行时被误解析")
        else:
            print(f"\n【检查4】✅ 赠品行 shop_remark 干净（不含订单级备注）")

    print(f"\n{'='*40}")
    if all_pass:
        print("🎉 全部通过！赠品行去重逻辑正确。")
    else:
        print("❌ 存在问题，需要修复代码！")
    print('='*40)
    
    return all_pass


def test_engine_with_erp_gift_duplicates():
    """
    测试：引擎层处理 ERP 创建的重复赠品行
    
    验证：engine.py 中正确跳过赠品行的 remark 作为解析来源
    """
    print("\n" + "=" * 80)
    print("测试：引擎层处理 ERP 创建的重复赠品行")
    print("=" * 80)

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)

    tid1 = '6928601810063031567'
    tid2 = '6928604049951915279'
    merged_tid = f'{tid1}&{tid2}'

    remark_tid1 = "定制双面革安妮森林;35x320cm-1张，赠品圆垫-1张"
    remark_tid2 = "补差价"
    order_remark = remark_tid1 + "，" + remark_tid2

    order = Order(
        id='test_engine',
        trade_id=tid1,
        tid=merged_tid,
        shop_remark=order_remark,
    )

    # 商品行
    order.items.append(OrderItem(
        id='item_prod_1',
        order_id=tid1,
        oid=f'oid_{tid1}',
        title='双面格电视柜台柜',
        shop_mapping_sku='双面格-定制-定制尺寸-安妮森林;35x320CM',
        num=1,
        price=1.0,
        shop_remark=remark_tid1,
        original_tid=tid1,
        raw=make_raw('item_prod_1', '双面格-定制-定制尺寸-安妮森林;35x320CM', 1, 0,
                     '双面格电视柜台柜', tid=tid1, oid=f'oid_{tid1}', price=1,
                     shop_remark=remark_tid1),
    ))

    # 正确的赠品行
    order.items.append(OrderItem(
        id='item_gift_1',
        order_id=tid1,
        oid=f'gift_oid_1_{tid1}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark='',
        original_tid=tid1,
        raw=make_raw('item_gift_1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid1, oid=f'gift_oid_1_{tid1}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0),
    ))

    # ERP 创建的重复赠品行（带有订单级备注）
    order.items.append(OrderItem(
        id='item_gift_dup_1',
        order_id=tid1,
        oid=f'gift_oid_dup_1_{tid1}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark=order_remark,  # ERP 自动关联的订单级备注
        original_tid=tid1,
        raw=make_raw('item_gift_dup_1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid1, oid=f'gift_oid_dup_1_{tid1}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0,
                     shop_remark=order_remark),
    ))

    # 补差价行
    order.items.append(OrderItem(
        id='item_prod_2',
        order_id=tid2,
        oid=f'oid_{tid2}',
        title='双面格电视柜台柜',
        shop_mapping_sku='定制-定制-补差价-不打印',
        num=1,
        price=1.0,
        shop_remark=remark_tid2,
        original_tid=tid2,
        raw=make_raw('item_prod_2', '定制-定制-补差价-不打印', 1, 0,
                     '双面格电视柜台柜', tid=tid2, oid=f'oid_{tid2}', price=1,
                     shop_remark=remark_tid2),
    ))

    print(f"\n订单: trade_id={order.trade_id}")
    print(f"订单级备注: '{order.shop_remark}'")
    
    # 验证 _is_gift_item 检测
    print(f"\n赠品行检测:")
    for i, item in enumerate(order.items):
        is_gift = adapter._is_gift_item(item)
        print(f"  [{i}] id={item.id}, is_gift={is_gift}, shop_remark='{item.shop_remark[:50]}'")

    # 检查引擎是否能正确处理
    # 关键验证：引擎处理后，不应该因为 ERP 重复赠品行而重新解析
    # 引擎会调用 _process_merged_order，它应该跳过赠品行的 remark
    
    print(f"\n调用引擎处理订单（dry run）...")
    engine.stats = {"total": 1, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    
    # 尝试处理
    try:
        engine._process_order(order)
        print(f"\n引擎统计: {engine.stats}")
        
        # 检查引擎输出
        if engine.stats.get('failed', 0) > 0:
            print("  ⚠️ 引擎报告失败")
        else:
            print("  ✅ 引擎处理完成")
            
    except Exception as e:
        print(f"  ❌ 引擎异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    result1 = test_gift_dedup_with_erp_created_duplicates()
    result2 = test_engine_with_erp_gift_duplicates()
    
    print(f"\n\n{'='*80}")
    print("总结")
    print(f"{'='*80}")
    print(f"  测试1 (adapter 层去重): {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"  测试2 (engine 层处理):  参见上方详细输出")