# -*- coding: utf-8 -*-
"""
内置自检（python main.py --selftest 或 随机抽号.exe --selftest）：
在临时目录中完整体验一遍核心流程，退出码 0 表示全部通过。
覆盖：3 个班级、名单上传、抽号、屏蔽、防重、导出、重启数据恢复、
配置损坏自动恢复、班级重命名/删除归档。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import app_data
from .app_data import ClassManager, MODE_ADVANCED, MODE_SIMPLE

FAILS: list[str] = []


def _check(name: str, cond: bool, detail: str = ""):
    """断言记录：失败收集，继续跑完。"""
    mark = "✔" if cond else "✘"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(f"{name} {detail}")


# ---------------------------------------------------------------------------
# 一、数据层测试（不依赖界面）
# ---------------------------------------------------------------------------

def _data_tests(base: Path) -> None:
    print("[1/2] 数据层测试")
    mgr = ClassManager(base)
    mgr.ensure_dirs()
    mgr.ensure_template()
    first = mgr.ensure_default_class()   # 首次启动自动创建“默认班级”

    # 1. 首次启动：自动创建默认班级 + 模板
    _check("首次启动创建默认班级", "默认班级" in mgr.list_classes())
    _check("生成名单模板", (base / "template" / "template.txt").exists())

    # 2. 创建 3 个班级
    names = [mgr.create_class("三年级1班"), mgr.create_class("二年级2班"), mgr.create_class("五年级3班")]
    _check("创建3个班级", len(mgr.list_classes()) == 4, str(mgr.list_classes()))

    # 3. 高级模式：上传名单（UTF-8）+ 配置
    c1 = mgr.get_class(names[0])
    roster = ["张三", "李四", "王五", "赵六", "孙七", "周八", "吴九", "郑十", "冯十一", "陈十二"]
    c1.roster_write(roster)
    cfg = c1.load_config()
    cfg["mode"] = MODE_ADVANCED
    cfg["total_count"] = len(roster)
    c1.save_config(cfg)

    # 4. 抽号池：初始 10 人
    pool = c1.draw_pool(cfg)
    _check("摇号池=全部名单", len(pool) == 10, str(len(pool)))

    # 5. 模拟抽号 3 次（第 1 次：号码3 王五）
    draws = [pool[2], pool[5], pool[8]]     # 号码 3/6/9
    for s in draws:
        c1.add_history(s["num"], s.get("name", ""), MODE_ADVANCED)
        c1.append_round(s["num"], s.get("name", ""))
        c1.record_cooling(s["num"])
    _check("历史记录已落盘", len(c1.history()) == 3)
    _check("本轮已抽落盘", len(c1.round_list()) == 3)
    _check("防重冷却落盘", len(c1.anti_records()) == 3)

    # 5b. 批量落盘：一次写三处，条数一致（批量抽号主路径）
    c1_batch = mgr.get_class(names[2])
    cfg_b = c1_batch.load_config()
    cfg_b["total_count"] = 8
    c1_batch.save_config(cfg_b)
    picks = [{"num": i, "name": ""} for i in (1, 2, 3, 4)]
    c1_batch.record_draws(picks, MODE_SIMPLE, anti_dup=True)
    _check("批量落盘：历史4条", len(c1_batch.history()) == 4)
    _check("批量落盘：本轮4条", len(c1_batch.round_list()) == 4)
    _check("批量落盘：冷却4条", len(c1_batch.anti_records()) == 4)
    _check("批量落盘：同批次时间一致",
           len({r["time"] for r in c1_batch.history()}) == 1)

    # 6. 防重生效：已抽号码不在新摇号池
    pool2 = c1.draw_pool(cfg)
    nums2 = {s["num"] for s in pool2}
    _check("防重：已抽号码被排除", all(n not in nums2 for n in (3, 6, 9)), str(sorted(nums2)))

    # 7. 关闭防重：全员在池
    cfg2 = dict(cfg); cfg2["anti_dup_enabled"] = False
    _check("关闭防重后全员可抽", len(c1.draw_pool(cfg2)) == 10)

    # 8. 长期屏蔽 + 短期屏蔽
    c1.set_long_exempt([1, 2])
    c1.set_short_exempt([4])
    pool3 = c1.draw_pool(cfg)
    nums3 = {s["num"] for s in pool3}
    _check("长期屏蔽生效(1,2)", 1 not in nums3 and 2 not in nums3, str(sorted(nums3)))
    _check("短期屏蔽生效(4)", 4 not in nums3)

    # 9. 短期屏蔽过期自动清理（写入昨天的日期）
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * 1))
    app_data.flush()
    app_data.reset_cache()            # 直接改文件后需让内存缓存失效
    c1.short_path.write_text(f'[{{"num": 5, "date": "{yesterday}"}}]', encoding="utf-8")
    _check("短期屏蔽次日自动解除", c1.short_exempt() == [], str(c1.short_exempt()))

    # 10. 概率统计（按姓名，降序）
    stats = c1.stats()
    _check("统计：王五=1次", any(s["display"] == "王五" and s["count"] == 1 for s in stats))
    _check("统计：降序排列", all(stats[i]["count"] >= stats[i + 1]["count"]
                                 for i in range(len(stats) - 1)))

    # 11. 导出文本格式
    txt = c1.export_text()
    _check("导出含班级名", "班级：三年级1班" in txt)
    _check("导出含总记录数", "总记录数：3条" in txt)
    _check("导出含模式列", "高级" in txt)

    # 12. 重置本轮：冷却清空、历史保留
    c1.reset_round()
    _check("重置本轮清空冷却", c1.anti_records() == [])
    _check("重置本轮清空已抽", c1.round_list() == [])
    _check("重置不影响历史", len(c1.history()) == 3)

    # 13. 重启恢复：新实例重新读取（模拟重启电脑）
    app_data.flush()                 # 等后台写盘完成
    app_data.reset_cache()           # 清空内存缓存，强制从磁盘读
    mgr2 = ClassManager(base)
    c1r = mgr2.get_class(names[0])
    cfg_r = c1r.load_config()
    _check("重启后配置恢复", cfg_r.get("mode") == MODE_ADVANCED and cfg_r.get("total_count") == 10)
    _check("重启后名单恢复", c1r.roster_read() == roster)
    _check("重启后历史恢复", len(c1r.history()) == 3)

    # 14. 配置损坏 -> 自动从 .bak 恢复
    c1r.cfg_path.write_text("{ 这不是合法JSON", encoding="utf-8")
    cfg_rec = c1r.load_config()
    _check("损坏配置自动恢复(.bak)", cfg_rec.get("total_count") == 10 and not c1r.needs_setup)
    _check("恢复后配置重写正式文件", "{ 这" not in c1r.cfg_path.read_text(encoding="utf-8"))

    # 15. 配置与备份都缺失 -> 需要重新引导
    c1r.cfg_path.unlink()
    c1r.cfg_bak_path.unlink()
    cfg_missing = c1r.load_config()
    _check("配置全缺失则标记 needs_setup", c1r.needs_setup and cfg_missing.get("total_count") == 0)

    # 16. 重命名 / 删除（归档到 backups）
    new_name = mgr.rename_class(names[1], "三年级2班(新)")
    _check("重命名班级", new_name == "三年级2班(新)" and (base / "classes" / new_name).exists())
    mgr.delete_class(names[2])
    _check("删除班级归档到 backups", len(list((base / "backups").iterdir())) >= 1
           and "五年级3班" not in mgr.list_classes())
    _check("删除后其余班级完好", "三年级1班" in mgr.list_classes())

    # 17. 非法字符清洗
    _check("非法字符清洗", app_data.safe_name('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij")
    _check("路径穿越防护", app_data.safe_name("..") == "未命名班级")


# ---------------------------------------------------------------------------
# 二、GUI 冒烟测试（offscreen）
# ---------------------------------------------------------------------------

def _gui_tests(app, base: Path) -> None:
    print("[2/2] GUI 冒烟测试")
    from .ui_main import MainWindow

    mgr = ClassManager(base)
    mgr.ensure_dirs()
    first = mgr.ensure_default_class()
    st = mgr.get_class(first)
    cfg = st.load_config()
    cfg["mode"] = MODE_SIMPLE
    cfg["total_count"] = 10
    st.save_config(cfg)

    win = MainWindow(mgr)
    win.show()
    app.processEvents()
    _check("主窗口创建", win.isVisible())

    # 预置一个高级模式班级并切换
    adv = mgr.create_class("初三(3)班")
    st_adv = mgr.get_class(adv)
    st_adv.roster_write(["阿明", "小美", "大壮", "乐乐", "婷婷"])
    c2 = st_adv.load_config()
    c2["mode"] = MODE_ADVANCED
    c2["total_count"] = 5
    st_adv.save_config(c2)

    # 抽号：开始 -> 停止（定格即记录）
    win._reload_class("初三(3)班")
    app.processEvents()
    win.draw_page.start()
    app.processEvents()
    win.draw_page.stop()
    app.processEvents()
    _check("GUI抽号写入历史", len(st_adv.history()) == 1)
    _check("GUI抽号写入本轮", len(st_adv.round_list()) == 1)
    _check("GUI抽号写入冷却", len(st_adv.anti_records()) == 1)
    _check("GUI摇号池缩至4人", len(win.draw_page._pool) == 4, str(len(win.draw_page._pool)))

    # 记录/统计/配置/屏蔽页刷新
    win.history_page.refresh()
    win.stats_page.refresh()
    win.config_page.refresh()
    win.shield_page.refresh()
    _check("各页面刷新无异常", True)

    # 屏蔽管理流程
    st_adv.set_long_exempt([2])
    win.shield_page.refresh()
    _check("屏蔽页标注长期屏蔽", "长期屏蔽" in win.shield_page.table.item(1, 0).text())

    # 配置向导：高级模式（直接注入名单后应用）
    from .ui_dialogs import SetupWizard
    wiz = SetupWizard(win, st_adv, c2)
    wiz.card_advanced.set_selected(True)
    wiz._roster = ["甲", "乙", "丙"]
    wiz._apply()
    c2b = st_adv.load_config()
    _check("向导高级模式写入配置", c2b.get("mode") == MODE_ADVANCED and len(st_adv.roster_read()) == 3)

    # 配置向导：简易模式
    st_first = mgr.get_class(first)
    cfb = st_first.load_config()
    wiz2 = SetupWizard(win, st_first, cfb)
    wiz2.card_simple.set_selected(True)
    wiz2.simple_count.setValue(8)
    wiz2._apply()
    cfb2 = st_first.load_config()
    _check("向导简易模式写入配置", cfb2.get("mode") == MODE_SIMPLE and cfb2.get("total_count") == 8)

    # 配置向导：状态机（点击“下一步”应切换页面并更新步骤指示）
    wiz3 = SetupWizard(win, st_first, cfb2)
    wiz3.card_advanced.set_selected(True)
    wiz3._next()                                   # mode -> count(高级)
    _check("向导下一步：进入人数步", wiz3._state == "count" and wiz3.stack.currentIndex() == 2)
    wiz3._next()                                   # count -> roster
    _check("向导下一步：进入名单步", wiz3._state == "roster" and wiz3.stack.currentIndex() == 3)
    _check("名单步未选名单时完成按钮禁用", not wiz3.btn_next.isEnabled())
    wiz3._roster = ["甲乙丙", "丁戊己"]
    wiz3._refresh()
    _check("名单步选中名单后完成按钮可用", wiz3.btn_next.isEnabled())
    wiz3.adv_count.setValue(2)
    wiz3._next()                                   # roster -> 完成(_apply)
    c3 = st_first.load_config()
    _check("向导状态机最终写入配置", c3.get("mode") == MODE_ADVANCED and
            (st_first.roster_read() == ["甲乙丙", "丁戊己"]))

    # 向导：简易模式走流程（下一步→下一步→写入）
    cfb3 = st_first.load_config()
    wiz4 = SetupWizard(win, st_first, cfb3)
    wiz4.card_simple.set_selected(True)
    wiz4._next()
    _check("向导简易：进入人数步", wiz4._state == "count" and wiz4.stack.currentIndex() == 1)
    wiz4.simple_count.setValue(5)
    wiz4._next()                                   # count -> _apply
    c4 = st_first.load_config()
    _check("向导简易流程写入配置", c4.get("mode") == MODE_SIMPLE and c4.get("total_count") == 5)

    # 模式卡：互斥（同时只能选一种）
    wiz5 = SetupWizard(win, st_first, cfb3)
    wiz5.card_simple.set_selected(True)
    wiz5.card_advanced._click(None)
    _check("模式卡互斥选择", wiz5.card_simple.is_checked() is False
           and wiz5.card_advanced.is_checked() is True)
    wiz5.card_simple._click(None)
    _check("模式卡互斥切换", wiz5.card_simple.is_checked() is True
           and wiz5.card_advanced.is_checked() is False)

    # 弹窗遮罩几何：必须盖住“顶层窗口”（父控件是子页面时此前会错位）
    from .ui_widgets import MaterialAlert, Snackbar, snack
    al = MaterialAlert(win.draw_page, "测试", "遮罩几何测试", buttons=[("好", True)])
    al.show()
    app.processEvents()
    geo = al.geometry()
    # 正确基准是父窗口的**客户区**（不是 frameGeometry：它含 31px 标题栏，
    # 用它对齐会让弹窗整体上移半个标题栏）
    from PySide6.QtCore import QRect, QPoint
    top = QRect(win.mapToGlobal(QPoint(0, 0)), win.size())
    ok = (abs(geo.x() - top.x()) <= 2 and abs(geo.y() - top.y()) <= 2
          and abs(geo.width() - top.width()) <= 2 and abs(geo.height() - top.height()) <= 2)
    _check("弹窗遮罩对齐主窗客户区", ok,
           f"dialog={geo.x()},{geo.y()}..{geo.width()}x{geo.height()} vs client={top.x()},{top.y()}..{top.width()}x{top.height()}")
    al.hide()
    app.processEvents()

    # 信息卡（Snackbar）：成功/失败两种样式可正常弹出
    snack(win, "记录已导出测试", kind="success")
    app.processEvents()
    sb = [w for w in win.findChildren(Snackbar)]
    _check("信息卡弹出", len(sb) >= 1 and sb[0].isVisible())
    snack(win, "导出失败测试", kind="error")
    app.processEvents()
    _check("信息卡切换样式不崩溃", True)
    for w in sb:
        w.hide()

    # 文字按钮下划线动画：进入=展开，离开=必须收起（回归：移开不消失）
    from PySide6.QtTest import QTest
    from .ui_widgets import RippleButton
    tb = RippleButton("新建班级")
    tb.setProperty("type", "ghost")
    tb._animate("uline", 12, target=1.0)
    QTest.qWait(250)
    opened = tb.uline > 0.7
    tb._animate("uline", 12, target=0.0)
    QTest.qWait(250)
    closed = tb.uline < 0.3
    _check("下划线：进入展开/离开收起", opened and closed)

    # 切换回默认班级
    win._reload_class(first)
    app.processEvents()
    _check("切回默认班级", win.draw_page.store.name == first)

    # ---- 新功能：语言切换 / 防重联动 / 快捷键 / 设置弹窗 ----
    from .lang import set_lang, t as _t, get_lang
    set_lang("en")
    _check("语言切换：导航英文", _t("nav_draw") == "Draw" and get_lang() == "en")
    set_lang("zh")
    _check("语言切回中文", _t("nav_draw") == "抽号" and get_lang() == "zh")

    # 防重开关联动：关闭后首页摇号池立即重算（不再含冷却者 → 全员可用）
    # 先构造可控状态：清屏蔽/清冷却，抽 4 池 = 5-1
    st_first.set_long_exempt([])
    st_first.set_short_exempt([])
    st_first.reset_round()
    c_before = st_first.load_config()
    c_before["anti_dup_enabled"] = True
    c_before["total_count"] = 5
    st_first.save_config(c_before)
    st_first.record_cooling(2)
    win._reload_class(st_first.name)
    n_before = len(win.draw_page._pool)
    win.config_page._on_anti_toggle(False)      # 关闭防重 → settings_changed → 主窗联动
    app.processEvents()
    n_after = len(win.draw_page._pool)
    _check("关闭防重首页摇号池立即扩大", n_after == 5 and n_before == 4,
           f"{n_before} vs {n_after} pool={[s['num'] for s in win.draw_page._pool]}")
    _check("关闭防重主窗配置同步", win.draw_page.cfg.get("anti_dup_enabled") is False)
    win.config_page._on_anti_toggle(True)       # 还原
    app.processEvents()

    # 快捷键：空格 / R / E 均注册（QShortcut 优先于焦点按钮，空格不会被按钮吃掉）
    from PySide6.QtGui import QShortcut
    scs = win.findChildren(QShortcut)
    _check("快捷键已注册(空格/R/E)", len(scs) >= 3, str(len(scs)))

    # 设置弹窗：语言选择 + 防重保存（_save 写盘）
    from .ui_dialogs import AppSettingsDialog
    dlg = AppSettingsDialog(win, st_first, st_first.load_config())
    dlg.seg_lang.setCurrentIndex(1)
    dlg.sw_anti.setChecked(False)
    dlg.spin_anti.setValue(48)
    dlg._save()
    app.processEvents()
    c_saved = st_first.load_config()
    _check("设置弹窗保存语言", get_lang() == "en")
    _check("设置弹窗保存防重", c_saved.get("anti_dup_enabled") is False
           and c_saved.get("anti_dup_hours") == 48)
    set_lang("zh")
    dlg_cfg = st_first.load_config()
    dlg_cfg["anti_dup_enabled"] = True
    dlg_cfg["anti_dup_hours"] = c_before.get("anti_dup_hours", 24)
    st_first.save_config(dlg_cfg)
    win._on_settings_changed()

    # 屏蔽多选弹窗（回归：曾因 count_label 创建顺序导致构造抛异常，
    # 表现为点击「添加长期/短期屏蔽」无任何反应）
    from .ui_dialogs import StudentPickDialog
    from PySide6.QtCore import Qt as _Qt
    studs = st_first.get_students(st_first.load_config())
    spd = StudentPickDialog(win.shield_page, _t("pick_title_pre"), studs, {1})
    _check("屏蔽多选弹窗构造", spd.listw.count() == len(studs), str(spd.listw.count()))
    spd.listw.item(0).setCheckState(_Qt.Checked)   # num=1 已预选，再点一次仍为已选
    sel = spd.selected()
    _check("屏蔽多选勾选统计", sel == {1}, str(sel))
    spd.listw.item(1).setCheckState(_Qt.Checked)
    _check("屏蔽多选追加勾选", spd.selected() == {1, 2})

    # 数字字号自适应（3 位数用更小字号，防溢出；具体像素随窗口高度缩放）
    win.draw_page._apply_num_size(3)
    px3 = win.draw_page.num_label.font().pixelSize()
    win.draw_page._apply_num_size(2)
    px2 = win.draw_page.num_label.font().pixelSize()
    _check("数字位数自适应字号", 0 < px3 < px2, f"{px3} vs {px2}")

    # 批量人数上限：永远不超过摇号池剩余人数
    from .ui_pages import DrawPage
    _check("批量上限：20 抽 15 收口", DrawPage._clamp_batch(20, 15) == (15, True))
    _check("批量上限：3 抽 15 不变", DrawPage._clamp_batch(3, 15) == (3, False))
    _check("批量上限：池空返回 0", DrawPage._clamp_batch(20, 0) == (0, True))
    _check("批量上限：非法值兜底", DrawPage._clamp_batch("x", 5) == (1, False))

    # 摇号池归零 → 自动重置（清空本轮 + 冷却，历史保留）
    st_auto = mgr.get_class(mgr.create_class("自动重置班"))
    st_auto.roster_write(["甲", "乙"])
    cfga = st_auto.load_config()
    cfga["mode"] = MODE_ADVANCED
    cfga["total_count"] = 2
    cfga["anti_dup_enabled"] = True
    st_auto.save_config(cfga)
    win._reload_class(st_auto.name)
    app.processEvents()
    st_auto.record_draws([{"num": 1, "name": "甲"}, {"num": 2, "name": "乙"}],
                         MODE_ADVANCED, anti_dup=True)
    win.draw_page._snap = st_auto.pool_snapshot(cfga)
    win.draw_page._pool = []
    did = win.draw_page._maybe_auto_reset()
    _check("池空自动重置", did and st_auto.round_list() == [] and st_auto.anti_records() == [])
    _check("自动重置保留历史", len(st_auto.history()) == 2)
    _check("自动重置后全员回池", len(st_auto.draw_pool(cfga)) == 2)

    # 批量揭晓覆盖层：构造 + 跳过动画 + 关闭（不阻塞、不崩溃）
    from .ui_widgets import BatchRevealOverlay
    ov = BatchRevealOverlay(win, [{"num": 1, "name": "甲"}, {"num": 2, "name": "乙"}], [1, 2])
    ov.show()
    ov.start()
    app.processEvents()
    ov.finish_all()
    _check("批量揭晓层可跳过", ov._done and len(ov._cards) == 2)
    ov.close_overlay()
    app.processEvents()

    # 管理员密码：用户自设（在临时目录里验证，不碰程序目录）
    from . import security
    pwd_root = Path(tempfile.mkdtemp(prefix="selftest_pwd_"))
    try:
        _check("密码：初始未设置", security.is_configured(pwd_root) is False)
        _check("密码：未设置时校验拒绝", security.verify(pwd_root, "anything") is False)
        _check("密码：过短拒绝", security.set_password(pwd_root, "123") is False)
        _check("密码：纯空白拒绝", security.set_password(pwd_root, "      ") is False)
        _check("密码：设置成功", security.set_password(pwd_root, "selftest-pwd") is True)
        _check("密码：已设置", security.is_configured(pwd_root) is True)
        _check("密码：错误拒绝", security.verify(pwd_root, "wrong") is False)
        _check("密码：正确通过", security.verify(pwd_root, "selftest-pwd") is True)
        _check("密码：空值拒绝", security.verify(pwd_root, "") is False)
        _check("密码：改密需旧密码", security.change_password(pwd_root, "wrong", "new-pwd") is False)
        _check("密码：改密成功", security.change_password(pwd_root, "selftest-pwd", "new-pwd") is True)
        _check("密码：新密码生效", security.verify(pwd_root, "new-pwd") is True)
        _check("密码：旧密码失效", security.verify(pwd_root, "selftest-pwd") is False)
        _check("密码：文件不含明文", "new-pwd" not in security.path_of(pwd_root).read_text(encoding="utf-8"))
        _check("密码：重置", security.reset(pwd_root) is True)
        _check("密码：重置后未设置", security.is_configured(pwd_root) is False)
    finally:
        shutil.rmtree(pwd_root, ignore_errors=True)

    # 密码弹窗：没设过密码时是「设置」形态，设过之后是「验证」形态
    pwd_root2 = Path(tempfile.mkdtemp(prefix="selftest_pwd2_"))
    try:
        from .ui_dialogs import AdminPasswordDialog
        d1 = AdminPasswordDialog(win, pwd_root2)
        _check("密码弹窗：首次为设置形态",
               d1.first_time is True and d1.edit2 is not None)
        d1.edit.setText("2468")
        d1.edit2.setText("2468")
        d1._check()
        _check("密码弹窗：设置后直接通过",
               d1.verified is True and security.is_configured(pwd_root2))

        d2 = AdminPasswordDialog(win, pwd_root2)
        _check("密码弹窗：再次打开为验证形态",
               d2.first_time is False and d2.edit2 is None)
        d2.edit.setText("0000")
        d2._check()
        _check("密码弹窗：错误密码不通过", d2.verified is False)
        d2.edit.setText("2468")
        d2._check()
        _check("密码弹窗：正确密码通过", d2.verified is True)
    finally:
        shutil.rmtree(pwd_root2, ignore_errors=True)

    # 记录区间删除：归档 + 只删区间内记录
    st_clean = mgr.get_class(mgr.create_class("记录清理班"))
    cfgc = st_clean.load_config()
    cfgc["total_count"] = 5
    st_clean.save_config(cfgc)
    base_hist = [
        {"time": "2026-01-01 08:00:00", "num": 1, "name": "", "mode": MODE_SIMPLE},
        {"time": "2026-01-02 08:00:00", "num": 2, "name": "", "mode": MODE_SIMPLE},
        {"time": "2026-01-03 08:00:00", "num": 3, "name": "", "mode": MODE_SIMPLE},
        {"time": "2026-01-04 08:00:00", "num": 4, "name": "", "mode": MODE_SIMPLE},
    ]
    app_data.json_write(st_clean.history_path, base_hist)
    n_del, archive = st_clean.delete_history_range("2026-01-02 00:00:00", "2026-01-03 23:59:59")
    _check("区间删除条数正确", n_del == 2 and len(st_clean.history()) == 2)
    _check("区间删除生成归档", archive is not None and archive.exists()
           and archive.parent.name == "backups")
    _check("区间外记录保留", [r["num"] for r in st_clean.history()] == [1, 4])
    _check("空区间不误删", st_clean.delete_history_range("2030-01-01 00:00:00",
                                                          "2030-01-02 00:00:00")[0] == 0)

    # 统计口径：同名不同号不合并
    st_dup = mgr.get_class(mgr.create_class("同名班"))
    cfgd = st_dup.load_config()
    cfgd["mode"] = MODE_ADVANCED
    cfgd["total_count"] = 3
    st_dup.save_config(cfgd)
    st_dup.roster_write(["小明", "小明", "小红"])
    st_dup.record_draws([{"num": 1, "name": "小明"}, {"num": 2, "name": "小明"},
                         {"num": 3, "name": "小红"}], MODE_ADVANCED, anti_dup=False)
    stats_dup = st_dup.stats()
    _check("统计：同名不合并", len(stats_dup) == 3 and
           sum(1 for s in stats_dup if s["display"] == "小明") == 2)

    # 配置兼容：旧 config 缺 batch_count 时自动补齐
    _check("旧配置补齐 batch_count", st_clean.load_config().get("batch_count") is not None)

    # 清除上一轮已抽后的 draw_page 停止状态检查
    win.draw_page.stop_silent()
    win.close()
    app.processEvents()
    _check("窗口正常关闭", True)


def run_selftest(app) -> int:
    # 控制台/管道编码兜底：Windows GBK 控制台无法输出 ✔/✘，会导致自检本身崩溃。
    # 统一把 stdout 切到 UTF-8（errors=replace），无 stdout 时忽略。
    try:
        if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("=" * 52)
    print(" 随机抽号软件 · 内置自检")
    print("=" * 52)
    base = Path(tempfile.mkdtemp(prefix="random_picker_selftest_"))
    try:
        _data_tests(base)
        _gui_tests(app, base)
    except Exception as e:
        import traceback
        traceback.print_exc()
        FAILS.append(f"异常：{e}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("-" * 52)
    if FAILS:
        print(f"自检结果：失败 {len(FAILS)} 项")
        for f in FAILS:
            print(f"   ✘ {f}")
        return 1
    print("自检结果：全部通过 ✔")
    return 0
