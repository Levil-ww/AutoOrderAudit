"""
测试备注解析器的两个修复：
1. 标准编码尺寸不带单位
2. 材质继承：后续段能继承现货的材质信息
"""

import pytest

from core.parser import parse_remark, extract_multiple_remarks
from adapters.fangguo.config import MATERIAL_MAP


def test_standard_code_size_no_unit():
    """测试标准编码的尺寸不带单位"""
    print("=" * 60)
    print("测试1: 标准编码尺寸不带单位")
    print("=" * 60)

    # 测试用例：现货格式
    remark1 = "现货吸水皮革蔓生花;40x60cm-1张"
    p1 = parse_remark(remark1, material_map=MATERIAL_MAP)
    print(f"\n输入: {remark1}")
    print(f"编码: {p1.shop_mapping_sku}")
    print(f"model_code: {p1.model_code}")
    assert "CM" not in p1.model_code.upper() or p1.model_code == "", f"model_code不应包含单位: {p1.model_code}"

    # 测试用例：实际发格式
    remark2 = "实际发吸水皮革蔓生花;40x60cm-1张"
    p2 = parse_remark(remark2, material_map=MATERIAL_MAP)
    print(f"\n输入: {remark2}")
    print(f"编码: {p2.shop_mapping_sku}")
    print(f"model_code: {p2.model_code}")
    assert "CM" not in p2.model_code.upper() or p2.model_code == "", f"model_code不应包含单位: {p2.model_code}"

    # 测试用例：带尺寸的备注
    remark3 = "吸水皮革蔓生花;40x60cm-1张"
    p3 = parse_remark(remark3, material_map=MATERIAL_MAP)
    print(f"\n输入: {remark3}")
    print(f"编码: {p3.shop_mapping_sku}")
    print(f"model_code: {p3.model_code}")
    assert p3.model_code == "40x60CM", "无现货前缀时保留 AutoOrderAudit 原有编码规则"

    print("\n[PASS] 测试1通过：标准编码尺寸不带单位")


def test_material_inheritance():
    """测试材质继承：后续段能继承现货的材质信息"""
    print("\n" + "=" * 60)
    print("测试2: 材质继承")
    print("=" * 60)

    # 测试用例：实际发 + 第二个商品
    remark = "实际发吸水皮革蔓生花;40x60cm-1张，闲叙青釉;40x60cm-1张"
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    print(f"\n输入: {remark}")
    print(f"解析结果数量: {len(results)}")

    for i, r in enumerate(results):
        print(f"\n结果{i+1}:")
        print(f"  编码: {r.shop_mapping_sku}")
        print(f"  材质: {r.material_code}")
        print(f"  颜色: {r.color_code}")
        print(f"  尺寸: {r.model_code}")
        print(f"  花型: {r.picture_code}")
        print(f"  成功: {r.success}")

    # 应该解析出两个商品
    assert len(results) == 2, f"应该解析出2个商品，实际: {len(results)}"

    # 第一个商品
    assert results[0].material_code == "吸水皮革", f"第一个商品材质应为吸水皮革: {results[0].material_code}"
    assert results[0].color_code == "标准", f"第一个商品颜色应为标准: {results[0].color_code}"
    assert "蔓生花" in results[0].picture_code, f"第一个商品花型应包含蔓生花: {results[0].picture_code}"

    # 第二个商品 - 关键测试：材质继承
    assert results[1].material_code == "吸水皮革", f"第二个商品材质应继承为吸水皮革: {results[1].material_code}"
    assert results[1].color_code == "标准", f"第二个商品颜色应为标准: {results[1].color_code}"
    assert "闲叙青釉" in results[1].picture_code, f"第二个商品花型应包含闲叙青釉: {results[1].picture_code}"
    assert results[1].success, "第二个商品应解析成功"

    print("\n[PASS] 测试2通过：材质继承正常")


