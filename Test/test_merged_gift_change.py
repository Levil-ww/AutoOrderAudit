"""
测试合并订单场景：子订单有原赠品行，需根据备注修改赠品编码
================================================================
订单号：6955053702366107312 & 6955042788995765936 & 6955053712970487472

场景描述：
- 子订单1(6955053702366107312)：商品行1条，吸水皮革台面垫50x80，无赠品
- 子订单2(6955042788995765936)：商品行1条，吸水皮革台面垫60x60，无赠品  
- 子订单3(6955053712970487472)：商品行1条 + 赠品行1条
    - 商品行：双面革餐桌垫75x125cm，备注"定制双面革素华牡丹;75x125cm-1张，送赠品方垫-1张"
    - 赠品行(原有)：圆垫编码"吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方"
    - 期望：赠品行被修改为方垫编码"吸水皮革-标准-30x50-随机发；30x50"
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks, ParsedRemark
from core.engine import AutoAuditEngine

adapter = FangguoAdapter()
engine = AutoAuditEngine(adapter=adapter, dry_run=True)


def make_raw(item_id, sku, num, type_val=0, title='测试商品', tid='', oid='', film_gift_code='', shop_remark=''):
    return {
        'id': item_id,
        'orderId': 'merge_order_001',
        'sysOid': f's{item_id}',
        'oid': oid or f'o{item_id}',
        'tid': tid or f't{item_id}',
        'title': title,
        'skuPropertiesName': '',
        'shopMappingSku': sku,
        'originalSkuId': '3644348072270850' if '赠品' in sku else '',
        'originalGoodsId': '3806988491654840639' if '赠品' in sku else '',
        'merchandisePicPath': '',
        'num': num,
        'price': 0 if '赠品' in sku else 100,
        'type': type_val,
        'shopRemark': shop_remark,
        'filmGiftCode': film_gift_code,
        'giftCodeName': '赠品沥水垫小圆或小方' if '赠品' in sku else None,
        'filmGiftNum': 1 if '赠品' in sku else 0,
    }


def build_test_order():
    """构建用户描述的合并订单测试数据"""
    tid1 = '6955053702366107312'  # 子订单1
    tid2 = '6955042788995765936'  # 子订单2
    tid3 = '6955053712970487472'  # 子订单3（包含原赠品行）

    # 子订单1备注：无赠品，正常修改编码
    remark1 = '定制吸水皮革庄园秘境;50x80cm-1张'
    # 子订单2备注：无赠品，正常修改编码
    remark2 = '定制吸水皮革庄园秘境;60x60cm-1张'
    # 子订单3备注：有商品定制信息 + 赠品方垫
    remark3 = '定制双面革素华牡丹;75x125cm-1张，送赠品方垫-1张'

    # 订单级备注（ERP会拼接所有子订单备注）
    order_remark = f'{remark1}，{remark2}，{remark3}'

    items = [
        # ===== 子订单1 商品行 =====
        OrderItem(
            id='item_1',
            order_id='merge_001',
            oid=tid1,
            sys_oid='sys_1',
            title='厨房台面垫吸水皮革台面垫硅藻泥防滑隔热耐高温桌布',
            shop_mapping_sku='吸水皮革-标准-50x80-庄园秘境;50x80',
            num=1,
            price=100,
            original_tid=tid1,
            shop_remark=remark1,
            raw=make_raw('item_1', '吸水皮革-标准-50x80-庄园秘境;50x80', 1, 0,
                        '厨房台面垫吸水皮革台面垫硅藻泥防滑隔热耐高温桌布',
                        tid=tid1, oid=tid1, shop_remark=remark1)
        ),
        # ===== 子订单2 商品行 =====
        OrderItem(
            id='item_2',
            order_id='merge_001',
            oid=tid2,
            sys_oid='sys_2',
            title='厨房台面垫吸水皮革台面垫硅藻泥防滑隔热耐高温桌布',
            shop_mapping_sku='吸水皮革-标准-60x60-庄园秘境;60x60',
            num=1,
            price=100,
            original_tid=tid2,
            shop_remark=remark2,
            raw=make_raw('item_2', '吸水皮革-标准-60x60-庄园秘境;60x60', 1, 0,
                        '厨房台面垫吸水皮革台面垫硅藻泥防滑隔热耐高温桌布',
                        tid=tid2, oid=tid2, shop_remark=remark2)
        ),
        # ===== 子订单3 商品行 =====
        OrderItem(
            id='item_3',
            order_id='merge_001',
            oid=tid3,
            sys_oid='sys_3',
            title='餐桌垫防油免洗防烫皮革桌布轻奢高级感客厅茶几餐垫',
            shop_mapping_sku='双面格-定制-定制尺寸-素华牡丹;75x125CM',
            num=1,
            price=100,
            original_tid=tid3,
            shop_remark=remark3,
            raw=make_raw('item_3', '双面格-定制-定制尺寸-素华牡丹;75x125CM', 1, 0,
                        '餐桌垫防油免洗防烫皮革桌布轻奢高级感客厅茶几餐垫',
                        tid=tid3, oid=tid3, shop_remark=remark3)
        ),
        # ===== 子订单3 原赠品行（圆垫编码，需要被修改为方垫） =====
        OrderItem(
            id='item_4',
            order_id='merge_001',
            oid=tid3,
            sys_oid='sys_4',
            title='赠品沥水垫小圆或小方',
            shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
            num=1,
            price=0,
            original_tid=tid3,
            shop_remark='',  # 赠品行一般无备注
            raw=make_raw('item_4', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                        '赠品沥水垫小圆或小方',
                        tid=tid3, oid=tid3, film_gift_code='3644348072270850',
                        shop_remark='')
        ),
    ]

    merged_trade_id = f'{tid1}&{tid2}&{tid3}'
    order = Order(
        id='merge_001',
        trade_id=merged_trade_id,
        tid=merged_trade_id,
        sys_tid='sys_tid_001',
        shop_remark=order_remark,
        buyer_remark='',
        factory_id=0,
        store_name='抖音-dmf家居日用旗舰',
        items=items,
    )

    return order, tid1, tid2, tid3


def test_parse_remark_gift():
    """第一步：验证备注解析是否正确提取出"方垫"赠品"""
    print("\n" + "=" * 70)
    print("【测试1】备注解析 - 提取赠品方垫")
    print("=" * 70)

    remark3 = '定制双面革素华牡丹;75x125cm-1张，送赠品方垫-1张'
    parsed_list = extract_multiple_remarks(
        remark3,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )

    print(f"备注文本: {remark3}")
    print(f"解析结果数量: {len(parsed_list)}")
    for i, p in enumerate(parsed_list):
        print(f"\n  Parsed[{i}]:")
        print(f"    success={p.success}")
        print(f"    SKU={p.shop_mapping_sku}")
        print(f"    num={p.num}")
        print(f"    gifts={p.gifts}")
        print(f"    gift_name='{p.gift_name}', gift_num={p.gift_num}")
        print(f"    is_stock={p.is_stock}")

    # 验证赠品提取
    has_square_gift = False
    for p in parsed_list:
        all_g = p.gifts or []
        if p.gift_name:
            all_g = all_g + [(p.gift_name, p.gift_num)]
        for name, num in all_g:
            if '方垫' in name:
                has_square_gift = True
                print(f"\n✅ 正确提取到赠品：方垫 x {num}")
                break

    if not has_square_gift:
        print("\n❌ 未提取到'方垫'赠品！")
        return False
    return True


def test_engine_process_merged():
    """第二步：使用完整引擎流程处理合并订单，验证赠品编码修改"""
    print("\n" + "=" * 70)
    print("【测试2】引擎流程 - 处理合并订单赠品编码修改")
    print("=" * 70)

    order, tid1, tid2, tid3 = build_test_order()

    print(f"\n订单号: {order.trade_id}")
    print(f"商品行数: {len(order.items)}")
    for i, item in enumerate(order.items):
        g = "[赠]" if adapter._is_gift_item(item) else "[商]"
        print(f"  [{i}] {g} tid={item.original_tid[-6:] if item.original_tid else 'None'} "
              f"sku={item.shop_mapping_sku[:55]} num={item.num}")

    # Mock API调用，捕获提交的payload
    captured = {}

    def mock_post(url, json=None, timeout=None):
        captured['payload'] = json
        captured['url'] = url
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
        return resp

    adapter._session.post = mock_post

    # 使用引擎处理（dry_run模式下adapter内部也会走逻辑）
    print("\n--- 开始引擎处理 ---")
    engine_process_order = AutoAuditEngine(adapter=adapter, dry_run=False)
    engine_process_order._process_order(order)

    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])

    if not all_items:
        print("\n⚠️ 未提交修改（可能判定为已正确），改为直接调用adapter验证")
        # 改为手动构造parsed_list调用update_merchant_code
        return test_direct_adapter_call()

    print(f"\n--- 提交结果 ---")
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    print(f"提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})")

    return verify_result(all_items, tid3)


def test_direct_adapter_call():
    """直接调用 adapter.update_merchant_code，模拟引擎分组后的parsed_list"""
    print("\n" + "=" * 70)
    print("【测试3】直接Adapter调用 - 模拟引擎分组处理结果")
    print("=" * 70)

    order, tid1, tid2, tid3 = build_test_order()

    remark1 = '定制吸水皮革庄园秘境;50x80cm-1张'
    remark2 = '定制吸水皮革庄园秘境;60x60cm-1张'
    remark3 = '定制双面革素华牡丹;75x125cm-1张，送赠品方垫-1张'

    # 分别解析3个子订单的备注
    parsed1 = extract_multiple_remarks(remark1, material_map=adapter.material_map,
                                       material_matcher=adapter.get_material_matcher())
    parsed2 = extract_multiple_remarks(remark2, material_map=adapter.material_map,
                                       material_matcher=adapter.get_material_matcher())
    parsed3 = extract_multiple_remarks(remark3, material_map=adapter.material_map,
                                       material_matcher=adapter.get_material_matcher())

    print("\n--- 各子订单解析结果 ---")
    print(f"子订单1({tid1[-6:]}):")
    for p in parsed1:
        print(f"  SKU={p.shop_mapping_sku}, gifts={p.gifts}, gift_name={p.gift_name}")

    print(f"子订单2({tid2[-6:]}):")
    for p in parsed2:
        print(f"  SKU={p.shop_mapping_sku}, gifts={p.gifts}, gift_name={p.gift_name}")

    print(f"子订单3({tid3[-6:]}):")
    for p in parsed3:
        print(f"  SKU={p.shop_mapping_sku}, gifts={p.gifts}, gift_name={p.gift_name}")

    # 为每个parsed设置original_tid，模拟引擎分组处理
    def attach_tid(parsed_list, tid, remark):
        result = []
        for p in parsed_list:
            np = ParsedRemark(
                material_code=p.material_code,
                color_code=p.color_code,
                model_code=p.model_code,
                picture_code=p.picture_code,
                num=p.num,
                success=p.success,
                gift_name=p.gift_name,
                gift_num=p.gift_num,
                gifts=list(p.gifts),
                original_tid=tid,
                shop_remark=remark,
                is_stock=p.is_stock,
                base_picture_code=p.base_picture_code,
            )
            result.append(np)
        return result

    all_parsed_list = []
    all_parsed_list.extend(attach_tid(parsed1, tid1, remark1))
    all_parsed_list.extend(attach_tid(parsed2, tid2, remark2))
    all_parsed_list.extend(attach_tid(parsed3, tid3, remark3))

    print(f"\n合并后parsed_list共 {len(all_parsed_list)} 条")

    # Mock API
    captured = {}

    def mock_post(url, json=None, timeout=None):
        captured['payload'] = json
        captured['url'] = url
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
        return resp

    adapter._session.post = mock_post

    # 调用修改
    print("\n--- 调用 adapter.update_merchant_code ---")
    result = adapter.update_merchant_code(
        order,
        all_parsed_list[0] if all_parsed_list else None,
        all_parsed_list,
        None,  # price_diff_updates
        gift_no_ship=False,
        gift_no_ship_tids=None,
    )
    print(f"调用返回: {result}")

    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])

    if not all_items:
        print("\n❌ 未提交任何修改（可能内部判断已正确？）")
        return False

    return verify_result(all_items, tid3)


def verify_result(all_items, tid3):
    """验证提交结果：子订单3的赠品行应被修改为方垫编码"""
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]

    print(f"\n--- 提交结果分析 ---")
    print(f"总商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})")

    def clean(s):
        return str(s or '').replace('<font color="red">', '').replace('</font>', '')

    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        sku = clean(it.get('shopMappingSku', ''))
        oid = str(it.get('oid', ''))
        tid_short = oid[-6:] if len(oid) >= 6 else oid
        num = it.get('num', '?')
        is_g = '赠品' if '赠品' in sku or '30x50' in sku else '商品'
        print(f"  [{i}] {flag} {is_g} tid={tid_short} sku={sku[:60]} num={num}")

    print("\n--- 关键验证 ---")

    # 定义期望的赠品编码（赠品材质固定为"吸水皮革"，不继承商品材质）
    ROUND_GIFT_SKU = '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方'
    SQUARE_GIFT_SKU = '吸水皮革-标准-30x50-随机发；30x50'
    errors = []

    print(f"\n期望赠品编码：")
    print(f"  圆垫 -> {ROUND_GIFT_SKU}")
    print(f"  方垫 -> {SQUARE_GIFT_SKU}")

    # 1. 找到所有赠品行
    gift_items_in_active = []
    for it in active_items:
        sku = clean(it.get('shopMappingSku', ''))
        oid = str(it.get('oid', ''))
        # 识别赠品行：包含"赠品"或匹配方垫/圆垫编码格式
        is_gift_sku = (
            '赠品沥水垫' in sku
            or sku == ROUND_GIFT_SKU
            or sku == SQUARE_GIFT_SKU
            or ('30x50' in sku and '随机发' in sku)
            or (it.get('filmGiftCode') and str(it.get('filmGiftCode')).strip())
            or (it.get('giftCodeName'))
        )
        if is_gift_sku:
            gift_items_in_active.append((sku, oid, it))

    print(f"识别到赠品行 {len(gift_items_in_active)} 条:")
    for sku, oid, it in gift_items_in_active:
        print(f"  - tid={oid[-6:] if len(oid) >= 6 else oid} sku={sku}")

    # 2. 检查子订单3(tid3)的赠品行：必须是方垫编码，不应该是圆垫编码
    tid3_gift_items = [(sku, oid, it) for sku, oid, it in gift_items_in_active
                       if (oid and oid.endswith(tid3[-10:])) or (tid3 and tid3.endswith(oid[-10:] if len(oid) >= 10 else ''))]

        # 如果按oid精确匹配不到，用更宽松的方式：遍历时根据原始order的original_tid
    if not tid3_gift_items:
        # 直接看是否存在方垫编码的赠品行（严格精确匹配）
        square_gifts = [(sku, oid, it) for sku, oid, it in gift_items_in_active
                        if sku == SQUARE_GIFT_SKU]
        round_gifts = [(sku, oid, it) for sku, oid, it in gift_items_in_active
                       if sku == ROUND_GIFT_SKU or '赠品沥水垫小圆或小方' in sku]

        print(f"\n宽松检查：方垫赠品行={len(square_gifts)}条, 圆垫赠品行={len(round_gifts)}条")

        if len(square_gifts) == 1 and len(round_gifts) == 0:
            print("✅ 检测到：原圆垫赠品行已被修改为方垫编码（精确匹配），无多余圆垫行")
        elif len(square_gifts) >= 1:
            # 有一个方垫，但圆垫还在（可能没改而是新增的？）
            if len(round_gifts) >= 1:
                errors.append(f"圆垫赠品行仍然存在！期望原行被修改为方垫，不应保留圆垫")
                errors.append(f"  圆垫行sku={round_gifts[0][0][:50]}")
                if len(square_gifts) == 1:
                    errors.append(f"  方垫行是新增的(不对)，应该是修改原圆垫行")
            # 还要检查方垫的材质是否为"吸水皮革"（防止出现"双面格-标准-30x50..."这种错误）
            for sku, oid, it in square_gifts:
                if not sku.startswith('吸水皮革-'):
                    errors.append(f"方垫赠品行材质错误！应以'吸水皮革'开头，实际: {sku}")
                    break
        else:
            errors.append("未找到精确匹配方垫编码的赠品行！候选列表：")
            for sku, oid, it in gift_items_in_active:
                errors.append(f"  - tid={oid[-6:]} sku={sku}")

        # 检查作废行里有没有原圆垫赠品行（应该被修改而非作废新增）
        round_void = []
        for it in void_items:
            sku = clean(it.get('shopMappingSku', ''))
            if '赠品沥水垫小圆或小方' in sku or sku == ROUND_GIFT_SKU:
                round_void.append(sku)
        if round_void:
            errors.append(f"原圆垫赠品行被作废了{len(round_void)}条！应该是修改原行编码，不是作废+新增")
            for s in round_void:
                errors.append(f"  作废的sku: {s[:50]}")

    else:
        # 精确匹配到子订单3的赠品行
        for sku, oid, it in tid3_gift_items:
            if sku == ROUND_GIFT_SKU or '赠品沥水垫小圆或小方' in sku:
                errors.append(f"❌ 子订单3的赠品行仍是圆垫编码！应该改为方垫编码")
                errors.append(f"   实际sku={sku}")
                errors.append(f"   期望sku={SQUARE_GIFT_SKU}")
            elif sku == SQUARE_GIFT_SKU:
                print(f"✅ 子订单3的赠品行已正确修改为方垫编码(精确匹配): {sku}")
            elif '30x50' in sku and '随机发' in sku:
                # 编码接近正确，但检查材质
                if sku.startswith('吸水皮革-'):
                    print(f"⚠️  子订单3赠品编码匹配但不完全精确: {sku}")
                else:
                    errors.append(f"❌ 子订单3赠品材质错误！应固定为'吸水皮革'")
                    errors.append(f"   实际sku={sku}")
                    errors.append(f"   期望sku={SQUARE_GIFT_SKU}")
            else:
                errors.append(f"子订单3赠品行编码不符合预期: {sku}")

    # 3. 检查普通商品行的编码是否也正确
    normal_items = [it for it in active_items if not (
        '赠品' in clean(it.get('shopMappingSku', ''))
        or '30x50' in clean(it.get('shopMappingSku', ''))
    )]
    print(f"\n普通商品行共 {len(normal_items)} 条")
    for it in normal_items:
        sku = clean(it.get('shopMappingSku', ''))
        oid = str(it.get('oid', ''))
        print(f"  - tid={oid[-6:] if len(oid) >= 6 else oid} sku={sku[:60]} num={it.get('num')}")

    if len(normal_items) >= 3:
        print(f"✅ 普通商品行数正确（至少3条，3个子订单各1条）")
    else:
        errors.append(f"普通商品行不足！期望≥3，实际{len(normal_items)}")

    # 总结
    print("\n" + "=" * 70)
    if errors:
        print("❌ 验证失败:")
        for e in errors:
            print(f"   - {e}")
        return False
    else:
        print("🎉 所有验证通过！子订单3的原赠品行被正确修改为方垫编码")
        return True


def run_all_tests():
    print("=" * 70)
    print("合并订单赠品编码修改场景 - 测试套件")
    print("订单号: 6955053702366107312 & 6955042788995765936 & 6955053712970487472")
    print("=" * 70)

    results = []
    results.append(("备注解析-提取方垫赠品", test_parse_remark_gift()))
    results.append(("直接Adapter调用-赠品修改", test_direct_adapter_call()))

    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    return all_passed


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
