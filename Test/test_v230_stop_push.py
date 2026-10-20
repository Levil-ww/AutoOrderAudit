"""监控停止回归：使用真实调度流程和虚构订单，禁止配置访问及网络请求。"""

import builtins
import importlib
import io
import sys
import threading
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
import requests

from core.adapter_base import ErpAdapter, Order, OrderItem
from core.engine import AutoAuditEngine


class StopPushAdapter(ErpAdapter):
    """记录引擎的提交边界，并在指定阶段触发停止。"""

    material_map = {"双面革": "双面格"}

    def __init__(self, status: int = 1) -> None:
        self.status = status
        self.orders = [Order(
            trade_id="stop-fixture", tid="stop-fixture",
            shop_remark="定制双面革蔓生花;80x150cm-1张",
            receiver_province="浙江", current_cp_code="ZTO",
            raw={"payTime": "2020-01-01 00:00:00"},
            items=[OrderItem(
                id="main", title="桌垫",
                shop_mapping_sku="双面格-定制-定制尺寸-蔓生花;80x150CM",
            )],
        )]
        self.queries: list[int] = []
        self.express_updates: list[str] = []
        self.pushed: list[str] = []
        self.on_query = lambda status: None
        self.on_audit = lambda: None
        self.on_express = lambda: None
        self.on_push = lambda: None

    def query_orders(self, **kwargs) -> list[Order]:
        status = kwargs["query_status"]
        self.queries.append(status)
        self.on_query(status)
        return self.orders if status == self.status else []

    def update_merchant_code(self, *args, **kwargs) -> bool:
        self.on_audit()
        return True

    def get_material_matcher(self) -> None:
        return None

    def update_express(self, order: Order, cp_code: str) -> bool:
        self.express_updates.append(order.trade_id)
        self.on_express()
        return True

    def push_orders(self, trade_ids: list[str]) -> dict:
        self.pushed.extend(trade_ids)
        self.on_push()
        return {"code": 0, "data": True}


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """在导入 GUI 和实例化引擎之前阻断用户配置及 ERP。"""
    protected = {"token.json", "last_username.json", "express_config.json", "gift_config.json"}
    for module in (builtins, io):
        original_open = module.open

        def guarded_open(file, *args, _open=original_open, **kwargs) -> Any:
            name = str(file).replace("\\", "/").rsplit("/", 1)[-1]
            assert name not in protected, "禁止访问用户配置"
            return _open(file, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded_open)

    def no_network(*args, **kwargs) -> None:
        raise AssertionError("禁止发送真实 ERP 请求")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    manager = SimpleNamespace(
        resolve_express=lambda *args, **kwargs: ("极兔", "JT"),
        keyword_map={}, store_map={}, platform_map={},
    )
    monkeypatch.setattr("core.engine.get_express_manager", lambda: manager)
    monkeypatch.setattr("core.engine.time.sleep", lambda seconds: None)
    monkeypatch.setattr(AutoAuditEngine, "_verify_push_result", Mock())

    config = ModuleType("adapters.fangguo.config")
    config.QUERY_STATUS_PENDING_PUSH = 2
    config.QUERY_STATUS = 1
    config.PAGE_SIZE = 500
    config.DRY_RUN = False
    config.MAX_ORDERS = 0
    config.get_time_begin = lambda: "2020-01-01 00:00:00"
    config.get_time_end = lambda: "2030-01-01 23:59:59"
    config.get_time_range_display = lambda: "隔离测试"
    package = ModuleType("adapters.fangguo")
    package.FangguoAdapter = StopPushAdapter
    package.config = config
    monkeypatch.setitem(sys.modules, "adapters.fangguo", package)
    monkeypatch.setitem(sys.modules, "adapters.fangguo.config", config)
    return package


