"""
核心 - 卖家备注解析引擎（通用，不依赖任何ERP）

将卖家备注解析为 { material_code, color_code, model_code, picture_code, num }。

参数化设计：
    - material_map: 材质静态映射表（由外部注入）
    - material_matcher: 材质自动匹配回调函数（可选，由外部注入）
"""

import re
import json
from typing import Callable, Optional


class ParsedRemark:
    """备注解析结果"""

    def __init__(
            self,
            material_code: str = "",
            color_code: str = "",
            model_code: str = "",
            picture_code: str = "",
            num: int = 1,
            raw_text: str = "",
            success: bool = False,
            material_source: str = "",
    ):
        self.material_code = material_code
        self.color_code = color_code
        self.model_code = model_code
        self.picture_code = picture_code
        self.num = num
        self.raw_text = raw_text
        self.success = success
        self.material_source = material_source

    @property
    def shop_mapping_sku(self) -> str:
        parts = [self.material_code, self.color_code,
                 self.model_code, self.picture_code]
        return "-".join(parts)

    def __repr__(self) -> str:
        return (
            f"ParsedRemark(success={self.success}, "
            f"material='{self.material_code}'[{self.material_source}], "
            f"color='{self.color_code}', model='{self.model_code}', "
            f"picture='{self.picture_code}', num={self.num}, "
            f"sku='{self.shop_mapping_sku}', raw='{self.raw_text}')"
        )

    def to_dict(self) -> dict:
        return {
            "material_code": self.material_code,
            "color_code": self.color_code,
            "model_code": self.model_code,
            "picture_code": self.picture_code,
            "num": self.num,
            "shop_mapping_sku": self.shop_mapping_sku,
            "raw_text": self.raw_text,
            "success": self.success,
            "material_source": self.material_source,
        }


# ========== 正则 ==========

# 支持小数尺寸：100x100, 57.7x171.2, 100x4000
_RE_SIZE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)?"
)

# 数量匹配：不限于末尾，匹配所有 "-1张", "*2个" 等
# 使用负向前瞻确保不匹配尺寸中的数字（如60x150中的60不应被匹配）
_RE_QTY = re.compile(r"[-*×](\d+)\s*(?:张|个|件|套|米)(?!\s*x|X|×|\*)")

# 花型关键词
_PATTERN_KEYWORDS = ["花幔", "印花", "烫画", "刺绣", "烫金", "激光", "压花", "裁剪有图", "裁剪无图"]


def parse_remark(
        remark_text: str,
        material_map: Optional[dict[str, str]] = None,
        material_matcher: Optional[Callable[[str], tuple[Optional[str], str]]] = None,
) -> ParsedRemark:
    """
    解析卖家备注文本，提取编码字段。

    编码格式: 材质-标准/定制-尺寸/定制尺寸-花型；实际尺寸

    参数:
        remark_text:     卖家备注原文
        material_map:    材质同义词映射表 {备注写法: 系统编码}
        material_matcher: 材质自动匹配回调，接收文本返回(code, source)
    """
    result = ParsedRemark(raw_text=remark_text)
    material_map = material_map or {}

    if not remark_text or not remark_text.strip():
        return result

    text = remark_text.strip()

    # 情况1：已经是编码格式 "材质-标准/定制-尺寸-花型;尺寸"
    if "-" in text and not text.startswith("定制"):
        parts = text.split("-")
        if len(parts) >= 4:
            result.material_code = _map_material(parts[0], material_map)
            result.color_code = parts[1]
            result.model_code = parts[2]
            result.picture_code = "-".join(parts[3:])
            result.num = _extract_qty(text)
            result.success = True
            return result

    # 情况2：解析备注
    is_custom = text.startswith("定制")
    body = text[2:] if is_custom else text

    # 提取数量（取所有匹配中的最大值）
    result.num = _extract_qty(body)

    # 提取所有尺寸
    all_sizes = _extract_all_sizes(body)

    if not all_sizes:
        # 没有尺寸，尝试作为简单模式解析
        return _parse_simple(body, result, is_custom, material_map, material_matcher)

    # 取第一个尺寸作为主尺寸（用于构建编码）
    first_size = all_sizes[0]
    actual_size = f"{first_size[0]}x{first_size[1]}"

    # 提取裁剪类型（裁剪有图/裁剪无图）
    cut_type = ""
    if "裁剪有图" in text:
        cut_type = "裁剪有图"
    elif "裁剪无图" in text:
        cut_type = "裁剪无图"

    # 提取cm后面的备注内容（包含裁剪类型和额外备注，但去掉数量标记如-1张）
    remark_after_size = ""
    cm_match = re.search(r"cm(.*)", text)
    if cm_match:
        after_cm = cm_match.group(1)
        # 去掉数量标记（如-1张），但保留其他内容
        after_cm = re.sub(r"-\d+[张个件套米]", "", after_cm).strip()
        remark_after_size = after_cm.strip().strip(";，,、")

    # 提取花型名称：从分号前的文本中提取（去掉材质和定制前缀后）
    pattern_name = ""
    if ";" in body:
        before_semicolon = body.split(";", 1)[0].strip()
        # 去掉材质名
        for key in sorted(material_map.keys(), key=len, reverse=True):
            if key in before_semicolon:
                pattern_name = before_semicolon.replace(key, "").strip().strip("-;,")
                break
        else:
            pattern_name = before_semicolon.strip().strip("-;,")

    # 如果没有分号，从整个body中提取（去掉材质和尺寸）
    if not pattern_name:
        pattern_name = _extract_pattern(body, material_map)

    # 提取材质
    _parse_material(body, result, material_map, material_matcher)

    if is_custom:
        result.color_code = "定制"
        result.model_code = cut_type if cut_type else "定制尺寸"
        pic_base = pattern_name or result.picture_code or "定制"
        pic_size_part = f"{actual_size}{remark_after_size}" if remark_after_size else actual_size
        result.picture_code = f"{pic_base};{pic_size_part}"
    else:
        result.color_code = "标准"
        result.model_code = actual_size
        pic_base = pattern_name or result.picture_code or "标准"
        pic_size_part = f"{actual_size}{remark_after_size}" if remark_after_size else actual_size
        result.picture_code = f"{pic_base};{pic_size_part}"

    if result.material_code and actual_size:
        result.success = True

    return result


