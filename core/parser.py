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
            gift_name: str = "",
            gift_num: int = 0,
            gifts: list[tuple[str, int]] = None,
            original_tid: str = "",
            shop_remark: str = "",
            is_stock: bool = False,
    ):
        self.material_code = material_code
        self.color_code = color_code
        self.model_code = model_code
        self.picture_code = picture_code
        self.num = num
        self.raw_text = raw_text
        self.success = success
        self.material_source = material_source
        self.gift_name = gift_name
        self.gift_num = gift_num
        self.gifts = gifts or []
        self.original_tid = original_tid
        self.shop_remark = shop_remark
        # 是否现货：现货编码格式为 材质-标准-尺寸-花型;尺寸（无cm/CM单位）
        self.is_stock = is_stock

    @property
    def shop_mapping_sku(self) -> str:
        parts = [self.material_code, self.color_code,
                 self.model_code, self.picture_code]
        return "-".join(parts)

    def __repr__(self) -> str:
        gifts_str = ", ".join([f"'{g[0]}'x{g[1]}" for g in self.gifts]) if self.gifts else f"'{self.gift_name}'x{self.gift_num}"
        return (
            f"ParsedRemark(success={self.success}, "
            f"material='{self.material_code}'[{self.material_source}], "
            f"color='{self.color_code}', model='{self.model_code}', "
            f"picture='{self.picture_code}', num={self.num}, "
            f"sku='{self.shop_mapping_sku}', is_stock={self.is_stock}, raw='{self.raw_text}', "
            f"gifts=[{gifts_str}], "
            f"original_tid='{self.original_tid[:10]}'..., "
            f"shop_remark='{self.shop_remark[:20]}'...)"
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
            "gift_name": self.gift_name,
            "gift_num": self.gift_num,
            "gifts": self.gifts,
            "original_tid": self.original_tid,
            "shop_remark": self.shop_remark,
            "is_stock": self.is_stock,
        }


# ========== 正则 ==========

# 支持小数尺寸：100x100, 57.7x171.2, 100x4000
_RE_SIZE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)?"
)

# 圆形尺寸：圆直径80cm, 圆80cm, 直径80cm，
_RE_ROUND_SIZE = re.compile(
    r"(圆形|圆(?:直径)?|直径)\s*(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)?"
)

# 数量匹配：不限于末尾，匹配所有 "-1张", "*2个" 等
# 使用负向前瞻确保不匹配尺寸中的数字（如60x150中的60不应被匹配）
_RE_QTY = re.compile(r"[-*×](\d+)\s*(?:张|个|件|套|米)(?!\s*x|X|×|\*)")

# 中文数字匹配（支持一到十及常用数量词）
_CHINESE_NUMBERS = r"(?:[一二两三四五六七八九十]|\d+)"

# 数量汇总信息匹配（如"共计两张"、"共三张"、"共计5张"）
_RE_QTY_SUMMARY = re.compile(rf"共(?:计)?{_CHINESE_NUMBERS}[张个件套米]")

# 到货返信息匹配（如"到货返22"、"到货返50元"、"确认收货返差价0.3元"、“返现10 /0.2元”）
_RE_ARRIVAL_REFUND = re.compile(r"(到货返|到货返差价|到货退差价|确认收货返差价|返差价|返现)\d+(?:\.\d+)?[元]?")

# 无关词语匹配（如"桌垫"、"地垫"等，作为后缀时应过滤）
_RE_IRRELEVANT_SUFFIX = re.compile(r"(桌垫|地垫)[，,；;]?")

# 花型关键词
_PATTERN_KEYWORDS = ["花幔", "卢浮梦境", "安妮森林", "暗夜缪斯", "萃园", 
"玫瑰骑士", "花园秘境", "复古大花", "中古大花","凯特玫瑰","中古花园",
"中古雨林","复古花丛","森夜私语","莫兰迪","戴安娜","花满金陵","花漾之约",
"花野","简织","克罗印花","路易花坊","流年","曼珠莎华","洛特蔷薇","蔓生花",
"莫比之窗","梦里兰香","莫奈花园","素华牡丹","佩斯","夏洛赫本","星辰漫步",
"馨香","虚拟繁星","烟雨","夜兰图尔","夜眠花影","樱花粉兔","悠米","月夜花影",
"绽蔓","织光造物","庄园秘境","巴洛克之星","白色大理石","柏川","摩登空间",
"圈杏棕熊","柔漪","相伴","线条格纹","欧克","静好","蝴蝶契约","奥斯汀","无尽夏",
"堇色素颜","青禾手记","风华格调","巴黎左岸","塞纳时光","旧枝漫语","哥特玫瑰","罗拉密码",
"飞屋构想","闲叙青釉","浮游家园","凡尔赛的梦","古巴夏日","繁花说","繁花朵朵","静谧之夜",
"香榭丽舍","平安喜乐","爱丽丝梦境","墨上花开","好多熊熊","青华","奥利奥","花之密语","绽放",
"吉金陌野","雾蓝花信","黑色诗人","浅灰绿","牛油果绿","藏青蓝","菱花白","裴颇浅灰","奶油布丁",
"莫系几何","夏昔","淡蓝夕雾","栀夏花语","简若","晨光","如期而至","侘寂风","汀兰","圣托里尼","蓝色鲸鱼",
"浅灰","深灰","一抹杏黄","抹茶绿","丹若云青","淡蓝相知","苏梦半盏","墨绿物语","日暮晨曦","半沐","涂鸦乐园",
"和颜悦色","殷红甜梦","旅途星海","事事都橙","水泥灰","新中式","祥瑞","花之恋","北欧大理石","童话","雅致恬静",
"归序","遇到童话","纯白色","梅花时节","普安蒂","草柳依依","杏仁白","花开富贵","粉色格子","青蔓","浅陌云雾",
"浅陌倾城","宇宙航行","近水含烟","春意花香","丹华","法卡","一见倾心","初雪悠然","麦田守望","粉色皇冠大理石",
"素缕花肆","夏卫安福","太空兔茶话会","都柏林狂欢","闲叙素年","深邃蓝","里芙","马蒂斯的猫","藏衣鲤锁"]

