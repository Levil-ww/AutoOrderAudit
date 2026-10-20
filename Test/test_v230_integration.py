"""V2.3.0 功能贯通验证：仅使用虚构数据与临时配置。"""
import json
from unittest.mock import Mock

import pytest

from adapters.fangguo.adapter import FangguoAdapter
from core.adapter_base import Order, OrderItem
from core.engine import AutoAuditEngine
from core.parser import extract_multiple_remarks
from express_manager import get_manager as get_express_manager
from gift_manager import get_manager as get_gift_manager


def test_legacy_express_config_round_trip(tmp_path, monkeypatch):
    import express_manager
    path = tmp_path / "legacy.json"
    data = {"province_rules": {"江苏": "测试快递"},
            "remark_keywords": {"发测试": "测试快递"},
            "express_codes": {"测试快递": "TEST"}}
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(express_manager, "_CONFIG_FILE", path)
    manager = get_express_manager()
    assert manager.resolve_express("江苏", "") == ("测试快递", "TEST")
    assert manager.resolve_express("浙江", "") == (None, None)
    manager.set_platform_express("测试平台", "测试快递")
    manager.save()
    monkeypatch.setattr(express_manager.ExpressManager, "_instance", None)
    manager = get_express_manager()
    assert manager.resolve_express("江苏", "", platform_name="测试平台") == ("测试快递", "TEST")
    assert manager.express_codes == {"测试快递": "TEST"}
    assert manager.keyword_map == {"发测试": "测试快递"}


def test_longest_express_keyword_still_wins():
    manager = get_express_manager()
    manager.add_keyword("发中通加急", "顺丰")
    assert manager.resolve_express("江苏", "发中通加急") == ("顺丰", "SF")


def test_custom_gift_parser_and_submit_fields():
    manager = get_gift_manager()
    manager.add_gift("测试赠品", "测试赠品标题", "测试材质-标准-10x20-测试图", "goods-test", "sku-test", ["测试小礼"])
    parsed = extract_multiple_remarks("定制双面革蔓生花;80x150cm-1张，送测试小礼-2张", {"双面革": "双面格"})
    gifts = [gift for item in parsed for gift in item.gifts]
    assert any(name in {"测试小礼", "测试赠品"} and num == 2 for name, num in gifts)
    adapter = FangguoAdapter()
    item = adapter._build_gift_item(OrderItem(), Order(tid="fixture"), "双面格", "测试小礼", 2, is_new=True)
    assert item["originalGoodsId"] == "goods-test"
    assert item["originalSkuId"] == "sku-test"
    assert item["materialCode"] == "测试材质"
    assert item["num"] == 2
    assert "测试材质-标准-10x20-测试图" in item["shopMappingSku"]
    assert adapter._is_gift_item(OrderItem(shop_mapping_sku=item["shopMappingSku"]))


def test_finished_goods_prefix():
    parsed = extract_multiple_remarks("成品吸水皮革蔓生花;40x60cm-1张", {"吸水皮革": "吸水皮革"})
    assert len(parsed) == 1
    assert parsed[0].shop_mapping_sku == "吸水皮革-标准-40x60-蔓生花;40x60"


def test_query_pagination_and_duplicate_guard(monkeypatch):
    adapter = FangguoAdapter()
    query = Mock(side_effect=[[Order(trade_id="a"), Order(trade_id="b")], [Order(trade_id="c")]])
    monkeypatch.setattr(adapter, "query_orders", query)
    assert [o.trade_id for o in adapter.query_all_orders(page_size=2)] == ["a", "b", "c"]
    assert [c.kwargs["page_no"] for c in query.call_args_list] == [1, 2]
    monkeypatch.setattr(adapter, "query_orders", lambda **kwargs: [Order(trade_id="same")])
    with pytest.raises(RuntimeError, match="重复"):
        adapter.query_all_orders(page_size=1)


def test_audit_only_ready_orders_and_stop(monkeypatch):
    adapter = FangguoAdapter()
    monkeypatch.setattr(adapter, "query_all_orders", lambda **kwargs: [Order(tid="a"), Order(tid="b")])
    engine = AutoAuditEngine(adapter, interval=0)
    processed = []
    monkeypatch.setattr(engine, "_process_order", lambda order: processed.append(order.tid))
    monkeypatch.setattr(engine, "_update_express_for_order", lambda order: True)
    engine.run(allowed_order_ids={"b"})
    assert processed == ["b"]
    engine.should_stop = lambda: True
    engine.run()
    assert processed == ["b"]


