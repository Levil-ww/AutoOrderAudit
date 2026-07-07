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

# 圆形尺寸：圆直径80cm, 圆80cm
_RE_ROUND_SIZE = re.compile(
    r"圆(?:直径)?\s*(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)?"
)

# 数量匹配：不限于末尾，匹配所有 "-1张", "*2个" 等
# 使用负向前瞻确保不匹配尺寸中的数字（如60x150中的60不应被匹配）
_RE_QTY = re.compile(r"[-*×](\d+)\s*(?:张|个|件|套|米)(?!\s*x|X|×|\*)")

# 花型关键词
_PATTERN_KEYWORDS = ["花幔", "卢浮梦境", "安妮森林", "暗夜缪斯", "萃园", 
"玫瑰骑士", "花园秘境", "复古大花", "中古大花","凯特玫瑰","中古花园",
"中古雨林","复古花丛","森夜私语","莫兰迪","戴安娜","花满金陵","花漾之约",
"花野","简织","克罗印花","路易花坊","流年","曼珠莎华","洛特蔷薇","蔓生花",
"莫比之窗","梦里兰香","莫奈花园","素华牡丹","佩斯","夏洛赫本","星辰漫步",
"馨香","虚拟繁星","烟雨","夜兰图尔","夜眠花影","樱花粉兔","悠米","月夜花影",
"绽蔓","织光造物","庄园秘境","巴洛克之星","白色大理石","柏川","摩登空间",
"圈杏棕熊","柔漪","相伴","线条格纹","欧克","静好","蝴蝶契约","奥斯汀","无尽夏"]


