"""
方果ERP自动审单 - 图形界面（美化版）
==================================
为客服人员设计，无需任何技术操作。
特点：简洁卡片布局、日志自动着色、结构化展示。
"""

import io
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth_manager import (
    load_auth, AuthInfo,
    auto_login, register_auth_callback,
    unregister_auth_callback,
)
from adapters.fangguo.config import (
    DRY_RUN, MAX_ORDERS, PAGE_SIZE, QUERY_STATUS,
    get_time_range_display, reload_auth,
)


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
}

FONT = "Microsoft YaHei"
FONT_MONO = "Consolas"

# ================================================================
#  自适应监控间隔配置
# ================================================================
MONITOR_MIN_INTERVAL = 10     # 有订单时：10秒后再次检查
MONITOR_MAX_INTERVAL = 180    # 无订单时：最长180秒（3分钟）
MONITOR_INIT_INTERVAL = 30    # 初始间隔：30秒
MONITOR_STEP_FACTOR = 1.5     # 无订单时间隔放大倍数


class LoginDialog:
    """登录对话框"""

    def __init__(self, parent, on_success=None):
        """
        Args:
            parent: 父窗口
            on_success: 登录成功回调，签名 on_success(auth: AuthInfo)
        """
        self.parent = parent
        self.on_success = on_success
        self.result = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("登录方果ERP")
        self.dialog.geometry("400x320")
        self.dialog.resizable(False, False)
        self.dialog.configure(bg=COLORS["card_bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._center()
        self._build_ui()

    def _center(self):
        self.dialog.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        w, h = 400, 320
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        container = tk.Frame(self.dialog, bg=COLORS["card_bg"], padx=30, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            container, text="🔐 登录方果ERP",
            font=(FONT, 16, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
        ).pack(anchor="w", pady=(0, 20))

        tk.Label(
            container, text="手机号",
            font=(FONT, 10), bg=COLORS["card_bg"], fg=COLORS["label_fg"],
        ).pack(anchor="w")
        self.username_var = tk.StringVar()
        tk.Entry(
            container, textvariable=self.username_var,
            font=(FONT, 12), bg="#f9fafb",
            relief=tk.SOLID, bd=1,
        ).pack(fill=tk.X, pady=(4, 14), ipady=4)

        tk.Label(
            container, text="密码",
            font=(FONT, 10), bg=COLORS["card_bg"], fg=COLORS["label_fg"],
        ).pack(anchor="w")
        self.password_var = tk.StringVar()
        password_entry = tk.Entry(
            container, textvariable=self.password_var,
            font=(FONT, 12), bg="#f9fafb",
            show="*", relief=tk.SOLID, bd=1,
        )
        password_entry.pack(fill=tk.X, pady=(4, 20), ipady=4)
        password_entry.bind("<Return>", lambda e: self._do_login())

        self.status_label = tk.Label(
            container, text="",
            font=(FONT, 10), bg=COLORS["card_bg"], fg=COLORS["danger"],
        )
        self.status_label.pack(anchor="w")

        btn_frame = tk.Frame(container, bg=COLORS["card_bg"])
        btn_frame.pack(fill=tk.X)

        self.login_btn = tk.Button(
            btn_frame, text="登 录", font=(FONT, 12, "bold"),
            bg=COLORS["accent"], fg="#ffffff",
            padx=24, pady=8, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._do_login,
        )
        self.login_btn.pack(side=tk.RIGHT)

        tk.Button(
            btn_frame, text="取消", font=(FONT, 12),
            bg=COLORS["card_bg"], fg=COLORS["label_fg"],
            padx=16, pady=8, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self.dialog.destroy,
        ).pack(side=tk.RIGHT, padx=(0, 10))

    def _do_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()

        if not username:
            self.status_label.config(text="请输入手机号")
            return
        if not password:
            self.status_label.config(text="请输入密码")
            return

        self.login_btn.config(state=tk.DISABLED, text="登录中...", bg="#9ca3af")
        self.status_label.config(text="正在登录...", fg=COLORS["info"])
        self.dialog.update()

        def _do():
            try:
                result = auto_login(username, password)
                self.dialog.after(0, self._login_callback, result)
            except Exception as e:
                self.dialog.after(0, self._error_callback, str(e))

        threading.Thread(target=_do, daemon=True).start()

    def _login_callback(self, result):
        self.login_btn.config(state=tk.NORMAL, text="登 录", bg=COLORS["accent"])

        if result.success:
            self.status_label.config(
                text=f"✅ {result.msg}（{result.main_username}）",
                fg=COLORS["success"],
            )
            self.dialog.update()
            self.dialog.after(800, self._close_success)
        else:
            self.status_label.config(text=f"❌ {result.msg}", fg=COLORS["danger"])

    def _error_callback(self, error_msg):
        self.login_btn.config(state=tk.NORMAL, text="登 录", bg=COLORS["accent"])
        self.status_label.config(text=f"❌ 登录异常: {error_msg}", fg=COLORS["danger"])

    def _close_success(self):
        auth = load_auth()
        self.dialog.destroy()
        if self.on_success:
            self.on_success(auth)


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
        (re.compile(r"^=+$"),       "tag_separator"),
        (re.compile(r"^─+$"),       "tag_separator"),
        (re.compile(r"^\[.*\].*$"), "tag_order"),
        (re.compile(r"^\s+│.*$"),   "tag_detail"),
    ]

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def write(self, string):
        if not string:
            return
        # 检测颜色
        tag = None
        for pattern, t in self._TAG_RULES:
            if pattern.match(string):
                tag = t
                break

        self.text_widget.insert(tk.END, string, tag)
        self.text_widget.see(tk.END)
        self.text_widget.update_idletasks()

    def flush(self):
        pass


class AutoAuditGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("方果ERP · 自动审单工具V2.1")
        self.root.geometry("950x720")
        self.root.resizable(True, True)
        self.root.configure(bg=COLORS["bg"])
        self._running = False
        self._batch_confirm_decision = None

        # 自动监控相关状态
        self._auto_monitor = False              # 监控开关
        self._monitor_thread = None             # 监控线程
        self._monitor_stop_event = threading.Event()  # 停止信号

        # Token自动检查相关状态
        self._token_check_running = False       # Token检查是否在运行
        self._token_check_stop_event = threading.Event()  # Token检查停止信号
        self._login_dialog_showing = False      # 登录对话框是否正在显示（防止重复弹出）

        self._center_window()
        self._configure_tags()
        self._build_layout()
        self._refresh_status()

        register_auth_callback(self._on_auth_changed)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.after(500, self._check_login_on_startup)
        self.root.after(1000, self._start_token_check)

    # ------------------------------------------------------------
    #  窗口
    # ------------------------------------------------------------
    def _center_window(self):
        self.root.update_idletasks()
        w, h = 950, 720
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ------------------------------------------------------------
    #  日志文本颜色配置
    # ------------------------------------------------------------
    def _configure_tags(self):
        # 这些标签在文本控件创建前就需要？不，在Text创建后配置
        pass

    def _setup_text_tags(self, text):
        text.tag_config("tag_success", foreground=COLORS["success"])
        text.tag_config("tag_danger",  foreground=COLORS["danger"])
        text.tag_config("tag_warning", foreground=COLORS["warning"])
        text.tag_config("tag_info",    foreground=COLORS["info"])
        text.tag_config("tag_separator", foreground="#9ca3af", font=(FONT_MONO, 8))
        text.tag_config("tag_order",   foreground=COLORS["header_fg"], font=(FONT, 10, "bold"))
        text.tag_config("tag_detail",  foreground="#6b7280")

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
        header = tk.Frame(parent, bg=COLORS["bg"])
        header.pack(fill=tk.X, pady=(0, 16))

        title = tk.Label(
            header, text="📋 方果ERP · 自动审单工具",
            font=(FONT, 20, "bold"), bg=COLORS["bg"],
            fg=COLORS["header_fg"],
        )
        title.pack(side=tk.LEFT)

        badge_frame = tk.Frame(header, bg=COLORS["bg"])
        badge_frame.pack(side=tk.RIGHT)

        # 模式标签
        mode_text = "🔶 模拟模式" if DRY_RUN else "✅ 正式模式"
        mode_bg = COLORS["warning_bg"] if DRY_RUN else COLORS["success_bg"]
        mode_fg = COLORS["warning"] if DRY_RUN else COLORS["success"]
        self._make_badge(badge_frame, mode_text, mode_bg, mode_fg).pack(side=tk.RIGHT, padx=(6, 0))

        self._make_badge(badge_frame, "V2.1", COLORS["info_bg"], COLORS["info"]).pack(side=tk.RIGHT)

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
            frame, "🔐 登录状态", "检查中...", 0
        )
        self._card_time = self._make_status_card(
            frame, "📅 审单范围", get_time_range_display(), 1
        )
        self._card_mode = self._make_status_card(
            frame, "⚙️ 运行模式",
            "仅模拟（不真实提交）" if DRY_RUN else "正式模式（会实际修改）",
            2
        )

    def _make_status_card(self, parent, title, value, col):
        card = tk.Frame(
            parent, bg=COLORS["card_bg"],
            highlightbackground=COLORS["card_border"],
            highlightthickness=1, padx=16, pady=12,
        )
        card.grid(row=0, column=col, sticky="ew", padx=(0, 10))
        parent.grid_columnconfigure(col, weight=1)

        tk.Label(
            card, text=title, font=(FONT, 9),
            bg=COLORS["card_bg"], fg=COLORS["label_fg"],
        ).pack(anchor="w")

        value_label = tk.Label(
            card, text=value, font=(FONT, 11, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
            anchor="w", wraplength=220,
        )
        value_label.pack(anchor="w", pady=(4, 0))

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
            title_row, text="📝 运行日志", font=(FONT, 12, "bold"),
            bg=COLORS["bg"], fg=COLORS["header_fg"],
        ).pack(side=tk.LEFT)

        # 统计信息
        self.stat_label = tk.Label(
            title_row, text="",
            font=(FONT, 9), bg=COLORS["bg"], fg=COLORS["label_fg"],
        )
        self.stat_label.pack(side=tk.RIGHT)

        # 日志卡片
        log_card = tk.Frame(
            log_outer, bg=COLORS["card_bg"],
            highlightbackground=COLORS["card_border"],
            highlightthickness=1,
        )
        log_card.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_card,
            wrap=tk.WORD,
            font=(FONT_MONO, 10),
            bg="#fafafa",
            fg=COLORS["text_fg"],
            insertbackground=COLORS["text_fg"],
            relief=tk.FLAT,
            borderwidth=0,
            padx=14, pady=10,
            height=18,
            highlightthickness=0,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self._setup_text_tags(self.log_text)

        # 重定向 print
        self.text_redirector = TextRedirector(self.log_text)
        sys.stdout = self.text_redirector

        # 初始信息
        print(f"🟢 自动审单工具已启动 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("📌 点击下方「登录」按钮，输入手机号密码即可开始使用")
        print("📌 点击「开始审单」自动处理待整理订单\n")

    # ------------------------------------------------------------
    #  底部按钮
    # ------------------------------------------------------------
    def _build_footer(self, parent):
        footer = tk.Frame(parent, bg=COLORS["bg"])
        footer.pack(fill=tk.X)

        # 左侧按钮组
        btn_group = tk.Frame(footer, bg=COLORS["bg"])
        btn_group.pack(side=tk.LEFT)

        self.start_btn = self._make_button(
            btn_group, "▶ 开始审单", COLORS["success"], "#ffffff",
            self._start_audit, 12,
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.monitor_btn = self._make_button(
            btn_group, "🔄 自动监控", COLORS["warning"], "#ffffff",
            self._toggle_monitor, 11,
        )
        self.monitor_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._make_button(
            btn_group, "🔄 刷新", COLORS["info"], "#ffffff",
            self._refresh_status, 10,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.login_btn_footer = self._make_button(
            btn_group, "🔐 登录", COLORS["accent"], "#ffffff",
            self._open_login, 10,
        )
        self.login_btn_footer.pack(side=tk.LEFT, padx=(0, 8))

        self.logout_btn_footer = self._make_button(
            btn_group, "🚪 退出登录", COLORS["danger"], "#ffffff",
            self._logout, 10,
        )
        self.logout_btn_footer.pack(side=tk.LEFT, padx=(0, 8))

        self._make_button(
            btn_group, "🗑 清空日志", "#6b7280", "#ffffff",
            self._clear_log, 10,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_button(
            btn_group, "🚚 快递配置", COLORS["warning"], "#ffffff",
            self._open_express_config, 10,
        ).pack(side=tk.LEFT)

        # 右侧进度条
        right = tk.Frame(footer, bg=COLORS["bg"])
        right.pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(right, mode="indeterminate", length=160)
        self.progress.pack(side=tk.RIGHT)

    def _make_button(self, parent, text, bg, fg, cmd, font_size):
        return tk.Button(
            parent, text=text, font=(FONT, font_size, "bold"),
            bg=bg, fg=fg, padx=18, pady=7,
            relief=tk.FLAT, bd=0, cursor="hand2",
            activebackground=bg, activeforeground=fg,
            command=cmd,
        )

    # ------------------------------------------------------------
    #  登录相关
    # ------------------------------------------------------------
    def _check_login_on_startup(self):
        """启动时检查登录状态"""
        auth = load_auth()
        if not auth.authorization:
            print("🔐 检测到未登录，请点击「登录」按钮输入账号密码")
        elif not auth.is_valid:
            print(f"⚠️ Token已过期（{auth.expires_at}），请重新登录")
        else:
            print(f"✅ Token有效（{auth.username or ''}，剩余{auth.remaining_days}天）")
            # 登录状态正常，弹窗询问是否开启自动监控
            self.root.after(800, self._ask_start_monitor)

    def _ask_start_monitor(self):
        """启动时弹窗询问是否开启自动监控"""
        if self._auto_monitor:
            return  # 已经在监控中
        ret = messagebox.askyesno(
            "自动审单",
            "✅ 登录状态正常！\n\n"
            "是否立即开启自动审单监控？\n\n"
            "📌 开启后程序将自动检测待处理订单并执行审单\n"
            "📌 自适应间隔：有订单时快查，无订单时自动拉长间隔\n"
            "📌 可随时点击「停止监控」按钮关闭"
        )
        if ret:
            self._start_monitor()

    def _open_login(self):
        """打开登录对话框"""
        if self._login_dialog_showing:
            return
        LoginDialog(self.root, on_success=self._on_login_success)

    def _show_auto_relogin_dialog(self, reason: str = "Token已过期"):
        """Token过期时自动弹出登录对话框

        Args:
            reason: 弹出登录框的原因描述
        """
        if self._login_dialog_showing:
            return

        self._login_dialog_showing = True
        print(f"\n⚠️ {reason}，请重新登录")

        def _on_success(auth: AuthInfo):
            self._login_dialog_showing = False
            self._on_login_success(auth)

        def _on_close():
            self._login_dialog_showing = False

        dialog = LoginDialog(self.root, on_success=_on_success)

        # 监听对话框关闭事件
        original_destroy = dialog.dialog.destroy

        def _wrapped_destroy():
            self._login_dialog_showing = False
            original_destroy()

        dialog.dialog.destroy = _wrapped_destroy

    def _on_login_success(self, auth: AuthInfo):
        """登录成功后回调"""
        try:
            reload_auth()
        except Exception:
            pass

        self._refresh_status()
        print(f"✅ 登录成功！欢迎 {auth.username or ''}")
        print(f"🔐 Token有效期至 {auth.expires_at}（剩余{auth.remaining_days}天）")
        print("💡 现在可以开始审单了")
        if not self._running:
            self.start_btn.config(state=tk.NORMAL, bg=COLORS["success"])

        # 登录成功后询问是否开启自动监控
        if not self._auto_monitor:
            self.root.after(500, self._ask_start_monitor)

    def _on_auth_changed(self, auth: AuthInfo):
        """鉴权信息变化回调（来自auth_manager的通知）"""
        self._refresh_status()

    # ------------------------------------------------------------
    #  🔐 Token自动检查（后台周期性检测）
    # ------------------------------------------------------------
    def _start_token_check(self):
        """启动Token定时检查线程"""
        if self._token_check_running:
            return
        self._token_check_running = True
        self._token_check_stop_event.clear()
        threading.Thread(target=self._token_check_loop, daemon=True).start()

    def _stop_token_check(self):
        """停止Token定时检查"""
        self._token_check_running = False
        self._token_check_stop_event.set()

    def _token_check_loop(self):
        """Token检查线程主循环"""
        # 首次等待2秒后开始检查
        self._token_check_stop_event.wait(timeout=2)

        while self._token_check_running:
            if self._token_check_stop_event.is_set():
                break

            try:
                auth = load_auth()

                # 只有在有Token的情况下才检查是否过期
                if auth.authorization:
                    if not auth.is_valid:
                        # Token已过期，自动弹出登录框
                        if not self._login_dialog_showing:
                            print(f"\n⚠️ 检测到Token已过期（{auth.expires_at}）")
                            self.root.after(0, lambda: self._show_auto_relogin_dialog("Token已过期"))
                    else:
                        # Token即将过期（剩余1天），提前提醒
                        if auth.remaining_days <= 1:
                            print(f"⚠️ Token即将过期，剩余{auth.remaining_days}天，请及时重新登录")

            except Exception as e:
                # 检查出错不影响主流程
                pass

            # 每60秒检查一次
            self._token_check_stop_event.wait(timeout=60)

        print("🔐 Token检查线程已退出")

    def _logout(self):
        """退出登录，清除Token"""
        if not load_auth().authorization:
            return
        if not messagebox.askyesno("确认退出", "确定要退出登录吗？退出后需重新登录才能使用。"):
            return

        from auth_manager import reset_auth
        reset_auth()
        try:
            reload_auth()
        except Exception:
            pass
        self._refresh_status()
        print("🔐 已退出登录")
        print("📌 下次使用时点击「登录」按钮重新登录")

    # ------------------------------------------------------------
    #  操作
    # ------------------------------------------------------------
    def _refresh_status(self):
        auth = load_auth()
        status = auth.status_text
        self._card_token.config(text=status)

        if "✅" in status:
            self._card_token.config(fg=COLORS["success"])
        elif "⚠️" in status:
            self._card_token.config(fg=COLORS["warning"])
        else:
            self._card_token.config(fg=COLORS["danger"])

        self._card_time.config(text=get_time_range_display())

        # 动态更新登录/退出按钮显示状态
        self._update_login_buttons(auth)

    def _update_login_buttons(self, auth: AuthInfo = None):
        """根据登录状态动态更新登录/退出按钮的显示"""
        if auth is None:
            auth = load_auth()

        is_logged_in = bool(auth.authorization) and auth.is_valid

        if is_logged_in:
            # 已登录：显示退出按钮，隐藏登录按钮
            self.logout_btn_footer.pack(side=tk.LEFT, padx=(0, 8))
            self.login_btn_footer.pack_forget()
        else:
            # 未登录或Token过期：显示登录按钮，隐藏退出按钮
            self.login_btn_footer.pack(side=tk.LEFT, padx=(0, 8))
            self.logout_btn_footer.pack_forget()

    def _open_token_file(self):
        path = os.path.join(os.path.dirname(__file__), "token.json")
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
        self.log_text.delete(1.0, tk.END)

    def _update_stat(self, text):
        self.stat_label.config(text=text)

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
        event.wait()

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
        self.start_btn.config(state=tk.DISABLED, text="⏳ 审单中...", bg="#9ca3af")
        self.progress.start()

        print("\n" + "━" * 60)
        print(f"🚀 开始自动审单 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 时间范围: {get_time_range_display()}")
        print(f"👤 当前用户: {auth.username or 'Unknown'}")
        print("━" * 60 + "\n")

        threading.Thread(target=self._run_audit, daemon=True).start()

    def _run_audit(self):
        try:
            from core import AutoAuditEngine
            from adapters.fangguo import FangguoAdapter
            from adapters.fangguo.config import (
                QUERY_STATUS, PAGE_SIZE, TIME_BEGIN, TIME_END,
                DRY_RUN, MAX_ORDERS,
            )

            adapter = FangguoAdapter()

            # 只在非 DRY_RUN 模式下才传入确认回调
            confirm_cb = self._confirm_update if not DRY_RUN else None

            engine = AutoAuditEngine(
                adapter=adapter, dry_run=DRY_RUN,
                max_orders=MAX_ORDERS, interval=0.5,
                confirm_callback=confirm_cb,
            )
            engine.run(
                page_no=1, page_size=PAGE_SIZE,
                query_status=QUERY_STATUS,
                time_begin=TIME_BEGIN, time_end=TIME_END,
            )
        except Exception as e:
            print(f"\n❌ 审单异常: {e}")
            import traceback
            print(traceback.format_exc())
        finally:
            self.root.after(0, self._finish_audit)

    def _finish_audit(self):
        self._running = False
        self._batch_confirm_decision = None  # 清理批量决策缓存
        self.start_btn.config(state=tk.NORMAL, text="▶ 开始审单", bg=COLORS["success"])
        self.progress.stop()
        print("\n" + "━" * 60)
        print("✅ 自动审单完成")
        print("━" * 60)

    # ------------------------------------------------------------
    #  🔁 自动监控模式（自适应间隔轮询）
    # ------------------------------------------------------------
    def _toggle_monitor(self):
        """切换自动监控开关"""
        if self._auto_monitor:
            self._stop_monitor()
        else:
            self._start_monitor()

    def _start_monitor(self):
        """启动自动监控"""
        auth = load_auth()
        if not auth.authorization:
            messagebox.showerror("未登录", "❌ 请先点击「登录」按钮输入账号密码！")
            return
        if not auth.is_valid:
            messagebox.showerror("Token已过期", "⚠️ Token已过期，请重新登录！")
            return

        self._auto_monitor = True
        self._monitor_stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        self.monitor_btn.config(text="⏸ 停止监控", bg=COLORS["danger"])
        print("\n" + "━" * 60)
        print(f"🔄 自动监控已启动 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📌 自适应间隔：有订单时 {MONITOR_MIN_INTERVAL}秒，无订单时逐步拉长至 {MONITOR_MAX_INTERVAL}秒")
        print("━" * 60)

    def _stop_monitor(self):
        """停止自动监控"""
        self._auto_monitor = False
        self._monitor_stop_event.set()
        self.monitor_btn.config(text="🔄 自动监控", bg=COLORS["warning"])
        print("\n🛑 自动监控已停止")

    def _monitor_loop(self):
        """监控线程主循环：自适应间隔轮询待处理订单"""
        interval = MONITOR_INIT_INTERVAL
        # 跨轮询共享的已正确订单缓存，避免重复处理同一订单
        skip_cache = {}

        while self._auto_monitor:
            # 检查停止信号
            if self._monitor_stop_event.is_set():
                break

            # 1. 检查 Token 有效性
            auth = load_auth()
            if not auth.authorization or not auth.is_valid:
                print("⚠️ Token已失效，自动监控已暂停，请重新登录")
                self.root.after(0, lambda: self._show_auto_relogin_dialog("Token已过期"))
                self.root.after(0, self._stop_monitor)
                return

            # 2. 如果正在手动审单，等待
            if self._running:
                self._monitor_stop_event.wait(timeout=3)
                continue

            # 3. 执行审单周期
            self._running = True
            self._batch_confirm_decision = None
            processed = 0

            try:
                from core import AutoAuditEngine
                from adapters.fangguo import FangguoAdapter
                from adapters.fangguo.config import (
                    QUERY_STATUS, PAGE_SIZE, TIME_BEGIN, TIME_END,
                    DRY_RUN, MAX_ORDERS,
                )

                adapter = FangguoAdapter()
                confirm_cb = None
                engine = AutoAuditEngine(
                    adapter=adapter, dry_run=DRY_RUN,
                    max_orders=MAX_ORDERS, interval=0.5,
                    confirm_callback=confirm_cb,
                    skip_cache=skip_cache,
                )
                processed = engine.run_monitor_cycle(
                    page_no=1, page_size=PAGE_SIZE,
                    query_status=QUERY_STATUS,
                    time_begin=TIME_BEGIN, time_end=TIME_END,
                )
            except Exception as e:
                print(f"❌ 监控异常: {e}")
                import traceback
                print(traceback.format_exc())
            finally:
                self._running = False
                self._batch_confirm_decision = None

            # 4. 自适应调整间隔
            if processed > 0:
                interval = MONITOR_MIN_INTERVAL
            else:
                interval = min(int(interval * MONITOR_STEP_FACTOR), MONITOR_MAX_INTERVAL)
                now = datetime.now().strftime('%H:%M:%S')
                print(f"😴 [{now}] 无待处理订单，{interval}秒后再次检查...")

            # 5. 更新UI按钮显示
            self.root.after(0, lambda i=interval, p=processed: self._update_monitor_btn(i, p))

            # 6. 可中断等待
            self._monitor_stop_event.wait(timeout=interval)

        print("🛑 自动监控线程已退出")

    def _update_monitor_btn(self, next_interval, processed):
        """更新监控按钮显示倒计时"""
        if not self._auto_monitor:
            return
        self.monitor_btn.config(text=f"⏸ 监控中({next_interval}s)", bg=COLORS["danger"])

    def _open_express_config(self):
        """打开快递配置对话框"""
        ExpressConfigDialog(self.root)

    def _on_close(self):
        # 先停止Token检查线程
        if self._token_check_running:
            self._token_check_running = False
            self._token_check_stop_event.set()

        # 先停止监控线程
        if self._auto_monitor:
            self._auto_monitor = False
            self._monitor_stop_event.set()

        if self._running:
            if not messagebox.askyesno("确认退出", "审单正在运行，确定退出吗？"):
                return
        try:
            unregister_auth_callback(self._on_auth_changed)
        except Exception:
            pass
        sys.stdout = sys.__stdout__
        self.root.destroy()


class ExpressConfigDialog:
    """快递配置对话框"""

    def __init__(self, parent):
        self.parent = parent
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("快递配置")
        self.dialog.geometry("680x600")
        self.dialog.configure(bg=COLORS["card_bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.resizable(True, True)

        self._center()
        self._build_ui()

    def _center(self):
        self.dialog.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        w, h = 680, 600
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        import express_config as ec

        container = tk.Frame(self.dialog, bg=COLORS["card_bg"], padx=20, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        # 标题
        tk.Label(
            container, text="🚚 快递配置",
            font=(FONT, 16, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
        ).pack(anchor="w", pady=(0, 12))

        # 说明文字
        tk.Label(
            container,
            text="• 备注关键词优先级高于省份规则\\n• 下方可修改各省份默认快递，也可添加新的快递公司",
            font=(FONT, 9),
            bg=COLORS["card_bg"], fg=COLORS["label_fg"],
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 10))

        # 使用Notebook分两个标签页
        notebook = ttk.Notebook(container)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        # ========== 标签页1：省份规则 ==========
        tab1 = tk.Frame(notebook, bg=COLORS["card_bg"])
        notebook.add(tab1, text="省份规则")

        self._build_province_tab(tab1, ec)

        # ========== 标签页2：快递类型 ==========
        tab2 = tk.Frame(notebook, bg=COLORS["card_bg"])
        notebook.add(tab2, text="快递类型")

        self._build_express_tab(tab2, ec)

        # 底部按钮
        btn_frame = tk.Frame(container, bg=COLORS["card_bg"])
        btn_frame.pack(fill=tk.X, pady=(4, 0))

        tk.Button(
            btn_frame, text="💾 保存配置", font=(FONT, 11, "bold"),
            bg=COLORS["success"], fg="#ffffff",
            padx=20, pady=6, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._save_config,
        ).pack(side=tk.RIGHT)

        tk.Button(
            btn_frame, text="🔄 恢复默认", font=(FONT, 11),
            bg=COLORS["warning_bg"], fg=COLORS["warning"],
            padx=16, pady=6, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._reset_default,
        ).pack(side=tk.RIGHT, padx=(0, 10))

        tk.Button(
            btn_frame, text="关闭", font=(FONT, 11),
            bg=COLORS["card_bg"], fg=COLORS["label_fg"],
            padx=16, pady=6, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self.dialog.destroy,
        ).pack(side=tk.RIGHT, padx=(0, 10))

    def _build_province_tab(self, parent, ec):
        """构建省份规则标签页"""
        # 表头
        header = tk.Frame(parent, bg=COLORS["card_bg"])
        header.pack(fill=tk.X, pady=(8, 4))

        tk.Label(header, text="省份", font=(FONT, 10, "bold"),
                 bg=COLORS["card_bg"], fg=COLORS["header_fg"], width=12).pack(side=tk.LEFT)
        tk.Label(header, text="默认快递", font=(FONT, 10, "bold"),
                 bg=COLORS["card_bg"], fg=COLORS["header_fg"]).pack(side=tk.LEFT, padx=(20, 0))

        # 滚动区域
        canvas_frame = tk.Frame(parent, bg=COLORS["card_bg"])
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_frame, bg=COLORS["card_bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=COLORS["card_bg"])

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 加载当前配置
        self.province_vars = {}
        rules = ec.get_all_province_rules()
        express_names = ec.get_all_express_names()

        row = 0
        for province in sorted(rules.keys(), key=lambda x: (len(x), x)):
            frame = tk.Frame(scroll_frame, bg=COLORS["card_bg"])
            frame.pack(fill=tk.X, pady=2)

            tk.Label(frame, text=province, font=(FONT, 10),
                     bg=COLORS["card_bg"], fg=COLORS["text_fg"], width=12, anchor="w").pack(side=tk.LEFT)

            var = tk.StringVar(value=rules.get(province, ""))
            self.province_vars[province] = var

            cb = ttk.Combobox(frame, textvariable=var, values=express_names,
                              state="readonly", width=14, font=(FONT, 10))
            cb.pack(side=tk.LEFT, padx=(20, 0))

            row += 1

    def _build_express_tab(self, parent, ec):
        """构建快递类型标签页"""
        # 当前列表
        list_frame = tk.Frame(parent, bg=COLORS["card_bg"])
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 8))

        tk.Label(list_frame, text="当前快递类型", font=(FONT, 11, "bold"),
                 bg=COLORS["card_bg"], fg=COLORS["header_fg"]).pack(anchor="w")

        self.express_tree = ttk.Treeview(list_frame, columns=("name", "code"), show="headings", height=10)
        self.express_tree.heading("name", text="快递公司")
        self.express_tree.heading("code", text="ERP编码")
        self.express_tree.column("name", width=160, anchor="w")
        self.express_tree.column("code", width=160, anchor="w")
        self.express_tree.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        self._refresh_express_list(ec)

        # 添加区域
        add_frame = tk.Frame(parent, bg=COLORS["card_bg"], pady=10)
        add_frame.pack(fill=tk.X)

        tk.Label(add_frame, text="添加快递:", font=(FONT, 10),
                 bg=COLORS["card_bg"], fg=COLORS["text_fg"]).pack(side=tk.LEFT)

        self.new_name_var = tk.StringVar()
        tk.Entry(add_frame, textvariable=self.new_name_var, font=(FONT, 10),
                 width=12, relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(add_frame, text="编码:", font=(FONT, 10),
                 bg=COLORS["card_bg"], fg=COLORS["text_fg"]).pack(side=tk.LEFT, padx=(10, 0))

        self.new_code_var = tk.StringVar()
        tk.Entry(add_frame, textvariable=self.new_code_var, font=(FONT, 10),
                 width=12, relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=(6, 0))

        tk.Button(
            add_frame, text="➕ 添加", font=(FONT, 10),
            bg=COLORS["accent"], fg="#ffffff",
            padx=12, pady=3, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._add_express_type,
        ).pack(side=tk.LEFT, padx=(10, 0))

        tk.Button(
            add_frame, text="🗑 删除选中", font=(FONT, 10),
            bg=COLORS["danger_bg"], fg=COLORS["danger"],
            padx=12, pady=3, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._remove_selected_express,
        ).pack(side=tk.LEFT, padx=(8, 0))

    def _refresh_express_list(self, ec):
        """刷新快递类型列表"""
        for item in self.express_tree.get_children():
            self.express_tree.delete(item)
        config = ec.load_config()
        for name, code in config.get("express_codes", {}).items():
            self.express_tree.insert("", tk.END, values=(name, code))

    def _add_express_type(self):
        import express_config as ec
        name = self.new_name_var.get().strip()
        code = self.new_code_var.get().strip()
        if not name or not code:
            messagebox.showwarning("输入不完整", "请填写快递公司名称和编码", parent=self.dialog)
            return
        ec.add_express_type(name, code)
        self._refresh_express_list(ec)
        self.new_name_var.set("")
        self.new_code_var.set("")
        messagebox.showinfo("添加成功", f"已添加 {name} ({code})", parent=self.dialog)

    def _remove_selected_express(self):
        import express_config as ec
        selected = self.express_tree.selection()
        if not selected:
            messagebox.showwarning("未选择", "请先选中要删除的快递类型", parent=self.dialog)
            return
        item = selected[0]
        values = self.express_tree.item(item, "values")
        name = values[0]
        if messagebox.askyesno("确认删除", f"确定删除快递类型 '{name}' 吗？\\n（使用该快递的省份规则也会被清除）", parent=self.dialog):
            ec.remove_express_type(name)
            self._refresh_express_list(ec)
            # 刷新省份页的下拉框需要重建，简单处理是提示用户重新打开
            messagebox.showinfo("已删除", "快递类型已删除，请关闭窗口重新打开以刷新省份下拉框", parent=self.dialog)

    def _save_config(self):
        import express_config as ec
        # 保存省份规则
        for province, var in self.province_vars.items():
            ec.update_province_rule(province, var.get())
        messagebox.showinfo("保存成功", "快递配置已保存", parent=self.dialog)

    def _reset_default(self):
        import express_config as ec
        if messagebox.askyesno("确认恢复", "确定恢复为默认配置吗？所有自定义修改将丢失。", parent=self.dialog):
            ec.reset_to_default()
            messagebox.showinfo("已恢复", "已恢复默认配置，请关闭窗口重新打开", parent=self.dialog)
            self.dialog.destroy()


def main():
    root = tk.Tk()
    app = AutoAuditGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()