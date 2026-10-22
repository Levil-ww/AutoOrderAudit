# -*- coding: utf-8 -*-
"""合并订单孤儿复制行回归测试。

背景：ERP 自动合并子订单时，会把程序复制行的归属（tid/orderId）改写为合并号
并盖上合并备注，导致后续运行时 original_tid/order_id 匹配不到该行：
1. 匹配阶段失手 → 对同一规格重复创建手工单（merged_sku_fallback 兜底修复）；
2. 去重阶段 (tid, sku) 键对不上 → 旧重复行永不清理（孤儿行清理修复）。

对应修复提交：fix: 合并订单孤儿复制行按SKU复用并清理重复行
"""

from copy import deepcopy
import builtins
import io
import re
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
import requests

from core.parser import ParsedRemark


TITLE = "测试主商品"
SKU_58 = "吸水皮革-定制-定制尺寸-克罗印花;58.7x127CM"
SKU_43 = "吸水皮革-定制-定制尺寸-克罗印花;43x137CM"
MERGED_TID = "child-a&child-b"


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> SimpleNamespace:
    """保留真实适配器逻辑，只替换配置读取和 HTTP 提交边界。"""
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
    import auth_manager
    import gift_manager

    monkeypatch.setattr(auth_manager, "load_auth", lambda: auth_manager.AuthInfo())
    monkeypatch.setattr(gift_manager, "_CONFIG_FILE", tmp_path / "gift-fixture.json")
    monkeypatch.setattr(gift_manager.GiftManager, "_instance", None)

    from adapters.fangguo.adapter import FangguoAdapter
    from adapters.fangguo import config

    adapter = FangguoAdapter()
    monkeypatch.setattr(adapter, "get_material_matcher", lambda: None)
    saved: list[dict] = []
    cancelled: list[str] = []

    def post(url: str, *, json: dict, timeout: int) -> Mock:
        if url == config.API_SAVE_PRODUCT:
            saved.append(deepcopy(json))
            cancelled.extend(row["id"] for row in json["orderItems"] if row.get("cancelStatus"))
        else:
            raise AssertionError(f"非预期接口: {url}")
        response = Mock()
        response.json.return_value = {"code": 0, "data": True}
        return response

    monkeypatch.setattr(adapter._session, "post", post)
    return SimpleNamespace(adapter=adapter, saved=saved, cancelled=cancelled)


def active_rows(payload: dict) -> list[dict]:
    """保存时标记作废的行不属于有效行，清理数量由 cancelled 独立断言。"""
    return [row for row in payload["orderItems"] if not row.get("cancelStatus") and not row.get("discardStatus")]


def make_row(row_id: str, tid: str, sku: str, oid: str = "") -> dict:
    row = {
        "id": row_id, "tid": tid, "oid": oid or tid, "title": TITLE,
        "shopMappingSku": sku, "num": 1, "type": 0,
        "originalSkuId": f"platform-sku-{row_id}",
        "originalGoodsId": f"platform-goods-{row_id}",
    }
    return row


def build_merged_order(adapter, with_duplicate_orphan: bool = False):
    """构造合并订单原始数据并经 _to_order 转换（与线上路径一致）。

    子订单A：备注"差价"；子订单B：定制备注（58.7 编码行）。
    M1：上一轮程序创建的 43 复制行，归属已被 ERP 改写为合并号；
    M2（可选）：再上一轮遗留的第二条 43 重复行。
    """
    raw_items = [
        make_row("row-a", "child-a", "旧编码A", oid="child-a"),
        dict(make_row("row-b", "child-b", "", oid="child-b"),
             shopRemark="定制吸水皮革克罗印花;58.7x127cm-1张，43x137cm-1张，共2张"),
        # 归属被改写为合并号的孤儿复制行
        make_row("row-m1", MERGED_TID, SKU_43, oid=MERGED_TID),
    ]
    if with_duplicate_orphan:
        raw_items.append(make_row("row-m2", MERGED_TID, SKU_43, oid=MERGED_TID))
    raw = {
        "id": "order-merged", "tradeId": MERGED_TID, "tid": MERGED_TID,
        "shopRemark": "差价 定制吸水皮革克罗印花;58.7x127cm-1张，43x137cm-1张，共2张",
        "orderItems": raw_items,
    }
    raw_items[0]["shopRemark"] = "差价"
    return adapter._to_order(raw)


