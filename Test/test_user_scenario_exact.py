"""
验证用户场景：
- 合并订单: 6928602547231620576&6928608971292638688
- 子订单6928608971292638688: 备注"定制双面革安妮森林;90x90cm-1张，送沥水垫30x50cm-1张"
- 子订单6928602547231620576: 空备注
- ERP自动关联了订单级备注到赠品行，导致30x50赠品行重复
"""
import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from unittest.mock import MagicMock


def make_raw(item_id, sku, num, type_val=0, title='', tid='', oid='',
             film_gift_code='', price=100, shop_remark='', origin_tid=''):
    return {
        'id': item_id,
        'orderId': '6928602547231620576&6928608971292638688',
        'sysOid': f's{item_id}',
        'oid': oid or f'o{item_id}',
        'tid': tid or f't{item_id}',
        'title': title,
        'skuPropertiesName': '',
        'shopMappingSku': sku,
        'originalSkuId': '',
        'originalGoodsId': '',
        'merchandisePicPath': '',
        'filmGiftCode': film_gift_code,
        'num': num,
        'price': price,
        'type': type_val,
        'shopRemark': shop_remark,
        'originTradeId': origin_tid,
    }


print("=" * 80)
print("用户场景验证")
print("合并订单: 6928602547231620576&6928608971292638688")
print("子订单2备注: 定制双面革安妮森林;90x90cm-1张，送沥水垫30x50cm-1张")
print("子订单1备注: (空)")
print("=" * 80)

adapter = FangguoAdapter()
adapter._session = MagicMock()
adapter._session.tenant_id = '5068663'
adapter._session.auth_cookie = 'fake_cookie'
adapter._session.auth_header = {}

tid1 = '6928602547231620576'
tid2 = '6928608971292638688'
merged_tid = f'{tid1}&{tid2}'
remark_tid2 = '定制双面革安妮森林;90x90cm-1张，送沥水垫30x50cm-1张'

order = Order(
    id='test_user_scenario',
    trade_id=tid2,
    tid=merged_tid,
    shop_remark=remark_tid2,
)

# === 子订单1 - 商品行（空备注） ===
order.items.append(OrderItem(
    id='item_prod_1',
    order_id=tid1,
    oid=f'oid_{tid1}',
    title='双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
    shop_mapping_sku='双面格-定制-定制尺寸-安妮森林;70x140CM',
    num=1,
    price=1.0,
    shop_remark='',
    original_tid=tid1,
    raw=make_raw('item_prod_1', '双面格-定制-定制尺寸-安妮森林;70x140CM', 1, 0,
                 '双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
                 tid=tid1, oid=f'oid_{tid1}', price=1),
))

# === 子订单2 - 商品行 ===
order.items.append(OrderItem(
    id='item_prod_2',
    order_id=tid2,
    oid=f'oid_{tid2}',
    title='双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
    shop_mapping_sku='双面格-定制-定制尺寸-安妮森林;90x90CM',
    num=1,
    price=1.0,
    shop_remark=remark_tid2,
    original_tid=tid2,
    raw=make_raw('item_prod_2', '双面格-定制-定制尺寸-安妮森林;90x90CM', 1, 0,
                 '双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
                 tid=tid2, oid=f'oid_{tid2}', price=1, shop_remark=remark_tid2),
))

# === ERP自动创建的30x50赠品行1（订单级备注被关联） ===
order.items.append(OrderItem(
    id='item_gift_2a',
    order_id=tid2,
    oid=f'oid_gift_{tid2}_a',
    title='赠品沥水垫30x50cm',
    shop_mapping_sku='吸水皮革-标准-30x50-随机发；30x50',
    num=1,
    price=0.0,
    shop_remark=remark_tid2,
    original_tid=merged_tid,
    raw=make_raw('item_gift_2a', '吸水皮革-标准-30x50-随机发；30x50', 1, 0,
                 '赠品沥水垫30x50cm',
                 tid=merged_tid, oid=f'oid_gift_{tid2}_a', price=0,
                 shop_remark=remark_tid2, origin_tid=merged_tid),
))

# === ERP自动创建的30x50赠品行2（重复） ===
order.items.append(OrderItem(
    id='item_gift_2b',
    order_id=tid2,
    oid=f'oid_gift_{tid2}_b',
    title='赠品沥水垫30x50cm',
    shop_mapping_sku='吸水皮革-标准-30x50-随机发；30x50',
    num=1,
    price=0.0,
    shop_remark=remark_tid2,
    original_tid=merged_tid,
    raw=make_raw('item_gift_2b', '吸水皮革-标准-30x50-随机发；30x50', 1, 0,
                 '赠品沥水垫30x50cm',
                 tid=merged_tid, oid=f'oid_gift_{tid2}_b', price=0,
                 shop_remark=remark_tid2, origin_tid=merged_tid),
))

print(f"\n初始商品行 ({len(order.items)} 个):")
for i, item in enumerate(order.items):
    is_gift = adapter._is_gift_item(item)
    print(f"  [{i}] id={item.id}, tid={str(item.original_tid)[-16:]}, "
          f"SKU={item.shop_mapping_sku[:50]}, num={item.num}, is_gift={is_gift}")

# === 运行引擎 ===
print("\n" + "=" * 80)
print("引擎处理")
print("=" * 80)

from core.engine import AutoAuditEngine

captured = {}

def mock_post(url, json=None, timeout=None):
    captured['payload'] = json
    captured['url'] = url
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
    return resp

adapter._session.post = mock_post

engine = AutoAuditEngine(adapter, dry_run=False)
engine.stats = {"total": 1, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}

try:
    engine._process_order(order)
    print(f"\n引擎统计: {engine.stats}")
except Exception as exc:
    import traceback
    print(f"引擎异常: {exc}")
    traceback.print_exc()

# === 分析结果 ===
payload = captured.get('payload', {})
all_items = payload.get('orderItems', [])
print(f"\n{'=' * 80}")
print(f"最终提交的 orderItems ({len(all_items)} 个):")
print(f"{'=' * 80}")

for i, it in enumerate(all_items):
    is_void = it.get('cancelStatus') or it.get('discardStatus', 0) >= 2
    sku = it.get('shopMappingSku', '') or ''
    origin_tid = str(it.get('originTradeId', it.get('oid', '')))
    num = it.get('num', 1)
    is_gift_sku = '赠品沥水垫' in sku or ('吸水皮革' in sku and '30x50' in sku) or '小圆或小方' in sku
    if is_void:
        mark = "🗑️作废"
    elif is_gift_sku:
        mark = "🎁赠品"
    else:
        mark = "📦商品"
    print(f"  [{i}] {mark} tid={origin_tid[-20:]}, SKU={sku[:60]}, num={num}")
