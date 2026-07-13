"""
方果ERP - 登录客户端
========================
封装方果登录API，实现账号密码自动获取Token。
客服人员只需输入手机号和密码即可登录，无需手动复制Token。

API 端点: POST /fgapp/basic/system/auth/login
生产环境: https://fangguo.com/fgapp/basic/system/auth/login
"""

import requests
from typing import Optional


LOGIN_URL = "https://fangguo.com/fgapp/basic/system/auth/login"


class LoginResult:
    """登录结果"""

    def __init__(
        self,
        success: bool = False,
        access_token: str = "",
        tenant_id: str = "",
        main_username: str = "",
        jsessionid: str = "",
        msg: str = "",
    ):
        self.success = success
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.main_username = main_username
        self.jsessionid = jsessionid
        self.msg = msg

    def __repr__(self) -> str:
        if self.success:
            return (
                f"LoginResult(success=True, user='{self.main_username}', "
                f"tenant={self.tenant_id}, token={self.access_token[:20]}..., "
                f"jsessionid={self.jsessionid[:20]}...)"
            )
        return f"LoginResult(success=False, msg='{self.msg}')"


def login(username: str, password: str) -> LoginResult:
    """
    调用方果ERP登录API，获取Token/Cookie/TenantID。

    Args:
        username: 方果账号（手机号）
        password: 登录密码

    Returns:
        LoginResult 对象
    """
    if not username or not password:
        return LoginResult(success=False, msg="账号和密码不能为空")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://fangguo.com",
        "Referer": "https://fangguo.com/login",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    payload = {"username": username, "password": password}

    try:
        resp = requests.post(
            LOGIN_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.Timeout:
        return LoginResult(success=False, msg="登录超时，请检查网络连接")
    except requests.ConnectionError:
        return LoginResult(success=False, msg="无法连接方果服务器，请检查网络")
    except requests.RequestException as e:
        return LoginResult(success=False, msg=f"网络请求异常: {e}")

    try:
        body = resp.json()
    except ValueError:
        return LoginResult(success=False, msg="登录响应格式异常")

    code = body.get("code")
    msg = body.get("msg", "")

    if code != 0:
        error_map = {
            1002000000: "登录失败，账号密码不正确",
            1002003003: "账号不存在",
            1002000002: "账号已被禁用",
            1002000003: "登录过于频繁，请稍后再试",
            1002000004: "验证码错误",
        }
        user_msg = error_map.get(code, msg or f"登录失败（错误码: {code}）")
        return LoginResult(success=False, msg=user_msg)

    data = body.get("data") or {}
    access_token = data.get("accessToken", "")
    tenant_id = str(data.get("tenantId") or "")
    main_username = str(data.get("mainUsername") or username)

    jsessionid = resp.cookies.get("JSESSIONID", "")

    if not access_token:
        return LoginResult(success=False, msg="登录成功但未获取到Token，请联系技术人员")

    shop_tenant_id = _find_shop_tenant(access_token, jsessionid)
    if not shop_tenant_id:
        print("⚠️ 未找到店铺端tenant，将使用默认tenant")
    else:
        print(f"🔍 找到店铺端: tenant_id={shop_tenant_id}")

    tenant_result = _do_tenant_login(access_token, jsessionid, shop_tenant_id)
    if tenant_result:
        new_token, new_tenant_id = tenant_result
        if new_token:
            print(f"🔑 login/tenant 获取新Token成功: tenant={new_tenant_id}")
            access_token = new_token
            tenant_id = str(new_tenant_id)

    return LoginResult(
        success=True,
        access_token=access_token,
        tenant_id=tenant_id,
        main_username=main_username,
        jsessionid=jsessionid,
        msg="登录成功",
    )


def _find_shop_tenant(access_token: str, jsessionid: str) -> Optional[int]:
    """从权限信息中查找店铺端(type=1)的tenant_id"""
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "cookie": f"JSESSIONID={jsessionid}",
    }
    try:
        resp = requests.get(
            "https://fangguo.com/fgapp/user/system/permission/get-permission-info",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            tenants = (data.get("data") or {}).get("tenants") or []
            for t in tenants:
                if t.get("type") == 1:
                    return t["id"]
            for t in tenants:
                if not t.get("isDefault"):
                    return t["id"]
        return None
    except Exception:
        return None


def _do_tenant_login(access_token: str, jsessionid: str,
                     target_tenant_id: Optional[int] = None) -> Optional[tuple[str, int]]:
    """
    调用 login/tenant API 获取指定tenant上下文的新Token。

    方果需要二次登录才能获得特定tenant的访问权限。
    传入 target_tenant_id 可指定登录到店铺端。
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "cookie": f"JSESSIONID={jsessionid}",
        "from-client": "0",
        "origin": "https://fangguo.com",
        "referer": "https://fangguo.com/login",
    }
    if target_tenant_id:
        headers["tenant-id"] = str(target_tenant_id)
    try:
        body = {}
        if target_tenant_id:
            body["tenantId"] = target_tenant_id
        resp = requests.post(
            "https://fangguo.com/fgapp/user/system/auth/login/tenant",
            json=body,
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                d = data.get("data") or {}
                new_token = d.get("accessToken", "")
                new_tenant_id = d.get("tenantId")
                if new_token:
                    return (new_token, new_tenant_id)
        return None
    except Exception:
        return None


def verify_token(access_token: str, tenant_id: str, jsessionid: str) -> bool:
    """
    验证Token是否有效（调用一个轻量级API测试）。

    使用获取材质列表的API作为探针，因为它是只读且轻量的。
    """
    from adapters.fangguo.config import API_MATERIAL_LIST

    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "cookie": f"JSESSIONID={jsessionid}",
        "tenant-id": tenant_id,
    }
    try:
        resp = requests.post(
            API_MATERIAL_LIST,
            json={"factoryId": 0, "needAll": 1},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("e") == 0 or data.get("code") == 0
        return False
    except Exception:
        return False


def get_shop_tenant(access_token: str, jsessionid: str) -> Optional[str]:
    """
    获取店铺端（business）的 tenant_id。

    方果ERP有工厂端和店铺端两个子系统，
    订单数据在店铺端。登录后默认是工厂端，
    需要用店铺端的 tenant_id 才能查到订单。

    Args:
        access_token: Bearer token
        jsessionid: JSESSIONID

    Returns:
        店铺端的 tenant_id 字符串，如果找不到返回 None
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "cookie": f"JSESSIONID={jsessionid}",
    }
    try:
        resp = requests.get(
            "https://fangguo.com/fgapp/user/system/permission/get-permission-info",
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        tenants = (data.get("data") or {}).get("tenants") or []
        for t in tenants:
            if t.get("type") == 1:
                return str(t["id"])
        for t in tenants:
            if not t.get("isDefault"):
                return str(t["id"])
        if tenants:
            return str(tenants[0]["id"])
        return None
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        result = login(sys.argv[1], sys.argv[2])
        print(result)
    else:
        print("用法: python auth_client.py <username> <password>")