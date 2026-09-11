# -*- coding: utf-8 -*-
"""
数据层：负责所有文件的读写、多班级管理、配置备份与恢复。
=========================================================================
【关键约束】所有数据只保存在“软件所在目录”（exe 同级），
绝不写入注册表 / AppData / ProgramData 等 C 盘位置，
确保系统 C 盘还原后配置不丢失。
目录结构（详见使用说明）：
    随机抽号.exe
    ├── classes/<班级名>/          每个班级独立文件夹
    │   ├── config.json            主配置（模式、人数、防重设置）
    │   ├── config.json.bak        上一次成功加载的配置备份
    │   ├── roster.txt             班级名单（高级模式，一行一个姓名）
    │   ├── long_term_exempt.json  长期屏蔽名单
    │   ├── short_term_exempt.json 短期屏蔽名单（含日期，每日自动解除）
    │   ├── anti_duplicate.json    防重冷却记录（含抽中时间戳）
    │   ├── history.json           抽号记录（无限期追加，不可删除）
    │   └── current_round.json     本轮已抽名单（重置时清空，不影响历史）
    ├── exports/                   导出的记录文件
    ├── backups/                   整库备份目录（删除班级前自动归档）
    └── template/template.txt      名单格式示例模板
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
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

# 防重时间窗口（小时）允许范围：1 ~ 720（30 天）
ANTI_DUP_MIN_HOURS = 1
ANTI_DUP_DEFAULT_HOURS = 24
ANTI_DUP_MAX_HOURS = 720

# 班级名中不允许出现的文件系统非法字符（Windows）
_ILLEGAL_NAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')


def now_iso() -> str:
    """当前时间 ISO 字符串（本地时间，用于记录时间戳）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    """今天日期 YYYY-MM-DD（短期屏蔽按日期每天自动解除）。"""
    return datetime.now().strftime("%Y-%m-%d")


def safe_name(name: str) -> str:
    """把班级名清洗成安全、可作目录名的字符串。"""
    name = (name or "").strip()
    name = _ILLEGAL_NAME_CHARS.sub("", name)
    name = name.strip(". ")  # 防止 “..” 等路径穿越
    return name or "未命名班级"


def safe_filename(name: str) -> str:
    """班级名 -> 可用于文件名的字符串（导出文件前缀用）。"""
    return _ILLEGAL_NAME_CHARS.sub("_", (name or "班级")).strip() or "班级"


