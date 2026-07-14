import sys
sys.path.insert(0, 'd:\\AutoOrderAudit')

from core.parser import parse_remark, extract_multiple_remarks
from adapters.fangguo.adapter import FangguoAdapter

print('=' * 80)
print('测试"到货返xx"过滤')
print('=' * 80)

adapter = FangguoAdapter()
material_map = adapter.material_map
material_matcher = adapter.get_material_matcher()

test_cases = [
    {
        'remark': '定制双面革花漾之约;34x260cm-1张，庄园秘境;31x120cm-2张，24x46cm-1张，53x107cm-1张，花间晴;46x92cm-1张，28x52cm-1张，28x54cm-1张，共8张，到货返22',
        'description': '多商品备注，包含"到货返22"',
        'expect_no_refund': True
    },
    {
        'remark': '定制吸水皮革中古花园;60x243cm裁剪有图-1张余料一起发',
        'description': '单商品备注，包含"余料一起发"',
        'expect_remainder': True
    },
    {
        'remark': '定制吸水皮革摩登空间;55x131cm剪裁有图-1张，60x220cm剪裁有图-1张，共2张，剪裁好发出余料一起发',
        'description': '多商品备注，包含"余料一起发"',
        'expect_remainder': True
    },
    {'remark': '定制双面革纯黑色;圆直径80cm-1张，需要做效果图后再定制',
        'description': '单商品备注，包含业务备注',
        'expect_remainder': True,
        'expected_remainder_text': '需要做效果图后再定制'
    },
    {
        'remark': '定制双面革花漾之约;60x120cm-1张，到货返50元',
        'description': '单商品备注，包含"到货返50元"',
        'expect_no_refund': True
    }
]

for tc in test_cases:
    print(f'\n{tc["description"]}')
    print(f'备注原文: {tc["remark"]}')
    
    parsed_list = extract_multiple_remarks(tc['remark'], material_map=material_map, material_matcher=material_matcher)
    
    for i, parsed in enumerate(parsed_list):
        print(f'\n商品{i+1}:')
        print(f'  picture_code: {parsed.picture_code}')
        if '到货返' in parsed.picture_code:
            print(f'  ❌ 错误："到货返"被添加到编码中')
        else:
            print(f'  ✅ 正确："到货返"没有被添加')
        
        expected_text = tc.get('expected_remainder_text', '余料一起发')
        if tc.get('expect_remainder') and expected_text not in parsed.picture_code and i == len(parsed_list) - 1:
            print(f'  ❌ 错误："{expected_text}"没有被添加到最后一个商品')
        elif tc.get('expect_remainder') and expected_text in parsed.picture_code:
            print(f'  ✅ 正确："{expected_text}"被添加到编码中')
