"""
测试"赠品换赠品"场景 - 检查-修改-创建逻辑验证
================================================
场景说明：
  备注 "定制吸水皮革森夜私语;58x100CM-1张，赠品换赠品沥水垫30x50-1张"

  三种场景：
  1. 已有赠品行(圆垫编码) → 编码不匹配，应修改为方垫编码
  2. 已有赠品行(方垫编码) → 编码已匹配，应跳过修改（already correct路径）
  3. 无赠品行 → 应创建新赠品行并赋方垫编码
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from core.parser import ParsedRemark
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks

adapter = FangguoAdapter()

# 期望编码常量
EXPECTED_SQUARE_GIFT_SKU = '吸水皮革-标准-30x50-随机发；30x50'
EXPECTED_ROUND_GIFT_SKU = '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方'
PRODUCT_SKU = '吸水皮革-定制-定制尺寸-森夜私语;58x100CM'

TID = '69550535140957472'  # 示例子订单号
REMARK = '定制吸水皮革森夜私语;58x100CM-1张，赠品换赠品沥水垫30x50-1张'


def make_raw(item_id, sku, num, type_val=0, title='测试商品', tid='', oid='',
             film_gift_code='', gift_code_name='', price=100, shop_remark=''):
    return {
        'id': item_id,
        'orderId': 'order_001',
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
        'giftCodeName': gift_code_name,
        'filmGiftNum': num if film_gift_code else 0,
    }


def build_parsed_list_with_gift(remark, tid, gift_name, gift_num):
    """解析备注并构造带original_tid的ParsedRemark列表"""
    parsed_list = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )
    result = []
    for p in parsed_list:
        np = ParsedRemark(
            material_code=p.material_code,
            color_code=p.color_code,
            model_code=p.model_code,
            picture_code=p.picture_code,
            num=p.num,
            success=p.success,
            gift_name=gift_name,
            gift_num=gift_num,
            gifts=[(gift_name, gift_num)],
            original_tid=tid,
            shop_remark=remark,
            is_stock=p.is_stock,
            base_picture_code=p.base_picture_code,
        )
        result.append(np)
    return result


def parse_gift_from_remark():
    """测试1：验证备注解析是否正确提取"沥水垫30x50"赠品"""
    print("\n" + "=" * 70)
    print("【测试1】备注解析验证 - '换赠品沥水垫30x50'")
    print("=" * 70)

    parsed_list = extract_multiple_remarks(
        REMARK,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )

    print(f"备注: {REMARK}")
    print(f"解析结果数量: {len(parsed_list)}")
    for i, p in enumerate(parsed_list):
        print(f"\n  Parsed[{i}]:")
        print(f"    success={p.success}")
        print(f"    SKU={p.shop_mapping_sku}")
        print(f"    num={p.num}")
        print(f"    gifts={p.gifts}")
        print(f"    gift_name='{p.gift_name}', gift_num={p.gift_num}")

    errors = []
    if not parsed_list or not any(p.success for p in parsed_list):
        errors.append("商品解析失败！")

    gift_found = False
    for p in parsed_list:
        for name, num in (p.gifts or []):
            print(f"\n  赠品: {name} x {num}")
            if '30x50' in name or '沥水垫30x50' in name:
                gift_found = True
                print(f"  ✅ 正确识别到方垫赠品")
                if num != 1:
                    errors.append(f"赠品数量错误！期望1，实际{num}")
            elif '圆垫' in name and '方垫' not in name:
                errors.append(f"❌ 错误识别为圆垫赠品！应为方垫/30x50")

    if not gift_found:
        errors.append("❌ 未提取到方垫/30x50赠品！")

    if errors:
        for e in errors:
            print(f"  ❌ {e}")
        return False
    else:
        print("  🎉 备注解析正确！")
        return True


def test_scenario1_gift_exists_code_mismatch():
    """
    场景1：已有赠品行(圆垫编码)，编码不匹配 → 应修改为方垫编码
    """
    print("\n" + "=" * 70)
    print("【场景1】已有赠品行(圆垫)，编码不匹配 → 修改")
    print("=" * 70)

    # 商品行 + 原赠品行(圆垫编码)
    items = [
        OrderItem(
            id='item_prod',
            order_id='order_001',
            oid=TID,
            sys_oid='sys_prod',
            title='长条厨房防油贴',
            shop_mapping_sku=PRODUCT_SKU,
            num=1,
            price=100,
            original_tid=TID,
            shop_remark=REMARK,
            raw=make_raw('item_prod', PRODUCT_SKU, 1, 0,
                        '长条厨房防油贴', tid=TID, oid=TID, shop_remark=REMARK)
        ),
        OrderItem(
            id='item_gift_old',
            order_id='order_001',
            oid=TID,
            sys_oid='sys_gift',
            title='赠品沥水垫小圆或小方',
            shop_mapping_sku=EXPECTED_ROUND_GIFT_SKU,  # 原圆垫编码
            num=1,
            price=0,
            original_tid=TID,
            shop_remark='',
            raw=make_raw('item_gift_old', EXPECTED_ROUND_GIFT_SKU, 1, 0,
                        '赠品沥水垫小圆或小方', tid=TID, oid=TID,
                        film_gift_code='3644348072270850',
                        gift_code_name='赠品沥水垫小圆或小方', price=0)
        ),
    ]

    order = Order(
        id='order_001',
        trade_id=TID,
        tid=TID,
        sys_tid='',
        shop_remark=REMARK,
        buyer_remark='',
        factory_id=0,
        store_name='抖音-dmf家居日用旗舰',
        items=items,
    )

    # 构造parsed_list（带original_tid）
    parsed_list = build_parsed_list_with_gift(REMARK, TID, '沥水垫30x50', 1)

    print(f"商品行: SKU={items[0].shop_mapping_sku[:50]}")
    print(f"原赠品行: SKU={items[1].shop_mapping_sku} (圆垫)")
    print(f"期望赠品编码: {EXPECTED_SQUARE_GIFT_SKU} (方垫)")

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

    result = adapter.update_merchant_code(
        order, parsed_list[0] if parsed_list else None, parsed_list,
        None, gift_no_ship=False, gift_no_ship_tids=None,
    )
    print(f"\n调用返回: {result}")

    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])

    if not all_items:
        print("⚠️ 未提交修改（可能判定为已正确）")
        return False

    return verify_payload(all_items, EXPECTED_SQUARE_GIFT_SKU, EXPECTED_ROUND_GIFT_SKU,
                          expect_gift_modified=True, scenario_desc="场景1")


def test_scenario2_gift_exists_code_match():
    """
    场景2：已有赠品行(方垫编码)，编码已匹配 → 程序应判定为已正确，跳过修改
    注意：此场景在products也正确时走"already correct"路径
    但products也需要正确，所以我们让products编码也完全匹配
    """
    print("\n" + "=" * 70)
    print("【场景2】已有赠品行(方垫)，编码已匹配 → 跳过修改")
    print("=" * 70)

    # 商品行编码与解析结果完全一致
    item_prod_sku = '吸水皮革-定制-定制尺寸-森夜私语;58x100CM'

    items = [
        OrderItem(
            id='item_prod',
            order_id='order_002',
            oid=TID,
            sys_oid='sys_prod',
            title='长条厨房防油贴',
            shop_mapping_sku=item_prod_sku,
            num=1,
            price=100,
            original_tid=TID,
            shop_remark=REMARK,
            raw=make_raw('item_prod', item_prod_sku, 1, 0,
                        '长条厨房防油贴', tid=TID, oid=TID, shop_remark=REMARK)
        ),
        OrderItem(
            id='item_gift',
            order_id='order_002',
            oid=TID,
            sys_oid='sys_gift',
            title='赠品沥水垫30x50cm',
            shop_mapping_sku=EXPECTED_SQUARE_GIFT_SKU,  # 已经是正确的方垫编码
            num=1,
            price=0,
            original_tid=TID,
            shop_remark='',
            raw=make_raw('item_gift', EXPECTED_SQUARE_GIFT_SKU, 1, 0,
                        '赠品沥水垫30x50cm', tid=TID, oid=TID,
                        film_gift_code='364431371257858',
                        gift_code_name='随机发；30x50', price=0)
        ),
    ]

    order = Order(
        id='order_002',
        trade_id=TID,
        tid=TID,
        sys_tid='',
        shop_remark=REMARK,
        buyer_remark='',
        factory_id=0,
        store_name='抖音-dmf家居日用旗舰',
        items=items,
    )

    parsed_list = build_parsed_list_with_gift(REMARK, TID, '沥水垫30x50', 1)

    print(f"商品行: SKU={items[0].shop_mapping_sku}")
    print(f"原赠品行: SKU={items[1].shop_mapping_sku} (已是方垫!)")
    print(f"期望编码: {EXPECTED_SQUARE_GIFT_SKU}")

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
        order, parsed_list[0] if parsed_list else None, parsed_list,
        None, gift_no_ship=False, gift_no_ship_tids=None,
    )
    print(f"\n调用返回: {result}")

    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])

    if not all_items:
        print("✅ 场景2: 程序判定订单已正确，未提交修改 (符合预期)")
        return True

    return verify_payload(all_items, EXPECTED_SQUARE_GIFT_SKU, EXPECTED_ROUND_GIFT_SKU,
                          expect_gift_modified=False, scenario_desc="场景2")


def test_scenario3_no_gift_item():
    """
    场景3：无赠品行 → 应创建新赠品行并赋方垫编码
    """
    print("\n" + "=" * 70)
    print("【场景3】无赠品行 → 创建新赠品行并赋方垫编码")
    print("=" * 70)

    items = [
        OrderItem(
            id='item_prod',
            order_id='order_003',
            oid=TID,
            sys_oid='sys_prod',
            title='长条厨房防油贴',
            shop_mapping_sku=PRODUCT_SKU,
            num=1,
            price=100,
            original_tid=TID,
            shop_remark=REMARK,
            raw=make_raw('item_prod', PRODUCT_SKU, 1, 0,
                        '长条厨房防油贴', tid=TID, oid=TID, shop_remark=REMARK)
        ),
        # ⚠️ 没有赠品行！
    ]

    order = Order(
        id='order_003',
        trade_id=TID,
        tid=TID,
        sys_tid='',
        shop_remark=REMARK,
        buyer_remark='',
        factory_id=0,
        store_name='抖音-dmf家居日用旗舰',
        items=items,
    )

    parsed_list = build_parsed_list_with_gift(REMARK, TID, '沥水垫30x50', 1)

    print(f"商品行: SKU={items[0].shop_mapping_sku[:50]}")
    print(f"赠品行: (无)")
    print(f"期望: 创建新赠品行，编码={EXPECTED_SQUARE_GIFT_SKU}")

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
        order, parsed_list[0] if parsed_list else None, parsed_list,
        None, gift_no_ship=False, gift_no_ship_tids=None,
    )
    print(f"\n调用返回: {result}")

    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])

    if not all_items:
        print("⚠️ 未提交修改")
        return False

    return verify_payload(all_items, EXPECTED_SQUARE_GIFT_SKU, EXPECTED_ROUND_GIFT_SKU,
                          expect_gift_modified=True, scenario_desc="场景3(新建)")


def verify_payload(all_items, expected_square_sku, expected_round_sku,
                   expect_gift_modified=True, scenario_desc=""):
    """验证提交的payload"""
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]

    def clean(s):
        return str(s or '').replace('<font color="red">', '').replace('</font>', '')

    print(f"\n--- 提交结果 ({scenario_desc}) ---")
    print(f"总商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})")
    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        sku = clean(it.get('shopMappingSku', ''))
        oid = str(it.get('oid', ''))
        is_g = '赠品' if ('赠品' in sku or '30x50' in sku or '随机发' in sku) else '商品'
        print(f"  [{i}] {flag} {is_g} oid=...{oid[-6:]} sku={sku[:60]} num={it.get('num')}")

    errors = []

    # 检查赠品行
    gift_items = []
    for it in active_items:
        sku = clean(it.get('shopMappingSku', ''))
        if (sku == expected_square_sku or sku == expected_round_sku
                or ('30x50' in sku and '随机发' in sku)
                or ('赠品沥水垫小圆或小方' in sku)):
            gift_items.append(sku)

    # 也检查 filmGiftCode
    for it in active_items:
        if it.get('filmGiftCode') and str(it.get('filmGiftCode', '')).strip():
            sku = clean(it.get('shopMappingSku', ''))
            if sku not in gift_items:
                gift_items.append(sku)

    print(f"\n识别到赠品行: {len(gift_items)} 条")
    for g in gift_items:
        print(f"  - {g}")

    if len(gift_items) == 0:
        errors.append("❌ 未识别到赠品行！")
    elif expected_square_sku in gift_items:
        print(f"✅ 赠品行编码为期望的方垫编码")
    elif expected_round_sku in gift_items and expect_gift_modified:
        errors.append(f"❌ 赠品行仍是圆垫编码，未被修改！")
        errors.append(f"   当前: {expected_round_sku}")
        errors.append(f"   期望: {expected_square_sku}")
    elif len(gift_items) == 1:
        errors.append(f"赠品行编码不符合预期: {gift_items[0]}")
        errors.append(f"   期望: {expected_square_sku}")

    # 检查是否有重复赠品行
    if len(gift_items) > 1:
        errors.append(f"❌ 存在多个赠品行！期望1条，实际{len(gift_items)}条")

    # 检查普通商品行
    normal_count = len(active_items) - len(gift_items)
    if normal_count >= 1:
        print(f"✅ 普通商品行: {normal_count} 条")
    else:
        errors.append(f"❌ 普通商品行不足！")

    # 检查作废行是否包含错误的赠品删除
    round_void = [clean(it.get('shopMappingSku', '')) for it in void_items
                  if '赠品沥水垫小圆或小方' in clean(it.get('shopMappingSku', ''))]
    if round_void and expect_gift_modified:
        print(f"  ℹ️  原圆垫赠品行被标记为作废(将被新行替代): {len(round_void)}条")
    elif round_void and not expect_gift_modified:
        errors.append(f"❌ 圆垫赠品行被作废！场景2应保留原行")

    print("\n" + "-" * 40)
    if errors:
        for e in errors:
            print(f"  ❌ {e}")
        return False
    else:
        print(f"  🎉 {scenario_desc} 验证通过！")
        return True


def run_all():
    print("=" * 70)
    print("'赠品换赠品沥水垫30x50' 场景 - 完整功能验证")
    print("=" * 70)
    print(f"规则：")
    print(f"  1. 已有赠品行 → 比较编码")
    print(f"     - 不匹配 → 修改")
    print(f"     - 已匹配 → 跳过")
    print(f"  2. 无赠品行 → 创建")
    print(f"")
    print(f"期望赠品编码（方垫）: {EXPECTED_SQUARE_GIFT_SKU}")
    print(f"期望赠品编码（圆垫）: {EXPECTED_ROUND_GIFT_SKU}")

    results = []
    results.append(("备注解析", parse_gift_from_remark()))
    results.append(("场景1:有赠品行且编码不匹配→修改", test_scenario1_gift_exists_code_mismatch()))
    results.append(("场景2:有赠品行且编码已匹配→跳过", test_scenario2_gift_exists_code_match()))
    results.append(("场景3:无赠品行→创建新赠品行", test_scenario3_no_gift_item()))

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
    success = run_all()
    sys.exit(0 if success else 1)
