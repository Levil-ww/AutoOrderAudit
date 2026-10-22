"""参考项目增量同步：虚构备注和订单验证，禁止真实 ERP 操作。"""
import pytest

from adapters.fangguo.adapter import FangguoAdapter
from adapters.fangguo.config import MATERIAL_MAP
from core.adapter_base import Order, OrderItem
from core.engine import AutoAuditEngine
from core.parser import extract_multiple_remarks


@pytest.mark.parametrize("suffix", ["到货返差价26元", "到货反差价26元", "到货反26元", "返差26元", "反差26元", "到货退差价26元", "确认收货反差价0.3元", "到货后反12元", "收货后反12元"])
def test_refund_instructions_do_not_pollute_product_sku(suffix):
    results = extract_multiple_remarks("定制双面革蔓生花;80x120cm-1张，" + suffix, MATERIAL_MAP)
    assert len(results) == 1
    assert results[0].shop_mapping_sku == "双面格-定制-定制尺寸-蔓生花;80x120CM"


def test_pattern_internal_hyphen_is_removed():
    results = extract_multiple_remarks("定制双面革木纹-金鱼;80x120cm-1张", MATERIAL_MAP)
    assert results[0].shop_mapping_sku == "双面格-定制-定制尺寸-木纹金鱼;80x120CM"


@pytest.mark.parametrize("name,expected", [("高回弹", "镜面皮革"), ("高回弹皮革", "镜面皮革"), ("浴室垫", "浴室吸水科技布")])
def test_added_material_aliases(name, expected):
    assert MATERIAL_MAP[name] == expected
    parsed = extract_multiple_remarks(f"定制{name}蔓生花;80x120cm-1张", MATERIAL_MAP)
    assert parsed[0].material_code == expected


@pytest.mark.parametrize("blank", [False, True])
def test_bathroom_material_blocks_automatic_push(blank):
    adapter = FangguoAdapter()
    order = Order(shop_remark="" if blank else "现货浴室垫蔓生花;40x60cm-1张",
                  items=[OrderItem(title="测试商品", shop_mapping_sku="浴室吸水科技布-标准-40x60-蔓生花;40x60")])
    assert AutoAuditEngine(adapter)._get_push_skip_reason(order, allow_blank_remark=True) == "材质[浴室吸水科技布]不允许自动推送"


def test_no_print_quantity_is_already_one():
    item = FangguoAdapter()._build_price_diff_no_ship_item(OrderItem(num=32), Order())
    assert item["shopMappingSku"] == "定制-定制-补差价-不打印"
    assert item["num"] == 1


@pytest.mark.parametrize("merged", [False, True])
def test_no_ship_gift_does_not_restore_original_quantity(monkeypatch, merged):
    from unittest.mock import Mock
    from core.parser import ParsedRemark

    adapter = FangguoAdapter()
    tid = "child-a&child-b" if merged else "child-a"
    order = Order(trade_id=tid, tid=tid, shop_remark="不要赠品", items=[
        OrderItem(id="main", oid="child-a", original_tid="child-a", title="测试主商品",
                  original_goods_id="goods-main", shop_mapping_sku="吸水皮革-标准-40x60-蔓生花;40x60"),
        OrderItem(id="gift", oid="child-a", original_tid="child-a", title="赠品沥水垫小圆或小方",
                  num=32, shop_mapping_sku="吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方"),
    ])
    response = Mock()
    response.json.return_value = {"code": 0, "data": True}
    post = Mock(return_value=response)
    monkeypatch.setattr(adapter._session, "post", post)
    parsed = ParsedRemark(success=False)
    assert adapter.update_merchant_code(order, parsed, [parsed], gift_no_ship=not merged,
                                       gift_no_ship_tids=["child-a"] if merged else None) is True
    gift = next(row for row in post.call_args.kwargs["json"]["orderItems"] if row.get("id") == "gift")
    assert gift["shopMappingSku"] == "定制-定制-补差价-不打印"
    assert gift["num"] == 1


@pytest.mark.parametrize("prefix", ["现货", "实际发", "成品", "定制"])
def test_explicit_product_prefix_starts_an_independent_segment(prefix):
    remark = "现货双面革蔓生花;30x50cm-1张，" + prefix + "吸水皮革闲叙青釉;40x60cm-1张"
    results = extract_multiple_remarks(remark, MATERIAL_MAP)
    assert len(results) == 2
    assert results[0].shop_mapping_sku == "双面格-标准-30x50-蔓生花;30x50"
    expected = ("吸水皮革-定制-定制尺寸-闲叙青釉;40x60CM" if prefix == "定制"
                else "吸水皮革-标准-40x60-闲叙青釉;40x60")
    assert results[1].shop_mapping_sku == expected
