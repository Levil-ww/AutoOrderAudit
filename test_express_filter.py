from core.parser import parse_remark, extract_multiple_remarks, _RE_EXPRESS_DELIVERY

test_cases = [
    '定制双面革安妮森林;58x85CM发中通',
    '定制双面革安妮森林;58x85CM，发中通',
    '定制双面革安妮森林;58x85CM发顺丰',
    '定制双面革安妮森林;58x85CM，发顺丰，裁剪图',
    '定制双面革塞纳时光;33x120CM发德邦快递',
    '定制双面革塞纳时光;33x120CM，发京东物流',
]

print('=== 测试 parse_remark 函数 ===')
for tc in test_cases:
    parsed = parse_remark(tc)
    print(f'输入: {tc}')
    print(f'  SKU: {parsed.shop_mapping_sku}')
    print(f'  picture_code: {parsed.picture_code}')
    has_express = any(keyword in parsed.picture_code for keyword in ['发中通', '发顺丰', '发德邦', '发京东', '发邮政', '发极兔', '发圆通', '发韵达', '发申通'])
    print(f'  快递信息已过滤: {not has_express}')
    print()

print('=== 测试正则表达式 ===')
regex_tests = [
    ('发中通', True),
    ('发顺丰', True),
    ('发德邦', True),
    ('发京东', True),
    ('发邮政', True),
    ('发极兔', True),
    ('发圆通', True),
    ('发韵达', True),
    ('发申通', True),
    ('发中通快递', True),
    ('发顺丰速运', True),
    ('发中通，', True),
    ('发顺丰。', True),
    ('发送', False),
    ('送达', False),
    ('配送', False),
]

print('正则表达式匹配测试:')
all_pass = True
for text, expected in regex_tests:
    match = bool(_RE_EXPRESS_DELIVERY.search(text))
    status = '✅' if match == expected else '❌'
    if match != expected:
        all_pass = False
    print(f'  {status} "{text}": 期望={expected}, 实际={match}')

print()
if all_pass:
    print('✅ 所有测试通过!')
else:
    print('❌ 部分测试失败!')
