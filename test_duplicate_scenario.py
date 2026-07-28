import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks

adapter = FangguoAdapter()

def make_raw(item_id, sku, num, type_val=0, title='测试商品'):
    return {
        'id': item_id,
        'orderId': '6928300064387268308',
        'sysOid': f's{item_id}',
        'oid': '6928300064387268308',
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

def run_case(name, remark, items, expected_active_count, expected_active_skus, expected_void_ids=None, should_skip=False):
    print(f"\n{'='*60}")
    print(f"测试用例: {name}")
    print(f"{'='*60}")
    parsed_list = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )
    print('解析结果:')
    for p in parsed_list:
        print(f"  SKU: {p.shop_mapping_sku}")
        print(f"  base: {p.base_shop_mapping_sku}")
        print(f"  num: {p.num}")

    order = Order(
        trade_id='6928300064387268308',
        tid='6928300064387268308',
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
    result = adapter.update_merchant_code(order, parsed_list[0] if parsed_list else None, parsed_list, None, gift_no_ship=False)
    
    if should_skip:
        if result is True and 'payload' not in captured:
            print(f'✅ 正确跳过，未提交修改')
            return
        else:
            print(f'❌ 应该跳过但实际提交了修改')
            return
    
    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    active_skus = [it.get('shopMappingSku') for it in active_items]
    void_ids = [it.get('id') for it in void_items]

    print(f'\n结果: {result}')
    print(f'提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        clean_sku = it.get('shopMappingSku', '').replace('<font color="red">', '').replace('</font>', '')
        print(f"  item[{i}]: {flag} type={it.get('type')}, id={it.get('id')}, sku={clean_sku[:60]}, num={it.get('num')}")

    ok = True
    if len(active_items) == expected_active_count:
        print(f'✅ 有效商品行数符合预期 ({expected_active_count})')
    else:
        print(f'❌ 有效商品行数不符合预期，期望{expected_active_count}，实际{len(active_items)}')
        ok = False

    for expected_sku in expected_active_skus:
        found = any(expected_sku == sku.replace('<font color="red">', '').replace('</font>', '') for sku in active_skus)
        if found:
            print(f'✅ 找到期望有效SKU: {expected_sku}')
        else:
            print(f'❌ 缺少期望有效SKU: {expected_sku}')
            ok = False

    if expected_void_ids is not None:
        for vid in expected_void_ids:
            if vid in void_ids:
                print(f'✅ 重复行已标记作废: id={vid}')
            else:
                print(f'❌ 重复行未作废: id={vid}')
                ok = False

    if ok:
        print('🎉 用例通过')
    else:
        print('❌ 用例失败')


# 模拟用户截图场景：
# 第1-2行：原始商品行（原始SKU）
# 第3-4行：程序第一次运行创建的手工单行（正确编码）
# 第5-6行：程序第二次运行又创建的手工单行（重复）
# 我们测试的是：当订单已有原始行 + 第一次创建的手工单时，程序应该识别到手工单行已经存在，
# 不应该再创建新的手工单，同时正确处理原始行

remark = '定制吸水皮革白色大理石3;60x60cm-1张，白色大理石3;40x60cm-1张，共计2张'

# 场景：原始订单有2个商品行 + 程序已创建的2个手工单行
items = [
    # 原始商品行1
    OrderItem(
        id='1', 
        order_id='6928300064387268308', 
        oid='6928300064387268308', 
        sys_oid='s1', 
        title='轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫')
    ),
    # 原始商品行2
    OrderItem(
        id='2', 
        order_id='6928300064387268308', 
        oid='6928300064387268308', 
        sys_oid='s2', 
        title='轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        raw=make_raw('2', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫')
    ),
    # 程序第一次运行创建的手工单行1（正确编码）
    OrderItem(
        id='3', 
        order_id='6928300064387268308', 
        oid='6928300064387268308', 
        sys_oid='s3', 
        title='轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 
        num=1, 
        raw=make_raw('3', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 1, 1, '轻奢大理石纹防水垫')
    ),
    # 程序第一次运行创建的手工单行2（正确编码）
    OrderItem(
        id='4', 
        order_id='6928300064387268308', 
        oid='6928300064387268308', 
        sys_oid='s4', 
        title='轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 
        num=1, 
        raw=make_raw('4', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 1, 1, '轻奢大理石纹防水垫')
    ),
]

run_case(
    '第二次运行-已有手工单行-不应重复创建', 
    remark, 
    items, 
    expected_active_count=4,  # 2个原始行 + 2个手工单行（保留）
    expected_active_skus=[
        '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm',  # 原始行1
        '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm',  # 原始行2
        '吸水皮革-定制-定制尺寸-白色大理石3;60x60CM',   # 手工单行1（保留）
        '吸水皮革-定制-定制尺寸-白色大理石3;40x60CM',   # 手工单行2（保留）
    ],
    expected_void_ids=[],  # 不需要作废任何行
)

print("\n" + "="*60)
print("下面是关键问题：程序是否识别到手工单行已经存在？")
print("如果程序识别到了，就不会创建新的手工单行")
print("如果程序没识别到，就会再创建2个新的手工单行（总共6行）")
print("="*60)
