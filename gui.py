"""
方果ERP自动审单 - 图形界面（美化版）
==================================
为客服人员设计，无需任何技术操作。
特点：简洁卡片布局、日志自动着色、结构化展示。

V2.3.0：沿用原审单业务，补齐赠品配置、店铺快递规则、自适应监控和订单推送。
"""

from __future__ import annotations

import io
import json
import os
import queue
import re
import sys
import time
import threading
import tkinter as tk
from _version import __version__
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth_manager import (
    get_auth_status, load_auth, save_auth, AuthInfo,
    TOKEN_FILE, auto_login, register_auth_callback,
    unregister_auth_callback, is_logged_in,
)
from adapters.fangguo.config import (
    DRY_RUN, MAX_ORDERS, PAGE_SIZE, QUERY_STATUS,
    get_time_range_display,
)
from express_manager import get_manager as get_express_manager
from gift_manager import get_manager as get_gift_manager
from core.adaptive_poller import AdaptivePoller


# ================================================================
#  配色方案（干净、专业的浅色主题）
# ================================================================
COLORS = {
    "bg":          "#f0f2f5",     # 页面背景
    "card_bg":     "#ffffff",     # 卡片背景
    "card_border": "#e4e7ed",     # 卡片边框
    "header_fg":   "#1d1d1f",     # 标题文字
    "label_fg":    "#6b7280",     # 标签文字
    "text_fg":     "#374151",     # 正文文字
    "accent":      "#2563eb",     # 主题蓝
    "accent_light":"#dbeafe",     # 浅蓝背景
    "success":     "#059669",     # 绿色
    "success_bg":  "#d1fae5",     # 浅绿背景
    "warning":     "#d97706",     # 橙色
    "warning_bg":  "#fef3c7",     # 浅橙背景
    "danger":      "#dc2626",     # 红色
    "danger_bg":   "#fee2e2",     # 浅红背景
    "info":        "#2563eb",     # 蓝色
    "info_bg":     "#dbeafe",     # 浅蓝背景
    "header_bg":   "#1e293b",     # 深色标题栏
    "header_bg2":  "#334155",     # 标题栏渐变
    "log_bg":      "#1e1e2e",     # 深色日志背景
    "purple":      "#7c3aed",     # 紫色
}

FONT = "Microsoft YaHei"
FONT_MONO = "Consolas"


def _get_condensed_time_range() -> str:
    """返回精简时间范围，如 '10-06 ~ 10-13'"""
    full = get_time_range_display()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s*~\s*(\d{4})-(\d{2})-(\d{2})", full)
    if m:
        return f"{m.group(2)}-{m.group(3)} ~ {m.group(5)}-{m.group(6)}"
    return full


def _get_condensed_auth_status(auth) -> tuple[str, str]:
    """返回精简登录状态 (文本, 颜色key)"""
    if not auth.authorization:
        return "未登录", "danger"
    if not auth.is_valid:
        return "已过期", "danger"
    days = auth.remaining_days
    if days <= 1:
        return f"即将过期", "warning"
    return "已连接", "success"


def _center_toplevel(widget: tk.Toplevel | tk.Tk, parent: tk.Misc | None,
                     w: int, h: int, on_screen: bool = False):
    """居中显示顶层窗口。on_screen=True 时相对屏幕居中，否则相对 parent 居中。"""
    widget.update_idletasks()
    if on_screen or parent is None:
        sw = widget.winfo_screenwidth()
        sh = widget.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
    else:
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
    widget.geometry(f"{w}x{h}+{x}+{y}")


def _build_treeview(parent: tk.Widget, columns: tuple[str, ...],
                    headings: dict[str, str], widths: dict[str, int],
                    height: int = 10, pack_side: str = tk.LEFT,
                    pack_fill: str = tk.BOTH, pack_expand: bool = True
                    ) -> ttk.Treeview:
    """创建并配置 Treeview，返回实例。headings 和 widths 按列名映射。"""
    tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
    for col in columns:
        tree.heading(col, text=headings.get(col, col))
        tree.column(col, width=widths.get(col, 100), anchor="w")
    tree.pack(side=pack_side, fill=pack_fill, expand=pack_expand)
    return tree


class TextRedirector(io.StringIO):
    """重定向 print → 带颜色标签的文本框"""

    # 匹配行首的emoji标记，用于着色
    _TAG_RULES = [
        (re.compile(r"^.*✅.*$"),    "tag_success"),
        (re.compile(r"^.*❌.*$"),    "tag_danger"),
        (re.compile(r"^.*⏭️.*$"),   "tag_warning"),
        (re.compile(r"^.*⚠️.*$"),   "tag_warning"),
        (re.compile(r"^.*❓.*$"),    "tag_warning"),
        (re.compile(r"^.*🔶.*$"),   "tag_warning"),
        (re.compile(r"^.*📊.*$"),   "tag_info"),
        (re.compile(r"^.*🚀.*$"),   "tag_info"),
        (re.compile(r"^.*📦.*$"),   "tag_info"),
        (re.compile(r"^.*📋.*$"),   "tag_info"),
        (re.compile(r"^.*🔐.*$"),   "tag_info"),
        (re.compile(r"^.*📅.*$"),   "tag_info"),
        (re.compile(r"^.*⚙️.*$"),  "tag_info"),
        (re.compile(r"^.*👁.*$"),   "tag_info"),
        (re.compile(r"^.*🔄.*$"),   "tag_info"),
        (re.compile(r"^.*💤.*$"),   "tag_info"),
        (re.compile(r"^.*🔍.*$"),   "tag_info"),
        (re.compile(r"^.*⏹.*$"),   "tag_warning"),
        (re.compile(r"^.*💬.*$"),   "tag_info"),
        (re.compile(r"^=+$"),       "tag_separator"),
        (re.compile(r"^─+$"),       "tag_separator"),
        (re.compile(r"^\[.*\].*$"), "tag_order"),
        (re.compile(r"^\s+│.*$"),   "tag_detail"),
    ]

    def __init__(self, text_widget, log_queue=None):
        super().__init__()
        self.text_widget = text_widget
        # 线程安全的日志队列：若提供则优先投递到队列，由主线程消费
        self._log_queue = log_queue

    def write(self, string):
        if not string:
            return
        # 检测颜色
        tag = None
        for pattern, t in self._TAG_RULES:
            if pattern.match(string):
                tag = t
                break

        # 如果提供了线程安全队列（子线程场景），投递后由主线程消费
        if self._log_queue is not None:
            self._log_queue.put((string, tag))
            return

        # 主线程场景：直接操作 widget
        self.text_widget.insert(tk.END, string, tag)
        self.text_widget.see(tk.END)

    def flush(self):
        pass