# 赠品关键词
_GIFT_KEYWORDS = ["送", "赠品", "附赠", "加送"]

# 中文数字映射（一到十）
_CHINESE_NUM_MAP = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def parse_remark(
        remark_text: str,
        material_map: Optional[dict[str, str]] = None,
        material_matcher: Optional[Callable[[str], tuple[Optional[str], str]]] = None,
) -> ParsedRemark:
    """
    解析卖家备注文本，提取编码字段。

    编码格式:
        定制: 材质-定制-定制尺寸/裁剪有图-花型;尺寸CM
        现货: 材质-标准-尺寸-花型;尺寸（无cm/CM单位）

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

    # 情况1：已经是编码格式 "材质-标准/定制-尺寸-花型;尺寸" 或 现货编码 "材质-标准-尺寸-花型;尺寸"
    if "-" in text and not text.startswith("定制") and not text.startswith("现货"):
        parts = text.split("-")
        if len(parts) >= 4 and ";" in parts[-1]:
            result.material_code = _map_material(parts[0], material_map)
            result.color_code = parts[1]
            result.model_code = parts[2]
            result.picture_code = "-".join(parts[3:])
            result.num = _extract_qty(text)
            result.success = True
            # 现货编码特征：color="标准" 且 model为纯尺寸（数字x数字 或 直径/圆形尺寸），无cm/CM
            if result.color_code == "标准" and (
                re.match(r"^[\d.]+[xX×*][\d.]+(?:[圆直径圆形].*)?$", result.model_code)
                or re.match(r"^(?:直径|圆|圆形|圆直径)\d+(?:\.\d+)?$", result.model_code)
            ):
                result.is_stock = True
            return result

    # 情况2：解析备注
    # 检测"定制"或"现货"关键字（处理"等通知发 定制..."这种情况）
    custom_pos = text.find("定制")
    is_custom = custom_pos != -1

    stock_pos = text.find("现货")
    is_stock = stock_pos != -1

    # 优先级：定制优先于现货（如果同时存在，视为定制）
    if is_custom and is_stock:
        is_stock = False

    if is_custom:
        body = text[custom_pos:]
    elif is_stock:
        body = text[stock_pos:]
    else:
        body = text

    # 现货标志
    result.is_stock = is_stock

    # 提取数量（取所有匹配中的最大值）
    result.num = _extract_qty(body)

    # 提取所有尺寸
    all_sizes = _extract_all_sizes(body)

    if not all_sizes:
        _parse_simple(body, result, is_custom, material_map, material_matcher)
        # 现货使用"标准"色
        if is_stock:
            result.color_code = "标准"
            result.is_stock = True
        gifts = _extract_multiple_gifts(text)
        if gifts:
            result.gift_name = gifts[0][0]
            result.gift_num = gifts[0][1]
            result.gifts = gifts
        else:
            result.gift_name = ""
            result.gift_num = 0
            result.gifts = []
        return result

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

    # 去掉尺寸前缀中的"规格"
    if size_prefix.startswith("规格"):
        size_prefix = size_prefix[2:].strip().strip("-;,、")

    # 现货尺寸不带 cm/CM 单位；定制尺寸带 CM 单位
    if is_stock:
        # 现货：尺寸不带单位
        if first_size[1] in ["圆", "圆直径", "直径", "圆形"]:
            actual_size = f"{first_size[1]}{first_size[0]}"
        else:
            actual_size = f"{first_size[0]}x{first_size[1]}"
    else:
        actual_size = f"{first_size[0]}x{first_size[1]}CM" if first_size[1] not in ["圆", "圆直径", "直径", "圆形"] else f"{first_size[1]}{first_size[0]}CM"
    # 如果有尺寸前缀，添加到实际尺寸前面
    if size_prefix:
        actual_size = f"{size_prefix}{actual_size}"

    # 提取裁剪类型（裁剪有图/裁剪无图），现货忽略这些类型
    # ERP系统没有"裁剪无图"选项，所以将其映射为"定制尺寸"
    cut_type = ""
    cut_type_text = ""
    if not is_stock:
        if "裁剪有图" in text or "剪裁有图" in text:
            cut_type = "裁剪有图"
            cut_type_text = "裁剪有图"
        elif "裁剪无图" in text or "剪裁无图" in text:
            cut_type = "定制尺寸"
            cut_type_text = "裁剪无图"

    # 提取cm后面的备注内容（仅定制有效，现货不带单位）
    remark_after_size = ""
    if not is_stock:
        cm_match = re.search(r"cm(.*)", text, re.IGNORECASE)
        if cm_match:
            after_cm = cm_match.group(1)
            # 去掉数量标记（如-1张、*2张），但保留其他内容
            after_cm = re.sub(r"[-*×]\d+[张个件套米]", "", after_cm).strip()
            # 去掉数量汇总信息（如"共计2张"、"共三张"）
            after_cm = _RE_QTY_SUMMARY.sub("", after_cm).strip()
            # 过滤掉"到货返xx"这种无关备注
            after_cm = _RE_ARRIVAL_REFUND.sub("", after_cm).strip()
            # 过滤掉"桌垫"、"地垫"等无关词语
            after_cm = _RE_IRRELEVANT_SUFFIX.sub("", after_cm).strip()

            # 去掉赠品信息：找到最早的赠品关键词位置，然后向前找到分隔符
            # 处理"小垫子总共送3个"这种模式，把"小垫子"也去掉
            gift_pos = -1
            for kw in _GIFT_KEYWORDS:
                pos = after_cm.find(kw)
                if pos != -1:
                    if gift_pos == -1 or pos < gift_pos:
                        gift_pos = pos

            if gift_pos != -1:
                # 向前找到逗号、分号或数量标记
                separator_pos = -1
                for sep in ["，", ",", "；", ";", "-", " "]:
                    pos = after_cm.rfind(sep, 0, gift_pos)
                    if pos > separator_pos:
                        separator_pos = pos

                # 从分隔符位置截断，或者从开头截断（如果没有分隔符）
                if separator_pos != -1:
                    after_cm = after_cm[:separator_pos].strip()
                else:
                    after_cm = ""

            remark_after_size = after_cm.strip().strip(";，,、")

    # 提取花型名称：从分号前的文本中提取（去掉材质和定制/现货前缀后）
    pattern_name = ""
    # 同时支持中文分号和英文分号
    semicolon_pos = body.find(";")
    if semicolon_pos == -1:
        semicolon_pos = body.find("；")
    if semicolon_pos != -1:
        before_semicolon = body[:semicolon_pos].strip()
        # 去掉材质名（先从静态映射表，再从启发式列表）
        for key in sorted(material_map.keys(), key=len, reverse=True):
            if key in before_semicolon:
                pattern_name = before_semicolon.replace(key, "").strip().strip("-;,")
                break
        else:
            for mat in _HEURISTIC_MATERIALS:
                if mat in before_semicolon:
                    pattern_name = before_semicolon.replace(mat, "").strip().strip("-;,")
                    break
            else:
                pattern_name = before_semicolon.strip().strip("-;,")

    # 去掉可能残留的"定制"或"现货"前缀（循环处理）
    while pattern_name.startswith("定制") or pattern_name.startswith("现货"):
        if pattern_name.startswith("定制"):
            pattern_name = pattern_name[2:].strip()
        elif pattern_name.startswith("现货"):
            pattern_name = pattern_name[2:].strip()

    # 先检查是否匹配已知花型关键词（更健壮的方式）
    # 按长度从长到短排序，优先匹配更长的关键词（如"真爱花"优先于"爱花"）
    matched_keyword = ""
    for kw in sorted(_PATTERN_KEYWORDS, key=len, reverse=True):
        if kw in pattern_name:
            matched_keyword = kw
            break

    if matched_keyword:
        # 保留关键词后面的附加信息（如"黑色诗人22#"中的"22#"）
        kw_start = pattern_name.find(matched_keyword)
        kw_end = kw_start + len(matched_keyword)
        suffix = pattern_name[kw_end:].strip().strip("-;,、")
        pattern_name = matched_keyword + suffix
    else:
        # 清理花型名称中的冗余前缀（如"颜色分类:"、"真"、"无痕"等）
        pattern_name = _clean_pattern_name(pattern_name)

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
    elif is_stock:
        # 现货：color=标准, model=尺寸(无cm/CM), picture=花型;尺寸(无cm/CM)
        result.color_code = "标准"
        result.model_code = actual_size
        pic_base = pattern_name or result.picture_code or "标准"
        result.picture_code = f"{pic_base};{actual_size}"
        result.is_stock = True
    else:
        result.color_code = "标准"
        result.model_code = actual_size
        pic_base = pattern_name or result.picture_code or "标准"
        pic_size_part = f"{actual_size}{remark_after_size}" if remark_after_size else actual_size
        result.picture_code = f"{pic_base};{pic_size_part}"

    if result.material_code and actual_size:
        result.success = True

    gifts = _extract_multiple_gifts(text)
    if gifts:
        result.gift_name = gifts[0][0]
        result.gift_num = gifts[0][1]
        result.gifts = gifts
    else:
        result.gift_name = ""
        result.gift_num = 0
        result.gifts = []

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

    自动去重：相同 shop_mapping_sku 的商品行合并数量
    """
    results = []
    material_map = material_map or {}

    if not remark_text or not remark_text.strip():
        return results

    text = remark_text.strip()

    # 在整个文本中搜索"定制"或"现货"关键字（处理"等通知发 定制..."这种情况）
    custom_pos = text.find("定制")
    is_custom = custom_pos != -1
    stock_pos = text.find("现货")
    is_stock_text = stock_pos != -1

    # 优先级：定制优先于现货（如果同时存在，视为定制）
    if is_custom and is_stock_text:
        is_stock_text = False

    if is_custom:
        body = text[custom_pos:]
    elif is_stock_text:
        body = text[stock_pos:]
    else:
        body = text

    # 优先检测是否为直接编码格式（如现货编码 "双面格-标准-33x120-塞纳时光;33x120"）
    # 编码格式的特征：含"-"、不以"定制"/"现货"开头、按"-"分割后>=4段且最后一段含分号
    if "-" in text and not text.startswith("定制") and not text.startswith("现货"):
        parts = text.split("-")
        if len(parts) >= 4 and ";" in parts[-1]:
            encoded_parsed = parse_remark(text, material_map, material_matcher)
            if encoded_parsed.success:
                # 编码格式无需再分割段，直接返回单条结果
                gifts = _extract_multiple_gifts(remark_text)
                if gifts:
                    encoded_parsed.gift_name = gifts[0][0]
                    encoded_parsed.gift_num = gifts[0][1]
                    encoded_parsed.gifts = gifts
                return [encoded_parsed]

    # 将备注分割为独立商品段
    segments, trailing_remark = _split_into_segments(text)

    if not segments:
        # 无法分割，尝试正常解析
        parsed = parse_remark(text, material_map, material_matcher)
        if parsed.success:
            results.append(parsed)
        else:
            gifts = _extract_multiple_gifts(remark_text)
            if gifts:
                results.append(ParsedRemark(
                    gift_name=gifts[0][0],
                    gift_num=gifts[0][1],
                    gifts=gifts,
                    success=False,
                    raw_text=remark_text,
                ))
        return results

    # 为每个商品段独立解析，支持材质和花型继承
    current_material = ""
    current_material_source = ""
    current_pattern = ""

    for idx, (segment, qty) in enumerate(segments):
        # 根据原备注的全局类型决定段前缀
        if "定制" not in segment and "现货" not in segment:
            if is_custom:
                segment_with_prefix = f"定制{segment}"
            elif is_stock_text:
                segment_with_prefix = f"现货{segment}"
            else:
                segment_with_prefix = segment
        else:
            segment_with_prefix = segment

        parsed = parse_remark(segment_with_prefix, material_map, material_matcher)

        # 材质继承逻辑：如果当前段有明确材质，更新current_material；否则继承
        if parsed.material_code:
            current_material = parsed.material_code
            current_material_source = parsed.material_source
        elif current_material:
            parsed.material_code = current_material
            parsed.material_source = current_material_source

        # 花型继承逻辑：如果当前段只有尺寸没有花型名，继承前一段的花型
        if parsed.picture_code and ";" in parsed.picture_code:
            pattern_part, size_part = parsed.picture_code.split(";", 1)
            if not pattern_part.strip() and current_pattern:
                parsed.picture_code = f"{current_pattern};{size_part}"
            elif pattern_part.strip():
                current_pattern = pattern_part.strip()
        elif current_pattern and not parsed.picture_code:
            parsed.picture_code = current_pattern

        parsed.num = qty

        has_real_size = False
        if parsed.picture_code and ";" in parsed.picture_code:
            _, size_part = parsed.picture_code.split(";", 1)
            has_real_size = _RE_SIZE.search(size_part) or _RE_ROUND_SIZE.search(size_part)

        # 更新success标志：如果材质和尺寸都有，视为成功
        if parsed.material_code and has_real_size:
            parsed.success = True

        if parsed.success or (parsed.material_code and parsed.picture_code and has_real_size):
            if not parsed.material_code:
                continue
            # trailing_remark（如'裁剪图一张'）只附加到最后一个商品行
            # 现货段不附加 trailing_remark（保持编码纯净：材质-标准-尺寸-花型;尺寸）
            if trailing_remark and idx == len(segments) - 1 and not parsed.is_stock:
                clean_remark = _RE_QTY_SUMMARY.sub("", trailing_remark).strip().strip("-;,、，")
                # 过滤掉"到货返xx"这种无关备注
                clean_remark = _RE_ARRIVAL_REFUND.sub("", clean_remark).strip().strip("-;,、，")
                # 过滤掉"桌垫"、"地垫"等无关词语
                clean_remark = _RE_IRRELEVANT_SUFFIX.sub("", clean_remark).strip().strip("-;,、，")
                # 再清理一次可能的数量汇总残留（兼容"总"字残留：总共X张）
                clean_remark = re.sub(r'总?共(?:计)?\d+[张个件套米]', '', clean_remark).strip().strip('，,、;；')
                clean_remark = re.sub(r'总?共(?:计)?[一二两三四五六七八九十]+[张个件套米]', '', clean_remark).strip().strip('，,、;；')
                # 过滤掉过滤后剩下的单字无意义残留（如"总"）
                if clean_remark and len(clean_remark) > 1:
                    if ";" in parsed.picture_code:
                        pattern_part, size_part = parsed.picture_code.split(";", 1)
                        parsed.picture_code = f"{pattern_part};{size_part}{clean_remark}"
                    else:
                        parsed.picture_code = f"{parsed.picture_code};{clean_remark}"

            results.append(parsed)

    if results:
        gifts = _extract_multiple_gifts(remark_text)
        if gifts:
            # 赠品仅附加到第一个解析结果，避免多尺寸拆分后赠品数量被重复累加
            first = results[0]
            if not first.gift_name:
                first.gift_name = gifts[0][0]
                first.gift_num = gifts[0][1]
            if not first.gifts:
                first.gifts = gifts
    else:
        gifts = _extract_multiple_gifts(remark_text)
        if gifts:
            result = ParsedRemark(
                gift_name=gifts[0][0],
                gift_num=gifts[0][1],
                gifts=gifts,
                success=False,
                raw_text=remark_text,
            )
            results.append(result)

    # 商品行去重：相同 shop_mapping_sku 的商品合并数量和赠品
    if results:
        unique_results = []
        seen_skus = {}
        for r in results:
            if r.success:
                sku = r.shop_mapping_sku
                if sku in seen_skus:
                    seen_skus[sku].num += r.num
                    if r.gifts:
                        for gift_name, gift_num in r.gifts:
                            found = False
                            for i, (g_name, g_num) in enumerate(seen_skus[sku].gifts):
                                if g_name == gift_name:
                                    seen_skus[sku].gifts[i] = (g_name, g_num + gift_num)
                                    found = True
                                    break
                            if not found:
                                seen_skus[sku].gifts.append((gift_name, gift_num))
                else:
                    seen_skus[sku] = r
                    unique_results.append(r)
            else:
                unique_results.append(r)
        results = unique_results

    return results


