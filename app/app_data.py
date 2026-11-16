# -*- coding: utf-8 -*-
"""
数据层：所有文件读写、多班级管理、配置备份与恢复、批量抽号落盘、历史归档删除。
=========================================================================
【关键约束】所有数据只保存在“软件所在目录”（exe 同级），
绝不写入注册表 / AppData / ProgramData，确保系统 C 盘还原后配置不丢失。

目录结构：
    随机抽号.exe
    ├── classes/<班级名>/          每个班级独立文件夹
    │   ├── config.json            主配置（模式、人数、防重设置、批量人数）
    │   ├── config.json.bak        上一次成功加载的配置备份
    │   ├── roster.txt             班级名单（高级模式，一行一个姓名）
    │   ├── long_term_exempt.json  长期屏蔽名单
    │   ├── short_term_exempt.json 短期屏蔽名单（含日期，每日自动解除）
    │   ├── anti_duplicate.json    防重冷却记录（含抽中时间戳）
    │   ├── history.json           抽号记录（永久追加）
    │   ├── current_round.json     本轮已抽名单（重置时清空，不影响历史）
    │   └── history.corrupt_*.json 历史损坏时的改名保留
    ├── exports/                   导出的记录文件
    ├── backups/                   整库备份 + 被删除记录的归档
    ├── template/template.txt      名单格式示例模板
    └── admin.json                 管理员密码（PBKDF2 摘要 + 盐，用户自设，见 security.py）

性能说明（本次更新）：
- 一次抽号对 history / current_round / anti_duplicate 三个文件只读写各一次，
  且不再逐次 fsync（原子替换已能防止写坏；config 仍强制落盘）；
- 名单/班级学生列表带内存缓存，文件改动或切换班级时失效；
- 摇号池一次快照取齐（学生、屏蔽、冷却），避免同一次刷新重复读盘。
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MODE_SIMPLE = "simple"      # 简易引导模式：只有号码
MODE_ADVANCED = "advanced"  # 高级引导模式：号码 + 学生姓名

TEMPLATE_CONTENT = "张三\n李四\n王五\n赵六\n孙七\n周八\n吴九\n郑十\n"

ANTI_DUP_MIN_HOURS = 1
ANTI_DUP_DEFAULT_HOURS = 24
ANTI_DUP_MAX_HOURS = 720

BATCH_DEFAULT = 3
BATCH_MIN = 1
BATCH_MAX = 200

_ILLEGAL_NAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | \
                  {f"COM{i}" for i in range(1, 10)} | \
                  {f"LPT{i}" for i in range(1, 10)}


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def safe_name(name: str) -> str:
    """把班级名清洗成安全、可作目录名的字符串。"""
    name = (name or "").strip()
    name = _ILLEGAL_NAME_CHARS.sub("", name)
    name = name.strip(". ")
    if name.upper() in _RESERVED_NAMES:
        name = "_" + name
    return name or "未命名班级"


def safe_filename(name: str) -> str:
    return _ILLEGAL_NAME_CHARS.sub("_", (name or "班级")).strip() or "班级"


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# JSON 工具：原子写入（os.replace），durable=True 时强制落盘
# ---------------------------------------------------------------------------

def json_read(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def json_write(path: Path, data: Any, durable: bool = False) -> bool:
    """原子写入：临时文件 + os.replace。durable 时 flush+fsync（配置类用）。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            if durable:
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _append_json_list(path: Path, entries: list[dict], durable: bool = False) -> bool:
    data = json_read(path, [])
    if not isinstance(data, list):
        data = []
    data.extend(entries)
    return json_write(path, data, durable=durable)


# ---------------------------------------------------------------------------
# 异步写盘 + 内存缓存
# ---------------------------------------------------------------------------
# 说明：Windows 上 os.replace 单次约 5~10ms（杀软/文件系统开销），一次抽号要写
# 三个文件，同步写会造成定格瞬间约 40ms 卡顿。这里把「序列化」留在 UI 线程
# （微秒级），把「落盘」交给单线程队列串行执行；读取走内存缓存，因此界面
# 永远读到最新数据，而定格动画不受磁盘影响。
# 退出（closeEvent / atexit）会强制 flush，正常关闭不丢数据。

_MEM: dict[str, list] = {}
_MEM_LOCK = threading.Lock()

