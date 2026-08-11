"""
验证修复：两个子订单各有赠品时，不误去重，且纯赠品备注（success=False）也收集赠品

场景：
- 合并订单: 6928601810063031567&6928604049951915279
- 子订单1 (6928601810063031567): "定制双面革安妮森林;35x320cm-1张，赠品圆垫-1张"
- 子订单2 (6928604049951915279): "赠送赠品圆垫-1张，方垫-1张"（补差价+纯赠品备注）

期望：
- 子订单1: 1个商品行（编码修改） + 1个圆垫赠品行
- 子订单2: 1个补差价行（编码修改） + 1个圆垫赠品 + 1个30x50(方垫)赠品行
- 合计: 赠品行3个（两个子订单的圆垫不会互相去重）
"""
import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.adapter_base import Order, OrderItem
from core.parser import extract_multiple_remarks
from adapters.fangguo.adapter import FangguoAdapter
from unittest.mock import MagicMock


def make_raw(item_id, sku, num, type_val=0, title='', tid='', oid='', film_gift_code='', price=100, shop_remark=''):
    return {
        'id': item_id,
        'orderId': '6928601810063031567&6928604049951915279',
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
    }


print("=" * 80)
print("测试：合并订单-两个子订单各自赠品不互相去重 + 纯赠品备注收集")
print("=" * 80)

adapter = FangguoAdapter()
adapter._session = MagicMock()
adapter._session.tenant_id = '5068663'
adapter._session.auth_cookie = 'fake_cookie'
adapter._session.auth_header = {}

tid1 = '6928601810063031567'
tid2 = '6928604049951915279'
remark_tid1 = '定制双面革安妮森林;35x320cm-1张，赠品圆垫-1张'
remark_tid2 = '赠送赠品圆垫-1张，方垫-1张'  # 纯赠品备注
order_remark = remark_tid1 + '，' + remark_tid2

order = Order(
    id='test_two_suborder_gifts',
    trade_id=tid1,
    tid=f'{tid1}&{tid2}',
    shop_remark=order_remark,
)

# 子订单1 - 商品行
order.items.append(OrderItem(
    id='item_prod_1',
    order_id=tid1,
    oid=f'oid_{tid1}',
    title='双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
    shop_mapping_sku='双面格-定制-定制尺寸-安妮森林;35x320CM',
    num=1,
    price=1.0,
    shop_remark=remark_tid1,
    original_tid=tid1,
    raw=make_raw('item_prod_1', '双面格-定制-定制尺寸-安妮森林;35x320CM', 1, 0,
                 '双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
                 tid=tid1, oid=f'oid_{tid1}', price=1, shop_remark=remark_tid1),
))

# 子订单2 - 补差价行（纯赠品备注）
order.items.append(OrderItem(
    id='item_prod_2',
    order_id=tid2,
    oid=f'oid_{tid2}',
    title='双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
    shop_mapping_sku='定制-定制-补差价-不打印',
    num=1,
    price=1.0,
    shop_remark=remark_tid2,
    original_tid=tid2,
    raw=make_raw('item_prod_2', '定制-定制-补差价-不打印', 1, 0,
                 '双面格电视柜台柜电视柜台面保护垫鞋柜防脏桌布',
                 tid=tid2, oid=f'oid_{tid2}', price=1, shop_remark=remark_tid2),
))

print(f"\n订单: trade_id={order.trade_id}")
print(f"订单级备注: '{order.shop_remark}'")
print(f"\n商品行 ({len(order.items)} 个):")
for i, item in enumerate(order.items):
    is_gift = adapter._is_gift_item(item)
    print(f"  [{i}] id={item.id}, tid={item.original_tid[-8:]}, "
          f"SKU={item.shop_mapping_sku}, num={item.num}, is_gift={is_gift}")
    print(f"       shop_remark='{item.shop_remark}'")

# ---- 引擎层（merged order处理）----
print("\n" + "=" * 80)
print("【引擎测试】合并订单处理（验证赠品收集）")
print("=" * 80)

from core.engine import AutoAuditEngine

engine = AutoAuditEngine(adapter)
captured = {}

def mock_post(url, json=None, timeout=None):
    captured['payload'] = json
    captured['url'] = url
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
    return resp

adapter._session.post = mock_post

# 直接调用引擎的合并订单处理（dry run，收集赠品）
material_map = adapter.material_map
material_matcher = adapter.get_material_matcher() if hasattr(adapter, 'get_material_matcher') else None

# 使用内部函数 _process_merged_order 并捕获 all_gifts
# 由于 _process_merged_order 没有直接返回赠品，这里用 patch 观察
original_update_fn = adapter.update_merchant_code
update_captured = {}

def capture_update(order_obj, first_parsed_item, parsed_list, price_diff_updates, gift_no_ship_tids=[], engine_gifts=None, gift_no_ship=False):
    update_captured['first'] = first_parsed_item
    update_captured['parsed'] = parsed_list
    update_captured['price_diff_updates'] = price_diff_updates
    update_captured['gift_no_ship_tids'] = gift_no_ship_tids
    update_captured['engine_gifts'] = engine_gifts
    # 从调用中收集赠品信息 - 直接运行后从 captured payload 验证
    return original_update_fn(order_obj, first_parsed_item, parsed_list, price_diff_updates, gift_no_ship_tids=gift_no_ship_tids, engine_gifts=engine_gifts, gift_no_ship=gift_no_ship)

