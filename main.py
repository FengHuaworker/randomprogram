# -*- coding: utf-8 -*-
"""双击 / python main.py 启动入口（打包时作为 PyInstaller 入口脚本）。"""

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
