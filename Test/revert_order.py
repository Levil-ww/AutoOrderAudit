"""
订单修复/撤销脚本
=================
用于修复自动审单出错的订单。
支持：
  1. 按订单号查询当前状态
  2. 按备注搜索订单
  3. 使用正确的备注重新解析
  4. 提交修复后的商品编码
"""

import sys
import json
from datetime import datetime

sys.path.insert(0, "..")

from adapters.fangguo import FangguoAdapter
from core.parser import extract_multiple_remarks
from core import Order, OrderItem


def fetch_order_by_trade_id(adapter, trade_id):
    """通过订单号获取订单详情（增强版）"""
    detail = adapter.fetch_order_detail(order_id=trade_id)
    if not detail:
        print(f"❌ 未找到订单 {trade_id}")
        return None

    order = adapter._to_order(detail)
    adapter._enrich_order_with_detail(order)

    if not order.shop_remark:
        order.shop_remark = adapter._extract_field(detail, [
            "shopRemark", "sellerRemark", "remark", "备注", "卖家备注", "shop_remark",
        ])
    print(f"  卖家备注: {order.shop_remark}")
    return order


def fetch_order_by_trade_id_v2(adapter, trade_id):
    """通过 tradeIdStr 查询订单（解决平台订单号无法查询的问题）"""
    print(f"  使用 tradeIdStr 方式查询订单: {trade_id}")
    
    for status in [2, 1, 3]:
        orders = adapter.query_orders(
            page_no=1,
            page_size=10,
            query_status=status,
            trade_id=trade_id,
        )
        if orders:
            order = orders[0]
            print(f"  ✅ 在状态{status}找到订单: trade_id={order.trade_id}, sys_tid={order.sys_tid}")
            if not order.shop_remark or not order.items:
                adapter._enrich_order_with_detail(order)
            print(f"  卖家备注: {order.shop_remark}")
            return order
    
    print(f"  ❌ 未找到订单 {trade_id}")
    return None


def search_orders_by_remark(adapter, remark_keyword, max_pages=3):
    """通过备注关键字搜索订单（搜索多种状态）"""
    found_orders = []
    
    statuses_to_search = [1, 2, 3]
    
    for status in statuses_to_search:
        print(f"  正在搜索状态 {status} 的订单...")
        for page_no in range(1, max_pages + 1):
            try:
                orders = adapter.query_orders(page_no=page_no, page_size=200, query_status=status)
                if not orders:
                    break
                
                for order in orders:
                    if order.shop_remark and remark_keyword in order.shop_remark:
                        found_orders.append(order)
                        
                if len(orders) < 200:
                    break
                    
            except Exception as e:
                print(f"    ❌ 查询第 {page_no} 页失败: {e}")
                break
    
    return found_orders


def print_order_info(order):
    """打印订单信息"""
    print(f"\n📋 订单信息")
    print(f"  订单号: {order.trade_id}")
    print(f"  系统ID: {order.sys_tid}")
    print(f"  卖家备注: {order.shop_remark}")
    print(f"  买家备注: {order.buyer_remark}")
    print(f"  商品行数: {len(order.items)}")
    
    print(f"\n  当前商品行:")
    for idx, item in enumerate(order.items):
        is_gift = adapter._is_gift_item(item)
        gift_tag = " 🎁" if is_gift else ""
        print(f"    [{idx}] {gift_tag} 编码: {item.shop_mapping_sku}")
        print(f"        标题: {item.title[:50]}...")
        print(f"        数量: {item.num}")


def parse_and_show_expected(order, adapter):
    """解析备注并显示期望的编码"""
    print(f"\n🔍 解析备注")
    
    material_map = getattr(adapter, 'material_map', None)
    material_matcher = getattr(adapter, 'get_material_matcher', lambda: None)()
    
    parsed_list = extract_multiple_remarks(
        order.shop_remark,
        material_map=material_map,
        material_matcher=material_matcher,
    )
    
    print(f"  解析结果 ({len(parsed_list)} 个商品):")
    for idx, parsed in enumerate(parsed_list):
        gift_info = f" | 赠品: {parsed.gift_name} x {parsed.gift_num}" if parsed.gift_name else ""
        print(f"    [{idx}] 编码: {parsed.shop_mapping_sku}{gift_info}")
        print(f"        材质: {parsed.material_code}")
        print(f"        颜色: {parsed.color_code}")
        print(f"        尺寸: {parsed.model_code}")
        print(f"        花型: {parsed.picture_code}")
    
    return parsed_list


