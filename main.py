"""
方果ERP自动审单 - 主入口
选择适配器 → 启动引擎 → 自动审单。
"""

from core import AutoAuditEngine


def main():
    # 使用方果ERP适配器
    from adapters.fangguo import FangguoAdapter, DRY_RUN, MAX_ORDERS
    from adapters.fangguo.config import QUERY_STATUS, PAGE_SIZE, TIME_BEGIN, TIME_END

    adapter = FangguoAdapter()
    engine = AutoAuditEngine(
        adapter=adapter, dry_run=DRY_RUN,
        max_orders=MAX_ORDERS, interval=0.5,
    )
    engine.run(
        page_size=PAGE_SIZE, query_status=QUERY_STATUS,
        time_begin=TIME_BEGIN, time_end=TIME_END,
    )

    # ================================================================
    # 换系统时只改这里：
    #
    # from adapters.erp_x import ErpXAdapter
    # adapter = ErpXAdapter()
    #
    # engine = AutoAuditEngine(adapter=adapter, ...)
    # engine.run(...)
    # ================================================================


if __name__ == "__main__":
    main()