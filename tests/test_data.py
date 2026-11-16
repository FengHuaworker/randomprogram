# -*- coding: utf-8 -*-
"""数据层回归测试（不依赖 Qt）：python tests/test_data.py"""

import sys
import tempfile
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app_data  # noqa: E402
from app.app_data import ClassManager, MODE_ADVANCED  # noqa: E402


class DataLayerTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="rp_test_"))
        self.mgr = ClassManager(self.base)
        self.mgr.ensure_dirs()
        self.name = self.mgr.create_class("测试班")
        self.store = self.mgr.get_class(self.name)
        cfg = self.store.load_config()
        cfg["mode"] = MODE_ADVANCED
        cfg["total_count"] = 6
        self.store.save_config(cfg)
        self.store.roster_write([f"学生{i}" for i in range(1, 7)])

    def tearDown(self):
        app_data.flush()
        app_data.reset_cache()
        shutil.rmtree(self.base, ignore_errors=True)

    def test_batch_write_is_consistent(self):
        picks = [{"num": 1, "name": "学生1"}, {"num": 2, "name": "学生2"}]
        self.store.record_draws(picks, MODE_ADVANCED, anti_dup=True)
        self.assertEqual(len(self.store.history()), 2)
        self.assertEqual(len(self.store.round_list()), 2)
        self.assertEqual(len(self.store.anti_records()), 2)
        self.assertEqual(len({r["time"] for r in self.store.history()}), 1)

    def test_pool_excludes_cooling(self):
        self.store.record_draws([{"num": 1, "name": "学生1"}], MODE_ADVANCED)
        cfg = self.store.load_config()
        nums = [s["num"] for s in self.store.draw_pool(cfg)]
        self.assertNotIn(1, nums)
        self.assertEqual(len(nums), 5)

    def test_history_range_delete_archives(self):
        rows = [{"time": f"2026-01-0{i} 08:00:00", "num": i, "name": "", "mode": "simple"}
                for i in range(1, 5)]
        app_data.json_write(self.store.history_path, rows)
        app_data.reset_cache()
        n, archive = self.store.delete_history_range("2026-01-02 00:00:00",
                                                     "2026-01-03 23:59:59")
        self.assertEqual(n, 2)
        self.assertTrue(archive.exists())
        self.assertEqual([r["num"] for r in self.store.history()], [1, 4])

    def test_stats_do_not_merge_same_name(self):
        self.store.roster_write(["小明", "小明", "小红"])
        cfg = self.store.load_config()
        cfg["total_count"] = 3
        self.store.save_config(cfg)
        self.store.record_draws([{"num": 1, "name": "小明"}, {"num": 2, "name": "小明"},
                                 {"num": 3, "name": "小红"}], MODE_ADVANCED, anti_dup=False)
        self.assertEqual(len(self.store.stats()), 3)

    def test_reset_keeps_history(self):
        self.store.record_draws([{"num": 1, "name": "学生1"}], MODE_ADVANCED)
        self.store.reset_round()
        self.assertEqual(self.store.history().__len__(), 1)
        self.assertEqual(self.store.round_list(), [])
        self.assertEqual(self.store.anti_records(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
