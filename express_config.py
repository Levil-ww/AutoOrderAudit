"""
快递配置模块
=============================
功能：
  1. 根据省份自动选择快递
  2. 根据备注关键词自动选择快递
  3. 支持人工修改省份-快递映射
  4. 支持添加新的快递类型

配置文件：express_config.json（与代码同级目录）
"""

import json
import os
from typing import Dict, List, Optional

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "express_config.json")

# 快递编码映射（快递公司名称 -> ERP编码）
EXPRESS_CODE_MAP = {
    "极兔": "HTKY",
    "中通": "ZTO",
    "申通": "STO",
    "顺丰": "SF",
    "圆通": "YTO",
    "韵达": "YD",
}

# 备注关键词映射（关键词 -> 快递公司名称）
REMARK_KEYWORDS = {
    "发极兔": "极兔",
    "发中通": "中通",
    "发申通": "申通",
    "发顺丰": "顺丰",
    "发圆通": "圆通",
    "发韵达": "韵达",
}

# 默认省份-快递规则（从Excel导入）
DEFAULT_PROVINCE_RULES = {
    "江苏": "极兔",
    "浙江": "极兔",
    "上海": "极兔",
    "安徽": "极兔",
    "江西": "极兔",
    "山东": "极兔",
    "福建": "极兔",
    "广东": "极兔",
    "北京": "极兔",
    "天津": "极兔",
    "湖南": "极兔",
    "湖北": "极兔",
    "河南": "极兔",
    "河北": "极兔",
    "重庆": "极兔",
    "四川": "极兔",
    "山西": "极兔",
    "陕西": "极兔",
    "广西": "极兔",
    "贵州": "极兔",
    "云南": "极兔",
    "黑龙江": "极兔",
    "吉林": "极兔",
    "辽宁": "极兔",
    "海南": "中通",
    "甘肃": "中通",
    "内蒙古": "中通",
    "宁夏": "中通",
    "青海": "中通",
    "西藏": "中通",
    "新疆": "中通",
}


def _default_config() -> dict:
    """返回默认配置结构"""
    return {
        "province_rules": dict(DEFAULT_PROVINCE_RULES),
        "express_codes": dict(EXPRESS_CODE_MAP),
        "remark_keywords": dict(REMARK_KEYWORDS),
        "version": 1,
    }


def load_config() -> dict:
    """加载快递配置，如果不存在则创建默认配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            # 合并可能新增的默认值
            default_cfg = _default_config()
            for key, val in default_cfg.items():
                if key not in config:
                    config[key] = val
            return config
        except Exception as e:
            print(f"[快递配置] 加载失败，使用默认配置: {e}")
            return _default_config()
    else:
        config = _default_config()
        save_config(config)
        return config


def save_config(config: dict) -> bool:
    """保存快递配置到JSON文件"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[快递配置] 保存失败: {e}")
        return False


def get_express_for_province(province: str) -> Optional[str]:
    """
    根据省份获取快递公司名称（如"极兔"、"中通"）
    如果省份为空或不存在映射，返回 None
    """
    if not province:
        return None
    config = load_config()
    rules = config.get("province_rules", {})
    # 尝试精确匹配
    if province in rules:
        return rules[province]
    # 尝试去除"省"、"市"后缀匹配
    province_clean = province.replace("省", "").replace("市", "").replace("自治区", "").replace("壮族", "").replace("回族", "").replace("维吾尔", "")
    for prov, express in rules.items():
        prov_clean = prov.replace("省", "").replace("市", "").replace("自治区", "").replace("壮族", "").replace("回族", "").replace("维吾尔", "")
        if prov_clean == province_clean:
            return express
    return None


def get_express_code(express_name: str) -> Optional[str]:
    """
    根据快递公司名称获取ERP编码（如"ZTO"、"HTKY"）
    """
    if not express_name:
        return None
    config = load_config()
    codes = config.get("express_codes", {})
    return codes.get(express_name)


def get_express_by_remark(remark: str) -> Optional[str]:
    """
    根据备注内容匹配关键词，返回快递公司名称
    优先级按关键词长度降序（更具体的关键词优先）
    """
    if not remark:
        return None
    config = load_config()
    keywords = config.get("remark_keywords", {})
    matched = []
    for keyword, express_name in keywords.items():
        if keyword in remark:
            matched.append((len(keyword), express_name))
    if matched:
        # 匹配最长的关键词（最具体）
        matched.sort(key=lambda x: x[0], reverse=True)
        return matched[0][1]
    return None


def get_all_express_names() -> List[str]:
    """获取所有已配置的快递公司名称列表"""
    config = load_config()
    codes = config.get("express_codes", {})
    return list(codes.keys())


def get_all_province_rules() -> Dict[str, str]:
    """获取所有省份-快递规则"""
    config = load_config()
    return dict(config.get("province_rules", {}))


def update_province_rule(province: str, express_name: str) -> bool:
    """更新省份对应的快递规则"""
    config = load_config()
    if "province_rules" not in config:
        config["province_rules"] = {}
    config["province_rules"][province] = express_name
    return save_config(config)


def add_express_type(name: str, code: str) -> bool:
    """添加新的快递类型"""
    config = load_config()
    if "express_codes" not in config:
        config["express_codes"] = {}
    config["express_codes"][name] = code
    return save_config(config)


def remove_express_type(name: str) -> bool:
    """删除快递类型"""
    config = load_config()
    if "express_codes" in config and name in config["express_codes"]:
        del config["express_codes"][name]
    # 同时清理使用该快递的省份规则
    if "province_rules" in config:
        for prov, expr in list(config["province_rules"].items()):
            if expr == name:
                del config["province_rules"][prov]
    return save_config(config)


def reset_to_default() -> bool:
    """重置为默认配置"""
    return save_config(_default_config())
