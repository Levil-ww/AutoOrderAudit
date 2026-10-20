"""
公共工具函数（顶层模块，不依赖 core/ 以避免循环导入）
"""

import os
import sys
from pathlib import Path


def get_app_dir() -> Path:
    """获取应用程序数据目录。

    - 开发模式：项目根目录
    - 打包后：%APPDATA%/方果审单工具/（避免 JSON 文件散落在 exe 所在目录）
    """
    if getattr(sys, "frozen", False):
        app_dir = Path(os.environ.get("APPDATA", "~")) / "方果审单工具"
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir
    return Path(os.path.dirname(os.path.abspath(__file__)))
