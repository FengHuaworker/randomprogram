# -*- coding: utf-8 -*-
"""探针公共环境：把发布版数据**复制到临时目录**再交给 MainWindow。

两个坑都在这里统一解决：

1. ClassManager(base) 的 base 是「父目录」，班级实际在 <base>/classes。
   以前探针传的是 发布版/classes，于是程序在 发布版/classes/classes 里
   新建了一个空班级——截图全是空状态，还往发布目录里塞了垃圾。
2. 直接指向 发布版 会在真实数据上跑 daily_maintenance / 写 last_class，
   探针不该改动用户数据。所以一律用 temp 副本。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "发布版" / "classes"


def temp_classes(prefix: str = "rp_probe_") -> Path:
    """返回一个临时 base 目录，里面已经是发布版数据的副本。"""
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    if LIVE.exists():
        shutil.copytree(LIVE, tmp / "classes")
    else:
        (tmp / "classes").mkdir(parents=True)
    return tmp
