# -*- coding: utf-8 -*-
"""
管理员密码（用户自行设置，存于程序目录 admin.json）。
=========================================================================
设计：
- 不保存明文：PBKDF2-HMAC-SHA256 + 16 字节随机盐 + 200000 次迭代，只存盐与摘要。
- 文件位置：<程序目录>/admin.json（与 classes/ 同级），随程序目录整体拷贝迁移。
- 首次使用：没有 admin.json 时，由界面引导用户设置（见 ui_dialogs.AdminPasswordDialog）。
- 忘记密码：删除程序目录下的 admin.json 后重启，会重新引导设置。
- 校验用常数时间比较，避免时间侧信道（本地场景意义有限，但无成本）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

FILE_NAME = "admin.json"
_VERSION = 1
_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000
MIN_LEN = 4
MAX_LEN = 64


def path_of(base) -> Path:
    """密码文件路径（base = 程序根目录，即 classes/ 的上一级）。"""
    return Path(base) / FILE_NAME


def valid_password(password: str) -> bool:
    """长度合法且不是空白串。"""
    return bool(password) and MIN_LEN <= len(password) <= MAX_LEN and bool(password.strip())


def _derive(password: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations).hex()


def is_configured(base) -> bool:
    """是否已经设置过密码（文件存在且内容可用）。"""
    try:
        d = json.loads(path_of(base).read_text(encoding="utf-8"))
        return bool(d.get("salt")) and bool(d.get("hash"))
    except Exception:
        return False


def set_password(base, password: str) -> bool:
    """写入新密码（覆盖旧密码），原子落盘。"""
    if not valid_password(password):
        return False
    salt = secrets.token_bytes(16)
    payload = {
        "v": _VERSION,
        "algo": _ALGO,
        "iter": _ITERATIONS,
        "salt": salt.hex(),
        "hash": _derive(password, salt, _ITERATIONS),
    }
    p = path_of(base)
    tmp = p.with_name(p.name + ".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        return True
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass
        return False


def verify(base, password: str) -> bool:
    """校验密码（空值一律拒绝；未设置密码时也拒绝，需先 set_password）。"""
    if not password:
        return False
    try:
        d = json.loads(path_of(base).read_text(encoding="utf-8"))
        salt = bytes.fromhex(str(d["salt"]))
        iterations = int(d.get("iter", _ITERATIONS))
        expected = str(d["hash"])
    except Exception:
        return False
    return hmac.compare_digest(_derive(password, salt, iterations), expected)


def change_password(base, old: str, new: str) -> bool:
    """校验旧密码后写入新密码。"""
    return verify(base, old) and set_password(base, new)


def reset(base) -> bool:
    """删除密码文件（用于「忘记密码」）。"""
    try:
        path_of(base).unlink()
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False
