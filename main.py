# -*- coding: utf-8 -*-
"""双击 / python main.py 启动入口（打包时作为 PyInstaller 入口脚本）。"""

import sys
import os
import traceback


def _early_hook(exc_type, exc_val, exc_tb):
    """app.main 导入阶段的崩溃也留证。"""
    try:
        base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "_crash.txt"), 'a', encoding='utf-8') as f:
            traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
    except Exception:
        pass


sys.excepthook = _early_hook

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
