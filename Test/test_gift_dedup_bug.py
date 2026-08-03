"""
测试：合并订单赠品去重问题
场景：合并订单有2个子订单，每个子订单各有一个赠品行（相同赠品）
      如果备注中没有赠品修改信息，赠品不应被去重/删除
      
模拟用户截图中的场景：
- 子订单1: 692843687221264755 (商品行 + 赠品行)
- 子订单2: 692843687221264759 (商品行 + 赠品行)
- 两个子订单的商品行编码相同（同产品同尺寸）
- 备注不涉及赠品修改
"""
import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.engine import AutoAuditEngine
from unittest.mock import MagicMock


def make_raw(item_id, sku, num, type_val=0, title='', tid='', oid='', film_gift_code='', price=100):
    return {
        'id': item_id,
        'orderId': '692843687221264755&692843687221264759',
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
        'shopRemark': '',
        'filmGiftCode': film_gift_code,
    }


def test_merged_order_gift_preservation():
    """
    测试合并订单中赠品的保留逻辑：
    - 两个子订单，各有1个商品行 + 1个赠品行
    - 两个商品行SKU相同
    - 备注不涉及赠品修改
    - 期望：两个赠品行都被保留，不被去重
    """
    print("=" * 80)
    print("测试：合并订单赠品保留（备注无赠品修改）")
    print("=" * 80)

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)

    tid1 = '692843687221264755'
    tid2 = '692843687221264759'
    merged_tid = f'{tid1}&{tid2}'

    # 备注：不含赠品信息
    remark = "整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布;60*140cm-1张"

    order = Order(
        id='test',
        trade_id='692843687221264755',
        tid=merged_tid,
        shop_remark=remark,
    )

    # 子订单1 - 商品行
    order.items.append(OrderItem(
        id='item_prod_1',
        order_id='692843687221264755',
        oid=f'oid_{tid1}',
        title='整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布',
        shop_mapping_sku='吸水皮革-标准-60x140-克罗印花;60x140',
        num=1,
        price=100.0,
        shop_remark=remark,
        original_tid=tid1,
        raw=make_raw('item_prod_1', '吸水皮革-标准-60x140-克罗印花;60x140', 1, 0,
                     '整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布',
                     tid=tid1, oid=f'oid_{tid1}', price=100),
    ))

    # 子订单1 - 赠品行
    order.items.append(OrderItem(
        id='item_gift_1',
        order_id='692843687221264755',
        oid=f'gift_oid_{tid1}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark='',
        original_tid=tid1,
        raw=make_raw('item_gift_1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid1, oid=f'gift_oid_{tid1}', 
                     film_gift_code='赠品沥水垫小圆或小方', price=0),
    ))

    # 子订单2 - 商品行
    order.items.append(OrderItem(
        id='item_prod_2',
        order_id='692843687221264759',
        oid=f'oid_{tid2}',
        title='整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布',
        shop_mapping_sku='吸水皮革-标准-60x140-克罗印花;60x140',
        num=1,
        price=100.0,
        shop_remark=remark,
        original_tid=tid2,
        raw=make_raw('item_prod_2', '吸水皮革-标准-60x140-克罗印花;60x140', 1, 0,
                     '整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布',
                     tid=tid2, oid=f'oid_{tid2}', price=100),
    ))

    # 子订单2 - 赠品行
    order.items.append(OrderItem(
        id='item_gift_2',
        order_id='692843687221264759',
        oid=f'gift_oid_{tid2}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark='',
        original_tid=tid2,
        raw=make_raw('item_gift_2', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid2, oid=f'gift_oid_{tid2}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0),
    ))

    print(f"\n订单: trade_id={order.trade_id}, tid={order.tid}")
    print(f"订单备注: '{order.shop_remark}'")
    print(f"\n商品行 ({len(order.items)} 个):")
    for i, item in enumerate(order.items):
        print(f"  [{i}] id={item.id}, tid={item.original_tid}, SKU={item.shop_mapping_sku[:50]}, num={item.num}, price={item.price}, is_gift={adapter._is_gift_item(item)}")

    print(f"\n调用引擎处理订单（dry run）...")
    engine.stats = {"total": 1, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    engine._process_order(order)

    print(f"\n统计: {engine.stats}")


def test_adapter_direct_gift_scenario():
    """
    直接测试 adapter 的 update_merchant_code 方法
    模拟：合并订单中2个子订单，各有商品行和赠品行
    备注解析后产生2个相同SKU的解析结果（因dedup可能被去重）
    检查赠品处理是否正确
    """
    print("\n" + "=" * 80)
    print("测试：adapter 直接调用 - 赠品处理")
    print("=" * 80)

    adapter = FangguoAdapter()

    tid1 = '692843687221264755'
    tid2 = '692843687221264759'
    merged_tid = f'{tid1}&{tid2}'

    remark = "整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布;60*140cm-1张"

    order = Order(
        id='test',
        trade_id='692843687221264755',
        tid=merged_tid,
        shop_remark=remark,
    )

    # 子订单1 - 商品行
    order.items.append(OrderItem(
        id='item_prod_1',
        order_id='692843687221264755',
        oid=f'oid_{tid1}',
        title='整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布',
        shop_mapping_sku='吸水皮革-标准-60x140-克罗印花;60x140',
        num=1,
        price=100.0,
        shop_remark=remark,
        original_tid=tid1,
        raw=make_raw('item_prod_1', '吸水皮革-标准-60x140-克罗印花;60x140', 1, 0,
                     '整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布',
                     tid=tid1, oid=f'oid_{tid1}', price=100),
    ))

    # 子订单1 - 赠品行
    order.items.append(OrderItem(
        id='item_gift_1',
        order_id='692843687221264755',
        oid=f'gift_oid_{tid1}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark='',
        original_tid=tid1,
        raw=make_raw('item_gift_1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid1, oid=f'gift_oid_{tid1}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0),
    ))

    # 子订单2 - 商品行
    order.items.append(OrderItem(
        id='item_prod_2',
        order_id='692843687221264759',
        oid=f'oid_{tid2}',
        title='整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布',
        shop_mapping_sku='吸水皮革-标准-60x140-克罗印花;60x140',
        num=1,
        price=100.0,
        shop_remark=remark,
        original_tid=tid2,
        raw=make_raw('item_prod_2', '吸水皮革-标准-60x140-克罗印花;60x140', 1, 0,
                     '整铺厨房台面沥水垫水槽灶台防滑隔热垫耐高温防烫餐桌布',
                     tid=tid2, oid=f'oid_{tid2}', price=100),
    ))

    # 子订单2 - 赠品行
    order.items.append(OrderItem(
        id='item_gift_2',
        order_id='692843687221264759',
        oid=f'gift_oid_{tid2}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark='',
        original_tid=tid2,
        raw=make_raw('item_gift_2', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid2, oid=f'gift_oid_{tid2}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0),
    ))

    # 模拟解析结果 - 两个子订单各解析出相同的SKU
    from core.parser import extract_multiple_remarks, ParsedRemark

    parsed_1 = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None,
    )
    for p in parsed_1:
        p.original_tid = tid1
        p.shop_remark = remark

    parsed_2 = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None,
    )
    for p in parsed_2:
        p.original_tid = tid2
        p.shop_remark = remark

    parsed_list = parsed_1 + parsed_2

    print(f"\n解析结果 ({len(parsed_list)} 个):")
    for i, p in enumerate(parsed_list):
        print(f"  [{i}] SKU={p.shop_mapping_sku}, num={p.num}, tid={p.original_tid}, gift_name={p.gift_name}, gift_num={p.gift_num}")

    # Mock API调用
    captured = {}
    def mock_post(url, json=None, timeout=None):
        captured['payload'] = json
        captured['url'] = url
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
        return resp

    adapter._session.post = mock_post

    result = adapter.update_merchant_code(
        order,
        parsed_list[0] if parsed_list else None,
        parsed_list,
        None,  # price_diff_updates
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
        print(f"  [{i}] {flag} id={it.get('id')}, oid={str(it.get('oid',''))[:30]}, SKU={clean_sku[:60]}, num={it.get('num')}")

    # 分析结果
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    active_gift_items = [it for it in active_items if '赠品' in (it.get('shopMappingSku', '') or '')]
    active_prod_items = [it for it in active_items if '赠品' not in (it.get('shopMappingSku', '') or '')]

    print(f"\n分析:")
    print(f"  有效商品行: {len(active_items)} 个")
    print(f"    - 普通商品行: {len(active_prod_items)} 个")
    print(f"    - 赠品行: {len(active_gift_items)} 个")
    print(f"  作废商品行: {len(void_items)} 个")

    if len(active_gift_items) == 2:
        print(f"\n✅ 通过：两个赠品行都被保留")
    elif len(active_gift_items) == 1:
        print(f"\n❌ 失败：只有1个赠品行被保留，另1个被删除/去重！")
        print(f"   这正是用户反馈的问题：程序错误地删除了赠品行")
    else:
        print(f"\n❌ 异常：赠品行数量不符合预期（期望2，实际{len(active_gift_items)}）")


def test_adapter_partial_gift_remark_scenario():
    """
    关键场景测试（用户截图场景）：
    - 合并订单 2 个子订单
    - 子订单1 (6954947999332898654): 有1个原赠品圆垫，备注中**无**赠品修改说明
    - 子订单2 (6954950281027000158): 原订单**无**赠品行，但备注中明确说明"赠品方垫30x50cm-1张"
    - 正确行为：
        * 子订单1的圆垫赠品行必须**保留不变**（不能修改编码或数量）
        * 子订单2必须**新建**一个方垫赠品行（挂子订单2的original_tid）
        * 禁止：在子订单1的圆垫赠品行上直接改编码成方垫！
    """
    print("\n" + "=" * 80)
    print("测试：子订单1原赠品保留 + 子订单2备注新建赠品（关键场景）")
    print("=" * 80)

    adapter = FangguoAdapter()

    tid1 = '6954947999332898654'
    tid2 = '6954950281027000158'
    merged_tid = f'{tid1}&{tid2}'

    # 子订单1备注：无赠品说明
    remark_tid1 = "定制吸水皮革巴洛克之星;65x165cm-1张"
    # 子订单2备注：明确说明要送方垫
    remark_tid2 = "定制吸水皮革巴洛克之星;32x152cm-1张 赠品方垫30x50cm-1张"

    order = Order(
        id='test2',
        trade_id=tid1,
        tid=merged_tid,
        shop_remark=remark_tid1 + " | " + remark_tid2,
    )

    # ========== 子订单1 ==========
    # 商品行1 - 巴洛克之星65x165CM
    order.items.append(OrderItem(
        id='item_prod_1',
        order_id=tid1,
        oid=f'oid_{tid1}',
        title='复古厨房台面沥水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-巴洛克之星;65x165CM',
        num=1,
        price=100.0,
        shop_remark=remark_tid1,
        original_tid=tid1,
        raw=make_raw('item_prod_1', '吸水皮革-定制-定制尺寸-巴洛克之星;65x165CM', 1, 0,
                     '复古厨房台面沥水垫', tid=tid1, oid=f'oid_{tid1}', price=100),
    ))

    # 赠品行1 - 原订单就是圆垫（子订单1的原赠品行）
    order.items.append(OrderItem(
        id='item_gift_1',
        order_id=tid1,
        oid=f'gift_oid_{tid1}',
        title='赠品沥水垫小圆或小方',
        shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1,
        price=0.0,
        shop_remark='',
        original_tid=tid1,
        raw=make_raw('item_gift_1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                     '赠品沥水垫小圆或小方', tid=tid1, oid=f'gift_oid_{tid1}',
                     film_gift_code='赠品沥水垫小圆或小方', price=0),
    ))

    # ========== 子订单2 ==========
    # 商品行2 - 巴洛克之星32x152CM
    order.items.append(OrderItem(
        id='item_prod_2',
        order_id=tid2,
        oid=f'oid_{tid2}',
        title='复古厨房台面沥水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-巴洛克之星;32x152CM',
        num=1,
        price=100.0,
        shop_remark=remark_tid2,
        original_tid=tid2,
        raw=make_raw('item_prod_2', '吸水皮革-定制-定制尺寸-巴洛克之星;32x152CM', 1, 0,
                     '复古厨房台面沥水垫', tid=tid2, oid=f'oid_{tid2}', price=100),
    ))
    # 子订单2 原订单中没有赠品行！

    # ========== 构造解析结果 ==========
    from core.parser import extract_multiple_remarks

    # 子订单1解析 - 无赠品
    parsed_1 = extract_multiple_remarks(
        remark_tid1,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None,
    )
    for p in parsed_1:
        p.original_tid = tid1
        p.shop_remark = remark_tid1

    # 子订单2解析 - 有赠品方垫
    parsed_2 = extract_multiple_remarks(
        remark_tid2,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None,
    )
    for p in parsed_2:
        p.original_tid = tid2
        p.shop_remark = remark_tid2

    parsed_list = parsed_1 + parsed_2

    print(f"\n子订单1 remark: {remark_tid1}")
    print(f"子订单2 remark: {remark_tid2}")
    print(f"\n解析结果 ({len(parsed_list)} 个):")
    for i, p in enumerate(parsed_list):
        gift_info = f", gift_name={p.gift_name}, gift_num={p.gift_num}" if p.gift_name else f", gifts={p.gifts if p.gifts else '无'}"
        print(f"  [{i}] SKU={p.shop_mapping_sku}, tid={p.original_tid[-6:]}{gift_info}")

    # Mock API调用
    captured = {}
    def mock_post(url, json=None, timeout=None):
        captured['payload'] = json
        captured['url'] = url
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
        return resp

    adapter._session.post = mock_post

    result = adapter.update_merchant_code(
        order,
        parsed_list[0] if parsed_list else None,
        parsed_list,
        None,
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
        oid_str = str(it.get('oid', ''))
        origin_trade = str(it.get('originTradeId', ''))
        tid_info = f"originTradeId={origin_trade[-6:] if len(origin_trade)>6 else origin_trade}"
        print(f"  [{i}] {flag} id={str(it.get('id',''))[:15]} SKU={clean_sku[:60]}, num={it.get('num')}, {tid_info}")

    # 分析结果
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    active_gift_items = []
    for it in active_items:
        clean_sku = (it.get('shopMappingSku', '') or '').replace('<font color="red">', '').replace('</font>', '')
        if '赠品' in clean_sku or '30x50' in clean_sku:
            active_gift_items.append(it)

    print(f"\n=== 断言验证 ===")
    all_pass = True

    # 1. 应该有2个赠品行：1个圆垫保留 + 1个方垫新建
    print(f"\n【检查1】赠品行数量：期望=2，实际={len(active_gift_items)}")
    if len(active_gift_items) == 2:
        print("  ✅ 数量正确")
    else:
        print(f"  ❌ 错误！赠品行数量不对（可能方垫被错误地覆盖在圆垫上，或方垫没创建）")
        all_pass = False

    # 2. 检查每个赠品行的编码和子订单号
    gift_round_found = False  # 圆垫，子订单1
    gift_square_found = False  # 方垫，子订单2
    for it in active_gift_items:
        clean_sku = (it.get('shopMappingSku', '') or '').replace('<font color="red">', '').replace('</font>', '')
        origin_trade = str(it.get('originTradeId', ''))
        item_id = str(it.get('id', ''))
        oid_str = str(it.get('oid', ''))
        num = it.get('num', 0)

        is_original_gift_1 = (item_id == 'item_gift_1')  # 使用原赠品行ID
        is_new_gift = (it.get('id') is None or str(it.get('id')) == 'None' or '69549502' in origin_trade)

        if '小圆或小方' in clean_sku and ('898654' in origin_trade or is_original_gift_1):
            # 子订单1的圆垫 - 使用原赠品行的id修改，SKU不变
            gift_round_found = True
            print(f"\n【圆垫赠品行】发现子订单1的原圆垫：")
            print(f"  SKU={clean_sku}")
            print(f"  id={item_id}, originTradeId={origin_trade}")
            print(f"  num={num}（期望=1）")
            if num == 1:
                print(f"  ✅ 数量正确（没有被错误修改为2）")
            else:
                print(f"  ❌ 数量错误！应该是1，但实际是{num}")
                all_pass = False
            if '小圆或小方' in clean_sku:
                print(f"  ✅ 编码正确（保留原圆垫编码）")
            else:
                print(f"  ❌ 编码错误！应该保留圆垫编码，但实际变成了{clean_sku}")
                all_pass = False

        if ('30x50' in clean_sku or '方垫' in clean_sku) and ('000158' in origin_trade or '69549502' in origin_trade):
            gift_square_found = True
            print(f"\n【方垫赠品行】发现子订单2的方垫：")
            print(f"  SKU={clean_sku}")
            print(f"  id={item_id}, originTradeId={origin_trade}")
            print(f"  num={num}（期望=1）")
            if num == 1:
                print(f"  ✅ 数量正确")
            else:
                print(f"  ❌ 数量错误")
                all_pass = False
            if item_id == '' or item_id == 'None' or not item_id:
                print(f"  ✅ 正确新建赠品行（id为空，ERP会创建新行）")
            elif item_id == 'item_gift_1':
                print(f"  ❌ 严重错误！方垫直接修改了子订单1的圆垫赠品行！")
                all_pass = False
            else:
                print(f"  ℹ️ 使用了id={item_id}")

    print(f"\n【检查2】子订单1的圆垫是否保留: {'✅ 是' if gift_round_found else '❌ 否，圆垫被删除或修改！'}")
    print(f"【检查3】子订单2是否新建方垫: {'✅ 是' if gift_square_found else '❌ 否，方垫未创建！'}")
    if not gift_round_found:
        all_pass = False
    if not gift_square_found:
        all_pass = False

    # 4. 检查原圆垫赠品行是否被乱改
    orig_gift_used = False
    orig_gift_ok = False
    for it in active_gift_items:
        if str(it.get('id', '')) == 'item_gift_1':
            orig_gift_used = True
            clean_sku = (it.get('shopMappingSku', '') or '').replace('<font color="red">', '').replace('</font>', '')
            if '小圆或小方' in clean_sku:
                orig_gift_ok = True
    if orig_gift_used and not orig_gift_ok:
        print(f"\n【检查4】❌❌❌ 严重：原圆垫赠品行(item_gift_1)被修改为非圆垫编码！这正是用户描述的bug。")
        all_pass = False
    elif orig_gift_used and orig_gift_ok:
        print(f"\n【检查4】✅ 原圆垫赠品行被正确保留原编码")

    print(f"\n{'='*40}")
    if all_pass:
        print("🎉 全部通过！修复有效。")
    else:
        print("❌ 存在问题，请检查修复。")
    print('='*40)


if __name__ == '__main__':
    test_merged_order_gift_preservation()
    test_adapter_direct_gift_scenario()
    test_adapter_partial_gift_remark_scenario()
