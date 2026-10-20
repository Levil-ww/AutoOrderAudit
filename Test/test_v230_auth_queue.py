"""鉴权通知线程回归：无 Tk 窗口，控件替身拒绝任何非主线程调用。"""

import builtins
import io
import queue
import sys
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
import requests


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    protected = {"token.json", "last_username.json", "express_config.json", "gift_config.json"}
    for module in (builtins, io):
        original_open = module.open

        def guarded_open(file, *args, _open=original_open, **kwargs) -> Any:
            name = str(file).replace("\\", "/").rsplit("/", 1)[-1]
            assert name not in protected, "禁止访问用户配置"
            return _open(file, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded_open)

    def no_network(*args, **kwargs) -> None:
        raise AssertionError("禁止真实登录或 ERP 请求")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    import auth_manager
    monkeypatch.setattr(auth_manager, "load_auth", lambda: auth_manager.AuthInfo())
    monkeypatch.setattr(auth_manager, "_login_callbacks", [])
    import gui

    # gui 可能在同进程的其他隔离用例中已导入，显式隔离其绑定的读取函数。
    monkeypatch.setattr(gui, "load_auth", lambda: auth_manager.AuthInfo())
    main_thread = threading.get_ident()
    calls: list[tuple[str, int]] = []

    def ui_call(name: str) -> Mock:
        def invoke(*args, **kwargs) -> str:
            calls.append((name, threading.get_ident()))
            assert threading.get_ident() == main_thread, "后台线程触碰 Tk 控件"
            return "timer"
        return Mock(side_effect=invoke)

    app = gui.AutoAuditGUI.__new__(gui.AutoAuditGUI)
    app._log_queue = queue.Queue()
    app._auth_queue = queue.Queue()
    app._log_drain_job = "timer"
    app._running = False
    app._monitoring = False
    app._running_timer_job = None
    app._running_start_time = None
    app._running_elapsed = 0.0
    app._stop_token_check = Mock()
    app.root = SimpleNamespace(after=ui_call("after"), after_cancel=ui_call("after_cancel"), destroy=ui_call("destroy"))
    app.running_time_label = SimpleNamespace(config=ui_call("running_time_label"))
    app.log_text = SimpleNamespace(insert=ui_call("insert"), see=ui_call("see"), delete=ui_call("delete"))
    for field in ("_card_token", "auth_btn", "_card_time", "_card_mode"):
        setattr(app, field, SimpleNamespace(config=ui_call(field)))
    auth_manager.register_auth_callback(app._on_auth_changed)
    return SimpleNamespace(app=app, gui=gui, auth_manager=auth_manager, calls=calls, main_thread=main_thread)


def notify_on_worker(runtime: SimpleNamespace, count: int = 1) -> None:
    def notify() -> None:
        for _ in range(count):
            runtime.auth_manager._notify_login_callbacks(runtime.auth_manager.AuthInfo(authorization="fixture"))

    worker = threading.Thread(target=notify)
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive(), "后台通知不应等待 Tk 主循环"


def test_background_notification_touches_no_tk_until_main_thread_drains(runtime) -> None:
    notify_on_worker(runtime)

    assert runtime.calls == []
    runtime.app._drain_log_queue()
    assert any(name == "_card_token" for name, _ in runtime.calls)
    assert all(thread_id == runtime.main_thread for _, thread_id in runtime.calls)


def test_main_thread_notification_also_uses_queue(runtime) -> None:
    runtime.app._on_auth_changed(runtime.auth_manager.AuthInfo())

    assert runtime.calls == []
    runtime.app._drain_log_queue()
    assert runtime.app._card_token.config.call_count == 1


def test_multiple_notifications_are_consumed_on_main_thread(runtime) -> None:
    notify_on_worker(runtime, count=3)
    assert runtime.calls == []

    runtime.app._drain_log_queue()

    assert runtime.app._card_token.config.call_count == 3
    assert all(thread_id == runtime.main_thread for _, thread_id in runtime.calls)


def test_clear_log_does_not_drop_pending_auth_notification(runtime) -> None:
    notify_on_worker(runtime)
    runtime.app._log_queue.put(("old log", "info"))

    runtime.app._clear_log()
    runtime.app._drain_log_queue()

    assert runtime.app._card_token.config.call_count == 1
    runtime.app.log_text.insert.assert_not_called()
    assert all(thread_id == runtime.main_thread for _, thread_id in runtime.calls)


def test_log_rendering_and_existing_timer_are_unchanged(runtime) -> None:
    runtime.app._log_queue.put(("fixture log", "info"))

    runtime.app._drain_log_queue()

    runtime.app.log_text.insert.assert_called_once_with(runtime.gui.tk.END, "fixture log", "info")
    runtime.app.root.after.assert_called_once_with(100, runtime.app._drain_log_queue)
    runtime.app._card_token.config.assert_not_called()


def test_destroyed_widget_stops_auth_drain_without_rescheduling(runtime, monkeypatch) -> None:
    monkeypatch.setattr(runtime.app, "_refresh_status", Mock(side_effect=runtime.gui.tk.TclError("已销毁")))
    runtime.app._auth_queue.put(runtime.auth_manager.AuthInfo())

    runtime.app._drain_log_queue()

    runtime.app.root.after.assert_not_called()


def test_auth_refresh_error_does_not_stop_log_rendering_or_timer(runtime, monkeypatch) -> None:
    monkeypatch.setattr(runtime.app, "_refresh_status", Mock(side_effect=ValueError("模拟刷新异常")))
    runtime.app._auth_queue.put(runtime.auth_manager.AuthInfo())
    runtime.app._log_queue.put(("fixture log", "info"))

    runtime.app._drain_log_queue()

    runtime.app.log_text.insert.assert_called_once_with(runtime.gui.tk.END, "fixture log", "info")
    runtime.app.root.after.assert_called_once_with(100, runtime.app._drain_log_queue)


def test_close_cancels_existing_pump_and_late_callback_only_queues(runtime, monkeypatch) -> None:
    # 保留真实关闭流程，避免它恢复 stdout 时干扰 pytest 捕获。
    monkeypatch.setattr(sys, "__stdout__", sys.stdout)
    callback = runtime.app._on_auth_changed
    runtime.app._on_close()
    calls_after_close = list(runtime.calls)

    errors: list[Exception] = []

    def late_notify() -> None:
        try:
            callback(runtime.auth_manager.AuthInfo())
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=late_notify)
    worker.start()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert errors == []
    assert runtime.calls == calls_after_close
    runtime.app.root.after_cancel.assert_called_once_with("timer")
    assert runtime.app._log_drain_job is None
    assert runtime.auth_manager._login_callbacks == []