# 待写队列按路径合并：同一文件在队列里只保留最新内容，连续抽号不会堆积 IO
_PEND: dict[str, tuple] = {}
_PEND_CV = threading.Condition()
_W_BUSY = False
_W_STOP = False
_W_STARTED = False
_W_LOCK = threading.Lock()
_W_THREAD: Optional[threading.Thread] = None


def _write_text_atomic(path: Path, text: str, durable: bool) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            if durable:
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        pass


def _writer_loop() -> None:
    global _W_BUSY
    while True:
        with _PEND_CV:
            while not _PEND and not _W_STOP:
                _PEND_CV.wait()
            if _W_STOP and not _PEND:
                return
            batch = list(_PEND.values())
            _PEND.clear()
            _W_BUSY = True
        for path, text, durable in batch:
            _write_text_atomic(path, text, durable)
        with _PEND_CV:
            _W_BUSY = False
            _PEND_CV.notify_all()


def _ensure_writer() -> None:
    global _W_STARTED, _W_THREAD
    if _W_STARTED:
        return
    with _W_LOCK:
        if _W_STARTED:
            return
        _W_THREAD = threading.Thread(target=_writer_loop, name="rp-writer", daemon=True)
        _W_THREAD.start()
        _W_STARTED = True


def flush(timeout: float = 5.0) -> None:
    """等待待写内容全部落盘（关闭软件、删除班级、自检模拟重启前调用）。"""
    if not _W_STARTED:
        return
    deadline = time.monotonic() + timeout
    with _PEND_CV:
        while (_PEND or _W_BUSY) and time.monotonic() < deadline:
            _PEND_CV.wait(0.02)


def _shutdown() -> None:
    global _W_STOP
    try:
        flush(3.0)
        with _PEND_CV:
            _W_STOP = True
            _PEND_CV.notify_all()
    except Exception:
        pass


atexit.register(_shutdown)


def _cache_get(path: Path) -> list:
    key = str(path)
    with _MEM_LOCK:
        if key in _MEM:
            return _MEM[key]
    data = json_read(path, [])
    if not isinstance(data, list):
        data = []
    with _MEM_LOCK:
        _MEM[key] = data
    return data


def _cache_set(path: Path, data: list, durable: bool = False) -> None:
    key = str(path)
    with _MEM_LOCK:
        _MEM[key] = data
    text = json.dumps(data, ensure_ascii=False, indent=2)
    _ensure_writer()
    with _PEND_CV:
        _PEND[key] = (path, text, durable)
        _PEND_CV.notify()


def _cache_drop(path: Path) -> None:
    with _MEM_LOCK:
        _MEM.pop(str(path), None)


def reset_cache() -> None:
    """清空内存缓存（自检模拟“重启软件”时使用）。"""
    with _MEM_LOCK:
        _MEM.clear()


# ---------------------------------------------------------------------------
# 单个班级的数据存取
# ---------------------------------------------------------------------------