def _extract_all_sizes(text: str) -> list[tuple[str, str]]:
    """提取文本中所有尺寸对，包括矩形尺寸和圆形尺寸"""
    # 先找到赠品信息的起始位置，只提取赠品之前的尺寸
    gift_pos = -1
    for kw in _GIFT_KEYWORDS:
        pos = text.find(kw)
        if pos != -1:
            if gift_pos == -1 or pos < gift_pos:
                gift_pos = pos
    
    # 如果有赠品信息，只处理赠品之前的文本
    if gift_pos != -1:
        text = text[:gift_pos]
    
    sizes = []
    
    # 提取矩形尺寸
    for w, h in _RE_SIZE.findall(text):
        sizes.append((w, h))
    
    # 提取圆形尺寸（保留原始前缀格式）
    for prefix, diameter in _RE_ROUND_SIZE.findall(text):
        sizes.append((diameter, prefix))
    
    return sizes


def _extract_all_sizes_with_position(text: str) -> list[tuple[str, str, int, int]]:
    """提取文本中所有尺寸对，包括位置信息 (w, h, start_pos, end_pos)"""
    # 先找到赠品信息的起始位置，只提取赠品之前的尺寸
    gift_pos = -1
    for kw in _GIFT_KEYWORDS:
        pos = text.find(kw)
        if pos != -1:
            if gift_pos == -1 or pos < gift_pos:
                gift_pos = pos
    
    sizes_with_pos = []
    
    # 提取矩形尺寸（带位置）
    for match in _RE_SIZE.finditer(text):
        if gift_pos != -1 and match.start() >= gift_pos:
            continue
        w, h = match.groups()
        sizes_with_pos.append((w, h, match.start(), match.end()))
    
    # 提取圆形尺寸（带位置，保留原始前缀格式）
    for match in _RE_ROUND_SIZE.finditer(text):
        if gift_pos != -1 and match.start() >= gift_pos:
            continue
        prefix, diameter = match.groups()
        sizes_with_pos.append((diameter, prefix, match.start(), match.end()))
    
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
    result = _RE_QTY_SUMMARY.sub("", result)
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
    body = _RE_QTY_SUMMARY.sub("", body)
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
    if "裁剪有图" in text or "剪裁有图" in text:
        cut_type = "裁剪有图"
        cut_type_text = "裁剪有图"
    elif "裁剪无图" in text or "剪裁无图" in text:
        cut_type = "定制尺寸"
        cut_type_text = "裁剪无图"

    # 提取cm后面的备注内容（包含裁剪类型和额外备注，但去掉数量标记如-1张）
    remark_after_size = ""
    cm_match = re.search(r"cm(.*)", text, re.IGNORECASE)
    if cm_match:
        after_cm = cm_match.group(1)
        after_cm = re.sub(r"[-*×]\d+[张个件套米]", "", after_cm).strip()
        after_cm = _RE_QTY_SUMMARY.sub("", after_cm).strip()
        after_cm = _RE_ARRIVAL_REFUND.sub("", after_cm).strip()
        after_cm = _RE_IRRELEVANT_SUFFIX.sub("", after_cm).strip()
        remark_after_size = after_cm.strip().strip(";，,、")

    # 尝试提取材质
    body = text[custom_pos:] if is_custom else text
    temp_result = ParsedRemark()
    _parse_material(body, temp_result, material_map, material_matcher)
    material_code = temp_result.material_code
    material_source = temp_result.material_source

    if not material_code:
        return results

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
            if code.startswith("定制"):
                code = code[2:].strip()
            if code:
                result.material_code = code
                result.material_source = source
                _remove_material_remainder(text, code, material_map, result)
                return

    # 2. 静态映射表
    for key in sorted(material_map.keys(), key=len, reverse=True):
        if key in text:
            code = material_map[key]
            if code.startswith("定制"):
                code = code[2:].strip()
            if code:
                result.material_code = code
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
            
            if result.material_code.startswith("定制"):
                result.material_code = result.material_code[2:].strip()
            
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
        return max(int(m) for m in matches)
    return 1


