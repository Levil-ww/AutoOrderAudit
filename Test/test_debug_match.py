import sys
sys.path.insert(0, '/')
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks
import re

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

remark = '定制吸水皮革白色大理石3;60x60cm-1张，白色大理石3;40x60cm-1张，共计2张'
parsed_list = extract_multiple_remarks(
    remark,
    material_map=adapter.material_map,
    material_matcher=adapter.get_material_matcher(),
)

print('解析结果:')
for i, p in enumerate(parsed_list):
    print(f"  [{i}] shop_mapping_sku = {p.shop_mapping_sku}")
    print(f"       base_shop_mapping_sku = {p.base_shop_mapping_sku}")
    print(f"       num = {p.num}")
    print(f"       original_tid = '{p.original_tid}'")

items = [
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

order = Order(
    trade_id='6928300064387268308',
    tid='6928300064387268308',
    sys_tid='',
    shop_remark=remark,
    factory_id=0,
    items=items,
)

print(f'\n商品行数量: {len(order.items)}')
for i, item in enumerate(order.items):
    print(f"  [{i}] id={item.id}, title={item.title[:20]}, sku={item.shop_mapping_sku[:50]}, num={item.num}")
    print(f"       is_gift={adapter._is_gift_item(item)}, is_price_diff={adapter._is_price_difference_item(item)}, is_void={item.is_void}")

# 手动计算 valid_indices
valid_indices = [idx for idx, item in enumerate(order.items) 
                 if not adapter._is_gift_item(item) 
                 and not adapter._is_price_difference_item(item) 
                 and not item.is_void]
print(f'\nvalid_indices: {valid_indices}')

# 模拟匹配逻辑
def _clean_sku(sku):
    return re.sub(r'<[^>]+>', '', sku or '')

def _normalize_sku_for_duplicate(sku):
    sku = _clean_sku(sku)
    if not sku:
        return sku
    sku = re.sub(r'(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)', r'\1x\2', sku, flags=re.IGNORECASE)
    sku = re.sub(r'(直径|圆|圆形|圆直径|尺寸)(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)', r'\1\2', sku, flags=re.IGNORECASE)
    return sku

print(f'\n匹配过程:')
used_item_indices = set()
for pi, p in enumerate(parsed_list):
    if not p or not p.success:
        continue
    print(f"\n  解析结果[{pi}]: sku={p.shop_mapping_sku}")
    
    matched_item_idx = None
    
    # 按 SKU 匹配
    best_idx = None
    best_score = -1
    parsed_norm = _normalize_sku_for_duplicate(p.shop_mapping_sku)
    parsed_base = p.base_shop_mapping_sku
    parsed_norm_base = _normalize_sku_for_duplicate(parsed_base)
    
    print(f"    parsed_norm = {parsed_norm}")
    print(f"    parsed_base = {parsed_base}")
    print(f"    parsed_norm_base = {parsed_norm_base}")
    
    for idx in valid_indices:
        if idx in used_item_indices:
            continue
        item = order.items[idx]
        if item.num != p.num:
            print(f"    item[{idx}]: num不匹配 ({item.num} != {p.num})")
            continue
        clean_item_sku = _clean_sku(item.shop_mapping_sku)
        if not clean_item_sku:
            continue
        
        score = -1
        match_reason = "no match"
        if clean_item_sku == p.shop_mapping_sku:
            score = 0
            match_reason = "exact match"
        elif clean_item_sku == parsed_base:
            score = 3
            match_reason = "== parsed_base"
        elif parsed_norm_base and clean_item_sku == parsed_norm_base:
            score = 4
            match_reason = "== parsed_norm_base"
        elif parsed_base and clean_item_sku.startswith(parsed_base):
            score = 1
            match_reason = "startswith(parsed_base)"
        elif parsed_norm_base and clean_item_sku.startswith(parsed_norm_base):
            score = 2
            match_reason = "startswith(parsed_norm_base)"
        
        print(f"    item[{idx}]: score={score}, reason={match_reason}")
        print(f"      clean_item_sku = {clean_item_sku}")
        print(f"      p.shop_mapping_sku = {p.shop_mapping_sku}")
        
        if score > best_score:
            best_score = score
            best_idx = idx
    
    if best_idx is not None:
        matched_item_idx = best_idx
        print(f"    -> SKU匹配: item[{matched_item_idx}], score={best_score}")
    else:
        print(f"    -> SKU未匹配")
    
    # 顺序匹配
    if matched_item_idx is None:
        for idx in valid_indices:
            if idx not in used_item_indices:
                matched_item_idx = idx
                print(f"    -> 顺序匹配: item[{matched_item_idx}]")
                break
    
    if matched_item_idx is not None:
        used_item_indices.add(matched_item_idx)
        print(f"    => 最终匹配: item[{matched_item_idx}]")
    else:
        print(f"    => 未匹配，将创建新行")

print(f"\nused_item_indices = {used_item_indices}")
print(f"未匹配的商品行: {[i for i in valid_indices if i not in used_item_indices]}")
