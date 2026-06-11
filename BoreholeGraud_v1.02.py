import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import lasio
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import os

# ==================== 全局变量 ====================
las_data = None
file_path = ""
current_fig = None
current_canvas = None

tracks = []            # 道布局，如 [["GR"], ["RT"], ["RXO"]]
active_curve = None    # 当前激活的曲线名
active_track = None    # 当前激活的道索引（数据道，从0起）
pick_map = []          # 命中信息列表

config = {
    "header_height": round(3.0 / 2.54, 3),
    "depth_track_ratio": 0.35,
    "curve_track_ratio": 1.0,
    "max_data_height": 35,
}

current_scale = 0.008

# ==================== Family 模板库 ====================
FAMILY_TEMPLATES = {
    "GR":  {"left": 0.0,  "right": 200.0, "scale_type": "linear",
            "color": (0, 128, 0),  "desc": "ziran gamma"},
    "RT":  {"left": 0.2,  "right": 200.0, "scale_type": "log",
            "color": (240, 0, 0),  "desc": "diceng dianzulv"},
    "RXO": {"left": 0.2,  "right": 200.0, "scale_type": "log",
            "color": (0, 0, 240),  "desc": "chongxidai dianzulv"},
    "default": {"left": None, "right": None, "scale_type": "linear",
                "color": (0, 0, 0), "desc": "weifenlei"},
}

curve_family = {}


def rgb_to_mpl(rgb):
    return tuple(c / 255.0 for c in rgb)


def detect_family(curve_name):
    name = curve_name.upper()
    if "RXO" in name:
        return "RXO"
    if "RT" in name:
        return "RT"
    if "GR" in name:
        return "GR"
    return "default"


def get_curve_data(curve):
    raw = las_data[curve]
    return raw if isinstance(raw, np.ndarray) else raw.values


def get_curve_unit(curve):
    raw = las_data[curve]
    return raw.unit if (hasattr(raw, 'unit') and raw.unit) else ''


# 固定布局参数
FIG_WIDTH = 11.7
MARGIN_TOP = 0.4
MARGIN_BOTTOM = 0.2
MARGIN_LEFT = 0.03
MARGIN_RIGHT = 0.98
PREVIEW_DPI = 80


def compute_track_x(n_data_tracks):
    dr = config["depth_track_ratio"]
    cr = config["curve_track_ratio"]
    ratios = [dr] + [cr] * n_data_tracks
    total_ratio = sum(ratios)
    avail = MARGIN_RIGHT - MARGIN_LEFT
    boxes = []
    x = MARGIN_LEFT
    for r in ratios:
        w = avail * (r / total_ratio)
        boxes.append((x, w))
        x += w
    return boxes

