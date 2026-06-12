#!/usr/bin/env python3
"""BoreholeGuard v1.2 - 轻量级开源测井可视化工具

用法:
    python main.py
"""

import sys
import os

# 确保项目目录在 sys.path 中，以便模块间互相导入
_project_dir = os.path.dirname(os.path.abspath(__file__))
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)

from ui import main

if __name__ == "__main__":
    main()
