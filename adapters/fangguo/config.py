"""
方果ERP适配器 - 配置
=====================
使用前请修改：
  1. authorization: 从浏览器F12抓取的Bearer Token
  2. tenant_id: 租户ID
  3. cookie_str: JSESSIONID
"""

# ========== 账号鉴权 ==========
AUTHORIZATION = "Bearer 105fc476116f4956a302ad8bef0f0bc3"
COOKIE_STR = "JSESSIONID=1035D781E281DCFA935D4867ED7E05CF"
TENANT_ID = "5068663"

# ========== 接口地址 ==========
BASE_URL = "https://fangguo.com"
API_QUERY_ORDER  = f"{BASE_URL}/fgapp/order/shop/trade/queryForPageForTrade"
API_SAVE_PRODUCT = f"{BASE_URL}/fgapp/order/shop/trade/order/saveProduct"
API_ORDER_DETAIL = f"{BASE_URL}/fgapp/order/shop/trade/getDetailsByPage"
API_MATERIAL_LIST = f"{BASE_URL}/fgapp/order/shop/trade/order/materialColorsNew"

# ========== 查询配置 ==========
QUERY_STATUS = 1       # 1=待整理
PAGE_SIZE = 500
TIME_BEGIN = "2026-06-29 00:00:00"
TIME_END   = "2026-07-04 23:59:59"

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