class ClassStore:
    """一个班级的全部数据。每个班级 = classes/班级名/ 一个文件夹。"""

    def __init__(self, root: Path, name: str):
        self.name = name
        self.dir = root / name
        self.cfg_path = self.dir / "config.json"
        self.cfg_bak_path = self.dir / "config.json.bak"
        self.roster_path = self.dir / "roster.txt"
        self.long_path = self.dir / "long_term_exempt.json"
        self.short_path = self.dir / "short_term_exempt.json"
        self.anti_path = self.dir / "anti_duplicate.json"
        self.history_path = self.dir / "history.json"
        self.round_path = self.dir / "current_round.json"
        self.needs_setup = False
        self._roster_cache: Optional[list[str]] = None
        self._roster_stamp: Optional[tuple] = None

    # ---- 初始化 ----
    def ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        """软件根目录（classes 的上一级）。"""
        return self.dir.parent.parent

    # ---- 主配置 ----
    def default_config(self) -> dict:
        return {
            "name": self.name,
            "mode": MODE_SIMPLE,
            "total_count": 0,
            "anti_dup_enabled": True,
            "anti_dup_hours": ANTI_DUP_DEFAULT_HOURS,
            "batch_count": BATCH_DEFAULT,
            "created_at": now_iso(),
        }

    def load_config(self) -> dict:
        self.needs_setup = False
        cfg = json_read(self.cfg_path, None)
        if isinstance(cfg, dict) and cfg:
            return self._normalize_cfg(cfg)
        bak = json_read(self.cfg_bak_path, None)
        if isinstance(bak, dict) and bak:
            json_write(self.cfg_path, bak, durable=True)
            return self._normalize_cfg(bak)
        self.needs_setup = True
        return self.default_config()

    def _normalize_cfg(self, cfg: dict) -> dict:
        """补齐新版本新增的可选字段（不改动用户已有值）。"""
        cfg.setdefault("batch_count", BATCH_DEFAULT)
        cfg.setdefault("anti_dup_enabled", True)
        cfg.setdefault("anti_dup_hours", ANTI_DUP_DEFAULT_HOURS)
        return cfg

    def save_config(self, cfg: dict, durable: bool = True) -> bool:
        self.ensure_dir()
        ok = json_write(self.cfg_path, cfg, durable=durable)
        if ok:
            json_write(self.cfg_bak_path, cfg, durable=False)
        return ok

    def backup_config(self, cfg: dict) -> None:
        json_write(self.cfg_bak_path, cfg, durable=False)

    # ---- 名单（高级模式 roster.txt） ----
    def roster_read(self) -> list[str]:
        """读取名单；带 mtime 缓存，避免每次刷新都解析文件。"""
        try:
            st = self.roster_path.stat()
        except Exception:
            self._roster_cache = []
            self._roster_stamp = None
            return []
        stamp = (st.st_mtime_ns, st.st_size)
        if self._roster_cache is not None and self._roster_stamp == stamp:
            return list(self._roster_cache)
        try:
            raw_bytes = self.roster_path.read_bytes()
        except Exception:
            return []
        text = None
        for enc in ("utf-8-sig", "gbk", "utf-8"):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            return []
        names = [ln.strip() for ln in text.splitlines() if ln.strip()]
        self._roster_cache = names
        self._roster_stamp = stamp
        return list(names)

    def roster_write(self, lines: list[str]) -> bool:
        try:
            self.roster_path.parent.mkdir(parents=True, exist_ok=True)
            self.roster_path.write_text("\n".join(s.strip() for s in lines if s.strip()),
                                        encoding="utf-8")
            self._roster_cache = None
            self._roster_stamp = None
            return True
        except Exception:
            return False

    # ---- 学生列表 ----
    def get_students(self, cfg: dict) -> list[dict]:
        total = max(0, int(cfg.get("total_count", 0)))
        if cfg.get("mode") == MODE_ADVANCED:
            names = self.roster_read()
            if names:
                return [{"num": i + 1, "name": n} for i, n in enumerate(names)]
        return [{"num": i + 1, "name": ""} for i in range(total)]

    # ---- 屏蔽 ----
    def long_exempt(self) -> list[int]:
        data = _cache_get(self.long_path)
        return [int(x["num"]) for x in data if isinstance(x, dict) and "num" in x]

    def set_long_exempt(self, nums: list[int]) -> bool:
        _cache_set(self.long_path, [{"num": int(n)} for n in sorted(set(nums))], durable=True)
        return True

    def short_exempt(self) -> list[int]:
        """今天仍生效的短期屏蔽；顺带清理过期条目（仅在有变化时落盘）。"""
        data = _cache_get(self.short_path)
        today = today_str()
        valid = [d for d in data if isinstance(d, dict) and d.get("date") == today]
        if len(valid) != len(data):
            _cache_set(self.short_path, valid)
        return [int(d["num"]) for d in valid if "num" in d]

    def set_short_exempt(self, nums: list[int]) -> bool:
        today = today_str()
        _cache_set(self.short_path,
                   [{"num": int(n), "date": today} for n in sorted(set(nums))], durable=True)
        return True

    # ---- 防重冷却 ----
    def anti_records(self) -> list[dict]:
        return _cache_get(self.anti_path)

    def cooling_nums(self, cfg: dict) -> list[int]:
        """冷却中的号码；过期记录顺手裁剪（避免文件无限膨胀）。"""
        if not cfg.get("anti_dup_enabled", True):
            return []
        hours = float(cfg.get("anti_dup_hours", ANTI_DUP_DEFAULT_HOURS))
        now = time.time()
        records = self.anti_records()
        out, keep = [], []
        for r in records:
            if not isinstance(r, dict) or "num" not in r:
                continue
            t = float(r.get("drawn_at", 0))
            if now - t < hours * 3600:
                out.append(int(r["num"]))
                keep.append(r)
        if len(keep) != len(records):
            _cache_set(self.anti_path, keep)
        return out

    def record_cooling(self, num: int) -> None:
        recs = list(self.anti_records())
        recs.append({"num": int(num), "drawn_at": time.time(), "iso": now_iso()})
        _cache_set(self.anti_path, recs)

    # ---- 抽号落盘（单次 / 批量） ----
    def record_draws(self, draws: list[dict], mode: str, anti_dup: bool = True) -> None:
        """
        更新三处记录：history / current_round / anti_duplicate。
        内存即时生效（页面立刻可读），磁盘写入进入后台队列，定格动画零阻塞。
        anti_dup=False 时只写历史与本轮（不产生冷却记录）。
        """
        if not draws:
            return
        stamp = now_iso()
        t = time.time()
        hist = list(self.history())
        rnd = list(self.round_list())
        anti = list(self.anti_records()) if anti_dup else []
        for d in draws:
            num = int(d.get("num", 0))
            name = d.get("name", "") or ""
            hist.append({"time": stamp, "num": num, "name": name, "mode": mode})
            rnd.append({"num": num, "name": name, "time": stamp})
            if anti_dup:
                anti.append({"num": num, "drawn_at": t, "iso": stamp})
        _cache_set(self.history_path, hist)
        _cache_set(self.round_path, rnd)
        if anti_dup:
            _cache_set(self.anti_path, anti)

    def add_history(self, num: int, name: str, mode: str) -> None:
        """仅追加一条历史（兼容旧调用；抽号主路径请用 record_draws 批量写）。"""
        hist = list(self.history())
        hist.append({"time": now_iso(), "num": int(num), "name": name, "mode": mode})
        _cache_set(self.history_path, hist)

    def record_cooling_batch(self, nums: list[int]) -> None:
        stamp = now_iso()
        t = time.time()
        recs = list(self.anti_records())
        recs.extend({"num": int(n), "drawn_at": t, "iso": stamp} for n in nums)
        _cache_set(self.anti_path, recs)

    def reset_round(self) -> None:
        """清空防重冷却 + 本轮已抽（永久历史不受影响）。
        清空前自动归档到 backups/ 并追加操作日志——任何一次清空都可追溯、可恢复。"""
        rnd = _cache_get(self.round_path)
        anti = _cache_get(self.anti_path)
        self._archive_reset(rnd, anti)
        _cache_set(self.anti_path, [])
        _cache_set(self.round_path, [])

    def _archive_reset(self, rnd: list, anti: list) -> None:
        try:
            import traceback as _tb
            caller = "unknown"
            for fr in _tb.extract_stack()[-4:-1]:
                if "app_data" not in fr.filename:
                    caller = f"{os.path.basename(fr.filename)}:{fr.lineno} {fr.name}"
                    break
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak_dir = self.base_dir / "backups"
            bak_dir.mkdir(parents=True, exist_ok=True)
            bak = bak_dir / f"重置本轮_{safe_filename(self.name)}_{stamp}.json"
            payload = {
                "class": self.name,
                "reset_at": now_iso(),
                "caller": caller,
                "round_count": len(rnd),
                "anti_count": len(anti),
                "round": rnd,
                "anti": anti,
            }
            bak.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            with open(self.base_dir / "_actions.log", "a", encoding="utf-8") as f:
                f.write(f"{now_iso()} reset_round class={self.name} "
                        f"round={len(rnd)} anti={len(anti)} caller={caller}\n")
        except Exception:
            pass

    # ---- 抽号历史 ----
    def history(self) -> list[dict]:
        return _cache_get(self.history_path)

    def history_bounds(self) -> tuple[str, str] | None:
        h = self.history()
        if not h:
            return None
        times = sorted(str(r.get("time", "")) for r in h if r.get("time"))
        if not times:
            return None
        return times[0], times[-1]

    def count_history_range(self, start: str, end: str) -> int:
        """[start, end] 闭区间内的记录数（时间格式 YYYY-MM-DD HH:MM:SS）。"""
        return sum(1 for r in self.history() if start <= str(r.get("time", "")) <= end)

    def delete_history_range(self, start: str, end: str) -> tuple[int, Optional[Path]]:
        """
        删除时间段内的记录：先把被删记录整体归档到 backups/，再从 history.json 移除。
        返回 (删除条数, 归档文件路径)。归档失败则不删除（绝不静默销毁数据）。
        """
        records = self.history()
        keep, removed = [], []
        for r in records:
            t = str(r.get("time", ""))
            if start <= t <= end:
                removed.append(r)
            else:
                keep.append(r)
        if not removed:
            return 0, None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = self.base_dir / "backups" / \
            f"记录删除_{safe_filename(self.name)}_{stamp}.json"
        payload = {
            "class": self.name,
            "deleted_at": now_iso(),
            "range": {"start": start, "end": end},
            "count": len(removed),
            "records": removed,
        }
        ok = json_write(archive, payload, durable=True)
        if not ok:
            raise OSError("归档失败，已取消删除（未改动任何记录）")
        _cache_set(self.history_path, keep)
        return len(removed), archive

    # ---- 本轮 ----
    def round_list(self) -> list[dict]:
        return _cache_get(self.round_path)

    def append_round(self, num: int, name: str) -> None:
        rnd = list(self.round_list())
        rnd.append({"num": int(num), "name": name, "time": now_iso()})
        _cache_set(self.round_path, rnd)

    # ---- 摇号池快照 ----
    def pool_snapshot(self, cfg: dict) -> dict:
        """一次性取齐：学生、长期/短期屏蔽、冷却、可用池。"""
        students = self.get_students(cfg)
        long_set = set(self.long_exempt())
        short_set = set(self.short_exempt())
        cool_set = set(self.cooling_nums(cfg))
        pool = [s for s in students
                if s["num"] not in long_set
                and s["num"] not in short_set
                and s["num"] not in cool_set]
        return {
            "students": students,
            "pool": pool,
            "long": long_set,
            "short": short_set,
            "cool": cool_set,
            "total": len(students),
        }

    def draw_pool(self, cfg: dict) -> list[dict]:
        return self.pool_snapshot(cfg)["pool"]

    # ---- 统计 ----
    def stats(self) -> list[dict]:
        """
        按号码统计（高级模式显示姓名，重名不合并）。
        返回 [{"rank","display","count","pct"}]，次数降序、同次数按号码升序。
        """
        records = self.history()
        mode = self._mode_of(records)
        counter: dict[int, dict] = {}
        for r in records:
            if not isinstance(r, dict):
                continue
            try:
                num = int(r.get("num", 0))
            except (TypeError, ValueError):
                continue
            entry = counter.setdefault(num, {"num": num, "name": str(r.get("name", "") or ""),
                                             "count": 0})
            entry["count"] += 1
            if not entry["name"] and r.get("name"):
                entry["name"] = str(r["name"])
        total = sum(e["count"] for e in counter.values())
        items = sorted(counter.values(), key=lambda e: (-e["count"], e["num"]))
        out = []
        for i, e in enumerate(items):
            if mode == MODE_ADVANCED and e["name"]:
                display = e["name"]
            else:
                display = f"号码 {e['num']:02d}"
            out.append({"rank": i + 1, "display": display, "num": e["num"],
                        "count": e["count"],
                        "pct": round(e["count"] * 100.0 / total, 1) if total else 0.0})
        return out

    @staticmethod
    def _mode_of(records: list) -> str:
        for r in reversed(records):
            if isinstance(r, dict) and r.get("mode") in (MODE_SIMPLE, MODE_ADVANCED):
                return r["mode"]
        return MODE_SIMPLE

    # ---- 导出 ----
    def export_text(self) -> str:
        h = self.history()
        lines = ["=" * 60,
                 f"班级：{self.name}",
                 f"导出时间：{now_iso()}",
                 f"总记录数：{len(h)}条",
                 "=" * 60,
                 f"{'序号':<6}{'抽中号码':<10}{'学生姓名':<16}{'抽号时间':<22}{'模式'}",
                 "-" * 60]
        for i, r in enumerate(h, start=1):
            num = str(int(r.get("num", 0))).zfill(2)
            name = r.get("name", "") or "-"
            t = r.get("time", "")
            mode = "高级" if r.get("mode") == MODE_ADVANCED else "简易"
            lines.append(f"{str(i):<6}{num:<12}{name:<18}{t:<22}{mode}")
        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 班级管理器
