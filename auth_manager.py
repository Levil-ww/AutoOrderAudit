"""
Token管理模块
=============
从外置 token.json 读取鉴权信息，支持：
1. 技术人员更新token.json即可，客服无需改代码
2. 自动检测Token是否过期
3. 过期前提醒剩余天数
"""

import json
import os
from datetime import datetime, date
from typing import Optional


TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")


class AuthInfo:
    """鉴权信息"""
    def __init__(
        self,
        authorization: str = "",
        cookie_str: str = "",
        tenant_id: str = "",
        expires_at: str = "",  # "2026-07-14"
        note: str = "",
    ):
        self.authorization = authorization
        self.cookie_str = cookie_str
        self.tenant_id = tenant_id
        self.expires_at = expires_at
        self.note = note

    @property
    def is_valid(self) -> bool:
        """Token是否有效（未过期）"""
        if not self.expires_at:
            return bool(self.authorization)
        try:
            expire_date = datetime.strptime(self.expires_at, "%Y-%m-%d").date()
            return date.today() <= expire_date
        except ValueError:
            return bool(self.authorization)

    @property
    def remaining_days(self) -> int:
        """Token剩余有效天数"""
        if not self.expires_at:
            return 999
        try:
            expire_date = datetime.strptime(self.expires_at, "%Y-%m-%d").date()
            delta = (expire_date - date.today()).days
            return max(0, delta)
        except ValueError:
            return 999

    @property
    def status_text(self) -> str:
        """人类可读的状态文本"""
        if not self.authorization:
            return "❌ 未配置Token"
        if not self.is_valid:
            return f"❌ Token已过期（{self.expires_at}）"
        days = self.remaining_days
        if days <= 1:
            return f"⚠️ Token即将过期（剩余{days}天），请找技术人员更新"
        return f"✅ Token有效（剩余{days}天，到期{self.expires_at}）"


def load_auth() -> AuthInfo:
    """
    从 token.json 加载鉴权信息。
    如果文件不存在或格式不对，返回空的 AuthInfo。
    """
    if not os.path.exists(TOKEN_FILE):
        return AuthInfo()

    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return AuthInfo(
            authorization=data.get("authorization", ""),
            cookie_str=data.get("cookie_str", ""),
            tenant_id=data.get("tenant_id", ""),
            expires_at=data.get("expires_at", ""),
            note=data.get("note", ""),
        )
    except (json.JSONDecodeError, IOError):
        return AuthInfo()


def save_auth(auth: AuthInfo) -> bool:
    """保存鉴权信息到 token.json（给技术人员用的写工具）"""
    try:
        data = {
            "authorization": auth.authorization,
            "cookie_str": auth.cookie_str,
            "tenant_id": auth.tenant_id,
            "expires_at": auth.expires_at,
            "note": auth.note,
            "_tips": "===== 技术人员修改此文件 =====",
            "_how_to": "1. 登录方果ERP → F12 → Application → 复制Token/Cookie",
            "_how_to2": "2. 更新下方 authorization 和 cookie_str 的值",
            "_how_to3": "3. expires_at 设为Token到期日期（格式：2026-07-14）",
            "_how_to4": "4. 保存后发给客服覆盖即可",
        }
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def create_token_template():
    """创建 token.json 模板文件（如果不存在）"""
    if os.path.exists(TOKEN_FILE):
        return

    save_auth(AuthInfo(
        authorization="Bearer e3528ed7ea544b1f811a5e227b4d864d",
        cookie_str="JSESSIONID=B24BFB2F112398FACD5C8EC60E497187",
        tenant_id="5068663",
        expires_at="2026-07-14",
        note="示例Token，请替换为实际值",
    ))
    print(f"✅ 已创建 Token 配置文件: {TOKEN_FILE}")


# ========== 便捷函数 ==========

def get_auth_status() -> str:
    """获取Token状态的简短文本，供GUI显示"""
    auth = load_auth()
    return auth.status_text


def get_authorization() -> str:
    return load_auth().authorization


def get_cookie_str() -> str:
    return load_auth().cookie_str


def get_tenant_id() -> str:
    return load_auth().tenant_id


if __name__ == "__main__":
    # 命令行测试
    auth = load_auth()
    print(f"Authorization: {auth.authorization[:30]}..." if auth.authorization else "❌ 未配置")
    print(f"Cookie: {auth.cookie_str[:30]}..." if auth.cookie_str else "❌ 未配置")
    print(f"Tenant ID: {auth.tenant_id}")
    print(f"状态: {auth.status_text}")