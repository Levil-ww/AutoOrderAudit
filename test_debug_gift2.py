import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')
from core.adapter_base import OrderItem
from adapters.fangguo.adapter import FangguoAdapter
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

item = OrderItem(
    id='1', 
    order_id='6928300064387268308',
    oid='6928300064387268308',
    sys_oid='s1',
    title='轻奢大理石纹防水垫',
    shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
    num=1,
    price=100,
    raw=make_raw('1', '吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 1, 0, '轻奢大理石纹防水垫'),
)

print(f"item.price = {item.price}")
print(f"item.title = {item.title}")
print(f"item.shop_mapping_sku = {item.shop_mapping_sku}")
print(f"item.raw.get('price') = {item.raw.get('price')}")
print()

# 手动复制 _is_gift_item 的逻辑
def debug_is_gift(item):
    # 方式1
    gift_code = item.raw.get('filmGiftCode', '') if item.raw else ''
    print(f"  方式1: filmGiftCode='{gift_code}', 结果: {bool(gift_code)}")
    if gift_code:
        return True

    # 方式2
    title = item.title or ''
    print(f"  方式2: 标题含'赠品': {'赠品' in title}")
    if '赠品' in title:
        return True

    # 方式3
    sku = item.shop_mapping_sku or ''
    print(f"  方式3: SKU含'赠品': {'赠品' in sku}")
    if '赠品' in sku:
        return True

    # 方式4
    print(f"  方式4条件: price==0? {item.price == 0}, 标题含'垫'? {'垫' in title}")
    if item.price == 0 and '垫' in title:
        print("    进入方式4")
        if item.raw and item.raw.get('type') == 1:
            clean_sku = re.sub(r'<[^>]+>', '', sku)
            if clean_sku and not adapter._is_gift_sku(clean_sku):
                print("    手工单行且非赠品SKU -> 返回False")
                return False
        non_gift_keywords = ['桌垫', '餐垫', '杯垫', '地垫', '鼠标垫', '脚垫']
        has_non_gift_kw = any(kw in title for kw in non_gift_keywords)
        print(f"    含非赠品关键词? {has_non_gift_kw}")
        if not has_non_gift_kw:
            print("    返回True")
            return True

    # 方式5
    gift_sku_result = adapter._is_gift_sku(sku)
    print(f"  方式5: 是赠品SKU? {gift_sku_result}")
    if gift_sku_result:
        return True

    print("  都不匹配，返回False")
    return False

print("调试 _is_gift_item:")
result = debug_is_gift(item)
print(f"\n最终结果: {result}")
print(f"直接调用结果: {adapter._is_gift_item(item)}")
