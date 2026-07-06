"""
方果ERP适配器 - 实现 ErpAdapter 接口
====================================
通过方果的 queryForPageForTrade 和 saveProduct 接口
实现订单查询和商家编码修改。
"""

import re
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core import ErpAdapter, Order, OrderItem, ParsedRemark, parse_remark
from core.parser import extract_multiple_remarks
from .config import (
    API_QUERY_ORDER, API_SAVE_PRODUCT, API_ORDER_DETAIL,
    AUTHORIZATION, COOKIE_STR, TENANT_ID,
    MATERIAL_MAP,
)
from .material_source import get_material_source


class FangguoAdapter(ErpAdapter):
    """方果ERP适配器"""

    def __init__(self):
        self._session = self._create_session()
        self._material_source = get_material_source()
        self.material_map = MATERIAL_MAP

    def get_adapter_name(self) -> str:
        return "方果ERP"

    # -------------------------------------------------------------------
    # Session 管理
    # -------------------------------------------------------------------

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, allowed_methods={"POST"})
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update({
            "accept": "application/json, text/plain, */*",
            "authorization": AUTHORIZATION,
            "content-type": "application/json",
            "cookie": COOKIE_STR,
            "from-client": "0",
            "origin": "https://fangguo.com",
            "referer": "https://fangguo.com/business/order",
            "tenant-id": TENANT_ID,
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
            "tradeIdStr": "",
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
            "factoryLackPicStatus": "",
            "decodeErrorTypeList": [],
            "autoPush": "",
            "inventoryStatus": "",
            "sort": 1,
            "countTimeType": "",
            "countTimeStart": "",
            "countTimeEnd": "",
            "jitSendStatus": "",
            "inquiryModeByProductSn": 1,
            "productSn": "",
            "categoryIdList": [],
            "customIdStr": "",
            "inquiryModeByGiftCode": 0,
            "giftCode": "",
            "combinationGoodsType": None,
            "deductWarehouseName": "",
            "customOrderRemark": "",
            "aeWarehouseIds": [],
            "countryList": [],
            "temuWarehouseIds": [],
            "tkCrossWarehouseIds": [],
            "priceType": "pay_price",
            "minPrice": None,
            "maxPrice": None,
            "firstOrderStatus": [],
            "firstPrintStatus": [],
            "lastSyncStatus": [],
        }
        resp = self._session.post(API_QUERY_ORDER, json=payload, timeout=30)
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
                raw=it,
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
        resp = self._session.post(API_ORDER_DETAIL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        d = data.get("data")
        if isinstance(d, dict):
            return d
        if isinstance(d, list):
            return d[0] if d else {}
        return {}

    # def _enrich_order_with_detail(self, order: Order) -> Order:
    #     """如果订单没有备注/商品行，从详情接口补充"""
    #     if order.shop_remark and order.items:
    #         return order
    #
    #     detail = self.fetch_order_detail(
    #         order_id=order.trade_id or order.id,
    #         sys_tid=order.sys_tid,
    #     )
    #     if not detail:
    #         return order
    #
    #     # 补充卖家备注
    #     shop_remark = self._extract_field(detail, [
    #         "shopRemark", "sellerRemark", "remark",
    #         "备注", "卖家备注", "shop_remark",
    #     ])
    #     if shop_remark:
    #         order.shop_remark = shop_remark
    #
    #     # 补充商品行
    #     items = detail.get("orderItems") or detail.get("items") or []
    #     if items and not order.items:
    #         for it in items:
    #             order.items.append(OrderItem(
    #                 id=str(it.get("id") or ""),
    #                 order_id=str(it.get("orderId") or order.trade_id),
    #                 sys_oid=str(it.get("sysOid") or ""),
    #                 oid=str(it.get("oid") or order.tid),
    #                 title=str(it.get("title") or ""),
    #                 sku_properties_name=str(it.get("skuPropertiesName") or ""),
    #                 shop_mapping_sku=str(it.get("shopMappingSku") or ""),
    #                 original_sku_id=str(it.get("originalSkuId") or ""),
    #                 original_goods_id=str(it.get("originalGoodsId") or ""),
    #                 merchandise_pic_path=str(it.get("merchandisePicPath") or ""),
    #                 num=int(it.get("num") or 1),
    #                 price=float(it.get("price") or 0),
    #                 raw=it,
    #             ))
    #     return order

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
                        raw=it,
                    ))
        return order

    # -------------------------------------------------------------------
    # 3. 修改商家编码
    # -------------------------------------------------------------------
    def update_merchant_code(self, order: Order, parsed: ParsedRemark, parsed_list: list = None) -> bool:
        """
        调用 saveProduct 接口更新商家编码
        支持多尺寸：如果备注中有多个尺寸，会拆分成多个商品行
        """
        if parsed_list and len(parsed_list) > 1:
            effective_list = parsed_list
        else:
            effective_list = self._split_parsed_by_sizes(order, parsed)

        # 构建 orderItems
        order_items = []
        for p in effective_list:
            if order.items:
                # 为每个解析结果创建一个商品行
                for item in order.items:
                    new_item = self._build_order_item(item, order, p)
                    order_items.append(new_item)
            else:
                # 如果没有商品行，创建一个默认的商品行
                new_item = self._build_default_item(order, p)
                order_items.append(new_item)

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

        resp = self._session.post(API_SAVE_PRODUCT, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result.get("e") == 0

    def _split_parsed_by_sizes(self, order: Order, parsed: ParsedRemark) -> list[ParsedRemark]:
        """
        如果备注中包含多个尺寸，拆成多个 ParsedRemark

        例如：
        卖家备注：定制吸水皮革楼梯垫浅灰3,100x4000cm一张，浅灰，100x1000cm一张，共计2张
        →
        [
            ParsedRemark(..., picture='楼梯垫浅灰3;100x4000'),
            ParsedRemark(..., picture='楼梯垫浅灰3;100x1000')
        ]
        """
        remark = order.shop_remark or ""
        if not remark:
            return [parsed]

        # 使用 extract_multiple_remarks 进行多尺寸拆分
        multi_parsed = extract_multiple_remarks(
            remark,
            material_map=self.material_map,
            material_matcher=self.get_material_matcher(),
        )

        if len(multi_parsed) > 1:
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
            "num": item.num,
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
        """没有商品行时的默认构造"""
        return self._build_order_item(
            OrderItem(id=order.trade_id, order_id=order.trade_id,
                      oid=order.tid, num=1),
            order, parsed,
        )

    # -------------------------------------------------------------------
    # 3. 材质列表（可选，增强解析器）
    # -------------------------------------------------------------------

    def get_material_list(self) -> list[dict]:
        return self._material_source.fetch()

    def get_material_matcher(self):
        return self._material_source.matcher_callback

    # -------------------------------------------------------------------
    # 辅助：尝试多种字段名
    # -------------------------------------------------------------------

    @staticmethod
    def _extract_field(data: dict, candidates: list[str]) -> str:
        for key in candidates:
            val = data.get(key)
            if val is None:
                continue
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                for sub_key in ["remark", "text", "value", "content", "备注"]:
                    sub_val = val.get(sub_key)
                    if sub_val and isinstance(sub_val, str) and sub_val.strip():
                        return sub_val.strip()
                for v in val.values():
                    if isinstance(v, str) and v.strip():
                        return v.strip()
        return ""

    @staticmethod
    def _print_keys_sample(orders_raw: list[dict], label: str = "第一个订单"):
        if orders_raw:
            print(f"  🔍 {label} 原始字段: {list(orders_raw[0].keys())}")