"""UI 模块 - 所有 Tkinter 界面、事件交互、对话框。

职责：
  - 主窗口搭建（菜单、面板、状态栏）
  - 点击/滚轮/键盘交互
  - refresh_plot() 刷新绘图区域
  - 属性对话框（井/道/曲线）
  - PDF 导出、Family 编辑器
  - 文件导入（文件对话框 + UI 更新）
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
import os

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.backends.backend_pdf import PdfPages

import state
import config as cfg
from config import (FAMILY_TEMPLATES, MARGIN_TOP, PREVIEW_DPI,
                    rgb_to_mpl, detect_family)
from las_io import load_las, get_curve_unit, get_curve_data
from plot_engine import build_log_plot, build_header_figure, build_data_figure

# ==================== 全局 UI 引用（由 main() 填充）====================
root = None
plot_frame = None
tree = None
status_bar = None

# ==================== 表格工具全局变量 ====================
_table_window = None
_table_tree = None
_table_curves = []  # 当前表格中显示的曲线列表
_drag_data = {"curve": None, "start_x": 0, "start_y": 0, "dragging": False}

# ==================== 图版模式全局变量 ====================
_plate_mode = None  # None, "log", "crossplot"

# 交汇图版全局
_xp_window = None
_xp_x_curve = None
_xp_y_curve = None
_xp_x_frame = None
_xp_y_frame = None
_xp_fig = None
_xp_canvas = None

# ==================== 交互工具函数 ====================


def hit_test(fx, fy):
    """fx, fy 是 figure 比例坐标 (0~1)。返回命中的 pick 项，曲线优先于道。"""
    for p in state.pick_map:
        if p["type"] == "curve":
            if p["x0"] <= fx <= p["x1"] and p["y0"] <= fy <= p["y1"]:
                return p
    for p in state.pick_map:
        if p["type"] == "track":
            if p["x0"] <= fx <= p["x1"] and p["y0"] <= fy <= p["y1"]:
                return p
    return None


def on_plot_click(event):
    """处理绘图区域的鼠标点击事件。"""
    if event.inaxes is None and event.x is None:
        return
    if state.current_fig is None:
        return

    fw = state.current_fig.get_figwidth() * state.current_fig.dpi
    fh = state.current_fig.get_figheight() * state.current_fig.dpi
    if event.x is None or event.y is None:
        return
    fx = event.x / fw
    fy = event.y / fh

    hit = hit_test(fx, fy)
    if hit is None:
        state.active_curve = None
        state.active_track = None
        refresh_plot()
        return
    if hit["type"] == "curve":
        state.active_curve = hit["curve"]
        state.active_track = None
    else:
        state.active_track = hit["idx"]
        state.active_curve = None
    refresh_plot()


# ==================== 缩放与视图操作 ====================


def zoom_scale(factor):
    """缩放当前图的深度比例。"""
    if state.las_data is None:
        return
    state.current_scale = max(0.001, min(2.0, state.current_scale * factor))
    refresh_plot()


def _close_plot():
    """关闭当前绘图板（清空绘图区、重置 figure）。"""
    global _plate_mode
    _plate_mode = None
    if state.current_fig is not None:
        plt.close(state.current_fig)
        state.current_fig = None
    state.current_canvas = None
    for widget in plot_frame.winfo_children():
        widget.destroy()
    tk.Label(plot_frame, text="请通过 文件 - 导入 LAS 文件 开始",
             bg="white", fg="#999", font=("微软雅黑", 12)).pack(expand=True)


def move_active(direction):
    """direction: -1 左, +1 右。移动激活的曲线或道。"""
    if state.las_data is None:
        return

    if state.active_curve is not None:
        src = None
        for ti, clist in enumerate(state.tracks):
            if state.active_curve in clist:
                src = ti
                break
        if src is None:
            return
        dst = src + direction
        if dst < 0 or dst >= len(state.tracks):
            return
        state.tracks[src].remove(state.active_curve)
        state.tracks[dst].append(state.active_curve)
        refresh_plot()
        return

    if state.active_track is not None:
        src = state.active_track
        dst = src + direction
        if dst < 0 or dst >= len(state.tracks):
            return
        state.tracks[src], state.tracks[dst] = state.tracks[dst], state.tracks[src]
        state.active_track = dst
        refresh_plot()


def cancel_active(_event=None):
    """取消所有激活状态。"""
    state.active_curve = None
    state.active_track = None
    refresh_plot()


def on_key_left(_event=None):
    move_active(-1)


def on_key_right(_event=None):
    move_active(+1)


# ==================== 绘图区域刷新 ====================


def refresh_plot():
    """销毁旧绘图区，重建新图。

    图头和图道各自独立可滚动，中间有可拖动分割线调节空间分配。
    按住 Ctrl+滚轮 缩放 / 滚轮 垂直滚动。
    """
    if state.las_data is None:
        return

    # 图版模式：无图道时显示空图版占位符
    if _plate_mode == "log" and not state.tracks:
        _show_log_plate_empty()
        return

    if state.current_fig is not None:
        plt.close(state.current_fig)
        state.current_fig = None
    state.current_canvas = None

    for widget in plot_frame.winfo_children():
        widget.destroy()

    # ---- 工具栏 ----
    toolbar_frame = tk.Frame(plot_frame, bg="#eaeaea")
    toolbar_frame.pack(side="top", fill="x")

    if _plate_mode == "log":
        hint = "拖拽目录树曲线到图头区添加/切换道"
        close_text = "关闭图版"
    else:
        hint = "(点示例线选曲线 / 点道空白选道 - 左右键移动 - Esc取消)"
        close_text = "关闭绘图板"

    tk.Label(toolbar_frame, text=hint,
             bg="#eaeaea", font=("微软雅黑", 8), fg="#666").pack(side="left", padx=10)
    tk.Button(toolbar_frame, text=close_text, command=_close_plot,
              font=("微软雅黑", 8), padx=8, fg="red").pack(side="right", padx=2, pady=1)

    # ---- 构建图 Figure ----
    header_fig = build_header_figure(state.current_scale)
    data_fig = build_data_figure(state.current_scale)
    if header_fig is None or data_fig is None:
        return

    state.current_fig = data_fig  # 用于 hit_test

    header_h = int(header_fig.get_figheight() * PREVIEW_DPI)
    header_w_px = int(header_fig.get_figwidth() * PREVIEW_DPI)
    data_w_px = int(data_fig.get_figwidth() * PREVIEW_DPI)
    data_h_px = int(data_fig.get_figheight() * PREVIEW_DPI)

    # ========== 图头区（可双向滚动）==========
    header_outer = tk.Frame(plot_frame, bg="white", height=header_h + 4)
    header_outer.pack(side="top", fill="x")
    header_outer.pack_propagate(False)

    # 垂直 / 水平滚动条
    h_vscroll = tk.Scrollbar(header_outer, orient="vertical")
    h_vscroll.pack(side="right", fill="y")
    h_hscroll = tk.Scrollbar(header_outer, orient="horizontal")
    h_hscroll.pack(side="bottom", fill="x")

    h_canvas = tk.Canvas(header_outer, bg="white",
                         xscrollcommand=h_hscroll.set,
                         yscrollcommand=h_vscroll.set,
                         highlightthickness=0)
    h_canvas.pack(side="left", fill="both", expand=True)
    h_hscroll.config(command=h_canvas.xview)
    h_vscroll.config(command=h_canvas.yview)

    h_inner = tk.Frame(h_canvas, bg="white")
    h_canvas.create_window((0, 0), window=h_inner, anchor="nw")

    header_mpl = FigureCanvasTkAgg(header_fig, master=h_inner)
    header_mpl.draw()
    header_widget = header_mpl.get_tk_widget()
    header_widget.config(width=header_w_px, height=header_h)
    header_widget.pack()

    def _h_scrollregion(_event=None):
        h_canvas.configure(scrollregion=h_canvas.bbox("all"))
    h_inner.bind("<Configure>", _h_scrollregion)
    h_canvas.after(50, _h_scrollregion)

    # 图头滚轮：Shift+滚轮 → 水平；滚轮 → 垂直；Ctrl+滚轮 → 缩放
    def _h_wheel(event):
        if event.state & 0x0004:  # Ctrl+滚轮 → 缩放
            zoom_scale(1.15 if event.delta > 0 else 0.87)
        elif event.state & 0x0001:  # Shift+滚轮 → 水平
            h_canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        else:  # 滚轮 → 垂直
            h_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
    h_canvas.bind("<MouseWheel>", _h_wheel)

    # ========== 可拖动分割线 ==========
    DIVIDER_H = 5
    divider = tk.Frame(plot_frame, height=DIVIDER_H, cursor="sb_v_double_arrow",
                       bg="#b0b0b0", relief="sunken", bd=1)
    divider.pack(side="top", fill="x")

    _drag = {"active": False, "start_y": 0, "start_h": header_h + 4}

    def _div_enter(_e):
        divider.config(bg="#808080")
    def _div_leave(_e):
        divider.config(bg="#b0b0b0")
    def _div_press(event):
        _drag["active"] = True
        _drag["start_y"] = event.y_root
        _drag["start_h"] = header_outer.winfo_height()
    def _div_drag(event):
        if not _drag["active"]:
            return
        dy = event.y_root - _drag["start_y"]
        new_h = max(60, _drag["start_h"] + dy)
        header_outer.config(height=new_h)
    def _div_release(_event):
        _drag["active"] = False

    divider.bind("<Enter>", _div_enter)
    divider.bind("<Leave>", _div_leave)
    divider.bind("<Button-1>", _div_press)
    divider.bind("<B1-Motion>", _div_drag)
    divider.bind("<ButtonRelease-1>", _div_release)

    # ========== 图道区（可滚动）==========
    data_frame = tk.Frame(plot_frame, bg="white")
    data_frame.pack(side="top", fill="both", expand=True)

    yscroll = tk.Scrollbar(data_frame, orient="vertical")
    yscroll.pack(side="right", fill="y")
    xscroll = tk.Scrollbar(data_frame, orient="horizontal")
    xscroll.pack(side="bottom", fill="x")

    bg_canvas = tk.Canvas(data_frame, bg="white",
                          yscrollcommand=yscroll.set,
                          xscrollcommand=xscroll.set,
                          highlightthickness=0)
    bg_canvas.pack(side="left", fill="both", expand=True)
    yscroll.config(command=bg_canvas.yview)
    xscroll.config(command=bg_canvas.xview)

    inner = tk.Frame(bg_canvas, bg="white")
    bg_canvas.create_window((0, 0), window=inner, anchor="nw")

    data_mpl = FigureCanvasTkAgg(data_fig, master=inner)
    state.current_canvas = data_mpl
    data_mpl.draw()
    data_widget = data_mpl.get_tk_widget()
    data_widget.config(width=data_w_px, height=data_h_px)
    data_widget.pack()

    data_mpl.mpl_connect("button_press_event", on_plot_click)

    def _update_scrollregion(_event=None):
        bg_canvas.configure(scrollregion=bg_canvas.bbox("all"))

    inner.bind("<Configure>", _update_scrollregion)
    bg_canvas.after(50, _update_scrollregion)

    def _on_wheel(event):
        # Ctrl+滚轮 → 缩放
        if event.state & 0x0004:
            zoom_scale(1.15 if event.delta > 0 else 0.87)
        else:
            step = -1 if event.delta > 0 else 1
            bg_canvas.yview_scroll(step, "units")

    bg_canvas.bind("<MouseWheel>", _on_wheel)

    plot_frame.update_idletasks()


# ==================== 文件导入 ====================


def import_las():
    """打开文件选择对话框并导入 LAS 文件。"""
    global _plate_mode
    fp = filedialog.askopenfilename(
        title="选择 LAS 文件",
        filetypes=[("LAS files", "*.las"), ("All files", "*.*")])
    if not fp:
        return
    try:
        # 重置图版模式
        _plate_mode = None
        _close_xp_window()

        load_las(fp)
        curves_str = ', '.join(state.las_data.keys()[1:])
        strt = state.las_data.well.STRT.value
        stop = state.las_data.well.STOP.value
        unit = state.las_data.well.STRT.unit
        status_bar.config(
            text=f"已导入: {os.path.basename(fp)}  |  深度: "
                 f"{strt:.1f} ~ {stop:.1f} {unit}  |  曲线: {curves_str}")
        update_tree()
        refresh_plot()
    except Exception as e:
        messagebox.showerror("导入失败", f"无法读取 LAS 文件:\n{e}")


# ==================== 树状数据浏览器 ====================


def update_tree():
    """刷新左侧数据浏览器树。"""
    for item in tree.get_children():
        tree.delete(item)
    if state.las_data is None:
        return
    well_name = state.las_data.well.WELL.value \
        if 'WELL' in state.las_data.well.keys() else 'Unknown Well'
    wid = tree.insert("", "end", text=f"\U0001f6e2 {well_name}", open=True,
                      values=("well", ""))
    tree.insert(wid, "end", text=f"\U0001f4cf {state.las_data.keys()[0]} (m)",
                values=("depth", ""))
    fam_node = tree.insert(wid, "end", text="\U0001f5c2 曲线 Family 管理",
                           open=True, values=("famroot", ""))
    for curve in state.las_data.keys()[1:]:
        fam = state.curve_family.get(curve, detect_family(curve))
        tree.insert(fam_node, "end",
                    text=f"\U0001f4c8 {curve}  [{fam}族]",
                    values=("curve", curve))


# ==================== 井属性对话框 ====================


def open_well_properties():
    """打开井属性设置对话框。"""
    if state.las_data is None:
        messagebox.showwarning("提示", "请先导入 LAS 文件")
        return
    dialog = tk.Toplevel(root)
    dialog.title("井属性")
    dialog.geometry("420x380")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    debounce = {"timer": None}

    def debounce_refresh():
        if debounce["timer"] is not None:
            dialog.after_cancel(debounce["timer"])
        debounce["timer"] = dialog.after(120, refresh_plot)

    pad = {"padx": 20, "pady": (10, 0)}
    d_min_full = state.las_data.well.STRT.value
    d_max_full = state.las_data.well.STOP.value

    # === 图头栏高度 ===
    tk.Label(dialog, text="图头栏高度 (cm):", font=("微软雅黑", 9)).pack(anchor="w", **pad)
    hv = tk.DoubleVar(value=round(state.config["header_height"] * 2.54, 1))
    hl = tk.Label(dialog, text=f"{hv.get():.1f} cm", font=("微软雅黑", 8), fg="#06c")
    hl.pack(anchor="w", padx=20)

    def upd_h(*_):
        v = round(hv.get(), 1)
        hl.config(text=f"{v:.1f} cm")
        state.config["header_height"] = round(v / 2.54, 3)
        debounce_refresh()

    tk.Scale(dialog, from_=0.3, to=8.0, resolution=0.1, orient="horizontal",
             variable=hv, length=360, showvalue=False, command=upd_h).pack(padx=20)

    # === 显示深度范围 ===
    tk.Label(dialog, text="显示深度范围 (m):", font=("微软雅黑", 9)).pack(anchor="w", **pad)
    rf = tk.Frame(dialog)
    rf.pack(padx=20, pady=4, fill="x")

    well_cfg = state.config.get("well", {})
    cur_from = well_cfg.get("from_depth", d_min_full)
    cur_to = well_cfg.get("to_depth", d_max_full)
    if cur_from is None:
        cur_from = d_min_full
    if cur_to is None:
        cur_to = d_max_full

    fv = tk.DoubleVar(value=round(cur_from, 1))
    tv = tk.DoubleVar(value=round(cur_to, 1))

    tk.Label(rf, text="起始:", font=("微软雅黑", 9)).pack(side="left")
    f_entry = tk.Entry(rf, textvariable=fv, width=10, font=("微软雅黑", 9))
    f_entry.pack(side="left", padx=4)
    tk.Label(rf, text="终止:", font=("微软雅黑", 9)).pack(side="left", padx=(10, 0))
    t_entry = tk.Entry(rf, textvariable=tv, width=10, font=("微软雅黑", 9))
    t_entry.pack(side="left", padx=4)
    tk.Label(rf, text=f"(全井: {d_min_full:.1f}~{d_max_full:.1f})",
             font=("微软雅黑", 7), fg="#888").pack(side="left", padx=6)

    def _apply_range_immediate(*_):
        """实时应用深度范围（忽略无效值）。"""
        try:
            fv_v = fv.get()
            tv_v = tv.get()
            if tv_v > fv_v:
                state.config.setdefault("well", {})["from_depth"] = fv_v
                state.config.setdefault("well", {})["to_depth"] = tv_v
                debounce_refresh()
        except (ValueError, tk.TclError):
            pass

    fv.trace_add("write", _apply_range_immediate)
    tv.trace_add("write", _apply_range_immediate)

    # === 缩放比例 ===
    ttk.Separator(dialog, orient="horizontal").pack(fill="x", padx=20, pady=6)
    tk.Label(dialog, text="绘图缩放比例:", font=("微软雅黑", 9)).pack(anchor="w", **pad)

    ratio_options = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000]
    # 转换当前 scale 为最接近的 ratio
    def _scale_to_ratio():
        return int(round(1.0 / (state.current_scale * 0.0254))) if state.current_scale > 0 else 500

    def _ratio_to_scale(ratio):
        return 1.0 / (ratio * 0.0254)

    scale_ratio_var = tk.IntVar(value=_scale_to_ratio())

    ratio_combo = ttk.Combobox(dialog, textvariable=scale_ratio_var,
                                values=ratio_options, state="readonly",
                                font=("微软雅黑", 10), width=12)
    ratio_combo.pack(padx=20, pady=4)

    def upd_ratio(*_):
        r = scale_ratio_var.get()
        if r > 0:
            state.current_scale = _ratio_to_scale(r)
            refresh_plot()

    ratio_combo.bind("<<ComboboxSelected>>", lambda e: upd_ratio())

    # === 底部按钮 ===
    bf = tk.Frame(dialog)
    bf.pack(pady=16)

    def reset_defaults():
        state.config["header_height"] = round(3.0 / 2.54, 3)
        hv.set(3.0)
        hl.config(text="3.0 cm")
        state.config.setdefault("well", {})["from_depth"] = None
        state.config.setdefault("well", {})["to_depth"] = None
        fv.set(round(d_min_full, 1))
        tv.set(round(d_max_full, 1))
        state.current_scale = 0.008
        scale_ratio_var.set(_scale_to_ratio())
        refresh_plot()

    tk.Button(bf, text="重置默认", command=reset_defaults,
              font=("微软雅黑", 10), width=10).pack(side="left", padx=5)
    tk.Button(bf, text="关闭", command=dialog.destroy,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)


# ==================== 道属性对话框 ====================


def open_track_properties():
    """打开道属性设置对话框。"""
    if state.las_data is None:
        messagebox.showwarning("提示", "请先导入 LAS 文件")
        return
    dialog = tk.Toplevel(root)
    dialog.title("道属性")
    dialog.geometry("460x480")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    debounce = {"timer": None}

    def debounce_refresh():
        if debounce["timer"] is not None:
            dialog.after_cancel(debounce["timer"])
        debounce["timer"] = dialog.after(120, refresh_plot)

    pad = {"padx": 20, "pady": (8, 0)}

    # ===== 道宽比例 =====
    tk.Label(dialog, text="深度道宽度比例:", font=("微软雅黑", 9)).pack(anchor="w", **pad)
    dv = tk.DoubleVar(value=state.config["depth_track_ratio"])
    dl = tk.Label(dialog, text=f"{dv.get():.2f}", font=("微软雅黑", 8), fg="#06c")
    dl.pack(anchor="w", padx=20)

    def upd_d(*_):
        state.config["depth_track_ratio"] = round(dv.get(), 2)
        dl.config(text=f"{dv.get():.2f}")
        debounce_refresh()

    tk.Scale(dialog, from_=0.1, to=1.0, resolution=0.05, orient="horizontal",
             variable=dv, length=420, showvalue=False, command=upd_d).pack(padx=20)

    tk.Label(dialog, text="曲线道宽度比例:", font=("微软雅黑", 9)).pack(anchor="w", **pad)
    cv = tk.DoubleVar(value=state.config["curve_track_ratio"])
    cl = tk.Label(dialog, text=f"{cv.get():.2f}", font=("微软雅黑", 8), fg="#06c")
    cl.pack(anchor="w", padx=20)

    def upd_c(*_):
        state.config["curve_track_ratio"] = round(cv.get(), 2)
        cl.config(text=f"{cv.get():.2f}")
        debounce_refresh()

    tk.Scale(dialog, from_=0.5, to=3.0, resolution=0.1, orient="horizontal",
             variable=cv, length=420, showvalue=False, command=upd_c).pack(padx=20)

    # ===== 分隔线 =====
    ttk.Separator(dialog, orient="horizontal").pack(fill="x", padx=20, pady=12)

    # ===== 水平网格线 =====
    tk.Label(dialog, text="水平网格线 (y轴):", font=("微软雅黑", 9, "bold")).pack(anchor="w", **pad)
    hg = state.config.setdefault("grid", {}).setdefault("horizontal", {})

    hg_frame = tk.Frame(dialog)
    hg_frame.pack(padx=20, pady=2, fill="x")
    hg_enabled = tk.BooleanVar(value=hg.get("enabled", True))
    tk.Checkbutton(hg_frame, text="启用", variable=hg_enabled,
                   font=("微软雅黑", 8),
                   command=lambda: (hg.__setitem__("enabled", hg_enabled.get()),
                                    debounce_refresh())).pack(side="left")

    tk.Label(hg_frame, text="颜色:", font=("微软雅黑", 8)).pack(side="left", padx=(10, 2))
    hg_color_var = tk.StringVar(value=hg.get("color", "#cccccc"))
    hg_color_btn = tk.Button(hg_frame, text="  ", bg=hg_color_var.get(),
                             width=2, command=lambda: _pick_color(hg_color_var, hg_color_btn))
    hg_color_btn.pack(side="left", padx=2)

    def _apply_hg_color(*_):
        hg["color"] = hg_color_var.get()
        hg_color_btn.config(bg=hg_color_var.get())
        debounce_refresh()

    hg_color_var.trace_add("write", lambda *_: _apply_hg_color())

    tk.Label(hg_frame, text="粗细:", font=("微软雅黑", 8)).pack(side="left", padx=(10, 2))
    hg_wv = tk.DoubleVar(value=hg.get("linewidth", 0.3))
    tk.Scale(hg_frame, from_=0.1, to=2.0, resolution=0.1, orient="horizontal",
             variable=hg_wv, length=120, showvalue=False,
             command=lambda *_: (hg.__setitem__("linewidth", round(hg_wv.get(), 1)),
                                 debounce_refresh())).pack(side="left")
    tk.Label(hg_frame, textvariable=hg_wv, font=("微软雅黑", 8), fg="#06c",
             width=3).pack(side="left")

    # ===== 垂直网格线 =====
    tk.Label(dialog, text="垂直网格线 (x轴):", font=("微软雅黑", 9, "bold")).pack(anchor="w", **pad)
    vg = state.config.setdefault("grid", {}).setdefault("vertical", {})

    vg_frame1 = tk.Frame(dialog)
    vg_frame1.pack(padx=20, pady=2, fill="x")
    vg_enabled = tk.BooleanVar(value=vg.get("enabled", True))
    tk.Checkbutton(vg_frame1, text="启用", variable=vg_enabled,
                   font=("微软雅黑", 8),
                   command=lambda: (vg.__setitem__("enabled", vg_enabled.get()),
                                    debounce_refresh())).pack(side="left")

    tk.Label(vg_frame1, text="颜色:", font=("微软雅黑", 8)).pack(side="left", padx=(10, 2))
    vg_color_var = tk.StringVar(value=vg.get("color", "#cccccc"))
    vg_color_btn = tk.Button(vg_frame1, text="  ", bg=vg_color_var.get(),
                             width=2, command=lambda: _pick_color(vg_color_var, vg_color_btn))
    vg_color_btn.pack(side="left", padx=2)

    def _apply_vg_color(*_):
        vg["color"] = vg_color_var.get()
        vg_color_btn.config(bg=vg_color_var.get())
        debounce_refresh()

    vg_color_var.trace_add("write", lambda *_: _apply_vg_color())

    tk.Label(vg_frame1, text="粗细:", font=("微软雅黑", 8)).pack(side="left", padx=(10, 2))
    vg_wv = tk.DoubleVar(value=vg.get("linewidth", 0.3))
    tk.Scale(vg_frame1, from_=0.1, to=2.0, resolution=0.1, orient="horizontal",
             variable=vg_wv, length=120, showvalue=False,
             command=lambda *_: (vg.__setitem__("linewidth", round(vg_wv.get(), 1)),
                                 debounce_refresh())).pack(side="left")
    tk.Label(vg_frame1, textvariable=vg_wv, font=("微软雅黑", 8), fg="#06c",
             width=3).pack(side="left")

    vg_frame2 = tk.Frame(dialog)
    vg_frame2.pack(padx=20, pady=2, fill="x")
    tk.Label(vg_frame2, text="刻度数:", font=("微软雅黑", 8)).pack(side="left")
    vg_num = tk.IntVar(value=vg.get("num_ticks", 5))
    tk.Spinbox(vg_frame2, from_=2, to=20, textvariable=vg_num, width=4,
               font=("微软雅黑", 8),
               command=lambda: (vg.__setitem__("num_ticks", vg_num.get()),
                                debounce_refresh())).pack(side="left", padx=4)
    vg_num.trace_add("write", lambda *_: (vg.__setitem__("num_ticks", vg_num.get()),
                                          debounce_refresh()))

    # ===== 底部按钮 =====
    bf = tk.Frame(dialog)
    bf.pack(pady=20)

    def reset_defaults():
        state.config["depth_track_ratio"] = 0.35
        state.config["curve_track_ratio"] = 1.0
        dv.set(0.35)
        cv.set(1.0)
        dl.config(text="0.35")
        cl.config(text="1.00")
        hg["enabled"] = True
        hg["color"] = "#cccccc"
        hg["linewidth"] = 0.3
        hg_enabled.set(True)
        hg_color_var.set("#cccccc")
        hg_wv.set(0.3)
        vg["enabled"] = True
        vg["color"] = "#cccccc"
        vg["linewidth"] = 0.3
        vg["num_ticks"] = 5
        vg_enabled.set(True)
        vg_color_var.set("#cccccc")
        vg_wv.set(0.3)
        vg_num.set(5)
        refresh_plot()

    tk.Button(bf, text="重置默认", command=reset_defaults,
              font=("微软雅黑", 10), width=12).pack(side="left", padx=5)
    tk.Button(bf, text="关闭", command=dialog.destroy,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)


# ==================== 曲线属性对话框 ====================


def _pick_color(color_var, color_btn):
    """打开颜色选择器并更新按钮背景。"""
    rgb, hex_color = colorchooser.askcolor(title="选择颜色",
                                           color=color_var.get())
    if hex_color:
        color_var.set(hex_color)
        color_btn.config(bg=hex_color)


def open_curve_properties():
    """打开曲线属性设置对话框。"""
    if state.las_data is None:
        messagebox.showwarning("提示", "请先导入 LAS 文件")
        return

    curves = list(state.las_data.keys()[1:])
    if not curves:
        messagebox.showwarning("提示", "没有可设置的曲线")
        return

    dialog = tk.Toplevel(root)
    dialog.title("曲线属性")
    dialog.geometry("440x460")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    # ===== 曲线选择 =====
    tk.Label(dialog, text="选择曲线:", font=("微软雅黑", 9)).pack(anchor="w", padx=20, pady=(12, 2))
    curve_var = tk.StringVar(value=curves[0])
    curve_combo = ttk.Combobox(dialog, textvariable=curve_var,
                               values=curves, state="readonly",
                               font=("微软雅黑", 10), width=30)
    curve_combo.pack(padx=20, pady=2)

    # ===== Family 提示 =====
    fam_label = tk.Label(dialog, text="", font=("微软雅黑", 8), fg="#888")
    fam_label.pack(anchor="w", padx=20)

    # ===== 属性编辑区 =====
    prop_frame = tk.Frame(dialog)
    prop_frame.pack(padx=20, pady=8, fill="x")

    # 当前曲线样式控件
    style_widgets = {}

    def _build_row(parent, label, row):
        f = tk.Frame(parent)
        f.grid(row=row, column=0, sticky="w", pady=3)
        tk.Label(f, text=label, font=("微软雅黑", 9), width=10, anchor="w").pack(side="left")
        return f

    # 左刻度
    row = 0
    f = _build_row(prop_frame, "左刻度:", row)
    left_var = tk.StringVar()
    tk.Entry(f, textvariable=left_var, width=12, font=("微软雅黑", 9)).pack(side="left")
    style_widgets["left"] = left_var

    # 右刻度
    row += 1
    f = _build_row(prop_frame, "右刻度:", row)
    right_var = tk.StringVar()
    tk.Entry(f, textvariable=right_var, width=12, font=("微软雅黑", 9)).pack(side="left")
    style_widgets["right"] = right_var

    # 线宽
    row += 1
    f = _build_row(prop_frame, "线宽:", row)
    lw_var = tk.DoubleVar(value=0.6)
    tk.Scale(f, from_=0.1, to=3.0, resolution=0.1, orient="horizontal",
             variable=lw_var, length=150, showvalue=False).pack(side="left")
    tk.Label(f, textvariable=lw_var, font=("微软雅黑", 8), fg="#06c", width=3).pack(side="left")
    style_widgets["linewidth"] = lw_var

    # 线型
    row += 1
    f = _build_row(prop_frame, "线型:", row)
    ls_var = tk.StringVar(value="-")
    ls_combo = ttk.Combobox(f, textvariable=ls_var,
                            values=["-", "--", "-.", ":"],
                            state="readonly", width=8, font=("微软雅黑", 9))
    ls_combo.pack(side="left")
    style_widgets["linestyle"] = ls_var

    # 颜色
    row += 1
    f = _build_row(prop_frame, "颜色:", row)
    color_var = tk.StringVar(value="#000000")
    color_btn = tk.Button(f, text="  ", bg=color_var.get(), width=3,
                          command=lambda: _pick_color(color_var, color_btn))
    color_btn.pack(side="left", padx=2)
    tk.Label(f, textvariable=color_var, font=("微软雅黑", 8), fg="#666").pack(side="left", padx=4)
    style_widgets["color"] = color_var

    # 刻度类型
    row += 1
    f = _build_row(prop_frame, "刻度类型:", row)
    scale_type_var = tk.StringVar(value="linear")
    st_combo = ttk.Combobox(f, textvariable=scale_type_var,
                            values=["linear", "log"],
                            state="readonly", width=8, font=("微软雅黑", 9))
    st_combo.pack(side="left")
    style_widgets["scale_type"] = scale_type_var

    # ===== 加载曲线当前值 =====
    def load_curve(curve_name):
        sty = state.get_curve_style(curve_name)
        fam = state.curve_family.get(curve_name, detect_family(curve_name))
        tpl = FAMILY_TEMPLATES[fam]
        fam_label.config(text=f"当前 Family: {fam} — {tpl['desc']}")

        left_var.set("" if sty["left"] is None else f"{sty['left']:g}")
        right_var.set("" if sty["right"] is None else f"{sty['right']:g}")
        lw_var.set(sty["linewidth"])
        ls_var.set(sty["linestyle"])
        hex_color = "#{:02x}{:02x}{:02x}".format(*[int(c) for c in sty["color"]])
        color_var.set(hex_color)
        color_btn.config(bg=hex_color)
        scale_type_var.set(sty["scale_type"])

    load_curve(curves[0])

    def on_curve_change(*_):
        load_curve(curve_var.get())

    curve_combo.bind("<<ComboboxSelected>>", on_curve_change)

    # ===== 实时应用 =====
    _curve_debounce = {"timer": None}

    def _apply_style_immediate(*_):
        """实时应用曲线样式到 curve_styles。"""
        curve = curve_var.get()
        if not curve:
            return
        over = {}
        lv = left_var.get().strip()
        rv = right_var.get().strip()
        if lv:
            try:
                over["left"] = float(lv)
            except ValueError:
                pass  # 忽略无效输入
        if rv:
            try:
                over["right"] = float(rv)
            except ValueError:
                pass
        over["linewidth"] = round(lw_var.get(), 1)
        over["linestyle"] = ls_var.get()
        hex_c = color_var.get()
        try:
            hex_c = hex_c.lstrip("#")
            over["color"] = (int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16))
        except (ValueError, IndexError):
            pass
        over["scale_type"] = scale_type_var.get()
        state.curve_styles[curve] = over
        status_bar.config(text=f"曲线 {curve} 样式已实时更新")

        if _curve_debounce["timer"] is not None:
            dialog.after_cancel(_curve_debounce["timer"])
        _curve_debounce["timer"] = dialog.after(80, refresh_plot)

    # 所有控件实时追踪
    left_var.trace_add("write", _apply_style_immediate)
    right_var.trace_add("write", _apply_style_immediate)
    lw_var.trace_add("write", _apply_style_immediate)
    ls_var.trace_add("write", _apply_style_immediate)
    color_var.trace_add("write", _apply_style_immediate)
    scale_type_var.trace_add("write", _apply_style_immediate)

    def reset_curve():
        curve = curve_var.get()
        state.curve_styles.pop(curve, None)
        load_curve(curve)
        refresh_plot()
        status_bar.config(text=f"曲线 {curve} 样式已恢复默认")

    bf = tk.Frame(dialog)
    bf.pack(pady=16)
    tk.Button(bf, text="恢复默认", command=reset_curve,
              font=("微软雅黑", 10), width=10).pack(side="left", padx=5)
    tk.Button(bf, text="关闭", command=dialog.destroy,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)


# ==================== PDF 导出对话框 ====================


def print_long_pdf():
    """打开长卷 PDF 打印对话框。"""
    if state.las_data is None:
        messagebox.showwarning("提示", "请先导入 LAS 文件")
        return
    dialog = tk.Toplevel(root)
    dialog.title("打印长卷 PDF")
    dialog.geometry("400x320")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    tk.Label(dialog, text="长卷 PDF 打印设置",
             font=("微软雅黑", 12, "bold")).pack(pady=15)

    d_min_full = state.las_data.well.STRT.value
    d_max_full = state.las_data.well.STOP.value

    tk.Label(dialog, text="深度比例 (英寸/米):", font=("微软雅黑", 9)).pack(anchor="w", padx=20)
    sv = tk.DoubleVar(value=state.current_scale)
    sl = tk.Label(dialog, text=f"{sv.get():.3f}", font=("微软雅黑", 8), fg="#06c")
    sl.pack(anchor="w", padx=20)
    tk.Scale(dialog, from_=0.005, to=1.0, resolution=0.001, orient="horizontal",
             variable=sv, length=350, showvalue=False,
             command=lambda *_: sl.config(text=f"{sv.get():.3f}")).pack(padx=20)
    tk.Label(dialog, text="1:5000 yue 0.008, 1000m->0.2",
             font=("微软雅黑", 7), fg="#888").pack(anchor="w", padx=20)

    rf = tk.Frame(dialog)
    rf.pack(pady=12, padx=20, fill="x")
    tk.Label(rf, text="深度范围:", font=("微软雅黑", 9)).pack(side="left")
    fv = tk.DoubleVar(value=round(d_min_full, 1))
    tv = tk.DoubleVar(value=round(d_max_full, 1))
    tk.Entry(rf, textvariable=fv, width=8).pack(side="left", padx=5)
    tk.Label(rf, text="~").pack(side="left")
    tk.Entry(rf, textvariable=tv, width=8).pack(side="left", padx=5)

    def do_export():
        fp = filedialog.asksaveasfilename(
            title="保存 PDF", defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")])
        if not fp:
            return
        try:
            fig = build_log_plot(sv.get(), from_depth=fv.get(),
                                 to_depth=tv.get(), for_print=True)
            if fig is None:
                messagebox.showerror("错误", "无法生成图形")
                return
            with PdfPages(fp) as pp:
                pp.savefig(fig, dpi=200)
            plt.close(fig)
            messagebox.showinfo("完成", f"PDF 已保存:\n{fp}")
            dialog.destroy()
        except Exception as e:
            messagebox.showerror("导出失败", f"{e}")

    bf = tk.Frame(dialog)
    bf.pack(pady=10)
    tk.Button(bf, text="导出 PDF", command=do_export,
              font=("微软雅黑", 10), width=12).pack(side="left", padx=5)
    tk.Button(bf, text="取消", command=dialog.destroy,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)


# ==================== Family 编辑对话框 ====================


def edit_family(event):
    """处理树的双击事件，弹出 Family 编辑对话框。"""
    item = tree.identify_row(event.y)
    if not item:
        return
    vals = tree.item(item, "values")
    if not vals or vals[0] != "curve":
        return
    curve = vals[1]
    cur_fam = state.curve_family.get(curve, detect_family(curve))

    dialog = tk.Toplevel(root)
    dialog.title("修改 Family")
    dialog.geometry("300x190")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    tk.Label(dialog, text=f"曲线: {curve}",
             font=("微软雅黑", 11, "bold")).pack(pady=12)
    tk.Label(dialog, text="选择 Family:", font=("微软雅黑", 9)).pack()

    fam_var = tk.StringVar(value=cur_fam)
    combo = ttk.Combobox(dialog, textvariable=fam_var,
                         values=list(FAMILY_TEMPLATES.keys()),
                         state="readonly", font=("微软雅黑", 10), width=15)
    combo.pack(pady=8)

    desc_lbl = tk.Label(dialog, text="", font=("微软雅黑", 8), fg="#06c")
    desc_lbl.pack()

    def show_desc(*_):
        tpl = FAMILY_TEMPLATES[fam_var.get()]
        sc = "对数" if tpl["scale_type"] == "log" else "线性"
        rng = f"{tpl['left']}~{tpl['right']}" if tpl["left"] is not None else "自动"
        desc_lbl.config(text=f"刻度 {rng} | {sc}")

    combo.bind("<<ComboboxSelected>>", show_desc)
    show_desc()

    def apply_fam():
        state.curve_family[curve] = fam_var.get()
        update_tree()
        refresh_plot()
        dialog.destroy()

    bf = tk.Frame(dialog)
    bf.pack(pady=12)
    tk.Button(bf, text="应用", command=apply_fam,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)
    tk.Button(bf, text="取消", command=dialog.destroy,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)


# ==================== 表格工具 ====================


def _tree_drag_start(event):
    """开始拖拽曲线。"""
    item = tree.identify_row(event.y)
    if not item:
        return
    vals = tree.item(item, "values")
    if not vals or vals[0] != "curve":
        return
    _drag_data["curve"] = vals[1]
    _drag_data["start_x"] = event.x_root
    _drag_data["start_y"] = event.y_root
    _drag_data["dragging"] = False


def _tree_drag_motion(event):
    """拖拽过程中判断是否为有效拖拽（移动超过10像素则判定为拖拽）。"""
    if _drag_data["curve"] is None:
        return
    dx = abs(event.x_root - _drag_data["start_x"])
    dy = abs(event.y_root - _drag_data["start_y"])
    if dx > 10 or dy > 10:
        _drag_data["dragging"] = True


def _tree_drag_drop(event):
    """拖拽释放：表格工具 / 图版模式 的拖拽处理。"""
    if not _drag_data["dragging"] or _drag_data["curve"] is None:
        _drag_data["curve"] = None
        _drag_data["dragging"] = False
        return

    curve = _drag_data["curve"]
    _drag_data["curve"] = None
    _drag_data["dragging"] = False

    # ---- 表格工具 ----
    if _table_window is not None and _table_window.winfo_exists():
        tx = event.x_root - _table_window.winfo_rootx()
        ty = event.y_root - _table_window.winfo_rooty()
        if 0 <= tx <= _table_window.winfo_width() and 0 <= ty <= _table_window.winfo_height():
            _add_curve_to_table(curve)
            return

    # ---- 测井曲线图图版模式 ----
    if _plate_mode == "log":
        _handle_log_plate_drop(event, curve)
        return

    # ---- 交汇图图版模式 ----
    if _plate_mode == "crossplot" and _xp_window is not None and _xp_window.winfo_exists():
        _handle_crossplot_drop(event, curve)
        return


def _handle_log_plate_drop(event, curve):
    """处理测井曲线图图版的曲线拖放。"""
    # 检测释放位置是否在 plot_frame 内
    pf_x = plot_frame.winfo_rootx()
    pf_y = plot_frame.winfo_rooty()
    pf_w = plot_frame.winfo_width()
    pf_h = plot_frame.winfo_height()

    rx = event.x_root - pf_x
    ry = event.y_root - pf_y

    if not (0 <= rx <= pf_w and 0 <= ry <= pf_h):
        return

    # 没有图道 → 直接创建第一道
    if not state.tracks:
        state.tracks.append([curve])
        refresh_plot()
        return

    # 已有图道 → 弹出右键菜单让用户选择"新建道"或"添加到已有道"
    menu = tk.Menu(root, tearoff=0, font=("微软雅黑", 9))
    menu.add_command(label=f"📌 新建图道 [{curve}]",
                     command=lambda: _add_new_track(curve))
    menu.add_separator()
    for ti, clist in enumerate(state.tracks):
        label = f"  道{ti+1}: {', '.join(clist)}"
        menu.add_command(label=f"➕ {label}",
                         command=lambda t=ti: _append_to_track(t, curve))
    # 在鼠标位置弹出
    menu.post(event.x_root, event.y_root)


def _add_new_track(curve):
    """新建一个图道。"""
    state.tracks.append([curve])
    refresh_plot()


def _append_to_track(t_idx, curve):
    """添加到已有图道。"""
    if curve not in state.tracks[t_idx]:
        state.tracks[t_idx].append(curve)
    refresh_plot()


def _handle_crossplot_drop(event, curve):
    """处理交汇图图版的曲线拖放。"""

    def _in_widget(widget):
        if widget is None:
            return False
        wx = widget.winfo_rootx()
        wy = widget.winfo_rooty()
        ww = widget.winfo_width()
        wh = widget.winfo_height()
        x = event.x_root
        y = event.y_root
        return wx <= x <= wx + ww and wy <= y <= wy + wh

    if _in_widget(_xp_x_frame):
        _set_crossplot_axis("x", curve)
    elif _in_widget(_xp_y_frame):
        _set_crossplot_axis("y", curve)


def _add_curve_to_table(curve_name):
    """将曲线数据添加到表格。"""
    global _table_curves

    if curve_name in _table_curves:
        return  # 已存在，忽略

    _table_curves.append(curve_name)
    _rebuild_table()


def _remove_curve_from_table():
    """移除表格中选中的曲线。"""
    sel = _table_tree.selection()
    if not sel:
        return
    values = _table_tree.item(sel[0], "values")
    if not values:
        return
    # 第一列是 depth，点击的列确定是哪条曲线
    # 通过列 ID 判断
    col = _table_tree.identify_column(_table_tree.winfo_pointerx() - _table_tree.winfo_rootx())
    if not col:
        return
    col_idx = int(col.replace("#", "")) - 1  # 列号从1开始
    if col_idx <= 0 or col_idx >= len(_table_curves) + 1:
        return
    curve = _table_curves[col_idx - 1]
    _table_curves.remove(curve)
    _rebuild_table()


def _rebuild_table():
    """重建表格数据。"""
    global _table_tree, _table_curves

    for item in _table_tree.get_children():
        _table_tree.delete(item)

    if not _table_curves or state.las_data is None:
        return

    depth = state.las_data.index
    n = len(depth)

    columns = ["depth"] + _table_curves
    _table_tree["columns"] = columns
    _table_tree["displaycolumns"] = columns

    _table_tree.heading("depth", text="Depth (m)")
    _table_tree.column("depth", width=80, anchor="e", minwidth=60)

    for c in _table_curves:
        _table_tree.heading(c, text=c)
        _table_tree.column(c, width=100, anchor="e", minwidth=60)

    # 最多显示 5000 行，避免表格卡顿
    step = max(1, n // 5000)

    for i in range(0, n, step):
        row = [f"{depth[i]:.2f}"]
        for c in _table_curves:
            data = get_curve_data(c)
            v = data[i]
            row.append(f"{v:.4f}" if not np.isnan(v) else "")
        _table_tree.insert("", "end", values=row)


def open_table_tool():
    """打开表格工具窗口。"""
    global _table_window, _table_tree, _table_curves

    if state.las_data is None:
        messagebox.showwarning("提示", "请先导入 LAS 文件")
        return

    if _table_window is not None and _table_window.winfo_exists():
        _table_window.lift()
        return

    _table_window = tk.Toplevel(root)
    _table_window.title("数据表格工具")
    _table_window.geometry("650x450")
    _table_window.transient(root)

    # 顶部提示
    hint_frame = tk.Frame(_table_window, bg="#f0f0f0")
    hint_frame.pack(fill="x")
    tk.Label(hint_frame,
             text="从左侧数据浏览器的曲线拖拽到此处，即可显示数据",
             font=("微软雅黑", 9), fg="#666", bg="#f0f0f0",
             padx=8, pady=6).pack(side="left")

    # 操作按钮
    btn_frame = tk.Frame(_table_window, bg="#f0f0f0")
    btn_frame.pack(side="bottom", fill="x")
    tk.Button(btn_frame, text="移除选中曲线", command=_remove_curve_from_table,
              font=("微软雅黑", 9)).pack(side="left", padx=6, pady=4)
    tk.Button(btn_frame, text="清空表格", command=_clear_table,
              font=("微软雅黑", 9)).pack(side="left", padx=6, pady=4)
    tk.Label(btn_frame, text="右键点击列头可排序", font=("微软雅黑", 8),
             fg="#999", bg="#f0f0f0").pack(side="right", padx=10)

    # 表格框架
    table_frame = tk.Frame(_table_window)
    table_frame.pack(fill="both", expand=True, padx=4, pady=4)

    v_scroll = tk.Scrollbar(table_frame, orient="vertical")
    v_scroll.pack(side="right", fill="y")

    h_scroll = tk.Scrollbar(table_frame, orient="horizontal")
    h_scroll.pack(side="bottom", fill="x")

    _table_tree = ttk.Treeview(table_frame, show="headings",
                                yscrollcommand=v_scroll.set,
                                xscrollcommand=h_scroll.set)
    _table_tree.pack(side="left", fill="both", expand=True)
    v_scroll.config(command=_table_tree.yview)
    h_scroll.config(command=_table_tree.xview)

    # 支持右键菜单排序（Treeview 内置排序需按列点击）
    for col_id in _table_tree["columns"]:
        _table_tree.heading(col_id, command=lambda c=col_id: _sort_table_column(c, False))

    # 恢复已有数据
    if _table_curves:
        _rebuild_table()

    def _on_close():
        global _table_window, _table_tree, _table_curves
        _table_window.destroy()
        _table_window = None
        _table_tree = None
        _table_curves = []

    _table_window.protocol("WM_DELETE_WINDOW", _on_close)


def _clear_table():
    """清空表格所有数据。"""
    global _table_curves
    _table_curves = []
    if _table_tree is not None:
        for item in _table_tree.get_children():
            _table_tree.delete(item)
        _table_tree["columns"] = []
        _table_tree["displaycolumns"] = []


_sort_order = {}
def _sort_table_column(col_id, reverse=False):
    """按列排序表格。"""
    rows = [(_table_tree.set(child, col_id), child) for child in _table_tree.get_children("")]
    rows.sort(key=lambda x: _sort_key(x[0]), reverse=reverse)
    for idx, (_, child) in enumerate(rows):
        _table_tree.move(child, "", idx)
    _sort_order[col_id] = not reverse
    _table_tree.heading(col_id,
                        command=lambda: _sort_table_column(col_id, _sort_order.get(col_id, False)))


def _sort_key(val):
    """排序键：尝试转为数字，失败则用原字符串。"""
    try:
        return float(val) if val else float("-inf")
    except ValueError:
        return val


# ==================== 图版模式功能 ====================


def _show_log_plate_empty():
    """显示空测井曲线图图版（无图道时的占位符）。"""
    for widget in plot_frame.winfo_children():
        widget.destroy()

    plate = tk.Frame(plot_frame, bg="white", bd=2, relief="groove")
    plate.pack(fill="both", expand=True, padx=15, pady=15)

    # 图头区
    hdr = tk.Frame(plate, bg="#f0f0f0", height=55, bd=1, relief="sunken")
    hdr.pack(fill="x", padx=2, pady=(2, 1))
    hdr.pack_propagate(False)
    tk.Label(hdr, text="图头区", bg="#f0f0f0", fg="#888",
             font=("微软雅黑", 11, "bold")).pack(expand=True)

    # 图道区
    trk = tk.Frame(plate, bg="#fafafa", bd=1, relief="sunken")
    trk.pack(fill="both", expand=True, padx=2, pady=(1, 2))
    tk.Label(trk, text="图道区（空白）\n\n从左侧【数据浏览器】拖拽曲线到此处开始绘图",
             bg="#fafafa", fg="#bbb", font=("微软雅黑", 14)).pack(expand=True)

    # 底部关闭按钮
    tk.Button(plate, text="关闭图版", command=_close_plot,
              font=("微软雅黑", 9), padx=10, fg="red").pack(pady=6)

    plot_frame.update_idletasks()


def open_log_plate():
    """打开测井曲线图图版。"""
    global _plate_mode
    if state.las_data is None:
        messagebox.showwarning("提示", "请先导入 LAS 文件")
        return

    _plate_mode = "log"
    state.reset_view_state()
    state.tracks = []
    _show_log_plate_empty()
    status_bar.config(text="测井曲线图图版 | 拖拽目录树中的曲线到绘图区")


def _close_xp_window():
    """关闭交汇图图版窗口。"""
    global _xp_window, _xp_fig, _xp_canvas, _xp_x_curve, _xp_y_curve, _plate_mode
    if _xp_fig is not None:
        plt.close(_xp_fig)
        _xp_fig = None
    _xp_canvas = None
    _xp_x_curve = None
    _xp_y_curve = None
    if _xp_window is not None:
        try:
            _xp_window.destroy()
        except tk.TclError:
            pass
        _xp_window = None
    _plate_mode = None


def _set_crossplot_axis(axis, curve):
    """设置交汇图的 X 或 Y 轴曲线。"""
    global _xp_x_curve, _xp_y_curve
    if axis == "x":
        _xp_x_curve = curve
        _xp_x_frame.config(text=f"  X轴: {curve}", fg="#000", font=("微软雅黑", 10, "bold"))
    else:
        _xp_y_curve = curve
        _xp_y_frame.config(text=f"  Y轴: {curve}", fg="#000", font=("微软雅黑", 10, "bold"))
    _update_crossplot()


def _update_crossplot():
    """更新交汇图散点图。"""
    global _xp_fig, _xp_canvas
    if _xp_x_curve is None or _xp_y_curve is None:
        return

    try:
        x_data = get_curve_data(_xp_x_curve)
        y_data = get_curve_data(_xp_y_curve)

        if _xp_fig is not None:
            plt.close(_xp_fig)
            _xp_fig = None

        _xp_fig = plt.Figure(figsize=(5.5, 4.5), dpi=100)
        ax = _xp_fig.add_subplot(111)
        ax.scatter(x_data, y_data, s=1.5, c="#0066cc", alpha=0.6, edgecolors="none")
        ax.set_xlabel(_xp_x_curve, fontsize=9)
        ax.set_ylabel(_xp_y_curve, fontsize=9)
        ax.set_title(f"{_xp_y_curve}  vs  {_xp_x_curve}", fontsize=10)
        ax.grid(True, alpha=0.3, linewidth=0.3)

        # 检查刻度类型
        from state import get_curve_style
        x_sty = get_curve_style(_xp_x_curve)
        y_sty = get_curve_style(_xp_y_curve)
        if x_sty["scale_type"] == "log":
            ax.set_xscale("log")
        if y_sty["scale_type"] == "log":
            ax.set_yscale("log")

        _xp_fig.tight_layout()

        if _xp_canvas is not None:
            _xp_canvas.get_tk_widget().destroy()
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        _xp_canvas = FigureCanvasTkAgg(_xp_fig, master=_xp_window)
        _xp_canvas.draw()
        _xp_canvas.get_tk_widget().pack(side="right", fill="both", expand=True, padx=4, pady=4)
    except Exception as e:
        messagebox.showerror("交汇图错误", f"绘制交汇图失败:\n{e}")


def open_crossplot_plate():
    """打开交汇图图版窗口。"""
    global _xp_window, _xp_x_frame, _xp_y_frame, _xp_x_curve, _xp_y_curve, _plate_mode

    if state.las_data is None:
        messagebox.showwarning("提示", "请先导入 LAS 文件")
        return

    # 关闭已有的
    _close_xp_window()

    _plate_mode = "crossplot"
    _xp_x_curve = None
    _xp_y_curve = None

    _xp_window = tk.Toplevel(root)
    _xp_window.title("交汇图图版")
    _xp_window.geometry("900x550")
    _xp_window.transient(root)

    # 左侧面板
    left_panel = tk.Frame(_xp_window, width=220, bg="#f5f5f5", bd=1, relief="sunken")
    left_panel.pack(side="left", fill="y", padx=4, pady=4)
    left_panel.pack_propagate(False)

    tk.Label(left_panel, text="    交汇图设置",
             bg="#f5f5f5", font=("微软雅黑", 11, "bold")).pack(anchor="w", padx=10, pady=(12, 4))
    ttk.Separator(left_panel, orient="horizontal").pack(fill="x", padx=8, pady=4)

    # X轴拖放区
    tk.Label(left_panel, text="X 轴曲线:", bg="#f5f5f5",
             font=("微软雅黑", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
    _xp_x_frame = tk.LabelFrame(left_panel,
                                 text="  拖拽 X 轴曲线到此处",
                                 font=("微软雅黑", 9), fg="#999",
                                 height=50, bg="white", bd=2, relief="groove")
    _xp_x_frame.pack(fill="x", padx=10, pady=2)
    _xp_x_frame.pack_propagate(False)

    # Y轴拖放区
    tk.Label(left_panel, text="Y 轴曲线:", bg="#f5f5f5",
             font=("微软雅黑", 9, "bold")).pack(anchor="w", padx=10, pady=(12, 2))
    _xp_y_frame = tk.LabelFrame(left_panel,
                                 text="  拖拽 Y 轴曲线到此处",
                                 font=("微软雅黑", 9), fg="#999",
                                 height=50, bg="white", bd=2, relief="groove")
    _xp_y_frame.pack(fill="x", padx=10, pady=2)
    _xp_y_frame.pack_propagate(False)

    # 操作按钮
    btn_frame = tk.Frame(left_panel, bg="#f5f5f5")
    btn_frame.pack(fill="x", padx=10, pady=(20, 4))

    def _clear_xp():
        global _xp_x_curve, _xp_y_curve
        _xp_x_curve = None
        _xp_y_curve = None
        _xp_x_frame.config(text="  拖拽 X 轴曲线到此处",
                           fg="#999", font=("微软雅黑", 9))
        _xp_y_frame.config(text="  拖拽 Y 轴曲线到此处",
                           fg="#999", font=("微软雅黑", 9))
        if _xp_canvas is not None:
            _xp_canvas.get_tk_widget().destroy()
            _xp_canvas = None
        if _xp_fig is not None:
            plt.close(_xp_fig)
            _xp_fig = None

    tk.Button(btn_frame, text="清空", command=_clear_xp,
              font=("微软雅黑", 9), width=8).pack(side="left", padx=2)
    tk.Button(btn_frame, text="关闭", command=_close_xp_window,
              font=("微软雅黑", 9), width=8, fg="red").pack(side="right", padx=2)

    _xp_window.protocol("WM_DELETE_WINDOW", _close_xp_window)


# ==================== 主窗口入口 ====================


def main():
    """启动应用程序主窗口。"""
    global root, plot_frame, tree, status_bar

    root = tk.Tk()
    root.title("BoreholeGuard - 测井可视化工具")
    root.geometry("1200x800")

    # ---- 菜单栏 ----
    menubar = tk.Menu(root)

    # 文件菜单
    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(label="导入 LAS 文件 (Ctrl+O)", command=import_las)
    file_menu.add_command(label="打印长卷 PDF (Ctrl+P)", command=print_long_pdf)
    file_menu.add_separator()
    file_menu.add_command(label="退出 (Ctrl+Q)", command=root.quit)
    menubar.add_cascade(label="文件", menu=file_menu)

    # 属性菜单
    prop_menu = tk.Menu(menubar, tearoff=0)
    prop_menu.add_command(label="井属性", command=open_well_properties)
    prop_menu.add_command(label="道属性", command=open_track_properties)
    prop_menu.add_command(label="曲线属性", command=open_curve_properties)
    menubar.add_cascade(label="属性", menu=prop_menu)

    # 工具菜单
    tool_menu = tk.Menu(menubar, tearoff=0)
    tool_menu.add_command(label="表格工具", command=open_table_tool)
    menubar.add_cascade(label="工具", menu=tool_menu)

    # 图版菜单
    plate_menu = tk.Menu(menubar, tearoff=0)
    plate_menu.add_command(label="测井曲线图图版", command=open_log_plate)
    plate_menu.add_command(label="交汇图图版", command=open_crossplot_plate)
    menubar.add_cascade(label="图版", menu=plate_menu)

    # 帮助菜单
    help_menu = tk.Menu(menubar, tearoff=0)
    help_menu.add_command(
        label="关于",
        command=lambda: messagebox.showinfo(
            "关于", "BoreholeGuard v1.2\n轻量级开源测井可视化工具"))
    menubar.add_cascade(label="帮助", menu=help_menu)
    root.config(menu=menubar)

    # ---- 快捷键 ----
    root.bind("<Control-o>", lambda e: import_las())
    root.bind("<Control-p>", lambda e: print_long_pdf())
    root.bind("<Control-q>", lambda e: root.quit())
    root.bind("<Left>", on_key_left)
    root.bind("<Right>", on_key_right)
    root.bind("<Escape>", cancel_active)
    root.bind("<ButtonRelease-1>", _tree_drag_drop)

    # ---- 主面板 ----
    main_pane = tk.PanedWindow(root, orient="horizontal", sashwidth=4, bg="#ccc")
    main_pane.pack(fill="both", expand=True)

    left_frame = tk.Frame(main_pane, width=240, bg="#f5f5f5")
    tk.Label(left_frame, text="数据浏览器", bg="#f5f5f5",
             font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=8, pady=6)
    tree = ttk.Treeview(left_frame, show="tree")
    tree.pack(fill="both", expand=True, padx=4, pady=4)
    tree.bind("<Double-1>", edit_family)
    # 拖拽事件绑定（用于表格工具）
    tree.bind("<ButtonPress-1>", _tree_drag_start)
    tree.bind("<B1-Motion>", _tree_drag_motion)
    main_pane.add(left_frame)

    plot_frame = tk.Frame(main_pane, bg="white")
    main_pane.add(plot_frame)

    tk.Label(plot_frame, text="请通过 文件 - 导入 LAS 文件 开始",
             bg="white", fg="#999", font=("微软雅黑", 12)).pack(expand=True)

    # ---- 状态栏 ----
    status_bar = tk.Label(root, text="就绪 | 请导入 LAS 文件",
                          bd=1, relief="sunken", anchor="w", font=("微软雅黑", 9))
    status_bar.pack(side="bottom", fill="x")

    root.mainloop()