def _extract_gift(text: str) -> tuple[str, int]:
    """
    从文本中提取赠品信息，返回 (gift_name, gift_num)
    
    支持的格式：
    - "送防滑垫一张" → ("防滑垫", 1)
    - "送沥水垫25cm-1张" → ("沥水垫25cm", 1)
    - "送防滑垫一张，送抹布一块" → ("防滑垫", 1) 只提取第一个赠品
    - "赠品：防滑垫" → ("防滑垫", 1)
    - "附赠收纳袋" → ("收纳袋", 1)
    - "小垫子总共送2个" → ("小垫子", 2)
    - "总共送2个小垫子" → ("小垫子", 2)
    """
    gifts = _extract_multiple_gifts(text)
    if gifts:
        return gifts[0][0], gifts[0][1]
    return "", 0


def _extract_multiple_gifts(text: str) -> list[tuple[str, int]]:
    """
    从文本中提取多个赠品信息，返回 [(gift_name, gift_num), ...]
    
    支持的格式：
    - "送防滑垫一张" → [("防滑垫", 1)]
    - "送沥水垫25cm-1张" → [("沥水垫25cm", 1)]
    - "送防滑垫一张，送抹布一块" → [("防滑垫", 1), ("抹布", 1)]
    - "正常发，送赠品圆垫-2张，赠品方垫-1张" → [("圆垫", 2), ("方垫", 1)]
    - "赠品：防滑垫" → [("防滑垫", 1)]
    - "附赠收纳袋" → [("收纳袋", 1)]
    - "小垫子总共送2个" → [("小垫子", 2)]
    - "总共送2个小垫子" → [("小垫子", 2)]
    
    自动去重：相同赠品名称合并数量
    """
    gifts = []
    
    gift_pattern = re.compile(r"(送|赠品|附赠|加送)\s*([^，,；;\n]*?)[张个件套米]")
    
    for match in gift_pattern.finditer(text):
        keyword = match.group(1)
        content = match.group(2).strip()
        
        if keyword == "送":
            prev_pos = match.start() - 1
            if prev_pos >= 0:
                prev_char = text[prev_pos]
                if prev_char in "发送达放":
                    continue
            
            next_pos = match.start() + 1
            if next_pos < len(text):
                next_char = text[next_pos]
                if next_char in "达发":
                    continue
        
        if not content:
            continue
        
        qty_match = re.search(r"-(\d+)$", content)
        if qty_match:
            gift_num = int(qty_match.group(1))
            gift_text = content[:qty_match.start()].strip()
        else:
            qty_match2 = re.search(r"(\d+)$", content)
            if qty_match2:
                gift_num = int(qty_match2.group(1))
                gift_text = content[:qty_match2.start()].strip()
            else:
                qty_match3 = re.search(r"([一二两三四五六七八九十]+)$", content)
                if qty_match3:
                    chinese_num = qty_match3.group(1)
                    gift_num = _CHINESE_NUM_MAP.get(chinese_num, 1)
                    gift_text = content[:qty_match3.start()].strip()
                else:
                    gift_num = 1
                    gift_text = content
        
        gift_text = gift_text.strip().strip("-;,、，：")
        
        if gift_text and keyword == "送":
            qty_before_match = re.search(r"(\d+)$", content)
            if qty_before_match:
                prev_sep_pos = match.start() - 1
                start_pos = prev_sep_pos
                while start_pos >= 0 and text[start_pos] not in "，,；;、":
                    start_pos -= 1
                start_pos += 1
                if start_pos < prev_sep_pos:
                    before_text = text[start_pos:prev_sep_pos].strip()
                    before_text = re.sub(r"[一二两三四五六七八九十]+[张个件套米]", "", before_text).strip()
                    before_text = re.sub(r"\d+[张个件套米]", "", before_text).strip()
                    before_text = before_text.replace("总共", "").strip()
                    if before_text and before_text not in ["送", keyword]:
                        gift_text = before_text
        
        gift_text = re.sub(r"\d+[张个件套米]", "", gift_text).strip()
        gift_text = re.sub(r"[一二两三四五六七八九十]+[张个件套米]", "", gift_text).strip()
        gift_text = gift_text.replace("总共", "").strip()
        gift_text = re.sub(r"\*(\d+)[张个件套米]?", "", gift_text).strip()
        gift_text = re.sub(r"[-××](\d+)[张个件套米]?", "", gift_text).strip()
        gift_text = gift_text.strip().strip("-;,、，")
        
        if gift_text:
            gift_text = gift_text[:30]
            # 清理"换赠品..."这种"换"前缀（"换"表示替换/更换，噪声词）
            if gift_text.startswith("换赠品") and len(gift_text) > 3:
                gift_text = gift_text[3:].strip()
            elif gift_text.startswith("换") and len(gift_text) > 1 and "赠品" in gift_text[:5]:
                gift_text = gift_text[1:].strip()
            if gift_text.startswith("赠品") and len(gift_text) > 2:
                gift_text = gift_text[2:].strip()

            if gift_text and gift_text not in ["一", "二", "两", "三", "四", "五", "六", "七", "八", "九", "十", "赠品"]:
                gifts.append((gift_text, gift_num))
    
    if not gifts:
        gifts = _extract_gifts_fallback(text)
    
    # 赠品行去重：相同赠品名称合并数量
    unique_gifts = {}
    for gift_name, gift_num in gifts:
        if gift_name in unique_gifts:
            unique_gifts[gift_name] += gift_num
        else:
            unique_gifts[gift_name] = gift_num
    gifts = [(name, num) for name, num in unique_gifts.items()]
    
    return gifts


