"""
方果ERP适配器 - 实现 ErpAdapter 接口（修复版）
====================================
修改点：接口返回失败时打印具体错误原因
"""

import re
import json
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core import ErpAdapter, Order, OrderItem, ParsedRemark, parse_remark
from core.parser import extract_multiple_remarks
from . import config as fg_config
from .material_source import get_material_source


class FangguoAdapter(ErpAdapter):
    """方果ERP适配器"""

    def __init__(self):
        self._session = self._create_session()
        self._material_source = get_material_source()
        self.material_map = fg_config.MATERIAL_MAP

    def get_adapter_name(self) -> str:
        return "方果ERP"

    # -------------------------------------------------------------------
    # Session 管理
    # -------------------------------------------------------------------

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, allowed_methods={"POST"})
        session.mount("https://", HTTPAdapter(max_retries=retry))

        _t = fg_config.TENANT_ID or "(空)"
        _a = fg_config.AUTHORIZATION[:25] + "..." if fg_config.AUTHORIZATION else "(空)"
        _c = fg_config.COOKIE_STR[:25] + "..." if fg_config.COOKIE_STR else "(空)"
        print(f"  🔍 Session使用: tenant={_t}, auth={_a}, cookie={_c}")

        session.headers.update({
            "accept": "application/json, text/plain, */*",
            "authorization": fg_config.AUTHORIZATION,
            "content-type": "application/json",
            "cookie": fg_config.COOKIE_STR,
            "from-client": "0",
            "origin": "https://fangguo.com",
            "referer": "https://fangguo.com/business/order",
            "tenant-id": fg_config.TENANT_ID,
            "x-timezone-offset": "Asia/Shanghai",
        })
        return session

    # -------------------------------------------------------------------
    # 1. 查询订单
    # -------------------------------------------------------------------

    def query_orders(
        self,
        page_no: int = 1,
        page_size: int = 500,
        query_status: int = 1,
        time_begin: str = "",
        time_end: str = "",
        **kwargs,
    ) -> list[Order]:
        """调用 queryForPageForTrade 拉取待整理订单"""
        payload = {
            "pageNo": page_no,
            "pageSize": page_size,
            "queryStatus": query_status,
            "shopId": "",
            "tidStrs": "",
            "orderType": None,
            "remarkQuery": "",
            "timeTypeQuery": 0,
            "timeBegin": time_begin,
            "timeEnd": time_end,
            "timeShortcut": "",
            "storeIdList": [],
            "cpCode": "",
            "outerOrderStatusList": [],
            "waybillType": "",
            "flagListQuery": [],
            "receiverProvinceCodeList": [],
            "receiverCity": "",
            "cpNumStrs": "",
            "inquiryModeByTitle": 1,
            "title": "",
            "inquiryModeBySkuCode": 1,
            "shopMappingSkuRange": 1,
            "shopMappingSku": "",
            "inquiryModeByOuterIid": 1,
            "outerIid": "",
            "receiverName": "",
            "receiverMobileStrs": "",
            "buyerNickStrs": "",
            "receiverAddressStrs": "",
            "tradeIdStr": kwargs.get("trade_id", ""),
            "barcode": "",
            "shopRemark": "",
            "buyerRemark": "",
            "factoryRemark": "",
            "numEqualType": None,
            "num": 0,
            "equalRangeFlag": 0,
            "shipStatusOrder": "",
            "lockStatusOrder": "",
            "discardStatusOrder": "",
            "bigPackageLPNumberStrs": "",
            "milePackageStatus": "",
            "existCpNum": "",
            "waybillPrintStatus": "",
            "urgencyType": "",
            "isPicNum": "",
            "inquiryModeByProperties": 1,
            "skuPropertiesRange": 1,
            "skuProperties": "",
            "factoryId": "",
            "custodyType": None,
            "hourType": 0,
            "logisticsStatus": "",
            "isCustomGoods": "",
            "decodeStatus": "",
            "tagListQuery": [],
            "sheinSettlementType": "",
            "numIids": "",
            "payment": 0,
            "paymentEqualType": None,
            "firstOrderStatus": [],
            "firstPrintStatus": [],
            "lastSyncStatus": [],
        }
        resp = self._session.post(fg_config.API_QUERY_ORDER, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_orders = self._parse_order_list(data)
        orders = [self._to_order(o) for o in raw_orders]
        # 补充订单详情（列表接口不返回备注和商品行）
        for order in orders:
            if not order.shop_remark or not order.items:
                self._enrich_order_with_detail(order)
        return orders

    def _parse_order_list(self, data: dict) -> list[dict]:
        d = data.get("data")
        if d is None:
            return []
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            return d.get("list") or d.get("rows") or d.get("records") or []
        return []

    def _to_order(self, raw: dict) -> Order:
        """将方果原始订单数据转为通用 Order 对象，自动适配多种字段名"""
        shop_remark = self._extract_field(raw, [
            "shopRemark", "sellerRemark", "sellerNote",
            "remark", "sellerMemo", "备注", "卖家备注",
            "shop_remark", "seller_remark",
        ])
        buyer_remark = self._extract_field(raw, [
            "buyerRemark", "buyerNote", "buyerMessage",
            "买家留言", "buyer_remark",
        ])

        order = Order(
            id=str(raw.get("id") or ""),
            trade_id=str(raw.get("tradeId") or raw.get("id") or ""),
            shop_remark=shop_remark,
            buyer_remark=buyer_remark,
            factory_id=int(raw.get("factoryId") or 0),
            sys_tid=str(raw.get("sysTid") or ""),
            tid=str(raw.get("tid") or raw.get("tradeId") or ""),
            store_name=str(raw.get("storeName") or ""),
            raw=raw,
        )

        # 如果订单级没取到备注，尝试从商品行取
        items_raw = raw.get("orderItems") or raw.get("items") or []
        if not shop_remark and items_raw:
            for it in items_raw:
                item_remark = self._extract_field(it, [
                    "shopRemark", "sellerRemark", "remark",
                    "备注", "卖家备注", "shop_remark",
                ])
                if item_remark:
                    order.shop_remark = item_remark
                    break

        # 转换商品列表
        for it in items_raw:
            is_void = it.get("discardStatus") or it.get("cancelStatus") or it.get("isVoid") or False
            refund_status = it.get("refundStatus") or it.get("refundStatusDesc") or ""
            if isinstance(is_void, int):
                is_void = is_void != 0
            if isinstance(refund_status, int):
                refund_status = refund_status != 0
            if isinstance(refund_status, str):
                is_void = is_void or ("已退款" in refund_status)
            
            # 提取商品行级别的备注
            item_remark = self._extract_field(it, [
                "shopRemark", "sellerRemark", "remark",
                "备注", "卖家备注", "shop_remark",
            ])
            
            # 提取商品行所属的原始订单号（用于合并订单的拆分）
            original_tid = str(it.get("tid") or it.get("oid") or it.get("sysOid") or "")
            
            item = OrderItem(
                id=str(it.get("id") or ""),
                order_id=str(it.get("orderId") or order.trade_id),
                sys_oid=str(it.get("sysOid") or ""),
                oid=str(it.get("oid") or order.tid),
                title=str(it.get("title") or ""),
                sku_properties_name=str(it.get("skuPropertiesName") or ""),
                shop_mapping_sku=str(it.get("shopMappingSku") or ""),
                original_sku_id=str(it.get("originalSkuId") or ""),
                original_goods_id=str(it.get("originalGoodsId") or ""),
                merchandise_pic_path=str(it.get("merchandisePicPath") or ""),
                num=int(it.get("num") or 1),
                price=float(it.get("price") or 0),
                is_void=bool(is_void),
                raw=it,
                shop_remark=item_remark,
                original_tid=original_tid,
            )
            order.items.append(item)
        return order

    # -------------------------------------------------------------------
    # 2. 获取订单详情（含卖家备注、商品行）
    # -------------------------------------------------------------------

    def fetch_order_detail(self, order_id: str = "", sys_tid: str = "") -> dict:
        """调用 getDetailsByPage 获取订单完整详情"""
        if not order_id and not sys_tid:
            return {}
        payload = {
            "shopId": "",
            "sysTid": sys_tid or order_id,
            "pageNo": 1,
            "pageSize": 100,
            "total": 1,
        }
        resp = self._session.post(fg_config.API_ORDER_DETAIL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        d = data.get("data")
        if isinstance(d, dict):
            return d
        if isinstance(d, list):
            return d[0] if d else {}
        return {}

    def _enrich_order_with_detail(self, order: Order) -> Order:
        if order.shop_remark and order.items:
            return order
        detail = self.fetch_order_detail(
            order_id=order.trade_id or order.id,
            sys_tid=order.sys_tid,
        )
        if not detail:
            return order

        # 补充卖家备注（如果缺失）
        if not order.shop_remark:
            order.shop_remark = self._extract_field(detail, [
                "shopRemark", "sellerRemark", "remark",
                "备注", "卖家备注", "shop_remark",
            ])

        # 补充商品行（如果缺失）
        if not order.items:
            items = detail.get("orderItems") or detail.get("items") or []
            for it in items:
                    is_void = it.get("discardStatus") or it.get("cancelStatus") or it.get("isVoid") or False
                    refund_status = it.get("refundStatus") or it.get("refundStatusDesc") or ""
                    if isinstance(is_void, int):
                        is_void = is_void != 0
                    if isinstance(refund_status, int):
                        refund_status = refund_status != 0
                    if isinstance(refund_status, str):
                        is_void = is_void or ("已退款" in refund_status)
                    
                    item_remark = self._extract_field(it, [
                        "shopRemark", "sellerRemark", "remark",
                        "备注", "卖家备注", "shop_remark",
                    ])
                    
                    original_tid = str(it.get("tid") or it.get("oid") or it.get("sysOid") or "")
                    
                    order.items.append(OrderItem(
                        id=str(it.get("id") or ""),
                        order_id=str(it.get("orderId") or order.trade_id),
                        sys_oid=str(it.get("sysOid") or ""),
                        oid=str(it.get("oid") or order.tid),
                        title=str(it.get("title") or ""),
                        sku_properties_name=str(it.get("skuPropertiesName") or ""),
                        shop_mapping_sku=str(it.get("shopMappingSku") or ""),
                        original_sku_id=str(it.get("originalSkuId") or ""),
                        original_goods_id=str(it.get("originalGoodsId") or ""),
                        merchandise_pic_path=str(it.get("merchandisePicPath") or ""),
                        num=int(it.get("num") or 1),
                        price=float(it.get("price") or 0),
                        is_void=bool(is_void),
                        raw=it,
                        shop_remark=item_remark,
                        original_tid=original_tid,
                    ))
        return order

    # -------------------------------------------------------------------
    # 3. 修改商家编码（带详细错误日志）
    # -------------------------------------------------------------------
    def update_merchant_code(self, order: Order, parsed: ParsedRemark, parsed_list: list = None, price_diff_updates: list = None) -> bool:
        """
        调用 saveProduct 接口更新商家编码
        支持多尺寸：如果备注中有多个尺寸，会拆分成多个商品行
        支持赠品：检测已有赠品行并更新数量，或创建新的赠品行
        支持补差价订单：通过 price_diff_updates 参数处理补差价商品行
        
        强制修复逻辑：
        1. 即使订单被标记为"解码失败"也能强制重新修改
        2. 清理所有多余的错误商品行（包括被错误标记为赠品的行）
        3. 完全基于解析结果重建 orderItems，确保没有重复
        
        作废商品行处理逻辑：
        1. 如果所有非赠品行都已作废，跳过整个订单
        2. 如果部分商品行已作废，跳过作废行，使用有效行进行修改
        3. 如果有效行数不足，创建新商品行
        
        Args:
            price_diff_updates: 补差价商品行更新列表，每个元素包含 {'items': [...], 'ship': True/False}
                               - ship=True: 仅修改数量为1
                               - ship=False: 修改编码为"定制-定制-补差价-不打印"，数量改为1
        """
        # 检测是否为合并订单（解析结果带有 original_tid）
        is_merged_order = any(p.original_tid for p in (parsed_list or []))
        
        # 合并订单跳过 _split_parsed_by_sizes，因为解析结果已经按分组处理过了
        if parsed_list and len(parsed_list) > 1:
            effective_list = parsed_list
        elif not is_merged_order:
            effective_list = self._split_parsed_by_sizes(order, parsed)
        else:
            effective_list = parsed_list or [parsed]

        # 获取期望的商品编码集合（包含数量）
        expected_skus_set = {p.shop_mapping_sku for p in effective_list}
        expected_sku_num_set = {(p.shop_mapping_sku, p.num) for p in effective_list}
        
        # 调试日志：打印每个商品行的信息
        print(f"  📋 商品行详情 ({len(order.items)} 行):")
        for idx, item in enumerate(order.items):
            is_gift = self._is_gift_item(item)
            film_gift_code = item.raw.get('filmGiftCode', '') if item.raw else ''
            print(f"    [{idx}] id={item.id[:10]}..., title={item.title[:30]}..., is_void={item.is_void}, is_gift={is_gift}, filmGiftCode='{film_gift_code}', original_tid='{item.original_tid[:10]}'...")
        
        # 获取所有非赠品、非补差价、非作废的有效商品行
        valid_items = [item for item in order.items if not self._is_gift_item(item) and not self._is_price_difference_item(item) and not item.is_void]
        valid_indices = [idx for idx, item in enumerate(order.items) if not self._is_gift_item(item) and not self._is_price_difference_item(item) and not item.is_void]
        
        # 检查是否存在任何已作废或已退款的非赠品、非补差价商品行
        non_gift_non_price_diff_items = [item for item in order.items if not self._is_gift_item(item) and not self._is_price_difference_item(item)]
        void_non_gift_items = [item for item in non_gift_non_price_diff_items if item.is_void]
        if void_non_gift_items:
            print(f"  ⏭️  跳过：存在已作废或已退款的商品行")
            return None
        
        # 检查当前订单是否已经完全正确
        # 合并订单需要验证每个商品行的 original_tid 和 SKU 是否都匹配
        is_already_correct = False
        if len(valid_items) == len(effective_list):
            if is_merged_order:
                # 合并订单：按 original_tid 验证每个商品行的 SKU 和数量是否正确
                parsed_by_tid = {p.original_tid: p for p in effective_list if p.original_tid}
                all_matched = True
                for item in valid_items:
                    p = parsed_by_tid.get(item.original_tid)
                    if p and (item.shop_mapping_sku != p.shop_mapping_sku or item.num != p.num):
                        all_matched = False
                        break
                    if not p and item.shop_mapping_sku:
                        all_matched = False
                        break
                is_already_correct = all_matched
            else:
                # 普通订单：比较SKU和数量
                current_sku_num_set = {(item.shop_mapping_sku, item.num) for item in valid_items if item.shop_mapping_sku}
                is_already_correct = current_sku_num_set == expected_sku_num_set
        
        if is_already_correct:
            # 检查补差价商品行是否也已经正确
            price_diff_already_correct = True
            if price_diff_updates:
                for update in price_diff_updates:
                    for item in update['items']:
                        if update['ship']:
                            if item.num != 1:
                                price_diff_already_correct = False
                                break
                        else:
                            expected_sku = "定制-定制-补差价-不打印"
                            if item.shop_mapping_sku != expected_sku or item.num != 1:
                                price_diff_already_correct = False
                                break
                    if not price_diff_already_correct:
                        break
            
            if price_diff_already_correct:
                gift_name = ""
                gift_num = 0
                for p in effective_list:
                    if p.gift_name:
                        gift_name = p.gift_name
                        gift_num = p.gift_num
                        break
                
                if not gift_name:
                    print(f"  ✅ 编码已正确，跳过修改")
                    return True

        # 完全重建 orderItems，基于解析结果
        # 使用第一个有效商品行作为模板，保留必要的原始字段
        template_item = valid_items[0] if valid_items else (order.items[0] if order.items else None)

        order_items = []
        used_item_indices = set()

        # 获取所有非赠品、非补差价、非作废的有效商品行索引
        valid_indices = [idx for idx, item in enumerate(order.items) if not self._is_gift_item(item) and not self._is_price_difference_item(item) and not item.is_void]

        # 第一步：为每个解析结果创建商品行（按 original_tid 匹配）
        for p in effective_list:
            matched_item_idx = None
            match_method = "unknown"
            
            # 如果解析结果有 original_tid，按 original_tid 匹配商品行
            if p.original_tid:
                for idx in valid_indices:
                    if idx not in used_item_indices:
                        item = order.items[idx]
                        if item.original_tid == p.original_tid:
                            matched_item_idx = idx
                            match_method = "original_tid"
                            break
            
            # 如果没有匹配到，按顺序使用未使用的有效商品行
            if matched_item_idx is None:
                for idx in valid_indices:
                    if idx not in used_item_indices:
                        matched_item_idx = idx
                        match_method = "sequential"
                        break
            
            if matched_item_idx is not None:
                matched_item = order.items[matched_item_idx]
                print(f"    匹配: 解析结果[{p.shop_mapping_sku[:30]}...] -> 商品行[{matched_item_idx}] original_tid={matched_item.original_tid[:10]}... 方法={match_method}")
                # 使用现有有效行作为基础，替换编码信息
                new_item = self._build_order_item(matched_item, order, p)
                # 确保普通商品行不是赠品
                new_item['filmGiftCode'] = ''
                new_item['giftCodeName'] = None
                new_item['filmGiftNum'] = 0
                used_item_indices.add(matched_item_idx)
            elif template_item:
                # 超出原有效行数，创建新商品行
                new_item = self._build_new_item(order, p)
            else:
                # 没有模板，使用默认构造
                new_item = self._build_default_item(order, p)
            order_items.append(new_item)

        # 第二步：处理赠品（如果有）
        gift_name = ""
        gift_num = 0
        material_code = ""
        gift_original_tid = ""
        for p in effective_list:
            if p.gift_name:
                gift_name = p.gift_name
                gift_num = p.gift_num
                gift_original_tid = p.original_tid
            if p.material_code:
                material_code = p.material_code

        if gift_name and gift_num > 0:
            effective_material_code = material_code or "吸水皮革"
            # 查找现有赠品行
            existing_gift_idx = None
            for idx, item in enumerate(order.items):
                if idx not in used_item_indices and self._is_gift_item(item):
                    existing_gift_idx = idx
                    break
            
            if existing_gift_idx is not None:
                # 更新现有赠品行
                new_gift = self._build_gift_item(order.items[existing_gift_idx], order, effective_material_code, gift_name, gift_num, is_new=False, original_tid=gift_original_tid)
                order_items.append(new_gift)
            else:
                # 创建新赠品行（标识字段置空，ERP会创建新行）
                if template_item:
                    new_gift = self._build_gift_item(template_item, order, effective_material_code, gift_name, gift_num, is_new=True, original_tid=gift_original_tid)
                else:
                    new_gift = self._build_gift_item(
                        OrderItem(id=order.trade_id, order_id=order.trade_id, oid=order.tid, num=1),
                        order, effective_material_code, gift_name, gift_num, is_new=True, original_tid=gift_original_tid,
                    )
                order_items.append(new_gift)

        # 第二步.5：如果备注中没有赠品信息，但订单中存在赠品行，保留现有赠品行不变
        # 这确保赠品行在没有备注说明时保持原样，不会被误修改或删除
        if not gift_name:
            for idx, item in enumerate(order.items):
                if idx not in used_item_indices and self._is_gift_item(item):
                    if item.raw:
                        order_items.append(item.raw)
                    else:
                        order_items.append({
                            "id": item.id,
                            "orderId": item.order_id,
                            "sysOid": item.sys_oid,
                            "oid": item.oid,
                            "title": item.title,
                            "shopMappingSku": item.shop_mapping_sku,
                            "num": item.num,
                            "price": item.price,
                        })

        # 第三步：保留未匹配的非作废、非赠品、非补差价商品行（保持原样，不修改）
        # 这对于合并订单非常重要：被跳过的子订单的商品行需要保留
        for idx, item in enumerate(order.items):
            if idx not in used_item_indices and not item.is_void and not self._is_gift_item(item) and not self._is_price_difference_item(item):
                if item.raw:
                    order_items.append(item.raw)
                else:
                    order_items.append({
                        "id": item.id,
                        "orderId": item.order_id,
                        "sysOid": item.sys_oid,
                        "oid": item.oid,
                        "title": item.title,
                        "skuPropertiesName": item.sku_properties_name,
                        "shopMappingSku": item.shop_mapping_sku,
                        "originalSkuId": item.original_sku_id,
                        "originalGoodsId": item.original_goods_id,
                        "merchandisePicPath": item.merchandise_pic_path,
                        "num": item.num,
                        "price": item.price,
                        "shopRemark": item.shop_remark or "",
                    })

        # 第四步：保留作废商品行（保持原样，不修改）
        for idx, item in enumerate(order.items):
            if idx not in used_item_indices and item.is_void:
                if item.raw:
                    order_items.append(item.raw)
                else:
                    order_items.append({
                        "id": item.id,
                        "orderId": item.order_id,
                        "sysOid": item.sys_oid,
                        "oid": item.oid,
                        "title": item.title,
                        "num": item.num,
                        "price": item.price,
                        "shopMappingSku": item.shop_mapping_sku,
                        "cancelStatus": True,
                    })

        # 第五步：处理补差价商品行
        if price_diff_updates:
            for update in price_diff_updates:
                for item in update['items']:
                    item_idx = None
                    for idx, ord_item in enumerate(order.items):
                        if ord_item.id == item.id:
                            item_idx = idx
                            break
                    
                    if item_idx is not None and item_idx not in used_item_indices:
                        if update['ship']:
                            new_item = self._build_order_item_keep_sku(item, order, num=1)
                        else:
                            new_item = self._build_price_diff_no_ship_item(item, order)
                        order_items.append(new_item)
                        used_item_indices.add(item_idx)

        payload = {
            "orderType": 0,
            "id": order.trade_id,
            "shopRemark": order.shop_remark or "",
            "buyerRemark": order.buyer_remark or "",
            "factoryId": order.factory_id,
            "platform": 0,
            "platformDesc": "",
            "allManualOrder": False,
            "sysTid": order.sys_tid,
            "tid": order.tid,
            "dfStatus": 0,
            "tradeInitNum": 1,
            "orderItems": order_items,
            "totalCount": len(order_items),
            "outerOrderStatusDesc": "",
            "storeName": order.store_name,
            "goodsIndex": 0,
            "shopId": "",
        }

        # 打印payload摘要用于调试
        try:
            payload_str = json.dumps(payload, ensure_ascii=False)
            if len(payload_str) > 2000:
                print(f"  📤 发送payload: totalCount={payload['totalCount']}, items={len(payload['orderItems'])}个")
                for i, it in enumerate(payload['orderItems']):
                    print(f"      item[{i}]: id={it.get('id','')}, oid={it.get('oid','')}, sku={str(it.get('shopMappingSku',''))[:50]}")
            else:
                print(f"  📤 发送payload: {payload_str[:500]}")
        except:
            pass

        resp = self._session.post(fg_config.API_SAVE_PRODUCT, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        # ===== 判断 API 返回结果 =====
        # 方果返回: {"code": 0, "data": true, "msg": ""}
        if result.get("code") == 0 and result.get("data") is True:
            return True
        else:
            error_msg = result.get("msg", "未知错误")
            raw_body = json.dumps(result, ensure_ascii=False, indent=2)
            print(f"  ❌ 接口返回失败: code={result.get('code')}, msg={error_msg}")
            print(f"  🔍 API返回原文:\n{raw_body}")
            return False

    def _split_parsed_by_sizes(self, order: Order, parsed: ParsedRemark) -> list[ParsedRemark]:
        """如果备注中包含多个尺寸，拆成多个 ParsedRemark"""
        remark = order.shop_remark or ""
        if not remark:
            return [parsed]

        multi_parsed = extract_multiple_remarks(
            remark,
            material_map=self.material_map,
            material_matcher=self.get_material_matcher(),
        )

        if len(multi_parsed) > 1:
            for p in multi_parsed:
                p.original_tid = parsed.original_tid
            return multi_parsed

        return [parsed]

    def _build_order_item(self, item: OrderItem, order: Order, parsed: ParsedRemark) -> dict:
        return {
            "materialId": None,
            "materialCode": parsed.material_code,
            "materialCodeName": None,
            "technology": None,
            "printWayId": None,
            "multiImageUrlExists": None,
            "multiHolePic": None,
            "multiImageExists": None,
            "modelId": None,
            "modelCode": parsed.model_code,
            "modelCodeName": None,
            "brand": None,
            "customSize": True,
            "isCompactModel": None,
            "compactFactoryModelCode": None,
            "compactFactoryModelName": None,
            "compactFactoryModelId": None,
            "colorId": None,
            "colorCode": parsed.color_code,
            "colorCodeName": None,
            "customPicture": True,
            "pictureId": None,
            "pictureType": None,
            "pictureCode": parsed.picture_code,
            "picTypeId": None,
            "pictureCodePath": None,
            "pictureEffectPicPath": None,
            "familyNamePic": None,
            "folderId": None,
            "mustUrlPictureCheckSuccess": False,
            "designerPicCheck": None,
            "sizeMap": None,
            "designPicList": None,
            "effectPicList": None,
            "factorySkuId": None,
            "putSale": None,
            "stockOut": None,
            "combinationGoods": False,
            "factorySkuShopIdS": None,
            "holeSitePic": None,
            "picTechnology": None,
            "map4decodeGift": None,
            "map4FactoryDecodeGift": None,
            "multiplePicList": None,
            "giftBOList": [],
            "giftList": None,
            "giftMaterialList": None,
            "giftCodeName": None,
            "filmGiftCodeId": None,
            "filmGiftCode": "",
            "filmGiftNum": 0,
            "filmGiftPicCode": None,
            "decorationGiftCodeId": None,
            "decorationGiftCode": "",
            "decorationGiftNum": 0,
            "decorationGiftPicCode": None,
            "giftsWithOrder": [],
            "picChange": 0,
            "orderId": item.order_id,
            "originalSkuId": item.original_sku_id,
            "originalGoodsId": item.original_goods_id,
            "id": item.id,
            "sysOid": item.sys_oid,
            "oid": item.oid,
            "title": item.title,
            "merchandisePicPath": item.merchandise_pic_path,
            "workUrl": None,
            "effectUrl": None,
            "productionPicPath": None,
            "num": parsed.num,
            "price": item.price,
            "skuPropertiesName": item.sku_properties_name,
            "outerIid": "",
            "shopMappingSku": parsed.shop_mapping_sku,
            "diyList": [{
                "bg": "", "mask": "", "picName": "",
                "isPicMove": 1, "sort": 1,
                "effectUrl": "", "workUrl": "",
                "mobileIdentityNo": None, "picSourceType": 0,
                "layerList": [], "mobileLayerList": None, "lastImgUrl": None,
            }],
            "productType": 0,
            "productSn": None,
            "boxGiftCode": None,
            "shopRemark": order.shop_remark or "",
            "buyerRemark": order.buyer_remark or "",
            "tid": order.tid,
            "originTradeId": order.trade_id,
            "oldSysTid": None,
            "magnifyingSelectPic": False,
            "copySortFlag": 1,
            "logisticsOrderNum": None,
            "logisticsCompanyCode": "ZTO",
            "picType": 0,
            "oldPicWatermarkFlag": 0,
            "maxSendNum": None,
            "isCombinationGoods": False,
            "deriveSysOid": None,
            "inventoryNum": None,
            "picCode": parsed.picture_code,
            "lockStatusDesc": "",
            "lockStatus": False,
            "packageQuantity": None,
            "refundStatusDesc": "",
            "cancelStatus": False,
            "realModelCode": parsed.model_code,
            "realModelId": None,
            "type": 0,
            "showRemarkInfo": True,
            "check": True,
            "loaded": True,
        }

    def _build_default_item(self, order: Order, parsed: ParsedRemark) -> dict:
        """没有商品行时的默认构造（新建行，ERP会创建新行）"""
        return self._build_order_item(
            OrderItem(id=None, order_id=order.trade_id,
                      oid=None, sys_oid=None, num=parsed.num),
            order, parsed,
        )

    def _build_new_item(self, order: Order, parsed: ParsedRemark) -> dict:
        """超出原订单商品行数时，构建新商品行（所有标识字段置空，ERP创建新行）"""
        return self._build_order_item(
            OrderItem(id=None, order_id=order.trade_id,
                      oid=None, sys_oid=None,
                      original_sku_id=None, original_goods_id=None,
                      title=None, merchandise_pic_path=None,
                      price=0, num=parsed.num),
            order, parsed,
        )

    def _build_gift_item(self, item: OrderItem, order: Order, material_code: str, gift_name: str, gift_num: int, is_new: bool = False, original_tid: str = "") -> dict:
        """构建赠品商品行
        
        Args:
            is_new: 是否为创建新赠品行。如果为True，标识字段置空，ERP会创建新行；
                    如果为False，保留原商品行的标识字段，用于更新现有赠品行
            original_tid: 赠品所属的原始订单号，用于合并订单场景
        """
        gift_material = "吸水皮革"
        if "圆垫" in gift_name:
            model_code = "赠品沥水垫小圆或小方"
            picture_code = "赠品沥水垫小圆或小方"
            gift_code = "赠品沥水垫小圆或小方"
        elif "方垫" in gift_name:
            model_code = "30x50"
            picture_code = "随机发；30x50"
            gift_code = "30x50-随机发；30x50"
        else:
            model_code = "赠品沥水垫小圆或小方"
            picture_code = "赠品沥水垫小圆或小方"
            gift_code = "赠品沥水垫小圆或小方"

        if is_new:
            id_field = None
            sys_oid_field = None
            oid_field = None
            original_sku_id_field = None
            original_goods_id_field = None
            title_field = gift_name or ""
            merchandise_pic_path_field = None
            sku_properties_name_field = ""
        else:
            id_field = item.id
            sys_oid_field = item.sys_oid
            oid_field = item.oid
            original_sku_id_field = item.original_sku_id
            original_goods_id_field = item.original_goods_id
            title_field = gift_name or ""
            merchandise_pic_path_field = item.merchandise_pic_path
            sku_properties_name_field = ""

        return {
            "materialId": None,
            "materialCode": gift_material,
            "materialCodeName": None,
            "technology": None,
            "printWayId": None,
            "multiImageUrlExists": None,
            "multiHolePic": None,
            "multiImageExists": None,
            "modelId": None,
            "modelCode": model_code,
            "modelCodeName": None,
            "brand": None,
            "customSize": False,
            "isCompactModel": None,
            "compactFactoryModelCode": None,
            "compactFactoryModelName": None,
            "compactFactoryModelId": None,
            "colorId": None,
            "colorCode": "标准",
            "colorCodeName": None,
            "customPicture": False,
            "pictureId": None,
            "pictureType": None,
            "pictureCode": picture_code,
            "picTypeId": None,
            "pictureCodePath": None,
            "pictureEffectPicPath": None,
            "familyNamePic": None,
            "folderId": None,
            "mustUrlPictureCheckSuccess": False,
            "designerPicCheck": None,
            "sizeMap": None,
            "designPicList": None,
            "effectPicList": None,
            "factorySkuId": None,
            "putSale": None,
            "stockOut": None,
            "combinationGoods": False,
            "factorySkuShopIdS": None,
            "holeSitePic": None,
            "picTechnology": None,
            "map4decodeGift": None,
            "map4FactoryDecodeGift": None,
            "multiplePicList": None,
            "giftBOList": [],
            "giftList": None,
            "giftMaterialList": None,
            "giftCodeName": None,
            "filmGiftCodeId": None,
            "filmGiftCode": "",
            "filmGiftNum": 0,
            "filmGiftPicCode": None,
            "decorationGiftCodeId": None,
            "decorationGiftCode": "",
            "decorationGiftNum": 0,
            "decorationGiftPicCode": None,
            "giftsWithOrder": [],
            "picChange": 0,
            "orderId": original_tid or order.trade_id,
            "originalSkuId": original_sku_id_field,
            "originalGoodsId": original_goods_id_field,
            "id": id_field,
            "sysOid": sys_oid_field,
            "oid": oid_field,
            "title": title_field,
            "merchandisePicPath": merchandise_pic_path_field,
            "workUrl": None,
            "effectUrl": None,
            "productionPicPath": None,
            "num": gift_num,
            "price": 0,
            "skuPropertiesName": sku_properties_name_field,
            "outerIid": "",
            "shopMappingSku": f"{gift_material}-标准-{model_code}-{picture_code}",
            "diyList": [{
                "bg": "", "mask": "", "picName": "",
                "isPicMove": 1, "sort": 1,
                "effectUrl": "", "workUrl": "",
                "mobileIdentityNo": None, "picSourceType": 0,
                "layerList": [], "mobileLayerList": None, "lastImgUrl": None,
            }],
            "productType": 0,
            "productSn": None,
            "boxGiftCode": None,
            "shopRemark": order.shop_remark or "",
            "buyerRemark": order.buyer_remark or "",
            "tid": original_tid or order.tid,
            "originTradeId": original_tid or order.trade_id,
            "oldSysTid": None,
            "magnifyingSelectPic": False,
            "copySortFlag": 1,
            "logisticsOrderNum": None,
            "logisticsCompanyCode": "ZTO",
            "picType": 0,
            "oldPicWatermarkFlag": 0,
            "maxSendNum": None,
            "isCombinationGoods": False,
            "deriveSysOid": None,
            "inventoryNum": None,
            "picCode": picture_code,
            "lockStatusDesc": "",
            "lockStatus": False,
            "packageQuantity": None,
            "refundStatusDesc": "",
            "cancelStatus": False,
            "realModelCode": model_code,
            "realModelId": None,
            "type": 0,
            "showRemarkInfo": True,
            "check": True,
            "loaded": True,
        }

    def _handle_gift_item(self, order_items: list, order: Order, material_code: str,
                          gift_name: str, gift_num: int, template_item: OrderItem,
                          used_item_indices: set, original_tid: str = "") -> int | None:
        """处理赠品：更新已有赠品行或创建新的"""
        gift_material = "吸水皮革"
        if "圆垫" in gift_name:
            model_code = "赠品沥水垫小圆或小方"
            picture_code = "赠品沥水垫小圆或小方"
            gift_code = "赠品沥水垫小圆或小方"
        elif "方垫" in gift_name:
            model_code = "30x50"
            picture_code = "随机发；30x50"
            gift_code = "30x50-随机发；30x50"
        else:
            model_code = "赠品沥水垫小圆或小方"
            picture_code = "赠品沥水垫小圆或小方"
            gift_code = "赠品沥水垫小圆或小方"
        gift_sku = f"{gift_material}-标准-{model_code}-{picture_code}"
        
        for idx, item in enumerate(order.items):
            if idx not in used_item_indices and self._is_gift_item(item):
                cloned = item.raw.copy() if item.raw else {}
                if cloned:
                    cloned['filmGiftNum'] = gift_num
                    cloned['shopRemark'] = order.shop_remark or ""
                    cloned['buyerRemark'] = order.buyer_remark or ""
                    cloned['materialCode'] = gift_material
                    cloned['modelCode'] = model_code
                    cloned['colorCode'] = "标准"
                    cloned['pictureCode'] = picture_code
                    cloned['picCode'] = picture_code
                    cloned['giftCodeName'] = None
                    cloned['filmGiftCode'] = ""
                    cloned['filmGiftNum'] = 0
                    cloned['filmGiftPicCode'] = None
                    cloned['shopMappingSku'] = gift_sku
                    cloned['realModelCode'] = model_code
                    cloned['title'] = gift_name or ""
                    cloned['skuPropertiesName'] = ""
                    if original_tid:
                        cloned['orderId'] = original_tid
                        cloned['tid'] = original_tid
                        cloned['originTradeId'] = original_tid
                    order_items.append(cloned)
                    used_item_indices.add(idx)
                    return idx
                else:
                    new_gift = self._build_gift_item(item, order, material_code, gift_name, gift_num, is_new=False, original_tid=original_tid)
                    order_items.append(new_gift)
                    used_item_indices.add(idx)
                    return idx

        # 没有找到现有赠品，创建新的赠品行
        if template_item:
            new_gift = self._build_gift_item(template_item, order, material_code, gift_name, gift_num, is_new=True, original_tid=original_tid)
        else:
            new_gift = self._build_gift_item(
                OrderItem(id=order.trade_id, order_id=order.trade_id, oid=order.tid, num=1),
                order, material_code, gift_name, gift_num, is_new=True, original_tid=original_tid,
            )

        order_items.append(new_gift)
        return len(order_items) - 1

    _PRICE_DIFF_KEYWORDS = ["补差价专拍", "差价专用", "少几元拍几个"]

    def _is_gift_item(self, item: OrderItem) -> bool:
        """判断一个商品行是否是赠品行
        
        检测方式（任一满足即为赠品）：
        1. filmGiftCode 字段非空
        2. 商品标题包含"赠品"
        3. shop_mapping_sku 包含"赠品"
        4. price为0且标题包含"垫"（常见赠品如沥水垫、防滑垫等）
        """
        # 方式1：检查 filmGiftCode 字段
        gift_code = item.raw.get('filmGiftCode', '') if item.raw else ''
        if gift_code:
            return True
        
        # 方式2：检查标题是否包含"赠品"
        title = item.title or ''
        if '赠品' in title:
            return True
        
        # 方式3：检查 shop_mapping_sku 是否包含"赠品"
        sku = item.shop_mapping_sku or ''
        if '赠品' in sku:
            return True
        
        # 方式4：检查 price 为0 且标题包含"垫"（常见赠品）
        if item.price == 0 and '垫' in title:
            return True
        
        return False

    def _is_price_difference_item(self, item: OrderItem) -> bool:
        """判断商品行是否为补差价商品"""
        if item.title:
            for keyword in self._PRICE_DIFF_KEYWORDS:
                if keyword in item.title:
                    return True
        return False

    # -------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------

    def _extract_field(self, data: dict, field_names: list[str]) -> str:
        for name in field_names:
            val = data.get(name)
            if val:
                return str(val).strip()
        return ""

    def get_material_matcher(self):
        """返回材质自动匹配回调"""
        return self._material_source.auto_match if hasattr(self._material_source, 'auto_match') else None

    def update_price_difference_order(self, order: Order, items: list = None, ship: bool = True) -> bool:
        """
        处理补差价订单：
        - ship=True: 仅修改数量为1（默认，差价需要发货）
        - ship=False: 修改编码为"定制-定制-补差价-不打印"，数量改为1（差价不发货）
        
        Args:
            order: 订单对象
            items: 指定要修改的商品行列表（用于合并订单，默认使用所有商品行）
            ship: 是否需要发货，False表示不发货（使用特殊编码）
        """
        target_items = items or order.items
        
        print(f"  🔧 处理补差价订单: ship={ship}, items={len(target_items)}")
        
        # 检查是否已经正确，跳过重复修改
        is_already_correct = True
        for item in target_items:
            if ship:
                # ship=True: 检查数量是否已经为1
                if item.num != 1:
                    is_already_correct = False
                    break
            else:
                # ship=False: 检查编码是否为"定制-定制-补差价-不打印"且数量为1
                expected_sku = "定制-定制-补差价-不打印"
                if item.shop_mapping_sku != expected_sku or item.num != 1:
                    is_already_correct = False
                    break
        
        if is_already_correct:
            print(f"  ✅ 补差价订单编码已正确，跳过修改")
            return None
        
        order_items = []
        used_item_indices = set()
        
        for idx, item in enumerate(order.items):
            if item in target_items:
                if ship:
                    new_item = self._build_order_item_keep_sku(item, order, num=1)
                else:
                    new_item = self._build_price_diff_no_ship_item(item, order)
                order_items.append(new_item)
                used_item_indices.add(idx)
            else:
                if item.raw:
                    order_items.append(item.raw)
                else:
                    order_items.append({
                        "id": item.id,
                        "orderId": item.order_id,
                        "sysOid": item.sys_oid,
                        "oid": item.oid,
                        "title": item.title,
                        "skuPropertiesName": item.sku_properties_name,
                        "shopMappingSku": item.shop_mapping_sku,
                        "originalSkuId": item.original_sku_id,
                        "originalGoodsId": item.original_goods_id,
                        "merchandisePicPath": item.merchandise_pic_path,
                        "num": item.num,
                        "price": item.price,
                        "shopRemark": item.shop_remark or "",
                    })
        
        payload = {
            "orderType": 0,
            "id": order.trade_id,
            "shopRemark": order.shop_remark or "",
            "buyerRemark": order.buyer_remark or "",
            "factoryId": order.factory_id,
            "platform": 0,
            "platformDesc": "",
            "allManualOrder": False,
            "sysTid": order.sys_tid,
            "tid": order.tid,
            "dfStatus": 0,
            "tradeInitNum": 1,
            "orderItems": order_items,
            "totalCount": len(order_items),
            "outerOrderStatusDesc": "",
            "storeName": order.store_name,
            "goodsIndex": 0,
            "shopId": "",
        }
        
        try:
            payload_str = json.dumps(payload, ensure_ascii=False)
            if len(payload_str) > 2000:
                print(f"  📤 发送payload: totalCount={payload['totalCount']}, items={len(payload['orderItems'])}个")
                for i, it in enumerate(payload['orderItems']):
                    print(f"      item[{i}]: id={it.get('id','')}, oid={it.get('oid','')}, sku={str(it.get('shopMappingSku',''))[:50]}, num={it.get('num',1)}")
            else:
                print(f"  📤 发送payload: {payload_str[:500]}")
        except:
            pass
        
        resp = self._session.post(fg_config.API_SAVE_PRODUCT, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("code") == 0 and result.get("data") is True:
            return True
        else:
            error_msg = result.get("msg", "未知错误")
            raw_body = json.dumps(result, ensure_ascii=False, indent=2)
            print(f"  ❌ 接口返回失败: code={result.get('code')}, msg={error_msg}")
            print(f"  🔍 API返回原文:\n{raw_body}")
            return False

    def _build_order_item_keep_sku(self, item: OrderItem, order: Order, num: int = 1) -> dict:
        """
        构建商品行，保持原有商家编码不变，仅修改数量
        """
        return {
            "materialId": None,
            "materialCode": item.raw.get("materialCode", "") if item.raw else "",
            "materialCodeName": None,
            "technology": None,
            "printWayId": None,
            "multiImageUrlExists": None,
            "multiHolePic": None,
            "multiImageExists": None,
            "modelId": None,
            "modelCode": item.raw.get("modelCode", "") if item.raw else "",
            "modelCodeName": None,
            "brand": None,
            "customSize": True,
            "isCompactModel": None,
            "compactFactoryModelCode": None,
            "compactFactoryModelName": None,
            "compactFactoryModelId": None,
            "colorId": None,
            "colorCode": item.raw.get("colorCode", "") if item.raw else "",
            "colorCodeName": None,
            "customPicture": True,
            "pictureId": None,
            "pictureType": None,
            "pictureCode": item.raw.get("pictureCode", "") if item.raw else "",
            "picTypeId": None,
            "pictureCodePath": None,
            "pictureEffectPicPath": None,
            "familyNamePic": None,
            "folderId": None,
            "mustUrlPictureCheckSuccess": False,
            "designerPicCheck": None,
            "sizeMap": None,
            "designPicList": None,
            "effectPicList": None,
            "factorySkuId": None,
            "putSale": None,
            "stockOut": None,
            "combinationGoods": False,
            "factorySkuShopIdS": None,
            "holeSitePic": None,
            "picTechnology": None,
            "map4decodeGift": None,
            "map4FactoryDecodeGift": None,
            "multiplePicList": None,
            "giftBOList": [],
            "giftList": None,
            "giftMaterialList": None,
            "giftCodeName": None,
            "filmGiftCodeId": None,
            "filmGiftCode": "",
            "filmGiftNum": 0,
            "filmGiftPicCode": None,
            "decorationGiftCodeId": None,
            "decorationGiftCode": "",
            "decorationGiftNum": 0,
            "decorationGiftPicCode": None,
            "giftsWithOrder": [],
            "picChange": 0,
            "orderId": item.order_id,
            "originalSkuId": item.original_sku_id,
            "originalGoodsId": item.original_goods_id,
            "id": item.id,
            "sysOid": item.sys_oid,
            "oid": item.oid,
            "title": item.title,
            "merchandisePicPath": item.merchandise_pic_path,
            "workUrl": None,
            "effectUrl": None,
            "productionPicPath": None,
            "num": num,
            "price": item.price,
            "skuPropertiesName": item.sku_properties_name,
            "outerIid": "",
            "shopMappingSku": item.shop_mapping_sku,
            "diyList": [{
                "bg": "", "mask": "", "picName": "",
                "isPicMove": 1, "sort": 1,
                "effectUrl": "", "workUrl": "",
                "mobileIdentityNo": None, "picSourceType": 0,
                "layerList": [], "mobileLayerList": None, "lastImgUrl": None,
            }],
            "productType": 0,
            "productSn": None,
            "boxGiftCode": None,
            "shopRemark": order.shop_remark or "",
            "buyerRemark": order.buyer_remark or "",
            "tid": order.tid,
            "originTradeId": order.trade_id,
            "oldSysTid": None,
            "magnifyingSelectPic": False,
            "copySortFlag": 1,
            "logisticsOrderNum": None,
            "logisticsCompanyCode": "ZTO",
            "picType": 0,
            "oldPicWatermarkFlag": 0,
            "maxSendNum": None,
            "isCombinationGoods": False,
            "deriveSysOid": None,
            "inventoryNum": None,
            "picCode": item.raw.get("pictureCode", "") if item.raw else "",
            "lockStatusDesc": "",
            "lockStatus": False,
            "packageQuantity": None,
            "refundStatusDesc": "",
            "cancelStatus": False,
            "realModelCode": item.raw.get("modelCode", "") if item.raw else "",
            "realModelId": None,
            "type": 0,
            "showRemarkInfo": True,
            "check": True,
            "loaded": True,
        }

    def _build_price_diff_no_ship_item(self, item: OrderItem, order: Order) -> dict:
        """
        构建补差价不发货的商品行，使用特殊编码"定制-定制-补差价-不打印"
        """
        material_code = "定制"
        color_code = "定制"
        model_code = "补差价"
        picture_code = "不打印"
        shop_mapping_sku = f"{material_code}-{color_code}-{model_code}-{picture_code}"
        
        return {
            "materialId": None,
            "materialCode": material_code,
            "materialCodeName": None,
            "technology": None,
            "printWayId": None,
            "multiImageUrlExists": None,
            "multiHolePic": None,
            "multiImageExists": None,
            "modelId": None,
            "modelCode": model_code,
            "modelCodeName": None,
            "brand": None,
            "customSize": True,
            "isCompactModel": None,
            "compactFactoryModelCode": None,
            "compactFactoryModelName": None,
            "compactFactoryModelId": None,
            "colorId": None,
            "colorCode": color_code,
            "colorCodeName": None,
            "customPicture": True,
            "pictureId": None,
            "pictureType": None,
            "pictureCode": picture_code,
            "picTypeId": None,
            "pictureCodePath": None,
            "pictureEffectPicPath": None,
            "familyNamePic": None,
            "folderId": None,
            "mustUrlPictureCheckSuccess": False,
            "designerPicCheck": None,
            "sizeMap": None,
            "designPicList": None,
            "effectPicList": None,
            "factorySkuId": None,
            "putSale": None,
            "stockOut": None,
            "combinationGoods": False,
            "factorySkuShopIdS": None,
            "holeSitePic": None,
            "picTechnology": None,
            "map4decodeGift": None,
            "map4FactoryDecodeGift": None,
            "multiplePicList": None,
            "giftBOList": [],
            "giftList": None,
            "giftMaterialList": None,
            "giftCodeName": None,
            "filmGiftCodeId": None,
            "filmGiftCode": "",
            "filmGiftNum": 0,
            "filmGiftPicCode": None,
            "decorationGiftCodeId": None,
            "decorationGiftCode": "",
            "decorationGiftNum": 0,
            "decorationGiftPicCode": None,
            "giftsWithOrder": [],
            "picChange": 0,
            "orderId": item.order_id,
            "originalSkuId": item.original_sku_id,
            "originalGoodsId": item.original_goods_id,
            "id": item.id,
            "sysOid": item.sys_oid,
            "oid": item.oid,
            "title": item.title,
            "merchandisePicPath": item.merchandise_pic_path,
            "workUrl": None,
            "effectUrl": None,
            "productionPicPath": None,
            "num": 1,
            "price": item.price,
            "skuPropertiesName": item.sku_properties_name,
            "outerIid": "",
            "shopMappingSku": shop_mapping_sku,
            "diyList": [{
                "bg": "", "mask": "", "picName": "",
                "isPicMove": 1, "sort": 1,
                "effectUrl": "", "workUrl": "",
                "mobileIdentityNo": None, "picSourceType": 0,
                "layerList": [], "mobileLayerList": None, "lastImgUrl": None,
            }],
            "productType": 0,
            "productSn": None,
            "boxGiftCode": None,
            "shopRemark": order.shop_remark or "",
            "buyerRemark": order.buyer_remark or "",
            "tid": order.tid,
            "originTradeId": order.trade_id,
            "oldSysTid": None,
            "magnifyingSelectPic": False,
            "copySortFlag": 1,
            "logisticsOrderNum": None,
            "logisticsCompanyCode": "ZTO",
            "picType": 0,
            "oldPicWatermarkFlag": 0,
            "maxSendNum": None,
            "isCombinationGoods": False,
            "deriveSysOid": None,
            "inventoryNum": None,
            "picCode": picture_code,
            "lockStatusDesc": "",
            "lockStatus": False,
            "packageQuantity": None,
            "refundStatusDesc": "",
            "cancelStatus": False,
            "realModelCode": model_code,
            "realModelId": None,
            "type": 0,
            "showRemarkInfo": True,
            "check": True,
            "loaded": True,
        }