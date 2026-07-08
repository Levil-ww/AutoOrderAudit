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

from auth_manager import get_auth_status, load_auth, TOKEN_FILE
from adapters.fangguo.config import DRY_RUN, MAX_ORDERS, PAGE_SIZE, QUERY_STATUS, get_time_range_display


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
        self.root.geometry("820x680")
        self.root.resizable(True, True)
        self.root.configure(bg=COLORS["bg"])
        self._running = False

        self._center_window()
        self._configure_tags()
        self._build_layout()
        self._refresh_status()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------
    #  窗口
    # ------------------------------------------------------------
    def _center_window(self):
        self.root.update_idletasks()
        w, h = 820, 680
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

        self._make_badge(badge_frame, "v1.0", COLORS["info_bg"], COLORS["info"]).pack(side=tk.RIGHT)

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
            frame, "🔐 鉴权状态", "检查中...", 0
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
        print("📌 点击下方「开始审单」即可运行")
        print("📌 Token到期请联系技术人员更新 token.json\n")

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
            btn_group, "📂 Token", COLORS["warning"], "#ffffff",
            self._open_token_file, 10,
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
    #  操作
    # ------------------------------------------------------------
    def _refresh_status(self):
        auth = load_auth()
        status = auth.status_text
        self._card_token.config(text=status)

        if "有效" in status and "即将" not in status:
            self._card_token.config(fg=COLORS["success"])
        elif "即将" in status:
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
    #  开始审单
    # ------------------------------------------------------------
    def _start_audit(self):
        if self._running:
            messagebox.showinfo("提示", "正在审单中，请等待完成...")
            return

        auth = load_auth()
        if not auth.authorization:
            messagebox.showerror("鉴权失败", "❌ 未检测到有效Token！\n\n请联系技术人员更新 token.json")
            return
        if not auth.is_valid:
            ret = messagebox.askyesno(
                "Token已过期",
                f"⚠️ Token已过期（{auth.expires_at}），仍要尝试吗？"
            )
            if not ret:
                return

        self._running = True
        self.start_btn.config(state=tk.DISABLED, text="⏳ 审单中...", bg="#9ca3af")
        self.progress.start()

        print("\n" + "━" * 60)
        print(f"🚀 开始自动审单 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 时间范围: {get_time_range_display()}")
        print("━" * 60 + "\n")

        threading.Thread(target=self._run_audit, daemon=True).start()

    def _run_audit(self):
        try:
            from core import AutoAuditEngine
            from adapters.fangguo import FangguoAdapter
            from adapters.fangguo.config import  (
                QUERY_STATUS, PAGE_SIZE, TIME_BEGIN, TIME_END,
                DRY_RUN, MAX_ORDERS,
            )

            adapter = FangguoAdapter()
            engine = AutoAuditEngine(
                adapter=adapter, dry_run=DRY_RUN,
                max_orders=MAX_ORDERS, interval=0.5,
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
        self.start_btn.config(state=tk.NORMAL, text="▶ 开始审单", bg=COLORS["success"])
        self.progress.stop()
        print("\n" + "━" * 60)
        print("✅ 自动审单完成")
        print("━" * 60)

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("确认退出", "审单正在运行，确定退出吗？"):
                return
        sys.stdout = sys.__stdout__
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AutoAuditGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()