def make_gui(monkeypatch: pytest.MonkeyPatch, package: ModuleType,
             adapter: StopPushAdapter) -> Any:
    """调用真实 GUI 方法，但不创建 Tk 窗口或启动后台线程。"""
    gui = importlib.import_module("gui")
    monkeypatch.setattr(package, "FangguoAdapter", lambda: adapter)
    app = gui.AutoAuditGUI.__new__(gui.AutoAuditGUI)
    app._monitoring = True
    app._monitor_paused = False
    app._monitor_thread = None
    app._monitor_audit_count = 0
    app._running = True
    app._batch_confirm_decision = None
    app._set_monitor_btn_state = Mock()
    app._confirm_update = Mock(return_value=True)
    app.start_btn = Mock()
    app.progress = Mock()
    app.root = Mock()
    return app


def test_monitor_stopped_during_audit_never_enters_push(monkeypatch, isolated_runtime) -> None:
    adapter = StopPushAdapter()
    app = make_gui(monkeypatch, isolated_runtime, adapter)
    adapter.on_audit = app._stop_monitor

    app._run_audit(monitor_mode=True)

    assert adapter.queries == [1]
    assert adapter.pushed == []


def test_monitor_running_still_audits_then_pushes(monkeypatch, isolated_runtime) -> None:
    adapter = StopPushAdapter()
    app = make_gui(monkeypatch, isolated_runtime, adapter)

    app._run_audit(monitor_mode=True)

    assert adapter.queries == [1, 2, 1]
    assert adapter.pushed == ["stop-fixture"]
    app._confirm_update.assert_not_called()


def test_manual_audit_still_does_not_auto_push(monkeypatch, isolated_runtime) -> None:
    adapter = StopPushAdapter()
    app = make_gui(monkeypatch, isolated_runtime, adapter)
    app._monitoring = False

    app._run_audit(monitor_mode=False)

    assert adapter.queries == [1]
    assert adapter.pushed == []
    app._confirm_update.assert_called_once()
    app.root.after.assert_called_once()


def test_audit_timeout_does_not_become_push_timeout(monkeypatch, isolated_runtime) -> None:
    """原有十分钟上限只终止审单，监控未停止时仍保留后续推单。"""
    adapter = StopPushAdapter()
    app = make_gui(monkeypatch, isolated_runtime, adapter)
    clock = iter([0, 601])
    monkeypatch.setattr("time.time", lambda: next(clock, 601))

    app._run_audit(monitor_mode=True)

    assert adapter.pushed == ["stop-fixture"]


def test_push_already_stopped_does_not_query() -> None:
    adapter = StopPushAdapter()
    engine = AutoAuditEngine(adapter, should_stop=lambda: True)

    engine.push_eligible_orders()

    assert adapter.queries == []
    assert adapter.express_updates == []
    assert adapter.pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_stop_during_candidate_query_prevents_express_and_push(status: int) -> None:
    stopped = threading.Event()
    adapter = StopPushAdapter(status)
    adapter.on_query = lambda queried: stopped.set() if queried == status else None
    engine = AutoAuditEngine(adapter, should_stop=stopped.is_set)

    engine.push_eligible_orders()

    assert adapter.queries == ([2] if status == 2 else [2, 1])
    assert adapter.express_updates == []
    assert adapter.pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_stop_during_eligibility_check_prevents_express_and_push(status: int, monkeypatch) -> None:
    stopped = threading.Event()
    adapter = StopPushAdapter(status)
    engine = AutoAuditEngine(adapter, should_stop=stopped.is_set)
    check = engine._get_push_skip_reason

    def stop_after_check(*args, **kwargs) -> str:
        reason = check(*args, **kwargs)
        stopped.set()
        return reason

    monkeypatch.setattr(engine, "_get_push_skip_reason", stop_after_check)

    engine.push_eligible_orders()

    assert adapter.express_updates == []
    assert adapter.pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_stop_during_express_does_not_process_next_order_or_push(status: int) -> None:
    stopped = threading.Event()
    adapter = StopPushAdapter(status)
    adapter.orders.append(Order(trade_id="second-fixture"))
    adapter.on_express = stopped.set
    engine = AutoAuditEngine(adapter, should_stop=stopped.is_set)

    engine.push_eligible_orders()

    assert adapter.express_updates == ["stop-fixture"]
    assert adapter.queries == ([2] if status == 2 else [2, 1])
    assert adapter.pushed == []


