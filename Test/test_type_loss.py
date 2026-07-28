import sys
sys.path.insert(0, '/')
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks

adapter = FangguoAdapter()

def make_raw(item_id, sku, num, type_val=0, title='测试商品', price=100):
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
        'type': type_val,  # 关键：ERP 返回的 type 字段
        'shopRemark': '',
        'filmGiftCode': '',
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

    print(f'\n初始商品行数: {len(items)}')
    gift_count = 0
    for i, item in enumerate(items):
        clean_sku = item.shop_mapping_sku.replace('<font color="red">', '').replace('</font>', '')
        is_gift = adapter._is_gift_item(item)
        if is_gift:
            gift_count += 1
        print(f"  [{i}] id={item.id}, type={item.raw.get('type')}, price={item.price}, "
              f"is_gift={is_gift}, sku={clean_sku[:40]}")
    
    valid_count = len(items) - gift_count
    print(f'\n赠品数量: {gift_count}')
    print(f'有效商品行数量: {valid_count}')
    print(f'解析结果数量: {len([p for p in parsed_list if p.success])}')

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
        return 0
    
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    new_items = [it for it in active_items if it.get('type') == 1 and not it.get('id')]

    print(f'\n提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    print(f'新创建手工单行: {len(new_items)} 个')
    
    return len(new_items)


remark = '定制吸水皮革白色大理石3;60x60cm-1张，白色大理石3;40x60cm-1张，共计2张'
title = '轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布'

# ==== 场景：原始商品行price=0 + 手工单行保存后type丢失 ====
print("="*70)
print("模拟场景：原始商品行price=0 + ERP保存后手工单行type丢失")
print("="*70)

# 第一次运行后（模拟）：2个原始行都被识别为赠品，创建2个手工单行
# 第二次运行：ERP返回的手工单行type=0（而不是1），导致手工单行也被识别为赠品

items_run2 = [
    # 原始商品行1（price=0，type=0 → 被识别为赠品）
    OrderItem(
        id='1', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s1',
        title=title,
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1,
        price=0,  # price=0
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, title, 0)
    ),
    # 原始商品行2（price=0，type=0 → 被识别为赠品）
    OrderItem(
        id='2', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s2',
        title=title,
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1,
        price=0,
        raw=make_raw('2', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, title, 0)
    ),
    # 第一次运行创建的手工单行1（ERP保存后 type=0，price=0 → 被识别为赠品）
    OrderItem(
        id='3', order_id='6928300064387268308', oid='new_oid_1', sys_oid='s3',
        title=title,
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x60CM', 
        num=1,
        price=0,  # 新创建的手工单行 price=0
        raw=make_raw('3', '吸水皮革-定制-定制尺寸-白色大理石3;60x60CM', 1, 0, title, 0)  # 关键：type=0，不是1
    ),
    # 第一次运行创建的手工单行2（ERP保存后 type=0，price=0 → 被识别为赠品）
    OrderItem(
        id='4', order_id='6928300064387268308', oid='new_oid_2', sys_oid='s4',
        title=title,
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;40x60CM', 
        num=1,
        price=0,
        raw=make_raw('4', '吸水皮革-定制-定制尺寸-白色大理石3;40x60CM', 1, 0, title, 0)  # 关键：type=0
    ),
]

new_count = run_case(
    '第二次运行-手工单行type丢失', 
    remark, 
    items_run2, 
    '如果ERP保存后手工单行type变成0，且price=0，会被识别为赠品，导致每次都创建新行'
)

print(f"\n{'='*70}")
print("结论分析")
print(f"{'='*70}")
if new_count > 0:
    print(f"❌ 确认问题：本次运行新创建了 {new_count} 个手工单行")
    print(f"根本原因：")
    print(f"  1. 手工单行 price=0（创建时没有设置价格）")
    print(f"  2. ERP 保存后 type 字段丢失或变为0")
    print(f"  3. 导致手工单行被 _is_gift_item 误识别为赠品")
    print(f"  4. valid_indices 为空/不足，每次运行都创建新行")
    print(f"  5. 无限循环，重复行越来越多")
else:
    print(f"✅ 没有重复创建")
