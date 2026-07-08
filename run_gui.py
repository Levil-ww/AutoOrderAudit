"""
方果ERP自动审单 - GUI启动入口
=============================
客服人员双击这个文件运行即可。
不需要了解任何代码，不需要F12抓包。
"""

import sys
import os

# 确保在当前目录运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from gui import main

if __name__ == "__main__":
    main()