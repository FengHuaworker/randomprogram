# 随机抽号软件（源码 + 打包）

Windows 桌面随机抽号软件：多班级管理、简易/高级引导模式、抽号动画、
屏蔽（长期/短期）、防重号、抽号记录、概率统计、配置展示、名单编辑、
导出 TXT、配置自动备份恢复。莫兰迪色系 + 手账文具质感，触控友好（≥44px）。
全部数据保存在软件所在目录，不写注册表 / AppData / ProgramData（C 盘还原兼容）。

## 目录结构

```
random-picker/
├── main.py                 # 启动入口（开发：python main.py；打包：PyInstaller 入口）
├── app/                    # 应用包
│   ├── main.py             # QApplication 初始化、壳层
│   ├── app_data.py         # 数据层（班级管理/JSON原子落盘/备份恢复/防重/屏蔽/统计/导出）
│   ├── theme.py            # 莫兰迪主题：QSS、纸纹纹理、阴影工具、字体自适应
│   ├── ui_widgets.py       # 自定义控件：纸纹卡片/弹性缩放标签/光晕/徽章/消息框
│   ├── ui_dialogs.py       # 弹窗：班级名、配置向导、名单编辑器、学生多选
│   ├── ui_pages.py         # 页面：抽号/记录/统计/配置/屏蔽管理
│   ├── ui_main.py          # 主窗口：顶栏 + Tab + 快捷键
│   └── selftest.py         # 内置自检（--selftest）
├── tests/test_data.py      # 数据层回归测试（无 Qt 依赖）
├── tools/                  # 开发工具（不打进 exe）
│   ├── preview.py          # offscreen 界面截图预览
│   ├── make_icon.py        # 生成 assets/app_icon.ico
│   └── patch_tables.py     # 一次性小补丁脚本
├── assets/app_icon.ico
├── 使用说明.md             # 面向用户
└── dist/随机抽号.exe       # 打包产物（rebuild 生成）
```

## 开发运行

```powershell
python main.py                # 正常启动
python main.py --selftest     # 内置自检（数据层+GUI 冒烟，退出码 0=通过）
python tools/preview.py       # 生成 ui_preview/*.png 界面预览
python tests/test_data.py     # 数据层回归测试
```

## 打包

```powershell
python -m PyInstaller --noconfirm --onefile --noconsole --clean `
  --icon assets/app_icon.ico `
  --add-data "assets/app_icon.ico;assets" `
  --add-data "assets/fonts;assets/fonts" `
  --name 随机抽号 main.py
```

产物：`dist/随机抽号.exe`，双击即用。`assets/fonts/`（Playfair Display / DM Sans，OFL 协议）随包分发，程序启动时自动注册，缺失时回退系统字体。验证：

```powershell
copy dist\随机抽号.exe "D:\某个临时目录\"   # 放到独立目录测试
.\随机抽号.exe --selftest ; echo $LASTEXITCODE   # 应为 0
```

## 触屏适配要点

- 交互控件触控目标 ≥ 44×44px（按钮 48px+），窗口最大化默认；
- 所有列表/表格/滚动区启用 `QScroller`（`enable_touch_scroll`）：单指拖动滚动 + 惯性，鼠标拖拽同样可用（LeftMouseButtonGesture 统一手势）；
- 按压反馈 = 水波涟漪 + QSS 下沉；悬停动效（抬升阴影/下划线/高光位移）仅作补充，触屏退化为纯按压反馈；
- 应用内自绘弹窗（MaterialDialog）：遮罩、ESC、点遮罩均可关闭，触屏滚动列表。

## 设计语言（莫兰迪 · 杂志感 · 手工感 · 丝滑动效）

- 主色雾霾蓝灰蓝系 + 暖灰/米白/浅驼辅助；无荧光色/高饱和蓝/紫蓝渐变；
- 标题衬线（Playfair Display 打包附带）、正文无衬线（DM Sans 打包附带 / 微软雅黑回退），字号层级拉开；
- 手工感：顶栏手绘波浪线、弹窗偏移装饰双线、背景有机色块（倾斜椭圆/圆角方块）、纸纹噪点；
- 动效：`theme.bezier()` 实现 cubic-bezier LUT（Qt 无原生贝塞尔），统一 ease-out 0.3~0.6s；启动为圆形呼吸标识（SplashWindow）后优雅消隐；弹窗遮罩淡入 + 卡片轻弹入；内容滚入视口渐现上移（配置页 + 视差色块）。

## 验证 exe 不写 C 盘

放入全新文件夹运行 `随机抽号.exe --selftest`（或直接双击启动），
确认 `classes/`、`exports/`、`backups/`、`template/` 都生成在
**exe 同级目录**；`last_class.txt` 同理。程序内不写入任何 C 盘路径。

## 测试覆盖（对应需求第六节用例）

- 创建 3 个班级、每个班级独立数据（名单/屏蔽/防重/历史互不干扰）
- 名单上传（UTF-8/GBK）、名单编辑增删改、重新上传
- 抽号：开始/停止动画、定格即记录、本轮已抽、摇号池缩量
- 屏蔽：长期/短期（含次日自动解除）
- 防重：默认 24h 窗口生效、可关闭、可重置；重置清空本轮、保留历史
- 导出 TXT 格式（含班级/导出时间/总条数/表格对齐）
- 重启软件数据恢复（新进程重新加载）
- config.json 损坏 → .bak 自动恢复；双缺失 → 标记 needs_setup 引导重配
- 历史损坏 → 改名保留不删除
- 班级重命名（文件夹改名）/ 删除（归档 backups）
- 非法字符清洗、路径穿越防护
