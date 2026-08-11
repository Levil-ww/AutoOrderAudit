import sys
import io
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.engine import AutoAuditEngine


SAME_TITLE = "DMF厨房台面专用沥水垫硅藻泥洗手池水槽边吸水垫长条灶台隔热垫"


def _make_engine():
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter, dry_run=True)
    engine.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}
    return engine, adapter


def _check_implied_detection(order, expected_trigger, expected_no_remark_id=None, case_name=""):
    """辅助：检查 _detect_implied_price_diff_scenario 是否按预期触发"""
    engine, _ = _make_engine()
    result = engine._detect_implied_price_diff_scenario(order)
    triggered = result is not None

    status = "✅" if triggered == expected_trigger else "❌"
    print(f"{status} {case_name}")
    print(f"    预期触发={expected_trigger}, 实际触发={triggered}")

    if expected_trigger:
        assert triggered, f"[{case_name}] 期望触发但未触发"
        # 验证触发了正确的无备注行
        if expected_no_remark_id:
            items = result[0]['items']
            assert len(items) == 1, f"[{case_name}] 应只返回1个补差价行，实际={len(items)}"
            assert items[0].id == expected_no_remark_id or items[0].oid == expected_no_remark_id, \
                f"[{case_name}] 补差价行ID不符，期望={expected_no_remark_id}"
            assert result[0]['ship'] == False, f"[{case_name}] ship应为False（不打印）"
            print(f"    ✅ 无备注行ID={items[0].id or items[0].oid} 正确，ship=False")
    else:
        assert not triggered, f"[{case_name}] 不应触发但结果={result}"
    print()
    return result


# ============================================================
# Liveness 测试：应该触发的情况
# ============================================================

def test_liveness_user_scenario():
    """Liveness 1：用户实际场景（订单3316180332393021293）
    - 同标题 2 行
    - 一行有 item 备注（含'共1张'），一行无备注
    """
    print('=' * 80)
    print("Liveness 1: 用户实际场景 - 单行item备注含'共1张'，另一行无备注")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='3316180332393021293',
        tid='3316180332393021293',
        shop_remark="",  # 订单级备注为空，备注在商品行级
    )
    order.items.append(OrderItem(
        id='item_has_remark',
        order_id='3316180332393021293',
        oid='oid_has_remark',
        original_tid='3316180332393021293',
        title=SAME_TITLE,
        shop_mapping_sku="吸水皮革-定制-定制尺寸/裁剪有图-蔓生花;50x80CM",
        shop_remark="定制吸水皮革蔓生花50x180cm-1张，共1张",
        num=1,
        price=42.71,
    ))
    order.items.append(OrderItem(
        id='item_no_remark',
        order_id='3316180332393021293',
        oid='oid_no_remark',
        original_tid='3316180332393021293',
        title=SAME_TITLE,
        shop_mapping_sku="吸水皮革-标准-50x100-蔓生花;50x100",
        shop_remark="",  # 无备注
        num=1,
        price=53.38,
    ))

    _check_implied_detection(
        order,
        expected_trigger=True,
        expected_no_remark_id='item_no_remark',
        case_name="单行item备注含'共1张'"
    )


def test_liveness_order_remark_with_total():
    """Liveness 2：'共X张'出现在订单级备注，不在商品行级备注
    - 同标题 2 行
    - 一行有 item 备注（只是修改信息无'共X张'），一行无备注
    - order.shop_remark 包含'共1张'
    """
    print('=' * 80)
    print("Liveness 2: '共X张'在订单级备注")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='normal_002',
        tid='normal_002',
        shop_remark="定制吸水皮革蔓生花50x180cm-1张，共1张",
    )
    order.items.append(OrderItem(
        id='item_a',
        order_id='normal_002',
        oid='oid_a',
        title=SAME_TITLE,
        shop_remark="尺寸改为50x180",  # 有备注但不含"共X张"
        num=1,
        price=42.71,
    ))
    order.items.append(OrderItem(
        id='item_b',
        order_id='normal_002',
        oid='oid_b',
        title=SAME_TITLE,
        shop_remark="",  # 无备注
        num=1,
        price=53.38,
    ))

    _check_implied_detection(
        order,
        expected_trigger=True,
        expected_no_remark_id='item_b',
        case_name="'共X张'在订单级备注"
    )


