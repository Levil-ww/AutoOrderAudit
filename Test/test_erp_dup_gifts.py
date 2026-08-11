"""
测试：ERP自动创建多个赠品行导致重复问题

场景：
- 合并订单: 6928602547231620576&6928608971292638688
- 子订单1 (6928602547231620576): 原赠品行(小圆或小方,编码已正确)
- 子订单2 (6928608971292638688): 商品行 + 2个ERP自动创建的30x50赠品行
  - 备注: 定制双面革安妮森林;90x90cm-1张，送沥水垫30x50cm-1张
  - ERP因为订单级备注关联, 创建了2个相同的30x50赠品行

期望：程序能正确去重, 最终只有1个30x50赠品行
"""
import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.adapter_base import Order, OrderItem
from core.parser import extract_multiple_remarks
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
print("测试：ERP自动创建多个赠品行导致重复问题")
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
order_remark = remark_tid2

order = Order(
    id='test_erp_dup_gifts',
    trade_id=tid2,
    tid=merged_tid,
    shop_remark=order_remark,
)

# === 子订单1 - 商品行 ===
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

# === 子订单1 - 原赠品行(编码已正确) ===
item_gift_1 = OrderItem(
    id='item_gift_1',
    order_id=tid1,
    oid=f'oid_gift_{tid1}',
    title='赠品沥水垫小圆或小方',
    shop_mapping_sku='吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方',
    num=1,
    price=0.0,
    shop_remark='',
    original_tid=tid1,
    raw=make_raw('item_gift_1', '吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方', 1, 0,
                 '赠品沥水垫小圆或小方',
                 tid=tid1, oid=f'oid_gift_{tid1}', price=0),
)
order.items.append(item_gift_1)

# === 子订单2 - 商品行 ===
item_prod_2 = OrderItem(
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
)
order.items.append(item_prod_2)

# === 子订单2 - ERP自动创建的赠品行1 (30x50) ===
# 注意：ERP创建的赠品行使用合并订单号作为originTradeId
item_gift_2a = OrderItem(
    id='item_gift_2a',
    order_id=tid2,
    oid=f'oid_gift_{tid2}_a',
    title='赠品沥水垫30x50cm',
    shop_mapping_sku='吸水皮革-标准-30x50-随机发；30x50',
    num=1,
    price=0.0,
    shop_remark=remark_tid2,  # ERP关联了订单级备注
    original_tid=merged_tid,  # 关键：ERP创建的赠品行使用合并订单号
    raw=make_raw('item_gift_2a', '吸水皮革-标准-30x50-随机发；30x50', 1, 0,
                 '赠品沥水垫30x50cm',
                 tid=merged_tid, oid=f'oid_gift_{tid2}_a', price=0, 
                 shop_remark=remark_tid2, origin_tid=merged_tid),
)
order.items.append(item_gift_2a)

# === 子订单2 - ERP自动创建的赠品行2 (30x50) ===
# 这是第二个重复的赠品行（ERP可能因为某种原因创建了两个）
item_gift_2b = OrderItem(
    id='item_gift_2b',
    order_id=tid2,
    oid=f'oid_gift_{tid2}_b',
    title='赠品沥水垫30x50cm',
    shop_mapping_sku='吸水皮革-标准-30x50-随机发；30x50',
    num=1,
    price=0.0,
    shop_remark=remark_tid2,  # ERP关联了订单级备注
    original_tid=merged_tid,  # 关键：ERP创建的赠品行使用合并订单号
    raw=make_raw('item_gift_2b', '吸水皮革-标准-30x50-随机发；30x50', 1, 0,
                 '赠品沥水垫30x50cm',
                 tid=merged_tid, oid=f'oid_gift_{tid2}_b', price=0,
                 shop_remark=remark_tid2, origin_tid=merged_tid),
)
order.items.append(item_gift_2b)

