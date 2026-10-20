"""
赠品配置管理模块
================
管理备注赠品识别关键词、固定商品ID/SKUID、商家编码，并持久化到
gift_config.json。审单解析和方果赠品行生成共用同一份配置。
"""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

from _app_path import get_app_dir


_CONFIG_FILE = get_app_dir() / "gift_config.json"


_DEFAULT_GIFTS = {
    "圆垫": {
        "name": "圆垫",
        "title": "赠品沥水垫小圆或小方",
        "shop_sku": "吸水皮革-标准-赠品沥水垫小圆或小方-赠品沥水垫小圆或小方",
        "goods_id": "3806984491654840639",
        "sku_id": "3644348072270850",
        "aliases": ["圆垫", "沥水垫25cm", "沥水垫25厘米", "小圆垫"],
    },
    "方垫": {
        "name": "方垫",
        "title": "赠品沥水垫30x50cm",
        "shop_sku": "吸水皮革-标准-30x50-随机发；30x50",
        "goods_id": "3806985099191386298",
        "sku_id": "3644313731257858",
        "aliases": ["方垫", "30x50", "30*50", "30×50", "沥水垫30x50", "沥水垫30x50cm"],
    },
    "南瓜": {
        "name": "南瓜",
        "title": "赠品南瓜30x40",
        "shop_sku": "双面格-标准-30x40-南瓜;30x40",
        "goods_id": "3836348635373764869",
        "sku_id": "3705146089738242",
        "aliases": ["南瓜", "送南瓜", "赠品南瓜", "赠品南瓜30x40", "南瓜30x40"],
    },
}


def normalize_text(text: str) -> str:
    """用于赠品匹配的轻量归一化。"""
    text = (text or "").lower()
    text = text.replace("×", "x").replace("*", "x").replace("Ｘ", "x")
    text = text.replace("；", ";").replace("：", ":")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"(厘米|公分|cm)", "", text)
    text = re.sub(r"[，,。.;；:：、\-_/\\()（）【】\[\]]", "", text)
    text = text.replace("赠品", "").replace("附赠", "").replace("加送", "").replace("送", "")
    return text


def split_shop_sku(shop_sku: str) -> tuple[str, str, str, str]:
    """将商家编码拆为 material/color/model/picture 四段。"""
    parts = (shop_sku or "").split("-")
    if len(parts) >= 4:
        return parts[0], parts[1], parts[2], "-".join(parts[3:])
    return "", "", "", ""


class GiftManager:
    """赠品规则管理器（单例模式）。"""

    _instance: "GiftManager" | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._gifts: dict[str, dict] = {}
        self._load()

    def _load(self):
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        else:
            data = {}

        gifts = dict(_DEFAULT_GIFTS)
        for name, cfg in data.get("gifts", {}).items():
            gifts[name] = self._normalize_config(cfg, fallback_name=name)
        self._gifts = gifts

    def reload(self):
        self._load()

    def save(self):
        extra = {}
        for name, cfg in self._gifts.items():
            default_cfg = _DEFAULT_GIFTS.get(name)
            if default_cfg is None:
                extra[name] = cfg
            elif default_cfg.get("title") != cfg.get("title") or \
                 default_cfg.get("shop_sku") != cfg.get("shop_sku") or \
                 default_cfg.get("goods_id") != cfg.get("goods_id") or \
                 default_cfg.get("sku_id") != cfg.get("sku_id") or \
                 default_cfg.get("aliases") != cfg.get("aliases"):
                extra[name] = cfg
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"gifts": extra}, f, ensure_ascii=False, indent=2)

    def reset_to_default(self):
        self._gifts = dict(_DEFAULT_GIFTS)
        if _CONFIG_FILE.exists():
            os.remove(_CONFIG_FILE)

    @property
    def gifts(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._gifts.items()}

    @property
    def all_keywords(self) -> list[str]:
        keywords: list[str] = []
        for cfg in self._gifts.values():
            keywords.append(cfg["name"])
            keywords.extend(cfg.get("aliases", []))
        return sorted(set(k for k in keywords if k), key=len, reverse=True)

    @property
    def all_shop_skus(self) -> list[str]:
        return [cfg.get("shop_sku", "") for cfg in self._gifts.values() if cfg.get("shop_sku")]

    def add_gift(self, name: str, title: str, shop_sku: str, goods_id: str, sku_id: str, aliases: list[str] | None = None):
        cfg = {
            "name": name.strip(),
            "title": title.strip() or name.strip(),
            "shop_sku": shop_sku.strip(),
            "goods_id": goods_id.strip(),
            "sku_id": sku_id.strip(),
            "aliases": aliases or [],
        }
        self._gifts[cfg["name"]] = self._normalize_config(cfg, fallback_name=cfg["name"])

    def remove_gift(self, name: str) -> bool:
        if name in _DEFAULT_GIFTS:
            return False
        if name in self._gifts:
            del self._gifts[name]
            return True
        return False

    def get_config(self, gift_name: str) -> dict | None:
        canonical = self.match_gift(gift_name)
        if not canonical:
            return None
        return dict(self._gifts[canonical])

    def match_gift(self, text: str) -> str:
        """返回匹配到的规范赠品名；支持关键词、别名和轻量错字匹配。"""
        raw = text or ""
        norm = normalize_text(raw)
        if not norm:
            return ""

        best_name = ""
        best_score = 0.0
        for name, cfg in self._gifts.items():
            candidates = [name, *cfg.get("aliases", [])]
            for candidate in candidates:
                c_norm = normalize_text(candidate)
                if not c_norm:
                    continue
                if c_norm in norm or norm in c_norm:
                    score = 1.0 + min(len(c_norm), len(norm)) / 100
                else:
                    score = SequenceMatcher(None, norm, c_norm).ratio()
                if score > best_score:
                    best_name = name
                    best_score = score

        if best_score >= 0.78:
            return best_name
        # 短赠品名常见一字错别字（如“南爪”→“南瓜”），在赠品语境下放宽一点。
        if best_name:
            best_norm = normalize_text(best_name)
            if 1 < min(len(norm), len(best_norm)) <= 3 and norm[:1] == best_norm[:1] and best_score >= 0.5:
                return best_name
        return ""

    def _normalize_config(self, cfg: dict, fallback_name: str = "") -> dict:
        name = (cfg.get("name") or fallback_name or "").strip()
        aliases = cfg.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [a.strip() for a in re.split(r"[，,;；\n]+", aliases) if a.strip()]
        aliases = [str(a).strip() for a in aliases if str(a).strip()]
        if name and name not in aliases:
            aliases.insert(0, name)
        return {
            "name": name,
            "title": (cfg.get("title") or name).strip(),
            "shop_sku": (cfg.get("shop_sku") or "").strip(),
            "goods_id": str(cfg.get("goods_id") or "").strip(),
            "sku_id": str(cfg.get("sku_id") or "").strip(),
            "aliases": aliases,
        }


def get_manager() -> GiftManager:
    return GiftManager()
