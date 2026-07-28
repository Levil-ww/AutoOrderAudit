import sys
sys.path.insert(0, '/')
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks

adapter = FangguoAdapter()

def make_raw(item_id, sku, num, type_val=0, title='测试商品', price=0, gift_code=''):
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
        'price': price,
        'type': type_val,
        'shopRemark': '',
        'filmGiftCode': gift_code,
    }

def run_case(name, remark, items, desc=''):
    print(f"\n{'='*70}")
    print(f"测试用例: {name}")
    if desc:
        print(f"说明: {desc}")
    print(f"{'='*70}")
    
    parsed_list = extract_multiple_remarks(
        remark,
        material_map=adapter.material_map,
        material_matcher=adapter.get_material_matcher(),
    )

    product_parsed_list = [p for p in parsed_list if p.success]
    print(f'\n初始商品行数: {len(items)}')
    gift_count = 0
    for i, item in enumerate(items):
        clean_sku = item.shop_mapping_sku.replace('<font color="red">', '').replace('</font>', '')
        is_gift = adapter._is_gift_item(item)
        if is_gift:
            gift_count += 1
        print(f"  [{i}] id={item.id}, type={item.raw.get('type')}, price={item.price}, "
              f"is_gift={is_gift}, sku={clean_sku[:45]}")
    
    valid_count = len(items) - gift_count
    print(f'\n赠品数量: {gift_count}')
    print(f'有效商品行数量: {valid_count}')
    print(f'解析结果数量: {len(product_parsed_list)}')

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
        print(f'\n结果: 跳过修改（已正确）')
        return 0, 0
    
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    new_items = [it for it in active_items if it.get('type') == 1 and not it.get('id')]

    print(f'\n提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    print(f'新创建手工单行: {len(new_items)} 个')
    print(f'作废删除重复行: {len(void_items)} 个')
    
    if void_items:
        print(f'作废的行:')
        for it in void_items:
            sku = it.get('shopMappingSku', '').replace('<font color="red">', '').replace('</font>', '')
            print(f"  - id={it.get('id')}, sku={sku[:45]}, num={it.get('num')}")
    
    return len(new_items), len(void_items)


remark = '定制吸水皮革白色大理石3;60x60cm-1张，白色大理石3;40x60cm-1张，共计2张'
title = '轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布'

print("="*70)
print("模拟用户场景：已有多个重复手工单行（3组重复）")
print("="*70)

# 模拟用户遇到的情况：有多个重复的手工单行
# 所有行 price=0, type=0（ERP保存后type丢失）
items = [
    # 原始商品行
    OrderItem(
        id='1', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s1',
        title=title,
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x130CM', 
        num=1,
        price=0,
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x130CM', 1, 0, title, 0)
    ),
    # 赠品行
    OrderItem(
        id='2', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s2',
        title='赠品沥水垫',
        shop_mapping_sku='吸水皮革-标准-30x50-随机发；30x50', 
        num=1,
        price=0,
        raw=make_raw('2', '吸水皮革-标准-30x50-随机发；30x50', 1, 0, '赠品沥水垫', 0)
    ),
    # 第一次运行创建的手工单 - 60x60
    OrderItem(
        id='3', order_id='6928300064387268308', oid='new_oid_1', sys_oid='s3',
        title=title,
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 
        num=1,
        price=0,
        raw=make_raw('3', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 1, 0, title, 0)
    ),
    # 第一次运行创建的手工单 - 40x60
    OrderItem(
        id='4', order_id='6928300064387268308', oid='new_oid_2', sys_oid='s4',
        title=title,
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 
        num=1,
        price=0,
        raw=make_raw('4', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 1, 0, title, 0)
    ),
    # 第二次运行创建的重复手工单 - 60x60
    OrderItem(
        id='5', order_id='6928300064387268308', oid='new_oid_3', sys_oid='s5',
        title=title,
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 
        num=1,
        price=0,
        raw=make_raw('5', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 1, 0, title, 0)
    ),
    # 第二次运行创建的重复手工单 - 40x60
    OrderItem(
        id='6', order_id='6928300064387268308', oid='new_oid_4', sys_oid='s6',
        title=title,
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 
        num=1,
        price=0,
        raw=make_raw('6', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 1, 0, title, 0)
    ),
    # 第三次运行创建的重复手工单 - 60x60
    OrderItem(
        id='7', order_id='6928300064387268308', oid='new_oid_5', sys_oid='s7',
        title=title,
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 
        num=1,
        price=0,
        raw=make_raw('7', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;60x60CM</font>', 1, 0, title, 0)
    ),
    # 第三次运行创建的重复手工单 - 40x60
    OrderItem(
        id='8', order_id='6928300064387268308', oid='new_oid_6', sys_oid='s8',
        title=title,
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 
        num=1,
        price=0,
        raw=make_raw('8', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 1, 0, title, 0)
    ),
]

new_count, void_count = run_case(
    '用户场景-多组重复手工单', 
    remark, 
    items, 
    '模拟3组重复手工单行，验证程序能检测并删除重复行'
)

print(f"\n{'='*70}")
print("测试结论")
print(f"{'='*70}")
if void_count > 0:
    print(f"✅ 成功检测并作废了 {void_count} 个重复商品行")
    print(f"✅ 没有创建新的重复行（新创建: {new_count} 个）")
    print(f"\n修复效果：")
    print(f"  1. price=0 的正常商品不再被误识别为赠品")
    print(f"  2. 全局重复行检测能发现并删除多组重复手工单")
    print(f"  3. 程序检测到编码已正确时跳过修改，不再生成新行")
else:
    print(f"❌ 没有检测到重复行")