def test_gui_layout_offline(monkeypatch):
    import tkinter as tk
    import gui
    from auth_manager import AuthInfo
    monkeypatch.setattr(gui, "load_auth", lambda: AuthInfo())
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"当前解释器无法初始化 Tcl/Tk: {error}")
    app = gui.AutoAuditGUI(root)
    try:
        root.update_idletasks()
        assert "V2.3.0" in root.title()
        assert app.start_btn.cget("text") == "开始审单"
        assert app.push_btn.cget("text") == "开始推单"
        assert app.monitor_btn.cget("text") == "自动监控"
        assert app.log_text.winfo_height() > 200
    finally:
        app._on_close()


def test_ready_filter_applies_before_max_orders(monkeypatch):
    adapter = FangguoAdapter()
    monkeypatch.setattr(adapter, "query_all_orders", lambda **kwargs: [Order(tid="waiting"), Order(tid="ready")])
    engine = AutoAuditEngine(adapter, max_orders=1, interval=0)
    processed = []
    monkeypatch.setattr(engine, "_process_order", lambda order: processed.append(order.tid))
    monkeypatch.setattr(engine, "_update_express_for_order", lambda order: True)
    engine.run(allowed_order_ids={"ready"})
    assert processed == ["ready"]


def test_push_api_payload_and_no_empty_submit(monkeypatch):
    adapter = FangguoAdapter()
    response = Mock()
    response.json.return_value = {"code": 0, "data": True}
    post = Mock(return_value=response)
    monkeypatch.setattr(adapter._session, "post", post)
    assert adapter.push_orders([])["code"] != 0
    post.assert_not_called()
    assert adapter.push_orders(["fixture"])["code"] == 0
    payload = post.call_args.kwargs["json"]
    assert payload["tradeIdList"] == ["fixture"]
    assert payload["pushCheckDecodeBool"] is True


def test_store_platform_field_is_available_without_network():
    order = FangguoAdapter()._to_order({"tradeId": "fixture", "storeName": "测试店铺", "platformName": "测试平台"})
    assert order.platform_name == "测试平台"


@pytest.mark.parametrize("prefix", ["正常发", "特定"])
def test_keep_main_code_and_add_gift(prefix, monkeypatch):
    adapter = FangguoAdapter()
    remark = prefix + "，送圆垫-2张"
    order = Order(trade_id="fixture", tid="fixture", shop_remark=remark,
                  items=[OrderItem(id="main", oid="fixture", original_goods_id="goods-main",
                                   title="测试主商品", shop_mapping_sku="材质-标准-原规格-原图", num=3)])
    response = Mock()
    response.json.return_value = {"code": 0, "data": True}
    post = Mock(return_value=response)
    monkeypatch.setattr(adapter._session, "post", post)
    engine = AutoAuditEngine(adapter, interval=0)
    engine._process_order(order)
    assert engine.stats["success"] == 1
    payload = post.call_args.kwargs["json"]
    main = next(item for item in payload["orderItems"] if item.get("id") == "main")
    assert main["shopMappingSku"] == "材质-标准-原规格-原图"
    assert main["num"] == 3
    assert any(item["num"] == 2 and "赠品" in item["title"] for item in payload["orderItems"])


def test_merged_keep_main_code_gifts_stay_with_child(monkeypatch):
    adapter = FangguoAdapter()
    order = Order(trade_id="fixture-a&fixture-b", tid="fixture-a&fixture-b", items=[
        OrderItem(id="main-a", oid="fixture-a", original_tid="fixture-a",
                  original_goods_id="goods-a", title="测试商品A",
                  shop_mapping_sku="材质-标准-原规格-原图A", num=3, shop_remark="正常发，送圆垫-2张"),
        OrderItem(id="main-b", oid="fixture-b", original_tid="fixture-b",
                  original_goods_id="goods-b", title="测试商品B",
                  shop_mapping_sku="材质-标准-原规格-原图B", num=4, shop_remark="正常发，送方垫-1张"),
    ])
    response = Mock()
    response.json.return_value = {"code": 0, "data": True}
    post = Mock(return_value=response)
    monkeypatch.setattr(adapter._session, "post", post)
    engine = AutoAuditEngine(adapter, interval=0)
    engine._process_order(order)
    assert engine.stats["success"] == 1
    items = post.call_args.kwargs["json"]["orderItems"]
    assert next(item for item in items if item.get("id") == "main-a")["num"] == 3
    assert next(item for item in items if item.get("id") == "main-b")["num"] == 4
    gifts = [item for item in items if "赠品" in item["title"]]
    assert {(item["tid"], item["num"]) for item in gifts} == {("fixture-a", 2), ("fixture-b", 1)}