def test_liveness_total_prefix_zong():
    """Liveness 3：'总共1张'（带'总'前缀）应正确识别"""
    print('=' * 80)
    print("Liveness 3: '总共X张'（总前缀）识别")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='normal_003',
        tid='normal_003',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='h1',
        order_id='normal_003',
        oid='h1',
        title=SAME_TITLE,
        shop_remark="定制XXX;50x180，总共1张",
        num=1,
        price=1.0,
    ))
    order.items.append(OrderItem(
        id='n1',
        order_id='normal_003',
        oid='n1',
        title=SAME_TITLE,
        shop_remark="",
        num=1,
        price=1.0,
    ))

    _check_implied_detection(
        order,
        expected_trigger=True,
        expected_no_remark_id='n1',
        case_name="'总共1张'识别"
    )


def test_liveness_space_in_total():
    """Liveness 4：'共 2 张'（数字前后有空格）应正确识别"""
    print('=' * 80)
    print("Liveness 4: '共 X 张'（含空格）识别")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='normal_004',
        tid='normal_004',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='h2',
        order_id='normal_004',
        oid='h2',
        title=SAME_TITLE,
        shop_remark="定制YYY，共 2 张",
        num=1,
        price=1.0,
    ))
    order.items.append(OrderItem(
        id='n2',
        order_id='normal_004',
        oid='n2',
        title=SAME_TITLE,
        shop_remark="",
        num=1,
        price=1.0,
    ))

    _check_implied_detection(
        order,
        expected_trigger=True,
        expected_no_remark_id='n2',
        case_name="'共 2 张'含空格识别"
    )


def test_liveness_remark_on_second_item():
    """Liveness 5：有备注的行在第二个商品行，无备注行是第一个"""
    print('=' * 80)
    print("Liveness 5: 有备注行在后面（顺序不敏感）")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='normal_005',
        tid='normal_005',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='first_no_remark',
        order_id='normal_005',
        oid='f_nr',
        title=SAME_TITLE,
        shop_remark="",  # 无备注
        num=1,
        price=1.0,
    ))
    order.items.append(OrderItem(
        id='second_has_remark',
        order_id='normal_005',
        oid='s_hr',
        title=SAME_TITLE,
        shop_remark="定制ZZZ，共1张",  # 有备注
        num=1,
        price=1.0,
    ))

    _check_implied_detection(
        order,
        expected_trigger=True,
        expected_no_remark_id='first_no_remark',
        case_name="顺序不敏感：有备注行在后"
    )


# ============================================================
# Safety 测试：绝不能触发的情况
# ============================================================

def test_safety_both_have_remark():
    """Safety 1：两个商品行都有备注 → 绝不能触发"""
    print('=' * 80)
    print("Safety 1: 两个商品行都有备注 → 不触发")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='safety_001',
        tid='safety_001',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='both_a',
        order_id='safety_001',
        oid='ba',
        title=SAME_TITLE,
        shop_remark="定制A，共1张",
        num=1,
        price=1.0,
    ))
    order.items.append(OrderItem(
        id='both_b',
        order_id='safety_001',
        oid='bb',
        title=SAME_TITLE,
        shop_remark="定制B，改尺寸",
        num=1,
        price=1.0,
    ))

    _check_implied_detection(order, False, case_name="两个都有备注")


