"""测试"实际发"关键字与"现货"处理一致性"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.parser import parse_remark, extract_multiple_remarks
from adapters.fangguo.adapter import FangguoAdapter

adapter = FangguoAdapter()
material_map = adapter.material_map
material_matcher = adapter.get_material_matcher()

passed = 0
failed = 0

def check(name, actual, expected):
    global passed, failed
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if not ok:
        print(f"  期望: {expected}")
        print(f"  实际: {actual}")
        failed += 1
    else:
        passed += 1

# ============================================================
# 测试1: 实际发 - 用户示例
# ============================================================
print("=" * 60)
print("测试1: 实际发吸水皮革克罗印花;60x100cm-1张")
print("=" * 60)
remark = "实际发吸水皮革克罗印花;60x100cm-1张"
result = parse_remark(remark, material_map, material_matcher)
expected_sku = "吸水皮革-标准-60x100-克罗印花;60x100"
check("SKU", result.shop_mapping_sku, expected_sku)
check("is_stock", result.is_stock, True)
check("color_code", result.color_code, "标准")
check("model_code", result.model_code, "60x100")
check("picture_code", result.picture_code, "克罗印花;60x100")

# extract_multiple_remarks
results = extract_multiple_remarks(remark, material_map, material_matcher)
check("extract_multiple_remarks count", len(results), 1)
if results:
    check("extract SKU", results[0].shop_mapping_sku, expected_sku)
    check("extract is_stock", results[0].is_stock, True)

print()

# ============================================================
# 测试2: 现货回归 (确保不破坏)
# ============================================================
print("=" * 60)
print("测试2: 现货回归")
print("=" * 60)
remark2 = "现货吸水皮革克罗印花;60x100cm-1张"
result2 = parse_remark(remark2, material_map, material_matcher)
check("现货 SKU", result2.shop_mapping_sku, expected_sku)
check("现货 is_stock", result2.is_stock, True)

print()

# ============================================================
# 测试3: 定制回归 (确保不破坏)
# ============================================================
print("=" * 60)
print("测试3: 定制回归")
print("=" * 60)
remark3 = "定制吸水皮革克罗印花;60x100cm-1张"
result3 = parse_remark(remark3, material_map, material_matcher)
expected3 = "吸水皮革-定制-定制尺寸-克罗印花;60x100CM"
check("定制 SKU", result3.shop_mapping_sku, expected3)
check("定制 is_stock", result3.is_stock, False)

print()

# ============================================================
# 测试4: 实际发 多尺寸 (继承)
# ============================================================
print("=" * 60)
print("测试4: 实际发 多尺寸继承")
print("=" * 60)
remark4 = "实际发吸水皮革克罗印花;60x100cm-1张, 70x120cm-1张"
results4 = extract_multiple_remarks(remark4, material_map, material_matcher)
check("多尺寸 count", len(results4), 2)
if len(results4) == 2:
    check("第1段 SKU", results4[0].shop_mapping_sku, "吸水皮革-标准-60x100-克罗印花;60x100")
    check("第1段 is_stock", results4[0].is_stock, True)
    check("第2段 SKU", results4[1].shop_mapping_sku, "吸水皮革-标准-70x120-克罗印花;70x120")
    check("第2段 is_stock", results4[1].is_stock, True)

print()

# ============================================================
# 测试5: 定制优先于实际发
# ============================================================
print("=" * 60)
print("测试5: 定制优先于实际发")
print("=" * 60)
remark5 = "实际发定制吸水皮革克罗印花;60x100cm-1张"
result5 = parse_remark(remark5, material_map, material_matcher)
check("定制优先 is_stock", result5.is_stock, False)
check("定制优先 color", result5.color_code, "定制")

print()

# ============================================================
# 总结
# ============================================================
print("=" * 60)
print(f"总计: {passed} PASS, {failed} FAIL")
print("=" * 60)
sys.exit(1 if failed > 0 else 0)
