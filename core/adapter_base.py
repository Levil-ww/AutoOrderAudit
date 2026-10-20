"""
核心 - ERP适配器抽象接口
所有 ERP 系统需要实现这个接口，才能接入自动审单引擎。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class OrderItem:
    """订单商品行"""
    id: str = ""
    order_id: str = ""
    sys_oid: str = ""
    oid: str = ""
    title: str = ""
    sku_properties_name: str = ""
    shop_mapping_sku: str = ""
    original_sku_id: str = ""
    original_goods_id: str = ""
    merchandise_pic_path: str = ""
    num: int = 1
    price: float = 0
    is_void: bool = False
    raw: dict = field(default_factory=dict)
    shop_remark: str = ""
    original_tid: str = ""
    detail_enriched: bool = True


@dataclass
class Order:
    """订单"""
    id: str = ""
    trade_id: str = ""
    shop_remark: str = ""
    buyer_remark: str = ""
    factory_id: int = 0
    sys_tid: str = ""
    tid: str = ""
    items: list[OrderItem] = field(default_factory=list)
    store_name: str = ""
    raw: dict = field(default_factory=dict)
    receiver_province: str = ""       # 收件人省份
    receiver_address: str = ""        # 收件人完整地址
    current_cp_code: str = ""         # 当前快递编码
    platform_name: str = ""           # 店铺所属平台


class ErpAdapter(ABC):
    """
    ERP 适配器抽象接口。
    每个ERP系统都要实现这个接口。
    """

    @abstractmethod
    def query_orders(
        self,
        page_no: int = 1,
        page_size: int = 500,
        query_status: int = 1,
        time_begin: str = "",
        time_end: str = "",
    ) -> list[Order]:
        """查询待处理的订单列表"""
        ...

    @abstractmethod
    def update_merchant_code(self, order: Order, parsed: "ParsedRemark", *args, **kwargs) -> bool:
        """修改订单中商品的商家编码，返回是否成功"""
        ...

    def get_material_list(self) -> list[dict]:
        """获取系统支持的材质列表（可选）"""
        return []

    def get_adapter_name(self) -> str:
        return self.__class__.__name__

    def query_all_orders(
        self,
        page_size: int = 500,
        query_status: int = 1,
        time_begin: str = "",
        time_end: str = "",
        max_pages: int = 10,
        **kwargs,
    ) -> list[Order]:
        """自动分页查询所有订单（可选实现，默认只查询第一页）

        子类可以覆盖此方法以实现真正的分页查询。
        """
        return self.query_orders(
            page_no=1, page_size=page_size,
            query_status=query_status,
            time_begin=time_begin, time_end=time_end,
        )


    def is_gift_item(self, item: OrderItem) -> bool:
        """可选赠品识别接口。"""
        return False

    def _is_gift_item(self, item: OrderItem) -> bool:
        """兼容原审单引擎的赠品识别入口。"""
        return self.is_gift_item(item)

    def is_price_difference_item(self, item: OrderItem) -> bool:
        return False

    def push_orders(self, trade_id_list: list[str]) -> dict:
        """可选推单接口；未支持的适配器明确返回失败。"""
        return {"code": -1, "msg": "当前适配器不支持推单"}
