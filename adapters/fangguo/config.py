"""
方果ERP适配器 - 配置
=====================
使用前请修改：
  1. authorization: 从浏览器F12抓取的Bearer Token
  2. tenant_id: 租户ID
  3. cookie_str: JSESSIONID
"""


# 鉴权账号的Token是不定时更新的，需要每天重置
# ========== 账号鉴权 ==========
AUTHORIZATION = "Bearer e3528ed7ea544b1f811a5e227b4d864d"
COOKIE_STR = "JSESSIONID=B24BFB2F112398FACD5C8EC60E497187"
TENANT_ID = "5068663"

# ========== 接口地址 ==========
BASE_URL = "https://fangguo.com"
API_QUERY_ORDER  = f"{BASE_URL}/fgapp/order/shop/trade/queryForPageForTrade"
API_SAVE_PRODUCT = f"{BASE_URL}/fgapp/order/shop/trade/order/saveProduct"
API_ORDER_DETAIL = f"{BASE_URL}/fgapp/order/shop/trade/getDetailsByPage"
API_MATERIAL_LIST = f"{BASE_URL}/fgapp/order/shop/trade/order/materialColorsNew"

# 查询配置也需要更新，不然拉取到的订单信息不会改变
# ========== 查询配置 ==========
QUERY_STATUS = 1       # 1=待整理
PAGE_SIZE = 500
TIME_BEGIN = "2026-07-03 00:00:00"
TIME_END   = "2026-07-07 23:59:59"

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
DRY_RUN = True       # True=仅打印不提交
MAX_ORDERS = 0       # 0=不限制