def parse_remark(
        remark_text: str,
        material_map: Optional[dict[str, str]] = None,
        material_matcher: Optional[Callable[[str], tuple[Optional[str], str]]] = None,
) -> ParsedRemark:
    """
    解析卖家备注文本，提取编码字段。

    编码格式: 材质-标准/定制-尺寸/定制尺寸or裁剪有图-花型；实际尺寸

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
    # 在整个文本中搜索"定制"关键字（处理"等通知发 定制..."这种情况）
    custom_pos = text.find("定制")
    is_custom = custom_pos != -1
    body = text[custom_pos:] if is_custom else text

    # 提取数量（取所有匹配中的最大值）
    result.num = _extract_qty(body)

    # 提取所有尺寸
    all_sizes = _extract_all_sizes(body)

    if not all_sizes:
        # 没有尺寸，尝试作为简单模式解析
        return _parse_simple(body, result, is_custom, material_map, material_matcher)

    # 取第一个尺寸作为主尺寸（用于构建编码）
    # 同时提取尺寸前面的描述文本（如"竖版53x60"中的"竖版"）
    first_size = all_sizes[0]
    
    size_prefix = ""
    sizes_with_pos = _extract_all_sizes_with_position(body)
    if sizes_with_pos:
        first_size_start = sizes_with_pos[0][2]
        if first_size_start > 0:
            # 提取尺寸前面的文本（到分号为止）
            before_size = body[:first_size_start].strip()
            # 找到最后一个分号的位置
            last_semi = before_size.rfind(";")
            if last_semi != -1:
                size_prefix = before_size[last_semi + 1:].strip().strip("-;,、")
    
    actual_size = f"{first_size[0]}x{first_size[1]}CM" if first_size[1] != "圆" else f"圆直径{first_size[0]}CM"
    # 如果有尺寸前缀，添加到实际尺寸前面
    if size_prefix:
        actual_size = f"{size_prefix}{actual_size}"

    # 提取裁剪类型（裁剪有图/裁剪无图）
    # ERP系统没有"裁剪无图"选项，所以将其映射为"定制尺寸"
    cut_type = ""
    cut_type_text = ""
    if "裁剪有图" in text:
        cut_type = "裁剪有图"
        cut_type_text = "裁剪有图"
    elif "裁剪无图" in text:
        cut_type = "定制尺寸"
        cut_type_text = "裁剪无图"

    # 提取cm后面的备注内容（包含裁剪类型和额外备注，但去掉数量标记如-1张）
    remark_after_size = ""
    cm_match = re.search(r"cm(.*)", text, re.IGNORECASE)
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
    
    # 去掉可能残留的"定制"前缀
    if pattern_name.startswith("定制"):
        pattern_name = pattern_name[2:].strip()

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
    从一条备注中提取多个商品信息（多尺寸/多花型场景）

    例如：
        "定制吸水皮革楼梯垫浅灰3,100x4000cm一张，浅灰，100x1000cm一张，共计2张"
    → [
        ParsedRemark(...picture='楼梯垫浅灰3;100x4000'),
        ParsedRemark(...picture='楼梯垫浅灰3;100x1000')
      ]
    
    支持每个尺寸有独立描述：
        "等通知发 定制双面革无尽夏;44.5x60cm四个角都是半径5cm的圆角-1张，竖版53x60cm-1张"
    → [
        ParsedRemark(...picture='无尽夏;44.5x60四个角都是半径5cm的圆角'),
        ParsedRemark(...picture='无尽夏;竖版53x60')
      ]
    
    支持不同花型：
        "定制双面革克罗印花;30x50cm-1张，莫比之窗;25x35cm-1张,格子多些..."
    → [
        ParsedRemark(...picture='克罗印花;30x50格子多些...'),
        ParsedRemark(...picture='莫比之窗;25x35格子多些...')
      ]
    """
    results = []
    material_map = material_map or {}

    if not remark_text or not remark_text.strip():
        return results

    text = remark_text.strip()

    # 在整个文本中搜索"定制"关键字（处理"等通知发 定制..."这种情况）
    custom_pos = text.find("定制")
    is_custom = custom_pos != -1
    body = text[custom_pos:] if is_custom else text

    # 将备注分割为独立商品段
    segments, trailing_remark = _split_into_segments(text)

    if not segments:
        # 无法分割，尝试正常解析
        parsed = parse_remark(text, material_map, material_matcher)
        if parsed.success:
            results.append(parsed)
        return results

    # 提取共同的材质信息（从原始文本）
    material_code, material_source = _extract_material_info(body, material_map, material_matcher)
    
    # 为每个商品段独立解析
    for segment, qty in segments:
        # 如果段中没有"定制"关键字，添加前缀以便识别
        if "定制" not in segment and is_custom:
            segment_with_prefix = f"定制{segment}"
        else:
            segment_with_prefix = segment
        
        parsed = parse_remark(segment_with_prefix, material_map, material_matcher)
        
        # 强制使用正确的材质
        if material_code:
            parsed.material_code = material_code
            parsed.material_source = material_source
        
        # 使用从分割段中提取的数量
        parsed.num = qty
        
        if parsed.success or (parsed.material_code and parsed.picture_code):
            # 如果有共享尾部备注，追加到picture_code
            if trailing_remark:
                # 将尾部备注追加到picture_code中的尺寸部分
                if ";" in parsed.picture_code:
                    pattern_part, size_part = parsed.picture_code.split(";", 1)
                    parsed.picture_code = f"{pattern_part};{size_part}{trailing_remark}"
                else:
                    parsed.picture_code = f"{parsed.picture_code};{trailing_remark}"
            
            results.append(parsed)

    return results


def _extract_all_sizes(text: str) -> list[tuple[str, str]]:
    """提取文本中所有尺寸对，包括矩形尺寸和圆形尺寸"""
    sizes = []
    
    # 提取矩形尺寸
    for w, h in _RE_SIZE.findall(text):
        sizes.append((w, h))
    
    # 提取圆形尺寸（作为特殊的尺寸表示）
    for diameter in _RE_ROUND_SIZE.findall(text):
        sizes.append((diameter, "圆"))
    
    return sizes


