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
    raw: dict = field(default_factory=dict)


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
    def update_merchant_code(self, order: Order, parsed: "ParsedRemark") -> bool:
        """修改订单中商品的商家编码，返回是否成功"""
        ...

    def get_material_list(self) -> list[dict]:
        """获取系统支持的材质列表（可选）"""
        return []

    def get_adapter_name(self) -> str:
        return self.__class__.__name__