def parsed_group_b() -> list[ParsedRemark]:
    """子订单B分组解析出的两个定制产品（引擎按子订单分组后传入适配器的形态）。

    备注"58.7x127cm-1张，43x137cm-1张，共2张"拆分为 58.7 与 43 两条，
    均携带 original_tid='child-b'：58.7 先按 original_tid 占用 row-b，
    43 因 row-b 已被占用而落到 merged_sku_fallback 孤儿复用。
    """
    return [
        ParsedRemark(
            material_code="吸水皮革", color_code="定制", model_code="定制尺寸",
            picture_code="克罗印花;58.7x127CM", num=1, success=True,
            original_tid="child-b",
        ),
        ParsedRemark(
            material_code="吸水皮革", color_code="定制", model_code="定制尺寸",
            picture_code="克罗印花;43x137CM", num=1, success=True,
            original_tid="child-b",
        ),
    ]


def test_merged_orphan_copy_line_is_reused_not_recreated(runtime) -> None:
    """归属被改写的旧复制行应按 SKU 复用改码，不再新建手工单。"""
    order = build_merged_order(runtime.adapter)
    parsed_list = parsed_group_b()

    assert runtime.adapter.update_merchant_code(order, parsed_list[0], parsed_list) is True

    assert len(runtime.saved) == 1
    rows = active_rows(runtime.saved[0])
    by_id = {r.get("id"): r for r in rows}
    # 58.7 按 original_tid 命中 row-b 改码
    assert by_id["row-b"]["shopMappingSku"] == SKU_58
    # 43 复用孤儿行 row-m1，而非新建
    assert "row-m1" in by_id, "应复用孤儿行 row-m1"
    assert by_id["row-m1"]["shopMappingSku"] == SKU_43
    assert by_id["row-m1"]["num"] == 1
    # 不允许出现新建行（新建行无 id）
    assert all(r.get("id") for r in rows), f"不应创建新手工单: {rows}"
    assert runtime.cancelled == []


def test_merged_extra_orphan_duplicate_is_deleted_without_qty_merge(runtime) -> None:
    """多余的孤儿重复行应标记作废后保存清理，且不把数量合并进存活行。"""
    order = build_merged_order(runtime.adapter, with_duplicate_orphan=True)
    parsed_list = parsed_group_b()

    assert runtime.adapter.update_merchant_code(order, parsed_list[0], parsed_list) is True

    assert runtime.cancelled == ["row-m2"], "仅删除多余重复行 row-m2"
    rows = active_rows(runtime.saved[0])
    by_id = {r.get("id"): r for r in rows}
    assert "row-m2" not in by_id, "作废行不应出现在有效商品列表"
    assert "row-m1" in by_id
    assert by_id["row-m1"]["shopMappingSku"] == SKU_43
    assert by_id["row-m1"]["num"] == 1, "存活行数量不应被合并污染（需求为1张）"
    assert all(r.get("id") for r in rows), f"不应创建新手工单: {rows}"


@pytest.mark.parametrize("field", ["sysOid", "oid", "originTradeId", "tradeId"])
def test_internal_row_identifier_is_not_a_child_tid(runtime, field: str) -> None:
    """内部行标识不能遮蔽其他字段中的有效子订单号。"""
    raw = deepcopy(build_merged_order(runtime.adapter).raw)
    raw["orderItems"][2][field] = "internal-row-43"
    raw["orderItems"][2]["subTid"] = "child-b"
    order = runtime.adapter._to_order(raw)
    assert order.items[2].original_tid == "child-b"


@pytest.mark.parametrize("field", ["sysOid", "oid", "originTradeId"])
def test_internal_identifier_orphan_is_reused_and_duplicates_removed(runtime, field: str) -> None:
    """原始行号独立于子订单号时，也复用旧复制行，且不累加重复数量。"""
    raw = deepcopy(build_merged_order(runtime.adapter, with_duplicate_orphan=True).raw)
    for row in raw["orderItems"][2:]:
        row[field] = "internal-" + row["id"]
    order = runtime.adapter._to_order(raw)
    parsed_list = parsed_group_b()
    assert runtime.adapter.update_merchant_code(order, parsed_list[0], parsed_list) is True
    assert runtime.cancelled == ["row-m2"]
    rows = active_rows(runtime.saved[-1])
    assert all(row.get("id") for row in rows)
    assert [(row["id"], row["num"]) for row in rows if row["shopMappingSku"] == SKU_43] == [("row-m1", 1)]


def test_correct_skus_do_not_hide_extra_copy_rows(runtime) -> None:
    """需要的编码都存在时，仍须清理历史多余复制行。"""
    raw = deepcopy(build_merged_order(runtime.adapter, with_duplicate_orphan=True).raw)
    raw["orderItems"][0]["shopMappingSku"] = "定制-定制-补差价-不打印"
    raw["orderItems"][1]["shopMappingSku"] = SKU_58
    order = runtime.adapter._to_order(raw)
    parsed_list = parsed_group_b()
    assert runtime.adapter.update_merchant_code(order, parsed_list[0], parsed_list) is True
    assert runtime.cancelled == ["row-m2"]
    assert next(row for row in active_rows(runtime.saved[-1]) if row["id"] == "row-m1")["num"] == 1


