"""登录窗口应在布局完成后按内容高度居中，避免登录按钮被裁剪。"""
from unittest.mock import Mock

import pytest

from gui_dialogs import LoginDialog


@pytest.mark.parametrize("content_height", [440, 560])
def test_login_window_fits_content_before_centering(monkeypatch, content_height):
    import gui_dialogs
    window = Mock()
    window.winfo_reqwidth.return_value = 400
    window.winfo_reqheight.return_value = content_height
    built = []
    center = Mock()
    monkeypatch.setattr(gui_dialogs.tk, "Toplevel", lambda parent: window)
    monkeypatch.setattr(gui_dialogs, "_get_gui_resources", lambda: ({"card_bg": "white"}, "Arial", center, None))
    monkeypatch.setattr(LoginDialog, "_build_ui", lambda self: built.append(True))
    center.side_effect = lambda *args: built or pytest.fail("必须先完成布局再确定窗口尺寸")
    LoginDialog(Mock())
    width, height = center.call_args.args[2:]
    assert width >= 400
    assert height >= content_height, "登录按钮和取消操作不能被窗口底部裁剪"


def test_login_button_and_return_share_handler(monkeypatch):
    import gui
    import gui_dialogs

    username_entry, password_entry = Mock(), Mock()
    button_factory = Mock()
    for name in ("Frame", "Label", "StringVar"):
        monkeypatch.setattr(gui_dialogs.tk, name, Mock())
    monkeypatch.setattr(gui_dialogs.tk, "Entry", Mock(side_effect=[username_entry, password_entry]))
    monkeypatch.setattr(gui_dialogs.tk, "Button", button_factory)
    monkeypatch.setattr(gui_dialogs, "_get_gui_resources", lambda: (gui.COLORS, gui.FONT, None, None))
    monkeypatch.setattr(LoginDialog, "_load_last_username", lambda self: "")
    dialog = LoginDialog.__new__(LoginDialog)
    dialog.dialog = Mock()
    dialog._do_login = Mock()
    dialog._build_ui()

    login_options = next(call.kwargs for call in button_factory.call_args_list
                         if call.kwargs.get("text") == "登录")
    login_options["command"]()
    assert dialog._do_login.call_count == 1
    event, handler = password_entry.bind.call_args.args
    assert event == "<Return>"
    handler(Mock())
    assert dialog._do_login.call_count == 2