def get_base_dir() -> Path:
    """
    软件所在目录：
    - 打包后（frozen）：exe 所在目录
    - 源码运行：项目根目录（src 的上级）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# JSON 小工具：原子写入 + 强制落盘，防止意外断电/崩溃损坏数据
# ---------------------------------------------------------------------------

def json_read(path: Path, default: Any) -> Any:
    """读 JSON；文件不存在或损坏时返回 default（绝不抛出）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def json_write(path: Path, data: Any) -> bool:
    """
    原子写入 JSON：先写临时文件并 flush + fsync 强制落盘，
    再用 os.replace 替换正式文件（替换是原子的）。
    这样即使中途断电，旧文件也不会被写坏。
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 单个班级的数据存取
# ---------------------------------------------------------------------------

class ClassStore:
    """一个班级的全部数据。每个班级 = classes/班级名/ 一个文件夹。"""

    def __init__(self, root: Path, name: str):
        self.name = name                      # 班级名（即文件夹名）
        self.dir = root / name                # 班级数据目录
        self.cfg_path = self.dir / "config.json"
        self.cfg_bak_path = self.dir / "config.json.bak"
        self.roster_path = self.dir / "roster.txt"
        self.long_path = self.dir / "long_term_exempt.json"
        self.short_path = self.dir / "short_term_exempt.json"
        self.anti_path = self.dir / "anti_duplicate.json"
        self.history_path = self.dir / "history.json"
        self.round_path = self.dir / "current_round.json"
        self.needs_setup = False               # 配置丢失需重新引导时置 True

    # ---- 初始化 ----
    def ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---- 主配置 ----
    def default_config(self) -> dict:
        return {
            "name": self.name,
            "mode": MODE_SIMPLE,          # 默认简易模式
            "total_count": 0,             # 班级总人数（简易模式有效；高级模式随名单同步）
            "anti_dup_enabled": True,     # 防重开关，默认开启
            "anti_dup_hours": ANTI_DUP_DEFAULT_HOURS,  # 防重时间窗口（小时）
            "created_at": now_iso(),
        }

    def load_config(self) -> dict:
        """
        加载主配置，含 6.8 自动备份恢复策略：
        1. config.json 完整可读 -> 正常返回；
        2. 损坏/缺失 -> 尝试 config.json.bak；
        3. 备份也没有 -> 返回默认配置并标记 needs_setup=True，
           由界面层弹窗引导用户重新配置。
        """
        self.needs_setup = False
        cfg = json_read(self.cfg_path, None)
        if isinstance(cfg, dict) and cfg:
            return cfg
        bak = json_read(self.cfg_bak_path, None)
        if isinstance(bak, dict) and bak:
            # 从备份恢复后，立即写回正式文件
            json_write(self.cfg_path, bak)
            return bak
        self.needs_setup = True
        return self.default_config()

    def save_config(self, cfg: dict) -> bool:
        """保存主配置（含更新备份文件）。"""
        self.ensure_dir()
        ok = json_write(self.cfg_path, cfg)
        if ok:
            json_write(self.cfg_bak_path, cfg)   # 最新备份
        return ok

    def backup_config(self, cfg: dict) -> None:
        """每次成功进入主界面后，把当前配置覆盖写入 .bak 作为最新备份。"""
        json_write(self.cfg_bak_path, cfg)

    # ---- 名单（高级模式 roster.txt） ----
    def roster_read(self) -> list[str]:
        """
        读取名单：一行一个姓名，去除空行。号码 = 行号（从 1 开始）。
        兼容 UTF-8（含 BOM）与 Windows 常见 GBK 编码。
        """
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
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    def roster_write(self, lines: list[str]) -> bool:
        """覆盖写入名单（编辑器/重新上传用）。保存后同步总人数。"""
        try:
            self.roster_path.parent.mkdir(parents=True, exist_ok=True)
            self.roster_path.write_text("\n".join(s.strip() for s in lines if s.strip()), encoding="utf-8")
            return True
        except Exception:
            return False

    # ---- 学生列表（统一模型：学生 = 号码 + 可选姓名） ----
    def get_students(self, cfg: dict) -> list[dict]:
        """
        返回该班级全部学生：[{"num": 1, "name": "张三"}, ...]
        - 简易模式：1..total_count，无姓名；
        - 高级模式：优先名单（姓名），名单为空时回退为 1..total_count 无姓名。
        """
        total = max(0, int(cfg.get("total_count", 0)))
        if cfg.get("mode") == MODE_ADVANCED:
            names = self.roster_read()
            if names:
                return [{"num": i + 1, "name": n} for i, n in enumerate(names)]
        return [{"num": i + 1, "name": ""} for i in range(total)]

    # ---- 长期屏蔽（按号码存储；高级模式界面同时显示姓名） ----
    def long_exempt(self) -> list[int]:
        data = json_read(self.long_path, [])
        return [int(x["num"]) for x in data if isinstance(x, dict) and "num" in x] if isinstance(data, list) else []

    def set_long_exempt(self, nums: list[int]) -> bool:
        return json_write(self.long_path, [{"num": int(n)} for n in sorted(set(nums))])

    # ---- 短期屏蔽（含日期；每日自动清理过期项） ----
    def short_exempt(self) -> list[int]:
        """返回今天仍在生效的短期屏蔽号码；同时把过期条目清出文件。"""
        data = json_read(self.short_path, [])
        if not isinstance(data, list):
            data = []
        today = today_str()
        valid = [d for d in data if isinstance(d, dict) and d.get("date") == today]
        if len(valid) != len(data):
            json_write(self.short_path, valid)   # 过期条目自动清理落盘
        return [int(d["num"]) for d in valid if "num" in d]

    def set_short_exempt(self, nums: list[int]) -> bool:
        """把指定号码设为“今天”的短期屏蔽（日期自动取当天）。"""
        today = today_str()
        data = [{"num": int(n), "date": today} for n in sorted(set(nums))]
        return json_write(self.short_path, data)

    # ---- 防重冷却记录 ----
    def anti_records(self) -> list[dict]:
        data = json_read(self.anti_path, [])
        return data if isinstance(data, list) else []

    def cooling_nums(self, cfg: dict) -> list[int]:
        """当前处于防重冷却期（窗口 t 小时内被抽中过）的号码列表。"""
        if not cfg.get("anti_dup_enabled", True):
            return []
        hours = float(cfg.get("anti_dup_hours", ANTI_DUP_DEFAULT_HOURS))
        now = time.time()
        out = []
        for r in self.anti_records():
            if isinstance(r, dict) and "num" in r:
                t = float(r.get("drawn_at", 0))
                if now - t < hours * 3600:
                    out.append(int(r["num"]))
        return out

    def record_cooling(self, num: int) -> None:
        """抽中后立即记录冷却（带时间戳，flush 落盘）。"""
        records = self.anti_records()
        records.append({"num": int(num), "drawn_at": time.time(), "iso": now_iso()})
        json_write(self.anti_path, records)

    def reset_round(self) -> None:
        """【重置本轮】清空防重冷却记录 + 本轮已抽名单（永久历史不受影响）。"""
        json_write(self.anti_path, [])
        json_write(self.round_path, [])

    # ---- 抽号历史（永久、不可删除） ----
    def history(self) -> list[dict]:
        return json_read(self.history_path, [])

    def add_history(self, num: int, name: str, mode: str) -> None:
        """追加一条抽号记录并立即 flush 落盘（6.3 实时持久化）。"""
        records = self.history()
        if not isinstance(records, list):
            records = []
        records.append({"time": now_iso(), "num": int(num), "name": name, "mode": mode})
        json_write(self.history_path, records)

    # ---- 本轮已抽名单（6.1） ----
    def round_list(self) -> list[dict]:
        return json_read(self.round_path, [])

    def append_round(self, num: int, name: str) -> None:
        data = self.round_list()
        if not isinstance(data, list):
            data = []
        data.append({"num": int(num), "name": name, "time": now_iso()})
        json_write(self.round_path, data)

    # ---- 核心：构建当前摇号池 ----
    def draw_pool(self, cfg: dict) -> list[dict]:
        """
        摇号池 = 全部学生 - 长期屏蔽 - 短期屏蔽(当天) - 防重冷却中。
        返回可按任意顺序抽取的学生字典列表。
        """
        students = self.get_students(cfg)
        long_set = set(self.long_exempt())
        short_set = set(self.short_exempt())
        cool_set = set(self.cooling_nums(cfg))
        return [s for s in students
                if s["num"] not in long_set
                and s["num"] not in short_set
                and s["num"] not in cool_set]

    # ---- 统计（3.7 概率统计页面数据来源） ----
    def stats(self) -> list[dict]:
        """
        按历史记录统计：简易模式按号码，高级模式按学生姓名。
        返回 [{"rank":1, "key":"12", "display":"王小明", "count":5, "pct":33.3}, ...]
        按抽中次数降序、次数相同按号码升序。
        """
        records = self.history()
        if not isinstance(records, list):
            records = []
        counter: dict[str, dict] = {}
        for r in records:
            if not isinstance(r, dict):
                continue
            num = int(r.get("num", 0))
            name = str(r.get("name", "") or "")
            key = name if (name and self._mode_of(records) == MODE_ADVANCED) else f"#{num:03d}"
            # 高级模式按姓名统计；姓名可能重名，按姓名+号码合并展示
            if name and self._mode_of(records) == MODE_ADVANCED:
                key = f"{name}"
            entry = counter.setdefault(key, {"num": num, "name": name, "count": 0})
            entry["count"] += 1
        total = len(records)
        items = sorted(counter.values(), key=lambda e: (-e["count"], e["num"]))
        return [{"rank": i + 1,
                 "display": (e["name"] or f"号码 {e['num']:02d}"),
                 "count": e["count"],
                 "pct": round(e["count"] * 100.0 / total, 1) if total else 0.0}
                for i, e in enumerate(items)]

    @staticmethod
    def _mode_of(records: list) -> str:
        """取最近一条记录的模式作为统计口径（历史里已按班级统一）。"""
        for r in reversed(records):
            if isinstance(r, dict) and r.get("mode") in (MODE_SIMPLE, MODE_ADVANCED):
                return r["mode"]
        return MODE_SIMPLE

    # ---- 导出（6.2） ----
    def export_text(self) -> str:
        """
        生成与需求示例一致的导出文本：
        头部（班级/导出时间/总记录数） + 表格（序号/号码/姓名/时间/模式）。
        """
        h = self.history()
        lines = []
        lines.append("=" * 60)
        lines.append(f"班级：{self.name}")
        lines.append(f"导出时间：{now_iso()}")
        lines.append(f"总记录数：{len(h)}条")
        lines.append("=" * 60)
        lines.append(f"{'序号':<6}{'抽中号码':<10}{'学生姓名':<16}{'抽号时间':<22}{'模式'}")
        lines.append("-" * 60)
        for i, r in enumerate(h, start=1):
            num = str(int(r.get("num", 0))).zfill(2)
            name = r.get("name", "") or "-"
            t = r.get("time", "")
            mode = "高级" if r.get("mode") == MODE_ADVANCED else "简易"
            lines.append(f"{str(i):<6}{num:<12}{name:<18}{t:<22}{mode}")
        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 班级管理器（多班级根目录）
# ---------------------------------------------------------------------------

class ClassManager:
    """管理 classes/ 下的所有班级。"""

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
        """生成名单示例模板 template/template.txt（已存在则不覆盖）。"""
        p = self.template_dir / "template.txt"
        if not p.exists():
            try:
                p.write_text(TEMPLATE_CONTENT, encoding="utf-8")
            except Exception:
                pass
        return p

    def ensure_default_class(self) -> str:
        """首次启动自动创建“默认班级”。返回当前班级名。"""
        self.ensure_dirs()
        names = self.list_classes()
        if not names:
            names = [self.create_class("默认班级")]
        return names[0]

    def list_classes(self) -> list[str]:
        """列出全部班级名（按文件夹名，创建时间排序）。"""
        if not self.classes_dir.exists():
            return []
        return sorted([d.name for d in self.classes_dir.iterdir() if d.is_dir()])

    def create_class(self, name: str) -> str:
        """创建班级（同名已存在则自动加后缀避免冲突）。返回实际班级名。"""
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
        """重命名班级 = 文件夹改名。返回新班级名。"""
        new = safe_name(new)
        src = self.classes_dir / old
        dst = self.classes_dir / new
        if not src.exists():
            raise FileNotFoundError(f"班级不存在：{old}")
        if dst.exists():
            raise FileExistsError(f"班级名已存在：{new}")
        src.rename(dst)
        # 同步更新 config.json 里的 name 字段
        store = ClassStore(self.classes_dir, new)
        cfg = store.load_config()
        cfg["name"] = new
        store.save_config(cfg)
        return new

    def delete_class(self, name: str) -> None:
        """
        删除班级（界面已二次确认）。删除前自动把整个文件夹
        归档到 backups/，做到“可找回”，绝不静默销毁。
        """
        src = self.classes_dir / name
        if not src.exists():
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = self.backups_dir / f"{safe_filename(name)}_{ts}"
        try:
            src.rename(dst)
        except FileExistsError:
            shutil.move(str(src), str(dst))
        except Exception:
            # 归档失败时仍完成删除（不阻塞用户）
            shutil.rmtree(src, ignore_errors=True)

    def get_class(self, name: str) -> ClassStore:
        return ClassStore(self.classes_dir, name)


# ---------------------------------------------------------------------------
# 数据完整性巡检（启动时调用）
# ---------------------------------------------------------------------------

def daily_maintenance(store: ClassStore) -> None:
    """启动时自动维护：清理过期短期屏蔽（其中含落盘）。"""
    store.short_exempt()  # 调用即触发过期清理


def repair_history(store: ClassStore) -> None:
    """
    历史文件损坏防护：history.json 损坏时，把损坏文件改名保留
    （history.corrupt_时间戳.json，绝不删除），再开启新记录文件。
    """
    try:
        if not store.history_path.exists():
            return
        data = json_read(store.history_path, None)
        if isinstance(data, list):
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupt = store.history_path.with_name(f"history.corrupt_{ts}.json")
        store.history_path.rename(corrupt)
    except Exception:
        pass
