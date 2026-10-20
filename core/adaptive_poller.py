import time
from threading import Lock


class AdaptivePoller:
    """
    自适应轮询管理器

    核心策略：
    1. 无订单时：使用基础间隔（如60秒）
    2. 首次发现新订单：等待 new_order_wait 秒（如30秒），让备注完善
    3. 订单就绪后：
       - 若订单数量变化（新增/减少）：重置为 base_interval
       - 若订单数量稳定不变：逐步延长等待时间（指数增长），减轻API压力
    4. API出错时：指数退避
    """

    def __init__(
        self,
        base_interval: float = 60.0,
        min_interval: float = 15.0,
        max_interval: float = 180.0,
        new_order_wait: float = 30.0,
        stable_extend_factor: float = 1.5,
        max_stable_wait: float = 300.0,
    ):
        """
        :param base_interval: 基础轮询间隔（秒）
        :param min_interval: 最小轮询间隔（秒）
        :param max_interval: API出错时的最大间隔（秒）
        :param new_order_wait: 首次发现新订单后的等待时间（秒）
        :param stable_extend_factor: 订单数量稳定时的延长因子（每次乘以该值）
        :param max_stable_wait: 订单稳定时的最大等待时间（秒）
        """
        self.base_interval = base_interval
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.new_order_wait = new_order_wait
        self.stable_extend_factor = stable_extend_factor
        self.max_stable_wait = max_stable_wait

        # 监控线程与审单/推单线程共享状态，完整操作互斥，避免 reset 打断遍历。
        self._lock = Lock()
        self._known_orders: dict[str, dict] = {}
        self._current_interval: float = base_interval
        self._consecutive_errors: int = 0
        self._stable_count: int = 0
        self._prev_order_count: int = 0

    def reset(self):
        """重置所有状态"""
        with self._lock:
            self._known_orders.clear()
            self._current_interval = self.base_interval
            self._consecutive_errors = 0
            self._stable_count = 0
            self._prev_order_count = 0

    def record_poll_result(self, order_ids: set[str]):
        """记录轮询结果"""
        with self._lock:
            now = time.time()
            current_count = len(order_ids)

            # 判断订单数量是否稳定（与上次相同）
            if self._prev_order_count > 0 and current_count == self._prev_order_count:
                self._stable_count += 1
            else:
                self._stable_count = 0

            self._prev_order_count = current_count

            for order_id in order_ids:
                if order_id not in self._known_orders:
                    self._known_orders[order_id] = {
                        'first_seen': now,
                        'last_seen': now,
                        'seen_count': 1,
                        'ready_to_process': False,
                    }
                else:
                    self._known_orders[order_id]['last_seen'] = now
                    self._known_orders[order_id]['seen_count'] += 1

                    if self._known_orders[order_id]['seen_count'] >= 2:
                        wait_elapsed = now - self._known_orders[order_id]['first_seen']
                        if wait_elapsed >= self.new_order_wait:
                            self._known_orders[order_id]['ready_to_process'] = True

            # 清理已消失的订单
            for order_id in list(self._known_orders.keys()):
                if order_id not in order_ids:
                    del self._known_orders[order_id]

            self._consecutive_errors = 0

    def record_error(self):
        """记录API调用错误"""
        with self._lock:
            self._consecutive_errors += 1

    def get_wait_interval(self) -> float:
        """
        获取当前轮询的等待间隔（秒）

        策略优先级：
        1. API连续出错 → 指数退避
        2. 有未就绪的新订单 → new_order_wait
        3. 全部就绪，订单数量稳定 → 逐步延长（指数增长）
        4. 全部就绪，订单数量变化 → base_interval
        5. 无订单 → base_interval
        """
        with self._lock:
            # 1. API 错误退避
            if self._consecutive_errors > 0:
                error_interval = self.base_interval * (2 ** min(self._consecutive_errors, 5))
                return min(error_interval, self.max_interval)

            # 5. 无订单
            if not self._known_orders:
                self._current_interval = self.base_interval
                return self.base_interval

            now = time.time()
            has_new_unready = False

            # 2. 检查是否有未就绪的新订单
            for order_info in self._known_orders.values():
                wait_elapsed = now - order_info['first_seen']
                if order_info['seen_count'] == 1 or wait_elapsed < self.new_order_wait:
                    has_new_unready = True
                    break

            if has_new_unready:
                return self.new_order_wait

            # 到这里说明全部订单都已就绪
            # 3. 订单数量稳定 → 逐步延长等待时间
            if self._stable_count > 0:
                interval = self.base_interval * (self.stable_extend_factor ** self._stable_count)
                interval = min(interval, self.max_stable_wait)
                self._current_interval = interval
                return interval

            # 4. 订单数量变化（刚就绪或订单有增减）→ 使用基础间隔
            self._current_interval = self.base_interval
            return self.base_interval

    def get_order_status_summary(self) -> str:
        """获取订单状态摘要，用于日志输出"""
        with self._lock:
            if not self._known_orders:
                return "无待处理订单"

            now = time.time()
            ready_count = sum(1 for info in self._known_orders.values() if info['ready_to_process'])
            unready_count = len(self._known_orders) - ready_count

            if unready_count > 0:
                oldest_wait = max(
                    now - info['first_seen']
                    for info in self._known_orders.values()
                    if not info['ready_to_process']
                )
                return (
                    f"{len(self._known_orders)}笔待处理订单"
                    f"（{ready_count}笔就绪，{unready_count}笔等待备注完善，最长等待{int(oldest_wait)}秒）"
                )
            else:
                stable_info = f"，连续{self._stable_count}次稳定" if self._stable_count > 0 else ""
                return f"{len(self._known_orders)}笔待处理订单（全部就绪{stable_info}）"

    def should_process_now(self) -> bool:
        """判断是否应该立即处理订单"""
        with self._lock:
            if not self._known_orders:
                return False

            now = time.time()
            for order_info in self._known_orders.values():
                wait_elapsed = now - order_info['first_seen']
                if order_info['seen_count'] >= 2 and wait_elapsed >= self.new_order_wait:
                    return True

            return False

    def get_ready_order_ids(self) -> set[str]:
        """返回当前已就绪（备注等待时间已满足）的订单 ID 集合"""
        with self._lock:
            if not self._known_orders:
                return set()

            now = time.time()
            ready = set()
            for order_id, order_info in self._known_orders.items():
                wait_elapsed = now - order_info['first_seen']
                if order_info['seen_count'] >= 2 and wait_elapsed >= self.new_order_wait:
                    ready.add(order_id)
            return ready

    def get_current_interval(self) -> float:
        """获取当前间隔值"""
        with self._lock:
            return self._current_interval
