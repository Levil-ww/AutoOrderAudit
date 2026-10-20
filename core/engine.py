"""
核心 - 自动审单引擎
通用的自动审单流程，通过 ErpAdapter 接口与具体 ERP 解耦。
"""

from __future__ import annotations

import re
from _version import __version__
import time
from datetime import datetime
from collections import Counter
from html import unescape
from express_manager import get_manager as get_express_manager
from typing import Callable, Optional

from .adapter_base import ErpAdapter, Order, OrderItem
from .parser import parse_remark, extract_multiple_remarks, is_simple_price_diff_remark, ParsedRemark, _extract_multiple_gifts


_SKIP_KEYWORDS = [
    "待定",
    "待确定",
    "待确认",
    "等通知发",
    "需要效果图",
    "效果图",
    "确认再生产",
    "号发货",
    "安排发货",
    "在安排发货",
    "已代益",
    "已代森",
    "仓库发",
    "工厂发",
    "补发",
    "正常发",
]


_PRICE_DIFF_KEYWORDS = [
    "补差价专拍",
    "差价专用",
    "少几元拍几个",
]


# 备注指定发货日期时，交由人工处理；不因日期已到就自动放行。
_PUSH_SHIP_DATE = (
    r"(?:[0-9零〇一二三四五六七八九十两]{1,3}\s*月\s*"
    r"[0-9零〇一二三四五六七八九十两]{1,3}\s*[日号]?"
    r"|(?<![\d.])(?:\d{4}[-/.])?(?:0?[1-9]|1[0-2])\s*[-/.]\s*"
    r"(?:0?[1-9]|[12]\d|3[01])(?!\d|\s*(?:[xX×*]|[cCmM][mM]|厘米|毫米)))"
)
_PUSH_SHIP_ACTION = r"(?:发货|发出|发走|寄出|出货|安排发)"
_RE_PUSH_SCHEDULED_SHIP = re.compile(
    rf"{_PUSH_SHIP_DATE}[\s\S]{{0,12}}{_PUSH_SHIP_ACTION}"
    rf"|{_PUSH_SHIP_ACTION}[\s\S]{{0,12}}{_PUSH_SHIP_DATE}"
)


def _is_genuine_skip_keyword(keyword: str, remark: str) -> bool:
    """判断跳过关键字是否为真正的跳过指令。

    某些关键字在特定上下文中不是跳过信号，例如：
    - "补发" 后紧跟订单号（如 "补发:6929536054462610661"）是补发关联标记，
      表示本单是补发单，仍需正常解析定制信息。
    """
    if keyword == "补发":
        pos = remark.find(keyword)
        if pos >= 0:
            tail = remark[pos + len(keyword):].lstrip()
            if tail and (tail[0] in ":：" or tail[0].isdigit()):
                return False
    return True

_RE_RESHIPMENT_REF = re.compile(r"[,，;；\s]*补发\s*[:：]?\s*\d+\s*$")

def _strip_reshipment_ref(remark: str) -> str:
    """剥离备注末尾的补发关联标记（如 '补发:6929536054462610661'）。

    补发标记是订单关联信息，不属于定制内容，剥离后避免污染解析结果。
    """
    return _RE_RESHIPMENT_REF.sub("", remark).strip()

def _has_no_gift_ship(remark: str) -> bool:
    """与参考项目保持一致的赠品不发货写法。"""
    return any(keyword in remark for keyword in ("赠品不送", "不要赠品", "赠品不发货", "赠品不发", "赠品不要"))