def test_safety_different_titles():
    """Safety 2：两个商品行标题不一致 → 绝不能触发"""
    print('=' * 80)
    print("Safety 2: 标题不一致 → 不触发")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='safety_002',
        tid='safety_002',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='diff_a',
        order_id='safety_002',
        oid='da',
        title=SAME_TITLE,
        shop_remark="定制A，共1张",
        num=1,
        price=1.0,
    ))
    order.items.append(OrderItem(
        id='diff_b',
        order_id='safety_002',
        oid='db',
        title="另一种商品标题 硅藻泥软垫",  # 不同标题
        shop_remark="",
        num=1,
        price=1.0,
    ))

    _check_implied_detection(order, False, case_name="标题不一致")


def test_safety_merged_order():
    """Safety 3：合并订单（&订单号 + 多original_tid）→ 绝不能走这里，合并订单有专门分支"""
    print('=' * 80)
    print("Safety 3: 合并订单 → 在此检测之前已返回，这里若检测到也不触发（实际不会调用）")
    print('=' * 80)

    # 合并订单在 _process_order 中会先 return，所以这里实际不会调用
    # 但 _detect_implied_price_diff_scenario 本身不检查 is_merged（它假设在非合并订单中调用）
    # 为了更健壮，我们也验证一下如果调用它（虽然不会）不会误判非条件
    # 这里我们只验证非合并订单+3个商品行不触发（Safety 5）
    print("  ℹ️  合并订单检测由 _process_order 上游完成，这里不重复验证")
    print("  ✅ (由调用顺序保证)")
    print()


def test_safety_only_one_item():
    """Safety 4：只有1个商品行 → 不触发"""
    print('=' * 80)
    print("Safety 4: 只有1个商品行 → 不触发")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='safety_004',
        tid='safety_004',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='only_1',
        order_id='safety_004',
        oid='o1',
        title=SAME_TITLE,
        shop_remark="定制A，共1张",
        num=1,
        price=1.0,
    ))

    _check_implied_detection(order, False, case_name="只有1个商品行")


def test_safety_three_or_more_items():
    """Safety 5：3个及以上商品行 → 不触发"""
    print('=' * 80)
    print("Safety 5: 3个商品行 → 不触发")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='safety_005',
        tid='safety_005',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='t1', order_id='safety_005', oid='t1', title=SAME_TITLE,
        shop_remark="定制A，共1张", num=1, price=1.0,
    ))
    order.items.append(OrderItem(
        id='t2', order_id='safety_005', oid='t2', title=SAME_TITLE,
        shop_remark="", num=1, price=1.0,
    ))
    order.items.append(OrderItem(  # 第三个行（注意：标题不含"赠品"，避免被_is_gift_item过滤）
        id='t3', order_id='safety_005', oid='t3', title="第三种不同的普通商品 硅藻泥地垫",
        shop_remark="", num=1, price=1.0,
    ))

    _check_implied_detection(order, False, case_name="3个商品行（非赠品未过滤，这里直接按3个有效→不触发）")


def test_safety_no_total_keyword_in_remark():
    """Safety 6：备注中没有"共X张" → 不触发（可能只是普通修改，非凑面积）"""
    print('=' * 80)
    print("Safety 6: 备注无'共X张' → 不触发")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='safety_006',
        tid='safety_006',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='s6a', order_id='safety_006', oid='s6a', title=SAME_TITLE,
        shop_remark="定制吸水皮革蔓生花50x180cm-1张",  # 无"共1张"
        num=1, price=1.0,
    ))
    order.items.append(OrderItem(
        id='s6b', order_id='safety_006', oid='s6b', title=SAME_TITLE,
        shop_remark="", num=1, price=1.0,
    ))

    _check_implied_detection(order, False, case_name="备注无'共X张'")


def test_safety_both_no_remark():
    """Safety 7：两个商品行都无备注 → 不触发"""
    print('=' * 80)
    print("Safety 7: 两个都无备注 → 不触发")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='safety_007',
        tid='safety_007',
        shop_remark="普通备注但无共X张",
    )
    order.items.append(OrderItem(
        id='s7a', order_id='safety_007', oid='s7a', title=SAME_TITLE,
        shop_remark="", num=1, price=1.0,
    ))
    order.items.append(OrderItem(
        id='s7b', order_id='safety_007', oid='s7b', title=SAME_TITLE,
        shop_remark="", num=1, price=1.0,
    ))

    _check_implied_detection(order, False, case_name="两个都无备注")


