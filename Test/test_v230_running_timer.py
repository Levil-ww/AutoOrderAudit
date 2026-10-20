"""计时生命周期回归：不创建 Tk 窗口，不访问用户配置或 ERP。"""

import builtins
import io
import queue
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
        raise AssertionError("禁止真实 ERP 请求")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    import auth_manager
    monkeypatch.setattr(auth_manager, "load_auth", lambda: auth_manager.AuthInfo())
    import gui
    from core.adaptive_poller import AdaptivePoller

    app = gui.AutoAuditGUI.__new__(gui.AutoAuditGUI)
    state = SimpleNamespace(app=app, gui=gui, now=100.0, jobs={}, next_job=0, workers=[])
    main_thread = threading.get_ident()

    def after(delay: int, callback: Any) -> str:
        state.next_job += 1
        job = f"job-{state.next_job}"
        state.jobs[job] = (delay, callback)
        return job

    def configure(**kwargs) -> None:
        assert threading.get_ident() == main_thread, "子线程不能操作 Tk 控件"

    app.root = SimpleNamespace(after=after, after_cancel=lambda job: state.jobs.pop(job, None))
    app.running_time_label = Mock()
    app.running_time_label.config.side_effect = configure
    for name in ("start_btn", "push_btn", "monitor_btn", "progress", "log_text"):
        setattr(app, name, Mock())
    app._running_start_time = None
    app._running_timer_job = None
    app._running_elapsed = 0
    app._running = False
    app._monitoring = False
    app._monitor_paused = False
    app._monitor_thread = None
    app._monitor_poll_interval = 60
    app._monitor_audit_count = 0
    app._monitor_push_count = 0
    app._batch_confirm_decision = None
    app._adaptive_poller = AdaptivePoller()
    app._log_queue = queue.Queue()
    monkeypatch.setattr(gui.time, "time", lambda: state.now)
    monkeypatch.setattr(gui.time, "monotonic", lambda: state.now)
    monkeypatch.setattr(gui, "load_auth", lambda: SimpleNamespace(
        authorization="fixture", is_valid=True, username="fixture"))
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args: True)
    return state


def text(runtime: SimpleNamespace) -> str:
    return runtime.app.running_time_label.config.call_args.kwargs["text"]


def drain_finishes(runtime: SimpleNamespace) -> None:
    """仅执行投递到主线程的收尾，不自动推进每秒刷新。"""
    for job, (delay, callback) in list(runtime.jobs.items()):
        if delay == 0:
            runtime.jobs.pop(job)
            callback()


def refresh(runtime: SimpleNamespace) -> None:
    """模拟 Tk 执行一次已注册的每秒刷新。"""
    _, callback = runtime.jobs.pop(runtime.app._running_timer_job)
    callback()


