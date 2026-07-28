import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks

adapter = FangguoAdapter()

def make_raw(item_id, sku, num, type_val=0):
    return {
        'id': item_id,
        'orderId': '3314708616421014679',
        'sysOid': f's{item_id}',
        'oid': '3314708616421014679',
        'title': '测试商品',
        'skuPropertiesName': '',
        'shopMappingSku': sku,
        'originalSkuId': '',
        'originalGoodsId': '',
        'merchandisePicPath': '',
        'num': num,
        'price': 100,
        'type': type_val,
        'shopRemark': '',
    }

def run_case(name, remark, items, expected_active_count, expected_active_skus, expected_void_ids=None):
    print(f"\n===== 测试用例: {name} =====")
    parsed_list = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )
    print('解析结果:')
    for p in parsed_list:
        print(f"  {p.shop_mapping_sku} (base={p.base_shop_mapping_sku}) num={p.num}")

    order = Order(
        trade_id='3314708616421014679',
        tid='3314708616421014679',
        sys_tid='',
        shop_remark=remark,
        factory_id=0,
        items=items,
    )

    captured = {}
    def mock_post(url, json=None, timeout=None):
        captured['payload'] = json
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
        return resp

    adapter._session.post = mock_post
    result = adapter.update_merchant_code(order, parsed_list[0] if parsed_list else None, parsed_list, None, gift_no_ship=False)
    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])
    # 通过 cancelStatus 区分有效行和作废行
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    active_skus = [it.get('shopMappingSku') for it in active_items]
    void_ids = [it.get('id') for it in void_items]

    print(f'结果: {result}, 提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        print(f"  item[{i}]: {flag} type={it.get('type')}, id={it.get('id')}, shopMappingSku={it.get('shopMappingSku')}, num={it.get('num')}, cancelStatus={it.get('cancelStatus')}")

    ok = True
    if len(active_items) == expected_active_count:
        print(f'✅ 有效商品行数符合预期 ({expected_active_count})')
    else:
        print(f'❌ 有效商品行数不符合预期，期望{expected_active_count}，实际{len(active_items)}')
        ok = False

    for expected_sku in expected_active_skus:
        found = any(expected_sku == sku for sku in active_skus)
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


# 用例1：已有正确商品行 + 2个重复行（SKU完全一致）
remark1 = '定制镜面皮革墨客;124x124cm-1张'
items1 = [
    OrderItem(id='1', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s1', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('1', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 0)),
    OrderItem(id='2', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s2', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('2', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 1)),
    OrderItem(id='3', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s3', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('3', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 1)),
]
run_case('已有正确行+2个完全重复行', remark1, items1, 1, ['镜面皮革-定制-定制尺寸-墨客;124x124CM'], ['2', '3'])


# 用例2：已有正确商品行（无CM） + 2个重复行（有CM）
remark2 = '定制镜面皮革墨客;124x124cm-1张'
items2 = [
    OrderItem(id='1', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s1', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124', num=1, raw=make_raw('1', '镜面皮革-定制-定制尺寸-墨客;124x124', 1, 0)),
    OrderItem(id='2', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s2', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('2', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 1)),
    OrderItem(id='3', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s3', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('3', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 1)),
]
run_case('已有正确行无CM+2个有CM重复行', remark2, items2, 1, ['镜面皮革-定制-定制尺寸-墨客;124x124'], ['2', '3'])


# 用例3：截图中的原始场景（带尾部备注 8月10日发货）
remark3 = '定制双面革中古花园;33x43-1张, 巴黎左岸;45.8x194.5cm-1张, 花橙;40.8x220cm-1张, 定制镜面皮革墨客;124x124cm-1张，共计4张，8月10日发货'
items3 = [
    OrderItem(id='1', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s1', title='测试商品', shop_mapping_sku='双面格-定制-定制尺寸-中古花园;45.8x194.5CM', num=1, raw=make_raw('1', '双面格-定制-定制尺寸-中古花园;45.8x194.5CM', 1, 0)),
    OrderItem(id='2', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s2', title='测试商品', shop_mapping_sku='双面格-定制-定制尺寸-中古花园;40.8x220CM', num=1, raw=make_raw('2', '双面格-定制-定制尺寸-中古花园;40.8x220CM', 1, 0)),
    OrderItem(id='3', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s3', title='测试商品', shop_mapping_sku='双面格-定制-定制尺寸-中古花园;33x43CM', num=1, raw=make_raw('3', '双面格-定制-定制尺寸-中古花园;33x43CM', 1, 0)),
    OrderItem(id='4', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s4', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM8月10日发货', num=1, raw=make_raw('4', '镜面皮革-定制-定制尺寸-墨客;124x124CM8月10日发货', 1, 1)),
    OrderItem(id='5', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s5', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('5', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 1)),
    OrderItem(id='6', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s6', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('6', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 1)),
]
run_case('截图场景-带尾部发货备注', remark3, items3, 4, [
    '双面格-定制-定制尺寸-中古花园;33x43CM',
    '双面格-定制-定制尺寸-巴黎左岸;45.8x194.5CM',
    '双面格-定制-定制尺寸-花橙;40.8x220CM',
    '镜面皮革-定制-定制尺寸-墨客;124x124CM8月10日发货',
], ['4', '6'])