adapter.update_merchant_code = capture_update

# 使用 dry_run=False 真正调用 update_merchant_code（mock API）
engine = AutoAuditEngine(adapter, dry_run=False)
adapter._session.post = mock_post
engine.stats = {"total": 1, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}

try:
    engine._process_order(order)
    print(f"  引擎统计: {engine.stats}")
except Exception as exc:
    import traceback
    print(f"  引擎异常: {exc}")
    traceback.print_exc()

print(f"\n--- 捕获的 update_merchant_code 调用 ---")
if 'parsed' in update_captured:
    print(f"解析结果数: {len(update_captured['parsed'])}")
    for i, p in enumerate(update_captured['parsed']):
        gift_str = ""
        if p.gifts:
            gift_str = f", gifts={p.gifts}"
        elif p.gift_name:
            gift_str = f", gift={p.gift_name}x{p.gift_num}"
        print(f"  [{i}] success={p.success}, tid={str(p.original_tid)[-8:]}, sku={p.shop_mapping_sku[:40]}{gift_str}")
    print(f"engine_gifts 传入 (engine 层完整赠品): {update_captured.get('engine_gifts')}")
    print(f"price_diff_updates: {len(update_captured['price_diff_updates'])} 个")
    for u in update_captured['price_diff_updates']:
        print(f"  - tid={str(u['tid'])[-8:]}, ship={u['ship']}, remark='{str(u['remark'])[:30]}'")

payload = captured.get('payload', {})
all_items = payload.get('orderItems', [])
print(f"\n提交的 orderItems ({len(all_items)} 个):")

active_gifts = []
active_prods = []
for i, it in enumerate(all_items):
    is_void = it.get('cancelStatus') or it.get('discardStatus') or it.get('discardStatus', 0) >= 2
    sku = it.get('shopMappingSku', '') or ''
    oid = str(it.get('originTradeId', it.get('oid', '')))
    num = it.get('num', 1)
    is_gift_sku = '赠品沥水垫' in sku or ('吸水皮革' in sku and '30x50' in sku)
    mark = "🗑️作废" if is_void else ("🎁赠品" if is_gift_sku else "📦商品")
    print(f"  [{i}] {mark} tid={oid[-10:]}, SKU={sku}, num={num}")
    if not is_void:
        if is_gift_sku:
            active_gifts.append((oid[-8:], sku, num))
        else:
            active_prods.append((oid[-8:], sku, num))

print(f"\n=== 结果分析 ===")
print(f"  有效商品行: {len(active_prods)} 个")
for tid, sku, n in active_prods:
    print(f"    - {tid}: {sku[:50]} x{n}")
print(f"  有效赠品行: {len(active_gifts)} 个")
from collections import defaultdict
gifts_by_tid = defaultdict(list)
for tid, sku, n in active_gifts:
    # 提取简洁名
    if '小圆或小方' in sku:
        name = '圆垫/沥水垫25cm'
    elif '30x50' in sku:
        name = '方垫/30x50'
    else:
        name = '赠品'
    gifts_by_tid[tid].append(f"{name}x{n}")
for tid, glist in gifts_by_tid.items():
    print(f"    - 子订单 {tid}: {', '.join(glist)}")

print(f"\n=== 断言验证 ===")
ok = True

# 1. 赠品行总数=3
total_gifts = len(active_gifts)
if total_gifts == 3:
    print(f"【检查1】赠品行总数=3: ✅ 通过（子订单1圆垫x1, 子订单2圆垫x1+方垫/30x50x1）")
else:
    print(f"【检查1】赠品行总数期望=3，实际={total_gifts}: ❌ 失败")
    ok = False

# 2. 两个子订单都有赠品行（不互相去重）
if len(gifts_by_tid) >= 2:
    print(f"【检查2】两个子订单各有赠品行: ✅ 通过（不同 tid 不互相去重）")
else:
    print(f"【检查2】期望两个子订单都有赠品，实际子订单分组: {list(gifts_by_tid.keys())}: ❌ 失败")
    ok = False

# 3. 子订单2包含30x50赠品（方垫）
tid2_key = tid2[-8:]
has_30x50 = any('方垫' in x or '30x50' in x for x in gifts_by_tid.get(tid2_key, []))
if has_30x50:
    print(f"【检查3】子订单2有方垫30x50赠品: ✅ 通过（无前缀的方垫已被上下文继承识别）")
else:
    print(f"【检查3】子订单2缺失方垫30x50赠品（gifts={gifts_by_tid.get(tid2_key)}）: ❌ 失败")
    ok = False

# 4. 纯赠品备注（success=False）的子订单2的赠品被收集
tid1_key = tid1[-8:]
if gifts_by_tid.get(tid1_key) and gifts_by_tid.get(tid2_key):
    print(f"【检查4】两个子订单赠品均被收集: ✅ 通过（纯赠品备注未被跳过）")
else:
    print(f"【检查4】赠品收集不完整: {dict(gifts_by_tid)}: ❌ 失败")
    ok = False

print()
if ok:
    print("🎉 全部通过！修复有效：")
    print("   - 两个子订单的赠品不会互相去重（original_tid 不同）")
    print("   - 纯赠品备注（success=False）的子订单赠品也会被收集")
    print("   - 无前缀的'方垫'通过上下文继承被识别")
else:
    print("❌ 存在失败项，请检查上方输出。")
