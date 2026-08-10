"""
测试：合并订单中已作废/已退款子订单的跳过逻辑
==============================================

场景（模拟用户截图中的合并订单）：
- 子订单A（红框）：正常，备注可解析 → 应该正常处理
- 子订单B（绿框1）：正常，备注可解析 → 应该正常处理
- 子订单C（绿框2）：正常，备注可解析 → 应该正常处理
- 子订单D（绿框3）：所有商品行已作废/已退款，备注即使可解析也应该跳过
  - 不仅商品解析要跳过，赠品解析也要跳过

验证目标：
1. 子订单D的商品解析结果不会出现在 all_parsed_list 中
2. 子订单D的赠品不会出现在 all_gifts / gift_no_ship_tids 中
3. 最终 adapter 不会为子订单D创建任何新的商品行或赠品行
4. 子订单A/B/C 正常处理不受影响
5. 子订单D的原作废行被原样保留（cancelStatus=True）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.engine import AutoAuditEngine
from unittest.mock import MagicMock
import re


def make_raw(item_id, sku, num, type_val=0, title='', tid='', oid='',
             film_gift_code='', price=100, is_void=False):
    return {
        'id': item_id,
        'orderId': 'merge_void_test',
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
        'cancelStatus': is_void,
        'discardStatus': 2 if is_void else 0,
        'refundStatusDesc': '已退款' if is_void else '',
    }


def build_test_order():
    """
    构造模拟用户截图的合并订单：
    - 子订单1 (tid_A): 正常 - 定制双面革凡尔赛的梦;80x140cm裁剪有图-1张
    - 子订单2 (tid_B): 正常 - 定制双面革蔓生花;32x117cm-1张 赠品圆垫-1张
    - 子订单3 (tid_C): 正常 - 定制双面革蔓生花;32.3x195.3cm-1张
    - 子订单4 (tid_D): 已作废 - 定制双面革蔓生花;30x120-1张，赠品圆垫-2张 (is_void=True)
    """
    tid_A = '6955087895333771069'
    tid_B = '6955094737886123837'
    tid_C = '6955094740906809149'
    tid_D = '6955083645444036413'
    merged_tid = f'{tid_A}&{tid_B}&{tid_C}&{tid_D}'

    # 订单级备注（模拟ERP合并订单场景，只含一般信息，具体解析用商品行备注）
    order_remark = '订单级总备注'

    order = Order(
        id='merge_void_test',
        trade_id=merged_tid,
        tid=merged_tid,
        shop_remark=order_remark,
    )

    # --------- 子订单A：正常商品行 ---------
    remark_A = "定制双面革凡尔赛的梦;80x140cm裁剪有图-1张"
    order.items.append(OrderItem(
        id='item_A1',
        order_id=merged_tid,
        oid=f'oid_A',
        sys_oid='sys_A1',
        title='芙洛蒂纳时光法式餐桌垫防水防油免洗隔热垫长方形家用可定制',
        shop_mapping_sku='旧编码-凡尔赛的梦',
        num=1,
        price=149.4,
        shop_remark=remark_A,
        original_tid=tid_A,
        is_void=False,
        raw=make_raw('item_A1', '旧编码-凡尔赛的梦', 1, 0,
                     '芙洛蒂纳时光法式餐桌垫防水防油免洗隔热垫长方形家用可定制',
                     tid=tid_A, oid=f'oid_A', price=149.4, is_void=False),
    ))

    # --------- 子订单B：正常商品行（带赠品信息） ---------
    remark_B = "定制双面革蔓生花;32x117cm-1张 赠品圆垫-1张"
    order.items.append(OrderItem(
        id='item_B1',
        order_id=merged_tid,
        oid=f'oid_B',
        sys_oid='sys_B1',
        title='法式餐边柜保护垫防水防油免洗玄关2026新款茶几桌垫可定制',
        shop_mapping_sku='旧编码-蔓生花',
        num=1,
        price=63.2,
        shop_remark=remark_B,
        original_tid=tid_B,
        is_void=False,
        raw=make_raw('item_B1', '旧编码-蔓生花', 1, 0,
                     '法式餐边柜保护垫防水防油免洗玄关2026新款茶几桌垫可定制',
                     tid=tid_B, oid=f'oid_B', price=63.2, is_void=False),
    ))

    # --------- 子订单C：正常商品行 ---------
    remark_C = "定制双面革蔓生花;32.3x195.3cm-1张"
    order.items.append(OrderItem(
        id='item_C1',
        order_id=merged_tid,
        oid=f'oid_C',
        sys_oid='sys_C1',
        title='法式餐边柜保护垫防水防油免洗玄关2026新款茶几桌垫可定制',
        shop_mapping_sku='旧编码-蔓生花大尺寸',
        num=1,
        price=95.6,
        shop_remark=remark_C,
        original_tid=tid_C,
        is_void=False,
        raw=make_raw('item_C1', '旧编码-蔓生花大尺寸', 1, 0,
                     '法式餐边柜保护垫防水防油免洗玄关2026新款茶几桌垫可定制',
                     tid=tid_C, oid=f'oid_C', price=95.6, is_void=False),
    ))

    # --------- 子订单D：已作废商品行（但备注可解析 + 含赠品要求） ---------
    remark_D = "定制双面革蔓生花;30x120-1张，赠品圆垫-2张"
    order.items.append(OrderItem(
        id='item_D1',
        order_id=merged_tid,
        oid=f'oid_D',
        sys_oid='sys_D1',
        title='法式餐边柜保护垫防水防油免洗玄关2026新款茶几桌垫可定制',
        shop_mapping_sku='双面革-标准-30x120-蔓生花;30x120',
        num=1,
        price=63.2,
        shop_remark=remark_D,
        original_tid=tid_D,
        is_void=True,   # 关键：已作废/已退款
        raw=make_raw('item_D1', '双面革-标准-30x120-蔓生花;30x120', 1, 0,
                     '法式餐边柜保护垫防水防油免洗玄关2026新款茶几桌垫可定制',
                     tid=tid_D, oid=f'oid_D', price=63.2, is_void=True),
    ))

    return order, tid_A, tid_B, tid_C, tid_D


def test_void_suborder_skips_parsing_and_gifts():
    """
    核心测试：已作废子订单（tid_D）即使备注可解析且带赠品信息，
    也必须完全跳过——既不产生商品解析结果，也不产生赠品。
    """
    print("\n" + "=" * 80)
    print("测试用例: 合并订单-已作废子订单跳过解析（商品+赠品均跳过）")
    print("=" * 80)

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)

    order, tid_A, tid_B, tid_C, tid_D = build_test_order()

    # --- 直接调用 _process_merged_order 并拦截内部状态 ---
    # 通过 dry_run=True 的方式跑完整流程，在 _process_merged_order 里
    # 我们新增了 skip 打印，也可以通过最终 payload 验证

    # 收集打印输出中的 skip 标记
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        engine._process_order(order)

    output = buf.getvalue()
    print(output)

    # ====== 断言 1：控制台输出应有 "子订单所有商品行已作废/已退款，跳过解析" ======
    assert "已作废/已退款，跳过解析" in output, (
        "未检测到对子订单D的跳过打印，说明跳过逻辑未触发！"
    )

    # ====== 断言 2：最终 payload 中不包含 tid_D 的新建商品行 ======
    # 我们通过直接调用 adapter.update_merchant_code 来检查
    # 先重新构造订单并跑一次 engine 解析来拿到 parsed_list 等中间产物

    order2, tid_A, tid_B, tid_C, tid_D = build_test_order()

    # 先手动执行合并订单分组解析（复用 engine 内部逻辑）
    material_map = getattr(adapter, 'material_map', None)
    material_matcher = getattr(adapter, 'get_material_matcher', lambda: None)()

    # 直接调用 _process_merged_order 在 dry_run 下不会修改 order
    engine2 = AutoAuditEngine(adapter, dry_run=True)
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        engine2._process_merged_order(order2, material_map, material_matcher)

    output2 = buf2.getvalue()
    print("\n--- 合并订单解析输出 ---")
    print(output2)

    # ====== 断言 3：检查 engine 中被跳过的分组不会出现在解析结果里 ======
    # dry_run 模式下打印的 "🔶 DRY RUN: 新编码 = X" 数量等于解析成功且被保留的商品数
    dryrun_sku_count = len(re.findall(r'🔶 DRY RUN: 新编码 = ', output2))
    # 期望：A/B/C 三个子订单各1个解析结果 → 共 3 条
    assert dryrun_sku_count == 3, (
        f"期望3个正常子订单各产生1条编码修改，实际 {dryrun_sku_count} 条。\n"
        f"如果大于3：说明作废子订单D被错误解析了！\n"
        f"如果小于3：说明正常子订单解析被错误跳过！"
    )

    # ====== 断言 4：检查赠品数量 - 只有 tid_B 有赠品(圆垫x1)，不能出现 tid_D 的圆垫x2 ======
    # "赠品: 圆垫 x" 应只出现一次，且数量是 1
    gift_lines = re.findall(r'🎁 赠品: ([^ ]+) x (\d+)', output2)
    print(f"\n解析出的赠品列表: {gift_lines}")
    # 期望：只有圆垫 x1（来自子订单B）
    # 不应该出现圆垫 x2（来自作废子订单D）
    assert ('圆垫', '1') in gift_lines, "子订单B的圆垫x1赠品丢失！"
    # 检查是否有错误的 x2 赠品
    for gname, gnum in gift_lines:
        assert gnum != '2', (
            f"出现了赠品数量为2的条目 {gname}x{gnum}，这应属于作废子订单D，"
            "不应该被解析！"
        )

    print("\n✅ 断言 1-4 全部通过：已作废子订单成功跳过商品和赠品解析，正常子订单不受影响！")


def test_partial_void_suborder_still_processed():
    """
    边界测试：子订单里有部分商品行作废、还有部分有效
    → 该子订单不能被跳过，应正常解析
    """
    print("\n" + "=" * 80)
    print("边界测试: 子订单仅部分商品作废 → 仍应正常处理")
    print("=" * 80)

    tid_A = 'sub_A_normal'
    tid_B = 'sub_B_partial_void'
    merged_tid = f'{tid_A}&{tid_B}'

    order = Order(
        id='merge_partial_void_test',
        trade_id=merged_tid,
        tid=merged_tid,
        shop_remark='',
    )

    # 子订单A：正常
    remark_A = "定制双面格庄园秘境;55x60CM-1张"
    order.items.append(OrderItem(
        id='A1', order_id=merged_tid, oid='oA', sys_oid='sA1',
        title='庄园秘境55x60CM', shop_mapping_sku='旧编码',
        num=1, price=100, shop_remark=remark_A, original_tid=tid_A,
        is_void=False,
        raw=make_raw('A1', '旧编码', 1, 0, '庄园秘境55x60CM',
                     tid=tid_A, oid='oA', price=100, is_void=False),
    ))

    # 子订单B：有一个作废行 + 一个有效行（同一子订单号）
    remark_B = "定制双面革蔓生花;30x120-1张 赠品圆垫-1张"
    # 有效行
    order.items.append(OrderItem(
        id='B1', order_id=merged_tid, oid='oB1', sys_oid='sB1',
        title='蔓生花30x120', shop_mapping_sku='旧编码B',
        num=1, price=80, shop_remark=remark_B, original_tid=tid_B,
        is_void=False,  # 有效
        raw=make_raw('B1', '旧编码B', 1, 0, '蔓生花30x120',
                     tid=tid_B, oid='oB1', price=80, is_void=False),
    ))
    # 作废行（同一子订单！）
    order.items.append(OrderItem(
        id='B2', order_id=merged_tid, oid='oB2', sys_oid='sB2',
        title='作废的另一款商品', shop_mapping_sku='作废编码',
        num=1, price=50, shop_remark='', original_tid=tid_B,
        is_void=True,   # 作废
        raw=make_raw('B2', '作废编码', 1, 0, '作废的另一款商品',
                     tid=tid_B, oid='oB2', price=50, is_void=True),
    ))

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)

    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        engine._process_order(order)

    output = buf.getvalue()
    print(output)

    # 断言：不能出现"已作废/已退款，跳过解析"（子订单B还有有效行）
    assert "已作废/已退款，跳过解析" not in output, (
        "子订单B仍有有效行，不应被整体跳过！"
    )

    # 断言：✅ 材质应出现 1 次（按设计，只打印all_parsed_list[0]）
    # 用 dry_run 编码输出计数来校验两个子订单都被处理
    success_count = output.count("✅ 材质:")
    assert success_count >= 1, (
        f"期望至少1次材质打印（第一张解析摘要），实际 {success_count} 次"
    )
    dryrun_count = len(re.findall(r'🔶 DRY RUN: 新编码 = ', output))
    assert dryrun_count == 2, (
        f"期望2个子订单都正常解析（2条 dry_run 编码输出），实际 {dryrun_count} 条"
    )

    # 断言：子订单B的赠品被解析（圆垫 x1）
    assert ('圆垫', '1') in re.findall(r'🎁 赠品: ([^ ]+) x (\d+)', output), (
        "子订单B的赠品圆垫x1未被正确解析！"
    )

    print("\n✅ 边界测试通过：部分作废的子订单仍正常处理！")


def test_only_gift_suborder_void_skip():
    """
    边界测试：子订单只有赠品行（无普通商品行）且所有赠品行都已作废
    → 该子订单也应跳过（因为 non_gift_regular_items 是空列表，
       但所有非赠品行实际上也是空，视为"无有效行"需要跳过吗？
       这里确认行为：无普通商品行的纯赠品行分组不会被跳过，
       因为 non_gift_regular_items 为空时我们的条件不命中。
       这是合理的——纯赠品行分组的备注若有"赠品不送"等仍需处理。
    """
    print("\n" + "=" * 80)
    print("边界测试: 纯赠品行子订单（作废）→ 解析分组逻辑观察")
    print("=" * 80)

    tid_A = 'sub_A_good'
    tid_C = 'sub_C_gifts_only_void'
    merged_tid = f'{tid_A}&{tid_C}'

    order = Order(
        id='merge_gift_void_test',
        trade_id=merged_tid,
        tid=merged_tid,
        shop_remark='',
    )

    # 子订单A：正常商品
    remark_A = "定制双面格庄园秘境;55x60CM-1张"
    order.items.append(OrderItem(
        id='A1', order_id=merged_tid, oid='oA', sys_oid='sA1',
        title='庄园秘境55x60CM', shop_mapping_sku='旧编码',
        num=1, price=100, shop_remark=remark_A, original_tid=tid_A,
        is_void=False,
        raw=make_raw('A1', '旧编码', 1, 0, '庄园秘境55x60CM',
                     tid=tid_A, oid='oA', price=100, is_void=False),
    ))

    # 子订单C：只有赠品行，且都作废
    # non_gift_regular_items = []，所以我们的 if non_gift_regular_items and ... 不命中
    # 但纯赠品分组走的是正常商品分支，其 group_remark 是空（赠品行shop_remark不收集），
    # 所以会因"备注为空"跳过。这个行为是合理的，这里仅观察无断言异常即可。
    order.items.append(OrderItem(
        id='C_gift1', order_id=merged_tid, oid='oCG1', sys_oid='sCG1',
        title='赠品圆垫', shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
        num=1, price=0, shop_remark='', original_tid=tid_C,
        is_void=True,
        raw=make_raw('C_gift1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
                     1, 0, '赠品圆垫', tid=tid_C, oid='oCG1',
                     film_gift_code='赠品沥水垫小圆或小方', price=0, is_void=True),
    ))

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)

    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            engine._process_order(order)
        except Exception as e:
            pytest.fail(f"纯赠品行作废子订单导致异常: {e}")

    output = buf.getvalue()
    print(output)
    # ✅ 材质应出现 1 次（只有子订单A）
    success_count = output.count("✅ 材质:")
    assert success_count == 1, f"期望只有子订单A解析成功，实际 {success_count} 次"

    print("\n✅ 纯赠品行作废子订单测试通过（无异常，无错误解析）！")


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '-s'])