def defer_workers(runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """仅替换线程启动边界，真实开始/结束入口仍执行。"""
    monkeypatch.setattr(runtime.gui.threading, "Thread", lambda target, **kwargs:
                        SimpleNamespace(start=lambda: runtime.workers.append(target)))


@pytest.mark.parametrize("kind", ["audit", "push"])
def test_manual_task_keeps_final_time_and_next_task_resets(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    defer_workers(runtime, monkeypatch)
    app = runtime.app
    getattr(app, f"_start_{kind}")()
    assert app._running
    assert len(runtime.workers) == 1
    runtime.now += 65.9
    getattr(app, f"_finish_{kind}")()
    assert text(runtime) == "已运行 01:05"
    assert not app._running
    assert runtime.jobs == {}
    runtime.now += 100
    getattr(app, f"_start_{kind}")()
    assert text(runtime) == "已运行 00:00"
    assert len(runtime.jobs) == 1


def test_monitor_pause_resume_excludes_pause_and_preserves_fractions(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    defer_workers(runtime, monkeypatch)
    app = runtime.app
    app._start_monitor()
    runtime.now += 10.6
    app._pause_monitor()
    assert text(runtime) == "已运行 00:10"
    assert runtime.jobs == {}
    runtime.now += 100
    app._resume_monitor()
    runtime.now += 0.6
    app._stop_monitor()
    assert text(runtime) == "已运行 00:11"
    assert runtime.jobs == {}


def test_clear_log_does_not_stop_or_reset_timer(runtime: SimpleNamespace) -> None:
    app = runtime.app
    app._start_running_timer()
    runtime.now += 12
    app._clear_log()
    runtime.now += 5
    refresh(runtime)
    assert text(runtime) == "已运行 00:17"
    assert app._running_start_time is not None
    app.log_text.delete.assert_called_once()


def test_timer_ignores_system_clock_changes(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = runtime.app
    app._start_running_timer()
    runtime.now += 15
    monkeypatch.setattr(runtime.gui.time, "time", lambda: -999999.0)
    app._stop_running_timer()
    assert text(runtime) == "已运行 00:15"


@pytest.mark.parametrize("kind", ["audit", "push"])
@pytest.mark.parametrize("paused", [False, True])
def test_manual_task_inside_monitor_keeps_session_time(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str, paused: bool,
) -> None:
    defer_workers(runtime, monkeypatch)
    app = runtime.app
    app._start_monitor()
    runtime.now += 20
    if paused:
        app._pause_monitor()
        runtime.now += 100
    getattr(app, f"_start_{kind}")()
    runtime.now += 5
    getattr(app, f"_finish_{kind}")()
    if not paused:
        refresh(runtime)
    assert text(runtime) == "已运行 00:25"
    assert app._monitoring
    assert app._monitor_paused == paused
    assert len(runtime.jobs) == (0 if paused else 1)


@pytest.mark.parametrize("worker", ["_run_monitor_audit", "_run_monitor_push_only"])
def test_stop_monitor_waits_for_worker_exception_cleanup(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, worker: str,
) -> None:
    import adapters.fangguo

    app = runtime.app
    app._monitoring = True
    app._running = True
    app._start_running_timer()
    runtime.now += 10
    app._stop_monitor()
    assert app._running_start_time is not None, "后台尚未收尾，不应提前停止计时"

    def fail_adapter() -> None:
        runtime.now += 5
        raise RuntimeError("模拟初始化失败")

    monkeypatch.setattr(adapters.fangguo, "FangguoAdapter", fail_adapter)
    errors = []

    def run() -> None:
        try:
            getattr(app, worker)()
        except RuntimeError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    drain_finishes(runtime)
    assert not app._running
    assert text(runtime) == "已运行 00:15"
    assert runtime.jobs == {}
    assert errors == (["模拟初始化失败"] if worker.endswith("push_only") else [])


def test_repeated_start_has_one_refresh_job(runtime: SimpleNamespace) -> None:
    app = runtime.app
    app._start_running_timer()
    runtime.now += 3
    app._start_running_timer()
    assert text(runtime) == "已运行 00:00"
    assert len(runtime.jobs) == 1


@pytest.mark.parametrize("worker", ["_run_audit", "_run_push"])
def test_manual_worker_exception_finishes_timer_on_main_thread(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, worker: str,
) -> None:
    import adapters.fangguo
    import adapters.fangguo.adapter

    app = runtime.app
    app._running = True
    app._start_running_timer()

    def fail_adapter() -> None:
        runtime.now += 7
        raise RuntimeError("模拟初始化失败")

    monkeypatch.setattr(adapters.fangguo, "FangguoAdapter", fail_adapter)
    monkeypatch.setattr(adapters.fangguo.adapter, "FangguoAdapter", fail_adapter)
    thread = threading.Thread(target=getattr(app, worker))
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    drain_finishes(runtime)
    assert not app._running
    assert text(runtime) == "已运行 00:07"
    assert runtime.jobs == {}


def test_monitor_round_completion_does_not_reset_session_timer(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = runtime.app
    app._monitoring = True
    app._running = True
    app._start_running_timer()
    runtime.now += 20

    def finish_audit(**kwargs) -> None:
        runtime.now += 5

    monkeypatch.setattr(app, "_run_audit", finish_audit)
    thread = threading.Thread(target=app._run_monitor_audit)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    drain_finishes(runtime)
    refresh(runtime)
    assert text(runtime) == "已运行 00:25"
    assert app._monitoring and not app._running
    assert len(runtime.jobs) == 1
