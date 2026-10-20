"""推单筛选回归测试：仅使用虚构订单，禁止访问用户配置或真实 ERP。"""

from types import ModuleType, SimpleNamespace
import builtins
import io
import sys

import pytest
import requests

from core.adapter_base import ErpAdapter, Order, OrderItem
from core.engine import AutoAuditEngine


REMARK = "定制双面革蔓生花;80x150cm-1张"
SKU = "双面格-定制-定制尺寸-蔓生花;80x150CM"


class PushAdapter(ErpAdapter):
    """记录真实引擎筛选后的提交边界，不发送 HTTP 请求。"""

    material_map = {"双面革": "双面格", "双面格": "双面格"}

    def __init__(self, orders: list[Order], status: int) -> None:
        self.orders = orders
        self.status = status
        self.pushed: list[str] = []
        self.express_updates: list[str] = []

    def query_orders(self, **kwargs) -> list[Order]:
        return self.orders if kwargs["query_status"] == self.status else []

    def update_merchant_code(self, *args, **kwargs) -> bool:
        raise AssertionError("推单筛选不得修改商品编码")

    def get_material_matcher(self) -> None:
        return None

    def is_gift_item(self, item: OrderItem) -> bool:
        return item.title.startswith("赠品")

    def is_price_difference_item(self, item: OrderItem) -> bool:
        return "补差价" in item.title

    def update_express(self, order: Order, cp_code: str) -> bool:
        self.express_updates.append(order.trade_id)
        return True

    def push_orders(self, trade_ids: list[str]) -> dict:
        self.pushed.extend(trade_ids)
        return {"code": 0}


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    """配置读取和网络都设硬保护，快递规则仅使用内存对象。"""
    protected = {"token.json", "last_username.json", "express_config.json", "gift_config.json"}
    for module in (builtins, io):
        original_open = module.open

        def guarded_open(file, *args, _open=original_open, **kwargs):
            name = str(file).replace("\\", "/").rsplit("/", 1)[-1]
            assert name not in protected, "禁止访问用户配置"
            return _open(file, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded_open)

    def no_network(*args, **kwargs):
        raise AssertionError("禁止调用真实 ERP")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    manager = SimpleNamespace(
        resolve_express=lambda *args, **kwargs: ("极兔", "JT"),
        keyword_map={}, store_map={}, platform_map={},
    )
    monkeypatch.setattr("core.engine.get_express_manager", lambda: manager)
    monkeypatch.setattr(AutoAuditEngine, "_verify_push_result", lambda *args: None)
    config = ModuleType("adapters.fangguo.config")
    config.QUERY_STATUS_PENDING_PUSH = 2
    monkeypatch.setitem(sys.modules, "adapters.fangguo.config", config)


def make_order(remark: str = REMARK, sku: str = SKU, num: int = 1) -> Order:
    return Order(
        trade_id="fixture-order", tid="fixture-tid", shop_remark=remark,
        receiver_province="浙江", current_cp_code="JT",
        raw={"payTime": "2020-01-01 00:00:00"},
        items=[OrderItem(id="main", title="桌垫", shop_mapping_sku=sku, num=num)],
    )


def run_push(order: Order, status: int, dry_run: bool = False) -> PushAdapter:
    adapter = PushAdapter([order], status)
    AutoAuditEngine(adapter, dry_run=dry_run).push_eligible_orders()
    return adapter


@pytest.mark.parametrize("status", [1, 2])
@pytest.mark.parametrize("tid", ["platform-tid", ""])
@pytest.mark.parametrize("scenario", ["skip", "missing_time", "recent", "express_failed", "express_error", "eligible"])
def test_push_order_logs_use_tid(monkeypatch, capsys, status: int, tid: str, scenario: str) -> None:
    """推单各分支显示 tid，实际提交仍使用原 trade_id。"""
    order = make_order()
    order.tid = tid
    if scenario == "skip":
        order.shop_remark = "待定"
    elif scenario == "missing_time":
        order.raw = {}
    elif scenario == "recent":
        order.raw = {"payTime": "2099-01-01 00:00:00"}
    elif scenario == "express_failed":
        monkeypatch.setattr(AutoAuditEngine, "_update_express", lambda *args: False)
    elif scenario == "express_error":
        def fail_express(*args) -> bool:
            raise RuntimeError("模拟快递异常")
        monkeypatch.setattr(AutoAuditEngine, "_update_express", fail_express)

    adapter = run_push(order, status)

    output = capsys.readouterr().out
    expected = "platform-tid" if tid else "fixture-order"
    assert expected in output
    if tid:
        assert "fixture-order" not in output
    assert adapter.pushed == (["fixture-order"] if scenario == "eligible" else [])
    assert order.trade_id == "fixture-order"


