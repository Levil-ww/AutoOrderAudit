"""
核心 - 自动审单引擎
通用的自动审单流程，通过 ErpAdapter 接口与具体 ERP 解耦。
"""

import time
from datetime import datetime
from typing import Callable, Optional

from .adapter_base import ErpAdapter, Order, OrderItem
from .parser import parse_remark, extract_multiple_remarks


_SKIP_KEYWORDS = [
    "待定",
    "待确定",
    "待确认",
    "等通知发",
    "需要效果图",
    "效果图",
    "确认再生产",
    "号发货",
    "安排发货",
    "在安排发货",
    "已代益",
    "已代森",
    "仓库发",
    "工厂发",
    "补发",
]


_PRICE_DIFF_KEYWORDS = [
    "补差价专拍",
    "差价专用",
    "少几元拍几个",
]


class AutoAuditEngine:
    """自动审单引擎"""

    def __init__(
        self,
        adapter: ErpAdapter,
        dry_run: bool = False,
        max_orders: int = 0,
        interval: float = 0.5,
        confirm_callback: Optional[Callable] = None,
    ):
        """
        :param confirm_callback: 确认回调，签名 (order, parsed_list, changes: list[str]) -> bool
                                返回 True 表示确认修改，False 表示仅记录不修改。
                                仅在非 dry_run 模式下生效。
        """
        self.adapter = adapter
        self.dry_run = dry_run
        self.max_orders = max_orders
        self.interval = interval
        self.confirm_callback = confirm_callback
        self.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [],
                      "cancelled": 0}  # cancelled 统计用户取消的数量

    def _is_price_difference_order(self, order: Order) -> bool:
        """
        判断订单是否为补差价订单
        通过检查商品行标题是否包含补差价相关关键字
        """
        for item in order.items:
            if item.title:
                for keyword in _PRICE_DIFF_KEYWORDS:
                    if keyword in item.title:
                        return True
        return False

    def _process_price_difference_order(self, order: Order):
        """
        处理补差价订单的逻辑：
        1. 如果订单只有补差价商品行且备注为空，跳过不处理
        2. 如果备注包含"差价不发货"，将编码修改为"定制-定制-补差价-不打印"，数量改为1
        3. 如果备注非空且不包含"差价不发货"，按正常解析逻辑处理
        4. 如果订单有其他商品行且备注为空，仅修改补差价商品行数量为1
        """
        remark = order.shop_remark or ""
        print(f"  💰 补差价订单处理")
        
        price_diff_items = [item for item in order.items if self._is_price_difference_item(item)]
        only_price_diff = len(price_diff_items) == len(order.items)
        
        if only_price_diff and not remark.strip():
            print(f"  ⏭️  跳过：只有补差价订单且备注为空")
            self.stats["skipped"] += 1
            return
        
        if "差价不发货" in remark:
            print(f"  📝 差价不发货：修改编码为'定制-定制-补差价-不打印'，数量改为1")

            if self.dry_run:
                print(f"  🔶 DRY RUN: 修改编码为'定制-定制-补差价-不打印'")
                self.stats["success"] += 1
                return

            try:
                ok = self.adapter.update_price_difference_order(order, price_diff_items, ship=False)
                if ok is None:
                    print(f"  ⏭️  跳过：补差价订单编码已正确")
                    self.stats["skipped"] += 1
                elif ok:
                    print(f"  ✅ 修改成功！")
                    self.stats["success"] += 1
                else:
                    print(f"  ❌ 修改失败")
                    self.stats["failed"] += 1
            except Exception as e:
                print(f"  ❌ 请求异常: {e}")
                self.stats["failed"] += 1
            return

        if only_price_diff and remark.strip():
            # 只有补差价商品且备注含定制信息，直接按普通订单解析修改编码
            print(f"  📝 只有补差价商品，备注含信息，直接解析修改编码")
            self._process_normal_order_logic(order)
            return

        if remark.strip():
            print(f"  📝 备注含信息，按正常解析逻辑处理")
            price_diff_updates = [{
                'tid': order.tid,
                'items': price_diff_items,
                'remark': remark,
                'ship': True,
            }]
            self._process_normal_order_logic(order, price_diff_updates)
            return

        print(f"  📝 备注为空，仅修改补差价商品行数量为1")
        if self.dry_run:
            print(f"  🔶 DRY RUN: 仅修改数量为1")
            self.stats["success"] += 1
            return
        
        try:
            ok = self.adapter.update_price_difference_order(order, price_diff_items, ship=True)
            if ok is None:
                print(f"  ⏭️  跳过：补差价订单数量已为1")
                self.stats["skipped"] += 1
            elif ok:
                print(f"  ✅ 修改成功！数量已改为1")
                self.stats["success"] += 1
            else:
                print(f"  ❌ 修改失败")
                self.stats["failed"] += 1
        except Exception as e:
            print(f"  ❌ 请求异常: {e}")
            self.stats["failed"] += 1

    def _is_price_difference_item(self, item: OrderItem) -> bool:
        """判断商品行是否为补差价商品"""
        if item.title:
            for keyword in _PRICE_DIFF_KEYWORDS:
                if keyword in item.title:
                    return True
        return False

    def _process_normal_order_logic(self, order: Order, price_diff_updates: list = None):
        """
        普通订单处理逻辑（从 _process_order 提取的公共逻辑）
        
        Args:
            price_diff_updates: 补差价商品行更新列表，用于合并订单或混合订单的一次性处理
        """
        remark = order.shop_remark or ""
        gift_no_ship = "赠品不送" in remark
        
        for keyword in _SKIP_KEYWORDS:
            if keyword in remark:
                print(f"  ⏭️  跳过：备注包含关键字 '{keyword}'")
                self.stats["skipped"] += 1
                return

        material_map = getattr(self.adapter, 'material_map', None)
        material_matcher = getattr(self.adapter, 'get_material_matcher', lambda: None)()

        parsed_list = extract_multiple_remarks(
            remark,
            material_map=material_map,
            material_matcher=material_matcher,
        )

        if not parsed_list:
            if gift_no_ship:
                parsed_list = []
            else:
                print(f"  ⏭️  跳过：无法解析备注")
                self.stats["skipped"] += 1
                return

        parsed = parsed_list[0] if parsed_list else None
        
        has_product_info = parsed.success if parsed else False
        
        if has_product_info:
            summary = (
                f"  ✅ 材质: {parsed.material_code}  "
                f"|  颜色: {parsed.color_code}  "
                f"|  尺寸: {parsed.model_code}  "
                f"|  花型: {parsed.picture_code}"
            )
            print(summary)
        else:
            print(f"  ℹ️  无商品定制信息")

        all_gifts = []
        for p in parsed_list:
            if p.gifts:
                all_gifts.extend(p.gifts)
            elif p.gift_name and p.gift_num > 0:
                all_gifts.append((p.gift_name, p.gift_num))
        
        all_gifts = list(dict.fromkeys(all_gifts))
        
        for gift_name, gift_num in all_gifts:
            print(f"  🎁 赠品: {gift_name} x {gift_num}")
        
        if not has_product_info and not all_gifts and not gift_no_ship:
            print(f"  ⏭️  跳过：无商品定制信息且无赠品")
            self.stats["skipped"] += 1
            return

        if self.dry_run:
            print()
            for parsed in parsed_list:
                if parsed.success:
                    print(f"  🔶 DRY RUN: 新编码 = {parsed.shop_mapping_sku}")
            for gift_name, gift_num in all_gifts:
                print(f"  🔶 DRY RUN: 将添加赠品商品行 = {gift_name} x {gift_num}")
            if price_diff_updates:
                for update in price_diff_updates:
                    action = "修改编码为'定制-定制-补差价-不打印'" if not update['ship'] else "仅修改数量为1"
                    print(f"  🔶 DRY RUN: 补差价订单 -> {action}")
            if gift_no_ship:
                print(f"  🔶 DRY RUN: 赠品不发货 -> 修改赠品行编码为'定制-定制-补差价-不打印'")
            self.stats["success"] += 1
            return

        if self.confirm_callback:
            changes = []
            for p in parsed_list:
                if p.success:
                    changes.append(f"新编码: {p.shop_mapping_sku}")
            for gift_name, gift_num in all_gifts:
                changes.append(f"赠品: {gift_name} x {gift_num}")
            if price_diff_updates:
                for update in price_diff_updates:
                    action = "修改编码为'定制-定制-补差价-不打印'" if not update['ship'] else "仅修改数量为1"
                    changes.append(f"补差价订单: {action}")
            if gift_no_ship:
                changes.append(f"赠品不发货: 修改赠品行编码为'定制-定制-补差价-不打印'")

            should_update = self.confirm_callback(order, parsed_list, changes)
            if not should_update:
                if parsed_list and parsed_list[0].success:
                    print(f"  ⏭️  用户取消：新编码 {parsed_list[0].shop_mapping_sku}（未修改）")
                else:
                    print(f"  ⏭️  用户取消（未修改）")
                self.stats["cancelled"] += 1
                return

        try:
            ok = self.adapter.update_merchant_code(order, parsed_list[0] if parsed_list else None, parsed_list, price_diff_updates, gift_no_ship=gift_no_ship)
            if ok is None:
                print(f"  ⏭️  跳过：订单所有商品行已作废")
                self.stats["skipped"] += 1
            elif ok:
                if parsed_list[0].success:
                    print(f"  ✅ 修改成功！新编码: {parsed_list[0].shop_mapping_sku}")
                    if len(parsed_list) > 1:
                        print(f"  📦 包含 {len(parsed_list)} 个尺寸，已拆分处理")
                else:
                    print(f"  ✅ 修改成功！")
                for gift_name, gift_num in all_gifts:
                    print(f"  🎁 赠品已添加: {gift_name} x {gift_num}")
                if price_diff_updates:
                    print(f"  ✅ 补差价订单修改成功！")
                self.stats["success"] += 1
            else:
                print(f"  ❌ 修改失败")
                self.stats["failed"] += 1
                self.stats["errors"].append(f"订单 {order.trade_id}: 接口返回失败")
        except Exception as e:
            print(f"  ❌ 请求异常: {e}")
            self.stats["failed"] += 1
            self.stats["errors"].append(f"订单 {order.trade_id}: {e}")

    def run(self, page_no=1, page_size=500, query_status=1, time_begin="", time_end=""):
        print("=" * 60)
        print(f"自动审单引擎 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"适配器: {self.adapter.get_adapter_name()}")
        if self.dry_run:
            print("🔶 DRY RUN 模式：仅模拟，不会真实提交")
        if self.confirm_callback and not self.dry_run:
            print("💬 确认模式：修改前会弹窗确认")
        print("=" * 60)

        print("\n📦 正在查询待处理订单...")
        try:
            orders = self.adapter.query_orders(
                page_no=page_no, page_size=page_size,
                query_status=query_status, time_begin=time_begin, time_end=time_end,
            )
        except Exception as e:
            print(f"❌ 查询订单失败: {e}")
            return

        if not orders:
            print("✅ 没有待处理的订单")
            self._print_summary()
            return

        print(f"📋 共获取 {len(orders)} 个待处理订单")

        for idx, order in enumerate(orders):
            if self.max_orders > 0 and idx >= self.max_orders:
                print(f"\n⏸️  已达最大处理数量 ({self.max_orders})")
                break

            self.stats["total"] += 1
            print(f"[{idx+1}/{len(orders)}] 处理订单 {order.id or order.trade_id}")

            try:
                self._process_order(order)
                # 处理完商品编码后，统一处理快递
                self._update_express_for_order(order)
            except Exception as e:
                self.stats["failed"] += 1
                self.stats["errors"].append(str(e))
                print(f"  ❌ 订单处理异常: {e}")

            time.sleep(self.interval)

        self._print_summary()

    def _process_order(self, order):
        remark = order.shop_remark or ""
        print(f"  卖家备注: {remark[:60]}..." if len(remark) > 60 else f"  卖家备注: {remark}")

        material_map = getattr(self.adapter, 'material_map', None)
        material_matcher = getattr(self.adapter, 'get_material_matcher', lambda: None)()

        # ===== 检测补差价订单 =====
        if self._is_price_difference_order(order):
            self._process_price_difference_order(order)
            return

        # ===== 检测合并订单 =====
        # 合并订单特征：订单号包含 &，或商品行有不同的 original_tid
        is_merged_order = "&" in order.trade_id or "&" in order.tid
        
        if not is_merged_order:
            # 检查商品行是否有不同的 original_tid
            tids = set()
            for item in order.items:
                if item.original_tid:
                    tids.add(item.original_tid)
            if len(tids) >= 2:
                is_merged_order = True

        if is_merged_order:
            self._process_merged_order(order, material_map, material_matcher)
            return

        # ===== 普通订单处理 =====
        if not remark.strip():
            print("  ⏭️  跳过：卖家备注为空")
            self.stats["skipped"] += 1
            return

        self._process_normal_order_logic(order)

    def _process_merged_order(self, order, material_map, material_matcher):
        """
        处理合并订单：按商品行的 original_tid 分组，每组使用自己的备注单独处理
        """
        print(f"  🔄 合并订单，按原始订单号分组处理")
        
        # 按 original_tid 分组商品行
        groups = {}
        for item in order.items:
            tid = item.original_tid or order.tid
            if tid not in groups:
                groups[tid] = {
                    'items': [],
                    'remark': '',
                    'is_price_diff': False,
                }
            groups[tid]['items'].append(item)
            # 确保 item.original_tid 与分组键一致（处理空值情况）
            item.original_tid = tid
            # 收集该组的备注（优先使用商品行级别的备注）
            if item.shop_remark:
                groups[tid]['remark'] = item.shop_remark
            # 检测是否为补差价分组
            if self._is_price_difference_item(item):
                groups[tid]['is_price_diff'] = True
        
        # 合并订单中，每个原始订单使用自己的商品行备注
        # 不回退使用订单级备注，因为订单级备注可能属于另一个原始订单
        
        # 处理每个分组
        all_parsed_list = []
        all_gifts = []
        price_diff_updates = []
        gift_no_ship_tids = []
        
        for tid, group in groups.items():
            group_remark = group['remark']
            is_price_diff = group['is_price_diff']
            print(f"    原始订单 {tid[:16]}...: 备注='{group_remark[:40]}...' {'(补差价)' if is_price_diff else ''}")
            
            if "赠品不送" in group_remark:
                gift_no_ship_tids.append(tid)
            
            if is_price_diff:
                if not group_remark.strip():
                    print(f"      📝 补差价订单备注为空，仅修改数量为1")
                    price_diff_updates.append({
                        'tid': tid,
                        'items': group['items'],
                        'remark': group_remark,
                        'ship': True,
                    })
                elif "差价不发货" in group_remark:
                    print(f"      📝 差价不发货：修改编码为'定制-定制-补差价-不打印'，数量改为1")
                    price_diff_updates.append({
                        'tid': tid,
                        'items': group['items'],
                        'remark': group_remark,
                        'ship': False,
                    })
                else:
                    print(f"      📝 补差价订单备注含信息，按正常解析逻辑处理")
                    skip_reason = None
                    for keyword in _SKIP_KEYWORDS:
                        if keyword in group_remark:
                            skip_reason = f"包含关键字 '{keyword}'"
                            break
                    
                    if skip_reason:
                        print(f"        ⏭️  跳过：{skip_reason}")
                        continue
                    
                    parsed_list = extract_multiple_remarks(
                        group_remark,
                        material_map=material_map,
                        material_matcher=material_matcher,
                    )
                    
                    if not parsed_list:
                        print(f"        ⏭️  跳过：无法解析备注")
                        continue
                    
                    for p in parsed_list:
                        p.original_tid = tid
                    
                    all_parsed_list.extend(parsed_list)
                    
                    for p in parsed_list:
                        if p.gifts:
                            all_gifts.extend(p.gifts)
                        elif p.gift_name and p.gift_num > 0:
                            all_gifts.append((p.gift_name, p.gift_num))
            else:
                skip_reason = None
                for keyword in _SKIP_KEYWORDS:
                    if keyword in group_remark:
                        skip_reason = f"包含关键字 '{keyword}'"
                        break
                
                if not group_remark.strip():
                    skip_reason = "备注为空"
                
                if skip_reason:
                    print(f"      ⏭️  跳过：{skip_reason}")
                    continue
                
                parsed_list = extract_multiple_remarks(
                    group_remark,
                    material_map=material_map,
                    material_matcher=material_matcher,
                )
                
                if not parsed_list:
                    print(f"      ⏭️  跳过：无法解析备注")
                    continue
                
                for p in parsed_list:
                    p.original_tid = tid
                    p.shop_remark = group['remark']

                all_parsed_list.extend(parsed_list)

                for p in parsed_list:
                    if p.gifts:
                        all_gifts.extend(p.gifts)
                    elif p.gift_name and p.gift_num > 0:
                        all_gifts.append((p.gift_name, p.gift_num))

        all_gifts = list(dict.fromkeys(all_gifts))

        if not all_parsed_list and not price_diff_updates and not gift_no_ship_tids:
            print(f"  ⏭️  跳过：所有分组均无法解析")
            self.stats["skipped"] += 1
            return
        
        if all_parsed_list:
            parsed = all_parsed_list[0]
            summary = (
                f"  ✅ 材质: {parsed.material_code}  "
                f"|  颜色: {parsed.color_code}  "
                f"|  尺寸: {parsed.model_code}  "
                f"|  花型: {parsed.picture_code}"
            )
            print(summary)
            
            for gift_name, gift_num in all_gifts:
                print(f"  🎁 赠品: {gift_name} x {gift_num}")
        
        if self.dry_run:
            if all_parsed_list:
                for parsed in all_parsed_list:
                    print(f"  🔶 DRY RUN: 新编码 = {parsed.shop_mapping_sku}")
            for update in price_diff_updates:
                action = "修改编码为'定制-定制-补差价-不打印'" if not update['ship'] else "仅修改数量为1"
                print(f"  🔶 DRY RUN: 补差价订单 {update['tid'][:16]}... -> {action}")
            for tid in gift_no_ship_tids:
                print(f"  🔶 DRY RUN: 赠品不发货 {tid[:16]}... -> 修改赠品行编码为'定制-定制-补差价-不打印'")
            self.stats["success"] += 1
            return
        
        if self.confirm_callback and (all_parsed_list or gift_no_ship_tids):
            changes = []
            for p in all_parsed_list:
                changes.append(f"新编码: {p.shop_mapping_sku}")
            for gift_name, gift_num in all_gifts:
                changes.append(f"赠品: {gift_name} x {gift_num}")
            for update in price_diff_updates:
                action = "修改编码为'定制-定制-补差价-不打印'" if not update['ship'] else "仅修改数量为1"
                changes.append(f"补差价订单: {action}")
            for tid in gift_no_ship_tids:
                changes.append(f"赠品不发货: 修改赠品行编码为'定制-定制-补差价-不打印'")
            
            should_update = self.confirm_callback(order, all_parsed_list, changes)
            if not should_update:
                print(f"  ⏭️  用户取消（未修改）")
                self.stats["cancelled"] += 1
                return
        
        try:
            if all_parsed_list or price_diff_updates or gift_no_ship_tids:
                ok = self.adapter.update_merchant_code(order, 
                    all_parsed_list[0] if all_parsed_list else None, 
                    all_parsed_list,
                    price_diff_updates,
                    gift_no_ship_tids=gift_no_ship_tids,
                )
                if ok is None:
                    print(f"  ⏭️  跳过：订单所有商品行已作废")
                    self.stats["skipped"] += 1
                elif ok:
                    if all_parsed_list:
                        print(f"  ✅ 修改成功！共 {len(all_parsed_list)} 个编码")
                    if price_diff_updates:
                        print(f"  ✅ 补差价订单修改成功！")
                    if gift_no_ship_tids:
                        print(f"  ✅ 赠品不发货修改成功！")
                    self.stats["success"] += 1
                else:
                    print(f"  ❌ 修改失败")
                    self.stats["failed"] += 1
                    self.stats["errors"].append(f"订单 {order.trade_id}: 接口返回失败")
            else:
                print(f"  ⏭️  跳过：所有分组均无法解析")
                self.stats["skipped"] += 1
        except Exception as e:
            print(f"  ❌ 请求异常: {e}")
            self.stats["failed"] += 1
            self.stats["errors"].append(f"订单 {order.trade_id}: {e}")

    def _update_express_for_order(self, order):
        """
        根据备注关键词或省份规则，自动更新订单快递信息
        优先级：备注关键词 > 省份规则
        """
        from express_config import get_express_by_remark, get_express_for_province, get_express_code

        remark = order.shop_remark or ""
        province = order.receiver_province or ""

        # 1. 优先检测备注关键词
        express_name = get_express_by_remark(remark)
        match_source = "备注关键词"

        # 2. 如果没有匹配到关键词，使用省份规则
        if not express_name and province:
            express_name = get_express_for_province(province)
            match_source = f"省份规则({province})"

        if not express_name:
            return

        express_code = get_express_code(express_name)
        if not express_code:
            print(f"  ⚠️  快递编码未找到: {express_name}")
            return

        if self.dry_run:
            print(f"  🔶 DRY RUN: 将更新快递为 {express_name}({express_code})，来源: {match_source}")
            return

        # 检查适配器是否支持更新快递
        if not hasattr(self.adapter, 'update_express'):
            return

        try:
            ok = self.adapter.update_express(order, express_code)
            if ok:
                print(f"  ✅ 快递已更新: {express_name}({express_code})，来源: {match_source}")
            # 失败日志由 adapter.update_express 内部打印
        except Exception as e:
            print(f"  ❌ 快递更新异常: {e}")

    def _print_summary(self):
        print("\n" + "=" * 60)
        print("📊 处理汇总")
        print("=" * 60)
        print(f"  总处理:  {self.stats['total']}")
        print(f"  ✅ 成功:  {self.stats['success']}")
        print(f"  ⏭️  跳过:  {self.stats['skipped']}")
        if self.stats.get("cancelled", 0):
            print(f"  🔶 用户取消: {self.stats['cancelled']}")
        print(f"  ❌ 失败:  {self.stats['failed']}")
        if self.stats["errors"]:
            print(f"\n  ⚠️  错误明细 ({len(self.stats['errors'])}):")
            for err in self.stats["errors"][:10]:
                print(f"    • {err}")
            if len(self.stats["errors"]) > 10:
                print(f"    ... 还有 {len(self.stats['errors']) - 10} 个错误")
        print("=" * 60)