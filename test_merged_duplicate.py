import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks

adapter = FangguoAdapter()

def make_raw(item_id, sku, num, type_val=0, title='测试商品', tid='', oid='', original_tid=''):
    return {
        'id': item_id,
        'orderId': '6928300064387268308',
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

def run_case(name, remark, items, expected_active_count, expected_void_ids=None, is_merged=False):
    print(f"\n{'='*60}")
    print(f"测试用例: {name}")
    print(f"{'='*60}")
    
    parsed_list = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )
    print(f'解析结果数量: {len(parsed_list)}')
    for p in parsed_list:
        print(f"  SKU: {p.shop_mapping_sku}")
        print(f"  base: {p.base_shop_mapping_sku}")
        print(f"  num: {p.num}")
        print(f"  original_tid: {p.original_tid}")

    order = Order(
        trade_id='6928300064387268308',
        tid='6928300064387268308&sub2',
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
    
    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])
    
    if not all_items:
        print(f'\n结果: {result} - 跳过修改（已正确）')
        return
    
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    active_skus = [it.get('shopMappingSku') for it in active_items]
    void_ids = [it.get('id') for it in void_items]

    print(f'\n结果: {result}')
    print(f'提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        clean_sku = it.get('shopMappingSku', '').replace('<font color="red">', '').replace('</font>', '')
        print(f"  item[{i}]: {flag} type={it.get('type')}, id={it.get('id')}, oid={str(it.get('oid',''))[:20]}, sku={clean_sku[:50]}, num={it.get('num')}")

    ok = True
    if len(active_items) == expected_active_count:
        print(f'✅ 有效商品行数符合预期 ({expected_active_count})')
    else:
        print(f'❌ 有效商品行数不符合预期，期望{expected_active_count}，实际{len(active_items)}')
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


# 模拟合并订单场景：
# 订单号包含&，有两个子订单
# 子订单1：原始商品行1 + 手工单行1（已创建）
# 子订单2：原始商品行2 + 手工单行2（已创建）
# 第二次运行时，应该检测到手工单行已存在，不重复创建

remark = '定制吸水皮革白色大理石3;60x60cm-1张，白色大理石3;40x60cm-1张，共计2张'

tid1 = 'sub1_tid'
tid2 = 'sub2_tid'

# 合并订单：两个子订单，每个子订单有1个原始商品行 + 1个手工单行
items = [
    # 子订单1 - 原始商品行
    OrderItem(
        id='1', 
        order_id='6928300064387268308', 
        oid=f'o1_{tid1}',
        sys_oid='s1', 
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        original_tid=tid1,
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫', tid=tid1, oid=f'o1_{tid1}')
    ),
    # 子订单1 - 手工单行（程序第一次运行创建的）
    OrderItem(
        id='2', 
        order_id='6928300064387268308', 
        oid=f'o2_{tid1}_new',
        sys_oid='s2', 
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 
        num=1, 
        original_tid=tid1,
        raw=make_raw('2', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 1, 1, '轻奢大理石纹防水垫', tid=tid1, oid=f'o2_{tid1}_new')
    ),
    # 子订单2 - 原始商品行
    OrderItem(
        id='3', 
        order_id='6928300064387268308', 
        oid=f'o3_{tid2}',
        sys_oid='s3', 
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        original_tid=tid2,
        raw=make_raw('3', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫', tid=tid2, oid=f'o3_{tid2}')
    ),
    # 子订单2 - 手工单行（程序第一次运行创建的）
    OrderItem(
        id='4', 
        order_id='6928300064387268308', 
        oid=f'o4_{tid2}_new',
        sys_oid='s4', 
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 
        num=1, 
        original_tid=tid2,
        raw=make_raw('4', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 1, 1, '轻奢大理石纹防水垫', tid=tid2, oid=f'o4_{tid2}_new')
    ),
]

run_case(
    '合并订单-第二次运行-已有手工单行', 
    remark, 
    items, 
    expected_active_count=4,  # 2原始 + 2手工单
    expected_void_ids=[],  # 不需要作废
    is_merged=True,
)