def test_safety_void_item_counted_as_invalid():
    """Safety 8：一行作废 → 有效行只剩1个 → 不触发"""
    print('=' * 80)
    print("Safety 8: 一个作废+一个有效 → 不触发（有效行<2）")
    print('=' * 80)

    order = Order(
        id='test',
        trade_id='safety_008',
        tid='safety_008',
        shop_remark="",
    )
    order.items.append(OrderItem(
        id='s8a_void', order_id='safety_008', oid='s8a', title=SAME_TITLE,
        shop_remark="定制A，共1张", num=1, price=1.0, is_void=True,  # 作废
    ))
    order.items.append(OrderItem(
        id='s8b_valid', order_id='safety_008', oid='s8b', title=SAME_TITLE,
        shop_remark="", num=1, price=1.0,
    ))

    _check_implied_detection(order, False, case_name="一个作废+一个有效")


# ============================================================
# 端到端测试：实际调用 _process_order 验证编码被正确修改
# ============================================================

def test_e2e_user_scenario_dry_run():
    """E2E 测试：模拟用户实际订单（dry_run），验证补差价行被正确标记"""
    print('=' * 80)
    print("E2E: 用户实际场景 dry_run 验证")
    print('=' * 80)

    engine, adapter = _make_engine()

    order = Order(
        id='test',
        trade_id='3316180332393021293',
        tid='3316180332393021293',
        shop_remark="定制吸水皮革蔓生花50x180cm-1张，共1张",
    )
    order.items.append(OrderItem(
        id='item_main',
        order_id='3316180332393021293',
        oid='oid_main',
        original_tid='3316180332393021293',
        title=SAME_TITLE,
        sku_properties_name="蔓生花:50x80cm",
        shop_mapping_sku="吸水皮革-定制-定制尺寸/裁剪有图-蔓生花;50x80CM",
        shop_remark="",
        num=1,
        price=42.71,
    ))
    order.items.append(OrderItem(
        id='item_price_diff',  # 应该被标记为补差价不打印
        order_id='3316180332393021293',
        oid='oid_price_diff',
        original_tid='3316180332393021293',
        title=SAME_TITLE,
        sku_properties_name="蔓生花:50x100cm",
        shop_mapping_sku="吸水皮革-标准-50x100-蔓生花;50x100",
        shop_remark="",
        num=1,
        price=53.38,
    ))

    print(f"订单号: {order.trade_id}")
    print(f"订单级备注: {order.shop_remark}")
    print(f"商品行数: {len(order.items)}")
    print()

    engine._process_order(order)

    # dry_run 下 success=1 表示修改路径被正确执行
    assert engine.stats['success'] == 1, \
        f"期望 success=1，实际 success={engine.stats['success']}, skipped={engine.stats['skipped']}, failed={engine.stats['failed']}"
    print("✅ E2E 通过：订单被正确处理（success=1）")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("隐含补差价场景检测测试套件")
    print("=" * 80 + "\n")

    # --- Liveness 测试 ---
    test_liveness_user_scenario()
    test_liveness_order_remark_with_total()
    test_liveness_total_prefix_zong()
    test_liveness_space_in_total()
    test_liveness_remark_on_second_item()

    # --- Safety 测试 ---
    test_safety_both_have_remark()
    test_safety_different_titles()
    test_safety_merged_order()
    test_safety_only_one_item()
    test_safety_three_or_more_items()
    test_safety_no_total_keyword_in_remark()
    test_safety_both_no_remark()
    test_safety_void_item_counted_as_invalid()

    # --- E2E ---
    test_e2e_user_scenario_dry_run()

    print("=" * 80)
    print("🎉 所有测试通过！")
    print("=" * 80)