def extract_multiple_remarks(
        remark_text: str,
        material_map: Optional[dict[str, str]] = None,
        material_matcher: Optional[Callable[[str], tuple[Optional[str], str]]] = None,
) -> list[ParsedRemark]:
    """
    从一条备注中提取多个商品信息（多尺寸场景）

    例如：
        "定制吸水皮革楼梯垫浅灰3,100x4000cm一张，浅灰，100x1000cm一张，共计2张"
    → [
        ParsedRemark(...picture='楼梯垫浅灰3;100x4000'),
        ParsedRemark(...picture='楼梯垫浅灰3;100x1000')
      ]
    """
    results = []
    material_map = material_map or {}

    if not remark_text or not remark_text.strip():
        return results

    text = remark_text.strip()

    # 提取所有尺寸
    all_sizes = _extract_all_sizes(text)

    if len(all_sizes) <= 1:
        # 只有一个尺寸或没有尺寸，正常解析
        parsed = parse_remark(text, material_map, material_matcher)
        if parsed.success:
            results.append(parsed)
        return results

    # 先解析一次得到基础解析结果（不含尺寸）
    base_parsed = parse_remark(text, material_map, material_matcher)

    if not base_parsed.success:
        # 尝试直接解析每个尺寸对应的部分
        return _parse_multi_size_direct(text, all_sizes, material_map, material_matcher)

    # 提取共同的材质和花型
    material_code = base_parsed.material_code
    material_source = base_parsed.material_source
    is_custom = text.startswith("定制")

    # 提取裁剪类型（裁剪有图/裁剪无图）
    cut_type = ""
    if "裁剪有图" in text:
        cut_type = "裁剪有图"
    elif "裁剪无图" in text:
        cut_type = "裁剪无图"

    # 提取花型名称（去掉材质和数量后的文本）
    pattern_name = _extract_common_pattern(text, material_code, material_map)

    # 为每个尺寸生成一个解析结果
    for w, h in all_sizes:
        actual_size = f"{w}x{h}"

        # 提取该尺寸对应的cm后面的备注内容
        size_remark = ""
        if cut_type:
            size_remark = cut_type

        if is_custom:
            model_code = cut_type if cut_type else "定制尺寸"
            pic_size_part = f"{actual_size}{size_remark}" if size_remark else actual_size
            picture_code = f"{pattern_name};{pic_size_part}"
            parsed = ParsedRemark(
                material_code=material_code,
                color_code="定制",
                model_code=model_code,
                picture_code=picture_code,
                num=1,
                raw_text=remark_text,
                success=True,
                material_source=material_source,
            )
        else:
            picture_code = f"{pattern_name};{actual_size}"
            parsed = ParsedRemark(
                material_code=material_code,
                color_code="标准",
                model_code=actual_size,
                picture_code=picture_code,
                num=1,
                raw_text=remark_text,
                success=True,
                material_source=material_source,
            )
        results.append(parsed)

    return results