def build_log_plot(scale_factor, from_depth=None, to_depth=None, interactive=False, for_print=False):
    global las_data, config, curve_family, tracks, pick_map
    if las_data is None:
        return None

    las = las_data
    depth = las.index
    pick_map = []

    n_data = len(tracks)            # 数据道数量
    n_tracks = 1 + n_data           # 加深度道

    d_min_full = las.well.STRT.value
    d_max_full = las.well.STOP.value
    d_min = from_depth if from_depth is not None else d_min_full
    d_max = to_depth if to_depth is not None else d_max_full
    if d_max <= d_min:
        d_min, d_max = d_min_full, d_max_full
    d_range = d_max - d_min

    header_h = config["header_height"]
    data_h = max(8, d_range * scale_factor)

    if not for_print:
        data_h = min(data_h, 300)

    total_h = MARGIN_TOP + header_h + data_h + MARGIN_BOTTOM
    fig = plt.figure(figsize=(FIG_WIDTH, total_h))

    data_y0 = MARGIN_BOTTOM / total_h
    data_y1 = (MARGIN_BOTTOM + data_h) / total_h
    head_y0 = data_y1
    head_y1 = (MARGIN_BOTTOM + data_h + header_h) / total_h
    data_axes_height = data_y1 - data_y0
    head_axes_height = head_y1 - head_y0

    boxes = compute_track_x(n_data)

    step = 50 if d_range > 200 else 20
    ticks = np.arange(np.ceil(d_min / step) * step, d_max + step, step)

    header_axes = []
    data_axes = []
    for i in range(n_tracks):
        x, w = boxes[i]
        ax_h = fig.add_axes([x, head_y0, w, head_axes_height])
        ax_d = fig.add_axes([x, data_y0, w, data_axes_height])
        header_axes.append(ax_h)
        data_axes.append(ax_d)

    for ax in data_axes:
        ax.set_ylim(d_max, d_min)

    # ---- 深度道图头 ----
    ax_h0 = header_axes[0]
    ax_h0.set_xlim(0, 1)
    ax_h0.set_ylim(0, 1)
    ax_h0.axis('off')
    rect0 = plt.Rectangle((0, 0), 1, 1, linewidth=0.8, edgecolor='black',
                          facecolor='#F0F0F0', transform=ax_h0.transAxes, zorder=10)
    ax_h0.add_patch(rect0)

    ax_h0.text(0.5, 0.7, "DEPTH", fontsize=7, fontweight='bold',
               ha='center', va='center', zorder=11)
    ax_h0.text(0.5, 0.45, "(m)", fontsize=5.5, ha='center', va='center', zorder=11)
    ratio_n = int(round(1.0 / (scale_factor * 0.0254)))
    ax_h0.text(0.5, 0.18, f"1:{ratio_n}", fontsize=5,
               ha='center', va='center', color='#c00', zorder=11)


    # ---- 各数据道图头（每道可能多条曲线，每条一行：曲线名 + 示例线）----
    for t_idx, curve_list in enumerate(tracks):
        ax_h = header_axes[t_idx + 1]
        ax_h.set_xlim(0, 1)
        ax_h.set_ylim(0, 1)
        ax_h.axis('off')
        is_active_track = (active_track == t_idx)
        rect = plt.Rectangle((0, 0), 1, 1,
                             linewidth=2.0 if is_active_track else 0.8,
                             edgecolor='red' if is_active_track else 'black',
                             facecolor='#F0F0F0', transform=ax_h.transAxes, zorder=10)
        ax_h.add_patch(rect)
        # 记录"道空白区"命中（用于激活整道）
        x0, w0 = boxes[t_idx + 1]
        pick_map.append({"type": "track", "idx": t_idx,
                         "x0": x0, "x1": x0 + w0,
                         "y0": head_y0, "y1": head_y1})

        n_c = len(curve_list)
        if n_c == 0:
            ax_h.text(0.5, 0.5, "(empty)", fontsize=6, color='#999',
                      ha='center', va='center', zorder=11)
            continue

        # 每条曲线分配一个竖向区间
        for ci, curve in enumerate(curve_list):
            fam = curve_family.get(curve, detect_family(curve))
            tpl = FAMILY_TEMPLATES[fam]
            color = rgb_to_mpl(tpl["color"])
            unit = get_curve_unit(curve)
            label = f"{curve} ({unit})" if unit else curve
            # 区间：从上往下排
            top = 1.0 - ci * (1.0 / n_c)
            bot = 1.0 - (ci + 1) * (1.0 / n_c)
            mid = (top + bot) / 2
            name_y = mid + 0.18 * (top - bot)
            line_y = mid - 0.22 * (top - bot)

            is_active = (curve == active_curve)
            ax_h.text(0.5, name_y, label, fontsize=6, fontweight='bold',
                      ha='center', va='center', color=color, zorder=12)
            # 示例线：从左铺到右
            ax_h.plot([0.0, 1.0], [line_y, line_y],
                      color=color, linewidth=2.5 if is_active else 1.3,
                      linestyle='--' if is_active else '-', zorder=12,
                      clip_on=False)
            # 只显示左右两端刻度值（贴在线段两端、线的上方一点）
            left = tpl["left"] if tpl["left"] is not None else np.nanmin(get_curve_data(curve))
            right = tpl["right"] if tpl["right"] is not None else np.nanmax(get_curve_data(curve))
            txt_y = line_y + 0.12 * (top - bot)
            ax_h.text(0.02, txt_y, f"{left:g}", fontsize=4.5,
                      ha='left', va='center', color=color, zorder=12)
            ax_h.text(0.98, txt_y, f"{right:g}", fontsize=4.5,
                      ha='right', va='center', color=color, zorder=12)
            # 命中范围 = 整个道宽
            pick_map.append({"type": "curve", "curve": curve,
                             "x0": x0, "x1": x0 + w0,
                             "y0": head_y0 + head_axes_height * (line_y - 0.08),
                             "y1": head_y0 + head_axes_height * (line_y + 0.08)})



    # ---- 深度道数据 ----
    ax_d0 = data_axes[0]
    ax_d0.set_xlim(0, 1)
    ax_d0.set_xticks([])
    ax_d0.set_yticks([])
    ax_d0.set_ylim(d_max, d_min)
    # 左右边框竖线
    ax_d0.axvline(x=0, color='black', linewidth=0.6)
    ax_d0.axvline(x=1, color='black', linewidth=0.6)
    # 每个刻度：左右各画一小段横刻度线，深度数字居中
    for tk_val in ticks:
        if tk_val < d_min or tk_val > d_max:
            continue
        ax_d0.plot([0.0, 0.18], [tk_val, tk_val], color='black', linewidth=0.6)
        ax_d0.plot([0.82, 1.0], [tk_val, tk_val], color='black', linewidth=0.6)
        ax_d0.text(0.5, tk_val, f"{int(tk_val)}", fontsize=6,
                   ha='center', va='center', color='black')


    # ---- 各数据道曲线 ----
    for t_idx, curve_list in enumerate(tracks):
        ax = data_axes[t_idx + 1]
        ax.set_ylim(d_max, d_min)
        ax.set_yticks(ticks)
        ax.set_autoscaley_on(False)   # 锁死y轴，画曲线时不许自动改范围
        ax.tick_params(labelsize=5, direction='in', labelleft=False, length=3)
        ax.grid(True, alpha=0.3, linewidth=0.3, which='major', axis='y')


        if len(curve_list) == 0:
            ax.set_xticks([])
            continue
        # 用第一条曲线的 family 决定本道刻度类型/范围
        base_fam = curve_family.get(curve_list[0], detect_family(curve_list[0]))
        base_tpl = FAMILY_TEMPLATES[base_fam]
        if base_tpl["scale_type"] == "log":
            ax.set_xscale("log")
        # 画每条曲线
        for curve in curve_list:
            fam = curve_family.get(curve, detect_family(curve))
            tpl = FAMILY_TEMPLATES[fam]
            data = get_curve_data(curve)
            color = rgb_to_mpl(tpl["color"])
            left = tpl["left"]
            right = tpl["right"]
            if left is None or right is None:
                dmin = np.nanmin(data)
                dmax = np.nanmax(data)
                rng = dmax - dmin if dmax > dmin else 1
                left = dmin - 0.05 * rng
                right = dmax + 0.05 * rng
            ax.set_xlim(left, right)
            is_active = (curve == active_curve)
            ax.plot(data, depth, color=color,
                    linewidth=2.0 if is_active else 0.6,
                    linestyle='--' if is_active else '-')
            ax.set_ylim(d_max, d_min)
            
        ax.xaxis.set_ticks_position('top')
        ax.tick_params(axis='x', labelsize=4)

    well_name = las.well.WELL.value if 'WELL' in las.well.keys() else 'Unknown'
    fig.suptitle(f"Well: {well_name}   |   {d_min:.1f} - {d_max:.1f} {las.well.STRT.unit}",
                 fontsize=10, fontweight='bold',
                 y=1 - MARGIN_TOP / total_h * 0.35)
    return fig