def test_combined():
    """综合测试：两个修复一起验证"""
    print("\n" + "=" * 60)
    print("测试3: 综合测试")
    print("=" * 60)

    remark = "实际发吸水皮革蔓生花;40x60cm-1张，闲叙青釉;40x60cm-1张"
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    print(f"\n输入: {remark}")
    print(f"\n期望编码:")
    print(f"  1. 吸水皮革-标准-40x60-蔓生花;40x60")
    print(f"  2. 吸水皮革-标准-40x60-闲叙青釉;40x60")

    print(f"\n实际编码:")
    for i, r in enumerate(results):
        print(f"  {i+1}. {r.shop_mapping_sku}")

    # 验证编码格式
    expected1 = "吸水皮革-标准-40x60-蔓生花;40x60"
    expected2 = "吸水皮革-标准-40x60-闲叙青釉;40x60"

    assert results[0].shop_mapping_sku == expected1, f"第一个编码不匹配:\n期望: {expected1}\n实际: {results[0].shop_mapping_sku}"
    assert results[1].shop_mapping_sku == expected2, f"第二个编码不匹配:\n期望: {expected2}\n实际: {results[1].shop_mapping_sku}"

    print("\n[PASS] 测试3通过：综合测试通过")


def test_pattern_ending_with_ge_inherits_material():
    """测试花型名以'格'结尾时不能被误判为材质"""
    print("\n" + "=" * 60)
    print("测试4: 花型名以'格'结尾时继承材质")
    print("=" * 60)

    remark = "定制双面革尼姆八格;36x280cm-1张，40x174cm-1张"
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    print(f"\n输入: {remark}")
    print(f"解析结果数量: {len(results)}")
    for i, r in enumerate(results):
        print(f"  {i+1}. {r.shop_mapping_sku}")

    assert len(results) == 2, f"应该解析出2个商品，实际: {len(results)}"
    assert results[0].shop_mapping_sku == "双面格-定制-定制尺寸-尼姆八格;36x280CM"
    assert results[1].shop_mapping_sku == "双面格-定制-定制尺寸-尼姆八格;40x174CM"

    print("\n[PASS] 测试4通过：尼姆八格作为花型并正确继承材质")


def test_kamila_multiple_sizes_and_gifts():
    """测试多尺寸主商品不能被赠品解析挤掉"""
    print("\n" + "=" * 60)
    print("测试5: 卡蜜拉多尺寸+多赠品")
    print("=" * 60)

    remark = "定制双面革卡蜜拉;43.4x243.5cm-1张，32.1x119.4cm-1张，送南瓜垫-1张，小圆垫-2张，共计5张"
    results = extract_multiple_remarks(remark, material_map=MATERIAL_MAP)

    print(f"\n输入: {remark}")
    print(f"解析结果数量: {len(results)}")
    for i, r in enumerate(results):
        print(f"  {i+1}. {r.shop_mapping_sku} gifts={r.gifts}")

    assert len(results) == 2, f"应该解析出2个主商品，实际: {len(results)}"
    assert results[0].shop_mapping_sku == "双面格-定制-定制尺寸-卡蜜拉;43.4x243.5CM"
    assert results[1].shop_mapping_sku == "双面格-定制-定制尺寸-卡蜜拉;32.1x119.4CM"
    assert ("南瓜", 1) in results[0].gifts
    assert ("圆垫", 2) in results[0].gifts

    print("\n[PASS] 测试5通过：主商品和赠品均被解析")


if __name__ == "__main__":
    test_standard_code_size_no_unit()
    test_material_inheritance()
    test_combined()
    test_pattern_ending_with_ge_inherits_material()
    test_kamila_multiple_sizes_and_gifts()
    print("\n" + "=" * 60)
    print("[PASS] 所有测试通过！")
    print("=" * 60)


@pytest.mark.parametrize("prefix,expected", [
    ("", "吸水皮革-标准-40x60CM-蔓生花;40x60CM"),
    ("现货", "吸水皮革-标准-40x60-蔓生花;40x60"),
    ("成品", "吸水皮革-标准-40x60-蔓生花;40x60"),
    ("实际发", "吸水皮革-标准-40x60-蔓生花;40x60"),
    ("定制", "吸水皮革-定制-定制尺寸-蔓生花;40x60CM"),
])
def test_confirmed_size_encoding_rules(prefix, expected):
    results = extract_multiple_remarks(prefix + "吸水皮革蔓生花;40x60cm-1张", MATERIAL_MAP)
    assert len(results) == 1
    assert results[0].success
    assert results[0].shop_mapping_sku == expected
    assert results[0].num == 1