def _extract_all_sizes(text: str) -> list[tuple[str, str]]:
    """提取文本中所有尺寸对"""
    return _RE_SIZE.findall(text)


def _remove_sizes_and_qty(text: str, sizes: list[tuple[str, str]]) -> str:
    """移除文本中的尺寸和数量信息"""
    result = text

    # 移除尺寸（包含单位）
    for w, h in sizes:
        for sep in ["x", "X", "×", "*"]:
            pattern = re.compile(rf"{w}{sep}{h}\s*(?:cm|CM|厘米)?")
            result = pattern.sub("", result)

    # 移除数量信息
    result = _RE_QTY.sub("", result)

    # 移除"共计"、"一张"等残留
    result = re.sub(r"共计\d+张?", "", result)
    result = re.sub(r"\d+张?", "", result)
    result = re.sub(r"一张", "", result)

    # 清理残留的标记符号
    result = result.strip().strip("-;，,、").strip()

    return result


def _extract_common_pattern(text: str, material_code: str, material_map: dict) -> str:
    """提取共同的花型名称"""
    # 去掉前缀"定制"
    body = text
    if body.startswith("定制"):
        body = body[2:]

    # 去掉材质名
    for key in sorted(material_map.keys(), key=len, reverse=True):
        if key in body:
            body = body.replace(key, "").strip()
            break
    else:
        if material_code in body:
            body = body.replace(material_code, "").strip()

    # 去掉尺寸和数量
    body = _RE_SIZE.sub("", body)
    body = _RE_QTY.sub("", body)
    body = re.sub(r"共计\d+张", "", body)
    body = re.sub(r"\d+张", "", body)
    body = re.sub(r"一张", "", body)

    # 清理
    body = body.strip().strip("-;，,、").strip()

    # 如果还有内容，取第一个分号前的部分
    if ";" in body:
        body = body.split(";")[0].strip()

    # 如果还有逗号，取逗号前的部分（通常是花型名）
    if "，" in body:
        body = body.split("，")[0].strip()
    if "," in body:
        body = body.split(",")[0].strip()

    return body or "定制"


def _parse_multi_size_direct(
        text: str,
        sizes: list[tuple[str, str]],
        material_map: dict,
        material_matcher: Callable
) -> list[ParsedRemark]:
    """当单次解析失败时，尝试为每个尺寸直接解析"""
    results = []

    # 简化处理：只提取材质和花型，然后为每个尺寸生成编码
    material_code = ""
    material_source = ""
    is_custom = text.startswith("定制")

    # 提取裁剪类型（裁剪有图/裁剪无图）
    cut_type = ""
    if "裁剪有图" in text:
        cut_type = "裁剪有图"
    elif "裁剪无图" in text:
        cut_type = "裁剪无图"

    # 提取cm后面的备注内容（包含裁剪类型和额外备注，但去掉数量标记如-1张）
    remark_after_size = ""
    cm_match = re.search(r"cm(.*)", text)
    if cm_match:
        after_cm = cm_match.group(1)
        after_cm = re.sub(r"-\d+[张个件套米]", "", after_cm).strip()
        remark_after_size = after_cm.strip().strip(";，,、")

    # 尝试提取材质
    body = text[2:] if is_custom else text
    _parse_material(body, ParsedRemark(), material_map, material_matcher)

    # 提取花型（取第一个尺寸前的文本作为基础花型）
    pattern_name = ""
    for w, h in sizes:
        size_str = f"{w}x{h}"
        idx = text.find(size_str)
        if idx > 0:
            before = text[:idx].strip().strip("-;，,、")
            # 去掉材质
            for key in sorted(material_map.keys(), key=len, reverse=True):
                if key in before:
                    before = before.replace(key, "").strip()
                    break
            pattern_name = before
            break

    material_code = _map_material(body.split(";")[0].strip() if ";" in body else body, material_map)
    if not material_code:
        return results

    for w, h in sizes:
        actual_size = f"{w}x{h}"
        if is_custom:
            model_code = cut_type if cut_type else "定制尺寸"
            pic_size_part = f"{actual_size}{remark_after_size}" if remark_after_size else actual_size
            picture_code = f"{pattern_name};{pic_size_part}" if pattern_name else f"定制;{pic_size_part}"
            parsed = ParsedRemark(
                material_code=material_code,
                color_code="定制",
                model_code=model_code,
                picture_code=picture_code,
                num=1,
                raw_text=text,
                success=True,
                material_source=material_source or "heuristic",
            )
        else:
            pic_size_part = f"{actual_size}{remark_after_size}" if remark_after_size else actual_size
            picture_code = f"{pattern_name};{pic_size_part}" if pattern_name else f"标准;{pic_size_part}"
            parsed = ParsedRemark(
                material_code=material_code,
                color_code="标准",
                model_code=actual_size,
                picture_code=picture_code,
                num=1,
                raw_text=text,
                success=True,
                material_source=material_source or "heuristic",
            )
        results.append(parsed)

    return results


