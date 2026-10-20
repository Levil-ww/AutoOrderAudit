r"""中文数量匹配回归：两位中文数量不再被截取成末尾一位。

修复前：_CHINESE_NUMBERS 只匹配单个中文字符，"十一张"被截为"十"或"一"。
修复后：扩展正则匹配 1-99 的复合中文数字（十一、二十、二十一等）。
"""

import pytest

from core.parser import (
    _RE_CHINESE_QTY,
    _RE_QTY_SUMMARY_VALUE,
    _num_to_int,
    extract_multiple_remarks,
)
from adapters.fangguo.config import MATERIAL_MAP


@pytest.mark.parametrize("text,expected", [
    ("十一张", 11),
    ("十二张", 12),
    ("二十张", 20),
    ("二十一张", 21),
    ("三十二张", 32),
    ("九十九张", 99),
    ("十张", 10),
    ("三张", 3),
    ("两张", 2),
])
def test_chinese_qty_regex_matches_compound_numbers(text, expected):
    """_RE_CHINESE_QTY 能正确匹配复合中文数字。"""
    matches = _RE_CHINESE_QTY.findall(text)
    assert matches, f"{text!r} 应匹配到中文数量"
    assert _num_to_int(matches[0]) == expected


@pytest.mark.parametrize("text,expected", [
    ("共十一张", 11),
    ("共计二十一张", 21),
    ("共三张", 3),
])
def test_qty_summary_regex_matches_compound_numbers(text, expected):
    """_RE_QTY_SUMMARY_VALUE 能正确匹配汇总中的复合中文数字。"""
    matches = _RE_QTY_SUMMARY_VALUE.findall(text)
    assert matches, f"{text!r} 应匹配到汇总数量"
    assert _num_to_int(matches[0]) == expected


@pytest.mark.parametrize("chinese_text,expected_num", [
    ("定制双面革蔓生花;80x150cm-十一张", 11),
    ("定制双面革蔓生花;80x150cm-十二张", 12),
    ("定制双面革蔓生花;80x150cm-二十张", 20),
    ("定制双面革蔓生花;80x150cm-二十一张", 21),
])
def test_full_parse_with_compound_chinese_numbers(chinese_text, expected_num):
    """完整解析流程中，复合中文数量被正确转换为整数。"""
    results = extract_multiple_remarks(chinese_text, material_map=MATERIAL_MAP)
    success_results = [r for r in results if r.success]
    assert success_results, f"{chinese_text!r} 应解析成功"
    assert success_results[0].num == expected_num, (
        f"{chinese_text!r} 数量应为 {expected_num}，实际 {success_results[0].num}"
    )
