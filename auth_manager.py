"""
Token管理模块
=============
支持两种模式：
1. 自动登录：客服输入账号密码，程序自动获取Token（推荐）
2. 手动配置：技术人员更新token.json，客服直接使用

功能：
- 自动检测Token是否过期
- 过期前提醒剩余天数
- 自动登录并保存Token
"""

import json
import os
import threading
from datetime import datetime, date, timedelta
from typing import Optional

from auth_client import login as api_login, LoginResult


TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")

_login_callbacks: list = []
_lock = threading.Lock()


class AuthInfo:
    """鉴权信息"""
    def __init__(
        self,
        authorization: str = "",
        cookie_str: str = "",
        tenant_id: str = "",
        expires_at: str = "",
        note: str = "",
        username: str = "",
    ):
        self.authorization = authorization
        self.cookie_str = cookie_str
        self.tenant_id = tenant_id
        self.expires_at = expires_at
        self.note = note
        self.username = username

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
            return "❌ 未登录（请点击「登录」按钮）"
        if not self.is_valid:
            return f"❌ Token已过期（{self.expires_at}），请重新登录"
        days = self.remaining_days
        if days <= 1:
            return f"⚠️ Token即将过期（剩余{days}天），请重新登录"
        user = f" ({self.username})" if self.username else ""
        return f"✅ 已登录{user}（剩余{days}天）"

    def update(self, other: "AuthInfo"):
        """用另一个 AuthInfo 更新自身"""
        if other.authorization:
            self.authorization = other.authorization
        if other.cookie_str:
            self.cookie_str = other.cookie_str
        if other.tenant_id:
            self.tenant_id = other.tenant_id
        if other.expires_at:
            self.expires_at = other.expires_at
        if other.note:
            self.note = other.note
        if other.username:
            self.username = other.username


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
            username=data.get("username", ""),
        )
    except (json.JSONDecodeError, IOError):
        return AuthInfo()


def save_auth(auth: AuthInfo) -> bool:
    """保存鉴权信息到 token.json"""
    try:
        data = {
            "authorization": auth.authorization,
            "cookie_str": auth.cookie_str,
            "tenant_id": auth.tenant_id,
            "expires_at": auth.expires_at,
            "note": auth.note,
            "username": auth.username,
            "_tips": "===== 此文件由程序自动管理，无需手动修改 =====",
            "_how_to": "如需手动更新，请使用程序内的「登录」功能",
        }
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def auto_login(username: str, password: str) -> LoginResult:
    """
    自动登录方果ERP并保存Token到 token.json。

    Args:
        username: 方果账号（手机号）
        password: 登录密码

    Returns:
        LoginResult 对象
    """
    result = api_login(username, password)

    if result.success:
        auth = AuthInfo(
            authorization=f"Bearer {result.access_token}",
            cookie_str=f"JSESSIONID={result.jsessionid}",
            tenant_id=str(result.tenant_id),
            expires_at=_compute_expires_at(result),
            username=username,
        )

        print(f"🔍 新Token信息: tenant={auth.tenant_id}, user={auth.username} (API返回mainUsername={result.main_username})")
        print(f"🔍 新Token前缀: {auth.authorization[:25]}...")

        saved = save_auth(auth)
        print(f"🔍 save_auth() 返回值 = {saved} {'✅' if saved else '❌ 写入失败！'}")

        try:
            from adapters.fangguo.config import reload_auth
            reload_auth()
        except ImportError:
            pass

        _notify_login_callbacks(auth)

    return result


def _compute_expires_at(result: LoginResult) -> str:
    """根据登录结果计算过期日期（默认7天后）"""
    return (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")


def _notify_login_callbacks(auth: AuthInfo):
    """通知所有登录状态变化回调"""
    for cb in _login_callbacks:
        try:
            cb(auth)
        except Exception:
            pass


def register_auth_callback(callback) -> None:
    """
    注册鉴权状态变化回调。
    当Token更新（登录/刷新）时会被调用。
    回调签名: callback(auth: AuthInfo)
    """
    _login_callbacks.append(callback)


def unregister_auth_callback(callback) -> None:
    """取消注册鉴权状态变化回调"""
    if callback in _login_callbacks:
        _login_callbacks.remove(callback)


def reset_auth() -> bool:
    """
    重置鉴权信息（清除Token）。
    用于退出登录。
    """
    return save_auth(AuthInfo())


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


def is_logged_in() -> bool:
    """检查是否已登录（有有效Token）"""
    auth = load_auth()
    return bool(auth.authorization) and auth.is_valid


if __name__ == "__main__":
    # 命令行测试
    auth = load_auth()
    print(f"Authorization: {auth.authorization[:30]}..." if auth.authorization else "❌ 未配置")
    print(f"Cookie: {auth.cookie_str[:30]}..." if auth.cookie_str else "❌ 未配置")
    print(f"Tenant ID: {auth.tenant_id}")
    print(f"状态: {auth.status_text}")