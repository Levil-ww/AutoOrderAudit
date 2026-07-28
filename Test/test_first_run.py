import sys
sys.path.insert(0, '/')
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

def run_case(name, remark, items):
    print(f"\n{'='*70}")
    print(f"测试用例: {name}")
    print(f"{'='*70}")
    
    parsed_list = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )
    print(f'解析结果数量: {len(parsed_list)}')
    for i, p in enumerate(parsed_list):
        print(f"  [{i}] SKU: {p.shop_mapping_sku}")
        print(f"       base: {p.base_shop_mapping_sku}")
        print(f"       num: {p.num}")

    print(f'\n初始商品行数: {len(items)}')
    for i, item in enumerate(items):
        clean_sku = item.shop_mapping_sku.replace('<font color="red">', '').replace('</font>', '')
        print(f"  [{i}] id={item.id}, type={item.raw.get('type')}, sku={clean_sku[:50]}, num={item.num}")

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
    
    payload = captured.get('payload', {})
    all_items = payload.get('orderItems', [])
    
    if not all_items:
        print(f'\n结果: {result} - 跳过修改（已正确）')
        return
    
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]

    print(f'\n结果: {result}')
    print(f'提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    print(f'\n提交的商品行详情:')
    for i, it in enumerate(all_items):
        flag = '🗑️作废' if (it.get('cancelStatus') or it.get('discardStatus')) else '✅有效'
        clean_sku = it.get('shopMappingSku', '').replace('<font color="red">', '').replace('</font>', '')
        is_new = '🆕新行' if (it.get('type') == 1 and not it.get('id')) else ''
        print(f"  [{i}] {flag} {is_new} type={it.get('type')}, id={it.get('id')}, sku={clean_sku[:55]}, num={it.get('num')}")

    print(f'\n分析:')
    new_items = [it for it in active_items if it.get('type') == 1 and not it.get('id')]
    print(f'  新创建的手工单行: {len(new_items)} 个')
    if len(new_items) > len(parsed_list):
        print(f'  ❌ 异常：新创建行数({len(new_items)}) > 解析结果数({len(parsed_list)})')
    elif len(new_items) == 0:
        print(f'  ✅ 没有创建新行（使用现有行）')
    else:
        print(f'  ℹ️  创建了 {len(new_items)} 个新手工单')


# 场景1：第一次运行 - 只有原始商品行（2行），解析结果2个
# 预期：修改2个原始商品行，不创建新行
remark = '定制吸水皮革白色大理石3;60x60cm-1张，白色大理石3;40x60cm-1张，共计2张'
items1 = [
    OrderItem(
        id='1', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s1',
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫')
    ),
    OrderItem(
        id='2', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s2',
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        raw=make_raw('2', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫')
    ),
]
run_case('第一次运行-2个原始行-2个解析结果', remark, items1)


# 场景2：第二次运行 - 原始商品行（2行）+ 手工单行（2行）
# 预期：检测到已经正确，跳过修改
items2 = [
    OrderItem(
        id='1', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s1',
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫')
    ),
    OrderItem(
        id='2', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s2',
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        raw=make_raw('2', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫')
    ),
    OrderItem(
        id='3', order_id='6928300064387268308', oid='new_oid_1', sys_oid='s3',
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 
        num=1, 
        raw=make_raw('3', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 1, 1, '轻奢大理石纹防水垫')
    ),
    OrderItem(
        id='4', order_id='6928300064387268308', oid='new_oid_2', sys_oid='s4',
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 
        num=1, 
        raw=make_raw('4', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 1, 1, '轻奢大理石纹防水垫')
    ),
]
run_case('第二次运行-2原始+2手工单-应该跳过', remark, items2)


# 场景3：只有1个原始商品行，但解析结果有2个
# 预期：修改1个原始行，创建1个新手工单
items3 = [
    OrderItem(
        id='1', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s1',
        title='轻奢大理石纹防水垫',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1, 
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫')
    ),
]
run_case('第一次运行-1个原始行-2个解析结果', remark, items3)