def _parse_simple(body: str, result: ParsedRemark, is_custom: bool,
                  material_map: dict, material_matcher: Callable) -> ParsedRemark:
    """处理没有尺寸的情况"""
    _parse_material(body, result, material_map, material_matcher)

    if is_custom:
        result.color_code = "定制"
        result.model_code = "定制尺寸"
        pic_base = result.picture_code or "定制"
        result.picture_code = f"{pic_base};定制尺寸"
    else:
        result.color_code = "标准"
        result.model_code = "标准"
        pic_base = result.picture_code or "标准"
        result.picture_code = f"{pic_base};标准"

    if result.material_code:
        result.success = True

    return result


def _parse_material(text, result, material_map, material_matcher=None):
    """从文本中提取材质信息"""
    text = text.strip()
    if not text:
        return

    # 1. API 自动匹配
    if material_matcher:
        code, source = material_matcher(text)
        if code:
            result.material_code = code
            result.material_source = source
            _remove_material_remainder(text, code, material_map, result)
            return

    # 2. 静态映射表
    for key in sorted(material_map.keys(), key=len, reverse=True):
        if key in text:
            result.material_code = material_map[key]
            result.material_source = "static"
            _remove_material_remainder(text, key, material_map, result)
            return

    # 3. 启发式（含"革"/"格"）
    if "革" in text or "格" in text:
        m = re.search(r"([\u4e00-\u9fff]+革|[\u4e00-\u9fff]+格)", text)
        if m:
            raw = m.group(1)
            if material_matcher:
                code2, src2 = material_matcher(raw)
                if code2:
                    result.material_code = code2
                    result.material_source = src2
                else:
                    result.material_code = raw
                    result.material_source = "heuristic"
            else:
                result.material_code = _map_material(raw, material_map) or raw
                result.material_source = "heuristic"
            remainder = text.replace(raw, "").strip()
            if remainder and not result.picture_code:
                result.picture_code = remainder
            return

    # 4. 都没识别到 → 作为花型
    if not result.material_code and not result.picture_code:
        result.picture_code = text


def _remove_material_remainder(text, matched_key, material_map, result):
    remainder = text
    for key in sorted(material_map.keys(), key=len, reverse=True):
        if key in remainder:
            remainder = remainder.replace(key, "").strip().strip("-;,")
            break
    else:
        if matched_key in remainder:
            remainder = remainder.replace(matched_key, "").strip().strip("-;,")
    if remainder and not result.picture_code:
        result.picture_code = remainder


def _map_material(raw: str, material_map: dict) -> str:
    raw = raw.strip()
    if raw in material_map:
        return material_map[raw]
    for key, val in material_map.items():
        if key in raw or raw in key:
            return val
    return raw


def _extract_qty(text: str) -> int:
    matches = _RE_QTY.findall(text)
    if matches:
        # 取所有数量中的最大值
        return max(int(m) for m in matches)
    return 1


def _extract_pattern(text: str, material_map: dict = None) -> str:
    """从文本中提取花型名称"""
    material_map = material_map or {}

    text = text.strip().strip("-;,cmCM \t")
    if not text:
        return ""

    # 裁剪有图/裁剪无图是model_code，不是花型名，跳过
    cut_keywords = ["裁剪有图", "裁剪无图"]
    for kw in cut_keywords:
        text = text.replace(kw, "").strip().strip("-;,")

    # 检查其他花型关键词
    non_cut_keywords = [kw for kw in _PATTERN_KEYWORDS if kw not in cut_keywords]
    for kw in non_cut_keywords:
        if kw in text:
            return kw

    # 如果没有关键词，取分号前的文本
    if ";" in text:
        before = text.split(";")[0].strip()
        # 去掉材质
        for key in sorted(material_map.keys(), key=len, reverse=True):
            if key in before:
                before = before.replace(key, "").strip()
                break
        result = before if len(before) <= 20 else before[:20]
    else:
        result = text if len(text) <= 20 else text[:20]

    # 如果结果和材质名相同，返回空让上层使用默认值
    if result:
        for key in material_map:
            if key == result or material_map[key] == result:
                return ""
        for val in material_map.values():
            if val == result:
                return ""

    return result