def _extract_all_sizes_with_position(text: str) -> list[tuple[str, str, int, int]]:
    """提取文本中所有尺寸对，包括位置信息 (w, h, start_pos, end_pos)"""
    sizes_with_pos = []
    
    # 提取矩形尺寸（带位置）
    for match in _RE_SIZE.finditer(text):
        w, h = match.groups()
        sizes_with_pos.append((w, h, match.start(), match.end()))
    
    # 提取圆形尺寸（带位置）
    for match in _RE_ROUND_SIZE.finditer(text):
        diameter = match.group(1)
        sizes_with_pos.append((diameter, "圆", match.start(), match.end()))
    
    # 按位置排序
    sizes_with_pos.sort(key=lambda x: x[2])
    
    return sizes_with_pos


def _extract_material_info(body: str, material_map: dict, material_matcher: Callable) -> tuple[str, str]:
    """提取材质信息，返回 (material_code, material_source)"""
    result = ParsedRemark()
    _parse_material(body, result, material_map, material_matcher)
    return result.material_code, result.material_source


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
    body = _RE_ROUND_SIZE.sub("", body)
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

    # 去掉可能残留的"定制"前缀
    if body.startswith("定制"):
        body = body[2:].strip()

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
    # 在整个文本中搜索"定制"关键字（处理"等通知发 定制..."这种情况）
    custom_pos = text.find("定制")
    is_custom = custom_pos != -1

    # 提取裁剪类型（裁剪有图/裁剪无图）
    # ERP系统没有"裁剪无图"选项，所以将其映射为"定制尺寸"
    cut_type = ""
    cut_type_text = ""
    if "裁剪有图" in text:
        cut_type = "裁剪有图"
        cut_type_text = "裁剪有图"
    elif "裁剪无图" in text:
        cut_type = "定制尺寸"
        cut_type_text = "裁剪无图"

    # 提取cm后面的备注内容（包含裁剪类型和额外备注，但去掉数量标记如-1张）
    remark_after_size = ""
    cm_match = re.search(r"cm(.*)", text, re.IGNORECASE)
    if cm_match:
        after_cm = cm_match.group(1)
        after_cm = re.sub(r"-\d+[张个件套米]", "", after_cm).strip()
        remark_after_size = after_cm.strip().strip(";，,、")

    # 尝试提取材质
    body = text[custom_pos:] if is_custom else text
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
        actual_size = f"{w}x{h}CM"
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


def _extract_size_specific_remark(text: str, start_pos: int, end_pos: int, idx: int, total: int) -> str:
    """
    提取单个尺寸前后的特定描述
    
    对于第一个尺寸：提取尺寸前（上一个尺寸之后）到尺寸之间的文本
    对于其他尺寸：提取上一个尺寸之后到当前尺寸开始之间的文本
    
    同时提取尺寸后面到下一个尺寸或逗号/句号之间的文本（去掉数量标记）
    """
    before_text = ""
    after_text = ""
    
    # 提取尺寸前面的描述（如"竖版53x60"中的"竖版"）
    if idx == 0:
        # 第一个尺寸：从分号或"定制"后开始提取
        before_start = text.rfind(";", 0, start_pos)
        if before_start == -1:
            before_start = text.rfind("定制", 0, start_pos)
            if before_start != -1:
                before_start += 2
        if before_start == -1:
            before_start = 0
        before_text = text[before_start:start_pos].strip().strip("-;,、")
    else:
        # 后续尺寸：从上一个尺寸结束后到当前尺寸开始之间的文本
        # 先找到上一个尺寸的结束位置
        prev_size_end = 0
        size_count = 0
        for match in _RE_SIZE.finditer(text):
            if match.start() >= start_pos:
                break
            prev_size_end = match.end()
            size_count += 1
        if size_count == 0:
            for match in _RE_ROUND_SIZE.finditer(text):
                if match.start() >= start_pos:
                    break
                prev_size_end = match.end()
        
        # 从逗号或数量标记之后开始提取
        comma_after_prev = text.find("，", prev_size_end)
        if comma_after_prev == -1:
            comma_after_prev = text.find(",", prev_size_end)
        
        if comma_after_prev != -1 and comma_after_prev < start_pos:
            # 逗号后面到当前尺寸之间的文本
            between_text = text[comma_after_prev + 1:start_pos].strip().strip("-;,、")
            # 去掉数量标记（如"1张"）
            between_text = re.sub(r"-\d+[张个件套米]", "", between_text).strip()
            between_text = re.sub(r"\d+[张个件套米]", "", between_text).strip()
            before_text = between_text
        else:
            before_text = text[prev_size_end:start_pos].strip().strip("-;,、")
    
    # 提取尺寸后面的描述（到下一个尺寸或逗号/句号为止）
    next_size_pos = len(text)
    for match in _RE_SIZE.finditer(text):
        if match.start() > end_pos:
            next_size_pos = match.start()
            break
    for match in _RE_ROUND_SIZE.finditer(text):
        if match.start() > end_pos and match.start() < next_size_pos:
            next_size_pos = match.start()
    
    # 找逗号或句号
    comma_pos = text.find("，", end_pos)
    if comma_pos == -1:
        comma_pos = text.find(",", end_pos)
    if comma_pos == -1:
        comma_pos = text.find("。", end_pos)
    
    if comma_pos != -1 and comma_pos < next_size_pos:
        after_text = text[end_pos:comma_pos].strip().strip("-;,、")
    else:
        after_text = text[end_pos:next_size_pos].strip().strip("-;,、")
    
    # 去掉数量标记（如"-1张"）
    after_text = re.sub(r"-\d+[张个件套米]", "", after_text).strip().strip("-;,")
    
    # 去掉before_text中的数量标记
    before_text = re.sub(r"-\d+[张个件套米]", "", before_text).strip().strip("-;,")
    before_text = re.sub(r"\d+[张个件套米]", "", before_text).strip().strip("-;,")
    
    # 合并前后描述：对于后续尺寸，before_text（如"竖版"）应该在尺寸前面
    combined = ""
    if before_text:
        combined = before_text
    if after_text:
        if combined:
            combined += after_text
        else:
            combined = after_text
    
    return combined


