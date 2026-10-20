"""
快递管理模块
============
管理省份→快递映射、备注关键词→快递映射、用户自定义覆盖。
支持持久化配置到 express_config.json。

优先级（从高到低）：
1. 备注关键词匹配
2. 用户自定义省份映射
3. 默认省份映射
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from _app_path import get_app_dir


# ── 配置文件路径 ──────────────────────────────────────────
_CONFIG_FILE = get_app_dir() / "express_config.json"

# ── 默认省份映射（来自 Excel：快递规则2026） ──────────────
# 一区/二区/三区 → 极兔；四区/五区 → 中通
_DEFAULT_PROVINCE_MAP = {
    # 一区
    "江苏": "极兔", "浙江": "极兔", "上海": "极兔", "安徽": "极兔",
    # 二区
    "江西": "极兔", "山东": "极兔", "福建": "极兔", "广东": "极兔",
    "北京": "极兔", "天津": "极兔", "湖南": "极兔", "湖北": "极兔",
    "河南": "极兔", "河北": "极兔",
    # 三区
    "重庆": "极兔", "四川": "极兔", "山西": "极兔", "陕西": "极兔",
    "广西": "极兔", "贵州": "极兔", "云南": "极兔", "黑龙江": "极兔",
    "吉林": "极兔", "辽宁": "极兔",
    # 四区
    "海南": "中通", "甘肃": "中通", "内蒙古": "中通", "宁夏": "中通", "青海": "中通",
    # 五区
    "西藏": "中通", "新疆": "中通",
}

# ── 默认备注关键词映射 ────────────────────────────────────
_DEFAULT_KEYWORD_MAP = {
    "发申通": "申通",
    "发极兔": "极兔",
    "发中通": "中通",
    "发顺丰": "顺丰",
    "发圆通": "圆通",
    "发韵达": "韵达",
}

# ── 默认快递编码（名称 → API代码） ────────────────────────
_DEFAULT_EXPRESS_CODES = {
    "中通": "ZTO",
    "极兔": "HTKY",
    "申通": "STO",
    "顺丰": "SF",
    "韵达": "YD",
    "圆通": "YTO",
}


class ExpressManager:
    """快递规则管理器（单例模式）"""

    _instance: "ExpressManager" | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._province_map: dict[str, str] = {}
        self._keyword_map: dict[str, str] = {}
        self._express_codes: dict[str, str] = {}
        self._store_map: dict[str, str] = {}       # 店铺名 → 快递名
        self._platform_map: dict[str, str] = {}     # 平台名 → 快递名
        self._load()

    # ── 持久化 ──────────────────────────────────────────────

    def _load(self):
        """从 JSON 加载用户自定义配置，缺失项用默认值补全"""
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        else:
            data = {}

        self._province_map = dict(data["province_rules"]) if "province_rules" in data else {**_DEFAULT_PROVINCE_MAP, **data.get("province_overrides", {})}
        self._keyword_map = dict(data["remark_keywords"]) if "remark_keywords" in data else {**_DEFAULT_KEYWORD_MAP, **data.get("keyword_overrides", {})}
        self._express_codes = dict(data.get("express_codes", _DEFAULT_EXPRESS_CODES)) if "province_rules" in data else {**_DEFAULT_EXPRESS_CODES, **data.get("express_codes", {})}
        self._store_map = dict(data.get("store_overrides", {}))
        self._platform_map = dict(data.get("platform_overrides", {}))

    def save(self):
        """保存用户自定义配置到 JSON"""
        # 只保存与默认值不同的覆盖项，以及用户新增的快递公司
        province_overrides = {
            k: v for k, v in self._province_map.items()
            if _DEFAULT_PROVINCE_MAP.get(k) != v
        }
        keyword_overrides = {
            k: v for k, v in self._keyword_map.items()
            if _DEFAULT_KEYWORD_MAP.get(k) != v
        }
        # 快递公司：保存默认值中没有的 + 被修改的编码
        express_codes_extra = {
            k: v for k, v in self._express_codes.items()
            if _DEFAULT_EXPRESS_CODES.get(k) != v
        }

        data = {
            "province_rules": dict(self._province_map),
            "remark_keywords": dict(self._keyword_map),
            "province_overrides": province_overrides,
            "keyword_overrides": keyword_overrides,
            "express_codes": dict(self._express_codes),
            "store_overrides": dict(self._store_map),
            "platform_overrides": dict(self._platform_map),
        }
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 查询 ────────────────────────────────────────────────

    def resolve_express(
        self, province: str, remark: str,
        store_name: str = "", platform_name: str = "",
    ) -> tuple[str | None, str | None]:
        """
        根据店铺、平台、省份和备注，解析应使用的快递。

        优先级（从高到低）：
        1. 备注关键词匹配
        2. 店铺精确匹配
        3. 平台匹配
        4. 省份映射

        Returns:
            (快递名称, API编码)  若无法解析则返回 (None, None)
        """
        remark = remark or ""
        province = province or ""
        store_name = store_name or ""
        platform_name = platform_name or ""

        # 1. 备注关键词匹配（最高优先级）
        for keyword, express_name in sorted(self._keyword_map.items(), key=lambda item: len(item[0]), reverse=True):
            if keyword in remark:
                return express_name, self._express_codes.get(express_name)

        # 2. 店铺精确匹配
        if store_name and store_name in self._store_map:
            express_name = self._store_map[store_name]
            return express_name, self._express_codes.get(express_name)

        # 3. 平台匹配
        if platform_name and platform_name in self._platform_map:
            express_name = self._platform_map[platform_name]
            return express_name, self._express_codes.get(express_name)

        # 4. 省份映射（支持带后缀匹配：如"山西省"、"内蒙古自治区"）
        express_name = self._province_map.get(province)
        if not express_name:
            clean = province.rstrip("省市自治区特别行政区壮族回族维吾尔")
            express_name = self._province_map.get(clean)
        if not express_name:
            for suffix in ("省", "市", "自治区", "特别行政区"):
                if province.endswith(suffix):
                    clean = province[:-len(suffix)]
                    express_name = self._province_map.get(clean)
                    if express_name:
                        break
        if express_name:
            return express_name, self._express_codes.get(express_name)

        return None, None

    # ── 配置管理 ────────────────────────────────────────────

    @property
    def province_map(self) -> dict[str, str]:
        return dict(self._province_map)

    @property
    def keyword_map(self) -> dict[str, str]:
        return dict(self._keyword_map)

    @property
    def express_codes(self) -> dict[str, str]:
        return dict(self._express_codes)

    @property
    def all_express_names(self) -> list[str]:
        return sorted(self._express_codes.keys())

    def set_province_express(self, province: str, express_name: str):
        """设置省份对应的快递（用户自定义覆盖）"""
        self._province_map[province] = express_name

    def remove_province_override(self, province: str):
        """移除省份自定义覆盖，恢复默认值"""
        if province in self._province_map:
            default = _DEFAULT_PROVINCE_MAP.get(province)
            if default:
                self._province_map[province] = default
            else:
                del self._province_map[province]

    def add_keyword(self, keyword: str, express_name: str):
        self._keyword_map[keyword] = express_name

    def remove_keyword(self, keyword: str):
        if keyword in self._keyword_map:
            del self._keyword_map[keyword]

    def add_express(self, name: str, code: str):
        """添加新的快递公司"""
        self._express_codes[name] = code

    def remove_express(self, name: str) -> bool:
        """删除快递公司（不能删除默认的）"""
        if name in _DEFAULT_EXPRESS_CODES:
            return False
        if name in self._express_codes:
            del self._express_codes[name]
            # 清理引用该快递的映射
            for k, v in list(self._province_map.items()):
                if v == name:
                    self._province_map[k] = _DEFAULT_PROVINCE_MAP.get(k, "中通")
            for k, v in list(self._keyword_map.items()):
                if v == name:
                    del self._keyword_map[k]
            for k, v in list(self._store_map.items()):
                if v == name:
                    del self._store_map[k]
            for k, v in list(self._platform_map.items()):
                if v == name:
                    del self._platform_map[k]
            return True
        return False

    # ── 店铺/平台映射管理 ──────────────────────────────────

    def set_store_express(self, store_name: str, express_name: str):
        """设置店铺对应的快递"""
        self._store_map[store_name] = express_name

    def remove_store_express(self, store_name: str):
        """移除店铺快递配置"""
        self._store_map.pop(store_name, None)

    def set_platform_express(self, platform_name: str, express_name: str):
        """设置平台对应的快递"""
        self._platform_map[platform_name] = express_name

    def remove_platform_express(self, platform_name: str):
        """移除平台快递配置"""
        self._platform_map.pop(platform_name, None)

    @property
    def store_map(self) -> dict[str, str]:
        return dict(self._store_map)

    @property
    def platform_map(self) -> dict[str, str]:
        return dict(self._platform_map)

    def get_express_code(self, name: str) -> str | None:
        return self._express_codes.get(name)

    def reset_to_default(self):
        """恢复所有默认配置"""
        self._province_map = dict(_DEFAULT_PROVINCE_MAP)
        self._keyword_map = dict(_DEFAULT_KEYWORD_MAP)
        self._express_codes = dict(_DEFAULT_EXPRESS_CODES)
        self._store_map.clear()
        self._platform_map.clear()
        if _CONFIG_FILE.exists():
            os.remove(_CONFIG_FILE)


# ── 便捷函数 ──────────────────────────────────────────────

def get_manager() -> ExpressManager:
    return ExpressManager()
