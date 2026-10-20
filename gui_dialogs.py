"""
方果ERP自动审单 - 配置对话框
==============================
从 gui.py 提取的独立对话框模块：
- LoginDialog: 登录对话框
- ExpressConfigDialog: 快递配置弹窗
- GiftConfigDialog: 赠品配置弹窗
"""

import json
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from auth_manager import auto_login, load_auth
from express_manager import get_manager as get_express_manager
from gift_manager import get_manager as get_gift_manager


# ── 从 gui.py 导入共享 UI 资源 ────────────────────────────────
# 延迟导入避免循环依赖：gui.py 先定义这些资源，再导入本模块
# 本模块在运行时使用这些资源时，gui.py 已加载完毕
def _get_gui_resources():
    """获取 gui.py 中定义的共享 UI 资源。"""
    import gui
    return gui.COLORS, gui.FONT, gui._center_toplevel, gui._build_treeview


# ── 圆角按钮（供 LoginDialog 使用，也供 gui.py 的 AutoAuditGUI 使用）────
class _RoundedButton:
    """Canvas 实现的圆角按钮，支持实心和描边两种样式"""

    def __init__(self, parent, text, bg, fg, command, font_size,
                 radius=8, outline=None, outline_width=0, padx=18, pady=7):
        self.command = command
        self._bg = bg
        self._fg = fg
        self._active_bg = self._darken(bg, 0.15) if bg.startswith("#") else bg
        self._text = text
        self._font_size = font_size
        self._state = tk.NORMAL

        COLORS, FONT, _, _ = _get_gui_resources()

        # 估算文字尺寸
        tmp = tk.Label(parent, text=text, font=(FONT, font_size, "bold" if outline is None else "normal"))
        tmp.update_idletasks()
        tw = tmp.winfo_reqwidth()
        th = tmp.winfo_reqheight()
        tmp.destroy()

        w = tw + padx * 2
        h = th + pady * 2

        self.canvas = tk.Canvas(parent, width=w, height=h,
                                bg=parent.cget("bg") if hasattr(parent, "cget") else "#f0f2f5",
                                highlightthickness=0, cursor="hand2")
        self.canvas.pack(side=tk.LEFT, padx=4)

        self._draw(radius, outline, outline_width)

        self.canvas.bind("<Button-1>", lambda e: self._on_click())
        self.canvas.bind("<Enter>", lambda e: self._on_hover(True))
        self.canvas.bind("<Leave>", lambda e: self._on_hover(False))

    def _draw(self, radius, outline, outline_width):
        _, FONT, _, _ = _get_gui_resources()
        self.canvas.delete("all")
        w = int(self.canvas["width"])
        h = int(self.canvas["height"])
        r = min(radius, w // 2, h // 2)

        fill = self._bg
        self.canvas.create_roundrect(0, 0, w, h, r, fill=fill,
                                      outline=outline or "",
                                      width=outline_width or 0)

        cx, cy = w // 2, h // 2
        self.canvas.create_text(cx, cy, text=self._text,
                                font=(FONT, self._font_size,
                                      "bold" if outline is None else "normal"),
                                fill=self._fg)

    def _on_click(self):
        if self.command:
            self.command()

    def _on_hover(self, enter):
        _, FONT, _, _ = _get_gui_resources()
        if enter:
            self.canvas.delete("all")
            w = int(self.canvas["width"])
            h = int(self.canvas["height"])
            r = min(8, w // 2, h // 2)
            self.canvas.create_roundrect(0, 0, w, h, r,
                                          fill=self._active_bg,
                                          outline="", width=0)
            cx, cy = w // 2, h // 2
            self.canvas.create_text(cx, cy, text=self._text,
                                    font=(FONT, self._font_size, "bold"),
                                    fill="#ffffff")
        else:
            self._draw(8, None, 0)

    def config(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs["text"]
        if "bg" in kwargs:
            self._bg = kwargs["bg"]
            self._active_bg = self._darken(kwargs["bg"], 0.15)
        if "state" in kwargs:
            self._state = kwargs["state"]
            if kwargs["state"] == tk.DISABLED:
                self.canvas.config(cursor="")
            else:
                self.canvas.config(cursor="hand2")
        self._draw(8, None, 0)

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "bg":
            return self._bg
        return ""

    @staticmethod
    def _darken(hex_color, factor):
        """将颜色变暗"""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r = max(0, int(r * (1 - factor)))
        g = max(0, int(g * (1 - factor)))
        b = max(0, int(b * (1 - factor)))
        return f"#{r:02x}{g:02x}{b:02x}"


# 为 Canvas 添加 create_roundrect 方法
def _create_roundrect(self, x1, y1, x2, y2, radius, **kwargs):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return self.create_polygon(points, smooth=True, **kwargs)

tk.Canvas.create_roundrect = _create_roundrect


# ================================================================
#  登录对话框
# ================================================================

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

        COLORS, FONT, _center_toplevel, _ = _get_gui_resources()

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("登录方果ERP")
        self.dialog.resizable(False, False)
        self.dialog.configure(bg=COLORS["card_bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._build_ui()
        # 按实际内容尺寸居中，避免字体缩放后底部登录按钮被裁剪。
        self.dialog.update_idletasks()
        width = max(400, self.dialog.winfo_reqwidth())
        height = max(440, self.dialog.winfo_reqheight())
        _center_toplevel(self.dialog, parent, width, height)

    def _get_username_file(self) -> str:
        """获取保存上次账号文件路径（支持PyInstaller打包后）"""
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "last_username.json")

    def _load_last_username(self) -> str:
        """加载上次登录的账号"""
        path = self._get_username_file()
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("username", "")
        except Exception:
            return ""

    def _save_last_username(self, username: str):
        """保存上次登录的账号"""
        path = self._get_username_file()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"username": username}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _build_ui(self):
        COLORS, FONT, _, _ = _get_gui_resources()

        # 容器（居中布局）
        container = tk.Frame(self.dialog, bg=COLORS["card_bg"], padx=36, pady=24)
        container.pack(fill=tk.BOTH, expand=True)

        # 图标 + 标题（居中）
        icon_frame = tk.Frame(container, bg=COLORS["card_bg"])
        icon_frame.pack(pady=(0, 6))
        tk.Label(
            icon_frame, text="🔒",
            font=(FONT, 28), bg=COLORS["accent_light"], fg=COLORS["accent"],
            padx=14, pady=10,
        ).pack()

        tk.Label(
            container, text="登录方果ERP",
            font=(FONT, 16, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
        ).pack(pady=(0, 4))

        tk.Label(
            container, text="请输入您的账号信息",
            font=(FONT, 9), bg=COLORS["card_bg"], fg=COLORS["label_fg"],
        ).pack(pady=(0, 20))

        # 账号
        self.username_var = tk.StringVar()
        last_username = self._load_last_username()
        if last_username:
            self.username_var.set(last_username)
        self.username_entry = tk.Entry(
            container, textvariable=self.username_var,
            font=(FONT, 12), bg="#f8fafc",
            relief=tk.SOLID, bd=1,
        )
        self.username_entry.pack(fill=tk.X, pady=(0, 12), ipady=6)

        # 密码
        self.password_var = tk.StringVar()
        password_entry = tk.Entry(
            container, textvariable=self.password_var,
            font=(FONT, 12), bg="#f8fafc",
            show="*", relief=tk.SOLID, bd=1,
        )
        password_entry.pack(fill=tk.X, pady=(0, 20), ipady=6)
        password_entry.bind("<Return>", lambda e: self._do_login())

        # 状态标签
        self.status_label = tk.Label(
            container, text="",
            font=(FONT, 10), bg=COLORS["card_bg"], fg=COLORS["danger"],
        )
        self.status_label.pack(anchor="w", pady=(0, 12))

        # 登录按钮（全宽）
        self.login_btn = tk.Button(
            container, text="登录", font=(FONT, 13, "bold"),
            bg=COLORS["accent"], fg="#ffffff",
            command=self._do_login, padx=24, pady=10,
            relief=tk.FLAT, bd=0, cursor="hand2",
        )
        self.login_btn.pack(fill=tk.X, pady=(0, 12))

        # 取消链接
        tk.Button(
            container, text="取消", font=(FONT, 10),
            bg=COLORS["card_bg"], fg=COLORS["label_fg"],
            padx=16, pady=4, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self.dialog.destroy,
        ).pack()

    def _do_login(self):
        COLORS, FONT, _, _ = _get_gui_resources()
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username:
            self.status_label.config(text="请输入手机号")
            return
        if not password:
            self.status_label.config(text="请输入密码")
            return

        # 禁用按钮，显示加载中
        self.login_btn.config(state=tk.DISABLED, text="登录中...", bg="#9ca3af")
        self.status_label.config(text="正在登录...", fg=COLORS["info"])
        self.dialog.update()

        # 在后台线程执行登录
        def _do():
            try:
                result = auto_login(username, password)
                self.dialog.after(0, self._login_callback, result)
            except Exception as e:
                self.dialog.after(0, self._error_callback, str(e))

        threading.Thread(target=_do, daemon=True).start()

    def _login_callback(self, result):
        COLORS, _, _, _ = _get_gui_resources()
        self.login_btn.config(state=tk.NORMAL, text="登录", bg=COLORS["accent"])

        if result.success:
            self._save_last_username(self.username_var.get().strip())
            self.status_label.config(
                text=f"✅ {result.msg}（{result.main_username}）",
                fg=COLORS["success"],
            )
            self.dialog.update()
            self.dialog.after(800, self._close_success)
        else:
            self.status_label.config(text=f"❌ {result.msg}", fg=COLORS["danger"])

    def _error_callback(self, error_msg):
        COLORS, _, _, _ = _get_gui_resources()
        self.login_btn.config(state=tk.NORMAL, text="登录", bg=COLORS["accent"])
        self.status_label.config(text=f"❌ 登录异常: {error_msg}", fg=COLORS["danger"])

    def _close_success(self):
        auth = load_auth()
        self.dialog.destroy()
        if self.on_success:
            self.on_success(auth)


# ================================================================
#  快递配置弹窗
# ================================================================

class ExpressConfigDialog:
    """快递配置弹窗：省份映射、备注关键词、快递公司管理"""

    def __init__(self, parent):
        self.parent = parent
        self.mgr = get_express_manager()

        COLORS, FONT, _center_toplevel, _ = _get_gui_resources()

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("快递配置")
        self.dialog.geometry("720x560")
        self.dialog.resizable(False, False)
        self.dialog.configure(bg=COLORS["card_bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()
        _center_toplevel(self.dialog, self.parent, 720, 560)
        self._build_ui()

    def _build_ui(self):
        COLORS, FONT, _, _build_treeview = _get_gui_resources()

        container = tk.Frame(self.dialog, bg=COLORS["card_bg"], padx=20, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            container, text="快递规则配置",
            font=(FONT, 16, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
        ).pack(anchor="w", pady=(0, 12))

        # Notebook
        notebook = ttk.Notebook(container)
        notebook.pack(fill=tk.BOTH, expand=True)

        self._build_province_tab(notebook)
        self._build_keyword_tab(notebook)
        self._build_express_tab(notebook)
        self._build_store_tab(notebook)

        # 底部按钮
        btn_frame = tk.Frame(container, bg=COLORS["card_bg"])
        btn_frame.pack(fill=tk.X, pady=(14, 0))

        tk.Button(
            btn_frame, text="恢复默认", font=(FONT, 11),
            bg=COLORS["danger_bg"], fg=COLORS["danger"],
            padx=14, pady=5, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._reset_default,
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_frame, text="关闭", font=(FONT, 11, "bold"),
            bg=COLORS["accent"], fg="#ffffff",
            padx=24, pady=5, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self.dialog.destroy,
        ).pack(side=tk.RIGHT)

    # ── 省份映射标签页 ──────────────────────────────────────

    def _build_province_tab(self, notebook):
        COLORS, FONT, _, _build_treeview = _get_gui_resources()
        frame = tk.Frame(notebook, bg=COLORS["card_bg"])
        notebook.add(frame, text="省份映射")

        info = tk.Label(
            frame, text="  双击表格中的省份可修改快递；备注关键词优先级高于省份映射。",
            font=(FONT, 9), bg=COLORS["info_bg"], fg=COLORS["info"],
            padx=10, pady=6,
        )
        info.pack(fill=tk.X, pady=(8, 6))

        tree = _build_treeview(
            frame, ("province", "express"),
            headings={"province": "省份", "express": "快递"},
            widths={"province": 200, "express": 200},
            height=16, pack_side=tk.LEFT,
        )

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)

        self.province_tree = tree
        self._refresh_province_tree()

        tree.bind("<Double-1>", self._on_province_double_click)

    def _refresh_province_tree(self):
        for item in self.province_tree.get_children():
            self.province_tree.delete(item)
        for prov, expr in sorted(self.mgr.province_map.items()):
            self.province_tree.insert("", tk.END, values=(prov, expr))

    def _on_province_double_click(self, event):
        COLORS, FONT, _center_toplevel, _ = _get_gui_resources()
        row = self.province_tree.identify_row(event.y)
        if not row:
            return
        prov, curr = self.province_tree.item(row, "values")

        win = tk.Toplevel(self.dialog)
        win.title(f"修改 {prov}")
        win.configure(bg=COLORS["card_bg"])
        win.transient(self.dialog)
        win.grab_set()
        _center_toplevel(win, self.dialog, 280, 140)

        tk.Label(win, text=f"省份：{prov}", font=(FONT, 11),
                 bg=COLORS["card_bg"], fg=COLORS["header_fg"]).pack(pady=(12, 8))

        var = tk.StringVar(value=curr)
        combo = ttk.Combobox(win, textvariable=var,
                             values=self.mgr.all_express_names, state="readonly", width=18)
        combo.pack(pady=4)

        def _save():
            self.mgr.set_province_express(prov, var.get())
            self.mgr.save()
            self._refresh_province_tree()
            win.destroy()

        tk.Button(win, text="保存", font=(FONT, 11, "bold"),
                  bg=COLORS["accent"], fg="#ffffff",
                  padx=16, pady=4, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_save).pack(pady=(12, 0))

    # ── 备注关键词标签页 ────────────────────────────────────

    def _build_keyword_tab(self, notebook):
        COLORS, FONT, _, _build_treeview = _get_gui_resources()
        frame = tk.Frame(notebook, bg=COLORS["card_bg"])
        notebook.add(frame, text="备注关键词")

        info = tk.Label(
            frame, text="  若备注中包含以下关键词，将优先按关键词指定的快递发货。",
            font=(FONT, 9), bg=COLORS["info_bg"], fg=COLORS["info"],
            padx=10, pady=6,
        )
        info.pack(fill=tk.X, pady=(8, 6))

        tree = _build_treeview(
            frame, ("keyword", "express"),
            headings={"keyword": "关键词", "express": "快递"},
            widths={"keyword": 280, "express": 200},
            height=10, pack_side=tk.TOP,
        )

        self.keyword_tree = tree
        self._refresh_keyword_tree()

        ctrl = tk.Frame(frame, bg=COLORS["card_bg"])
        ctrl.pack(fill=tk.X, pady=(10, 0))

        tk.Label(ctrl, text="关键词：", font=(FONT, 10),
                 bg=COLORS["card_bg"], fg=COLORS["label_fg"]).pack(side=tk.LEFT)
        kw_var = tk.StringVar()
        tk.Entry(ctrl, textvariable=kw_var, font=(FONT, 10), width=16).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(ctrl, text="快递：", font=(FONT, 10),
                 bg=COLORS["card_bg"], fg=COLORS["label_fg"]).pack(side=tk.LEFT)
        expr_var = tk.StringVar()
        combo = ttk.Combobox(ctrl, textvariable=expr_var,
                             values=self.mgr.all_express_names, state="readonly", width=12)
        combo.pack(side=tk.LEFT, padx=(0, 8))

        def _add():
            k = kw_var.get().strip()
            e = expr_var.get()
            if not k or not e:
                messagebox.showwarning("提示", "请输入关键词并选择快递", parent=self.dialog)
                return
            self.mgr.add_keyword(k, e)
            self.mgr.save()
            self._refresh_keyword_tree()
            kw_var.set("")

        tk.Button(ctrl, text="添加", font=(FONT, 10, "bold"),
                  bg=COLORS["success"], fg="#ffffff",
                  padx=12, pady=3, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_add).pack(side=tk.LEFT, padx=(0, 8))

        def _remove():
            sel = tree.selection()
            if not sel:
                return
            kw, _ = tree.item(sel[0], "values")
            if messagebox.askyesno("确认删除", f"删除关键词 '{kw}'？", parent=self.dialog):
                self.mgr.remove_keyword(kw)
                self.mgr.save()
                self._refresh_keyword_tree()

        tk.Button(ctrl, text="删除选中", font=(FONT, 10),
                  bg=COLORS["danger_bg"], fg=COLORS["danger"],
                  padx=12, pady=3, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_remove).pack(side=tk.LEFT)

    def _refresh_keyword_tree(self):
        for item in self.keyword_tree.get_children():
            self.keyword_tree.delete(item)
        for kw, expr in sorted(self.mgr.keyword_map.items()):
            self.keyword_tree.insert("", tk.END, values=(kw, expr))

    # ── 快递公司标签页 ──────────────────────────────────────

    def _build_express_tab(self, notebook):
        COLORS, FONT, _, _build_treeview = _get_gui_resources()
        frame = tk.Frame(notebook, bg=COLORS["card_bg"])
        notebook.add(frame, text="快递公司")

        info = tk.Label(
            frame, text="  管理快递公司名称与API编码对应关系。默认快递公司不可删除。",
            font=(FONT, 9), bg=COLORS["info_bg"], fg=COLORS["info"],
            padx=10, pady=6,
        )
        info.pack(fill=tk.X, pady=(8, 6))

        tree = _build_treeview(
            frame, ("name", "code"),
            headings={"name": "名称", "code": "API编码"},
            widths={"name": 280, "code": 200},
            height=10, pack_side=tk.TOP,
        )

        self.express_tree = tree
        self._refresh_express_tree()

        ctrl = tk.Frame(frame, bg=COLORS["card_bg"])
        ctrl.pack(fill=tk.X, pady=(10, 0))

        tk.Label(ctrl, text="名称：", font=(FONT, 10),
                 bg=COLORS["card_bg"], fg=COLORS["label_fg"]).pack(side=tk.LEFT)
        name_var = tk.StringVar()
        tk.Entry(ctrl, textvariable=name_var, font=(FONT, 10), width=12).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(ctrl, text="编码：", font=(FONT, 10),
                 bg=COLORS["card_bg"], fg=COLORS["label_fg"]).pack(side=tk.LEFT)
        code_var = tk.StringVar()
        tk.Entry(ctrl, textvariable=code_var, font=(FONT, 10), width=12).pack(side=tk.LEFT, padx=(0, 8))

        def _add():
            n = name_var.get().strip()
            c = code_var.get().strip().upper()
            if not n or not c:
                messagebox.showwarning("提示", "请输入名称和编码", parent=self.dialog)
                return
            self.mgr.add_express(n, c)
            self.mgr.save()
            self._refresh_express_tree()
            self._refresh_province_tree()
            self._refresh_keyword_tree()
            name_var.set("")
            code_var.set("")

        tk.Button(ctrl, text="添加", font=(FONT, 10, "bold"),
                  bg=COLORS["success"], fg="#ffffff",
                  padx=12, pady=3, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_add).pack(side=tk.LEFT, padx=(0, 8))

        def _remove():
            sel = tree.selection()
            if not sel:
                return
            name, _ = tree.item(sel[0], "values")
            if not messagebox.askyesno("确认删除", f"删除快递公司 '{name}'？\n引用该快递的映射也会被重置。", parent=self.dialog):
                return
            ok = self.mgr.remove_express(name)
            if not ok:
                messagebox.showwarning("提示", f"'{name}' 是默认快递公司，不可删除。", parent=self.dialog)
                return
            self.mgr.save()
            self._refresh_express_tree()
            self._refresh_province_tree()
            self._refresh_keyword_tree()

        tk.Button(ctrl, text="删除选中", font=(FONT, 10),
                  bg=COLORS["danger_bg"], fg=COLORS["danger"],
                  padx=12, pady=3, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_remove).pack(side=tk.LEFT)

    def _refresh_express_tree(self):
        for item in self.express_tree.get_children():
            self.express_tree.delete(item)
        for name, code in sorted(self.mgr.express_codes.items()):
            self.express_tree.insert("", tk.END, values=(name, code))

    # ── 店铺/平台映射标签页 ────────────────────────────────

    def _build_store_tab(self, notebook):
        COLORS, FONT, _, _build_treeview = _get_gui_resources()
        frame = tk.Frame(notebook, bg=COLORS["card_bg"])
        notebook.add(frame, text="店铺映射")

        info = tk.Label(
            frame,
            text="  优先级：备注 > 店铺 > 平台 > 省份。双击表格行可修改快递。",
            font=(FONT, 9), bg=COLORS["info_bg"], fg=COLORS["info"],
            padx=10, pady=6,
        )
        info.pack(fill=tk.X, pady=(8, 6))

        # ── 平台映射区 ──
        tk.Label(
            frame, text="平台 → 快递（对该平台下所有店铺生效）",
            font=(FONT, 10, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
        ).pack(anchor="w", pady=(4, 2))

        platform_frame = tk.Frame(frame, bg=COLORS["card_bg"])
        platform_frame.pack(fill=tk.X, pady=(0, 8))

        self.platform_tree = _build_treeview(
            platform_frame, ("platform", "express"),
            headings={"platform": "平台", "express": "快递"},
            widths={"platform": 200, "express": 200},
            height=5, pack_side=tk.LEFT,
        )
        self.platform_tree.bind("<Double-1>", self._on_platform_double_click)
        self._refresh_platform_tree()

        platform_ctrl = tk.Frame(frame, bg=COLORS["card_bg"])
        platform_ctrl.pack(fill=tk.X, pady=(0, 12))

        tk.Label(platform_ctrl, text="平台：", font=(FONT, 10),
                 bg=COLORS["card_bg"], fg=COLORS["label_fg"]).pack(side=tk.LEFT)
        self._platform_name_var = tk.StringVar()
        tk.Entry(platform_ctrl, textvariable=self._platform_name_var,
                 font=(FONT, 10), width=12).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(platform_ctrl, text="快递：", font=(FONT, 10),
                 bg=COLORS["card_bg"], fg=COLORS["label_fg"]).pack(side=tk.LEFT)
        self._platform_expr_var = tk.StringVar()
        ttk.Combobox(platform_ctrl, textvariable=self._platform_expr_var,
                     values=self.mgr.all_express_names, state="readonly",
                     width=12).pack(side=tk.LEFT, padx=(0, 8))

        def _add_platform():
            p = self._platform_name_var.get().strip()
            e = self._platform_expr_var.get()
            if not p or not e:
                messagebox.showwarning("提示", "请输入平台名并选择快递", parent=self.dialog)
                return
            self.mgr.set_platform_express(p, e)
            self.mgr.save()
            self._refresh_platform_tree()
            self._platform_name_var.set("")

        tk.Button(platform_ctrl, text="添加", font=(FONT, 10, "bold"),
                  bg=COLORS["success"], fg="#ffffff",
                  padx=12, pady=3, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_add_platform).pack(side=tk.LEFT, padx=(0, 8))

        def _remove_platform():
            sel = self.platform_tree.selection()
            if not sel:
                return
            p, _ = self.platform_tree.item(sel[0], "values")
            if messagebox.askyesno("确认删除", f"删除平台 '{p}' 的快递配置？", parent=self.dialog):
                self.mgr.remove_platform_express(p)
                self.mgr.save()
                self._refresh_platform_tree()

        tk.Button(platform_ctrl, text="删除选中", font=(FONT, 10),
                  bg=COLORS["danger_bg"], fg=COLORS["danger"],
                  padx=12, pady=3, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_remove_platform).pack(side=tk.LEFT)

        # ── 分隔线 ──
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # ── 店铺映射区 ──
        shop_header = tk.Frame(frame, bg=COLORS["card_bg"])
        shop_header.pack(fill=tk.X)

        tk.Label(
            shop_header, text="店铺 → 快递（精确到单个店铺）",
            font=(FONT, 10, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
        ).pack(side=tk.LEFT)

        def _refresh_stores():
            """从 ERP 拉取最新店铺列表"""
            try:
                from adapters.fangguo import FangguoAdapter
                adapter = FangguoAdapter()
                shops = adapter.get_store_list()
                if shops:
                    messagebox.showinfo(
                        "刷新成功", f"已获取 {len(shops)} 家店铺",
                        parent=self.dialog,
                    )
                    self._refresh_store_tree()
                else:
                    messagebox.showwarning(
                        "刷新失败", "未获取到店铺数据，请检查登录状态",
                        parent=self.dialog,
                    )
            except Exception as e:
                messagebox.showerror(
                    "刷新异常", f"拉取店铺列表失败：{e}",
                    parent=self.dialog,
                )

        tk.Button(
            shop_header, text="刷新店铺列表", font=(FONT, 9),
            bg=COLORS["info"], fg="#ffffff",
            padx=10, pady=2, relief=tk.FLAT, bd=0,
            cursor="hand2", command=_refresh_stores,
        ).pack(side=tk.RIGHT)

        store_frame = tk.Frame(frame, bg=COLORS["card_bg"])
        store_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.store_tree = _build_treeview(
            store_frame, ("platform", "store", "express"),
            headings={"platform": "平台", "store": "店铺", "express": "快递"},
            widths={"platform": 100, "store": 240, "express": 140},
            height=10, pack_side=tk.LEFT,
        )
        store_scrollbar = ttk.Scrollbar(store_frame, orient=tk.VERTICAL, command=self.store_tree.yview)
        store_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.store_tree.configure(yscrollcommand=store_scrollbar.set)

        self.store_tree.bind("<Double-1>", self._on_store_double_click)
        self._refresh_store_tree()

    def _refresh_platform_tree(self):
        for item in self.platform_tree.get_children():
            self.platform_tree.delete(item)
        for platform, expr in sorted(self.mgr.platform_map.items()):
            self.platform_tree.insert("", tk.END, values=(platform, expr))

    def _refresh_store_tree(self):
        """刷新店铺映射表格：显示所有已知店铺及其快递配置"""
        for item in self.store_tree.get_children():
            self.store_tree.delete(item)

        from _app_path import get_app_dir
        cache_file = get_app_dir() / "shop_cache.json"
        shops: list[dict] = []
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    shops = json.load(f)
            except Exception:
                pass

        store_map = self.mgr.store_map
        for shop in sorted(shops, key=lambda s: (s.get("platform_name", ""), s.get("shop_name", ""))):
            shop_name = shop.get("shop_name", "")
            platform_name = shop.get("platform_name", "")
            express = store_map.get(shop_name, "（未设置）")
            self.store_tree.insert("", tk.END, values=(platform_name, shop_name, express))

    def _on_platform_double_click(self, event):
        COLORS, FONT, _center_toplevel, _ = _get_gui_resources()
        row = self.platform_tree.identify_row(event.y)
        if not row:
            return
        platform, curr = self.platform_tree.item(row, "values")

        win = tk.Toplevel(self.dialog)
        win.title(f"修改 {platform} 的快递")
        win.configure(bg=COLORS["card_bg"])
        win.transient(self.dialog)
        win.grab_set()
        _center_toplevel(win, self.dialog, 280, 140)

        tk.Label(win, text=f"平台：{platform}", font=(FONT, 11),
                 bg=COLORS["card_bg"], fg=COLORS["header_fg"]).pack(pady=(12, 8))

        var = tk.StringVar(value=curr)
        combo = ttk.Combobox(win, textvariable=var,
                             values=self.mgr.all_express_names, state="readonly", width=18)
        combo.pack(pady=4)

        def _save():
            self.mgr.set_platform_express(platform, var.get())
            self.mgr.save()
            self._refresh_platform_tree()
            win.destroy()

        tk.Button(win, text="保存", font=(FONT, 11, "bold"),
                  bg=COLORS["accent"], fg="#ffffff",
                  padx=16, pady=4, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_save).pack(pady=(12, 0))

    def _on_store_double_click(self, event):
        COLORS, FONT, _center_toplevel, _ = _get_gui_resources()
        row = self.store_tree.identify_row(event.y)
        if not row:
            return
        _platform, store_name, curr = self.store_tree.item(row, "values")
        if curr == "（未设置）":
            curr = ""

        win = tk.Toplevel(self.dialog)
        win.title(f"修改 {store_name} 的快递")
        win.configure(bg=COLORS["card_bg"])
        win.transient(self.dialog)
        win.grab_set()
        _center_toplevel(win, self.dialog, 300, 160)

        tk.Label(win, text=f"店铺：{store_name}", font=(FONT, 11),
                 bg=COLORS["card_bg"], fg=COLORS["header_fg"]).pack(pady=(12, 4))
        tk.Label(win, text="留空表示不设置（将使用平台/省份规则）",
                 font=(FONT, 8), bg=COLORS["card_bg"], fg=COLORS["label_fg"]).pack(pady=(0, 4))

        var = tk.StringVar(value=curr)
        combo = ttk.Combobox(win, textvariable=var,
                             values=[""] + self.mgr.all_express_names, state="readonly", width=20)
        combo.pack(pady=4)

        def _save():
            val = var.get().strip()
            if val:
                self.mgr.set_store_express(store_name, val)
            else:
                self.mgr.remove_store_express(store_name)
            self.mgr.save()
            self._refresh_store_tree()
            win.destroy()

        tk.Button(win, text="保存", font=(FONT, 11, "bold"),
                  bg=COLORS["accent"], fg="#ffffff",
                  padx=16, pady=4, relief=tk.FLAT, bd=0,
                  cursor="hand2", command=_save).pack(pady=(12, 0))

    def _reset_default(self):
        if messagebox.askyesno("确认恢复", "确定恢复所有默认配置吗？自定义修改将全部丢失。", parent=self.dialog):
            self.mgr.reset_to_default()
            self._refresh_province_tree()
            self._refresh_keyword_tree()
            self._refresh_express_tree()
            self._refresh_platform_tree()
            self._refresh_store_tree()


# ================================================================
#  赠品配置弹窗
# ================================================================

class GiftConfigDialog:
    """赠品配置弹窗：管理赠品关键词、固定商品ID/SKUID和商家编码"""

    def __init__(self, parent):
        self.parent = parent
        self.mgr = get_gift_manager()

        COLORS, FONT, _center_toplevel, _ = _get_gui_resources()

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("赠品配置")
        self.dialog.geometry("860x640")
        self.dialog.resizable(True, True)
        self.dialog.configure(bg=COLORS["card_bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()
        _center_toplevel(self.dialog, parent, 860, 640)
        self._build_ui()

    def _build_ui(self):
        COLORS, FONT, _, _ = _get_gui_resources()

        container = tk.Frame(self.dialog, bg=COLORS["card_bg"], padx=20, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            container, text="赠品规则配置",
            font=(FONT, 16, "bold"),
            bg=COLORS["card_bg"], fg=COLORS["header_fg"],
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            container,
            text="  备注中出现关键词后，审单会按这里配置的商家编码、商品ID和SKUID创建或更新赠品行。",
            font=(FONT, 9), bg=COLORS["info_bg"], fg=COLORS["info"],
            padx=10, pady=6,
        ).pack(fill=tk.X, pady=(0, 8))

        cols = ("name", "title", "shop_sku", "goods_id", "sku_id", "aliases")
        self.tree = ttk.Treeview(container, columns=cols, show="headings", height=11)
        headings = {
            "name": "赠品名",
            "title": "商品标题",
            "shop_sku": "商家编码",
            "goods_id": "商品ID",
            "sku_id": "SKUID",
            "aliases": "关键词/别名",
        }
        widths = {
            "name": 70, "title": 130, "shop_sku": 230,
            "goods_id": 145, "sku_id": 130, "aliases": 210,
        }
        for col in cols:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True)

        self._refresh_tree()

        # 表单区域
        form_container = tk.Frame(container, bg=COLORS["card_bg"])
        form_container.pack(fill=tk.X, pady=(12, 0))

        self.form_canvas = tk.Canvas(form_container, bg=COLORS["card_bg"], highlightthickness=0, height=55)
        form_scrollbar = ttk.Scrollbar(form_container, orient=tk.HORIZONTAL, command=self.form_canvas.xview)
        self.form_scrollable = tk.Frame(self.form_canvas, bg=COLORS["card_bg"])

        self.form_scrollable.bind(
            "<Configure>",
            lambda e: self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all"))
        )
        self.form_canvas.create_window((0, 0), window=self.form_scrollable, anchor="nw")
        self.form_canvas.configure(xscrollcommand=form_scrollbar.set)

        self.form_canvas.pack(side=tk.TOP, fill=tk.X)
        form_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.name_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.shop_sku_var = tk.StringVar()
        self.goods_id_var = tk.StringVar()
        self.sku_id_var = tk.StringVar()
        self.aliases_var = tk.StringVar()

        self._form_entry(self.form_scrollable, "赠品名", self.name_var, 9, 0)
        self._form_entry(self.form_scrollable, "商品标题", self.title_var, 18, 1)
        self._form_entry(self.form_scrollable, "商家编码", self.shop_sku_var, 34, 2)
        self._form_entry(self.form_scrollable, "商品 ID", self.goods_id_var, 20, 3)
        self._form_entry(self.form_scrollable, "SKUID", self.sku_id_var, 20, 4)
        self._form_entry(self.form_scrollable, "关键词", self.aliases_var, 36, 5)

        btn_frame = tk.Frame(container, bg=COLORS["card_bg"])
        btn_frame.pack(fill=tk.X, pady=(14, 0))

        tk.Button(
            btn_frame, text="添加/更新", font=(FONT, 10, "bold"),
            bg=COLORS["success"], fg="#ffffff",
            padx=14, pady=5, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._add_or_update,
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_frame, text="删除选中", font=(FONT, 10),
            bg=COLORS["danger_bg"], fg=COLORS["danger"],
            padx=14, pady=5, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._remove_selected,
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_frame, text="恢复默认", font=(FONT, 10),
            bg=COLORS["warning_bg"], fg=COLORS["warning"],
            padx=14, pady=5, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._reset_default,
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_frame, text="关闭", font=(FONT, 11, "bold"),
            bg=COLORS["accent"], fg="#ffffff",
            padx=24, pady=5, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self.dialog.destroy,
        ).pack(side=tk.RIGHT)

        self.tree.bind("<Double-1>", self._load_selected)

    def _form_entry(self, parent, label, variable, width, column):
        COLORS, FONT, _, _ = _get_gui_resources()
        frame = tk.Frame(parent, bg=COLORS["card_bg"])
        frame.grid(row=0, column=column, sticky="w", padx=(0, 8))
        tk.Label(frame, text=label, font=(FONT, 9),
                 bg=COLORS["card_bg"], fg=COLORS["label_fg"]).pack(anchor="w")
        tk.Entry(frame, textvariable=variable, font=(FONT, 9), width=width).pack(anchor="w")

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for name, cfg in sorted(self.mgr.gifts.items()):
            aliases = "，".join(cfg.get("aliases", []))
            self.tree.insert("", tk.END, values=(
                name,
                cfg.get("title", ""),
                cfg.get("shop_sku", ""),
                cfg.get("goods_id", ""),
                cfg.get("sku_id", ""),
                aliases,
            ))

    def _load_selected(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        name, title, shop_sku, goods_id, sku_id, aliases = self.tree.item(sel[0], "values")
        self.name_var.set(name)
        self.title_var.set(title)
        self.shop_sku_var.set(shop_sku)
        self.goods_id_var.set(goods_id)
        self.sku_id_var.set(sku_id)
        self.aliases_var.set(aliases)

    def _add_or_update(self):
        name = self.name_var.get().strip()
        title = self.title_var.get().strip()
        shop_sku = self.shop_sku_var.get().strip()
        goods_id = self.goods_id_var.get().strip()
        sku_id = self.sku_id_var.get().strip()
        aliases_raw = self.aliases_var.get().strip()
        aliases = [a.strip() for a in re.split(r"[，,;；\n]+", aliases_raw) if a.strip()]

        if not name or not shop_sku or not goods_id or not sku_id:
            messagebox.showwarning("提示", "请填写赠品名、商家编码、商品ID、SKUID", parent=self.dialog)
            return
        if shop_sku.count("-") < 3:
            messagebox.showwarning("提示", "商家编码格式应为：材质-标准-规格-图案", parent=self.dialog)
            return

        self.mgr.add_gift(name, title or name, shop_sku, goods_id, sku_id, aliases)
        self.mgr.save()
        self._refresh_tree()
        print(f"🎁 赠品规则已保存：{name}")

    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("确认删除", f"删除赠品规则 '{name}'？", parent=self.dialog):
            return
        ok = self.mgr.remove_gift(name)
        if not ok:
            messagebox.showwarning("提示", "默认赠品规则不可删除，可通过添加/更新修改。", parent=self.dialog)
            return
        self.mgr.save()
        self._refresh_tree()

    def _reset_default(self):
        if messagebox.askyesno("确认恢复", "确定恢复默认赠品配置吗？自定义新增将全部丢失。", parent=self.dialog):
            self.mgr.reset_to_default()
            self._refresh_tree()
