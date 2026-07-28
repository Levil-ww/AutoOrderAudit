import sys
sys.path.insert(0, '/')
from core.adapter_base import OrderItem
from adapters.fangguo.adapter import FangguoAdapter
import re

adapter = FangguoAdapter()

item = OrderItem(
    id='1', 
    title='轻奢大理石纹防水垫',
    shop_mapping_sku='吸水皮革-定制-定制尺寸-白色大理石3;60x110cm', 
    num=1,
    price=100,
    raw={
        'id': '1',
        'filmGiftCode': '',
        'type': 0,
    }
)

print(f"title: {item.title}")
print(f"sku: {item.shop_mapping_sku}")
print(f"price: {item.price}")
print(f"filmGiftCode: {item.raw.get('filmGiftCode', '')}")
print()

# 逐个检查
gift_code = item.raw.get('filmGiftCode', '') if item.raw else ''
print(f"方式1 - filmGiftCode非空: {bool(gift_code)}")

title = item.title or ''
print(f"方式2 - 标题含'赠品': {'赠品' in title}")

sku = item.shop_mapping_sku or ''
print(f"方式3 - SKU含'赠品': {'赠品' in sku}")

print(f"方式4条件 - price==0且标题含'垫': {item.price == 0 and '垫' in title}")

gift_sku_result = adapter._is_gift_sku(sku)
print(f"方式5 - 是赠品SKU: {gift_sku_result}")

# 直接调用
print(f"\n最终 is_gift: {adapter._is_gift_item(item)}")

# 看看是不是有其他字段影响
print(f"\nitem.raw.keys(): {item.raw.keys()}")