def hit_test(fx, fy):
    """fx,fy 是 figure 比例坐标(0~1)。返回命中的 pick 项，曲线优先于道。"""
    # 先找曲线（示例线），命中范围小、优先
    for p in pick_map:
        if p["type"] == "curve":
            if p["x0"] <= fx <= p["x1"] and p["y0"] <= fy <= p["y1"]:
                return p
    # 再找道（空白区）
    for p in pick_map:
        if p["type"] == "track":
            if p["x0"] <= fx <= p["x1"] and p["y0"] <= fy <= p["y1"]:
                return p
    return None


def on_plot_click(event):
    global active_curve, active_track
    if event.inaxes is None and event.x is None:
        return
    # 把像素坐标转成 figure 比例坐标
    if current_fig is None:
        return
    fw = current_fig.get_figwidth() * current_fig.dpi
    fh = current_fig.get_figheight() * current_fig.dpi
    if event.x is None or event.y is None:
        return
    fx = event.x / fw
    fy = event.y / fh

    hit = hit_test(fx, fy)
    if hit is None:
        # 点空白处取消激活
        active_curve = None
        active_track = None
        refresh_plot()
        return
    if hit["type"] == "curve":
        active_curve = hit["curve"]
        active_track = None
    else:
        active_track = hit["idx"]
        active_curve = None
    refresh_plot()


