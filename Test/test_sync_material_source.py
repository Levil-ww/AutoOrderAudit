"""材质缓存、失败保留与匹配边界；只替换 HTTP 和时钟边界。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from adapters.fangguo import material_source


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, real_material_fetch) -> SimpleNamespace:
    state = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(material_source.time, "time", lambda: state.now)
    state.post = Mock()
    monkeypatch.setattr(material_source.requests, "post", state.post)
    state.source = material_source.FangguoMaterialSource()
    state.source.factory_tenant_id = 12345
    state.source.shop_tenant_id = ""
    response = Mock()
    response.json.return_value = {"code": 0, "data": {"materials": [{"code": "双面格", "name": "双面革"}]}}
    state.post.return_value = response
    return state


def test_cache_expires_at_ttl_and_force_bypasses_cache(runtime: SimpleNamespace) -> None:
    source = runtime.source
    assert source.fetch() == [{"code": "双面格", "name": "双面革"}]
    runtime.now = 1299.0
    assert source.matcher_callback("双面革") == ("双面格", "api")
    assert runtime.post.call_count == 1
    runtime.now = 1300.0
    source.fetch()
    assert runtime.post.call_count == 2
    source.fetch(force=True)
    assert runtime.post.call_count == 3


@pytest.mark.parametrize("failure", ["network", "business"])
def test_failed_refresh_preserves_last_good_materials(runtime: SimpleNamespace, failure: str) -> None:
    source = runtime.source
    source.fetch()
    runtime.now = 1300.0
    if failure == "network":
        runtime.post.side_effect = requests.Timeout("fixture timeout")
    else:
        runtime.post.return_value.json.return_value = {"code": 1, "msg": "fixture failure"}
    assert source.fetch() == [{"code": "双面格", "name": "双面革"}]
    assert source.match("双面革") == ("双面格", 1.0)
    runtime.now = 1301.0
    source.fetch()
    assert runtime.post.call_count == 2
    runtime.now = 1360.0
    source.fetch()
    assert runtime.post.call_count == 3


def test_initial_failure_retries_without_nonempty_cache(runtime: SimpleNamespace) -> None:
    runtime.post.side_effect = requests.Timeout("fixture timeout")
    assert runtime.source.fetch() == []
    assert runtime.source.matcher_callback("双面革") == (None, "")
    assert runtime.post.call_count == 1
    runtime.now = 1060.0
    runtime.source.fetch()
    assert runtime.post.call_count == 2


def test_fuzzy_match_threshold_rejects_weak_match(runtime: SimpleNamespace) -> None:
    runtime.post.return_value.json.return_value = {"code": 0, "data": {"materials": [{"code": "abc", "name": "abc"}]}}
    runtime.source.fetch()
    assert runtime.source.match("abd", min_ratio=0.6) == ("abc", pytest.approx(2 / 3))
    assert runtime.source.match("abd", min_ratio=0.7) == (None, pytest.approx(2 / 3))
    assert runtime.source.match("") == (None, 0)


def test_request_uses_current_endpoint_and_factory_context(runtime: SimpleNamespace) -> None:
    runtime.source.shop_tenant_id = "fixture-shop"
    runtime.source.fetch()
    args, kwargs = runtime.post.call_args
    assert args[0].endswith("/fgapp/warehouse/shop/encode/combobox/materialColorsNew")
    assert kwargs["json"] == {"factoryTenantId": 12345, "shopTenantId": "fixture-shop"}


def test_empty_success_is_cached(runtime: SimpleNamespace) -> None:
    runtime.post.return_value.json.return_value = {"code": 0, "data": {"materials": []}}
    runtime.source.fetch()
    runtime.now = 1299.0
    runtime.source.fetch()
    assert runtime.post.call_count == 1
    runtime.now = 1300.0
    runtime.source.fetch()
    assert runtime.post.call_count == 2


@pytest.mark.parametrize("payload", [None, [], {"code": 0, "data": {}}, {"code": 0, "data": {"materials": [None]}}, {"code": 0, "data": {"materials": "invalid"}}])
def test_malformed_response_preserves_cache(runtime: SimpleNamespace, payload: object) -> None:
    runtime.source.fetch()
    runtime.now = 1300.0
    runtime.post.return_value.json.return_value = payload
    assert runtime.source.fetch() == [{"code": "双面格", "name": "双面革"}]
    assert runtime.source.match("双面革") == ("双面格", 1.0)


def test_force_bypasses_failure_backoff(runtime: SimpleNamespace) -> None:
    runtime.post.side_effect = requests.HTTPError("fixture 404")
    runtime.source.fetch()
    runtime.source.fetch(force=True)
    assert runtime.post.call_count == 2


def test_missing_factory_skips_request(runtime: SimpleNamespace) -> None:
    runtime.source.factory_tenant_id = 0
    assert runtime.source.matcher_callback("双面革") == (None, "")
    runtime.post.assert_not_called()


def test_order_matchers_isolate_factory_and_account(runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    from adapters.fangguo.adapter import FangguoAdapter
    from core.adapter_base import Order
    from core.engine import AutoAuditEngine

    adapter = FangguoAdapter()
    monkeypatch.setattr(material_source.fg_config, "TENANT_ID", "fixture-account")
    engine = AutoAuditEngine(adapter, dry_run=True)
    order = Order(factory_id=12345)
    _, first = engine._get_material_context(order)
    assert first("双面革") == ("双面格", "api")
    _, same = engine._get_material_context(order)
    assert same("双面革") == ("双面格", "api")
    assert runtime.post.call_count == 1
    _, other = engine._get_material_context(Order(factory_id=67890))
    other("双面革")
    assert runtime.post.call_args.kwargs["json"]["factoryTenantId"] == 67890
    monkeypatch.setattr(material_source.fg_config, "TENANT_ID", "other-account")
    _, changed = engine._get_material_context(order)
    changed("双面革")
    assert runtime.post.call_count == 3
    assert runtime.post.call_args.kwargs["headers"]["tenant-id"] == "other-account"