def _extract_gifts_fallback(text: str) -> list[tuple[str, int]]:
    """
    备用提取逻辑：当正则匹配失败时使用
    """
    gifts = []
    
    gift_start_pos = -1
    matched_keyword = ""
    for kw in _GIFT_KEYWORDS:
        pos = text.find(kw)
        if pos != -1 and (gift_start_pos == -1 or pos < gift_start_pos):
            gift_start_pos = pos
            matched_keyword = kw
    
    if gift_start_pos == -1:
        return gifts
    
    if matched_keyword == "送":
        prev_char = text[gift_start_pos - 1] if gift_start_pos > 0 else ""
        if prev_char and prev_char in "发送达放":
            return gifts
        
        next_pos = gift_start_pos + 1
        if next_pos < len(text):
            next_char = text[next_pos]
            if next_char in "达发":
                return gifts
    
    keyword_len = len(matched_keyword)
    after_keyword = text[gift_start_pos + keyword_len:].strip()
    
    qty_match = re.search(r"^(\d+)[张个件套米]", after_keyword)
    if qty_match and matched_keyword == "送":
        gift_num = int(qty_match.group(1))
        
        before_gift = text[:gift_start_pos].strip()
        
        last_separator = -1
        for sep in ["，", ",", ";", "；", " "]:
            pos = before_gift.rfind(sep)
            if pos > last_separator:
                last_separator = pos
        
        if last_separator != -1:
            gift_name_candidate = before_gift[last_separator + 1:].strip()
            if gift_name_candidate and not _RE_SIZE.search(gift_name_candidate) and not _RE_ROUND_SIZE.search(gift_name_candidate):
                gift_name_candidate = re.sub(r"\d+[张个件套米]", "", gift_name_candidate).strip()
                gift_name_candidate = re.sub(r"[一二两三四五六七八九十]+[张个件套米]", "", gift_name_candidate).strip()
                gift_name_candidate = gift_name_candidate.replace("总共", "").strip()
                gift_name_candidate = gift_name_candidate.strip("-;,、，")
                if gift_name_candidate:
                    gift_name = gift_name_candidate[:30]
                    gifts.append((gift_name, gift_num))
                    return gifts
        
        return gifts
    
    gift_text = after_keyword.strip("-;,、，：")
    
    parts = re.split(r"[，,；;]", gift_text)
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        qty_match = re.search(r"-(\d+)[张个件套米]", part)
        if qty_match:
            gift_num = int(qty_match.group(1))
            gift_name = part[:qty_match.start()].strip()
        else:
            qty_match2 = re.search(r"(\d+)[张个件套米]", part)
            if qty_match2:
                gift_num = int(qty_match2.group(1))
                gift_name = part[:qty_match2.start()].strip()
            else:
                qty_match3 = re.search(r"([一二两三四五六七八九十]+)[张个件套米]", part)
                if qty_match3:
                    chinese_num = qty_match3.group(1)
                    gift_num = _CHINESE_NUM_MAP.get(chinese_num, 1)
                    gift_name = part[:qty_match3.start()].strip()
                else:
                    gift_num = 1
                    gift_name = part
        
        gift_name = gift_name.strip().strip("-;,、，")
        gift_name = re.sub(r"[一二两三四五六七八九十]+[张个件套米]", "", gift_name).strip()
        gift_name = gift_name.strip().strip("-;,、，")
        gift_name = re.sub(r"\*(\d+)[张个件套米]?", "", gift_name).strip()
        gift_name = re.sub(r"[-××](\d+)[张个件套米]?", "", gift_name).strip()
        gift_name = gift_name.strip().strip("-;,、，")
        
        if gift_name:
            gift_name = gift_name[:30]
            if gift_name.startswith("赠品") and len(gift_name) > 2:
                gift_name = gift_name[2:].strip()
            
            gifts.append((gift_name, gift_num))
    
    return gifts