@pytest.mark.parametrize("status", [1, 2])
@pytest.mark.parametrize("remark", [
    "定制", "多送防滑贴", "补差价", "补的差价", "补差价的",
    "补差价，", "11月10日发货", "11月10号发货", "十一月十日发货",
    "11/10发货", "11-10发货", "11.10发货", "请于11月10日安排发货",
    REMARK + "，11月10日发货", REMARK + "，待确认",
])
def test_unsafe_remarks_never_reach_push_or_express_update(status, remark, capsys):
    """两种来源均不能以原编码解码成功为由放行未处理或延期订单。"""
    order = make_order(remark)
    order.current_cp_code = "ZTO"
    adapter = run_push(order, status)
    assert adapter.pushed == []
    assert adapter.express_updates == []
    assert "跳过" in capsys.readouterr().out


@pytest.mark.parametrize("status", [1, 2])
@pytest.mark.parametrize("sku,num", [
    ("双面格-标准-80x150-蔓生花;80x150", 1),
    (SKU, 2), ("吸水皮革-标准-*-*", 1), ("", 1),
    ("定制-定制-补差价-不打印", 1),
])
def test_unapplied_or_incomplete_codes_are_blocked(status, sku, num):
    """备注虽有效，编码或数量尚未落实时也不得推送。"""
    assert run_push(make_order(sku=sku, num=num), status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_applied_custom_order_can_push_after_restart(status):
    """以 ERP 当前编码验证落实结果，不依赖本轮是否发生修改。"""
    assert run_push(make_order(), status).pushed == ["fixture-order"]


@pytest.mark.parametrize("status", [1, 2])
def test_item_remark_restriction_blocks_whole_order(status):
    order = make_order()
    order.items.append(OrderItem(id="other", title="餐垫", shop_remark="补的差价", shop_mapping_sku=SKU))
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_gift_only_changes_do_not_qualify_custom_only_remark(status):
    order = make_order("定制，赠品南瓜-1张")
    order.items.append(OrderItem(title="赠品南瓜", shop_mapping_sku="双面格-标准-30x40-南瓜;30x40"))
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_multi_product_codes_and_quantities_must_all_match(status):
    order = make_order(REMARK.replace("1张", "2张") + "，浅草蔓影;40x120cm-1张", num=2)
    order.items.append(OrderItem(id="second", title="桌垫", shop_mapping_sku="双面格-定制-定制尺寸-浅草蔓影;40x120CM"))
    assert run_push(order, status).pushed == ["fixture-order"]
    order.items[1].shop_mapping_sku = "双面格-标准-40x120-浅草蔓影;40x120"
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_void_rows_and_gift_rows_do_not_break_applied_product_match(status):
    order = make_order()
    order.items.extend([
        OrderItem(id="old", title="旧商品", is_void=True, shop_mapping_sku="*-*-*-*", shop_remark="11月10日发货"),
        OrderItem(id="gift", title="赠品南瓜", shop_mapping_sku="双面格-标准-30x40-南瓜;30x40"),
    ])
    assert run_push(order, status).pushed == ["fixture-order"]


@pytest.mark.parametrize("status", [1, 2])
def test_merged_child_without_valid_remark_blocks_entire_order(status):
    order = make_order()
    order.tid = "child-a&child-b"
    order.items[0].original_tid = "child-a"
    order.items[0].shop_remark = REMARK
    order.items.append(OrderItem(id="child-b", title="桌垫", original_tid="child-b", shop_remark="定制", shop_mapping_sku=SKU))
    assert run_push(order, status).pushed == []


def test_dry_run_does_not_submit_or_modify_express():
    order = make_order()
    order.current_cp_code = "ZTO"
    adapter = run_push(order, 2, dry_run=True)
    assert adapter.pushed == []
    assert adapter.express_updates == []


@pytest.mark.parametrize("status", [1, 2])
def test_merged_child_cannot_borrow_other_childs_order_remark(status):
    order = make_order()
    order.tid = "child-a&child-b"
    order.items[0].original_tid = "child-a"
    order.items[0].shop_remark = REMARK
    order.items.append(OrderItem(id="child-b", title="桌垫", original_tid="child-b", shop_mapping_sku=SKU))
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_valid_merged_children_with_same_remark_can_push(status):
    order = make_order()
    order.tid = "child-a&child-b"
    order.items[0].original_tid = "child-a"
    order.items[0].shop_remark = REMARK
    order.items.append(OrderItem(id="child-b", title="桌垫", original_tid="child-b", shop_remark=REMARK, shop_mapping_sku=SKU))
    assert run_push(order, status).pushed == ["fixture-order"]


@pytest.mark.parametrize("status", [1, 2])
def test_child_split_rows_share_their_own_remark(status):
    order = make_order()
    order.tid = "child-a&child-b"
    order.items[0].original_tid = "child-a"
    order.items[0].shop_remark = REMARK.replace("1张", "2张")
    order.items.append(OrderItem(id="split-a", title="桌垫", original_tid="child-a", shop_mapping_sku=SKU))
    order.items.append(OrderItem(id="child-b", title="桌垫", original_tid="child-b", shop_remark=REMARK, shop_mapping_sku=SKU))
    assert run_push(order, status).pushed == ["fixture-order"]


@pytest.mark.parametrize("status", [1, 2])
def test_display_tags_and_case_do_not_block_applied_order(status):
    order = make_order(sku="<font color='red'>双面格-定制-定制尺寸-蔓生花;80x150cm</font>")
    assert run_push(order, status).pushed == ["fixture-order"]


@pytest.mark.parametrize("status", [1, 2])
def test_incomplete_item_details_block_push(status):
    order = make_order()
    order.items[0].detail_enriched = False
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_parse_failure_blocks_order_without_touching_express(status, monkeypatch):
    def broken_parser(*args, **kwargs):
        raise ValueError("fixture parser failure")

    monkeypatch.setattr("core.engine.extract_multiple_remarks", broken_parser)
    order = make_order()
    order.current_cp_code = "ZTO"
    adapter = run_push(order, status)
    assert adapter.pushed == []
    assert adapter.express_updates == []


@pytest.mark.parametrize("status", [1, 2])
@pytest.mark.parametrize("size", ["80.5x150", "5.5x20", "10.5x20"])
def test_decimal_size_next_to_shipping_word_is_not_a_date(status, size):
    order = make_order(
        f"定制双面革蔓生花;{size}cm-1张发货",
        f"双面格-定制-定制尺寸-蔓生花;{size}CM发货",
    )
    assert run_push(order, status).pushed == ["fixture-order"]


@pytest.mark.parametrize("status", [1, 2])
def test_item_level_date_blocks_valid_order_level_remark(status):
    order = make_order()
    order.items[0].shop_remark = REMARK + "，2026年11月10日寄出"
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_valid_spot_remark_can_push(status):
    order = make_order("现货双面革蔓生花;80x150cm-1张", "双面格-标准-80x150-蔓生花;80x150")
    assert run_push(order, status).pushed == ["fixture-order"]


@pytest.mark.parametrize("status", [1, 2])
def test_payment_less_than_thirty_minutes_old_remains_blocked(status):
    from datetime import datetime

    order = make_order()
    order.raw["payTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_no_items_never_pushes(status):
    order = make_order()
    order.items.clear()
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
def test_merged_order_without_ampersand_cannot_share_remarks(status):
    order = make_order(REMARK.replace("1张", "2张"))
    order.items[0].original_tid = "child-a"
    order.items[0].shop_remark = order.shop_remark
    order.items.append(OrderItem(id="child-b", title="桌垫", original_tid="child-b", shop_mapping_sku=SKU))
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
@pytest.mark.parametrize("remark", ["11月10日，安排发货", "11月10号\n发货", "请发货，日期11/10"])
def test_order_level_date_cannot_be_hidden_by_valid_item_remark(status, remark):
    order = make_order(remark)
    order.items[0].shop_remark = REMARK
    assert run_push(order, status).pushed == []


@pytest.mark.parametrize("status", [1, 2])
@pytest.mark.parametrize("remark", ["", "   ", "\n\t"])
def test_blank_standard_order_only_pushes_from_pending_push(status, remark):
    """待推送是标准单入口，空备注无需解析定制信息；待整理仍拦截。"""
    order = make_order(remark, "双面格-标准-80x150-蔓生花;80x150")
    adapter = run_push(order, status)
    assert adapter.pushed == (["fixture-order"] if status == 2 else [])


@pytest.mark.parametrize("minutes,should_push", [(29, False), (30, True), (31, True)])
def test_blank_standard_order_obeys_payment_cutoff(minutes, should_push, monkeypatch):
    from datetime import datetime, timedelta

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 15, 12, 0, 0)

    monkeypatch.setattr("core.engine.datetime", FixedDateTime)
    order = make_order("", "双面格-标准-80x150-蔓生花;80x150")
    order.raw["payTime"] = (FixedDateTime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    adapter = run_push(order, 2)
    assert adapter.pushed == (["fixture-order"] if should_push else [])


@pytest.mark.parametrize("remark", ["待定", "待确认", "待确定", "补的差价", "11月10日发货"])
@pytest.mark.parametrize("item_level", [False, True])
def test_standard_order_still_checks_order_and_item_restrictions(remark, item_level):
    order = make_order("" if item_level else remark, "双面格-标准-80x150-蔓生花;80x150")
    if item_level:
        order.items[0].shop_remark = remark
    order.current_cp_code = "ZTO"
    adapter = run_push(order, 2)
    assert adapter.pushed == []
    assert adapter.express_updates == []


@pytest.mark.parametrize("pay_time", [None, "not-a-time"])
def test_blank_standard_order_without_valid_payment_time_is_not_ready(pay_time):
    order = make_order("", "双面格-标准-80x150-蔓生花;80x150")
    order.raw["payTime"] = pay_time
    assert run_push(order, 2).pushed == []


@pytest.mark.parametrize("sku", ["", "吸水皮革-标准-*-*", "定制-定制-补差价-不打印"])
def test_blank_standard_order_does_not_bypass_product_safety(sku):
    assert run_push(make_order("", sku), 2).pushed == []


def test_blank_standard_order_does_not_need_material_parser(monkeypatch):
    def unexpected_parse(*args, **kwargs):
        raise AssertionError("标准空备注订单不应解析定制信息")

    monkeypatch.setattr("core.engine.extract_multiple_remarks", unexpected_parse)
    order = make_order("", "双面格-标准-80x150-蔓生花;80x150")
    assert run_push(order, 2).pushed == ["fixture-order"]


@pytest.mark.parametrize("material", ["防辣椒油", "丝圈", "泡泡绒兔毛"])
@pytest.mark.parametrize("status", [1, 2])
@pytest.mark.parametrize("blank_remark", [False, True])
def test_confirmed_materials_never_auto_push(material, status, blank_remark, capsys):
    remark = "" if blank_remark else f"定制{material}蔓生花;80x150cm-1张"
    sku = (f"{material}-标准-80x150-蔓生花;80x150" if blank_remark
           else f"{material}-定制-定制尺寸-蔓生花;80x150CM")
    adapter = PushAdapter([make_order(remark, sku)], status)
    adapter.material_map = {**adapter.material_map, material: material}
    adapter.push_blocked_materials = {"防辣椒油", "丝圈", "泡泡绒兔毛"}
    AutoAuditEngine(adapter).push_eligible_orders()
    assert adapter.pushed == []
    assert adapter.express_updates == []
    assert f"材质[{material}]不允许自动推送" in capsys.readouterr().out