def refresh_plot():
    global current_fig, current_canvas, las_data, current_scale
    if las_data is None:
        return
    if current_fig is not None:
        plt.close(current_fig)
        current_fig = None
    for widget in plot_frame.winfo_children():
        widget.destroy()
    current_canvas = None

    current_fig = build_log_plot(current_scale, interactive=True)
    if current_fig is None:
        return

    toolbar_frame = tk.Frame(plot_frame, bg="#eaeaea")
    toolbar_frame.pack(side="top", fill="x")
    tk.Button(toolbar_frame, text="属性", command=open_properties,
              font=("微软雅黑", 8), padx=8).pack(side="right", padx=2, pady=1)
    tk.Button(toolbar_frame, text="放大", command=lambda: zoom_scale(1.25),
              font=("微软雅黑", 8), padx=6).pack(side="left", padx=2, pady=1)
    tk.Button(toolbar_frame, text="缩小", command=lambda: zoom_scale(0.8),
              font=("微软雅黑", 8), padx=6).pack(side="left", padx=2, pady=1)
    tk.Label(toolbar_frame,
             text="(点示例线选曲线/点道空白选道 - 左右键移动 - Esc取消)",
             bg="#eaeaea", font=("微软雅黑", 8), fg="#666").pack(side="left", padx=10)

    canvas_holder = tk.Frame(plot_frame, bg="white")
    canvas_holder.pack(side="top", fill="both", expand=True)

    yscroll = tk.Scrollbar(canvas_holder, orient="vertical")
    yscroll.pack(side="right", fill="y")
    xscroll = tk.Scrollbar(canvas_holder, orient="horizontal")
    xscroll.pack(side="bottom", fill="x")

    bg_canvas = tk.Canvas(canvas_holder, bg="white",
                          yscrollcommand=yscroll.set,
                          xscrollcommand=xscroll.set,
                          highlightthickness=0)
    bg_canvas.pack(side="left", fill="both", expand=True)
    yscroll.config(command=bg_canvas.yview)
    xscroll.config(command=bg_canvas.xview)

    inner = tk.Frame(bg_canvas, bg="white")
    bg_canvas.create_window((0, 0), window=inner, anchor="nw")

    mpl_canvas = FigureCanvasTkAgg(current_fig, master=inner)
    current_canvas = mpl_canvas
    mpl_canvas.draw()
    widget = mpl_canvas.get_tk_widget()
    w_px = int(current_fig.get_figwidth() * PREVIEW_DPI)
    h_px = int(current_fig.get_figheight() * PREVIEW_DPI)
    widget.config(width=w_px, height=h_px)
    widget.pack()

    mpl_canvas.mpl_connect("button_press_event", on_plot_click)

    def _update_scrollregion(event=None):
        bg_canvas.configure(scrollregion=bg_canvas.bbox("all"))
    inner.bind("<Configure>", _update_scrollregion)
    bg_canvas.after(50, _update_scrollregion)

     

    def _on_wheel(event):
        ctrl_down = bool(event.state & 0x0004)
        if ctrl_down:
            if event.delta > 0:
                zoom_scale(1.15)
            else:
                zoom_scale(0.87)
        else:
            step = -1 if event.delta > 0 else 1
            bg_canvas.yview_scroll(step, "units")
    bg_canvas.bind_all("<MouseWheel>", _on_wheel)
  



    plot_frame.update_idletasks()


def zoom_scale(factor):
    global current_scale
    if las_data is None:
        return
    current_scale = max(0.001, min(2.0, current_scale * factor))
    refresh_plot()

def move_active(direction):
    """direction: -1 左, +1 右。移动激活的曲线或道。"""
    global tracks, active_curve, active_track
    if las_data is None:
        return

    # 移动曲线：从当前道挪到相邻道
    if active_curve is not None:
        # 找曲线在哪个道
        src = None
        for ti, clist in enumerate(tracks):
            if active_curve in clist:
                src = ti
                break
        if src is None:
            return
        dst = src + direction
        if dst < 0 or dst >= len(tracks):
            return
        tracks[src].remove(active_curve)
        tracks[dst].append(active_curve)
        refresh_plot()
        return

    # 移动道：和相邻道交换位置
    if active_track is not None:
        src = active_track
        dst = src + direction
        if dst < 0 or dst >= len(tracks):
            return
        tracks[src], tracks[dst] = tracks[dst], tracks[src]
        active_track = dst
        refresh_plot()
        return


def cancel_active(event=None):
    global active_curve, active_track
    active_curve = None
    active_track = None
    refresh_plot()


def on_key_left(event=None):
    move_active(-1)


def on_key_right(event=None):
    move_active(+1)


