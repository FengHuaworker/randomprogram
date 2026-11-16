# -*- coding: utf-8 -*-
"""
管理员密码校验（固定密码，编译进程序）。
=========================================================================
设计：
- 只保存「盐 + 摘要」常量，不保存明文；程序内不做任何写盘，
  因此换 exe 即可完成更新，不产生也不依赖任何新的数据文件。
- 校验用常数时间比较，避免时间侧信道（本地场景意义有限，但无成本）。
- 修改密码 = 改 ADMIN_HASH 后重新打包（源码里不留明文）。
"""

from __future__ import annotations

import hashlib
import hmac

_SALT = "lucky-draw::v1::"

# sha256(_SALT + 密码)：只存摘要，不存明文
ADMIN_HASH = "b21ebb53ca8cda497e6c58a98ad95f028f66694225a4421e49636e622fc15db2"


def _digest(password: str) -> str:
    return hashlib.sha256((_SALT + password).encode("utf-8")).hexdigest()


def verify(password: str) -> bool:
    """校验管理员密码（空密码一律拒绝）。"""
    if not password:
        return False
    return hmac.compare_digest(_digest(password), ADMIN_HASH)