# ── 从 gui_dialogs 导入提取的对话框和组件 ─────────────────────
from gui_dialogs import LoginDialog, ExpressConfigDialog, GiftConfigDialog, _RoundedButton


class AutoAuditGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"方果ERP · 自动审单工具 V{__version__}")
        self.root.geometry("1050x720")
        self.root.resizable(True, True)
        self.root.configure(bg=COLORS["bg"])
        self._running = False
        # 批量确认决策缓存：None=未决定，True=全部确定，False=全部取消
        self._batch_confirm_decision = None

        # 自动监控模式
        self._monitor_skip_cache = {}
        self._monitoring = False          # 是否正在监控
        self._monitor_paused = False      # 监控是否暂停
        self._monitor_thread = None       # 监控线程引用
        self._monitor_poll_interval = 60  # 基础轮询间隔（秒）
        self._monitor_audit_count = 0     # 监控期间累计审单轮次
        self._monitor_push_count = 0      # 监控期间累计推单轮次（仅推单，无审单）

        # 运行时间计时器
        self._running_start_time = None   # 当前计时段的单调时钟起点
        self._running_timer_job = None    # after 定时器 job ID
        self._running_elapsed = 0.0       # 累计已运行秒数（暂停时保留小数）
        self._adaptive_poller = AdaptivePoller(
            base_interval=60.0,
            min_interval=15.0,
            max_interval=180.0,
            new_order_wait=30.0,
            stable_extend_factor=1.5,
            max_stable_wait=300.0,
        )


        # 线程安全的日志队列：子线程的 print 通过 TextRedirector 投递到此处，
        # 主线程通过 after 定时消费，避免跨线程操作 Tkinter widget。
        self._log_queue = queue.Queue()
        # 鉴权通知独立排队，避免清空日志时丢失状态刷新。
        self._auth_queue = queue.Queue()
        self._log_drain_job = None

        self._center_window()
        self._build_layout()
        self._refresh_status()

        # 启动日志队列消费定时器
        self._start_log_drain()

        # 注册鉴权变化回调
        register_auth_callback(self._on_auth_changed)

        # Token 过期自动检测
        self._token_check_job = None  # 定时检查的 after job ID
        self._token_check_interval = 60 * 1000  # 检查间隔（毫秒），默认1分钟

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动时检查是否有Token，没有则提示登录
        self.root.after(500, self._check_login_on_startup)
        # 启动Token过期自动检测
        self.root.after(1000, self._start_token_check)

    # ------------------------------------------------------------
    #  窗口
    # ------------------------------------------------------------
    def _center_window(self):
        _center_toplevel(self.root, None, 1050, 720, on_screen=True)

    # ------------------------------------------------------------
    #  日志文本颜色配置
    # ------------------------------------------------------------
    def _configure_tags(self):
        self._setup_text_tags(self.log_text)

    # ------------------------------------------------------------
    #  日志队列消费（主线程定时刷新）
    # ------------------------------------------------------------
    def _start_log_drain(self):
        """启动主线程定时消费日志队列。"""
        self._drain_log_queue()

    def _drain_log_queue(self):
        """主线程消费鉴权通知并把日志写入文本框，共用原有定时器。"""
        try:
            while True:
                self._auth_queue.get_nowait()
                try:
                    self._refresh_status()
                except tk.TclError:
                    return
                except Exception as e:
                    print(f"⚠️ 登录状态刷新异常: {e}")
        except queue.Empty:
            pass
        try:
            while True:
                string, tag = self._log_queue.get_nowait()
                try:
                    self.log_text.insert(tk.END, string, tag)
                    self.log_text.see(tk.END)
                except tk.TclError:
                    # widget 已销毁
                    return
        except queue.Empty:
            pass
        # 100ms 后再次刷新
        try:
            self._log_drain_job = self.root.after(100, self._drain_log_queue)
        except tk.TclError:
            pass

    def _setup_text_tags(self, text):
        text.tag_config("tag_success", foreground="#34d399")
        text.tag_config("tag_danger",  foreground="#f87171")
        text.tag_config("tag_warning", foreground="#fbbf24")
        text.tag_config("tag_info",    foreground="#60a5fa")
        text.tag_config("tag_separator", foreground="#6b7280", font=(FONT_MONO, 8))
        text.tag_config("tag_order",   foreground="#f1f5f9", font=(FONT, 10, "bold"))
        text.tag_config("tag_detail",  foreground="#94a3b8")

    # ------------------------------------------------------------
    #  布局
    # ------------------------------------------------------------
    def _build_layout(self):
        # 整体容器，带内边距
        container = tk.Frame(self.root, bg=COLORS["bg"])
        container.pack(fill=tk.BOTH, expand=True, padx=24, pady=(18, 18))

        # 各部分
        self._build_header(container)
        self._build_status_cards(container)
        self._build_log_section(container)
        self._build_footer(container)

    # ------------------------------------------------------------
    #  顶部标题
    # ------------------------------------------------------------
    def _build_header(self, parent):
        header = tk.Frame(parent, bg=COLORS["header_bg"], height=52)
        header.pack(fill=tk.X, pady=(0, 16))
        header.pack_propagate(False)

        title = tk.Label(
            header, text="方果ERP · 自动审单工具",
            font=(FONT, 18, "bold"), bg=COLORS["header_bg"],
            fg="#ffffff",
        )
        title.pack(side=tk.LEFT, padx=18)

        badge_frame = tk.Frame(header, bg=COLORS["header_bg"])
        badge_frame.pack(side=tk.RIGHT, padx=14)

        self.auth_btn = _RoundedButton(
            badge_frame, "登 录", COLORS["header_bg2"], "#ffffff",
            self._on_auth_button_click, 10, radius=6, padx=14, pady=4,
        )

        self._make_badge(badge_frame, f"V{__version__}", COLORS["accent"], "#ffffff").pack(side=tk.RIGHT)

    def _make_badge(self, parent, text, bg, fg):
        return tk.Label(
            parent, text=text, font=(FONT, 9),
            bg=bg, fg=fg, padx=10, pady=2,
        )

    # ------------------------------------------------------------
    #  状态卡片
    # ------------------------------------------------------------
    def _build_status_cards(self, parent):
        frame = tk.Frame(parent, bg=COLORS["bg"])
        frame.pack(fill=tk.X, pady=(0, 14))

        # 三张卡片并排
        self._card_token = self._make_status_card(
            frame, "登录状态", "未登录", 0
        )
        self._card_time = self._make_status_card(
            frame, "审单范围", _get_condensed_time_range(), 1
        )
        self._card_mode = self._make_status_card(
            frame, "运行模式",
            "仅模拟（不真实提交）" if DRY_RUN else "正式模式（会实际修改）",
            2
        )

    def _make_status_card(self, parent, title, value, col):
        card = tk.Frame(
            parent, bg=COLORS["card_bg"],
            highlightbackground=COLORS["card_border"],
            highlightthickness=1, padx=16, pady=14,
        )
        card.grid(row=0, column=col, sticky="ew", padx=(0, 10))
        parent.grid_columnconfigure(col, weight=1)

        inner = tk.Frame(card, bg=COLORS["card_bg"])
        inner.pack(fill=tk.X)

        icon_colors = {0: COLORS["accent"], 1: COLORS["purple"], 2: "#0d9488"}
        icon_bg = {0: COLORS["accent_light"], 1: "#ede9fe", 2: "#ccfbf1"}
        icons = {0: "\u2714", 1: "\U0001f4c5", 2: "\u2699"}
        ic = icon_colors[col]
        ib = icon_bg[col]

        icon_label = tk.Label(
            inner, text=icons[col], font=(FONT, 14),
            bg=ib, fg=ic, padx=8, pady=6,
        )
        icon_label.pack(side=tk.LEFT, padx=(0, 12))

        text_frame = tk.Frame(inner, bg=COLORS["card_bg"])
        text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            text_frame, text=title, font=(FONT, 9),
            bg=COLORS["card_bg"], fg=COLORS["label_fg"],
        ).pack(anchor="w")

        value_label = tk.Label(
            text_frame, text=value, font=(FONT, 12, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
            anchor="w", wraplength=220,
        )
        value_label.pack(anchor="w", pady=(2, 0))

        return value_label

    # ------------------------------------------------------------
    #  日志区域
    # ------------------------------------------------------------
    def _build_log_section(self, parent):
        log_outer = tk.Frame(parent, bg=COLORS["bg"])
        log_outer.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        # 标题行
        title_row = tk.Frame(log_outer, bg=COLORS["bg"])
        title_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            title_row, text="运行日志", font=(FONT, 12, "bold"),
            bg=COLORS["bg"], fg=COLORS["header_fg"],
        ).pack(side=tk.LEFT)

        # 运行时间标签（右侧）
        self.running_time_label = tk.Label(
            title_row, text="",
            font=(FONT, 10), bg=COLORS["bg"], fg=COLORS["label_fg"],
        )
        self.running_time_label.pack(side=tk.RIGHT, padx=(0, 4))

        # 统计信息
        self.stat_label = tk.Label(
            title_row, text="",
            font=(FONT, 9), bg=COLORS["bg"], fg=COLORS["label_fg"],
        )
        self.stat_label.pack(side=tk.RIGHT)

        # 日志卡片（深色背景）
        log_card = tk.Frame(
            log_outer, bg=COLORS["log_bg"],
            highlightbackground="#374151",
            highlightthickness=1,
        )
        log_card.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_card,
            wrap=tk.WORD,
            font=(FONT_MONO, 10),
            bg=COLORS["log_bg"],
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            relief=tk.FLAT,
            borderwidth=0,
            padx=14, pady=10,
            height=18,
            highlightthickness=0,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self._setup_text_tags(self.log_text)

        # 重定向 print：传入日志队列，子线程的 print 通过队列由主线程消费
        self.text_redirector = TextRedirector(self.log_text, self._log_queue)
        sys.stdout = self.text_redirector

        # 初始信息
        print(f"🟢 自动审单工具已启动 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("📌 点击下方「登录」按钮，输入手机号密码即可开始使用")
        print("📌 点击「开始审单」手动处理一批待整理订单")
        print("📌 点击「自动监控」开启全自动模式，无需手动操作\n")

    # ------------------------------------------------------------
    #  底部按钮
    # ------------------------------------------------------------
    def _build_footer(self, parent):
        footer = tk.Frame(parent, bg=COLORS["bg"])
        footer.pack(fill=tk.X)

        # 左侧按钮组
        btn_group = tk.Frame(footer, bg=COLORS["bg"])
        btn_group.pack(side=tk.LEFT)

        # 主要操作：实心按钮
        self.start_btn = self._make_button(
            btn_group, "开始审单", COLORS["success"], "#ffffff",
            self._start_audit, 11,
        )

        self.push_btn = self._make_button(
            btn_group, "开始推单", COLORS["info"], "#ffffff",
            self._start_push, 11,
        )

        self.monitor_btn = self._make_button(
            btn_group, "自动监控", COLORS["purple"], "#ffffff",
            self._toggle_monitor, 11,
        )

        # 次要操作：描边按钮
        self._make_outlined_button(
            btn_group, "刷新", COLORS["accent"], COLORS["accent_light"],
            self._refresh_status, 10,
        )
        self._make_outlined_button(
            btn_group, "清空日志", "#6b7280", "#f3f4f6",
            self._clear_log, 10,
        )
        self._make_outlined_button(
            btn_group, "快递配置", COLORS["warning"], COLORS["warning_bg"],
            self._open_express_config, 10,
        )
        self._make_outlined_button(
            btn_group, "赠品配置", COLORS["success"], COLORS["success_bg"],
            self._open_gift_config, 10,
        )

        # 右侧进度条
        right = tk.Frame(footer, bg=COLORS["bg"])
        right.pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(right, mode="indeterminate", length=160)
        self.progress.pack(side=tk.RIGHT)

    def _make_button(self, parent, text, bg, fg, cmd, font_size):
        """实心圆角按钮"""
        return _RoundedButton(parent, text, bg, fg, cmd, font_size, radius=8)

    def _make_outlined_button(self, parent, text, color, bg_color, cmd, font_size):
        """描边圆角按钮"""
        return _RoundedButton(parent, text, color, bg_color, cmd, font_size,
                              radius=6, outline=color, outline_width=1)

    # ------------------------------------------------------------
    #  登录相关
    # ------------------------------------------------------------
    def _check_login_on_startup(self):
        """启动时检查登录状态"""
        auth = load_auth()
        if not auth.authorization:
            print("检测到未登录，请点击右上角「登录」按钮输入账号密码")
        elif not auth.is_valid:
            print(f"Token已过期（{auth.expires_at}），请重新登录")
        else:
            print(f"Token有效（{auth.username or ''}，剩余{auth.remaining_days}天）")

    def _open_login(self):
        """打开登录对话框"""
        LoginDialog(self.root, on_success=self._on_login_success)

    def _on_login_success(self, auth: AuthInfo):
        """登录成功后回调"""
        # 刷新状态卡片
        self._refresh_status()
        # 日志
        print(f"✅ 登录成功！欢迎 {auth.username or ''}")
        print(f"🔐 Token有效期至 {auth.expires_at}（剩余{auth.remaining_days}天）")
        print("💡 现在可以开始审单了")
        # 启用开始按钮
        if not self._running:
            self.start_btn.config(state=tk.NORMAL, bg=COLORS["success"])

    def _on_auth_changed(self, auth: AuthInfo):
        """接收鉴权变化通知；后台线程只入队，不调用任何 Tk 方法。"""
        self._auth_queue.put(auth)

    # ------------------------------------------------------------
    #  Token 过期自动检测
    # ------------------------------------------------------------
    def _start_token_check(self):
        """启动Token过期定时检测"""
        self._check_token_expiry()

    def _check_token_expiry(self):
        """
        检查Token是否过期。
        如果已过期且当前处于登录状态，则自动退出登录并提示重新登录。
        """
        try:
            auth = load_auth()
            # 如果有Token但已过期，执行自动退出
            if auth.authorization and not auth.is_valid:
                was_monitoring = self._monitoring
                was_running = self._running

                # 自动退出登录
                self._logout(auto=True)

                # 如果正在监控，停止监控
                if was_monitoring:
                    self._stop_monitor()

                # 审单线程是同步阻塞的（engine.run 内部循环），无法直接中断。
                # 若正在审单，提示用户等待当前轮次结束后再操作。
                if was_running:
                    print("⚠️ 检测到审单线程仍在运行，当前轮次完成后将自动停止")
                    print("⚠️ 由于 Token 已失效，后续 API 调用可能失败，请稍后重新登录")
                    # 禁用开始按钮，避免用户在 Token 失效期间再次发起审单
                    try:
                        self.start_btn.config(state=tk.DISABLED, text="Token已过期", bg="#9ca3af")
                    except tk.TclError:
                        pass

                # 弹出提示并自动打开登录对话框
                print("\n⚠️ " + "=" * 50)
                print("⚠️ Token已过期，已自动退出登录")
                print("⚠️ 请重新登录以继续使用")
                print("⚠️ " + "=" * 50 + "\n")

                # 弹出确认框，询问是否立即重新登录
                ret = messagebox.askyesno(
                    "Token已过期",
                    f"⚠️ Token已过期（{auth.expires_at}），\n是否立即重新登录？"
                )
                if ret:
                    self._open_login()
        except Exception as e:
            print(f"⚠️ Token检查异常: {e}")
        finally:
            # 安排下一次检查
            self._token_check_job = self.root.after(
                self._token_check_interval, self._check_token_expiry
            )

    def _stop_token_check(self):
        """停止Token过期检测"""
        if self._token_check_job is not None:
            try:
                self.root.after_cancel(self._token_check_job)
            except Exception:
                pass
            self._token_check_job = None

    def _on_auth_button_click(self):
        """登录/退出登录按钮点击处理（根据当前状态动态切换）"""
        auth = load_auth()
        if auth.authorization and auth.is_valid:
            # 已登录且有效 → 执行退出登录
            self._logout()
        else:
            # 未登录或已过期 → 打开登录对话框
            self._open_login()

    def _update_auth_button(self):
        """根据登录状态更新按钮文本和颜色"""
        auth = load_auth()
        if auth.authorization and auth.is_valid:
            self.auth_btn.config(text="退出登录", bg=COLORS["danger"])
        else:
            self.auth_btn.config(text="登 录", bg=COLORS["header_bg2"])

    def _logout(self, auto=False):
        """
        退出登录，清除Token
        Args:
            auto: 是否为自动退出（Token过期触发），自动退出不弹确认框
        """
        if not load_auth().authorization:
            return

        if not auto:
            if not messagebox.askyesno("确认退出", "确定要退出登录吗？退出后需重新登录才能使用。"):
                return

        from auth_manager import reset_auth
        reset_auth()
        from adapters.fangguo.config import reload_auth
        reload_auth()
        self._refresh_status()

        if auto:
            print("⚠️ Token已过期，已自动退出登录")
            print("🔐 请重新登录以继续使用")
        else:
            print("🔐 已退出登录")
            print("📌 下次使用时点击「登录」按钮重新登录")

    # ------------------------------------------------------------
    #  操作
    # ------------------------------------------------------------
    def _refresh_status(self):
        auth = load_auth()
        status_text, color_key = _get_condensed_auth_status(auth)
        self._card_token.config(text=status_text, fg=COLORS[color_key])

        # 更新登录/退出登录按钮状态
        self._update_auth_button()

        self._card_time.config(text=_get_condensed_time_range())

        # 刷新运行模式卡片（DRY_RUN 为常量，但保持刷新一致性）
        try:
            self._card_mode.config(
                text="仅模拟（不真实提交）" if DRY_RUN else "正式模式（会实际修改）"
            )
        except tk.TclError:
            pass

    def _open_token_file(self):
        # 复用 auth_manager.TOKEN_FILE：打包后 __file__ 指向 _MEIxxxxx 临时目录，
        # 而 token.json 实际写在 exe 同级目录（_get_app_dir）。
        from auth_manager import TOKEN_FILE
        path = TOKEN_FILE
        if os.path.exists(path):
            try:
                if sys.platform == "win32":
                    os.startfile(path)
                else:
                    import subprocess
                    subprocess.run(["xdg-open", path], check=False)
            except Exception as e:
                print(f"⚠️ 无法打开Token文件: {e}")
        else:
            messagebox.showerror("文件不存在", "token.json 不存在，请联系技术人员。")

    def _clear_log(self):
        # 先清空队列中尚未消费的日志，避免清屏后旧日志又被刷新出来
        try:
            while True:
                self._log_queue.get_nowait()
        except queue.Empty:
            pass
        self.log_text.delete(1.0, tk.END)

    def _open_express_config(self):
        """打开快递配置对话框"""
        ExpressConfigDialog(self.root)

    def _open_gift_config(self):
        """打开赠品配置对话框"""
        GiftConfigDialog(self.root)

    def _update_stat(self, text):
        self.stat_label.config(text=text)

    # ------------------------------------------------------------
    #  运行时间计时器
    # ------------------------------------------------------------
    @staticmethod
    def _format_elapsed(seconds: int) -> str:
        """将秒数格式化为 MM:SS"""
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    def _start_running_timer(self, reset: bool = True) -> None:
        """新任务从零计时；监控会话内继续累计，避免重复注册刷新。"""
        if reset:
            self._stop_running_timer()
            self._running_elapsed = 0.0
        elif self._running_start_time is not None:
            return
        self._running_start_time = time.monotonic()
        self._update_running_time()

    def _stop_running_timer(self) -> None:
        """冻结计时并保留最终显示，重复调用不重复累计。"""
        if self._running_timer_job is not None:
            try:
                self.root.after_cancel(self._running_timer_job)
            except tk.TclError:
                pass
            self._running_timer_job = None
        if self._running_start_time is not None:
            self._running_elapsed += time.monotonic() - self._running_start_time
        self._running_start_time = None
        self.running_time_label.config(
            text=f"已运行 {self._format_elapsed(int(self._running_elapsed))}"
        )

    def _sync_running_timer(self) -> None:
        """只同步计时显示，不改变任务或监控状态。"""
        if self._running or (self._monitoring and not self._monitor_paused):
            self._start_running_timer(reset=False)
        else:
            self._stop_running_timer()

    def _update_running_time(self) -> None:
        """刷新运行时间显示，并安排下一次更新"""
        if self._running_start_time is None:
            return
        elapsed = int(time.monotonic() - self._running_start_time + self._running_elapsed)
        self.running_time_label.config(text=f"已运行 {self._format_elapsed(elapsed)}")
        self._running_timer_job = self.root.after(1000, self._update_running_time)

    # ------------------------------------------------------------
    #  🔥 确认弹窗（线程安全）
    # ------------------------------------------------------------
    def _confirm_update(self, order, parsed_list, changes):
        """
        由引擎线程调用，通过 root.after() 在主线程弹窗。
        第一次弹出时询问用户，之后自动沿用相同选择（批量操作）。
        """
        # 如果已经有批量决策，直接返回缓存值
        if self._batch_confirm_decision is not None:
            return self._batch_confirm_decision

        order_id = getattr(order, 'trade_id', '') or getattr(order, 'id', '')
        change_text = "\n".join(f"  • {c}" for c in changes)

        msg = (
            f"订单 {order_id} 备注解析成功，可生成新编码：\n"
            f"{change_text}\n\n"
            f"是否一键自动审单？\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"「确定」→ 自动更新所有可处理订单\n"
            f"「取消」→ 仅日志记录，不修改"
        )

        result = [None]
        event = threading.Event()

        def _show():
            result[0] = messagebox.askyesno("是否一键自动审单", msg)
            event.set()

        # 调度到主线程显示
        self.root.after(0, _show)
        # 设置超时避免审计线程永久阻塞（5分钟）
        event.wait(timeout=300)
        if result[0] is None:
            result[0] = False
            print("⚠️ 确认弹窗超时，默认取消修改")

        # 缓存本次批量决策，后续订单自动沿用
        self._batch_confirm_decision = result[0]
        return result[0]

    # ------------------------------------------------------------
    #  开始审单
    # ------------------------------------------------------------
    def _start_audit(self):
        if self._running:
            messagebox.showinfo("提示", "正在审单中，请等待完成...")
            return

        auth = load_auth()
        if not auth.authorization:
            messagebox.showerror("未登录", "❌ 请先点击「登录」按钮输入账号密码！")
            return
        if not auth.is_valid:
            ret = messagebox.askyesno(
                "Token已过期",
                f"⚠️ Token已过期（{auth.expires_at}），是否重新登录？"
            )
            if ret:
                self._open_login()
            return

        self._running = True
        self._batch_confirm_decision = None  # 重置批量确认决策
        self.start_btn.config(state=tk.DISABLED, text="审单中...", bg="#9ca3af")
        self.progress.start()
        self._start_running_timer(reset=not self._monitoring)

        print("\n" + "━" * 60)
        print(f"🚀 开始自动审单 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 时间范围: {get_time_range_display()}")
        print(f"👤 当前用户: {auth.username or 'Unknown'}")
        print("━" * 60 + "\n")

        threading.Thread(target=self._run_audit, daemon=True).start()

    def _finish_audit(self):
        self._running = False
        self._batch_confirm_decision = None  # 清理批量决策缓存
        self._sync_running_timer()
        # 根据监控状态恢复按钮
        if self._monitoring:
            self.start_btn.config(state=tk.DISABLED, text="监控中...", bg="#9ca3af")
        else:
            self.start_btn.config(state=tk.NORMAL, text="开始审单", bg=COLORS["success"])
        self.progress.stop()
        print("\n" + "━" * 60)
        print("✅ 自动审单完成")
        print("━" * 60)

    # ------------------------------------------------------------
    #  开始推单
    # ------------------------------------------------------------
    def _start_push(self):
        if self._running:
            messagebox.showinfo("提示", "正在审单中，请等待完成...")
            return

        auth = load_auth()
        if not auth.authorization:
            messagebox.showerror("未登录", "❌ 请先点击「登录」按钮输入账号密码！")
            return
        if not auth.is_valid:
            ret = messagebox.askyesno(
                "Token已过期",
                f"⚠️ Token已过期（{auth.expires_at}），是否重新登录？"
            )
            if ret:
                self._open_login()
            return

        self._running = True
        self.push_btn.config(state=tk.DISABLED, text="推单中...", bg="#9ca3af")
        self.progress.start()
        self._start_running_timer(reset=not self._monitoring)

        print("\n" + "━" * 60)
        print(f"🚀 开始自动推单 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 时间范围：{get_time_range_display()}")
        print(f"👤 当前用户：{auth.username or 'Unknown'}")
        print("━" * 60 + "\n")

        threading.Thread(target=self._run_push, daemon=True).start()

    def _run_push(self):
        try:
            from adapters.fangguo.adapter import FangguoAdapter
            from core.engine import AutoAuditEngine
            from adapters.fangguo.config import (
                PAGE_SIZE, DRY_RUN, MAX_ORDERS,
                get_time_begin, get_time_end,
            )

            adapter = FangguoAdapter()
            engine = AutoAuditEngine(
                adapter=adapter,
                dry_run=DRY_RUN,
                max_orders=MAX_ORDERS,
            )

            engine.push_eligible_orders(
                page_no=1, page_size=PAGE_SIZE,
                time_begin=get_time_begin(), time_end=get_time_end(),
            )
        except Exception as e:
            print(f"❌ 推单异常：{e}")
        finally:
            self.root.after(0, self._finish_push)

    def _finish_push(self):
        self._running = False
        self._sync_running_timer()
        self.push_btn.config(state=tk.NORMAL, text="开始推单", bg=COLORS["info"])
        self.progress.stop()
        print("\n" + "━" * 60)
        print("✅ 自动推单完成")
        print("━" * 60)

    # ------------------------------------------------------------
    #  自动监控模式
    # ------------------------------------------------------------
    def _toggle_monitor(self):
        """三态循环切换：未监控 → 运行中 → 已暂停 → 未监控"""
        if not self._monitoring:
            self._start_monitor()
        elif self._monitor_paused:
            # 已暂停状态点击 = 彻底停止监控（回到未监控）
            self._stop_monitor()
        else:
            # 运行中状态点击 = 暂停监控
            self._pause_monitor()

    def _set_monitor_btn_state(self, state):
        """根据状态刷新 monitor_btn 的显示"""
        # state: "idle" / "running" / "paused"
        cfg = {
            "idle":    ("自动监控", "#7c3aed"),
            "running": ("暂停监控", COLORS["warning"]),
            "paused":  ("停止监控", COLORS["danger"]),
        }[state]
        text, bg = cfg
        self.monitor_btn.config(state=tk.NORMAL, text=text, bg=bg)

    def _pause_monitor(self):
        """暂停监控（不停止线程，只是暂停轮询）"""
        if not self._monitoring or self._monitor_paused:
            return
        # 如果正在审单中，不允许暂停
        if self._running:
            messagebox.showinfo("提示", "正在审单中，审单完成后才能暂停...")
            return

        self._monitor_paused = True
        self._sync_running_timer()
        # 暂停时 monitor_btn 显示"停止监控"，点击即彻底停止
        self._set_monitor_btn_state("paused")

        print(f"\n⏸ 监控已暂停 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 暂停前已执行审单 {self._monitor_audit_count} 轮")
        print("💡 再次点击「停止监控」可彻底结束监控\n")

    def _resume_monitor(self):
        """继续监控"""
        if not self._monitoring or not self._monitor_paused:
            return

        self._monitor_paused = False
        # 恢复运行：monitor_btn 回到"暂停监控"状态
        self._sync_running_timer()
        self._set_monitor_btn_state("running")

        print(f"\n▶ 监控已恢复 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("🔄 继续自动检测待处理订单...\n")

    def _start_monitor(self):
        """开启自动监控模式"""
        monitor_thread = getattr(self, "_monitor_thread", None)
        if monitor_thread is not None and monitor_thread.is_alive():
            messagebox.showinfo("提示", "上一轮监控正在退出，请稍后再试。")
            return
        if self._running:
            messagebox.showinfo("提示", "正在审单中，请等待完成后再开启监控...")
            return

        auth = load_auth()
        if not auth.authorization:
            messagebox.showerror("未登录", "请先点击「登录」按钮输入账号密码！")
            return
        if not auth.is_valid:
            ret = messagebox.askyesno(
                "Token已过期",
                f"Token已过期（{auth.expires_at}），是否重新登录？"
            )
            if ret:
                self._open_login()
            return

        if not messagebox.askyesno(
            "开启自动监控",
            "开启后将自动检测待处理订单并执行审单，\n"
            "审单过程无需手动确认，全自动处理。\n\n"
            "自适应轮询策略：\n"
            f"  • 基础间隔: {self._monitor_poll_interval}秒\n"
            f"  • 新订单等待: {int(self._adaptive_poller.new_order_wait)}秒（备注完善）\n"
            f"  • 最短间隔: {int(self._adaptive_poller.min_interval)}秒\n\n"
            "是否开启自动监控？"
        ):
            return

        self._monitoring = True
        self._monitor_paused = False
        self._monitor_audit_count = 0
        self._monitor_push_count = 0
        self._monitor_skip_cache = {}

        # 更新按钮状态
        # monitor_btn 三态：未监控 → 运行中 → 已暂停 → 未监控
        self._set_monitor_btn_state("running")
        self.start_btn.config(state=tk.DISABLED, text="监控中...", bg="#9ca3af")
        self.progress.start()
        self._start_running_timer()

        print("\n" + "━" * 60)
        print(f"👁 自动监控模式已开启 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔄 自适应轮询策略: 基础{self._monitor_poll_interval}秒 / 新订单等待{int(self._adaptive_poller.new_order_wait)}秒 / 最短{int(self._adaptive_poller.min_interval)}秒")
        print(f"👤 当前用户: {auth.username or 'Unknown'}")
        print(f"📅 时间范围: {get_time_range_display()}")
        print("💬 监控模式下审单无需确认，全自动处理")
        print("━" * 60 + "\n")

        # 启动监控线程
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _stop_monitor(self):
        """停止自动监控"""
        self._monitoring = False
        self._monitor_paused = False
        # 不在主线程中 join，避免 GUI 冻结
        # 监控线程会通过 should_stop 回调检测 _monitoring 标志并自行退出
        # 保留线程引用，上一轮查询退出前禁止再次启动监控。

        # monitor_btn 回到未监控态
        self._set_monitor_btn_state("idle")
        self._sync_running_timer()
        if not self._running:
            self.start_btn.config(state=tk.NORMAL, text="开始审单", bg=COLORS["success"])
        self.progress.stop()

        print("\n" + "━" * 60)
        print(f"⏹ 自动监控已停止 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 监控期间共执行审单 {self._monitor_audit_count} 轮")
        print("━" * 60 + "\n")

    def _monitor_loop(self):
        """监控主循环：自适应轮询待处理订单，智能判断处理时机"""
        self._adaptive_poller.reset()
        
        while self._monitoring:
            while self._monitor_paused and self._monitoring:
                time.sleep(1)

            if not self._monitoring:
                break

            try:
                auth = load_auth()
                if not auth.is_valid:
                    print("⚠️ Token已过期，自动监控暂停，请重新登录")
                    self.root.after(0, self._stop_monitor)
                    return

                from adapters.fangguo import FangguoAdapter
                from adapters.fangguo.config import (
                    QUERY_STATUS, QUERY_STATUS_PENDING_PUSH, PAGE_SIZE,
                    get_time_begin, get_time_end,
                )

                adapter = FangguoAdapter()
                # 待整理订单分页获取，确保每单都参与备注等待计时，避免只处理前10单。
                pending_audit_orders = adapter.query_all_orders(
                    page_size=PAGE_SIZE,
                    query_status=QUERY_STATUS,
                    time_begin=get_time_begin(), time_end=get_time_end(),
                )
                # 待推送仅探测是否存在，实际推单时再分页获取完整列表。
                pending_push_orders = adapter.query_orders(
                    page_no=1, page_size=10,
                    query_status=QUERY_STATUS_PENDING_PUSH,
                    time_begin=get_time_begin(), time_end=get_time_end(),
                )

                # 待整理订单用于自适应轮询器
                order_ids = {order.tid or order.trade_id for order in pending_audit_orders}
                self._adaptive_poller.record_poll_result(order_ids)

                status_summary = self._adaptive_poller.get_order_status_summary()
                # 扩展状态摘要，包含待推送订单数
                if pending_push_orders:
                    status_summary = f"{status_summary}，待推送 {len(pending_push_orders)} 个"
                wait_interval = self._adaptive_poller.get_wait_interval()

                has_audit_orders = bool(pending_audit_orders)
                has_push_orders = bool(pending_push_orders)

                if has_audit_orders or has_push_orders:
                    if self._adaptive_poller.should_process_now() or (has_push_orders and not has_audit_orders):
                        if self._running:
                            print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] 上一轮处理仍在进行中，跳过本轮")
                        else:
                            if has_audit_orders:
                                # 有待整理订单：启动审单+推单线程
                                order_count = len(pending_audit_orders)
                                ready_ids = self._adaptive_poller.get_ready_order_ids()
                                print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] {status_summary}，开始自动审单...")
                                self._monitor_audit_count += 1

                                self._running = True
                                self._batch_confirm_decision = None
                                self.root.after(0, lambda: self.start_btn.config(
                                    state=tk.DISABLED, text="审单中...", bg="#9ca3af"
                                ))
                                # 子线程执行审单，不阻塞监控循环，停止信号可在订单边界即时生效
                                audit_thread = threading.Thread(
                                    target=self._run_monitor_audit,
                                    args=(ready_ids,),
                                    daemon=True,
                                )
                                audit_thread.start()
                                self._sleep_monitor(10)
                            else:
                                # 仅有待推送订单：启动推单线程
                                print(f"📤 [{datetime.now().strftime('%H:%M:%S')}] {status_summary}，开始自动推单...")
                                self._monitor_push_count += 1

                                self._running = True
                                self.root.after(0, lambda: self.start_btn.config(
                                    state=tk.DISABLED, text="推单中...", bg="#9ca3af"
                                ))
                                push_thread = threading.Thread(
                                    target=self._run_monitor_push_only,
                                    daemon=True,
                                )
                                push_thread.start()
                                self._sleep_monitor(10)
                    else:
                        print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] {status_summary}，{int(wait_interval)}秒后再次检查")
                else:
                    print(f"💤 [{datetime.now().strftime('%H:%M:%S')}] 暂无待处理订单，{int(wait_interval)}秒后再次检查")

            except Exception as e:
                self._adaptive_poller.record_error()
                wait_interval = self._adaptive_poller.get_wait_interval()
                print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] 监控循环异常: {e}")
                import traceback
                print(traceback.format_exc())
                print(f"🔄 {int(wait_interval)}秒后重试...")

            self._sleep_monitor(wait_interval)

    def _sleep_monitor(self, seconds):
        """监控模式下的可中断睡眠，支持随时停止"""
        for _ in range(int(seconds)):
            if not self._monitoring:
                return
            time.sleep(1)

    def _run_monitor_audit(self, ready_order_ids: set[str] | None = None):
        """监控模式下的审单子线程：执行审单并处理后续清理。
        不阻塞监控循环，停止信号可在订单边界即时生效。"""
        try:
            self._run_audit(monitor_mode=True, allowed_order_ids=ready_order_ids)
        finally:
            self._running = False
            self._batch_confirm_decision = None
            self._adaptive_poller.reset()
            self.root.after(0, self._sync_running_timer)
            if self._monitoring:
                self.root.after(0, lambda: self.start_btn.config(
                    state=tk.DISABLED, text="监控中...", bg="#9ca3af"
                ))

    def _run_monitor_push_only(self):
        """监控模式下的推单子线程：仅执行推单，不审单。
        用于仅有待推送订单但无待整理订单的场景。"""
        try:
            from core import AutoAuditEngine
            from adapters.fangguo import FangguoAdapter
            from adapters.fangguo.config import (
                PAGE_SIZE, get_time_begin, get_time_end, DRY_RUN,
            )

            adapter = FangguoAdapter()
            engine = AutoAuditEngine(
                adapter=adapter, dry_run=DRY_RUN,
                max_orders=0, interval=0.5,
                confirm_callback=None,
                should_stop=lambda: not self._monitoring,
            )

            print("\n" + "━" * 60)
            print(" 开始推单（仅推单模式）...")
            print("━" * 60)
            try:
                engine.push_eligible_orders(
                    page_no=1, page_size=PAGE_SIZE,
                    time_begin=get_time_begin(), time_end=get_time_end(),
                )
            except Exception as e:
                print(f"❌ 推单异常：{e}")
        finally:
            self._running = False
            self._adaptive_poller.reset()
            self.root.after(0, self._sync_running_timer)
            if self._monitoring:
                self.root.after(0, lambda: self.start_btn.config(
                    state=tk.DISABLED, text="监控中...", bg="#9ca3af"
                ))

    def _run_audit(self, monitor_mode=False, allowed_order_ids: set[str] | None = None):
        """执行审单。monitor_mode=True 时 confirm_callback=None，无需确认弹窗。"""
        try:
            from core import AutoAuditEngine
            from adapters.fangguo import FangguoAdapter
            from adapters.fangguo.config import (
                QUERY_STATUS, PAGE_SIZE,
                get_time_begin, get_time_end,
                DRY_RUN, MAX_ORDERS,
            )

            adapter = FangguoAdapter()

            # 监控模式下 confirm_callback=None，不弹确认框，直接自动处理
            # 非监控模式下，非 DRY_RUN 时才传入确认回调
            if monitor_mode:
                confirm_cb = None
            else:
                confirm_cb = self._confirm_update if not DRY_RUN else None

            # 监控模式下加超时上限，避免单轮审单长时间阻塞监控循环
            import time as _time
            _audit_start = _time.time()
            _MAX_AUDIT_SECONDS = 600  # 单轮审单上限 10 分钟

            def _should_stop():
                if not self._monitoring:
                    return True
                if _time.time() - _audit_start > _MAX_AUDIT_SECONDS:
                    print(f"⚠️ 审单超时（{_MAX_AUDIT_SECONDS}秒），自动终止本轮")
                    return True
                return False

            engine = AutoAuditEngine(
                adapter=adapter, dry_run=DRY_RUN,
                max_orders=MAX_ORDERS, interval=0.5,
                confirm_callback=confirm_cb,
                should_stop=_should_stop if monitor_mode else None,
                skip_cache=getattr(self, "_monitor_skip_cache", None) if monitor_mode else None,
            )
            # 时间范围动态计算：避免长时间运行后跨天导致漏单
            engine.run(
                page_no=1, page_size=PAGE_SIZE,
                query_status=QUERY_STATUS,
                time_begin=get_time_begin(), time_end=get_time_end(),
                allowed_order_ids=allowed_order_ids,
            )

            # 监控模式下，审单完成后自动执行推单
            if monitor_mode:
                if not self._monitoring:
                    print("⏹️  监控已停止，取消后续推单")
                    return
                # 推单仅响应停止监控，保留十分钟上限只作用于审单的原有行为。
                engine.should_stop = lambda: not self._monitoring
                print("\n" + "━" * 60)
                print(" 审单完成，开始推单...")
                print("━" * 60)
                try:
                    engine.push_eligible_orders(
                        page_no=1, page_size=PAGE_SIZE,
                        time_begin=get_time_begin(), time_end=get_time_end(),
                    )
                except Exception as e:
                    print(f"❌ 推单异常：{e}")
        except Exception as e:
            print(f"\n❌ 审单异常: {e}")
            import traceback
            print(traceback.format_exc())
        finally:
            if not monitor_mode:
                self.root.after(0, self._finish_audit)

    def _on_close(self):
        if self._running or self._monitoring:
            if not messagebox.askyesno("确认退出", "审单/监控正在运行，确定退出吗？"):
                return
        # 停止监控：先保存线程引用，再设标志，最后短暂等待
        if self._monitoring:
            monitor_thread = self._monitor_thread
            self._stop_monitor()
            if monitor_thread and monitor_thread.is_alive():
                monitor_thread.join(timeout=2)
        # 停止Token检测
        self._stop_token_check()
        # 停止运行时间计时器
        self._stop_running_timer()
        # 停止日志队列消费定时器
        if self._log_drain_job is not None:
            try:
                self.root.after_cancel(self._log_drain_job)
            except tk.TclError:
                pass
            self._log_drain_job = None
        # 清理回调注册
        try:
            unregister_auth_callback(self._on_auth_changed)
        except Exception:
            pass
        sys.stdout = sys.__stdout__
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AutoAuditGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