def import_las():
    global las_data, file_path, curve_family, tracks, active_curve, active_track
    fp = filedialog.askopenfilename(
        title="选择 LAS 文件",
        filetypes=[("LAS files", "*.las"), ("All files", "*.*")])
    if not fp:
        return
    try:
        las_data = lasio.read(fp)
        file_path = fp
        curve_family = {}
        for curve in las_data.keys()[1:]:
            curve_family[curve] = detect_family(curve)
        tracks = [[c] for c in las_data.keys()[1:]]
        active_curve = None
        active_track = None
        curves_str = ', '.join(las_data.keys()[1:])
        strt = las_data.well.STRT.value
        stop = las_data.well.STOP.value
        unit = las_data.well.STRT.unit
        status_bar.config(
            text=f"已导入: {os.path.basename(fp)}  |  深度: "
                 f"{strt:.1f} ~ {stop:.1f} {unit}  |  曲线: {curves_str}")
        update_tree()
        refresh_plot()
    except Exception as e:
        messagebox.showerror("导入失败", f"无法读取 LAS 文件:\n{e}")


def update_tree():
    global las_data, curve_family
    for item in tree.get_children():
        tree.delete(item)
    if las_data is None:
        return
    well_name = las_data.well.WELL.value if 'WELL' in las_data.well.keys() else 'Unknown Well'
    wid = tree.insert("", "end", text=f"🛢️ {well_name}", open=True, values=("well", ""))
    tree.insert(wid, "end", text=f"📏 {las_data.keys()[0]} (m)", values=("depth", ""))
    fam_node = tree.insert(wid, "end", text="🗂️ 曲线 Family 管理", open=True, values=("famroot", ""))
    for curve in las_data.keys()[1:]:
        fam = curve_family.get(curve, detect_family(curve))
        tree.insert(fam_node, "end",
                    text=f"📈 {curve}  [{fam}族]",
                    values=("curve", curve))

def open_properties():
    if las_data is None:
        messagebox.showwarning("提示", "请先导入 LAS 文件")
        return
    dialog = tk.Toplevel(root)
    dialog.title("属性设置")
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

    tk.Label(dialog, text="图头栏高度 (cm):", font=("微软雅黑", 9)).pack(anchor="w", **pad)
    hv = tk.DoubleVar(value=round(config["header_height"] * 2.54, 1))
    hl = tk.Label(dialog, text=f"{hv.get():.1f} cm", font=("微软雅黑", 8), fg="#06c")
    hl.pack(anchor="w", padx=20)

    def upd_h(*_):
        v = round(hv.get(), 1)
        hl.config(text=f"{v:.1f} cm")
        config["header_height"] = round(v / 2.54, 3)
        debounce_refresh()
    tk.Scale(dialog, from_=0.3, to=8.0, resolution=0.1, orient="horizontal",
             variable=hv, length=360, showvalue=False, command=upd_h).pack(padx=20)

    tk.Label(dialog, text="深度道宽度比例:", font=("微软雅黑", 9)).pack(anchor="w", **pad)
    dv = tk.DoubleVar(value=config["depth_track_ratio"])
    dl = tk.Label(dialog, text=f"{dv.get():.2f}", font=("微软雅黑", 8), fg="#06c")
    dl.pack(anchor="w", padx=20)

    def upd_d(*_):
        config["depth_track_ratio"] = round(dv.get(), 2)
        dl.config(text=f"{dv.get():.2f}")
        debounce_refresh()
    tk.Scale(dialog, from_=0.1, to=1.0, resolution=0.05, orient="horizontal",
             variable=dv, length=360, showvalue=False, command=upd_d).pack(padx=20)

    tk.Label(dialog, text="曲线道宽度比例:", font=("微软雅黑", 9)).pack(anchor="w", **pad)
    cv = tk.DoubleVar(value=config["curve_track_ratio"])
    cl = tk.Label(dialog, text=f"{cv.get():.2f}", font=("微软雅黑", 8), fg="#06c")
    cl.pack(anchor="w", padx=20)

    def upd_c(*_):
        config["curve_track_ratio"] = round(cv.get(), 2)
        cl.config(text=f"{cv.get():.2f}")
        debounce_refresh()
    tk.Scale(dialog, from_=0.5, to=3.0, resolution=0.1, orient="horizontal",
             variable=cv, length=360, showvalue=False, command=upd_c).pack(padx=20)

    bf = tk.Frame(dialog)
    bf.pack(pady=20)

    def reset():
        config["header_height"] = round(3.0 / 2.54, 3)
        config["depth_track_ratio"] = 0.35
        config["curve_track_ratio"] = 1.0
        hv.set(3.0)
        dv.set(0.35)
        cv.set(1.0)
        hl.config(text="3.0 cm")
        dl.config(text="0.35")
        cl.config(text="1.00")
        refresh_plot()

    tk.Button(bf, text="重置默认", command=reset,
              font=("微软雅黑", 10), width=12).pack(side="left", padx=5)
    tk.Button(bf, text="关闭", command=dialog.destroy,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)


