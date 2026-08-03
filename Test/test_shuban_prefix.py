# -*- coding: utf-8 -*-
"""测试"竖版"尺寸前缀是否会被丢弃"""
import sys
sys.path.insert(0, 'd:/AutoOrderAudit')
from core.parser import extract_multiple_remarks, parse_remark, _split_into_segments

remark = '定制吸水皮革克罗印花;58.5x64cm-1张，63x140cm剪裁有图-1张，竖版58.5x48cm剪裁有图-1张，共3张'

print('===== 分割段测试 =====')
segments, trailing = _split_into_segments(remark)
for i, (seg, qty) in enumerate(segments):
    print(f'段{i+1}: qty={qty}, text="{seg}"')
print(f'trailing_remark: "{trailing}"')
print()

print('===== 多备注解析结果 =====')
material_map = {'吸水皮革': '吸水皮革'}
results = extract_multiple_remarks(remark, material_map)
for i, r in enumerate(results):
    print(f'商品{i+1}:')
    print(f'  材质: {r.material_code}')
    print(f'  色号: {r.color_code}')
    print(f'  型号: {r.model_code}')
    print(f'  花型: {r.picture_code}')
    print(f'  商家编码: {r.shop_mapping_sku}')
    print(f'  数量: {r.num}')
    print(f'  is_stock: {r.is_stock}')
    print()
