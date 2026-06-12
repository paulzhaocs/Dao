"""集中状态管理模块 - 所有可变全局状态在此定义。"""

from copy import deepcopy
from config import DEFAULT_CONFIG


# ==================== 数据状态 ====================
las_data = None        # lasio 读取的 LAS 数据对象
file_path = ""         # 当前 LAS 文件路径

# ==================== 曲线与道状态 ====================
tracks = []            # 道布局，如 [["GR"], ["RT"], ["RXO"]]
active_curve = None    # 当前激活的曲线名
active_track = None    # 当前激活的道索引（数据道，从0起）
pick_map = []          # 命中信息列表

# ==================== 视图状态 ====================
current_fig = None     # 当前 matplotlib figure
current_canvas = None  # 当前 FigureCanvasTkAgg 对象
current_scale = 0.008  # 当前深度缩放比

# ==================== 配置状态 ====================
config = deepcopy(DEFAULT_CONFIG)  # 可变配置字典

# ==================== 曲线家族映射 ====================
curve_family = {}      # {curve_name: family_name, ...}

# ==================== 曲线样式覆盖 ====================
# {curve_name: {"left": float, "right": float,
#               "linewidth": float, "linestyle": str,
#               "color": (r,g,b) 0-255, "scale_type": "linear"|"log"}}
curve_styles = {}


def get_curve_style(curve):
    """获取曲线样式的合并结果（curve_styles 覆盖 FAMILY_TEMPLATES）。"""
    from config import FAMILY_TEMPLATES, detect_family
    fam = curve_family.get(curve, detect_family(curve))
    tpl = FAMILY_TEMPLATES[fam]
    over = curve_styles.get(curve, {})
    return {
        "left": over.get("left", tpl["left"]),
        "right": over.get("right", tpl["right"]),
        "linewidth": over.get("linewidth", 0.6),
        "linestyle": over.get("linestyle", "-"),
        "color": over.get("color", tpl["color"]),
        "scale_type": over.get("scale_type", tpl["scale_type"]),
    }


def get_track_scale_type(t_idx):
    """获取指定道的 x 轴刻度类型。如果道内有曲线有 scale_type 覆盖则使用，否则从家族推断。"""
    from config import FAMILY_TEMPLATES, detect_family
    if t_idx >= len(tracks) or not tracks[t_idx]:
        return "linear"
    first_curve = tracks[t_idx][0]
    over = curve_styles.get(first_curve, {})
    if "scale_type" in over:
        return over["scale_type"]
    fam = curve_family.get(first_curve, detect_family(first_curve))
    return FAMILY_TEMPLATES[fam]["scale_type"]


def reset_view_state():
    """重置视图相关状态（不涉及数据）。"""
    global active_curve, active_track, pick_map, current_fig, current_canvas
    active_curve = None
    active_track = None
    pick_map = []
    current_fig = None
    current_canvas = None


def reset_all():
    """重置所有状态到默认值。"""
    global las_data, file_path, tracks, curve_family, current_scale, config
    global active_curve, active_track, pick_map, current_fig, current_canvas
    global curve_styles
    las_data = None
    file_path = ""
    tracks = []
    curve_family = {}
    curve_styles = {}
    current_scale = 0.008
    config = deepcopy(DEFAULT_CONFIG)
    reset_view_state()
