"""固定轮询业务边界，并用受控交错复现跨线程重置竞争。"""

from collections.abc import Iterator
import threading
from typing import Any

import pytest

from core import adaptive_poller
from core.adaptive_poller import AdaptivePoller


def test_readiness_requires_second_sighting_and_wait_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(adaptive_poller.time, "time", lambda: now[0])
    poller = AdaptivePoller(new_order_wait=30)
    poller.record_poll_result({"A"})
    now[0] = 1029.0
    poller.record_poll_result({"A"})
    assert poller.get_ready_order_ids() == set()
    assert poller.should_process_now() is False
    assert poller.get_wait_interval() == 30
    now[0] = 1030.0
    assert poller.get_ready_order_ids() == {"A"}
    assert poller.should_process_now() is True
    poller.record_poll_result({"A", "B"})
    assert poller.get_ready_order_ids() == {"A"}
    assert poller.get_wait_interval() == 30
    poller.record_poll_result({"B"})
    assert poller.get_ready_order_ids() == set()
    now[0] = 1060.0
    assert poller.get_ready_order_ids() == {"B"}


def test_first_sighting_stays_unready_even_after_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(adaptive_poller.time, "time", lambda: now[0])
    poller = AdaptivePoller()
    poller.record_poll_result({"A"})
    now[0] = 2000.0
    assert poller.get_ready_order_ids() == set()
    assert poller.should_process_now() is False
    assert poller.get_wait_interval() == 30


def test_stable_extension_cap_and_count_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adaptive_poller.time, "time", lambda: 1000.0)
    poller = AdaptivePoller(new_order_wait=0)
    poller.record_poll_result({"A"})
    for expected in [90, 135, 202.5, 300, 300]:
        poller.record_poll_result({"A"})
        assert poller.get_wait_interval() == expected
        assert poller.get_current_interval() == expected
    poller.record_poll_result(set())
    assert poller.get_wait_interval() == 60
    assert poller.should_process_now() is False
    assert poller.get_order_status_summary() == "无待处理订单"


def test_error_backoff_cap_success_and_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adaptive_poller.time, "time", lambda: 1000.0)
    poller = AdaptivePoller()
    for expected in [120, 180, 180, 180, 180, 180]:
        poller.record_error()
        assert poller.get_wait_interval() == expected
    poller.record_poll_result({"A"})
    assert poller.get_wait_interval() == 30
    poller.record_error()
    poller.reset()
    assert poller.get_wait_interval() == 60
    assert poller.get_current_interval() == 60
    assert poller.get_ready_order_ids() == set()


class PausingOrders(dict):
    """在真实字典遍历/查找中暂停，扩大原有竞争窗口而不改变返回值。"""

    def __init__(self, orders: dict, entered: threading.Event, release: threading.Event, operation: str) -> None:
        super().__init__(orders)
        self.entered = entered
        self.release = release
        self.operation = operation

    def _pause(self) -> None:
        self.entered.set()
        if not self.release.wait(5):
            raise TimeoutError("测试未释放轮询操作")

    def values(self) -> Iterator[Any]:
        iterator = iter(super().values())
        first = next(iterator)
        self._pause()
        yield first
        yield from iterator

    def items(self) -> Iterator[Any]:
        iterator = iter(super().items())
        first = next(iterator)
        self._pause()
        yield first
        yield from iterator

    def __contains__(self, key: object) -> bool:
        result = super().__contains__(key)
        if self.operation == "record_poll_result":
            self._pause()
        return result


@pytest.mark.parametrize("operation", [
    "record_poll_result", "get_wait_interval", "get_order_status_summary",
    "should_process_now", "get_ready_order_ids",
])
def test_reset_cannot_interrupt_inflight_state_operation(
    monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    monkeypatch.setattr(adaptive_poller.time, "time", lambda: 1000.0)
    poller = AdaptivePoller(new_order_wait=0)
    poller.record_poll_result({"A"})
    poller.record_poll_result({"A"})
    entered, release = threading.Event(), threading.Event()
    reset_started, reset_done = threading.Event(), threading.Event()
    poller._known_orders = PausingOrders(poller._known_orders, entered, release, operation)
    results, errors = [], []

    def operate() -> None:
        try:
            method = getattr(poller, operation)
            results.append(method({"A"}) if operation == "record_poll_result" else method())
        except BaseException as exc:
            errors.append(exc)

    def reset() -> None:
        reset_started.set()
        try:
            poller.reset()
        except BaseException as exc:
            errors.append(exc)
        finally:
            reset_done.set()

    worker = threading.Thread(target=operate, daemon=True)
    resetter = threading.Thread(target=reset, daemon=True)
    worker.start()
    try:
        assert entered.wait(5), "未进入受控竞争窗口"
        resetter.start()
        assert reset_started.wait(5)
        assert not reset_done.wait(0.1), "reset 在状态操作尚未结束时清空了状态"
    finally:
        release.set()
        worker.join(5)
        if resetter.ident is not None:
            resetter.join(5)
    assert not worker.is_alive() and not resetter.is_alive(), "轮询器发生死锁"
    assert errors == []
    expected = {
        "record_poll_result": None, "get_wait_interval": 90.0,
        "get_order_status_summary": "1笔待处理订单（全部就绪，连续1次稳定）",
        "should_process_now": True, "get_ready_order_ids": {"A"},
    }
    assert results == [expected[operation]]
    assert poller.get_order_status_summary() == "无待处理订单"
    assert poller.get_ready_order_ids() == set()
    assert poller.get_wait_interval() == 60
