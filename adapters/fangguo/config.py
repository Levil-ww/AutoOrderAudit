"""
方果ERP适配器 - 配置（增强版）
=============================
相较于原 config.py 的改进：
  1. Token 从外置 token.json 读取，客服无需改代码
  2. 时间范围自动计算为「最近7天」
  3. 技术人员只需更新 token.json 即可
"""

from datetime import datetime, timedelta

from auth_manager import get_authorization, get_cookie_str, get_tenant_id


# ========== 账号鉴权（自动从 token.json 读取） ==========
AUTHORIZATION = get_authorization()
COOKIE_STR = get_cookie_str()
TENANT_ID = get_tenant_id()

# ========== 接口地址 ==========
BASE_URL = "https://fangguo.com"
API_QUERY_ORDER  = f"{BASE_URL}/fgapp/order/shop/trade/queryForPageForTrade"
API_SAVE_PRODUCT = f"{BASE_URL}/fgapp/order/shop/trade/order/saveProduct"
API_ORDER_DETAIL = f"{BASE_URL}/fgapp/order/shop/trade/getDetailsByPage"
API_MATERIAL_LIST = f"{BASE_URL}/fgapp/order/shop/trade/order/materialColorsNew"

# ========== 查询配置 ==========
QUERY_STATUS = 1       # 1=待整理
PAGE_SIZE = 500

# ========== ✨ 7天滚动时间范围 ==========
# 自动计算：往前推6天 ~ 今天
# 客服无需手动改任何日期
_SEVEN_DAYS_AGO = datetime.now() - timedelta(days=6)
TIME_BEGIN = _SEVEN_DAYS_AGO.strftime("%Y-%m-%d 00:00:00")
TIME_END   = datetime.now().strftime("%Y-%m-%d 23:59:59")

# ========== 材质同义词映射 ==========
MATERIAL_MAP = {
    "双面芊": "双面格",
    "双面革": "双面格",
    "双面格": "双面格",
    "pu防水": "pu防水",
    "别墅橡胶垫": "别墅橡胶垫",
    "定制": "定制",
    "多尼尔提花": "多尼尔提花",
    "防辣椒油": "防辣椒油",
    "镜面皮革": "镜面皮革",
    "镜面革": "镜面皮革",
    "镜面皮革卷材": "镜面皮革卷材",
    "泡泡绒兔毛": "泡泡绒兔毛",
    "软玻璃" : "软玻璃",
    "丝圈": "丝圈",
    "吸水皮革": "吸水皮革",
    "有机硅": "有机硅",
    "浴室吸水科技布": "浴室吸水科技布",
    "浴室吸水植绒": "浴室吸水植绒",
    "珍珠纱": "珍珠纱",
    "珍珠纱小地垫": "珍珠纱小地垫",
}

# ========== 运行模式 ==========
DRY_RUN = False       # False=打印提交（初次使用建议True测试）
# DRY_RUN = True       # True=仅打印不提交（初次使用建议True测试）
MAX_ORDERS = 0       # 0=不限制


def get_time_range_display() -> str:
    """返回当前时间范围的人类可读文本，供GUI显示"""
    return f"{TIME_BEGIN[:10]} ~ {TIME_END[:10]} (最近7天)"