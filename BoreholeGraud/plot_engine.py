"""绘图引擎模块 - 纯 matplotlib 构建测井图，无 tkinter 依赖。

职责：
  - compute_track_x(): 计算各道在 figure 中的 x 位置和宽度
  - build_log_plot(): 构建完整的测井 matplotlib Figure 对象（PDF 导出用）
  - build_header_figure(): 仅构建图头区（固定显示）
  - build_data_figure(): 仅构建图道区（可滚动）
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import state
from config import (FAMILY_TEMPLATES, FIG_WIDTH,
                    MARGIN_TOP, MARGIN_BOTTOM, MARGIN_LEFT, MARGIN_RIGHT,
                    PREVIEW_DPI, rgb_to_mpl, detect_family)
from las_io import get_curve_data, get_curve_unit


def compute_track_x(n_data_tracks):
    """计算各道在 figure 中的 (x, 宽度) 坐标列表。

    返回列表：[(depth_x, depth_w), (data0_x, data0_w), ...]
    坐标和宽度均为 figure 比例坐标 (0~1)。
    """
    dr = state.config["depth_track_ratio"]
    cr = state.config["curve_track_ratio"]
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


def _compute_layout(scale_factor, from_depth, to_depth, for_print=False):
    """计算绘图布局所需的全部尺寸和刻度，返回字典。

    此函数供 build_log_plot / build_header_figure / build_data_figure 共用。
    """
    las = state.las_data
    depth = las.index

    well_cfg = state.config.get("well", {})
    d_min_full = las.well.STRT.value
    d_max_full = las.well.STOP.value
    d_min = from_depth if from_depth is not None else well_cfg.get("from_depth", d_min_full)
    d_max = to_depth if to_depth is not None else well_cfg.get("to_depth", d_max_full)
    if d_min is None:
        d_min = d_min_full
    if d_max is None:
        d_max = d_max_full
    if d_max <= d_min:
        d_min, d_max = d_min_full, d_max_full
    d_range = d_max - d_min

    n_data = len(state.tracks)
    n_tracks = 1 + n_data

    header_h = state.config["header_height"]
    data_h = max(8, d_range * scale_factor)
    if not for_print:
        data_h = min(data_h, 300)

    total_h = MARGIN_TOP + header_h + data_h + MARGIN_BOTTOM
    boxes = compute_track_x(n_data)

    data_y0 = MARGIN_BOTTOM / total_h
    data_y1 = (MARGIN_BOTTOM + data_h) / total_h
    head_y0 = data_y1
    head_y1 = (MARGIN_BOTTOM + data_h + header_h) / total_h
    head_axes_height = head_y1 - head_y0
    data_axes_height = data_y1 - data_y0

    step = 50 if d_range > 200 else 20
    ticks = np.arange(np.ceil(d_min / step) * step, d_max + step, step)

    return {
        "las": las,
        "depth": depth,
        "n_data": n_data,
        "n_tracks": n_tracks,
        "d_min": d_min,
        "d_max": d_max,
        "d_min_full": d_min_full,
        "d_max_full": d_max_full,
        "d_range": d_range,
        "header_h": header_h,
        "data_h": data_h,
        "total_h": total_h,
        "boxes": boxes,
        "head_y0": head_y0,
        "head_y1": head_y1,
        "data_y0": data_y0,
        "data_y1": data_y1,
        "head_axes_height": head_axes_height,
        "data_axes_height": data_axes_height,
        "ticks": ticks,
        "scale_factor": scale_factor,
        "for_print": for_print,
    }


def build_header_figure(scale_factor, from_depth=None, to_depth=None):
    """仅构建图头区 matplotlib Figure（固定高度，不滚动）。

    返回 matplotlib.figure.Figure 对象，或 None（无数据时）。
    """
    if state.las_data is None:
        return None

    state.pick_map = []
    lay = _compute_layout(scale_factor, from_depth, to_depth)

    # 图头区只占 header_h + MARGIN_TOP + MARGIN_BOTTOM 那一点点高度
    fig_h = MARGIN_TOP + lay["header_h"] + MARGIN_BOTTOM
    fig = plt.figure(figsize=(FIG_WIDTH, fig_h), dpi=PREVIEW_DPI)
    # 调整比例：head_y0/1 在这个小 figure 中的映射
    head_y0 = MARGIN_BOTTOM / fig_h
    head_y1 = (MARGIN_BOTTOM + lay["header_h"]) / fig_h
    head_axes_height = head_y1 - head_y0

    # 创建 header_axes
    header_axes = []
    for i in range(lay["n_tracks"]):
        x, w = lay["boxes"][i]
        ax_h = fig.add_axes([x, head_y0, w, head_axes_height])
        header_axes.append(ax_h)

    _draw_headers(header_axes, lay, head_y0, head_y1, head_axes_height)

    return fig


def build_data_figure(scale_factor, from_depth=None, to_depth=None,
                      for_print=False):
    """仅构建图道区 matplotlib Figure（可滚动）。

    返回 matplotlib.figure.Figure 对象，或 None（无数据时）。
    """
    if state.las_data is None:
        return None

    lay = _compute_layout(scale_factor, from_depth, to_depth, for_print)

    # 图道区只占 data_h + MARGIN_TOP + MARGIN_BOTTOM 高度
    data_h = lay["data_h"]
    fig_h = MARGIN_TOP + data_h + MARGIN_BOTTOM
    fig = plt.figure(figsize=(FIG_WIDTH, fig_h), dpi=PREVIEW_DPI)

    data_y0 = MARGIN_BOTTOM / fig_h
    data_y1 = (MARGIN_BOTTOM + data_h) / fig_h
    data_axes_height = data_y1 - data_y0

    # 创建 data_axes
    data_axes = []
    for i in range(lay["n_tracks"]):
        x, w = lay["boxes"][i]
        ax_d = fig.add_axes([x, data_y0, w, data_axes_height])
        data_axes.append(ax_d)

    _draw_data_tracks(data_axes, lay, data_h)

    return fig


def build_log_plot(scale_factor, from_depth=None, to_depth=None,
                   for_print=False):
    """构建完整的测井图并返回 matplotlib Figure（用于 PDF 导出）。

    参数：
      scale_factor: 深度缩放因子 (英寸/米)
      from_depth/to_depth: 显示深度范围，None 则从 state.config["well"] 读取
      for_print: True 则允许大高度（PDF 导出），False 则限制预览高度 <=300

    返回：
      matplotlib.figure.Figure 对象，或 None（无数据时）
    """
    if state.las_data is None:
        return None

    las = state.las_data
    depth = las.index

    state.pick_map = []
    lay = _compute_layout(scale_factor, from_depth, to_depth, for_print)

    fig = plt.figure(figsize=(FIG_WIDTH, lay["total_h"]))

    # 创建所有子图
    header_axes = []
    data_axes = []
    for i in range(lay["n_tracks"]):
        x, w = lay["boxes"][i]
        ax_h = fig.add_axes([x, lay["head_y0"], w, lay["head_axes_height"]])
        ax_d = fig.add_axes([x, lay["data_y0"], w, lay["data_axes_height"]])
        header_axes.append(ax_h)
        data_axes.append(ax_d)

    for ax in data_axes:
        ax.set_ylim(lay["d_max"], lay["d_min"])

    _draw_headers(header_axes, lay, lay["head_y0"], lay["head_y1"],
                  lay["head_axes_height"])
    _draw_data_tracks(data_axes, lay, lay["data_h"])

    # 图标题
    well_name = las.well.WELL.value if 'WELL' in las.well.keys() else 'Unknown'
    fig.suptitle(
        f"Well: {well_name}   |   {lay['d_min']:.1f} - {lay['d_max']:.1f} "
        f"{las.well.STRT.unit}",
        fontsize=10, fontweight='bold',
        y=1 - MARGIN_TOP / lay["total_h"] * 0.35,
    )
    return fig


def _draw_headers(header_axes, lay, head_y0, head_y1, head_axes_height):
    """在给定的 axes 上绘制图头区（通用函数）。"""
    las = lay["las"]
    d_min = lay["d_min"]
    d_max = lay["d_max"]
    scale_factor = lay["scale_factor"]
    boxes = lay["boxes"]

    # 深度道图头
    ax_h0 = header_axes[0]
    ax_h0.set_xlim(0, 1)
    ax_h0.set_ylim(0, 1)
    ax_h0.axis('off')
    rect0 = Rectangle((0, 0), 1, 1, linewidth=0.8, edgecolor='black',
                      facecolor='#F0F0F0', transform=ax_h0.transAxes, zorder=10)
    ax_h0.add_patch(rect0)
    ax_h0.text(0.5, 0.7, "DEPTH", fontsize=7, fontweight='bold',
               ha='center', va='center', zorder=11)
    ax_h0.text(0.5, 0.45, "(m)", fontsize=5.5, ha='center', va='center', zorder=11)
    ratio_n = int(round(1.0 / (scale_factor * 0.0254)))
    ax_h0.text(0.5, 0.18, f"1:{ratio_n}", fontsize=5,
               ha='center', va='center', color='#c00', zorder=11)

    # 各数据道图头
    for t_idx, curve_list in enumerate(state.tracks):
        ax_h = header_axes[t_idx + 1]
        ax_h.set_xlim(0, 1)
        ax_h.set_ylim(0, 1)
        ax_h.axis('off')

        is_active_track = (state.active_track == t_idx)
        rect = Rectangle((0, 0), 1, 1,
                         linewidth=2.0 if is_active_track else 0.8,
                         edgecolor='red' if is_active_track else 'black',
                         facecolor='#F0F0F0', transform=ax_h.transAxes, zorder=10)
        ax_h.add_patch(rect)

        x0, w0 = boxes[t_idx + 1]
        state.pick_map.append({
            "type": "track", "idx": t_idx,
            "x0": x0, "x1": x0 + w0,
            "y0": head_y0, "y1": head_y1,
        })

        n_c = len(curve_list)
        if n_c == 0:
            ax_h.text(0.5, 0.5, "(empty)", fontsize=6, color='#999',
                      ha='center', va='center', zorder=11)
            continue

        for ci, curve in enumerate(curve_list):
            sty = state.get_curve_style(curve)
            color_mpl = rgb_to_mpl(sty["color"])
            unit = get_curve_unit(curve)
            label = f"{curve} ({unit})" if unit else curve

            top = 1.0 - ci * (1.0 / n_c)
            bot = 1.0 - (ci + 1) * (1.0 / n_c)
            mid = (top + bot) / 2
            name_y = mid + 0.18 * (top - bot)
            line_y = mid - 0.22 * (top - bot)

            is_active = (curve == state.active_curve)
            ax_h.text(0.5, name_y, label, fontsize=6, fontweight='bold',
                      ha='center', va='center', color=color_mpl, zorder=12)
            hdr_lw = 2.5 if is_active else 1.3
            hdr_ls = '--' if is_active else '-'
            ax_h.plot([0.0, 1.0], [line_y, line_y],
                      color=color_mpl, linewidth=hdr_lw,
                      linestyle=hdr_ls, zorder=12, clip_on=False)

            left = sty["left"] if sty["left"] is not None else np.nanmin(get_curve_data(curve))
            right = sty["right"] if sty["right"] is not None else np.nanmax(get_curve_data(curve))
            txt_y = line_y + 0.12 * (top - bot)
            ax_h.text(0.02, txt_y, f"{left:g}", fontsize=4.5,
                      ha='left', va='center', color=color_mpl, zorder=12)
            ax_h.text(0.98, txt_y, f"{right:g}", fontsize=4.5,
                      ha='right', va='center', color=color_mpl, zorder=12)

            state.pick_map.append({
                "type": "curve", "curve": curve,
                "x0": x0, "x1": x0 + w0,
                "y0": head_y0 + head_axes_height * (line_y - 0.08),
                "y1": head_y0 + head_axes_height * (line_y + 0.08),
            })


def _draw_data_tracks(data_axes, lay, data_h):
    """在给定的 axes 上绘制数据道曲线（通用函数）。"""
    depth = lay["depth"]
    d_min = lay["d_min"]
    d_max = lay["d_max"]
    ticks = lay["ticks"]

    grid_cfg = state.config.get("grid", {})
    hg = grid_cfg.get("horizontal", {})
    vg = grid_cfg.get("vertical", {})

    # 深度道
    ax_d0 = data_axes[0]
    ax_d0.set_xlim(0, 1)
    ax_d0.set_xticks([])
    ax_d0.set_yticks([])
    ax_d0.set_ylim(d_max, d_min)
    ax_d0.axvline(x=0, color='black', linewidth=0.6)
    ax_d0.axvline(x=1, color='black', linewidth=0.6)
    for tk_val in ticks:
        if tk_val < d_min or tk_val > d_max:
            continue
        ax_d0.plot([0.0, 0.18], [tk_val, tk_val], color='black', linewidth=0.6)
        ax_d0.plot([0.82, 1.0], [tk_val, tk_val], color='black', linewidth=0.6)
        ax_d0.text(0.5, tk_val, f"{int(tk_val)}", fontsize=6,
                   ha='center', va='center', color='black')

    # 各数据道曲线
    for t_idx, curve_list in enumerate(state.tracks):
        ax = data_axes[t_idx + 1]
        ax.set_ylim(d_max, d_min)
        ax.set_yticks(ticks)
        ax.set_autoscaley_on(False)
        ax.tick_params(labelsize=5, direction='in', labelleft=False, length=3)

        if hg.get("enabled", True):
            ax.grid(True, axis='y', which='major',
                    color=hg.get("color", "#cccccc"),
                    linewidth=hg.get("linewidth", 0.3))

        if vg.get("enabled", True):
            ax.grid(True, axis='x', which='major',
                    color=vg.get("color", "#cccccc"),
                    linewidth=vg.get("linewidth", 0.3))
            vg_num = vg.get("num_ticks", 5)
            if vg_num > 0:
                ax.xaxis.set_major_locator(plt.MaxNLocator(vg_num))

        if len(curve_list) == 0:
            ax.set_xticks([])
            continue

        scale_type = state.get_track_scale_type(t_idx)
        if scale_type == "log":
            ax.set_xscale("log")

        for curve in curve_list:
            sty = state.get_curve_style(curve)
            data = get_curve_data(curve)
            color_mpl = rgb_to_mpl(sty["color"])
            left = sty["left"]
            right = sty["right"]
            if left is None or right is None:
                dmin = np.nanmin(data)
                dmax = np.nanmax(data)
                rng = dmax - dmin if dmax > dmin else 1
                left = dmin - 0.05 * rng
                right = dmax + 0.05 * rng
            ax.set_xlim(left, right)
            is_active = (curve == state.active_curve)
            lw = 2.0 if is_active else sty["linewidth"]
            ls = '--' if is_active else sty["linestyle"]
            ax.plot(data, depth, color=color_mpl,
                    linewidth=lw, linestyle=ls)
            ax.set_ylim(d_max, d_min)

        ax.xaxis.set_ticks_position('top')
        ax.tick_params(axis='x', labelsize=4)
