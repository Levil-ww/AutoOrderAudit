import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')
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
        'type': type_val,
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
    for i, item in enumerate(items):
        clean_sku = item.shop_mapping_sku.replace('<font color="red">', '').replace('</font>', '')
        is_gift = adapter._is_gift_item(item)
        print(f"  [{i}] id={item.id}, type={item.raw.get('type')}, price={item.price}, "
              f"is_gift={is_gift}, sku={clean_sku[:45]}")

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
        return 0
    
    active_items = [it for it in all_items if not it.get('cancelStatus') and not it.get('discardStatus')]
    void_items = [it for it in all_items if it.get('cancelStatus') or it.get('discardStatus')]
    new_items = [it for it in active_items if it.get('type') == 1 and not it.get('id')]

    print(f'\n结果: {result}')
    print(f'提交商品行数: {len(all_items)} (有效{len(active_items)}, 作废{len(void_items)})')
    print(f'新创建手工单行: {len(new_items)} 个')
    
    return len(new_items)


# 场景：模拟用户遇到的问题
# 原始订单只有1个商品行，解析出2个尺寸
# 第一次运行创建1个手工单行（price=0）
# 第二次运行时，手工单行被识别为赠品，导致又创建新的手工单行

remark = '定制吸水皮革白色大理石3;60x60cm-1张，白色大理石3;40x60cm-1张，共计2张'

# ==== 第一次运行 ====
print("\n" + "="*70)
print("模拟：第一次运行")
print("="*70)

items_run1 = [
    OrderItem(
        id='1', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s1',
        title='轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
        num=1,
        price=100,  # 原始商品行 price=100
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, 
                     '轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布', 100)
    ),
]
new_count1 = run_case('第一次运行', remark, items_run1, '只有1个原始商品行')

# ==== 模拟第一次运行后的订单状态 ====
# 假设第一次运行创建了1个手工单行（price=0）
print("\n" + "="*70)
print("模拟：第一次运行后的订单状态")
print("="*70)

items_run2 = [
    # 原始商品行（被修改了SKU，但price保持100）
    OrderItem(
        id='1', order_id='6928300064387268308', oid='6928300064387268308', sys_oid='s1',
        title='轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布',
        shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x60CM', 
        num=1,
        price=100,
        raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x60CM', 1, 0,
                     '轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布', 100)
    ),
    # 第一次运行创建的手工单行（注意：price=0，因为 _build_default_item 没有设置price）
    OrderItem(
        id='2', order_id='6928300064387268308', oid='new_oid_1', sys_oid='s2',
        title='轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布',
        shop_mapping_sku='<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 
        num=1,
        price=0,  # 关键：新创建的手工单行 price=0
        raw=make_raw('2', '<font color="red">吸水皮革-定制-定制尺寸-白色大理石3;40x60CM</font>', 1, 1,
                     '轻奢大理石纹防水垫速干厨房台面吸水垫浴室洗手台防滑垫桌布', 0)
    ),
]

# 检查手工单行是否被识别为赠品
print(f"\n检查第一次运行后创建的手工单行：")
print(f"  price = {items_run2[1].price}")
print(f"  title 含'垫' = {'垫' in items_run2[1].title}")
print(f"  is_gift = {adapter._is_gift_item(items_run2[1])}")

# ==== 第二次运行 ====
new_count2 = run_case('第二次运行', remark, items_run2, 
                      '手工单行price=0，被识别为赠品，导致重复创建')

print(f"\n{'='*70}")
print("结论")
print(f"{'='*70}")
print(f"第一次运行新创建: {new_count1} 个手工单行")
print(f"第二次运行新创建: {new_count2} 个手工单行")
if new_count2 > 0:
    print(f"❌ 问题确认：第二次运行仍然创建了 {new_count2} 个新手工单行，存在重复生成问题")
    print(f"根本原因：新创建的手工单行 price=0，标题含'垫'，被误识别为赠品行")
    print(f"         导致 valid_items 数量不足，每次运行都创建新行")
else:
    print(f"✅ 没有重复创建")
