"""解析器 SKU 去重回归：同 SKU 多段数量累加，不同 SKU 互不影响。

修复前：同 SKU 的后续段被丢弃，只保留首段的数量。
修复后：同 SKU 的成功结果累加数量，保留首段的完整属性。
"""

from core.parser import ParsedRemark, extract_multiple_remarks
from adapters.fangguo.config import MATERIAL_MAP


def test_same_sku_accumulates_quantity():
    """审查报告 P1 第 1 项：同 SKU 两段数量应累加为 3，而非只保留 1。"""
    remark = "定制双面革蔓生花;80x150cm-1张，定制双面革蔓生花;80x150cm-2张，共3张"
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    success_results = [r for r in results if r.success]
    assert len(success_results) == 1, f"同 SKU 应合并为 1 条，实际: {len(success_results)}"
    assert success_results[0].num == 3, (
        f"同 SKU 数量应累加为 3，实际: {success_results[0].num}"
    )


def test_single_segment_keeps_original_quantity():
    """单段备注的数量不应被改变。"""
    remark = "定制双面革蔓生花;80x150cm-2张"
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    success_results = [r for r in results if r.success]
    assert len(success_results) == 1
    assert success_results[0].num == 2


def test_different_skus_not_merged():
    """不同 SKU 的商品段应各自保留，不合并。"""
    remark = "定制双面革蔓生花;80x150cm-1张，定制双面革闲叙青釉;80x150cm-1张"
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    success_results = [r for r in results if r.success]
    assert len(success_results) == 2, f"不同 SKU 应保留 2 条，实际: {len(success_results)}"
    assert success_results[0].num == 1
    assert success_results[1].num == 1


def test_same_sku_three_segments():
    """同 SKU 三段的数量应全部累加。"""
    remark = (
        "定制双面革蔓生花;80x150cm-1张，"
        "定制双面革蔓生花;80x150cm-2张，"
        "定制双面革蔓生花;80x150cm-3张，共6张"
    )
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    success_results = [r for r in results if r.success]
    assert len(success_results) == 1
    assert success_results[0].num == 6, (
        f"三段同 SKU 数量应累加为 6，实际: {success_results[0].num}"
    )


def test_mixed_same_and_different_skus():
    """混合场景：部分 SKU 重复、部分独立，各自正确累加或保留。"""
    remark = (
        "定制双面革蔓生花;80x150cm-1张，"
        "定制双面革蔓生花;80x150cm-2张，"
        "定制双面革闲叙青釉;80x150cm-4张，共7张"
    )
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    success_results = [r for r in results if r.success]
    assert len(success_results) == 2, f"应有 2 个不同 SKU，实际: {len(success_results)}"

    sku_nums = {r.shop_mapping_sku: r.num for r in success_results}
    for sku, num in sku_nums.items():
        if "蔓生花" in sku:
            assert num == 3, f"蔓生花数量应累加为 3，实际: {num}"
        elif "闲叙青釉" in sku:
            assert num == 4, f"闲叙青釉数量应为 4，实际: {num}"


def test_first_segment_attributes_preserved():
    """累加时保留首段的完整属性（材质、颜色、花型等）。"""
    remark = (
        "定制双面革蔓生花;80x150cm-1张，"
        "定制双面革蔓生花;80x150cm-2张，共3张"
    )
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    success_results = [r for r in results if r.success]
    assert len(success_results) == 1
    kept = success_results[0]
    assert kept.material_code == "双面格"
    assert "蔓生花" in kept.picture_code
    assert kept.num == 3
