"""LAS 文件 I/O 模块 - 读取文件和访问曲线数据。"""

import lasio
import numpy as np

import state
from config import detect_family


def get_curve_data(curve):
    """获取曲线数据，返回 numpy 数组。"""
    raw = state.las_data[curve]
    return raw if isinstance(raw, np.ndarray) else raw.values


def get_curve_unit(curve):
    """获取曲线单位字符串。"""
    raw = state.las_data[curve]
    return raw.unit if (hasattr(raw, 'unit') and raw.unit) else ''


def load_las(filepath):
    """加载 LAS 文件并更新状态。

    返回 True 表示成功；抛出异常表示失败。
    """
    las = lasio.read(filepath)
    state.las_data = las
    state.file_path = filepath

    # 初始化曲线家族
    state.curve_family = {}
    for curve in las.keys()[1:]:
        state.curve_family[curve] = detect_family(curve)

    # 初始化道布局：每条曲线独立一道
    state.tracks = [[c] for c in las.keys()[1:]]

    # 重置视图状态
    state.reset_view_state()
    return True