_HEURISTIC_MATERIALS = ["双面革", "吸水皮革", "镜面皮革", "双面格", "软玻璃", "丝圈", "防滑皮革", "仿皮"]

_PATTERN_CLEAN_PREFIXES = ["颜色分类:", "颜色分类", "真", "无痕", "止滑", "规格", "桌垫", "地垫"]

def _clean_pattern_name(pattern_name: str) -> str:
    """清理花型名称中的冗余前缀和无关词语"""
    if not pattern_name:
        return pattern_name
    
    result = pattern_name.strip()
    
    for prefix in _PATTERN_CLEAN_PREFIXES:
        if result.startswith(prefix):
            result = result[len(prefix):].strip().strip("-;,、")
    
    for word in ["桌垫", "地垫"]:
        result = result.replace(word, "").strip().strip("-;,、")
    
    result = result.strip().strip("-;,、")
    
    return result

def _extract_pattern(text: str, material_map: dict = None) -> str:
    """从文本中提取花型名称"""
    material_map = material_map or {}

    text = text.strip().strip("-;,cmCM \t")
    if not text:
        return ""

    # 裁剪有图/裁剪无图是model_code，不是花型名，跳过
    cut_keywords = ["裁剪有图", "剪裁有图"]
    for kw in cut_keywords:
        text = text.replace(kw, "").strip().strip("-;,")

    # 移除赠品信息（在提取花型前）
    for kw in _GIFT_KEYWORDS:
        pos = text.find(kw)
        if pos != -1:
            text = text[:pos].strip().strip("-;,、，")
            break

    # 检查其他花型关键词
    non_cut_keywords = [kw for kw in _PATTERN_KEYWORDS if kw not in cut_keywords]
    for kw in non_cut_keywords:
        if kw in text:
            return kw

    # 如果没有关键词，取分号前的文本
    if ";" in text:
        before = text.split(";")[0].strip()
        # 去掉材质（先从静态映射表，再从启发式列表）
        for key in sorted(material_map.keys(), key=len, reverse=True):
            if key in before:
                before = before.replace(key, "").strip()
                break
        else:
            for mat in _HEURISTIC_MATERIALS:
                if mat in before:
                    before = before.replace(mat, "").strip()
                    break
        result = before if len(before) <= 20 else before[:20]
    else:
        before = text
        for mat in _HEURISTIC_MATERIALS:
            if mat in before:
                before = before.replace(mat, "").strip()
                break
        result = before if len(before) <= 20 else before[:20]

    # 清理花型名称中的冗余前缀（如"颜色分类:"、"真"、"无痕"等）
    result = _clean_pattern_name(result)

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
            between_text = re.sub(r"[-*×]\d+[张个件套米]", "", between_text).strip()
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
    after_text = re.sub(r"[-*×]\d+[张个件套米]", "", after_text).strip().strip("-;,")
    
    # 去掉before_text中的数量标记
    before_text = re.sub(r"[-*×]\d+[张个件套米]", "", before_text).strip().strip("-;,")
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
    after_comma = re.sub(r"[-*×]\d+[张个件套米]", "", after_comma).strip().strip("-;,")
    
    return after_comma


