import sys
sys.path.insert(0, '.')

from core.parser import _extract_gift

test_cases = [
    ("送沥水垫25cm-1张", "沥水垫25cm"),
    ("送圆垫*1", "圆垫"),
    ("送方垫一张", "方垫"),
    ("赠品：防滑垫", "防滑垫"),
    ("附赠收纳袋", "收纳袋"),
    ("小垫子总共送2个", "小垫子"),
    ("总共送2个小垫子", "小垫子"),
    ("送赠品一张", ""),
    ("定制双面革花漾之约;35.5x124cm-1张，送沥水垫25cm-1张", "沥水垫25cm"),
]

print('=== 测试赠品名称提取 ===')
for remark, expected in test_cases:
    gift_name, gift_num = _extract_gift(remark)
    status = '✅' if gift_name == expected else '❌'
    print(f'{status} 备注: {remark[:40]} -> 赠品名称: "{gift_name}" 数量: {gift_num} (期望: "{expected}")')