class AutoAuditEngine:
    """自动审单引擎"""

    def __init__(
        self,
        adapter: ErpAdapter,
        dry_run: bool = False,
        max_orders: int = 0,
        interval: float = 0.5,
        confirm_callback: Optional[Callable] = None,
        skip_cache: Optional[dict] = None,
        should_stop: Optional[Callable] = None,
    ):
        """
        :param confirm_callback: 确认回调，签名 (order, parsed_list, changes: list[str]) -> bool
                                返回 True 表示确认修改，False 表示仅记录不修改。
                                仅在非 dry_run 模式下生效。
        :param skip_cache: 已正确订单缓存，格式 {trade_id: expected_key}。
                           传入同一个 dict 可在多次轮询间共享缓存。
        """
        self.should_stop = should_stop or (lambda: False)
        self.express_mgr = get_express_manager()
        self.adapter = adapter
        self.dry_run = dry_run
        self.max_orders = max_orders
        self.interval = interval
        self.confirm_callback = confirm_callback
        self.skip_cache = skip_cache if skip_cache is not None else {}
        self.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [],
                      "cancelled": 0}  # cancelled 统计用户取消的数量

    # ------------------------------------------------------------------
    #  缓存辅助方法：避免重复处理已正确的订单
    # ------------------------------------------------------------------
    def _compute_expected_key(
        self,
        parsed_list=None,
        price_diff_updates=None,
        gift_no_ship: bool = False,
        gift_no_ship_tids=None,
        order: Order = None,
    ):
        """计算订单的期望编码签名，用于缓存比对
        
        签名维度：
        1. 解析出的商品编码+数量
        2. 赠品名称+数量
        3. 补差价行编码
        4. 赠品不送标记
        5. 订单备注（shop_remark + buyer_remark）
        6. 现有商品行作废状态（防止外部作废后缓存命中跳过）
        """
        parts = []

        # 普通商品编码+数量
        for p in (parsed_list or []):
            if p and p.success:
                parts.append(("p", p.shop_mapping_sku, p.num))

        # 赠品（去重排序）
        gifts = set()
        for p in (parsed_list or []):
            if p and p.gifts:
                for name, num in p.gifts:
                    gifts.add((name, num))
            elif p and p.gift_name and p.gift_num > 0:
                gifts.add((p.gift_name, p.gift_num))
        for name, num in sorted(gifts):
            parts.append(("g", name, num))

        # 补差价行
        for update in (price_diff_updates or []):
            ship = update.get("ship", True)
            for item in update.get("items", []):
                if ship:
                    parts.append(("d", item.shop_mapping_sku, 1))
                else:
                    parts.append(("d", "定制-定制-补差价-不打印", 1))

        # 赠品不送
        if gift_no_ship:
            parts.append(("ns", "all"))
        if gift_no_ship_tids:
            # 优化：如果所有子订单都需要赠品不送，等价于 gift_no_ship=True
            if order and len(gift_no_ship_tids) >= 2:
                all_item_tids = set()
                for item in order.items:
                    if item.original_tid:
                        all_item_tids.add(item.original_tid)
                    elif item.oid:
                        all_item_tids.add(item.oid)
                if all_item_tids and all_item_tids.issubset(set(gift_no_ship_tids)):
                    parts.append(("ns", "all"))
                    return frozenset(parts)
            for tid in sorted(gift_no_ship_tids):
                parts.append(("ns", tid))

        # 订单备注（防止备注措辞变化但SKU不变时缓存命中）
        if order:
            shop_remark = order.shop_remark or ""
            buyer_remark = order.buyer_remark or ""
            if shop_remark or buyer_remark:
                parts.append(("rm", hash(shop_remark + "|" + buyer_remark)))

        # 现有商品行作废状态摘要（防止外部作废后缓存命中跳过）
        if order:
            void_summary = tuple(
                sorted(
                    (item.original_tid or str(item.id), item.is_void or False)
                    for item in order.items
                )
            )
            parts.append(("void", void_summary))

        return frozenset(parts)

    def _check_skip_cache(self, order: Order, expected_key) -> bool:
        """检查订单是否已在缓存中且期望签名未变"""
        if not expected_key:
            return False
        cached_key = self.skip_cache.get(order.trade_id)
        if cached_key is None:
            return False
        if cached_key == expected_key:
            print(f"  ⏭️  跳过：订单编码已正确（缓存命中）")
            return True
        return False

    def _update_skip_cache(self, order: Order, expected_key):
        """将订单期望签名写入缓存（dry_run 模式下不写入）"""
        if expected_key and not self.dry_run:
            self.skip_cache[order.trade_id] = expected_key

    def _is_price_difference_order(self, order: Order) -> bool:
        """
        判断订单是否为补差价订单
        通过检查每个商品行是否满足补差价商品条件。
        """
        return any(self._is_price_difference_item(item) for item in order.items)

    @staticmethod
    def _is_no_ship_remark(remark: str) -> bool:
        """判断备注是否表示补差价不发货/不打印"""
        return "差价不发货" in remark or "不打印" in remark or "不用发" in remark

    @staticmethod
    def _get_no_print_reason(remark: str) -> str:
        """
        判断是否需要将补差价行标记为'定制-定制-补差价-不打印'编码。
        条件（按优先级）：
        1. 备注为空（无信息）
        2. 备注内容为"补差价"或"差价"
        3. 包含"差价不发货"
        4. 包含"不用发"
        5. 包含"不打印"
        返回原因字符串，None 表示不匹配。
        """
        stripped = remark.strip()
        if not stripped:
            return "备注为空"
        if stripped == "补差价" or stripped == "差价":
            return f"备注为'{stripped}'"
        if "差价不发货" in remark:
            return "差价不发货"
        if "不用发" in remark:
            return "不用发"
        if "不打印" in remark:
            return "不打印"
        return None

    def _process_price_difference_order(self, order: Order):
        """
        处理补差价订单的逻辑：
        1. 如果备注为空、为"补差价"、或包含"差价不发货"/"不打印"，
           将编码修改为"定制-定制-补差价-不打印"，数量改为1
        2. 如果订单只有补差价商品且备注含定制信息，按正常解析逻辑修改编码和数量
           - 一条备注：覆盖原补差价行的编码和数量
           - 多条备注：覆盖一个，其余创建新手工单
        3. 如果订单有其他商品行且备注非空：
           - 补差价行按备注信息修改编码和数量（与仅有补差价行的逻辑一致）
           - 一条备注则覆盖原补差价行，多条则覆盖一个、其余创建新的
           - 若无剩余解析结果则仅修改数量为1
        """
        remark = order.shop_remark or ""
        print(f"  💰 补差价订单处理")

        price_diff_items = [item for item in order.items if self._is_price_difference_item(item)]
        only_price_diff = len(price_diff_items) == len(order.items)

        # 场景1：备注为空、为"补差价"、或包含"差价不发货"/"不打印"
        # → 编码改为"定制-定制-补差价-不打印"，数量改为1
        no_print_reason = self._get_no_print_reason(remark)
        if no_print_reason:
            print(f"  📝 {no_print_reason}：修改编码为'定制-定制-补差价-不打印'，数量改为1")

            expected_key = self._compute_expected_key(
                price_diff_updates=[{'tid': order.tid, 'items': price_diff_items, 'ship': False}]
            )
            if self._check_skip_cache(order, expected_key):
                self.stats["skipped"] += 1
                return

            if self.dry_run:
                # 预检查：判断补差价行是否已正确（与 adapter.update_price_difference_order 逻辑对齐）
                already_correct = True
                for item in price_diff_items:
                    if item.num != 1:
                        already_correct = False
                        break
                    clean_sku = re.sub(r'<[^>]+>', '', item.shop_mapping_sku or '')
                    if clean_sku != '定制-定制-补差价-不打印':
                        already_correct = False
                        break
                if already_correct:
                    print(f"  ⏭️  DRY RUN: 补差价订单编码已正确，跳过")
                    self._update_skip_cache(order, expected_key)
                    self.stats["skipped"] += 1
                else:
                    print(f"  🔶 DRY RUN: 修改编码为'定制-定制-补差价-不打印'")
                    self.stats["success"] += 1
                    self._update_skip_cache(order, expected_key)
                return

            try:
                ok = self.adapter.update_price_difference_order(order, price_diff_items, ship=False)
                if ok is None:
                    print(f"  ⏭️  跳过：补差价订单编码已正确")
                    self._update_skip_cache(order, expected_key)
                    self.stats["skipped"] += 1
                elif ok:
                    print(f"  ✅ 修改成功！")
                    self._update_skip_cache(order, expected_key)
                    self.stats["success"] += 1
                else:
                    print(f"  ❌ 修改失败")
                    self.stats["failed"] += 1
            except Exception as e:
                print(f"  ❌ 请求异常: {e}")
                self.stats["failed"] += 1
            return

        # 场景2：仅有补差价行 + 备注含定制信息 → 按正常解析修改编码和数量
        if only_price_diff and remark.strip():
            print(f"  📝 只有补差价商品，备注含信息，直接解析修改编码")
            self._process_normal_order_logic(order)
            return

        # 场景3：混合订单（有普通商品行 + 补差价行）+ 备注非空
        if remark.strip():
            print(f"  📝 混合订单备注含信息，解析备注并按补差价逻辑处理补差价行")
            # 解析备注，判断是否有剩余解析结果可分配给补差价行
            material_map = getattr(self.adapter, 'material_map', None)
            material_matcher = getattr(self.adapter, 'get_material_matcher', lambda: None)()
            parsed_list = extract_multiple_remarks(
                remark, material_map=material_map, material_matcher=material_matcher,
            )

            # 统计普通商品行数量（非赠品、非补差价、非作废）
            regular_item_count = sum(
                1 for item in order.items
                if not self._is_price_difference_item(item)
                and not self.adapter._is_gift_item(item)
                and not item.is_void
            )

            # 统计解析成功的条目数
            successful_parsed = [p for p in parsed_list if p.success]

            # 如果有剩余解析结果（超出普通商品行数量），分配给补差价行
            extra_parsed = successful_parsed[regular_item_count:] if len(successful_parsed) > regular_item_count else []

            if extra_parsed:
                print(f"  📝 有 {len(extra_parsed)} 条额外解析结果分配给补差价行（覆盖1个，多余创建新手工单）")
                price_diff_updates = [{
                    'tid': order.tid,
                    'items': price_diff_items,
                    'remark': remark,
                    'ship': True,  # 有剩余解析结果时按解析结果编码
                    'parsed_list': extra_parsed,  # 分配给补差价行的解析结果
                }]
            else:
                # 备注中的定制信息已全部分配给普通商品行，
                # 补差价行未获得定制信息，按不发货处理。
                price_diff_updates = [{
                    'tid': order.tid,
                    'items': price_diff_items,
                    'remark': remark,
                    'ship': False,
                }]

            self._process_normal_order_logic(order, price_diff_updates, parsed_list_override=parsed_list)
            return

    def _is_price_difference_item(self, item: OrderItem) -> bool:
        """判断商品行是否为补差价商品

        检测方式（任一满足即为补差价）：
        1. 商品标题包含补差价关键词
        2. shop_mapping_sku 为"定制-定制-补差价-不打印"
        3. 商品行备注为"差价"、"补差价"或包含"差价不发货"/"不打印"等补差价特征
        """
        if item.title:
            for keyword in _PRICE_DIFF_KEYWORDS:
                if keyword in item.title:
                    return True
        sku = item.shop_mapping_sku or ''
        clean_sku = re.sub(r'<[^>]+>', '', sku)
        if clean_sku == '定制-定制-补差价-不打印':
            return True
        remark = item.shop_remark or ''
        stripped = remark.strip()
        if stripped in ('差价', '补差价', '补的差价'):
            return True
        if '差价不发货' in remark or '不打印' in remark or '不用发' in remark:
            return True
        return False

    def _detect_implied_price_diff_scenario(self, order: Order):
        """
        检测隐含补差价场景（正常订单中，两个标题相同的商品行，
        一个有备注含"共X张"，另一个无备注）。
        无备注的一行实际只是补差价凑面积的作用，需要标记为不打印。

        触发条件（全部满足）：
        1. 订单非合并（已在调用方保证）
        2. 订单非显式补差价订单（已在调用方保证，即没有标题带补差价关键词的行）
        3. 订单有且仅有2个有效商品行（非作废、非赠品）
        4. 两个商品行的标题完全相同
        5. 恰好一个商品行有 shop_remark（非空），另一个 shop_remark 完全为空
        6. 有备注行的 shop_remark 或订单级 shop_remark 中包含"共X张"模式

        返回：price_diff_updates 列表（无备注行标记为 ship=False→编码改为不打印）
              不匹配时返回 None
        """
        # 获取有效商品行：非作废、非赠品
        valid_items = [
            item for item in order.items
            if not item.is_void and not self.adapter._is_gift_item(item)
        ]

        # 条件3：恰好2个有效商品行
        if len(valid_items) != 2:
            return None

        item_a, item_b = valid_items

        # 条件4：标题完全相同
        if not item_a.title or item_a.title.strip() != item_b.title.strip():
            return None

        # 条件5：恰好一个有 shop_remark，另一个为空
        remark_a = (item_a.shop_remark or "").strip()
        remark_b = (item_b.shop_remark or "").strip()
        a_has = bool(remark_a)
        b_has = bool(remark_b)
        if a_has == b_has:
            # 两个都有或两个都没有，不匹配
            return None

        if a_has:
            remarked_item = item_a
            no_remark_item = item_b
        else:
            remarked_item = item_b
            no_remark_item = item_a

        # 条件6：检查"共X张"模式（在商品行备注或订单级备注中）
        # 根据 lessons learned: 处理 "总?共" 前缀，避免 "总共X张" 只匹配 "共" 残留"总"
        total_count_pattern = re.compile(r'总?共\s*(\d+)\s*张')

        has_total_pattern = False
        if remarked_item.shop_remark and total_count_pattern.search(remarked_item.shop_remark):
            has_total_pattern = True
        if not has_total_pattern:
            order_remark = order.shop_remark or ""
            if order_remark and total_count_pattern.search(order_remark):
                has_total_pattern = True

        if not has_total_pattern:
            return None

        # 所有条件满足，返回 price_diff_updates（无备注行→补差价不打印）
        print(f"  💡 检测到隐含补差价场景：同标题两商品行，无备注行凑面积")
        print(f"     标题: {no_remark_item.title[:30]}...")
        remarked_remark_preview = (remarked_item.shop_remark or order.shop_remark or "")[:40]
        print(f"     有备注行: ID={remarked_item.id or remarked_item.oid[:8]}..., remark='{remarked_remark_preview}...'")
        print(f"     无备注行: ID={no_remark_item.id or no_remark_item.oid[:8]}... → 编码改为'定制-定制-补差价-不打印'")

        return [{
            'tid': order.tid,
            'items': [no_remark_item],
            'remark': "隐含补差价场景(凑面积)",
            'ship': False,  # ship=False → 编码改为不打印
        }]

    def _process_normal_order_logic(self, order: Order, price_diff_updates: list = None, parsed_list_override: list = None, keep_main_code: bool = False):
        """
        普通订单处理逻辑（从 _process_order 提取的公共逻辑）

        Args:
            price_diff_updates: 补差价商品行更新列表，用于合并订单或混合订单的一次性处理
            parsed_list_override: 外部传入的预解析结果，避免重复解析。混合订单场景使用。
        """
        remark = order.shop_remark or ""
        gift_no_ship = _has_no_gift_ship(remark)

        for keyword in _SKIP_KEYWORDS:
            if keyword in remark and not (keep_main_code and keyword == "正常发"):
                print(f"  ⏭️  跳过：备注包含关键字 '{keyword}'")
                self.stats["skipped"] += 1
                return

        if parsed_list_override is not None:
            parsed_list = parsed_list_override
        else:
            material_map = getattr(self.adapter, 'material_map', None)
            material_matcher = getattr(self.adapter, 'get_material_matcher', lambda: None)()
            parsed_list = extract_multiple_remarks(
                remark,
                material_map=material_map,
                material_matcher=material_matcher,
            )

        if not parsed_list:
            if gift_no_ship:
                parsed_list = []
            elif any(self._is_price_difference_item(item) for item in order.items):
                # 订单中有补差价行，即使备注为空也要继续处理
                parsed_list = []
            else:
                print(f"  ⏭️  跳过：无法解析备注")
                self.stats["skipped"] += 1
                return

        parsed = parsed_list[0] if parsed_list else None
        
        has_product_info = parsed.success if parsed else False
        
        if has_product_info:
            summary = (
                f"  ✅ 材质: {parsed.material_code}  "
                f"|  颜色: {parsed.color_code}  "
                f"|  尺寸: {parsed.model_code}  "
                f"|  花型: {parsed.picture_code}"
            )
            print(summary)
        else:
            print(f"  ℹ️  无商品定制信息")

        all_gifts = []
        for p in parsed_list:
            if p.gifts:
                all_gifts.extend(p.gifts)
            elif p.gift_name and p.gift_num > 0:
                all_gifts.append((p.gift_name, p.gift_num))
        
        all_gifts = list(dict.fromkeys(all_gifts))
        
        for gift_name, gift_num in all_gifts:
            print(f"  🎁 赠品: {gift_name} x {gift_num}")
        
        if not has_product_info and not all_gifts and not gift_no_ship:
            # 如果订单中有补差价行，不跳过（补差价行需要处理）
            if not any(self._is_price_difference_item(item) for item in order.items):
                print(f"  ⏭️  跳过：无商品定制信息且无赠品")
                self.stats["skipped"] += 1
                return

        # 混合订单补差价行处理：当外部未传入 price_diff_updates 时，自行构建
        if price_diff_updates is None:
            price_diff_items = [item for item in order.items if self._is_price_difference_item(item)]
            if price_diff_items:
                no_print_reason = self._get_no_print_reason(remark)
                if no_print_reason:
                    price_diff_updates = [{
                        'tid': order.tid,
                        'items': price_diff_items,
                        'remark': remark,
                        'ship': False,
                    }]
                else:
                    # 备注有定制信息，计算剩余解析结果分配给补差价行
                    regular_item_count = sum(
                        1 for item in order.items
                        if not self._is_price_difference_item(item)
                        and not self.adapter._is_gift_item(item)
                        and not item.is_void
                    )
                    successful_parsed = [p for p in parsed_list if p.success]
                    extra_parsed = successful_parsed[regular_item_count:] if len(successful_parsed) > regular_item_count else []
                    if extra_parsed:
                        price_diff_updates = [{
                            'tid': order.tid,
                            'items': price_diff_items,
                            'remark': remark,
                            'ship': True,
                            'parsed_list': extra_parsed,
                        }]
                    else:
                        # 备注中的定制信息已全部分配给普通商品行，
                        # 补差价行未获得定制信息，按不发货处理。
                        price_diff_updates = [{
                            'tid': order.tid,
                            'items': price_diff_items,
                            'remark': remark,
                            'ship': False,
                        }]

        # ---- 缓存检查：如果订单已正确，直接跳过 ----
        expected_key = self._compute_expected_key(
            parsed_list=parsed_list,
            price_diff_updates=price_diff_updates,
            gift_no_ship=gift_no_ship,
            order=order,
        )
        if self._check_skip_cache(order, expected_key):
            self.stats["skipped"] += 1
            return
        # ------------------------------------------

        if self.dry_run:
            print()
            for parsed in parsed_list:
                if parsed.success:
                    print(f"  🔶 DRY RUN: 新编码 = {parsed.shop_mapping_sku}")
            for gift_name, gift_num in all_gifts:
                print(f"  🔶 DRY RUN: 将添加赠品商品行 = {gift_name} x {gift_num}")
            if price_diff_updates:
                for update in price_diff_updates:
                    action = "修改编码为'定制-定制-补差价-不打印'" if not update['ship'] else "仅修改数量为1"
                    print(f"  🔶 DRY RUN: 补差价订单 -> {action}")
            if gift_no_ship:
                print(f"  🔶 DRY RUN: 赠品不发货 -> 修改赠品行编码为'定制-定制-补差价-不打印'")
            self._update_skip_cache(order, expected_key)
            self.stats["success"] += 1
            return

        if self.confirm_callback:
            changes = []
            for p in parsed_list:
                if p.success:
                    changes.append(f"新编码: {p.shop_mapping_sku}")
            for gift_name, gift_num in all_gifts:
                changes.append(f"赠品: {gift_name} x {gift_num}")
            if price_diff_updates:
                for update in price_diff_updates:
                    action = "修改编码为'定制-定制-补差价-不打印'" if not update['ship'] else "仅修改数量为1"
                    changes.append(f"补差价订单: {action}")
            if gift_no_ship:
                changes.append(f"赠品不发货: 修改赠品行编码为'定制-定制-补差价-不打印'")

            should_update = self.confirm_callback(order, parsed_list, changes)
            if not should_update:
                if parsed_list and parsed_list[0].success:
                    print(f"  ⏭️  用户取消：新编码 {parsed_list[0].shop_mapping_sku}（未修改）")
                else:
                    print(f"  ⏭️  用户取消（未修改）")
                self.stats["cancelled"] += 1
                return

        try:
            update_kwargs = {"keep_main_code": True} if keep_main_code else {}
            ok = self.adapter.update_merchant_code(order, parsed_list[0] if parsed_list else None, parsed_list, price_diff_updates, gift_no_ship=gift_no_ship, engine_gifts=[(g[0], g[1], '') for g in all_gifts], **update_kwargs)
            if ok is None:
                print(f"  ⏭️  跳过：订单所有商品行已作废")
                self.stats["skipped"] += 1
            elif ok:
                if parsed_list and parsed_list[0].success:
                    print(f"  ✅ 修改成功！新编码: {parsed_list[0].shop_mapping_sku}")
                    if len(parsed_list) > 1:
                        print(f"  📦 包含 {len(parsed_list)} 个尺寸，已拆分处理")
                else:
                    print(f"  ✅ 修改成功！")
                for gift_name, gift_num in all_gifts:
                    print(f"  🎁 赠品已添加: {gift_name} x {gift_num}")
                if price_diff_updates:
                    print(f"  ✅ 补差价订单修改成功！")
                self._update_skip_cache(order, expected_key)
                self.stats["success"] += 1
            else:
                print(f"  ❌ 修改失败")
                self.stats["failed"] += 1
                self.stats["errors"].append(f"订单 {order.trade_id}: 接口返回失败")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"  ❌ 请求异常: {e}")
            print(tb)
            self.stats["failed"] += 1
            self.stats["errors"].append(f"订单 {order.trade_id}: {e}\n{tb}")

    def run(self, page_no=1, page_size=500, query_status=1, time_begin="", time_end="", allowed_order_ids=None):
        if self.should_stop():
            return
        print("=" * 60)
        print(f"自动审单引擎 V{__version__} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"适配器: {self.adapter.get_adapter_name()}")
        if self.dry_run:
            print("🔶 DRY RUN 模式：仅模拟，不会真实提交")
        if self.confirm_callback and not self.dry_run:
            print("💬 确认模式：修改前会弹窗确认")
        print("=" * 60)

        print("\n📦 正在查询待处理订单...")
        try:
            orders = self.adapter.query_all_orders(
                page_size=page_size,
                query_status=query_status, time_begin=time_begin, time_end=time_end,
            )
        except Exception as e:
            print(f"❌ 查询订单失败: {e}")
            return

        if allowed_order_ids is not None:
            orders = [order for order in orders if (order.tid or order.trade_id) in allowed_order_ids]

        if not orders:
            print("✅ 没有待处理的订单")
            self._print_summary()
            return

        print(f"📋 共获取 {len(orders)} 个待处理订单")

        for idx, order in enumerate(orders):
            if self.should_stop():
                break
            if self.max_orders > 0 and idx >= self.max_orders:
                print(f"\n⏸️  已达最大处理数量 ({self.max_orders})")
                break

            self.stats["total"] += 1
            print(f"[{idx+1}/{len(orders)}] 处理订单 {order.id or order.trade_id}")

            try:
                cancelled_before = self.stats["cancelled"]
                failed_before = self.stats["failed"]
                self._process_order(order)
                # 处理完商品编码后，统一处理快递
                if not self.should_stop() and self.stats["cancelled"] == cancelled_before and self.stats["failed"] == failed_before:
                    self._update_express_for_order(order)
            except Exception as e:
                self.stats["failed"] += 1
                import traceback
                tb = traceback.format_exc()
                self.stats["errors"].append(f"订单 {order.trade_id}: {e}\n{tb}")
                print(f"  ❌ 订单处理异常: {e}")
                print(tb)

            time.sleep(self.interval)

        self._print_summary()

    def run_monitor_cycle(self, page_no=1, page_size=500, query_status=1, time_begin="", time_end="", allowed_order_ids=None) -> int:
        """
        监控周期：查询订单，有则处理，无则安静返回。
        比 run() 更安静，不打印 banner，无订单时不打印多余信息。
        返回本次处理的订单总数（0 表示无待处理订单）。
        """
        # 重置统计
        self.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": [], "cancelled": 0}

        try:
            orders = self.adapter.query_all_orders(
                page_size=page_size,
                query_status=query_status, time_begin=time_begin, time_end=time_end,
            )
        except Exception as e:
            print(f"❌ 查询订单失败: {e}")
            return 0

        if allowed_order_ids is not None:
            orders = [order for order in orders if (order.tid or order.trade_id) in allowed_order_ids]

        if not orders:
            return 0

        print(f"\n📋 检测到 {len(orders)} 个待处理订单，开始处理...")
        print(f"🚀 开始自动审单 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        for idx, order in enumerate(orders):
            if self.should_stop():
                break
            if self.max_orders > 0 and idx >= self.max_orders:
                print(f"\n⏸️  已达最大处理数量 ({self.max_orders})")
                break

            self.stats["total"] += 1
            print(f"[{idx+1}/{len(orders)}] 处理订单 {order.id or order.trade_id}")

            try:
                cancelled_before = self.stats["cancelled"]
                failed_before = self.stats["failed"]
                self._process_order(order)
                if not self.should_stop() and self.stats["cancelled"] == cancelled_before and self.stats["failed"] == failed_before:
                    self._update_express_for_order(order)
            except Exception as e:
                self.stats["failed"] += 1
                self.stats["errors"].append(str(e))
                print(f"  ❌ 订单处理异常: {e}")

            time.sleep(self.interval)

        self._print_summary()
        return self.stats["total"]

    def _process_order(self, order):
        remark = order.shop_remark or ""
        print(f"  卖家备注: {remark[:60]}..." if len(remark) > 60 else f"  卖家备注: {remark}")

        material_map = getattr(self.adapter, 'material_map', None)
        material_matcher = getattr(self.adapter, 'get_material_matcher', lambda: None)()

        # ===== 检测合并订单 =====
        # 合并订单特征：订单号包含 &，或商品行有不同的 original_tid
        is_merged_order = "&" in order.trade_id or "&" in order.tid
        
        if not is_merged_order:
            # 检查商品行是否有不同的 original_tid
            tids = set()
            for item in order.items:
                if item.original_tid:
                    tids.add(item.original_tid)
            if len(tids) >= 2:
                is_merged_order = True

        if is_merged_order:
            self._process_merged_order(order, material_map, material_matcher)
            return

        # 正常发/特定保持原商品编码，只补齐备注中的赠品。
        if "正常发" in remark or "特定" in remark:
            gifts = _extract_multiple_gifts(remark)
            if gifts or _has_no_gift_ship(remark):
                parsed = ParsedRemark(raw_text=remark, gifts=gifts,
                                      gift_name=gifts[0][0] if gifts else "",
                                      gift_num=gifts[0][1] if gifts else 0)
                self._process_normal_order_logic(order, parsed_list_override=[parsed], keep_main_code=True)
                return

        # ===== 检测补差价订单 =====
        if self._is_price_difference_order(order):
            self._process_price_difference_order(order)
            return

        # ===== 检测隐含补差价场景（标题相同+单行备注共X张+另一行无备注） =====
        # 注意：必须在 补差价订单检测之后、普通订单处理之前执行
        implied_price_diff_updates = self._detect_implied_price_diff_scenario(order)

        # ===== 普通订单处理 =====
        # 混合订单（有普通商品行 + 补差价行）：即使备注为空，也要处理补差价行
        price_diff_items = [item for item in order.items if self._is_price_difference_item(item)]

        # 预构建完整的 price_diff_updates（显式 + 隐含），避免传参后内部逻辑遗漏显式行
        # 说明：_process_normal_order_logic 仅在 price_diff_updates is None 时自行构建显式行
        #       如果我们只传隐含行，会导致显式补差价行被遗漏，所以这里统一构建。
        prebuilt_price_diff_updates = None
        if price_diff_items or implied_price_diff_updates:
            prebuilt_price_diff_updates = []
            # 显式补差价行（与 _process_normal_order_logic 内部构建逻辑对齐）
            if price_diff_items:
                no_print_reason = self._get_no_print_reason(remark)
                if no_print_reason:
                    prebuilt_price_diff_updates.append({
                        'tid': order.tid,
                        'items': price_diff_items,
                        'remark': remark,
                        'ship': False,
                    })
                else:
                    # 备注有定制信息，后续流程会计算 extra_parsed 分配；这里先标记 ship=True
                    # 真正的分配在 update_merchant_code 第五步通过 parsed_list 字段处理
                    regular_item_count = sum(
                        1 for item in order.items
                        if not self._is_price_difference_item(item)
                        and not self.adapter._is_gift_item(item)
                        and not item.is_void
                    )
                    # 先临时构建 ship=False，让后续逻辑接管（如果传了 price_diff_updates 就跳过了内部构建）
                    # 实际上：为避免复杂分支，直接传 None 让内部处理显式行，然后在 adapter 层合并隐含行
                    # → 更简单方案：把隐含场景追加到后面，且只对隐含行 ship=False
                    prebuilt_price_diff_updates.append({
                        'tid': order.tid,
                        'items': price_diff_items,
                        'remark': remark,
                        'ship': False if not remark.strip() else True,
                    })
            # 隐含场景补差价行（ship=False → 编码改为不打印）
            if implied_price_diff_updates:
                prebuilt_price_diff_updates.extend(implied_price_diff_updates)

        if not remark.strip():
            if price_diff_items or implied_price_diff_updates:
                # 备注为空但有补差价行（显式或隐含） → 继续处理
                self._process_normal_order_logic(order, price_diff_updates=prebuilt_price_diff_updates)
            else:
                print("  ⏭️  跳过：卖家备注为空")
                self.stats["skipped"] += 1
                return
        else:
            self._process_normal_order_logic(order, price_diff_updates=prebuilt_price_diff_updates)

    def _process_merged_order(self, order, material_map, material_matcher):
        """
        处理合并订单：按商品行的 original_tid 分组，每组使用自己的备注单独处理
        
        分组策略：
        1. 优先使用不含&的 original_tid / oid 作为分组键
        2. 含&时，先收集所有唯一ID，检查是否存在前缀碰撞
        3. 前缀碰撞时使用完整ID作为分组键，否则取&前的子订单号
        4. 所有ID都不可用时，使用 item.id 兜底
        """
        print(f"  🔄 合并订单，按原始订单号分组处理")
        
        # 预收集：统计所有不含&的子订单号、所有含&的完整ID
        clean_tids = set()       # 不含&的子订单号
        amp_tids = set()         # 含&的完整ID
        amp_tid_prefixes = {}    # prefix -> count (用于检测前缀碰撞)
        for item in order.items:
            if item.original_tid and "&" not in item.original_tid:
                clean_tids.add(item.original_tid)
            if item.oid and "&" not in item.oid:
                clean_tids.add(item.oid)
            if item.original_tid and "&" in item.original_tid:
                amp_tids.add(item.original_tid)
                prefix = item.original_tid.split("&")[0]
                amp_tid_prefixes[prefix] = amp_tid_prefixes.get(prefix, 0) + 1
            if item.oid and "&" in item.oid:
                amp_tids.add(item.oid)
                prefix = item.oid.split("&")[0]
                amp_tid_prefixes[prefix] = amp_tid_prefixes.get(prefix, 0) + 1
        
        # 检测前缀碰撞：如果任何前缀对应多个含&的完整ID
        has_prefix_collision = any(v > 1 for v in amp_tid_prefixes.values())
        
        # 按 original_tid 分组商品行
        # 预收集所有非赠品行的有效子订单tid，供赠品行匹配使用
        valid_suborder_tids = set()
        for item in order.items:
            if not self.adapter._is_gift_item(item) and item.original_tid and "&" not in item.original_tid:
                valid_suborder_tids.add(item.original_tid)
        
        groups = {}
        for idx, item in enumerate(order.items):
            # 保存 ERP 原始 original_tid，避免后续处理丢失
            if not hasattr(item, '_erp_original_tid'):
                item._erp_original_tid = item.original_tid
            
            is_gift_item = self.adapter._is_gift_item(item)
            
            # 优先使用不包含&的子订单号
            if item.original_tid and "&" not in item.original_tid:
                tid = item.original_tid
            elif is_gift_item and item.original_tid and "&" in item.original_tid:
                # 赠品行特殊处理：如果 original_tid 包含 &，尝试从子订单中找到正确的 tid
                # ERP 在合并订单中会自动创建赠品行，其 original_tid 是合并订单号
                # 需要将赠品行分配到正确的子订单分组
                # 策略：通过 shop_remark 匹配关联的商品行，确定正确的子订单
                candidate_tids = item.original_tid.split("&")
                matched_tid = None
                
                # 优先策略：通过 shop_remark 匹配（赠品行的 shop_remark 通常与关联的商品行相同）
                if item.shop_remark:
                    for ctid in candidate_tids:
                        if ctid in valid_suborder_tids and ctid in groups:
                            # 检查该分组是否有商品行与赠品行的 shop_remark 匹配
                            for gitem in groups[ctid]['items']:
                                if not self.adapter._is_gift_item(gitem) and gitem.shop_remark == item.shop_remark:
                                    matched_tid = ctid
                                    break
                            if matched_tid:
                                break
                
                # 备用策略：如果 shop_remark 匹配失败，从后向前遍历（赠品行通常关联到最后一个子订单）
                if not matched_tid:
                    for ctid in reversed(candidate_tids):
                        if ctid in valid_suborder_tids:
                            matched_tid = ctid
                            break
                
                # 最后兜底：使用最后一个候选
                if not matched_tid and candidate_tids:
                    matched_tid = candidate_tids[-1]
                
                tid = matched_tid if matched_tid else (str(item.id) if item.id else f"item_{idx}")
            elif item.oid and "&" not in item.oid:
                tid = item.oid
            elif item.original_tid and "&" in item.original_tid:
                if has_prefix_collision:
                    # 前缀碰撞：使用完整 original_tid 作为分组键
                    # 同一完整ID的商品行归为一组，不同完整ID的分开
                    tid = item.original_tid
                else:
                    # 无前缀碰撞：取&前的子订单号
                    tid = item.original_tid.split("&")[0]
            elif item.oid and "&" in item.oid:
                if has_prefix_collision:
                    tid = item.oid
                else:
                    tid = item.oid.split("&")[0]
            else:
                # 所有ID都含&或为空时，使用item.id作为兜底分组键
                tid = str(item.id) if item.id else f"item_{idx}"
            if tid not in groups:
                groups[tid] = {
                    'items': [],
                    'remark': '',
                    'price_diff_remark': '',
                    'regular_remark': '',
                    'is_price_diff': False,
                }
            groups[tid]['items'].append(item)
            # 确保 item.original_tid 与分组键一致（处理空值情况）
            item.original_tid = tid
            # 收集该组的备注：区分补差价商品行和普通商品行。
            # 合并订单里 ERP 常把订单级备注复制到所有商品行，
            # 若直接用普通商品行的订单级备注覆盖补差价行备注，
            # 会导致补差价行被错误解析并改编码。
            # 此外，手工单行（type==1）的备注常被ERP自动关联为订单级备注，
            # 若以此作为解析来源，会导致反复创建手工单（反复增值）。
            # 赠品行同样会被ERP复制订单级备注，若以其备注作为解析来源，
            # 会导致解析出其他分组的商品信息并创建重复行。
            # 
            # 关键规则：ERP 在合并订单中会自动将订单级备注关联到新建的商品行/赠品行，
            # 这些行的特征是 original_tid 或 oid 包含 "&"（合并订单号）。
            # 这些行的 shop_remark 是订单级备注而非子订单专属备注，不应作为解析来源。
            is_manual_item = item.raw and item.raw.get('type') == 1
            is_gift_item = self.adapter._is_gift_item(item)
            # 检查是否为 ERP 合并订单自动创建的商品行（其备注是订单级备注，不可信）
            erp_tid = item._erp_original_tid
            is_erp_created = (
                (erp_tid and "&" in erp_tid) or
                (item.oid and "&" in item.oid)
            )
            if item.shop_remark and not is_manual_item and not is_gift_item and not is_erp_created:
                if self._is_price_difference_item(item):
                    groups[tid]['price_diff_remark'] = item.shop_remark
                else:
                    groups[tid]['regular_remark'] = item.shop_remark
            # 检测是否为补差价分组
            if self._is_price_difference_item(item):
                groups[tid]['is_price_diff'] = True
        
        # 合并订单中，每个原始订单使用自己的商品行备注
        # 不回退使用订单级备注，因为订单级备注可能属于另一个原始订单
        
        # 快速路径：简单合并订单（1个正常分组 + 1个纯补差价分组，且补差价备注为空）
        # 按普通订单逻辑处理，避免补差价行因分组备注为空而被错误改为不打印
        normal_tids = [tid for tid, g in groups.items() if not g['is_price_diff']]
        price_diff_tids = [tid for tid, g in groups.items() if g['is_price_diff']]
        if (len(normal_tids) == 1 and len(price_diff_tids) == 1
                and not groups[price_diff_tids[0]]['price_diff_remark'].strip()
                and order.shop_remark.strip()):
            # 额外检查：补差价分组内部不能包含普通商品行（混合分组不走快速路径）
            diff_group = groups[price_diff_tids[0]]
            regular_in_diff_group = [
                item for item in diff_group['items']
                if not self._is_price_difference_item(item)
            ]
            if not regular_in_diff_group:
                print(f"  📝 检测到简单合并订单（1正常分组+1纯补差价分组，补差价备注为空），按普通订单逻辑处理")
                self._process_normal_order_logic(order)
                return
        
        # 处理每个分组
        all_parsed_list = []
        all_gifts = []
        price_diff_updates = []
        gift_no_ship_tids = []
        
        for tid, group in groups.items():
            # ===== 全作废子订单跳过检测 =====
            # 如果该分组（子订单）内所有非赠品、非补差价的普通商品行全部已作废/已退款，
            # 则直接跳过该分组，不再解析备注、不再处理商品和赠品，
            # 避免因备注能解析成功而为已退款的子订单错误地新建商品行和赠品行。
            non_gift_regular_items = [
                item for item in group['items']
                if not self.adapter._is_gift_item(item)
                and not self._is_price_difference_item(item)
            ]
            if non_gift_regular_items and all(item.is_void for item in non_gift_regular_items):
                # 补差价分组单独判断：补差价行本身也可能是唯一非赠品行
                # （补差价分组的补差价行也是要处理的"有效行"，全作废才跳过）
                if not group['is_price_diff']:
                    print(f"    ⏭️  原始订单 {tid[:16]}...: 子订单所有商品行已作废/已退款，跳过解析")
                    continue
            # 补差价分组：若补差价行和普通行都已作废，也跳过
            if group['is_price_diff']:
                all_void = all(item.is_void for item in group['items']
                               if not self.adapter._is_gift_item(item))
                if all_void:
                    print(f"    ⏭️  原始订单 {tid[:16]}...: 子订单（补差价）所有行已作废/已退款，跳过解析")
                    continue

            # 补差价分组必须优先使用补差价商品行的备注，避免被普通商品行上的
            # 订单级备注覆盖后错误解析；普通分组则优先使用普通商品行备注。
            if group['is_price_diff']:
                # 补差价分组必须使用补差价商品行自身的备注；
                # 当补差价行备注为空时，按"补差价不发货"处理，
                # 不能回退使用同一分组内普通商品行的备注。
                group_remark = group['price_diff_remark']
            else:
                group_remark = group['regular_remark'] or group['price_diff_remark']
            is_price_diff = group['is_price_diff']
            print(f"    原始订单 {tid[:16]}...: 备注='{group_remark[:40]}...' {'(补差价)' if is_price_diff else ''}")
            
            if _has_no_gift_ship(group_remark):
                gift_no_ship_tids.append(tid)
            
            if not is_price_diff and ("正常发" in group_remark or "特定" in group_remark):
                if not any(keyword in group_remark for keyword in _SKIP_KEYWORDS if keyword != "正常发"):
                    gifts = _extract_multiple_gifts(group_remark)
                    all_gifts.extend((name, num, tid) for name, num in gifts)
                    all_parsed_list.append(ParsedRemark(raw_text=group_remark, gifts=gifts,
                                                        original_tid=tid))
                continue

            if is_price_diff:
                # 分离补差价商品行和普通商品行
                diff_items = [item for item in group['items'] if self._is_price_difference_item(item)]
                regular_items_in_group = [item for item in group['items'] if not self._is_price_difference_item(item)]

                # 先统一解析备注（用于赠品收集，补差价无论何种分支都可能有赠品）
                parsed_list_for_gifts = extract_multiple_remarks(
                    group_remark,
                    material_map=material_map,
                    material_matcher=material_matcher,
                )
                # 收集纯赠品信息：即使商品解析 success=False，
                # 补差价订单也可能只携带赠品描述（如"赠送圆垫-1张，方垫-1张"）
                for p in parsed_list_for_gifts:
                    if p.gifts:
                        for gname, gnum in p.gifts:
                            all_gifts.append((gname, gnum, tid))
                    elif p.gift_name and p.gift_num > 0:
                        all_gifts.append((p.gift_name, p.gift_num, tid))

                # 检测备注是否为空、"补差价"、"差价不发货"或"不打印"
                # → 编码改为"定制-定制-补差价-不打印"，数量改为1
                no_print_reason = self._get_no_print_reason(group_remark)
                if no_print_reason:
                    print(f"      📝 {no_print_reason}：修改编码为'定制-定制-补差价-不打印'，数量改为1")
                    price_diff_updates.append({
                        'tid': tid,
                        'items': diff_items,
                        'remark': group_remark,
                        'ship': False,
                    })
                    # 赠品已在上方统一收集，这里不 return/continue
                else:
                    print(f"      📝 补差价订单备注含信息，按正常解析逻辑处理")
                    skip_reason = None
                    for keyword in _SKIP_KEYWORDS:
                        if keyword in group_remark:
                            skip_reason = f"包含关键字 '{keyword}'"
                            break
                    
                    if skip_reason:
                        print(f"        ⏭️  跳过：{skip_reason}")
                        # 赠品已收集，continue 到下一分组
                        continue
                    
                    parsed_list = parsed_list_for_gifts
                    
                    if not parsed_list or not any(p.success for p in parsed_list):
                        print(f"        ⏭️  跳过：无法解析备注（赠品仍已收集）")
                        # success=False 但有赠品时，不处理商品行修改，但赠品已收集
                        continue
                    
                    for p in parsed_list:
                        p.original_tid = tid
                        p.shop_remark = ""

                    # 如果分组内同时有普通商品行和补差价行（混合分组）
                    if regular_items_in_group:
                        non_gift_regular_count = sum(
                            1 for item in regular_items_in_group
                            if not self.adapter._is_gift_item(item) and not item.is_void
                        )
                        successful_parsed = [p for p in parsed_list if p.success]
                        extra_parsed = successful_parsed[non_gift_regular_count:] if len(successful_parsed) > non_gift_regular_count else []

                        if extra_parsed:
                            print(f"        📝 有 {len(extra_parsed)} 条额外解析结果分配给补差价行")
                            price_diff_updates.append({
                                'tid': tid,
                                'items': diff_items,
                                'remark': group_remark,
                                'ship': True,
                                'parsed_list': extra_parsed,
                            })
                        else:
                            # 备注中的定制信息已全部分配给普通商品行，
                            # 补差价行未获得定制信息，按不发货处理。
                            price_diff_updates.append({
                                'tid': tid,
                                'items': diff_items,
                                'remark': group_remark,
                                'ship': False,
                            })
                    else:
                        # 没有普通商品行，所有解析结果分配给补差价行
                        successful_parsed = [p for p in parsed_list if p.success]
                        if successful_parsed:
                            print(f"        📝 补差价分组，{len(successful_parsed)} 条解析结果分配给补差价行")
                            price_diff_updates.append({
                                'tid': tid,
                                'items': diff_items,
                                'remark': group_remark,
                                'ship': True,
                                'parsed_list': successful_parsed,
                            })
                        else:
                            price_diff_updates.append({
                                'tid': tid,
                                'items': diff_items,
                                'remark': group_remark,
                                'ship': True,
                            })

                    all_parsed_list.extend(parsed_list)
            else:
                skip_reason = None
                for keyword in _SKIP_KEYWORDS:
                    if keyword in group_remark:
                        skip_reason = f"包含关键字 '{keyword}'"
                        break
                
                if not group_remark.strip():
                    skip_reason = "备注为空"
                
                if skip_reason:
                    print(f"      ⏭️  跳过：{skip_reason}")
                    continue
                
                parsed_list = extract_multiple_remarks(
                    group_remark,
                    material_map=material_map,
                    material_matcher=material_matcher,
                )
                
                # 先收集赠品：普通分组也可能出现"无商品信息但有赠品"的备注，
                # 即使 success=False 也要把赠品收集到 all_gifts 中
                for p in parsed_list:
                    if p.gifts:
                        for gname, gnum in p.gifts:
                            all_gifts.append((gname, gnum, tid))
                    elif p.gift_name and p.gift_num > 0:
                        all_gifts.append((p.gift_name, p.gift_num, tid))
                
                if not parsed_list or not any(p.success for p in parsed_list):
                    print(f"      ⏭️  跳过：无法解析备注（赠品仍已收集）")
                    # success=False 不处理商品行修改，但赠品已收集
                    continue
                
                for p in parsed_list:
                    p.original_tid = tid
                    p.shop_remark = group['remark']

                all_parsed_list.extend(parsed_list)

        # 赠品去重：按 (赠品名, tid) 合并数量，不同子订单的赠品不合并
        gift_merged = {}
        for gname, gnum, gtid in all_gifts:
            key = (gname, gtid)
            if key in gift_merged:
                gift_merged[key] += gnum
            else:
                gift_merged[key] = gnum
        all_gifts = [(name, num, gtid) for (name, gtid), num in gift_merged.items()]

        # ===== 合并订单解析结果净化 =====
        # 合并订单中 ERP 常把订单级备注复制到多个商品行，导致：
        # 1. 单个分组的备注解析出其他子订单的商品（跨分组污染）
        # 2. 多个分组解析出相同 SKU 但带有不同 original_tid（重复解析）
        # 本环节做两步净化：
        #   a. 跨分组污染过滤：若某分组的解析结果与「其他分组的现有商品行」SKU 等价，
        #      说明是订单级备注带进来的其他子订单商品，直接剔除。
        #   b. 同 SKU 去重：若多个分组产生相同 SKU，保留与现有商品行 original_tid
        #      匹配的那个，确保每个 SKU 只属于正确的子订单。
        def _normalize_sku_for_dup(sku: str) -> str:
            if not sku:
                return sku
            sku = re.sub(r'(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)',
                         r'\1x\2', sku, flags=re.IGNORECASE)
            sku = re.sub(r'(直径|圆|圆形|圆直径|尺寸)(\d+(?:\.\d+)?)\s*(?:cm|CM|厘米)',
                         r'\1\2', sku, flags=re.IGNORECASE)
            return sku

        # 构建现有商品行的 (normalized_sku, num) -> set of original_tid 映射
        # 同时构建 original_tid -> set of (normalized_sku, num) 反向映射
        existing_sku_tids = {}  # {(norm_sku, num): set of tid}
        tid_to_skus = {}       # {tid: set of (norm_sku, num)}
        for item in order.items:
            if item.is_void or self.adapter._is_gift_item(item) or self._is_price_difference_item(item):
                continue
            norm_sku = _normalize_sku_for_dup(item.shop_mapping_sku or '')
            if norm_sku:
                key = (norm_sku, item.num)
                if key not in existing_sku_tids:
                    existing_sku_tids[key] = set()
                item_tid = item.original_tid or ''
                existing_sku_tids[key].add(item_tid)
                # 反向映射：tid -> set of sku keys
                if item_tid:
                    if item_tid not in tid_to_skus:
                        tid_to_skus[item_tid] = set()
                    tid_to_skus[item_tid].add(key)

        # --- a. 跨分组污染过滤 ---
        # 对每个解析结果，检查其 SKU 是否已经存在于「其他 original_tid 的商品行」。
        # 若存在则说明是订单级备注带进来的外组商品，剔除。
        # 修复：当解析结果的 original_tid 不在现有商品行的 tid 集合中时，
        # 检查当前子订单是否有「这个特定 SKU」的现有商品行（而不是检查是否有任何有效商品行）。
        # 如果当前子订单也有该 SKU → 合法商品（不同子订单相同SKU），保留。
        # 如果当前子订单没有该 SKU → 订单级备注污染，剔除。
        filtered_parsed = []
        contamination_count = 0
        
        # 预计算每个 original_tid 是否有有效商品行（用于订单级别的辅助判断）
        all_tids_in_order = set()  # 所有出现在订单中的 tid（包括全作废的子订单）
        for item in order.items:
            tid = item.original_tid or ''
            if tid:
                all_tids_in_order.add(tid)
        
        for p in all_parsed_list:
            if not p or not p.success:
                filtered_parsed.append(p)
                continue
            norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
            key = (norm_sku, p.num)
            existing_tids = existing_sku_tids.get(key, set())
            if existing_tids:
                # 该 SKU 已有商品行存在
                if p.original_tid and p.original_tid in existing_tids:
                    # 本组已有该 SKU 的商品行 → 这是本组自己的商品，保留
                    filtered_parsed.append(p)
                else:
                    # 该 SKU 的商品行在其他组 → 检查当前子订单是否有「这个特定 SKU」的现有商品行
                    p_tid = p.original_tid or ''
                    # 检查当前子订单是否有该 SKU 的现有商品行（合法跨子订单相同SKU）
                    current_tid_skus = tid_to_skus.get(p_tid, set())
                    if key in current_tid_skus:
                        # 当前子订单也有该 SKU → 是合法商品（不同子订单相同SKU），保留
                        filtered_parsed.append(p)
                    elif p_tid and p_tid in all_tids_in_order and not tid_to_skus.get(p_tid, set()):
                        # 子订单存在但没有任何有效商品行（全作废/全赠品/全补差价）→ 保留
                        # 这种情况可能是赠品对应的子订单，需要保留解析结果
                        filtered_parsed.append(p)
                    else:
                        # 当前子订单没有该 SKU 的现有商品行 → 订单级备注污染，剔除
                        contamination_count += 1
            else:
                # 该 SKU 没有现有商品行 → 可能是新尺寸/新商品，保留
                filtered_parsed.append(p)

        if contamination_count > 0:
            print(f"  🧹 合并订单净化：过滤掉 {contamination_count} 个跨分组污染的解析结果")

        # --- b. 同 SKU 去重（多分组各解析出同一个 SKU 的情况） ---
        success_parsed = [p for p in filtered_parsed if p and p.success]
        non_success_parsed = [p for p in filtered_parsed if p and not p.success]

        # 检测是否为套装订单：
        # 1. 商品行title包含"件套"、"套装"、"优惠装"等关键词
        # 2. 或存在多个相同SKU的非赠品、非作废商品行
        is_set_order_engine = False
        set_keywords = ['件套', '套装', '优惠装', '组合装']
        for item in order.items:
            if item.is_void:
                continue
            sku = item.shop_mapping_sku or ''
            if '赠品' in sku or '补差价' in sku:
                continue
            title = item.title or ''
            for kw in set_keywords:
                if kw in title:
                    is_set_order_engine = True
                    print(f"  📦 引擎检测到套装订单：商品标题包含 '{kw}'")
                    break
            if is_set_order_engine:
                break
        
        # 方式2：解析结果中存在重复的 SKU+数量 组合，且原始商品行中也有多个相同SKU
        if not is_set_order_engine and success_parsed:
            from collections import Counter
            sku_num_counter = Counter()
            for p in success_parsed:
                sku_num_counter[(_normalize_sku_for_dup(p.shop_mapping_sku), p.num)] += 1
            for key, count in sku_num_counter.items():
                if count > 1:
                    norm_sku, num = key
                    raw_count = 0
                    for item in order.items:
                        if item.is_void:
                            continue
                        item_sku = re.sub(r'<[^>]+>', '', item.shop_mapping_sku or '')
                        if not item_sku:
                            continue
                        if '赠品' in item_sku or '补差价' in item_sku:
                            continue
                        item_norm = _normalize_sku_for_dup(item_sku)
                        if item_norm == norm_sku and item.num == num:
                            raw_count += 1
                    if raw_count > 1:
                        is_set_order_engine = True
                        print(f"  📦 引擎检测到套装订单：存在 {raw_count} 个相同SKU({norm_sku[:40]})的商品行")
                        break

        if is_set_order_engine:
            print(f"  📦 套装订单：引擎SKU去重将合并数量而非删除")

        # 关键修复：按 (normalized_sku, num, original_tid) 分组，
        # 确保不同子订单的商品永不互斥去重。
        # 同一子订单内的相同SKU才需要去重（数量合并或保留最优）。
        dedup_groups = {}
        for p in success_parsed:
            norm_sku = _normalize_sku_for_dup(p.shop_mapping_sku)
            # 以 (SKU, 数量, original_tid) 为分组键，确保跨子订单不去重
            dedup_key = (norm_sku, p.num, p.original_tid or '')
            if dedup_key not in dedup_groups:
                dedup_groups[dedup_key] = []
            dedup_groups[dedup_key].append(p)

        deduped_parsed = []
        dup_removed = 0
        for dedup_key, candidates in dedup_groups.items():
            norm_sku, num, group_tid = dedup_key
            
            if len(candidates) == 1:
                deduped_parsed.append(candidates[0])
                continue

            # 套装订单：相同SKU的解析结果全部保留，不做去重删除
            # 因为套装中的每个商品行都是独立的，不应因SKU相同而去除
            if is_set_order_engine:
                for p in candidates:
                    deduped_parsed.append(p)
                continue

            # 同一子订单内的纯重复解析 → 保留最优的一个
            dup_removed += len(candidates) - 1
            best = None
            best_score = -1
            for p in candidates:
                score = 0
                if p.original_tid and "&" not in p.original_tid:
                    score = 50   # 有明确的子订单号（不含&）
                else:
                    score = 0    # 含合并号或空
                if score > best_score:
                    best_score = score
                    best = p
            if best:
                deduped_parsed.append(best)

        if dup_removed > 0:
            print(f"  🧹 合并订单去重：移除 {dup_removed} 个同子订单内的重复解析结果")

        all_parsed_list = deduped_parsed + non_success_parsed

        if not all_parsed_list and not price_diff_updates and not gift_no_ship_tids and not all_gifts:
            print(f"  ⏭️  跳过：所有分组均无法解析")
            self.stats["skipped"] += 1
            return
        
        if all_parsed_list:
            parsed = all_parsed_list[0]
            summary = (
                f"  ✅ 材质: {parsed.material_code}  "
                f"|  颜色: {parsed.color_code}  "
                f"|  尺寸: {parsed.model_code}  "
                f"|  花型: {parsed.picture_code}"
            )
            print(summary)
            
            for gift_name, gift_num, _ in all_gifts:
                print(f"  🎁 赠品: {gift_name} x {gift_num}")
        
        # ---- 缓存检查：如果订单已正确，直接跳过 ----
        expected_key = self._compute_expected_key(
            parsed_list=all_parsed_list,
            price_diff_updates=price_diff_updates,
            gift_no_ship_tids=gift_no_ship_tids,
            order=order,
        )
        if self._check_skip_cache(order, expected_key):
            self.stats["skipped"] += 1
            return
        # ------------------------------------------

        if self.dry_run:
            if all_parsed_list:
                for parsed in all_parsed_list:
                    print(f"  🔶 DRY RUN: 新编码 = {parsed.shop_mapping_sku}")
            for update in price_diff_updates:
                action = "修改编码为'定制-定制-补差价-不打印'" if not update['ship'] else "仅修改数量为1"
                print(f"  🔶 DRY RUN: 补差价订单 {update['tid'][:16]}... -> {action}")
            for tid in gift_no_ship_tids:
                print(f"  🔶 DRY RUN: 赠品不发货 {tid[:16]}... -> 修改赠品行编码为'定制-定制-补差价-不打印'")
            self._update_skip_cache(order, expected_key)
            self.stats["success"] += 1
            return
        
        if self.confirm_callback and (all_parsed_list or gift_no_ship_tids):
            changes = []
            for p in all_parsed_list:
                changes.append(f"新编码: {p.shop_mapping_sku}")
            for gift_name, gift_num, _ in all_gifts:
                changes.append(f"赠品: {gift_name} x {gift_num}")
            for update in price_diff_updates:
                action = "修改编码为'定制-定制-补差价-不打印'" if not update['ship'] else "仅修改数量为1"
                changes.append(f"补差价订单: {action}")
            for tid in gift_no_ship_tids:
                changes.append(f"赠品不发货: 修改赠品行编码为'定制-定制-补差价-不打印'")
            
            should_update = self.confirm_callback(order, all_parsed_list, changes)
            if not should_update:
                print(f"  ⏭️  用户取消（未修改）")
                self.stats["cancelled"] += 1
                return
        
        try:
            if all_parsed_list or price_diff_updates or gift_no_ship_tids:
                ok = self.adapter.update_merchant_code(order,
                    all_parsed_list[0] if all_parsed_list else None,
                    all_parsed_list,
                    price_diff_updates,
                    gift_no_ship_tids=gift_no_ship_tids,
                    engine_gifts=all_gifts,
                )
                if ok is None:
                    print(f"  ⏭️  跳过：订单所有商品行已作废")
                    self.stats["skipped"] += 1
                elif ok:
                    if all_parsed_list:
                        print(f"  ✅ 修改成功！共 {len(all_parsed_list)} 个编码")
                    if price_diff_updates:
                        print(f"  ✅ 补差价订单修改成功！")
                    if gift_no_ship_tids:
                        print(f"  ✅ 赠品不发货修改成功！")
                    self._update_skip_cache(order, expected_key)
                    self.stats["success"] += 1
                else:
                    print(f"  ❌ 修改失败")
                    self.stats["failed"] += 1
                    self.stats["errors"].append(f"订单 {order.trade_id}: 接口返回失败")
        except Exception as e:
            print(f"  ❌ 请求异常: {e}")
            self.stats["failed"] += 1
            self.stats["errors"].append(f"订单 {order.trade_id}: {e}")

    def _update_express_for_order(self, order: Order) -> bool:
        """保留现有调用入口，支持备注、店铺、平台、省份四级快递规则。"""
        return self._update_express(order)

    def _update_express(self, order: Order) -> bool:
        """根据规则自动修改订单快递（在商家编码修改成功后调用）

        逻辑：
        1. 根据店铺+平台+省份+备注解析目标快递（四级优先级）
        2. 获取当前快递编码（adapter字段 → order.raw → 备选字段名）
        3. 如果订单当前快递已与目标一致 → 跳过，打印提示
        4. 否则调用 API 修改，并更新 order.current_cp_code

        返回值：
            bool: True 表示快递满足规则可以推送，False 表示不满足规则应阻止推送
        """
        express_name, cp_code = self.express_mgr.resolve_express(
            order.receiver_province, order.shop_remark,
            store_name=order.store_name,
            platform_name=order.platform_name,
        )
        if not express_name or not cp_code:
            return True

        # 判断匹配来源，用于日志输出
        match_source = self._resolve_match_source(
            order.shop_remark, order.store_name, order.platform_name
        )

        # 获取当前快递编码
        current_code = (order.current_cp_code or "").strip().upper()
        if not current_code and order.raw:
            current_code = self._find_express_code_from_raw(order.raw)

        target_code = cp_code.strip().upper()

        # 打印快递选择信息
        source_tag = f"({match_source})" if match_source else ""
        if current_code:
            if current_code == target_code:
                print(f"  🚚 快递{source_tag}：{express_name}({cp_code}) | 当前：{current_code} | ⏭️ 已正确，跳过")
                return True
            else:
                print(f"  🚚 快递{source_tag}：{express_name}({cp_code}) | 当前：{current_code} → 需修改")
        else:
            print(f"  🚚 快递{source_tag}：{express_name}({cp_code}) | 当前：未知 → 需修改")

        if self.dry_run:
            print(f"  🔶 DRY RUN: 将快递从 [{current_code or '无'}] 改为 [{express_name}({cp_code})]")
            return True

        try:
            ok = self.adapter.update_express(order, cp_code)
            if ok:
                print(f"  ✅ 快递已改为 {express_name}({cp_code})")
                order.current_cp_code = cp_code
                return True
            else:
                print(f"  ⚠️ 修改快递失败：{express_name}({cp_code})")
                return False
        except Exception as e:
            print(f"  ⚠️ 修改快递异常: {e}")
            return False

    def _resolve_match_source(
        self, remark: str, store_name: str, platform_name: str
    ) -> str:
        """判断快递匹配的来源层级，返回中文标签用于日志"""
        remark = remark or ""
        for keyword in self.express_mgr.keyword_map:
            if keyword in remark:
                return "备注指定"
        if store_name and store_name in self.express_mgr.store_map:
            return "店铺专属"
        if platform_name and platform_name in self.express_mgr.platform_map:
            return "平台默认"
        return "省份默认"

    @staticmethod
    def _find_express_code_from_raw(raw: dict) -> str:
        """从订单原始数据中深度搜索快递编码"""
        # 常见的快递编码字段名
        code_fields = [
            "cpCode", "logisticsCompanyCode", "currentCpCode",
            "expressCode", "shippingCode",
        ]
        for field in code_fields:
            val = raw.get(field)
            if val and isinstance(val, str) and val.strip():
                return val.strip().upper()
        # 搜索 orderItems 中的物流信息（部分ERP在商品行中存储）
        items = raw.get("orderItems") or raw.get("items") or []
        for item in (items if isinstance(items, list) else []):
            if isinstance(item, dict):
                for field in code_fields:
                    val = item.get(field)
                    if val and isinstance(val, str) and val.strip():
                        return val.strip().upper()
                # 嵌套的 logisticsInfo
                logistics = item.get("logisticsInfo") or item.get("logistics") or {}
                if isinstance(logistics, dict):
                    for field in code_fields:
                        val = logistics.get(field)
                        if val and isinstance(val, str) and val.strip():
                            return val.strip().upper()
        # 搜索顶层的 logisticsInfo
        logistics = raw.get("logisticsInfo") or raw.get("logistics") or {}
        if isinstance(logistics, dict):
            for field in code_fields:
                val = logistics.get(field)
                if val and isinstance(val, str) and val.strip():
                    return val.strip().upper()
        return ""

    def _print_summary(self):
        print("\n" + "=" * 60)
        print("📊 处理汇总")
        print("=" * 60)
        print(f"  总处理:  {self.stats['total']}")
        print(f"  ✅ 成功:  {self.stats['success']}")
        print(f"  ⏭️  跳过:  {self.stats['skipped']}")
        if self.stats.get("cancelled", 0):
            print(f"  🔶 用户取消: {self.stats['cancelled']}")
        print(f"  ❌ 失败:  {self.stats['failed']}")
        if self.stats["errors"]:
            print(f"\n  ⚠️  错误明细 ({len(self.stats['errors'])}):")
            for err in self.stats["errors"][:10]:
                print(f"    • {err}")
            if len(self.stats["errors"]) > 10:
                print(f"    ... 还有 {len(self.stats['errors']) - 10} 个错误")
        print("=" * 60)
    def _get_material_context(self, order: Order | None = None) -> tuple:
        """获取材质解析上下文：material_map 和 material_matcher。

        Returns:
            (material_map, material_matcher): 适配器提供的材质映射和匹配器
        """
        material_map = getattr(self.adapter, 'material_map', None)
        order_matcher = getattr(type(self.adapter), "get_material_matcher_for_order", None)
        if order is not None and callable(order_matcher):
            material_matcher = self.adapter.get_material_matcher_for_order(order)
        else:
            material_matcher = getattr(self.adapter, 'get_material_matcher', lambda: None)()
        return material_map, material_matcher


    def push_eligible_orders(self, page_no=1, page_size=500, time_begin="", time_end=""):
        """
        推送符合条件的订单到工厂待审。

        流程：
        1. 查询待推送订单 (queryStatus=2)，允许空备注标准单，检查跳过指令与付款时间
        2. 查询待整理订单 (queryStatus=1)，检查解码状态 + 跳过关键词 + 时间，收集 tradeId
        3. 合并 tradeId 列表，调用 adapter.push_orders()

        Args:
            page_no: 页码
            page_size: 每页数量
            time_begin: 开始时间
            time_end: 结束时间
        """
        if self.should_stop():
            print("⏹️  收到停止信号，取消推单")
            return

        from datetime import timedelta
        from adapters.fangguo.config import QUERY_STATUS_PENDING_PUSH

        print("\n" + "=" * 60)
        print(f"自动推单 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.dry_run:
            print("🔶 DRY RUN 模式：仅模拟，不会真实推送")
        print("=" * 60)

        cutoff = datetime.now() - timedelta(minutes=30)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        print(f"⏰ 时间 cutoff: {cutoff_str}（只推送此时间之前付款的订单）")

        push_trade_ids = []
        from_pending_push = 0  # 来自「待推送」状态
        from_pending_audit = 0  # 来自「待整理」状态

        # ===== 来源1：待推送订单 (queryStatus=2) =====
        print("\n 查询待推送订单...")
        try:
            pending_push_orders = self.adapter.query_all_orders(
                page_size=page_size,
                query_status=QUERY_STATUS_PENDING_PUSH,
                time_begin=time_begin, time_end=time_end,
            )
        except Exception as e:
            print(f"❌ 查询待推送订单失败: {e}")
            return

        print(f"📋 待推送订单: {len(pending_push_orders)} 个")

        for order in pending_push_orders:
            if self.should_stop():
                print("⏹️  收到停止信号，终止推单，本批次未提交")
                return
            try:
                skip_reason = self._get_push_skip_reason(order, allow_blank_remark=True)
            except Exception as e:
                skip_reason = f"推送条件检查异常，需人工确认: {e}"
            if skip_reason:
                print(f"  ⏭️  跳过（待推送）: {order.tid or order.trade_id} - {skip_reason}")
                continue

            # 时间过滤
            pay_time = self._get_pay_time(order)
            if pay_time is None:
                print(f"  ⏭️  跳过（待推送）: {order.tid or order.trade_id} - 付款时间缺失或无效，无法确认已满30分钟")
                continue
            if pay_time > cutoff:
                print(f"  ️  跳过（待推送）: {order.tid or order.trade_id} - 付款时间 {pay_time} 晚于 cutoff")
                continue

            if self.should_stop():
                print("⏹️  收到停止信号，终止推单，本批次未提交")
                return

            # 快递合规检查
            try:
                express_ok = self._update_express(order)
            except Exception as e:
                print(f"  ⚠️ 快递检查异常: {order.tid or order.trade_id}: {e}")
                express_ok = False
            if not express_ok:
                print(f"  ⏭️ 跳过（待推送）: {order.tid or order.trade_id} - 快递修改失败，阻止推送")
                continue

            push_trade_ids.append(order.trade_id)
            from_pending_push += 1
            print(f"  ✅ 待推送订单加入推送列表: {order.tid or order.trade_id}")

        # ===== 来源2：待整理订单 (queryStatus=1) —— 只检查，不审单 =====
        if self.should_stop():
            print("⏹️  收到停止信号，终止推单，本批次未提交")
            return
        print("\n 查询待整理订单...")
        try:
            pending_audit_orders = self.adapter.query_all_orders(
                page_size=page_size,
                query_status=1,
                time_begin=time_begin, time_end=time_end,
            )
        except Exception as e:
            print(f" 查询待整理订单失败: {e}")
            return

        print(f" 待整理订单: {len(pending_audit_orders)} 个")

        for order in pending_audit_orders:
            if self.should_stop():
                print("⏹️  收到停止信号，终止推单，本批次未提交")
                return
            try:
                skip_reason = self._get_push_skip_reason(order)
            except Exception as e:
                skip_reason = f"推送条件检查异常，需人工确认: {e}"
            if skip_reason:
                print(f"  ⏭️  跳过（待整理）: {order.tid or order.trade_id} - {skip_reason}")
                continue

            # 时间过滤
            pay_time = self._get_pay_time(order)
            if pay_time is None:
                print(f"  ⏭️  跳过（待整理）: {order.tid or order.trade_id} - 付款时间缺失或无效，无法确认已满30分钟")
                continue
            if pay_time > cutoff:
                print(f"  ⏭️  跳过（待整理）: {order.tid or order.trade_id} - 付款时间 {pay_time} 晚于 cutoff")
                continue

            if self.should_stop():
                print("⏹️  收到停止信号，终止推单，本批次未提交")
                return

            # 快递合规检查
            try:
                express_ok = self._update_express(order)
            except Exception as e:
                print(f"  ⚠️ 快递检查异常: {order.tid or order.trade_id}: {e}")
                express_ok = False
            if not express_ok:
                print(f"  ⏭️ 跳过（待整理）: {order.tid or order.trade_id} - 快递修改失败，阻止推送")
                continue

            push_trade_ids.append(order.trade_id)
            from_pending_audit += 1
            print(f"  ✅ 待整理订单加入推送列表: {order.tid or order.trade_id}")

        push_trade_ids = list(dict.fromkeys(push_trade_ids))

        # ===== 推送 =====
        print(f"\n📤 待推送订单总数: {len(push_trade_ids)}（待推送来源: {from_pending_push}，待整理来源: {from_pending_audit}）")

        if not push_trade_ids:
            print("✅ 没有需要推送的订单")
            return

        if self.dry_run:
            print(f" DRY RUN: 将推送 {len(push_trade_ids)} 个订单（待推送: {from_pending_push} + 待整理: {from_pending_audit}）")
            print(f"   tradeIdList: {push_trade_ids[:10]}{'...' if len(push_trade_ids) > 10 else ''}")
            return

        print(f" 正在推送 {len(push_trade_ids)} 个订单（待推送: {from_pending_push} + 待整理: {from_pending_audit}）...")
        try:
            if self.should_stop():
                print("⏹️  收到停止信号，终止推单，本批次未提交")
                return
            result = self.adapter.push_orders(push_trade_ids)
            code = result.get("code")
            if code == 0:
                print(f"✅ API 响应: code=0, data={result.get('data', True)}")
                # 验证推送结果
                self._verify_push_result(push_trade_ids)
            else:
                print(f"❌ 推送失败: {result.get('msg', '未知错误')} (code={code})")
        except Exception as e:
            print(f"❌ 推送异常: {e}")


    def _verify_push_result(self, pushed_trade_ids: list[str]) -> None:
        """验证推送结果：查询工厂待审状态，确认订单已转移"""
        import time

        # 推送是异步任务，等待完成
        wait_seconds = 5
        print(f"\n⏳ 等待推送任务完成（{wait_seconds}秒）...")
        time.sleep(wait_seconds)

        print(f"\n 验证推送结果...")
        try:
            from adapters.fangguo.config import QUERY_STATUS_FACTORY_REVIEW, get_time_begin, get_time_end
            factory_orders = self.adapter.query_orders(
                page_no=1, page_size=500,
                query_status=QUERY_STATUS_FACTORY_REVIEW,
                time_begin=get_time_begin(), time_end=get_time_end(),
            )
            factory_trade_ids = {o.trade_id for o in factory_orders}
            verified = [tid for tid in pushed_trade_ids if tid in factory_trade_ids]
            missing = [tid for tid in pushed_trade_ids if tid not in factory_trade_ids]

            if not missing:
                print(f"  ✅ {len(verified)}/{len(pushed_trade_ids)} 验证通过，全部已移至工厂待审")
            else:
                print(f"  ⚠️ {len(verified)}/{len(pushed_trade_ids)} 验证通过")
                print(f"   {len(missing)} 个订单未找到（可能推送失败）:")
                for tid in missing:
                    print(f"     - {tid}")
        except Exception as e:
            print(f"  ️ 验证查询异常: {e}")


    def _get_pay_time(self, order: Order) -> datetime | None:
        """从订单 raw 数据中提取付款时间"""
        if not order.raw:
            return None

        pay_time_str = (
            order.raw.get("payTime")
            or order.raw.get("paymentTime")
            or order.raw.get("buyerPayTime")
        )
        if not pay_time_str:
            return None

        try:
            # 尝试多种时间格式
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(pay_time_str, fmt)
                except ValueError:
                    continue
            return None
        except Exception:
            return None


    @staticmethod
    def _normalize_push_sku(sku: str) -> str:
        """去除 ERP 展示标签、空白及大小写差异，保留编码业务内容。"""
        plain = re.sub(r"<[^>]*>", "", unescape(sku or ""))
        return re.sub(r"\s+", "", plain).replace("；", ";").casefold()


    def _get_push_skip_reason(self, order: Order, allow_blank_remark: bool = False) -> str:
        """核对备注要求；待推送标准单可允许空备注，仍执行共同安全检查。"""
        active_items = [item for item in order.items if not item.is_void]
        if not active_items:
            return "没有有效商品行，需人工确认"
        if any(not item.detail_enriched for item in active_items):
            return "商品详情不完整，需人工确认"

        # 商品行处于退款中状态时，整单不应推送，避免推送到已发起退款的订单。
        for item in active_items:
            refund_desc = ""
            if item.raw:
                refund_desc = str(item.raw.get("refundStatusDesc") or "")
            if "退款中" in refund_desc:
                return f"商品行 {item.id} 退款中，需人工确认"

        # 所有有效行上的延期/补差价说明都具有约束力，不能只看第一条备注。
        remarks = {order.shop_remark.strip()} if order.shop_remark else set()
        remarks.update((item.shop_remark or "").strip() for item in active_items)
        for remark in remarks:
            if _RE_PUSH_SCHEDULED_SHIP.search(remark):
                return "备注指定日期发货，需人工处理"
            if is_simple_price_diff_remark(remark.strip(" ,，。;；!！")):
                return "备注仅为补差价，不安排生产"
            for keyword in _SKIP_KEYWORDS:
                if keyword != "正常发" and keyword in remark and _is_genuine_skip_keyword(keyword, remark):
                    return f"备注含'{keyword}'"

        if self._is_decode_failed(order):
            return "解码失败或商品编码不完整"

        # 所有商品行均为补差价且商家编码含"不打印"时，无需推送生产。
        if all(
            self.adapter.is_price_difference_item(item)
            and "不打印" in self._normalize_push_sku(item.shop_mapping_sku)
            for item in active_items
        ):
            return "全部为补差价不打印商品，无需推送"

        # 不打印的差价行、赠品行不能作为主商品已完成审单的凭据。
        product_items = [
            item for item in active_items
            if not self.adapter.is_gift_item(item)
            and "不打印" not in self._normalize_push_sku(item.shop_mapping_sku)
        ]
        if not product_items:
            return "只有赠品或不打印商品，没有可生产的主商品"

        # 空备注标准单也必须遵守材质限制，不能依赖备注解析后才检查。
        blocked_materials = getattr(self.adapter, "push_blocked_materials", set())
        for item in product_items:
            material = self._normalize_push_sku(item.shop_mapping_sku).split("-", 1)[0]
            if material in blocked_materials:
                return f"材质[{material}]不允许自动推送"

        # 待推送标准单无需定制备注；商品行有备注时仍须继续校验。
        if allow_blank_remark and not any(remarks):
            return ""

        # 合并订单按子订单独立校验，避免一单有效就带着未处理的另一单推送。
        original_tids = {item.original_tid for item in product_items if item.original_tid}
        is_merged = "&" in order.tid or "&" in order.trade_id or len(original_tids) >= 2
        child_remarks: dict[str, set[str]] = {}
        if is_merged:
            for item in product_items:
                group_id = item.original_tid
                if not group_id or "&" in group_id or group_id in {order.tid, order.trade_id}:
                    return "合并订单子订单归属不明确，需人工确认"
                remark = (item.shop_remark or "").strip()
                if remark:
                    child_remarks.setdefault(group_id, set()).add(remark)
        groups: dict[tuple[str, str], list[OrderItem]] = {}
        for item in product_items:
            remark = (item.shop_remark or order.shop_remark or "").strip()
            group_id = item.original_tid if is_merged else ""
            if is_merged:
                remark = (item.shop_remark or "").strip()
                if not remark:
                    own_remarks = child_remarks.get(group_id, set())
                    if len(own_remarks) != 1:
                        return "合并订单子订单备注缺失或不明确，需人工确认"
                    remark = next(iter(own_remarks))
            groups.setdefault((group_id, remark), []).append(item)

        material_map, material_matcher = self._get_material_context(order)
        for (_, remark), items in groups.items():
            if not remark:
                return "备注为空，无商品定制信息"
            parsed_list = extract_multiple_remarks(
                _strip_reshipment_ref(remark), material_map=material_map,
                material_matcher=material_matcher,
            )
            products = [parsed for parsed in parsed_list if parsed.success]
            if not products:
                return "备注无有效商品信息，主商品尚未完成审单"
            blocked_materials = getattr(self.adapter, "push_blocked_materials", set())
            for parsed in products:
                if parsed.material_code in blocked_materials:
                    return f"材质[{parsed.material_code}]不允许自动推送"
            expected: Counter[str] = Counter()
            actual: Counter[str] = Counter()
            for parsed in products:
                expected[self._normalize_push_sku(parsed.shop_mapping_sku)] += parsed.num
            for item in items:
                actual[self._normalize_push_sku(item.shop_mapping_sku)] += item.num
            if actual != expected:
                return "主商品编码或数量与备注不一致，尚未完成审单"
        return ""


    def _is_decode_failed(self, order: Order) -> bool:
        """检查订单是否解码失败"""
        # 检查 decodeStatus 字段
        decode_status = (order.raw or {}).get("decodeStatus")
        if decode_status and "失败" in str(decode_status):
            return True

        # 检查商品行是否有解码失败的标记
        for item in order.items:
            if item.is_void:
                continue
            if item.raw:
                item_decode = item.raw.get("decodeStatus")
                if item_decode and "失败" in str(item_decode):
                    return True
            # 单个字段仍为星号或编码为空时，不能视为已完成解码。
            sku = self._normalize_push_sku(item.shop_mapping_sku)
            if not sku or re.search(r"(?:^|[-_/])\*+(?=$|[-_/])", sku):
                return True

        return False