def test_same_child_exact_sku_is_reused_before_another_spec(runtime) -> None:
    """行顺序与备注尺寸顺序相反时，不应覆盖另一规格再复制一条。"""
    raw = deepcopy(build_merged_order(runtime.adapter).raw)
    raw["orderItems"][1]["shopMappingSku"] = SKU_43
    raw["orderItems"][2]["shopMappingSku"] = SKU_58
    raw["orderItems"][2]["tid"] = "child-b"
    raw["orderItems"][1]["num"] = 2  # 触发保存，验证按规格复用后将数量改回1。
    order = runtime.adapter._to_order(raw)
    parsed_list = parsed_group_b()
    assert runtime.adapter.update_merchant_code(order, parsed_list[0], parsed_list) is True
    rows = active_rows(runtime.saved[-1])
    assert [(row["id"], row["shopMappingSku"]) for row in rows] == [("row-m1", SKU_58), ("row-b", SKU_43)]


def test_orphan_cannot_be_assigned_to_two_children_with_same_sku(runtime, capsys) -> None:
    """相同 SKU 同时属于两个子订单时，不猜测孤儿行归属，不提交或删除。"""
    raw = deepcopy(build_merged_order(runtime.adapter).raw)
    raw["orderItems"][0]["shopRemark"] = "定制吸水皮革克罗印花;43x137cm-1张"
    order = runtime.adapter._to_order(raw)
    parsed_list = [deepcopy(parsed_group_b()[1]), parsed_group_b()[1]]
    parsed_list[0].original_tid = "child-a"
    assert runtime.adapter.update_merchant_code(order, parsed_list[0], parsed_list) is None
    assert runtime.saved == []
    assert runtime.cancelled == []
    assert "人工确认" in capsys.readouterr().out


def test_same_sku_in_two_known_children_is_preserved(runtime) -> None:
    """两个子订单各有明确购买行时，同 SKU 不应被误删或合并数量。"""
    raw = deepcopy(build_merged_order(runtime.adapter).raw)
    raw["orderItems"] = raw["orderItems"][:2]
    raw["orderItems"][0]["shopRemark"] = "定制吸水皮革克罗印花;43x137cm-1张"
    order = runtime.adapter._to_order(raw)
    parsed_list = [deepcopy(parsed_group_b()[1]), parsed_group_b()[1]]
    parsed_list[0].original_tid = "child-a"
    assert runtime.adapter.update_merchant_code(order, parsed_list[0], parsed_list) is True
    assert runtime.cancelled == []
    assert [(row["id"], row["num"]) for row in active_rows(runtime.saved[-1])] == [("row-a", 1), ("row-b", 1)]


def test_repeated_runs_reuse_saved_rows_after_erp_rewrites_ownership(runtime) -> None:
    """连续三轮模拟 ERP 改写复制行归属，第二轮起不再创建任何主商品行。"""
    raw = deepcopy(build_merged_order(runtime.adapter).raw)
    raw["orderItems"] = raw["orderItems"][:2]
    parsed_list = parsed_group_b()
    for run in range(3):
        order = runtime.adapter._to_order(deepcopy(raw))
        saved_before = len(runtime.saved)
        assert runtime.adapter.update_merchant_code(order, parsed_list[0], parsed_list) is True
        if len(runtime.saved) > saved_before:
            rows = deepcopy(active_rows(runtime.saved[-1]))
            new_rows = [row for row in rows if not row.get("id")]
            assert len(new_rows) == (1 if run == 0 else 0)
            for row in rows:
                if not row.get("id"):
                    row.update(id="created-43", type=0, tid=MERGED_TID, orderId=MERGED_TID,
                               oid="internal-43", sysOid="internal-sys-43", originTradeId=MERGED_TID,
                               shopRemark=raw["shopRemark"])
            raw["orderItems"] = rows
        assert sum(re.sub(r"<[^>]+>", "", row["shopMappingSku"]) == SKU_43 for row in raw["orderItems"]) == 1
        assert runtime.cancelled == []


