# BoreholeGuard v1.2 — 轻量级开源测井可视化工具

基于 Python + Tkinter + matplotlib 的桌面端测井曲线绘图与交互分析工具，支持标准 LAS 文件格式的导入、多道布局管理、曲线样式编辑、PDF 导出等核心功能。

---

## 目录

- [架构总览](#架构总览)
- [快速开始](#快速开始)
- [模块说明](#模块说明)
- [数据流](#数据流)
- [UI 交互指南](#ui-交互指南)
- [配置系统](#配置系统)
- [家族模板（Family）](#家族模板family)
- [导出 PDF](#导出-pdf)
- [开发扩展](#开发扩展)

---

## 架构总览

```
┌────────────────────────────────────────────────────────┐
│  main.py         入口，确保模块路径，启动 mainloop        │
├────────────────────────────────────────────────────────┤
│  ui.py           所有 Tkinter 界面、事件、对话框          │
│     ├── 菜单栏 / 快捷键                                 │
│     ├── 左侧数据树 (Treeview)                           │
│     ├── 右侧绘图区 (分层滚动视图)                        │
│     ├── 属性对话框 (井/道/曲线)                         │
│     └── Family 编辑器 / PDF 导出                         │
├────────────────────────────────────────────────────────┤
│  plot_engine.py   matplotlib 测井图构建引擎               │
│     ├── build_log_plot()   完整单图 (PDF 导出用)          │
│     ├── build_header_figure()  仅图头区                  │
│     └── build_data_figure()   仅图道区                   │
├────────────────────────────────────────────────────────┤
│  state.py        所有可变全局状态的集中管理                │
├────────────────────────────────────────────────────────┤
│  config.py       家族模板、布局参数、默认配置              │
├────────────────────────────────────────────────────────┤
│  las_io.py       LAS 文件 I/O 和曲线数据访问              │
└────────────────────────────────────────────────────────┘
```

### 依赖关系

```
main.py
  └── ui.py
        ├── state.py
        ├── config.py
        ├── las_io.py
        └── plot_engine.py
              ├── state.py
              └── config.py
```

---

## 快速开始

### 环境要求

- Python ≥ 3.8
- 依赖库：`lasio`, `numpy`, `matplotlib`

### 安装

```bash
pip install lasio numpy matplotlib
```

### 运行

```bash
cd BoreholeGraud
python main.py
```

### 使用流程

1. **File → 导入 LAS 文件**，或快捷键 `Ctrl+O`
2. 左侧数据树显示已导入曲线
3. 右侧自动生成多道测井图
4. 鼠标交互操作
5. **File → 导出 PDF** 输出高分辨率测井图

---

## 模块说明

### 1. `main.py` — 程序入口

仅做两件事：

- 将项目目录加入 `sys.path`
- 调用 `ui.main()`

### 2. `ui.py` — UI 主模块（~1500 行）

负责全部图形界面和用户交互，包含：

| 组件 | 描述 |
|------|------|
| 主窗口 | 菜单栏 + 左侧数据树 + 右侧绘图区 + 状态栏 |
| 绘图区 | 图头区（可双向滚动） + 分割线（可拖动） + 图道区（可滚动） |
| 井属性 | 图头高度、深度范围、缩放比例实时调整 |
| 道属性 | 道宽比例、网格线实时调整 |
| 曲线属性 | 刻度、线型、线宽、颜色、刻度类型实时调整 |
| Family 编辑器 | 查看和修改家族模板默认值 |
| PDF 导出 | 完整单图或每道分页两种模式 |

#### 关键函数

- `refresh_plot()` — 重建整个绘图区域（图头 + 分割线 + 图道）
- `import_las()` — 文件对话框 + LAS 加载 + 树刷新 + 绘图
- `on_plot_click()` — 鼠标点击命中检测（选曲线/选道）
- `zoom_scale()` — 深度比例缩放
- `move_active()` — 左右键移动曲线或道

### 3. `plot_engine.py` — 绘图引擎

纯 matplotlib 构建，无 tkinter 依赖。核心函数：

```
build_log_plot()          → 完整单 Figure（用于 PDF 导出）
build_header_figure()     → 仅图头 Figure（图头区显示）
build_data_figure()       → 仅图道 Figure（图道区显示）
```

内部共享函数：

- `_compute_layout()` — 统一计算深度范围、Figure 尺寸、轴坐标、刻度
- `_draw_headers()` — 绘制图头区（曲线名、刻度值、示例线）
- `_draw_data_tracks()` — 绘制各数据道曲线和网格

布局计算通过 `MARGIN_LEFT / RIGHT` 和 `compute_track_x()` 确定各道 x 位置，所有三个函数使用相同的算法，保证图头与图道对齐。

### 4. `state.py` — 状态管理

所有可变全局状态的单一来源。主要状态变量：

| 变量 | 类型 | 用途 |
|------|------|------|
| `las_data` | LASFile | lasio 读取的 LAS 数据 |
| `tracks` | `list[list[str]]` | 道布局，如 `[["GR"], ["RT", "RXO"]]` |
| `curve_family` | `dict[str, str]` | 每根曲线的家族名 |
| `curve_styles` | `dict[str, dict]` | 用户对曲线样式的覆盖 |
| `config` | `dict` | 所有可调节配置项 |
| `current_scale` | float | 当前深度缩放比 |
| `active_curve` | str | 当前激活的曲线名 |
| `active_track` | int | 当前激活的道索引 |
| `pick_map` | `list[dict]` | 命中检测索引 |

### 5. `config.py` — 配置和常量

| 项目 | 值 | 说明 |
|------|-----|------|
| `FAMILY_TEMPLATES` | dict | 家族模板定义（刻度、颜色、默认样式） |
| `DEFAULT_CONFIG` | dict | 井属性/道属性/网格默认值 |
| `FIG_WIDTH` | 11.7 (英寸) | 绘图区宽度 |
| `PREVIEW_DPI` | 80 | 屏幕预览分辨率 |
| `MARGIN_TOP/BOTTOM/LEFT/RIGHT` | 0.4/0.2/0.03/0.98 | 图边距比例 |
| `rgb_to_mpl(rgb)` | — | 色彩转换 (0-255 → 0-1) |
| `detect_family(name)` | — | 曲线名自动匹配家族 |

### 6. `las_io.py` — LAS 文件 I/O

| 函数 | 说明 |
|------|------|
| `load_las(filepath)` | 加载 LAS 文件，初始化曲线家族和道布局 |
| `get_curve_data(curve)` | 获取曲线数值数组 |
| `get_curve_unit(curve)` | 获取曲线单位字符串 |

加载流程：

```
load_las(path)
  ├── lasio.read() → state.las_data
  ├── detect_family() → 初始化 state.curve_family
  ├── 每条曲线独立一道 → state.tracks
  └── state.reset_view_state()
```

---

## 数据流

### 加载 LAS 文件

```
File → 导入 LAS 文件
  → import_las()
    → load_las(path)
      → lasio.read → state.las_data
      → detect_family → state.curve_family
      → 初始化 tracks, 重置状态
    → update_tree()       (刷新左侧树)
    → refresh_plot()      (重建绘图)
```

### 绘图刷新

```
refresh_plot()
  ├── build_header_figure()
  │     └── _compute_layout() + _draw_headers()
  ├── build_data_figure()
  │     └── _compute_layout() + _draw_data_tracks()
  ├── 图头区嵌入可滚动 Canvas (水平/垂直滚动条)
  ├── 分割线 (可拖动调节高度)
  └── 图道区嵌入可滚动 Canvas (水平/垂直滚动条)
```

### 交互事件流

```
鼠标点击 → on_plot_click()
  → hit_test(fx, fy)     (遍历 pick_map)
  → 设置 active_curve 或 active_track
  → refresh_plot()       (高亮激活项)

键盘左右键 → move_active()
  → 交换曲线或道位置
  → refresh_plot()

滚轮 → _on_wheel() / _h_wheel()
  → 普通: 垂直滚动
  → Shift+滚轮: 水平滚动 (仅图头)
  → Ctrl+滚轮: zoom_scale()
```

---

## UI 交互指南

### 绘图区

```
┌───────────────────────────────────────────┐
│  工具栏（提示信息 + 关闭按钮）              │
├───────────────────────────────────────────┤
│  图头区 (双向可滚动，含滚动条)              │
│  ┌─────┬─────────┬──────────┐            │
│  │DEPTH│GR (API) │RT (OHMM) │            │
│  │ (m) │─────────│─────────││  ↕│↔│       │
│  │1:125│ 0 ───200│0.2───2000││   │  │       │
│  └─────┴─────────┴──────────┘            │
├───────────────────────────────────────────┤ ← 可拖动分割线
│  图道区 (双向可滚动，含滚动条)              │
│  ┌─────┬─────────┬──────────┐ │↕│        │
│  │     │         │          │ │  │        │
│  │ 深度│  GR道   │  RT道    │ │  │        │
│  │ 刻度│  曲线    │  曲线    │ │  │        │
│  │     │         │          │ │  │        │
│  └─────┴─────────┴──────────┘ │  │        │
│  ──────────────────────────────────        │ ← 水平滚动条
└───────────────────────────────────────────┘
```

### 交互操作表

| 操作 | 效果 |
|------|------|
| **点击图头示例线** | 选中该曲线，曲线加粗/虚线显示 |
| **点击图头空白区域** | 选中该道，边框变红 |
| **← / → 方向键** | 移动所选曲线到相邻道 或 交换道顺序 |
| **Esc** | 取消所有选中状态 |
| **滚轮（图道区）** | 垂直滚动 |
| **滚轮（图头区）** | 垂直滚动 |
| **Shift+滚轮（图头区）** | 水平滚动 |
| **Ctrl+滚轮** | 深度缩放 |
| **拖拽分割线** | 调节图头/图道空间分配（光标变为上下箭头） |

### 对话框

| 对话框 | 功能 |
|--------|------|
| 井属性 | 图头高度(cm)、深度范围、缩放比例（1:xxx） |
| 道属性 | 每道宽度比例、水平/垂直网格线 |
| 曲线属性 | 左右刻度、线宽、线型、颜色、线性/对数 |
| Family 编辑器 | 查看和修改各家族的默认刻度、颜色 |

所有属性对话框均实时生效，无需点击"应用"按钮。

---

## 配置系统

`DEFAULT_CONFIG` 结构：

```python
{
    "header_height": 1.181,       # 图头栏高度（英寸）
    "depth_track_ratio": 0.35,    # 深度道宽度比例
    "curve_track_ratio": 1.0,     # 曲线道宽度比例
    "well": {
        "from_depth": None,       # 显示起始深度
        "to_depth": None,         # 显示终止深度
    },
    "grid": {
        "horizontal": {
            "enabled": True,
            "color": "#cccccc",
            "linewidth": 0.3,
        },
        "vertical": {
            "enabled": True,
            "color": "#cccccc",
            "linewidth": 0.3,
            "num_ticks": 5,
        },
    },
}
```

---

## 家族模板（Family）

家族是测井曲线的分类单位，定义曲线的默认样式。

### 内置家族

| 家族 | 左刻度 | 右刻度 | 刻度类型 | 颜色 |
|------|--------|--------|----------|------|
| **GR** | 0.0 | 200.0 | linear | 绿色 (0,128,0) |
| **RT** | 0.2 | 200.0 | log | 红色 (240,0,0) |
| **RXO** | 0.2 | 200.0 | log | 蓝色 (0,0,240) |
| **BIT** | 6.0 | 16.0 | linear | 棕色 (139,69,19) |
| **CAL** | 6.0 | 16.0 | linear | 橙色 (255,140,0) |
| **default** | 自动 | 自动 | linear | 黑色 (0,0,0) |

### 家族匹配规则

`detect_family(name)` 按顺序匹配曲线名（不区分大小写）：

```
"RXO" in name → RXO
"RT"  in name → RT
"GR"  in name → GR
"BIT" in name → BIT
"CAL" in name → CAL
else          → default
```

用户可通过 Family 编辑器修改默认值，也可通过曲线属性对话框单独覆盖某条曲线的样式。

---

## 导出 PDF

通过 `File → 导出 PDF` 或快捷键 `Ctrl+P` 打开导出对话框。

### 导出选项

| 模式 | 描述 |
|------|------|
| **完整单图** | 所有道合并在一个 Figure 中，含图标题 |
| **按道分页** | 每道一页，适合单道详情查看 |

导出使用 `build_log_plot(for_print=True)`，DPI 可设置为 150 或 300，满足出版要求。

---

## 开发扩展

### 添加新家族

在 `config.py` 的 `FAMILY_TEMPLATES` 中添加：

```python
"DEN": {
    "left": 1.5, "right": 3.0,
    "scale_type": "linear",
    "color": (0, 150, 150),
    "desc": "midu",
},
```

在 `detect_family()` 中添加匹配规则：

```python
if "DEN" in name:
    return "DEN"
```

### 添加新配置项

1. 在 `config.py` 的 `DEFAULT_CONFIG` 中定义默认值
2. 在 `state.py` 中通过 `state.config["key"]` 访问
3. 在 `ui.py` 中添加对应的 UI 控件

### 添加新交互

1. 在 `refresh_plot()` 中绑定事件
2. 实现对应回调函数
3. 调用 `refresh_plot()` 更新视图

---

*BoreholeGuard v1.2 — 发布于 2025-2026*
