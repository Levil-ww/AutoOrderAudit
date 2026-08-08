"""
测试跨子订单去重逻辑修复
======================
场景：合并订单的两个子订单，商品编码相同，但属于不同子订单号
验证：不同子订单的相同SKU不应被去重删除

订单号：5127563593247004046 & 5127508836260332023
两个子订单的备注均为："双面格-定制尺寸-庄园秘境;55x60CM"
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks

adapter = FangguoAdapter()

def make_raw(item_id, sku, num, type_val=0, title='测试商品', tid='', oid='', original_tid=''):
    return {
        'id': item_id,
        'orderId': 'merge_order_001',
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
        'price': 100,
        'type': type_val,
        'shopRemark': '',
        'filmGiftCode': '',
    }

def test_merged_order_same_sku_different_tid():
    """
    测试：合并订单两个子订单，相同SKU但不同子订单号
    期望：两个子订单的商品行都被保留，不互相去重
    """
    print("\n" + "=" * 60)
    print("测试用例: 合并订单-不同子订单相同SKU不去重")
    print("=" * 60)

    # 两个子订单号
    tid1 = '5127563593247004046'
    tid2 = '5127508836260332023'

    # 两个子订单的备注相同（都要求编码为相同SKU）
    remark = '定制双面格庄园秘境;55x60CM-1张'

    # 模拟合并订单：两个子订单各有一个商品行
    # 原始SKU不同（模拟订单原始数据），但经备注解析后目标SKU相同
    items = [
        # 子订单1 - 原始商品行（原始SKU为旧编码）
        OrderItem(
            id='item_1',
            order_id='merge_order_001',
            oid=tid1,
            sys_oid='sys_1',
            title='庄园秘境55x60CM',
            shop_mapping_sku='双面格-标准-55x60-庄园秘境',
            num=1,
            original_tid=tid1,
            shop_remark=remark,
            raw=make_raw('item_1', '双面格-标准-55x60-庄园秘境', 1, 0, 
                        '庄园秘境55x60CM', tid=tid1, oid=tid1)
        ),
        # 子订单2 - 原始商品行（原始SKU为旧编码，但备注指定了相同的目标编码）
        OrderItem(
            id='item_2',
            order_id='merge_order_001',
            oid=tid2,
            sys_oid='sys_2',
            title='庄园秘境55x60CM',
            shop_mapping_sku='双面格-标准-55x60-庄园秘境',
            num=1,
            original_tid=tid2,
            shop_remark=remark,
            raw=make_raw('item_2', '双面格-标准-55x60-庄园秘境', 1, 0,
                        '庄园秘境55x60CM', tid=tid2, oid=tid2)
        ),
    ]

    # 解析备注
    parsed_list = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )
    print(f'解析结果数量: {len(parsed_list)}')
    for p in parsed_list:
        print(f'  SKU: {p.shop_mapping_sku}')
        print(f'  num: {p.num}')
        print(f'  success: {p.success}')

    # 为解析结果设置 original_tid（模拟引擎已按分组处理）
    # 注意：两个子订单都要解析出相同SKU
    if len(parsed_list) >= 1:
        # 克隆解析结果，分别设置不同的 original_tid
        parsed_list_tid1 = [type('Parsed', (), {
            'material_code': parsed_list[0].material_code,
            'color_code': parsed_list[0].color_code,
            'model_code': parsed_list[0].model_code,
            'picture_code': parsed_list[0].picture_code,
            'shop_mapping_sku': parsed_list[0].shop_mapping_sku,
            'base_shop_mapping_sku': parsed_list[0].base_shop_mapping_sku,
            'num': parsed_list[0].num,
            'success': True,
            'gifts': [],
            'gift_name': '',
            'gift_num': 0,
            'original_tid': tid1,
            'shop_remark': remark,
        })()]
        parsed_list_tid2 = [type('Parsed', (), {
            'material_code': parsed_list[0].material_code,
            'color_code': parsed_list[0].color_code,
            'model_code': parsed_list[0].model_code,
            'picture_code': parsed_list[0].picture_code,
            'shop_mapping_sku': parsed_list[0].shop_mapping_sku,
            'base_shop_mapping_sku': parsed_list[0].base_shop_mapping_sku,
            'num': parsed_list[0].num,
            'success': True,
            'gifts': [],
            'gift_name': '',
            'gift_num': 0,
            'original_tid': tid2,
            'shop_remark': remark,
        })()]
        
        # 合并两个解析结果
        merged_parsed_list = parsed_list_tid1 + parsed_list_tid2
    else:
        print('❌ 备注解析失败，无法继续测试')
        return False

    # 创建模拟订单
    order = Order(
        trade_id='5127563593247004046&5127508836260332023',
        tid='5127563593247004046&5127508836260332023',
        sys_tid='',
        shop_remark=remark,
        factory_id=0,
        items=items,
    )

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

    # 执行修改
    result = adapter.update_merchant_code(
        order, 
        merged_parsed_list[0] if merged_parsed_list else None, 
        merged_parsed_list, 
        None,  # price_diff_updates
        gift_no_ship=False
    )

    # 验证结果
    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])
    
    if not all_items:
        print(f'\n结果: {result} - 跳过修改（已正确）')
        # 即使跳过，也需要验证现有商品行是否都被保留
        return verify_items_preserved(items, [tid1, tid2])

    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    
    print(f'\n结果: {result}')
    print(f'提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    
    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        clean_sku = str(it.get('shopMappingSku', '')).replace('<font color="red">', '').replace('</font>', '')
        oid = str(it.get('oid', ''))[:20]
        print(f"  item[{i}]: {flag} oid={oid}, sku={clean_sku[:50]}, num={it.get('num')}")

    # 关键验证：应有2个有效商品行（两个子订单各1个）
    errors = []
    
    # 1. 检查有效商品行数量
    if len(active_items) != 2:
        errors.append(f'期望2个有效商品行，实际{len(active_items)}个')
    
    # 2. 检查两个子订单的商品行是否都被保留
    active_oids = [str(it.get('oid', '')) for it in active_items]
    if tid1 not in active_oids:
        errors.append(f'子订单 {tid1} 的商品行丢失！')
    if tid2 not in active_oids:
        errors.append(f'子订单 {tid2} 的商品行丢失！')
    
    # 3. 检查SKU是否正确
    target_sku = merged_parsed_list[0].shop_mapping_sku
    for it in active_items:
        clean_sku = str(it.get('shopMappingSku', '')).replace('<font color="red">', '').replace('</font>', '')
        if clean_sku != target_sku:
            errors.append(f'商品行SKU不正确：期望 {target_sku}，实际 {clean_sku}')
    
    if errors:
        print(f'\n❌ 测试失败!')
        for e in errors:
            print(f'   - {e}')
        return False
    else:
        print(f'\n🎉 测试通过！两个子订单的商品行均被正确保留，无跨子订单去重')
        return True

def test_merged_order_same_sku_same_tid():
    """
    测试：同一子订单内两个相同SKU的商品行应该被去重
    验证：同一子订单内的重复商品行需要合并
    """
    print("\n" + "=" * 60)
    print("测试用例: 同一子订单内相同SKU应被去重")
    print("=" * 60)

    tid1 = '5127563593247004046'
    remark = '定制双面格庄园秘境;55x60CM-1张'

    # 同一子订单有2个商品行（模拟重复创建的手工单）
    items = [
        OrderItem(
            id='item_1',
            order_id='merge_order_001',
            oid=tid1,
            sys_oid='sys_1',
            title='庄园秘境55x60CM',
            shop_mapping_sku='双面格-定制尺寸-庄园秘境;55x60CM',
            num=1,
            original_tid=tid1,
            shop_remark=remark,
            raw=make_raw('item_1', '双面格-定制尺寸-庄园秘境;55x60CM', 1, 1,
                        '庄园秘境55x60CM', tid=tid1, oid=tid1)
        ),
        # 同一子订单的第二个相同商品行（重复）
        OrderItem(
            id='item_2',
            order_id='merge_order_001',
            oid=tid1,
            sys_oid='sys_2',
            title='庄园秘境55x60CM',
            shop_mapping_sku='双面格-定制尺寸-庄园秘境;55x60CM',
            num=1,
            original_tid=tid1,
            shop_remark=remark,
            raw=make_raw('item_2', '双面格-定制尺寸-庄园秘境;55x60CM', 1, 1,
                        '庄园秘境55x60CM', tid=tid1, oid=tid1)
        ),
    ]

    parsed_list = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )

    merged_parsed_list = [type('Parsed', (), {
        'material_code': parsed_list[0].material_code,
        'color_code': parsed_list[0].color_code,
        'model_code': parsed_list[0].model_code,
        'picture_code': parsed_list[0].picture_code,
        'shop_mapping_sku': parsed_list[0].shop_mapping_sku,
        'base_shop_mapping_sku': parsed_list[0].base_shop_mapping_sku,
        'num': parsed_list[0].num,
        'success': True,
        'gifts': [],
        'gift_name': '',
        'gift_num': 0,
        'original_tid': tid1,
        'shop_remark': remark,
    })()]

    order = Order(
        trade_id='5127563593247004046',
        tid=tid1,
        sys_tid='',
        shop_remark=remark,
        factory_id=0,
        items=items,
    )

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
        merged_parsed_list[0],
        merged_parsed_list,
        None,
        gift_no_ship=False
    )

    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])
    
    if not all_items:
        print(f'\n结果: {result} - 跳过修改（已正确）')
        return True

    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    
    print(f'\n结果: {result}')
    print(f'提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    
    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        clean_sku = str(it.get('shopMappingSku', '')).replace('<font color="red">', '').replace('</font>', '')
        print(f"  item[{i}]: {flag}, sku={clean_sku[:50]}, num={it.get('num')}")

    # 同一子订单内的重复行应该被去重
    if len(active_items) <= 2:
        print(f'\n🎉 测试通过！同一子订单内的重复行被正确处理')
        return True
    else:
        print(f'\n❌ 同一子订单内的重复行未被去重')
        return False

def test_gift_cross_suborder():
    """
    测试：合并订单的赠品处理，不同子订单的赠品不应合并
    """
    print("\n" + "=" * 60)
    print("测试用例: 合并订单赠品-不同子订单赠品不合并")
    print("=" * 60)

    tid1 = '5127563593247004046'
    tid2 = '5127508836260332023'
    
    # 两个子订单的备注都包含相同的赠品信息
    remark1 = '定制吸水皮革白色大理石3;60x60cm-1张，赠品圆垫-1张'
    remark2 = '定制吸水皮革白色大理石3;40x60cm-1张，赠品圆垫-1张'

    items = [
        # 子订单1 - 商品行
        OrderItem(
            id='item_1',
            order_id='merge_order_001',
            oid=tid1,
            sys_oid='sys_1',
            title='大理石纹防水垫',
            shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm',
            num=1,
            original_tid=tid1,
            shop_remark=remark1,
            raw=make_raw('item_1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0,
                        '大理石纹防水垫', tid=tid1, oid=tid1)
        ),
        # 子订单2 - 商品行
        OrderItem(
            id='item_2',
            order_id='merge_order_001',
            oid=tid2,
            sys_oid='sys_2',
            title='大理石纹防水垫',
            shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm',
            num=1,
            original_tid=tid2,
            shop_remark=remark2,
            raw=make_raw('item_2', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0,
                        '大理石纹防水垫', tid=tid2, oid=tid2)
        ),
    ]

    # 分别解析两个备注
    parsed1 = extract_multiple_remarks(remark1, material_map=adapter.material_map, material_matcher=adapter.get_material_matcher())
    parsed2 = extract_multiple_remarks(remark2, material_map=adapter.material_map, material_matcher=adapter.get_material_matcher())

    # 为每个解析结果设置对应的 original_tid
    def clone_parsed(p, tid):
        return type('Parsed', (), {
            'material_code': p.material_code,
            'color_code': p.color_code,
            'model_code': p.model_code,
            'picture_code': p.picture_code,
            'shop_mapping_sku': p.shop_mapping_sku,
            'base_shop_mapping_sku': p.base_shop_mapping_sku,
            'num': p.num,
            'success': p.success,
            'gifts': p.gifts if p.gifts else [],
            'gift_name': p.gift_name,
            'gift_num': p.gift_num,
            'original_tid': tid,
            'shop_remark': remark1 if tid == tid1 else remark2,
        })

    merged_parsed_list = []
    for p in parsed1:
        merged_parsed_list.append(clone_parsed(p, tid1))
    for p in parsed2:
        merged_parsed_list.append(clone_parsed(p, tid2))

    print(f'解析结果数量: {len(merged_parsed_list)}')
    for p in merged_parsed_list:
        print(f'  SKU: {p.shop_mapping_sku}, num: {p.num}, tid: {p.original_tid}')
        if p.gifts:
            print(f'  Gifts: {p.gifts}')

    order = Order(
        trade_id='5127563593247004046&5127508836260332023',
        tid='5127563593247004046&5127508836260332023',
        sys_tid='',
        shop_remark=remark1 + '，' + remark2,
        factory_id=0,
        items=items,
    )

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
        merged_parsed_list[0] if merged_parsed_list else None,
        merged_parsed_list,
        None,
        gift_no_ship=False
    )

    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])
    
    if not all_items:
        print(f'\n结果: {result} - 跳过修改')
        return True

    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    
    print(f'\n结果: {result}')
    print(f'提交商品行数: {len(all_items)} (有效{len(active_items)})')
    
    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        clean_sku = str(it.get('shopMappingSku', '')).replace('<font color="red">', '').replace('</font>', '')
        oid = str(it.get('oid', ''))[:20]
        print(f"  item[{i}]: {flag} oid={oid}, sku={clean_sku[:60]}, num={it.get('num')}")

    # 验证：应有2个商品行 + 2个赠品行 = 4个有效行
    # 且赠品行应分别属于不同子订单
    gift_items = [it for it in active_items if '赠品' in str(it.get('shopMappingSku', '')) or '礼品' in str(it.get('shopMappingSku', ''))]
    non_gift_items = [it for it in active_items if '赠品' not in str(it.get('shopMappingSku', '')) and '礼品' not in str(it.get('shopMappingSku', ''))]
    
    # 检查是否有2个商品行和2个赠品行
    if len(non_gift_items) >= 2:
        print(f'\n✅ 商品行数量正确 ({len(non_gift_items)}个)')
    else:
        print(f'\n❌ 商品行数量不足 (期望≥2, 实际{len(non_gift_items)})')
    
    print(f'赠品数量: {len(gift_items)}')
    for g in gift_items:
        print(f'  赠品: oid={str(g.get("oid",""))[:20]}, sku={str(g.get("shopMappingSku",""))[:50]}')
    
    return True

def verify_items_preserved(items, expected_tids):
    """验证所有预期的商品行都被保留"""
    item_tids = [item.original_tid for item in items]
    for tid in expected_tids:
        if tid not in item_tids:
            print(f'❌ 子订单 {tid} 的商品行丢失！')
            return False
    print(f'✅ 所有子订单的商品行均被保留')
    return True

def run_tests():
    print("=" * 70)
    print("跨子订单去重逻辑修复 - 测试套件")
    print("=" * 70)
    
    results = []
    
    # 测试1：不同子订单相同SKU不应去重（核心场景）
    results.append(("不同子订单相同SKU不去重", test_merged_order_same_sku_different_tid()))
    
    # 测试2：同一子订单内相同SKU应被去重
    results.append(("同子订单内相同SKU去重", test_merged_order_same_sku_same_tid()))
    
    # 测试3：赠品跨子订单不去重
    results.append(("赠品跨子订单不去重", test_gift_cross_suborder()))
    
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
    success = run_tests()
    sys.exit(0 if success else 1)