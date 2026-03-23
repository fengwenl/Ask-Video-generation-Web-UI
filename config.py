# -*- coding: utf-8 -*-
"""
配置文件 - 火山方舟 Ark 视频生成 Web UI
"""

import os

# ============ API 配置 ============
API_HOST = "https://ark.cn-beijing.volces.com"
API_KEY_ENV = "ARK_API_KEY"  # 环境变量名

# ============ 默认参数 ============
DEFAULT_MODEL = "doubao-seedance-1-5-pro-251215"

# 支持的模型列表
MODELS = [
    "doubao-seedance-1-5-pro-251215",
    "doubao-seedance-1-0-pro-250118",
    "doubao-seedance-1-0-pro-fast-250118",
    "doubao-seedance-1-0-lite-t2v-250118",
    "doubao-seedance-1-0-lite-i2v-250118",
]

# 各模型支持的分辨率
MODEL_RESOLUTIONS = {
    "doubao-seedance-1-5-pro-251215": ["480p", "720p", "1080p"],
    "doubao-seedance-1-0-pro-250118": ["480p", "720p", "1080p"],
    "doubao-seedance-1-0-pro-fast-250118": ["480p", "720p", "1080p"],
    "doubao-seedance-1-0-lite-t2v-250118": ["480p", "720p", "1080p"],
    "doubao-seedance-1-0-lite-i2v-250118": ["480p", "720p", "1080p"],
}

# 支持的时长（秒）
DURATIONS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

# 支持的画面比例
RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]

# ============ 轮询配置 ============
POLL_INTERVAL = 3  # 轮询间隔（秒）
POLL_TIMEOUT = 600  # 总超时时间（秒）

# ============ UI 配置 ============
APP_TITLE = "🎬 火山方舟 Ark 视频生成工具"
APP_DESCRIPTION = "基于火山方舟 Ark API 的 AI 视频生成 Web UI，支持多种模型和分辨率"

# 主题色
THEME_ACCENT_COLOR = "#E8630A"

# -*- coding: utf-8 -*-
