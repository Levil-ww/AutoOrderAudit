"""
方果ERP适配器 - 材质数据源
从方果 materialColorsNew 接口拉取材质列表，供解析器做自动匹配。
"""

import time
from difflib import SequenceMatcher
from typing import Optional

import requests

from . import config as fg_config


class FangguoMaterialSource:
    """方果材质数据源"""

    def __init__(self):
        self._materials: list[dict] = []
        self._search_index: list[tuple[str, str, str]] = []
        self._last_fetch_time = 0
        self._cache_ttl = 300

    def fetch(self, force: bool = False) -> list[dict]:
        now = time.time()
        if not force and self._materials and (now - self._last_fetch_time) < self._cache_ttl:
            return self._materials

        headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": fg_config.AUTHORIZATION,
            "content-type": "application/json",
            "cookie": fg_config.COOKIE_STR,
            "tenant-id": fg_config.TENANT_ID,
        }
        try:
            resp = requests.post(
                fg_config.API_MATERIAL_LIST, json={"factoryId": 0, "needAll": 1},
                headers=headers, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("e") == 0:
                self._materials = self._parse_list(data)
        except Exception:
            pass  # 静默降级

        self._last_fetch_time = now
        self._build_index()
        return self._materials

    def _parse_list(self, data: dict) -> list[dict]:
        if "data" in data:
            d = data["data"]
            if isinstance(d, list): return d
            if isinstance(d, dict): return d.get("list") or d.get("records") or []
        return data.get("list") or data.get("rows") or []

    def _build_index(self):
        self._search_index = []
        for m in self._materials:
            code = str(m.get("code") or m.get("materialCode") or m.get("name") or "")
            name = str(m.get("name") or m.get("materialName") or code)
            if code:
                self._search_index.append((code, code, name))
                if name != code:
                    self._search_index.append((name, code, name))

    def match(self, text: str, min_ratio: float = 0.5) -> tuple[Optional[str], float]:
        if not text or not self._search_index:
            return None, 0
        text = text.strip()
        best_code, best_ratio = None, 0
        for keyword, code, _ in self._search_index:
            if keyword and keyword in text:
                ratio = len(keyword) / max(len(text), 1)
                if ratio > best_ratio:
                    best_ratio, best_code = ratio, code
        if not best_code:
            for keyword, code, _ in self._search_index:
                if not keyword: continue
                ratio = SequenceMatcher(None, keyword, text).ratio()
                if len(keyword) <= len(text):
                    for i in range(len(text) - len(keyword) + 1):
                        r = SequenceMatcher(None, keyword, text[i:i+len(keyword)]).ratio()
                        ratio = max(ratio, r)
                if ratio > best_ratio:
                    best_ratio, best_code = ratio, code
        return (best_code, best_ratio) if best_ratio >= min_ratio else (None, best_ratio)

    def matcher_callback(self, text: str) -> tuple[Optional[str], str]:
        """返回 (材质编码, 来源)，符合 parser 的 material_matcher 签名"""
        self.fetch()
        code, ratio = self.match(text)
        return (code, "api") if code else (None, "")


_instance: Optional[FangguoMaterialSource] = None

def get_material_source() -> FangguoMaterialSource:
    global _instance
    if _instance is None:
        _instance = FangguoMaterialSource()
    return _instance