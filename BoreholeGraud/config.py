"""常量配置模块 - 家族模板、布局参数、工具函数"""

# ==================== Family 模板库 ====================
FAMILY_TEMPLATES = {
    "GR":  {"left": 0.0,  "right": 200.0, "scale_type": "linear",
            "color": (0, 128, 0),  "desc": "ziran gamma"},
    "RT":  {"left": 0.2,  "right": 200.0, "scale_type": "log",
            "color": (240, 0, 0),  "desc": "diceng dianzulv"},
    "RXO": {"left": 0.2,  "right": 200.0, "scale_type": "log",
            "color": (0, 0, 240),  "desc": "chongxidai dianzulv"},
    "BIT": {"left": 6.0,  "right": 16.0, "scale_type": "linear",
            "color": (139, 69, 19),  "desc": "zuantou zhijing"},
    "CAL": {"left": 6.0,  "right": 16.0, "scale_type": "linear",
            "color": (255, 140, 0),  "desc": "jingyan zhijing"},
    "default": {"left": None, "right": None, "scale_type": "linear",
                "color": (0, 0, 0), "desc": "weifenlei"},
}

# ==================== 默认布局/网格配置 ====================
DEFAULT_CONFIG = {
    "header_height": round(3.0 / 2.54, 3),
    "depth_track_ratio": 0.35,
    "curve_track_ratio": 1.0,
    "max_data_height": 35,
    "well": {
        "from_depth": None,
        "to_depth": None,
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

# ==================== 固定布局参数 ====================
FIG_WIDTH = 11.7
MARGIN_TOP = 0.4
MARGIN_BOTTOM = 0.2
MARGIN_LEFT = 0.03
MARGIN_RIGHT = 0.98
PREVIEW_DPI = 80


def rgb_to_mpl(rgb):
    """将 0-255 RGB 元组转为 matplotlib 0-1 元组。"""
    return tuple(c / 255.0 for c in rgb)


def detect_family(curve_name):
    """根据曲线名自动检测所属家族。"""
    name = curve_name.upper()
    if "RXO" in name:
        return "RXO"
    if "RT" in name:
        return "RT"
    if "GR" in name:
        return "GR"
    if "BIT" in name:
        return "BIT"
    if "CAL" in name:
        return "CAL"
    return "default"
