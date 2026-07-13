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
    get_auth_status, load_auth, save_auth, AuthInfo,
    TOKEN_FILE, auto_login, register_auth_callback,
    unregister_auth_callback, is_logged_in,
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
        print(f"🔍 登录对话框提交: username=\"{username}\"")

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
        self.root.title("方果ERP · 自动审单工具")
        self.root.geometry("820x720")
        self.root.resizable(True, True)
        self.root.configure(bg=COLORS["bg"])
        self._running = False
        self._batch_confirm_decision = None

        self._center_window()
        self._configure_tags()
        self._build_layout()
        self._refresh_status()

        register_auth_callback(self._on_auth_changed)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.after(500, self._check_login_on_startup)

    # ------------------------------------------------------------
    #  窗口
    # ------------------------------------------------------------
    def _center_window(self):
        self.root.update_idletasks()
        w, h = 820, 720
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

        self._make_badge(badge_frame, "v2.0", COLORS["info_bg"], COLORS["info"]).pack(side=tk.RIGHT)

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

        self._make_button(
            btn_group, "🔄 刷新", COLORS["info"], "#ffffff",
            self._refresh_status, 10,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_button(
            btn_group, "� 登录", COLORS["accent"], "#ffffff",
            self._open_login, 10,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_button(
            btn_group, "🚪 退出登录", COLORS["danger"], "#ffffff",
            self._logout, 10,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_button(
            btn_group, "🗑 清空日志", "#6b7280", "#ffffff",
            self._clear_log, 10,
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

    def _open_login(self):
        """打开登录对话框"""
        LoginDialog(self.root, on_success=self._on_login_success)

    def _on_login_success(self, auth: AuthInfo):
        """登录成功后回调"""
        from adapters.fangguo import config as fg_config
        print(f"🔍 登录前 config.TENANT_ID = {fg_config.TENANT_ID}")
        print(f"🔍 登录前 config.AUTHORIZATION 前缀 = {fg_config.AUTHORIZATION[:20] if fg_config.AUTHORIZATION else '空'}")

        from auth_manager import TOKEN_FILE
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as _f:
                _raw = _f.read()
            print(f"🔍 当前 token.json 内容:\n{_raw}")
        except Exception as _e:
            print(f"⚠️ 读 token.json 失败: {_e}")

        try:
            reload_auth()
            print(f"🔍 登录后 config.TENANT_ID = {fg_config.TENANT_ID}")
            print(f"🔍 登录后 config.AUTHORIZATION 前缀 = {fg_config.AUTHORIZATION[:20] if fg_config.AUTHORIZATION else '空'}")
        except Exception as e:
            print(f"⚠️ reload_auth() 失败: {e}")
        self._refresh_status()
        print(f"✅ 登录成功！欢迎 {auth.username or ''}")
        print(f"🔐 Token有效期至 {auth.expires_at}（剩余{auth.remaining_days}天）")
        print("💡 现在可以开始审单了")
        if not self._running:
            self.start_btn.config(state=tk.NORMAL, bg=COLORS["success"])

    def _on_auth_changed(self, auth: AuthInfo):
        """鉴权信息变化回调（来自auth_manager的通知）"""
        self._refresh_status()

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

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("确认退出", "审单正在运行，确定退出吗？"):
                return
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