def test_stop_after_collecting_candidates_discards_pending_batch() -> None:
    stopped = threading.Event()
    adapter = StopPushAdapter(2)
    adapter.on_query = lambda status: stopped.set() if status == 1 else None
    engine = AutoAuditEngine(adapter, should_stop=stopped.is_set)

    engine.push_eligible_orders()

    assert adapter.express_updates == ["stop-fixture"]
    assert adapter.pushed == []


def test_stop_after_push_sent_keeps_result_verification() -> None:
    """已发出的推送不能撤回，仍执行原有只读结果核验。"""
    stopped = threading.Event()
    adapter = StopPushAdapter()
    adapter.on_push = stopped.set
    engine = AutoAuditEngine(adapter, should_stop=stopped.is_set)

    engine.push_eligible_orders()

    assert adapter.pushed == ["stop-fixture"]
    engine._verify_push_result.assert_called_once_with(["stop-fixture"])


@pytest.mark.parametrize("order_count", [70, 570])
def test_monitor_tracks_all_pending_orders_before_auditing(
    monkeypatch: pytest.MonkeyPatch, isolated_runtime: ModuleType, order_count: int,
) -> None:
    """超过十单及跨页时全部参与就绪判断，第二轮新出现的订单仍须等待。"""
    from core.adaptive_poller import AdaptivePoller

    class PagedAdapter(StopPushAdapter):
        def query_orders(self, page_no: int = 1, page_size: int = 500,
                         query_status: int = 1, **kwargs: Any) -> list[Order]:
            if query_status != 1:
                return []
            start = (page_no - 1) * page_size
            return self.orders[start:start + page_size]

        def query_all_orders(self, page_size: int = 500, query_status: int = 1,
                             **kwargs: Any) -> list[Order]:
            orders = []
            page_no = 1
            while True:
                page = self.query_orders(page_no, page_size, query_status, **kwargs)
                orders.extend(page)
                if len(page) < page_size:
                    return orders
                page_no += 1

    adapter = PagedAdapter()
    adapter.orders = [Order(trade_id=f"monitor-{i}") for i in range(order_count)]
    app = make_gui(monkeypatch, isolated_runtime, adapter)
    app._running = False
    app._adaptive_poller = AdaptivePoller()
    clock = [1000.0]
    scheduled: list[set[str]] = []
    first_poll_ready: list[set[str]] = []

    def sleep_monitor(seconds: float) -> None:
        first_poll_ready.append(app._adaptive_poller.get_ready_order_ids())
        clock[0] += seconds
        if len(first_poll_ready) == 1:
            adapter.orders.append(Order(trade_id="new-arrival"))
        # 防止回归时死循环；正常第二轮即启动处理。
        if len(first_poll_ready) >= 4:
            app._monitoring = False

    def record_audit(ready_ids: set[str]) -> None:
        scheduled.append(ready_ids)
        app._monitoring = False

    gui = importlib.import_module("gui")
    monkeypatch.setattr(gui, "load_auth", lambda: SimpleNamespace(is_valid=True))
    monkeypatch.setattr("core.adaptive_poller.time.time", lambda: clock[0])
    monkeypatch.setattr(gui.threading, "Thread", lambda target, args=(), **kwargs:
                        SimpleNamespace(start=lambda: target(*args)))
    monkeypatch.setattr(app, "_sleep_monitor", sleep_monitor)
    monkeypatch.setattr(app, "_run_monitor_audit", record_audit)

    app._monitor_loop()

    assert first_poll_ready[0] == set(), "首次发现不能直接审单"
    assert len(scheduled) == 1
    assert scheduled[0] == {f"monitor-{i}" for i in range(order_count)}
    assert "new-arrival" not in scheduled[0], "新订单未等待满30秒不能进入审单"
