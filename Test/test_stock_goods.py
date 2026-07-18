"""
测试现货编码解析功能

现货编码标准：材质-标准-尺寸（没有单位cm或CM）-花型;尺寸（没有单位cm或CM）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.parser import parse_remark, extract_multiple_remarks
from adapters.fangguo.adapter import FangguoAdapter

adapter = FangguoAdapter()
material_map = adapter.material_map
material_matcher = adapter.get_material_matcher()


def run_test(name, remark, expected_count, expected_results=None):
    """运行单个测试用例

    expected_results: list of dict, 每个元素包含 material, color, model, picture, num, is_stock
    """
    print("=" * 80)
    print(f"测试: {name}")
    print(f"备注: {remark}")
    print("=" * 80)

    parsed_list = extract_multiple_remarks(remark, material_map=material_map, material_matcher=material_matcher)

    print(f"解析出 {len(parsed_list)} 个商品:")
    all_pass = True
    for i, p in enumerate(parsed_list):
        print(f"\n商品{i+1}:")
        print(f"  success: {p.success}")
        print(f"  material_code: {p.material_code}")
        print(f"  color_code: {p.color_code}")
        print(f"  model_code: {p.model_code}")
        print(f"  picture_code: {p.picture_code}")
        print(f"  num: {p.num}")
        print(f"  is_stock: {p.is_stock}")
        print(f"  shop_mapping_sku: {p.shop_mapping_sku}")
        if p.gifts:
            print(f"  gifts: {p.gifts}")

        if expected_results and i < len(expected_results):
            expected = expected_results[i]
            for key, val in expected.items():
                actual = getattr(p, key, None)
                if actual != val:
                    print(f"  ❌ 字段 {key}: 期望 {val}, 实际 {actual}")
                    all_pass = False
                else:
                    print(f"  ✅ 字段 {key}: {val}")

    if expected_count is not None and len(parsed_list) != expected_count:
        print(f"\n❌ 数量不符：期望 {expected_count}, 实际 {len(parsed_list)}")
        all_pass = False
    elif expected_count is not None:
        print(f"\n✅ 数量正确: {expected_count}")

    print()
    return all_pass


# ============================================================
# 测试1：单个现货商品
# ============================================================
print("\n" + "#" * 80)
print("# 测试1：单个现货商品（基本场景）")
print("#" * 80)
result1 = run_test(
    "单个现货商品",
    "现货双面革塞纳时光;33x120-1张",
    expected_count=1,
    expected_results=[
        {"material_code": "双面格", "color_code": "标准", "model_code": "33x120",
         "picture_code": "塞纳时光;33x120", "is_stock": True, "num": 1},
    ],
)


# ============================================================
# 测试2：单个现货商品（带cm单位）
# ============================================================
print("\n" + "#" * 80)
print("# 测试2：单个现货商品（带cm单位应去除）")
print("#" * 80)
result2 = run_test(
    "单个现货商品带cm",
    "现货双面革塞纳时光;33x120cm-1张",
    expected_count=1,
    expected_results=[
        {"material_code": "双面格", "color_code": "标准", "model_code": "33x120",
         "picture_code": "塞纳时光;33x120", "is_stock": True, "num": 1},
    ],
)


# ============================================================
# 测试3：现货商品组（同花型多尺寸）
# ============================================================
print("\n" + "#" * 80)
print("# 测试3：现货商品组（同花型多尺寸）")
print("#" * 80)
result3 = run_test(
    "现货商品组",
    "现货双面革安妮森林;35x160-1张, 40x160-1张",
    expected_count=2,
    expected_results=[
        {"material_code": "双面格", "color_code": "标准", "model_code": "35x160",
         "picture_code": "安妮森林;35x160", "is_stock": True, "num": 1},
        {"material_code": "双面格", "color_code": "标准", "model_code": "40x160",
         "picture_code": "安妮森林;40x160", "is_stock": True, "num": 1},
    ],
)


# ============================================================
# 测试4：现货商品组（同花型多尺寸，含cm）
# ============================================================
print("\n" + "#" * 80)
print("# 测试4：现货商品组（多尺寸含cm）")
print("#" * 80)
result4 = run_test(
    "现货商品组带cm",
    "现货双面革安妮森林;35x160cm-1张, 40x160cm-1张",
    expected_count=2,
    expected_results=[
        {"material_code": "双面格", "color_code": "标准", "model_code": "35x160",
         "picture_code": "安妮森林;35x160", "is_stock": True, "num": 1},
        {"material_code": "双面格", "color_code": "标准", "model_code": "40x160",
         "picture_code": "安妮森林;40x160", "is_stock": True, "num": 1},
    ],
)


# ============================================================
# 测试5：用户原图场景（混合定制和现货）
# ============================================================
print("\n" + "#" * 80)
print("# 测试5：用户原图场景（混合定制和现货）")
print("#" * 80)
user_remark = ("定制吸水皮革克罗印花;60x270cm-1张, "
               "现货吸水皮革克罗印花;60x110-2张, 50x120-1张, "
               "定制双面革安妮森林;35x50cm-1张, 36.5x177cm-1张, "
               "现货双面革安妮森林;35x160-1张, 40x160-1张, "
               "现货双面革凡尔赛的梦;70x130-1张, "
               "赠品方垫30x50-4张, "
               "总共14张")
result5 = run_test(
    "用户原图场景",
    user_remark,
    expected_count=8,  # 8个商品 + 赠品
    expected_results=[
        # 1. 定制吸水皮革克罗印花;60x270cm
        {"material_code": "吸水皮革", "color_code": "定制", "is_stock": False},
        # 2. 现货吸水皮革克罗印花;60x110 - 2张
        {"material_code": "吸水皮革", "color_code": "标准", "model_code": "60x110",
         "picture_code": "克罗印花;60x110", "is_stock": True, "num": 2},
        # 3. 现货吸水皮革克罗印花;50x120 - 1张 (继承)
        {"material_code": "吸水皮革", "color_code": "标准", "model_code": "50x120",
         "picture_code": "克罗印花;50x120", "is_stock": True, "num": 1},
        # 4. 定制双面革安妮森林;35x50cm
        {"material_code": "双面格", "color_code": "定制", "is_stock": False},
        # 5. 定制双面革安妮森林;36.5x177cm (继承)
        {"material_code": "双面格", "color_code": "定制", "is_stock": False},
        # 6. 现货双面革安妮森林;35x160
        {"material_code": "双面格", "color_code": "标准", "model_code": "35x160",
         "picture_code": "安妮森林;35x160", "is_stock": True, "num": 1},
        # 7. 现货双面革安妮森林;40x160 (继承)
        {"material_code": "双面格", "color_code": "标准", "model_code": "40x160",
         "picture_code": "安妮森林;40x160", "is_stock": True, "num": 1},
        # 8. 现货双面革凡尔赛的梦;70x130
        {"material_code": "双面格", "color_code": "标准", "model_code": "70x130",
         "picture_code": "凡尔赛的梦;70x130", "is_stock": True, "num": 1},
    ],
)


# ============================================================
# 测试6：现货编码格式直接输入
# ============================================================
print("\n" + "#" * 80)
print("# 测试6：现货编码格式直接输入")
print("#" * 80)
result6 = run_test(
    "现货编码格式",
    "双面格-标准-33x120-塞纳时光;33x120",
    expected_count=1,
    expected_results=[
        {"material_code": "双面格", "color_code": "标准", "model_code": "33x120",
         "picture_code": "塞纳时光;33x120", "is_stock": True},
    ],
)


# ============================================================
# 测试7：现货带赠品
# ============================================================
print("\n" + "#" * 80)
print("# 测试7：现货带赠品")
print("#" * 80)
result7 = run_test(
    "现货带赠品",
    "现货双面革安妮森林;50x120-1张, 赠品方垫30x50-2张",
    expected_count=1,  # 1个商品 + 赠品
)


# ============================================================
# 测试8：纯现货+赠品
# ============================================================
print("\n" + "#" * 80)
print("# 测试8：纯现货+赠品")
print("#" * 80)
result8 = run_test(
    "纯现货+赠品",
    "现货双面革塞纳时光;33x120-1张, 现货双面革安妮森林;40x160-1张, 赠品方垫30x50-1张",
    expected_count=2,
    expected_results=[
        {"material_code": "双面格", "color_code": "标准", "model_code": "33x120",
         "picture_code": "塞纳时光;33x120", "is_stock": True, "num": 1},
        {"material_code": "双面格", "color_code": "标准", "model_code": "40x160",
         "picture_code": "安妮森林;40x160", "is_stock": True, "num": 1},
    ],
)


# ============================================================
# 总结
# ============================================================
print("\n" + "=" * 80)
print("测试总结")
print("=" * 80)
results = [result1, result2, result3, result4, result5, result6, result7, result8]
test_names = ["单个现货商品", "单个现货商品带cm", "现货商品组", "现货商品组带cm",
              "用户原图场景", "现货编码格式", "现货带赠品", "纯现货+赠品"]
for i, (name, r) in enumerate(zip(test_names, results), 1):
    print(f"  测试{i} ({name}): {'✅ 通过' if r else '❌ 失败'}")
all_pass = all(results)
print(f"\n整体结果: {'✅ 全部通过' if all_pass else '❌ 存在失败'}")
print("=" * 80)