def _extract_global_remark_after_sizes(text: str) -> str:
    """
    提取所有尺寸之后的全局备注（逗号后面的内容，去掉数量标记）
    
    例如："定制双面革纯黑色;圆直径80cm-1张，需要做效果图后再定制"
    → "需要做效果图后再定制"
    """
    # 找到最后一个尺寸的位置
    last_size_end = 0
    
    for match in _RE_SIZE.finditer(text):
        if match.end() > last_size_end:
            last_size_end = match.end()
    
    for match in _RE_ROUND_SIZE.finditer(text):
        if match.end() > last_size_end:
            last_size_end = match.end()
    
    # 从最后一个尺寸之后找逗号
    comma_pos = text.find("，", last_size_end)
    if comma_pos == -1:
        comma_pos = text.find(",", last_size_end)
    
    if comma_pos == -1:
        return ""
    
    # 提取逗号后面的内容
    after_comma = text[comma_pos + 1:].strip().strip("-;,、")
    
    # 去掉数量标记
    after_comma = re.sub(r"-\d+[张个件套米]", "", after_comma).strip().strip("-;,")
    
    return after_comma


def _split_into_segments(text: str) -> tuple[list[tuple[str, int]], str]:
    """
    将备注文本分割为独立的商品段
    
    分割规则：
    1. 优先按 "-N张，" 或 "-N张," 模式分割（N为数字），这是最明确的记录分隔符
    2. 对于每个分割段：
       - 第一个段保留完整的材质和花型信息
       - 后续段如果包含分号，说明有独立花型名
       - 后续段如果不包含分号，继承前面段的花型名
       - 保留尺寸前面的描述文本（如"竖版53x60"中的"竖版"）
    3. 提取尾部共享备注（最后一个尺寸之后的逗号后面的内容，不包含尺寸）
    
    返回：(segments, trailing_remark)
    - segments: 商品段列表，每个元素为 (segment_text, quantity)
    - trailing_remark: 所有商品段之后的共享备注（如"效果图发给顾客确认下"）
    """
    segments = []
    trailing_remark = ""
    
    # 查找所有 "-N张，"、"-N张,"、"-N张 "（空格）的位置（作为分割点）
    split_pattern = re.compile(r"-\d+[张个件套米](?:[，,]|\s)")
    
    split_positions = []
    for match in split_pattern.finditer(text):
        split_positions.append((match.start(), match.end()))
    
    if split_positions:
        prev_end = 0
        for start, end in split_positions:
            segment = text[prev_end:end].strip()
            if segment:
                # 提取数量（从分割点附近提取）
                qty_match = re.search(r"-(\d+)[张个件套米]", segment)
                qty = int(qty_match.group(1)) if qty_match else 1
                segments.append((segment, qty))
            prev_end = end
        
        last_segment = text[prev_end:].strip()
        if last_segment:
            qty_match = re.search(r"-(\d+)[张个件套米]", last_segment)
            qty = int(qty_match.group(1)) if qty_match else 1
            segments.append((last_segment, qty))
        
        # 过滤掉不包含尺寸的段和以"送"开头的赠品段
        valid_segments = []
        potential_trailing = []
        
        for seg, qty in segments:
            # 跳过以"送"开头的赠品段
            if seg.strip().startswith("送"):
                continue
            
            if _RE_SIZE.search(seg) or _RE_ROUND_SIZE.search(seg):
                valid_segments.append((seg, qty))
            else:
                potential_trailing.append(seg)
        
        segments = valid_segments
        
        # 将潜在的尾部备注合并
        if potential_trailing:
            trailing_remark = "，".join(potential_trailing).strip().strip("-;,、")
        
        # 如果没有找到尾部备注，尝试从最后一个尺寸之后提取
        if not trailing_remark and segments:
            last_size_end = 0
            for match in _RE_SIZE.finditer(text):
                if match.end() > last_size_end:
                    last_size_end = match.end()
            for match in _RE_ROUND_SIZE.finditer(text):
                if match.end() > last_size_end:
                    last_size_end = match.end()
            
            comma_pos = text.find("，", last_size_end)
            if comma_pos == -1:
                comma_pos = text.find(",", last_size_end)
            
            if comma_pos != -1:
                after_comma = text[comma_pos + 1:].strip().strip("-;,、")
                after_comma = re.sub(r"-\d+[张个件套米]", "", after_comma).strip().strip("-;,")
                
                if "送" in after_comma:
                    gift_pos = after_comma.find("送")
                    after_comma = after_comma[:gift_pos].strip().strip("-;,、")
                
                if after_comma and not _RE_SIZE.search(after_comma) and not _RE_ROUND_SIZE.search(after_comma):
                    if trailing_remark:
                        trailing_remark = f"{trailing_remark}，{after_comma}"
                    else:
                        trailing_remark = after_comma
        
        # 为后续段补充花型名（如果没有分号）
        first_pattern = ""
        if segments and ";" in segments[0][0]:
            first_part = segments[0][0].split(";", 1)[0].strip()
            pattern_candidate = first_part
            if pattern_candidate.startswith("定制"):
                pattern_candidate = pattern_candidate[2:].strip()
            for key in ["双面革", "吸水皮革", "双面格", "镜面皮革", "丝圈", "软玻璃"]:
                if key in pattern_candidate:
                    pattern_candidate = pattern_candidate.replace(key, "").strip()
                    break
            if pattern_candidate:
                first_pattern = pattern_candidate
        
        # 为后续段补充花型名，并保留尺寸前面的描述
        processed_segments = []
        for i, (seg, qty) in enumerate(segments):
            cleaned_seg = _clean_segment(seg)
            
            if i == 0:
                processed_segments.append((cleaned_seg, qty))
                continue
            
            if ";" in cleaned_seg:
                processed_segments.append((cleaned_seg, qty))
            else:
                if first_pattern:
                    processed_segments.append((f"{first_pattern};{cleaned_seg}", qty))
                else:
                    processed_segments.append((cleaned_seg, qty))
        
        segments = [s for s in processed_segments if s[0]]
    else:
        # 没有找到分割点，使用原有逻辑（按尺寸分割）
        all_sizes_pos = []
        for match in _RE_SIZE.finditer(text):
            all_sizes_pos.append((match.start(), match.end()))
        for match in _RE_ROUND_SIZE.finditer(text):
            all_sizes_pos.append((match.start(), match.end()))
        all_sizes_pos.sort(key=lambda x: x[0])
        
        if len(all_sizes_pos) <= 1:
            # 只有一个尺寸，整个文本作为一个段
            cleaned = _clean_segment(text)
            if cleaned:
                qty_match = re.search(r"-(\d+)[张个件套米]", text)
                qty = int(qty_match.group(1)) if qty_match else 1
                segments.append((cleaned, qty))
            return segments, trailing_remark
        
        # 查找分号位置
        semi_positions = []
        for match in re.finditer(r";", text):
            semi_positions.append(match.start())
        
        # 分析每个尺寸前面的花型名
        patterns_before_sizes = []
        for i, (size_start, size_end) in enumerate(all_sizes_pos):
            # 找到该尺寸前面的分号
            prev_semi = -1
            for pos in reversed(semi_positions):
                if pos < size_start:
                    prev_semi = pos
                    break
            
            if prev_semi != -1:
                # 找到上一个分号或逗号
                upper_bound = -1
                # 先找分号
                for pos in reversed(semi_positions):
                    if pos < prev_semi:
                        upper_bound = pos
                        break
                
                # 如果没有上一个分号，找逗号
                if upper_bound == -1:
                    comma_pos = text.rfind("，", 0, prev_semi)
                    if comma_pos == -1:
                        comma_pos = text.rfind(",", 0, prev_semi)
                    upper_bound = comma_pos
                
                if upper_bound != -1:
                    pattern_text = text[upper_bound + 1:prev_semi].strip()
                else:
                    # 从开始到该分号
                    pattern_text = text[:prev_semi].strip()
                    # 如果有"定制"前缀，去掉
                    if pattern_text.startswith("定制"):
                        # 去掉材质名
                        for key in ["双面革", "吸水皮革", "双面格", "镜面皮革", "丝圈", "软玻璃"]:
                            if key in pattern_text:
                                pattern_text = pattern_text.replace("定制", "").replace(key, "").strip()
                                break
                patterns_before_sizes.append(pattern_text)
            else:
                patterns_before_sizes.append("")
        
        # 检查是否有不同的花型名
        unique_patterns = set(p for p in patterns_before_sizes if p)
        
        if len(unique_patterns) >= 2:
            # 有不同的花型名，每个尺寸是一个独立商品段
            for i, (size_start, size_end) in enumerate(all_sizes_pos):
                # 找到该尺寸前面的分号
                prev_semi = -1
                for pos in reversed(semi_positions):
                    if pos < size_start:
                        prev_semi = pos
                        break
                
                # 找到下一个尺寸的位置
                next_size_start = len(text)
                if i < len(all_sizes_pos) - 1:
                    next_size_start = all_sizes_pos[i + 1][0]
                
                # 确定段的范围
                if prev_semi != -1:
                    # 找到上一个分号
                    upper_semi = -1
                    for pos in reversed(semi_positions):
                        if pos < prev_semi:
                            upper_semi = pos
                            break
                    
                    if upper_semi != -1:
                        segment_start = upper_semi + 1
                    else:
                        segment_start = 0
                else:
                    segment_start = 0
                
                segment = text[segment_start:next_size_start].strip()
                
                # 跳过赠品段
                if segment.startswith("送"):
                    continue
                
                # 清理
                segment = _clean_segment(segment)
                
                if segment:
                    original_segment = text[segment_start:next_size_start].strip()
                    qty = _extract_qty(original_segment)
                    segments.append((segment, qty))
        else:
            # 花型名相同或没有花型名，是同花型的不同尺寸
            # 为每个尺寸创建独立段，但保留完整的花型信息
            # 提取共同的花型名
            common_pattern = ""
            if semi_positions:
                first_semi = semi_positions[0]
                # 从开始到第一个分号，提取花型名
                pattern_text = text[:first_semi].strip()
                # 如果包含"定制"，从"定制"开始处理
                custom_pos = pattern_text.find("定制")
                if custom_pos != -1:
                    pattern_text = pattern_text[custom_pos:]
                if pattern_text.startswith("定制"):
                    for key in ["双面革", "吸水皮革", "双面格", "镜面皮革", "丝圈", "软玻璃"]:
                        if key in pattern_text:
                            common_pattern = pattern_text.replace("定制", "").replace(key, "").strip()
                            break
            
            for i, (size_start, size_end) in enumerate(all_sizes_pos):
                # 找到该尺寸前面的分号
                prev_semi = -1
                for pos in reversed(semi_positions):
                    if pos < size_start:
                        prev_semi = pos
                        break
                
                # 找到下一个尺寸的位置
                next_size_start = len(text)
                if i < len(all_sizes_pos) - 1:
                    next_size_start = all_sizes_pos[i + 1][0]
                
                # 提取该尺寸的完整描述（从尺寸开始到下一个尺寸开始）
                size_desc = text[size_start:next_size_start].strip()
                
                size_desc = re.sub(r"-\d+[张个件套米]", "", size_desc).strip()
                size_desc = re.sub(r"\d+[张个件套米]", "", size_desc).strip()
                
                if i < len(all_sizes_pos) - 1:
                    comma_pos = size_desc.find("，")
                    if comma_pos == -1:
                        comma_pos = size_desc.find(",")
                    if comma_pos != -1:
                        size_desc = size_desc[:comma_pos].strip()
                
                if i > 0:
                    prev_end = all_sizes_pos[i - 1][1]
                    comma_after_prev = text.find("，", prev_end)
                    if comma_after_prev == -1:
                        comma_after_prev = text.find(",", prev_end)
                    
                    if comma_after_prev != -1 and comma_after_prev < size_start:
                        prefix_text = text[comma_after_prev + 1:size_start].strip().strip("-;,、")
                        size_desc = f"{prefix_text}{size_desc}"
                
                if common_pattern:
                    segment = f"{common_pattern};{size_desc}"
                else:
                    segment = size_desc
                
                if segment.startswith("送"):
                    continue
                
                segment = _clean_segment(segment)
                
                if segment:
                    size_desc_with_qty = text[size_start:next_size_start].strip()
                    qty = _extract_qty(size_desc_with_qty)
                    segments.append((segment, qty))
        
        # 提取共享尾部备注（原有逻辑）
        if segments:
            last_size_end = 0
            for match in _RE_SIZE.finditer(text):
                if match.end() > last_size_end:
                    last_size_end = match.end()
            for match in _RE_ROUND_SIZE.finditer(text):
                if match.end() > last_size_end:
                    last_size_end = match.end()
            
            comma_pos = text.find("，", last_size_end)
            if comma_pos == -1:
                comma_pos = text.find(",", last_size_end)
            
            if comma_pos != -1:
                after_comma = text[comma_pos + 1:].strip().strip("-;,、")
                after_comma = re.sub(r"-\d+[张个件套米]", "", after_comma).strip().strip("-;,")
                
                if "送" in after_comma:
                    gift_pos = after_comma.find("送")
                    after_comma = after_comma[:gift_pos].strip().strip("-;,、")
                
                if not _RE_SIZE.search(after_comma) and not _RE_ROUND_SIZE.search(after_comma) and after_comma:
                    trailing_remark = after_comma
    
    return segments, trailing_remark


def _clean_segment(segment: str) -> str:
    """清理商品段，去掉赠品和数量标记"""
    # 去掉"送..."部分
    gift_pos = segment.find("送")
    if gift_pos != -1:
        segment = segment[:gift_pos].strip()
    
    # 去掉数量标记（如"-1张"）
    segment = re.sub(r"-\d+[张个件套米]", "", segment).strip()
    segment = re.sub(r"\d+[张个件套米]", "", segment).strip()
    
    # 清理结尾符号
    segment = segment.strip().strip("-;,、")
    
    return segment