def print_long_pdf():
    if las_data is None:
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

    d_min_full = las_data.well.STRT.value
    d_max_full = las_data.well.STOP.value

    tk.Label(dialog, text="深度比例 (英寸/米):", font=("微软雅黑", 9)).pack(anchor="w", padx=20)
    sv = tk.DoubleVar(value=current_scale)
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
            fig = build_log_plot(sv.get(), from_depth=fv.get(), to_depth=tv.get(), for_print=True)
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


def edit_family(event):
    global curve_family
    item = tree.identify_row(event.y)
    if not item:
        return
    vals = tree.item(item, "values")
    if not vals or vals[0] != "curve":
        return
    curve = vals[1]
    cur_fam = curve_family.get(curve, detect_family(curve))

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

    def show_desc(*_):
        tpl = FAMILY_TEMPLATES[fam_var.get()]
        sc = "对数" if tpl["scale_type"] == "log" else "线性"
        rng = f"{tpl['left']}~{tpl['right']}" if tpl["left"] is not None else "自动"
        desc_lbl.config(text=f"刻度 {rng} | {sc}")
    desc_lbl = tk.Label(dialog, text="", font=("微软雅黑", 8), fg="#06c")
    desc_lbl.pack()
    combo.bind("<<ComboboxSelected>>", show_desc)
    show_desc()

    def apply_fam():
        curve_family[curve] = fam_var.get()
        update_tree()
        refresh_plot()
        dialog.destroy()

    bf = tk.Frame(dialog)
    bf.pack(pady=12)
    tk.Button(bf, text="应用", command=apply_fam,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)
    tk.Button(bf, text="取消", command=dialog.destroy,
              font=("微软雅黑", 10), width=8).pack(side="left", padx=5)


# ==================== 主窗口 ====================
root = tk.Tk()
root.title("BoreholeGuard - 测井可视化工具")
root.geometry("1200x800")

menubar = tk.Menu(root)
file_menu = tk.Menu(menubar, tearoff=0)
file_menu.add_command(label="导入 LAS 文件 (Ctrl+O)", command=import_las)
file_menu.add_command(label="打印长卷 PDF (Ctrl+P)", command=print_long_pdf)
file_menu.add_separator()
file_menu.add_command(label="退出 (Ctrl+Q)", command=root.quit)
menubar.add_cascade(label="文件", menu=file_menu)

help_menu = tk.Menu(menubar, tearoff=0)
help_menu.add_command(label="关于", command=lambda: messagebox.showinfo(
    "关于", "BoreholeGuard v1.2\n轻量级开源测井可视化工具"))
menubar.add_cascade(label="帮助", menu=help_menu)
root.config(menu=menubar)

root.bind("<Control-o>", lambda e: import_las())
root.bind("<Control-p>", lambda e: print_long_pdf())
root.bind("<Control-q>", lambda e: root.quit())
root.bind("<Left>", on_key_left)
root.bind("<Right>", on_key_right)
root.bind("<Escape>", cancel_active)

main_pane = tk.PanedWindow(root, orient="horizontal", sashwidth=4, bg="#ccc")
main_pane.pack(fill="both", expand=True)

left_frame = tk.Frame(main_pane, width=240, bg="#f5f5f5")
tk.Label(left_frame, text="数据浏览器", bg="#f5f5f5",
         font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=8, pady=6)
tree = ttk.Treeview(left_frame, show="tree")
tree.pack(fill="both", expand=True, padx=4, pady=4)
tree.bind("<Double-1>", edit_family)
main_pane.add(left_frame)

plot_frame = tk.Frame(main_pane, bg="white")
main_pane.add(plot_frame)

tk.Label(plot_frame, text="请通过 文件 - 导入 LAS 文件 开始",
         bg="white", fg="#999", font=("微软雅黑", 12)).pack(expand=True)

status_bar = tk.Label(root, text="就绪 | 请导入 LAS 文件",
                      bd=1, relief="sunken", anchor="w", font=("微软雅黑", 9))
status_bar.pack(side="bottom", fill="x")

root.mainloop()