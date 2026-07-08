"""
核心 - 自动审单引擎
通用的自动审单流程，通过 ErpAdapter 接口与具体 ERP 解耦。
"""

import time
from datetime import datetime

from .adapter_base import ErpAdapter
from .parser import parse_remark, extract_multiple_remarks


_SKIP_KEYWORDS = [
    "待定",
    "待确定",
    # "待确认",
    "等通知发",
    "需要效果图",
    "效果图",
    "确认再生产",
    "号发货",
    "号安排发货",
    "号在安排发货",
    "已代益",
    "已代森",
    "仓库发",
    "工厂发",
    "补发"
]


class AutoAuditEngine:
    """自动审单引擎"""

    def __init__(
        self,
        adapter: ErpAdapter,
        dry_run: bool = False,
        max_orders: int = 0,
        interval: float = 0.5,
    ):
        self.adapter = adapter
        self.dry_run = dry_run
        self.max_orders = max_orders
        self.interval = interval
        self.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": []}

    def run(self, page_no=1, page_size=500, query_status=1, time_begin="", time_end=""):
        print("=" * 60)
        print(f"自动审单引擎 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"适配器: {self.adapter.get_adapter_name()}")
        if self.dry_run:
            print("🔶 DRY RUN 模式：仅模拟，不会真实提交")
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

        if self.dry_run:
            print()
            for parsed in parsed_list:
                print(f"  🔶 DRY RUN: 新编码 = {parsed.shop_mapping_sku}")
            self.stats["success"] += 1
            return

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
        print(f"  ❌ 失败:  {self.stats['failed']}")
        if self.stats["errors"]:
            print(f"  ⚠️  错误详情:")
            for err in self.stats["errors"][:5]:
                print(f"    - {err}")