def fix_order(adapter, order, parsed_list, dry_run=False):
    """修复订单"""
    print(f"\n🛠️  {'[模拟]' if dry_run else ''} 开始修复订单")
    
    if dry_run:
        print(f"  模拟模式：仅显示将要发送的数据，不实际提交")
        return False
    
    try:
        ok = adapter.update_merchant_code(order, parsed_list[0], parsed_list)
        if ok:
            print(f"  ✅ 修复成功！")
            return True
        else:
            print(f"  ❌ 修复失败")
            return False
    except Exception as e:
        print(f"  ❌ 修复异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def compare_codes(order, parsed_list):
    """对比当前编码和期望编码"""
    current_skus = set()
    for item in order.items:
        if item.shop_mapping_sku and not adapter._is_gift_item(item):
            current_skus.add(item.shop_mapping_sku)
    
    expected_skus = {p.shop_mapping_sku for p in parsed_list}
    
    print(f"\n📊 编码对比:")
    print(f"  当前商品编码: {current_skus}")
    print(f"  期望商品编码: {expected_skus}")
    
    missing = expected_skus - current_skus
    extra = current_skus - expected_skus
    
    if missing:
        print(f"  ❌ 缺失编码: {missing}")
    if extra:
        print(f"  ⚠️  多余编码: {extra}")
    
    is_correct = not missing and not extra
    if is_correct:
        print(f"  ✅ 编码已正确，无需修复")
    else:
        print(f"  ❌ 编码不一致，需要修复")
    
    return is_correct


def main():
    global adapter
    adapter = FangguoAdapter()
    
    print("=" * 60)
    print("📦 订单修复/撤销工具")
    print("=" * 60)
    
    trade_ids = ["6927793866839260495", "6927800195821436239"]
    
    print(f"\n🔍 正在查询订单...")
    
    found_orders = []
    for trade_id in trade_ids:
        print(f"  查询订单号: {trade_id}")
        order = fetch_order_by_trade_id(adapter, trade_id)
        if order:
            found_orders.append(order)
        else:
            order = fetch_order_by_trade_id_v2(adapter, trade_id)
            if order:
                found_orders.append(order)
    
    if not found_orders:
        print("\n❌ 未找到任何订单")
        
        custom_trade_id = input("\n请手动输入订单号: ").strip()
        if custom_trade_id:
            print(f"\n🔍 尝试方式一: 使用 fetch_order_detail 查询")
            order = fetch_order_by_trade_id(adapter, custom_trade_id)
            if order:
                found_orders = [order]
            else:
                print(f"\n🔍 尝试方式二: 使用 tradeIdStr 查询")
                order = fetch_order_by_trade_id_v2(adapter, custom_trade_id)
                if order:
                    found_orders = [order]
                else:
                    print("❌ 未找到订单")
                    return
        else:
            return
    
    print(f"\n✅ 找到 {len(found_orders)} 个订单:")
    for i, order in enumerate(found_orders):
        print(f"  [{i+1}] 订单号: {order.trade_id}")
        print(f"      备注: {order.shop_remark[:60]}...")
        print(f"      商品数: {len(order.items)}")
    
    choice = input(f"\n请选择要修复的订单序号 (1-{len(found_orders)}): ").strip()
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(found_orders):
            print("❌ 无效的选择")
            return
        order = found_orders[idx]
    except ValueError:
        print("❌ 无效的输入")
        return
    
    print_order_info(order)
    
    parsed_list = parse_and_show_expected(order, adapter)
    
    if not parsed_list:
        print("❌ 无法解析备注，无法修复")
        return
    
    is_correct = compare_codes(order, parsed_list)
    
    if is_correct:
        print("\n✅ 当前编码已正确，无需修复")
        return
    
    print(f"\n{'=' * 60}")
    print("⚠️  确认修复")
    print("=" * 60)
    print("即将执行以下操作:")
    print("  1. 使用重新解析的编码覆盖当前商品行")
    print("  2. 正确处理赠品信息")
    print(f"  订单号: {order.trade_id}")
    print(f"  当前卖家备注: {order.shop_remark}")
    
    choice = input("\n确认修复? (y/n): ").strip().lower()
    if choice != 'y':
        print("✅ 已取消修复")
        return
    
    dry_run_choice = input("使用模拟模式? (y/n，仅显示不提交): ").strip().lower()
    dry_run = dry_run_choice == 'y'
    
    success = fix_order(adapter, order, parsed_list, dry_run)
    
    if success and not dry_run:
        print(f"\n✅ 订单 {order.trade_id} 修复完成！")
    elif dry_run:
        print(f"\n📋 模拟修复完成，请检查输出是否正确")


if __name__ == "__main__":
    main()