print(f"\n订单: trade_id={order.trade_id}")
print(f"订单级备注: '{order.shop_remark}'")
print(f"\n商品行 ({len(order.items)} 个):")
for i, item in enumerate(order.items):
    is_gift = adapter._is_gift_item(item)
    print(f"  [{i}] id={item.id}, tid={str(item.original_tid)[-16:]}, "
          f"SKU={item.shop_mapping_sku[:50]}, num={item.num}, is_gift={is_gift}")
    print(f"       shop_remark='{item.shop_remark[:50]}'")

# === 运行引擎 ===
print("\n" + "=" * 80)
print("【引擎测试】处理合并订单")
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

# 使用非dry_run模式
engine = AutoAuditEngine(adapter, dry_run=False)
engine.stats = {"total": 1, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}

try:
    engine._process_order(order)
    print(f"  引擎统计: {engine.stats}")
except Exception as exc:
    import traceback
    print(f"  引擎异常: {exc}")
    traceback.print_exc()

# === 分析结果 ===
payload = captured.get('payload', {})
all_items = payload.get('orderItems', [])
print(f"\n提交的 orderItems ({len(all_items)} 个):")

active_gifts = []
active_prods = []
void_count = 0
for i, it in enumerate(all_items):
    is_void = it.get('cancelStatus') or it.get('discardStatus', 0) >= 2
    sku = it.get('shopMappingSku', '') or ''
    origin_tid = str(it.get('originTradeId', it.get('oid', '')))
    num = it.get('num', 1)
    is_gift_sku = '赠品沥水垫' in sku or ('吸水皮革' in sku and '30x50' in sku)
    mark = "🗑️作废" if is_void else ("🎁赠品" if is_gift_sku else "📦商品")
    if is_void:
        void_count += 1
    print(f"  [{i}] {mark} originTradeId={origin_tid[-20:]}, SKU={sku[:60]}, num={num}")
    if not is_void:
        if is_gift_sku:
            active_gifts.append((origin_tid[-20:], sku, num))
        else:
            active_prods.append((origin_tid[-20:], sku, num))

print(f"\n=== 结果分析 ===")
print(f"  有效商品行: {len(active_prods)} 个")
for tid, sku, n in active_prods:
    print(f"    - {tid}: {sku[:50]} x{n}")
print(f"  有效赠品行: {len(active_gifts)} 个")
from collections import defaultdict
gifts_by_sku = defaultdict(list)
for tid, sku, n in active_gifts:
    gifts_by_sku[sku].append((tid, n))
for sku, glist in gifts_by_sku.items():
    print(f"    - {sku[:60]}: {len(glist)}个")
    for tid, n in glist:
        print(f"      tid={tid}, num={n}")
print(f"  作废行: {void_count} 个")

print(f"\n=== 断言验证 ===")
ok = True

# 1. 30x50赠品行数量应该为1（不是2）
gift_30x50_count = sum(1 for _, sku, _ in active_gifts if '30x50' in sku)
if gift_30x50_count == 1:
    print(f"【检查1】30x50赠品行数量=1: ✅ 通过")
else:
    print(f"【检查1】30x50赠品行数量期望=1，实际={gift_30x50_count}: ❌ 失败")
    ok = False

# 2. 总赠品行数量应该为2（1个小圆或小方 + 1个30x50）
total_gifts = len(active_gifts)
if total_gifts == 2:
    print(f"【检查2】总赠品行数量=2: ✅ 通过")
else:
    print(f"【检查2】总赠品行数量期望=2，实际={total_gifts}: ❌ 失败")
    ok = False

# 3. 应该有作废的行（被去重的重复赠品行）
if void_count >= 1:
    print(f"【检查3】有作废行(被去重): ✅ 通过 (作废{void_count}个)")
else:
    print(f"【检查3】期望有作废行(去重重复赠品行): ❌ 失败")
    ok = False

print()
if ok:
    print("🎉 全部通过！修复有效")
else:
    print("❌ 存在失败项")