def _split_into_segments(text: str) -> tuple[list[tuple[str, int]], str]:
    """
    将备注文本分割为独立的商品段
    
    分割规则：
    1. 优先检测合并订单：当备注中包含多个"定制"关键字且每个"定制"后面都有尺寸信息时，按"定制"拆分
    2. 其次按 "-N张，"、"N张，" 或 "剪裁有图N张，" 模式分割（N为数字），这是最明确的记录分隔符
    3. 对于每个分割段：
       - 第一个段保留完整的材质和花型信息
       - 后续段如果包含分号，说明有独立花型名
       - 后续段如果不包含分号，继承前面段的花型名
       - 保留尺寸前面的描述文本（如"竖版53x60"中的"竖版"）
    4. 提取尾部共享备注（最后一个尺寸之后的逗号后面的内容，不包含尺寸）
    
    返回：(segments, trailing_remark)
    - segments: 商品段列表，每个元素为 (segment_text, quantity)
    - trailing_remark: 所有商品段之后的共享备注（如"效果图发给顾客确认下"）
    """
    segments = []
    trailing_remark = ""
    
    # ===== 检测合并订单 =====
    # 合并订单的特征：备注中包含多个"定制"关键字，且每个"定制"后面都有尺寸信息
    custom_positions = []
    start_pos = 0
    while True:
        pos = text.find("定制", start_pos)
        if pos == -1:
            break
        custom_positions.append(pos)
        start_pos = pos + 2
    
    # 如果有多个"定制"关键字，检测是否为合并订单
    if len(custom_positions) >= 2:
        is_merged_order = True
        
        # 检查每个"定制"后面是否有尺寸信息
        for i, pos in enumerate(custom_positions):
            segment_candidate = text[pos:pos+100]
            if not _RE_SIZE.search(segment_candidate) and not _RE_ROUND_SIZE.search(segment_candidate):
                is_merged_order = False
                break
        
        # 关键判断：合并订单中，第二个及以后的"定制"前面没有逗号分隔
        # 如果第二个"定制"紧邻前面有逗号（如"做，定制"），说明是同一个订单中的多个商品
        # 如果第二个"定制"前面没有逗号（如"赠品一张定制"），说明是合并订单
        # 只检查前面3个字符，避免误判第一个商品描述中的逗号
        if is_merged_order:
            for i in range(1, len(custom_positions)):
                curr_start = custom_positions[i]
                # 检查"定制"前面3个字符是否有逗号
                look_back = text[max(0, curr_start - 3):curr_start]
                if "，" in look_back or "," in look_back or "；" in look_back or ";" in look_back:
                    is_merged_order = False
                    break
        
        if is_merged_order:
            # 按"定制"关键字拆分
            for i, pos in enumerate(custom_positions):
                if i < len(custom_positions) - 1:
                    end_pos = custom_positions[i + 1]
                    segment = text[pos:end_pos].strip()
                else:
                    segment = text[pos:].strip()
                
                if segment:
                    qty_match = re.search(r"-(\d+)[张个件套米]", segment)
                    qty = int(qty_match.group(1)) if qty_match else 1
                    segments.append((segment, qty))
            
            return segments, trailing_remark
    
    # ===== 原有分割逻辑 =====
    # 查找所有分割点："-N张，"、"N张，"、"剪裁有图N张，"、"剪裁无图N张，"、"-N张 "（空格）等
    # 注意：使用非贪婪匹配，避免跨段匹配
    split_pattern = re.compile(r"(?:-)?\d+[张个件套米](?:[，,；;]|\s+)")
    
    split_positions = []
    for match in split_pattern.finditer(text):
        split_positions.append((match.start(), match.end()))
    
    if split_positions:
        prev_end = 0
        for start, end in split_positions:
            segment = text[prev_end:end].strip()
            
            has_gift = False
            for kw in _GIFT_KEYWORDS:
                if kw in segment:
                    has_gift = True
                    break
            
            if has_gift:
                prev_end = end
                continue
            
            if segment:
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
            has_gift = False
            for kw in _GIFT_KEYWORDS:
                if kw in seg:
                    has_gift = True
                    break
            if has_gift:
                continue
            
            if _RE_SIZE.search(seg) or _RE_ROUND_SIZE.search(seg):
                valid_segments.append((seg, qty))
            else:
                potential_trailing.append(seg)
        
        segments = valid_segments
        
        # 将潜在的尾部备注合并，过滤掉赠品信息
        if potential_trailing:
            filtered_trailing = []
            for seg in potential_trailing:
                has_gift = False
                for kw in _GIFT_KEYWORDS:
                    if kw in seg:
                        has_gift = True
                        break
                if not has_gift:
                    filtered_trailing.append(seg)
            trailing_remark = "，".join(filtered_trailing).strip().strip("-;,、")
        
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
                after_comma = re.sub(r"[-*×]\d+[张个件套米]", "", after_comma).strip().strip("-;,")
                
                gift_pos = -1
                for kw in _GIFT_KEYWORDS:
                    pos = after_comma.find(kw)
                    if pos != -1 and (gift_pos == -1 or pos < gift_pos):
                        gift_pos = pos
                
                if gift_pos == -1:
                    if after_comma and not _RE_SIZE.search(after_comma) and not _RE_ROUND_SIZE.search(after_comma):
                        after_comma = _RE_QTY_SUMMARY.sub("", after_comma).strip().strip("-;,、，")
                        after_comma = _RE_ARRIVAL_REFUND.sub("", after_comma).strip().strip("-;,、，")
                        after_comma = _RE_IRRELEVANT_SUFFIX.sub("", after_comma).strip().strip("-;,、，")
                        if after_comma:
                            if trailing_remark:
                                trailing_remark = f"{trailing_remark}，{after_comma}"
                            else:
                                trailing_remark = after_comma
        
        # 为后续段补充花型名（如果没有分号），支持花型继承
        # 同时支持现货/定制类型的继承（现货商品组中后续尺寸无现货前缀时也能正确识别）
        processed_segments = []
        current_pattern = ""
        current_is_stock = False  # 跟踪当前组的现货/定制类型

        for i, (seg, qty) in enumerate(segments):
            cleaned_seg = _clean_segment(seg)

            if ";" in cleaned_seg:
                first_part = cleaned_seg.split(";", 1)[0].strip()
                pattern_candidate = first_part
                if pattern_candidate.startswith("定制"):
                    pattern_candidate = pattern_candidate[2:].strip()
                    current_is_stock = False
                elif pattern_candidate.startswith("现货"):
                    pattern_candidate = pattern_candidate[2:].strip()
                    current_is_stock = True
                for key in ["双面革", "吸水皮革", "双面格", "镜面皮革", "丝圈", "软玻璃"]:
                    if key in pattern_candidate:
                        pattern_candidate = pattern_candidate.replace(key, "").strip()
                        break
                if pattern_candidate:
                    current_pattern = pattern_candidate
                processed_segments.append((cleaned_seg, qty))
            else:
                if current_pattern:
                    # 继承pattern时，同时继承现货/定制类型（添加前缀供parse_remark识别）
                    prefix = "现货" if current_is_stock else ""
                    processed_segments.append((f"{prefix}{current_pattern};{cleaned_seg}", qty))
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
                
                size_desc = re.sub(r"[-*×]\d+[张个件套米]", "", size_desc).strip()
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
                after_comma = re.sub(r"[-*×]\d+[张个件套米]", "", after_comma).strip().strip("-;,")
                
                gift_pos = -1
                for kw in _GIFT_KEYWORDS:
                    pos = after_comma.find(kw)
                    if pos != -1 and (gift_pos == -1 or pos < gift_pos):
                        gift_pos = pos
                
                if gift_pos == -1:
                    if not _RE_SIZE.search(after_comma) and not _RE_ROUND_SIZE.search(after_comma) and after_comma:
                        after_comma = _RE_QTY_SUMMARY.sub("", after_comma).strip().strip("-;,、，")
                        after_comma = _RE_ARRIVAL_REFUND.sub("", after_comma).strip().strip("-;,、，")
                        after_comma = _RE_IRRELEVANT_SUFFIX.sub("", after_comma).strip().strip("-;,、，")
                        if after_comma:
                            trailing_remark = after_comma
    
    return segments, trailing_remark


def _clean_segment(segment: str) -> str:
    """清理商品段，去掉赠品和数量标记"""
    # 去掉赠品关键词及其后面的内容
    gift_pos = -1
    for kw in _GIFT_KEYWORDS:
        pos = segment.find(kw)
        if pos != -1 and (gift_pos == -1 or pos < gift_pos):
            gift_pos = pos
    
    if gift_pos != -1:
        segment = segment[:gift_pos].strip()
    
    # 去掉数量标记（如"-1张"）
    segment = re.sub(r"[-*×]\d+[张个件套米]", "", segment).strip()
    segment = re.sub(r"\d+[张个件套米]", "", segment).strip()
    
    # 去掉数量汇总信息（如"共计2张"、"共三张"）
    segment = _RE_QTY_SUMMARY.sub("", segment).strip()
    
    # 过滤掉"到货返xx"这种无关备注
    segment = _RE_ARRIVAL_REFUND.sub("", segment).strip()
    
    # 清理结尾符号（包括逗号和中文分号）
    segment = segment.strip().strip("-;,、，；")
    
    return segment