@pytest.mark.parametrize("copy_type", [0, 1])
def test_reported_order_parses_only_children_and_keeps_three_main_rows(runtime, monkeypatch, copy_type: int) -> None:
    """用报告中的备注贯通引擎与适配器，连续运行时不重复解析综合备注或增殖73CM。"""
    from core import engine as engine_module

    child_a = "fixture-child-1"
    child_b = "fixture-child-2"
    merged_tid = child_a + "&" + child_b
    remark_a = "定制镜面地垫闲叙青釉;130x130cm-1张，送蔓生花小圆垫-2张"
    remark_b = "定制双面革蔓生花;直径44cm-1张，直径73cm-1张，送南瓜垫-1张"
    combined = remark_a + " " + remark_b
    sku_73 = "双面格-定制-定制尺寸-蔓生花;直径73CM"
    raw = {
        "tid": merged_tid, "tradeId": merged_tid, "shopRemark": combined,
        "orderItems": [
            dict(make_row("row-130", child_a, "旧编码130"), shopRemark=remark_a),
            dict(make_row("row-44", child_b, "旧编码44"), shopRemark=remark_b),
            dict(make_row("row-73", merged_tid, sku_73, oid="internal-73"),
                 sysOid="internal-sys-73", shopRemark=combined, type=copy_type),
            dict(make_row("duplicate-73", merged_tid, sku_73, oid="internal-duplicate-73"),
                 sysOid="internal-sys-duplicate-73", shopRemark=combined, type=copy_type),
        ],
    }
    parsed_remarks = []
    extract = engine_module.extract_multiple_remarks

    def record_parse(remark: str, **kwargs) -> list[ParsedRemark]:
        parsed_remarks.append(remark)
        return extract(remark, **kwargs)

    monkeypatch.setattr(engine_module, "extract_multiple_remarks", record_parse)
    engine = engine_module.AutoAuditEngine(runtime.adapter)
    for run in range(3):
        order = runtime.adapter._to_order(deepcopy(raw))
        before = len(runtime.saved)
        engine._process_merged_order(order, runtime.adapter.material_map, None)
        assert parsed_remarks[-2:] == [remark_a, remark_b]
        assert combined not in parsed_remarks
        assert engine.stats["failed"] == 0
        assert len(runtime.saved) in (before, before + 1)
        rows = deepcopy(active_rows(runtime.saved[-1]) if len(runtime.saved) > before else raw["orderItems"])
        main_rows = [row for row in rows if "定制-定制尺寸" in re.sub(r"<[^>]+>", "", row["shopMappingSku"])]
        assert len(main_rows) == 3
        assert all(row.get("id") for row in main_rows)
        assert [(row["id"], row["num"]) for row in main_rows if re.sub(r"<[^>]+>", "", row["shopMappingSku"]) == sku_73] == [("row-73", 1)]
        for index, row in enumerate(rows):
            if not row.get("id"):
                row["id"] = f"gift-{run}-{index}"
            if row["id"] == "row-73":
                row.update(tid=merged_tid, orderId=merged_tid, oid="internal-73",
                           sysOid="internal-sys-73", shopRemark=combined, type=copy_type)
        # ERP 保留原始子订单备注，复制行展示综合备注。
        next(row for row in rows if row["id"] == "row-130")["shopRemark"] = remark_a
        next(row for row in rows if row["id"] == "row-44")["shopRemark"] = remark_b
        raw["orderItems"] = rows
    assert runtime.cancelled == ["duplicate-73"]


@pytest.mark.parametrize("quantity", [2, 32])
def test_extra_orphan_quantity_is_not_merged_into_survivor(runtime, quantity):
    raw = deepcopy(build_merged_order(runtime.adapter, with_duplicate_orphan=True).raw)
    raw["orderItems"][-1]["num"] = quantity
    order = runtime.adapter._to_order(raw)
    parsed = parsed_group_b()
    assert runtime.adapter.update_merchant_code(order, parsed[0], parsed) is True
    assert runtime.cancelled == ["row-m2"]
    surviving = [row for row in active_rows(runtime.saved[-1]) if row["shopMappingSku"] == SKU_43]
    assert [(row["id"], row["num"]) for row in surviving] == [("row-m1", 1)]


@pytest.mark.parametrize("clone_first", [False, True])
def test_merged_row_remark_cannot_replace_first_child_remark(runtime, monkeypatch, clone_first):
    from core import engine as engine_module

    raw = deepcopy(build_merged_order(runtime.adapter).raw)
    remark_a = "定制吸水皮革蔓生花;40x60cm-1张"
    remark_b = raw["orderItems"][1]["shopRemark"]
    raw["orderItems"][0]["shopRemark"] = remark_a
    combined = remark_a + " " + remark_b
    clone = raw["orderItems"][2]
    clone.update(subTid="child-a", shopRemark=combined)
    if clone_first:
        raw["orderItems"] = [clone, *raw["orderItems"][:2]]
    order = runtime.adapter._to_order(raw)
    extract = engine_module.extract_multiple_remarks
    recorded = []

    def parse(remark, **kwargs):
        recorded.append(remark)
        return extract(remark, **kwargs)

    monkeypatch.setattr(engine_module, "extract_multiple_remarks", parse)
    engine_module.AutoAuditEngine(runtime.adapter)._process_merged_order(order, runtime.adapter.material_map, None)
    assert recorded == [remark_a, remark_b]
    assert combined not in recorded
