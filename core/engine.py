"""
核心 - 自动审单引擎
通用的自动审单流程，通过 ErpAdapter 接口与具体 ERP 解耦。
"""

import time
from datetime import datetime
from typing import Callable, Optional

from .adapter_base import ErpAdapter
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
    "差价",
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
            except Exception as e:
                self.stats["failed"] += 1
                self.stats["errors"].append(str(e))
                print(f"  ❌ 订单处理异常: {e}")

            time.sleep(self.interval)

        self._print_summary()

    def _process_order(self, order):
        remark = order.shop_remark or ""
        print(f"  卖家备注: {remark[:60]}..." if len(remark) > 60 else f"  卖家备注: {remark}")

        if not remark.strip():
            print("  ⏭️  跳过：卖家备注为空")
            self.stats["skipped"] += 1
            return

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
            print(f"  ⏭️  跳过：无法解析备注")
            self.stats["skipped"] += 1
            return

        parsed = parsed_list[0]
        summary = (
            f"  ✅ 材质: {parsed.material_code}  "
            f"|  颜色: {parsed.color_code}  "
            f"|  尺寸: {parsed.model_code}  "
            f"|  花型: {parsed.picture_code}"
        )
        print(summary)

        # 检查赠品信息
        gift_name = ""
        gift_num = 0
        for p in parsed_list:
            if p.gift_name:
                gift_name = p.gift_name
                gift_num = p.gift_num
                break
        if gift_name:
            print(f"  🎁 赠品: {gift_name} x {gift_num}")

        if self.dry_run:
            print()
            for parsed in parsed_list:
                print(f"  🔶 DRY RUN: 新编码 = {parsed.shop_mapping_sku}")
            if gift_name:
                print(f"  🔶 DRY RUN: 将添加赠品商品行 = {gift_name} x {gift_num}")
            self.stats["success"] += 1
            return

        # ===== 确认弹窗：在调用 API 之前征求用户意见 =====
        if self.confirm_callback:
            changes = []
            for p in parsed_list:
                changes.append(f"新编码: {p.shop_mapping_sku}")
            if gift_name:
                changes.append(f"赠品: {gift_name} x {gift_num}")

            should_update = self.confirm_callback(order, parsed_list, changes)
            if not should_update:
                print(f"  ⏭️  用户取消：新编码 {parsed_list[0].shop_mapping_sku}（未修改）")
                self.stats["cancelled"] += 1
                return

        # ===== 执行实际的 API 修改 =====
        try:
            ok = self.adapter.update_merchant_code(order, parsed_list[0], parsed_list)
            if ok:
                print(f"  ✅ 修改成功！新编码: {parsed_list[0].shop_mapping_sku}")
                if len(parsed_list) > 1:
                    print(f"  📦 包含 {len(parsed_list)} 个尺寸，已拆分处理")
                self.stats["success"] += 1
            else:
                print(f"  ❌ 修改失败")
                self.stats["failed"] += 1
                self.stats["errors"].append(f"订单 {order.trade_id}: 接口返回失败")
        except Exception as e:
            print(f"  ❌ 请求异常: {e}")
            self.stats["failed"] += 1
            self.stats["errors"].append(f"订单 {order.trade_id}: {e}")

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