# ---------------------------------------------------------------------------

class ClassManager:
    def __init__(self, base_dir: Optional[Path] = None):
        self.base = Path(base_dir) if base_dir else get_base_dir()
        self.classes_dir = self.base / "classes"
        self.exports_dir = self.base / "exports"
        self.backups_dir = self.base / "backups"
        self.template_dir = self.base / "template"

    def ensure_dirs(self) -> None:
        for d in (self.classes_dir, self.exports_dir, self.backups_dir, self.template_dir):
            d.mkdir(parents=True, exist_ok=True)

    def ensure_template(self) -> Path:
        p = self.template_dir / "template.txt"
        if not p.exists():
            try:
                p.write_text(TEMPLATE_CONTENT, encoding="utf-8")
            except Exception:
                pass
        return p

    def ensure_default_class(self) -> str:
        self.ensure_dirs()
        # 优先返回真正初始化过的班级：classes/ 里混进的无 config 目录
        # （backups/template 之类）不能顶替用户的班级。
        usable = self.usable_classes()
        if usable:
            return usable[0]
        names = self.list_classes()
        if not names:
            names = [self.create_class("默认班级")]
        return names[0]

    def list_classes(self) -> list[str]:
        if not self.classes_dir.exists():
            return []
        return sorted([d.name for d in self.classes_dir.iterdir() if d.is_dir()])

    def has_config(self, name: str) -> bool:
        """该班级目录是否带有 config.json（用来识别真正初始化的班级）。

        classes/ 下偶尔会混进 backups / exports / template 这类目录（手工
        操作、旧版本残留）。它们没有 config.json，按名字排序往往还排在
        真实班级前面，startup() 一旦选中就会弹「首次使用向导」——用户看到
        的却是自己原来的班级不见了。所以选班级时优先挑有 config 的。
        """
        try:
            return (self.classes_dir / name / "config.json").exists()
        except OSError:
            return False

    def usable_classes(self) -> list[str]:
        """有配置的班级（正常可用的那批）。"""
        return [n for n in self.list_classes() if self.has_config(n)]

    def create_class(self, name: str) -> str:
        self.ensure_dirs()
        name = safe_name(name)
        base, idx = name, 2
        while (self.classes_dir / name).exists():
            name = f"{base}({idx})"
            idx += 1
        store = ClassStore(self.classes_dir, name)
        store.ensure_dir()
        store.save_config(store.default_config())
        return name

    def rename_class(self, old: str, new: str) -> str:
        flush()
        new = safe_name(new)
        src = self.classes_dir / old
        dst = self.classes_dir / new
        if not src.exists():
            raise FileNotFoundError(f"班级不存在：{old}")
        if dst.exists():
            raise FileExistsError(f"班级名已存在：{new}")
        src.rename(dst)
        store = ClassStore(self.classes_dir, new)
        cfg = store.load_config()
        cfg["name"] = new
        store.save_config(cfg)
        return new

    def delete_class(self, name: str) -> None:
        """删除班级：先整体归档到 backups/；归档失败则中止（绝不静默销毁）。"""
        flush()
        src = self.classes_dir / name
        if not src.exists():
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = self.backups_dir / f"{safe_filename(name)}_{ts}"
        try:
            src.rename(dst)
            return
        except Exception:
            pass
        try:
            shutil.copytree(src, dst)
            shutil.rmtree(src, ignore_errors=True)
        except Exception as e:
            raise OSError(f"归档到 backups 失败：{e}")

    def get_class(self, name: str) -> ClassStore:
        return ClassStore(self.classes_dir, name)


# ---------------------------------------------------------------------------
# 启动巡检
# ---------------------------------------------------------------------------

def daily_maintenance(store: ClassStore) -> None:
    store.short_exempt()


def repair_history(store: ClassStore) -> None:
    _cache_drop(store.history_path)
    try:
        if not store.history_path.exists():
            return
        data = json_read(store.history_path, None)
        if isinstance(data, list):
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupt = store.history_path.with_name(f"history.corrupt_{ts}.json")
        store.history_path.rename(corrupt)
        _cache_drop(store.history_path)
    except Exception:
        pass
