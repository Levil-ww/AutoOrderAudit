"""离线回归入口：隔离用户配置，禁止真实 ERP 请求。"""
import ast
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_runtime = TemporaryDirectory(prefix="autoorder-test-")
_patch = pytest.MonkeyPatch()
_active = True

class IsolationError(BaseException):
    """不能被业务异常处理吞掉的隔离错误。"""

def _audit(event, args):
    if not _active:
        return
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        if path.parent == ROOT and path.name.lower() in {
            "token.json", "last_username.json", "express_config.json", "gift_config.json", "shop_cache.json"
        }:
            raise IsolationError("测试禁止访问用户配置: " + path.name)
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo"}:
        raise IsolationError("测试禁止访问真实网络")

sys.addaudithook(_audit)

def _no_http(*args, **kwargs):
    raise IsolationError("请 mock HTTP 请求，禁止真实 ERP 访问")

_patch.setattr(requests.sessions.Session, "request", _no_http)
import auth_manager
_patch.setattr(auth_manager, "TOKEN_FILE", str(Path(_runtime.name) / "token.json"))
import express_config
_patch.setattr(express_config, "CONFIG_FILE", str(Path(_runtime.name) / "express_config.json"))
import _app_path
_patch.setattr(_app_path, "get_app_dir", lambda: Path(_runtime.name))
import express_manager
import gift_manager
_patch.setattr(express_manager, "_CONFIG_FILE", Path(_runtime.name) / "express_config.json")
_patch.setattr(gift_manager, "_CONFIG_FILE", Path(_runtime.name) / "gift_config.json")
from adapters.fangguo.material_source import FangguoMaterialSource
_material_fetch = FangguoMaterialSource.fetch
_patch.setattr(FangguoMaterialSource, "fetch", lambda self, *args, **kwargs: [])

def _automated(path):
    if path.name in {"test.py", "revert_order.py"}:
        return False
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return any(isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
               or isinstance(n, ast.ClassDef) and n.name.startswith("Test") for n in tree.body)

def pytest_ignore_collect(collection_path, config):
    if collection_path.suffix == ".py" and collection_path.name.startswith("test"):
        return not _automated(collection_path)

class _ManualModule(pytest.Module):
    def collect(self):
        pytest.skip("手工场景脚本未执行，不计为通过", allow_module_level=True)

def pytest_pycollect_makemodule(module_path, parent):
    if not _automated(module_path):
        return _ManualModule.from_parent(parent, path=module_path)

def pytest_unconfigure(config):
    global _active
    _active = False
    _patch.undo()
    _runtime.cleanup()


@pytest.fixture(autouse=True)
def _isolated_managers(monkeypatch, tmp_path):
    monkeypatch.setattr(express_manager, "_CONFIG_FILE", tmp_path / "express_config.json")
    monkeypatch.setattr(gift_manager, "_CONFIG_FILE", tmp_path / "gift_config.json")
    monkeypatch.setattr(express_manager.ExpressManager, "_instance", None)
    monkeypatch.setattr(gift_manager.GiftManager, "_instance", None)


def pytest_configure(config):
    if config.option.basetemp is None:
        config.option.basetemp = str(Path(_runtime.name) / "pytest")


@pytest.fixture
def real_material_fetch(monkeypatch):
    """材质专用测试恢复实际实现；请求仍须在用例中 mock。"""
    monkeypatch.setattr(FangguoMaterialSource, "fetch", _material_fetch)
