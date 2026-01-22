# -*- coding: utf-8 -*-
"""
配置文件：安全参数与 Function Calling 设置

作用：
- 集中管理运动控制的安全参数（速度限制、持续时间等）
- 配置 Function Calling 功能的行为（是否启用、超时、回退策略等）
"""

# ===================== 安全参数配置 =====================

SAFETY_CONFIG = {
    # 运动速度限制
    "MAX_SAFE_SPEED_VX": 1.0,      # 前进/后退最大安全速度 (m/s)
    "MAX_SAFE_SPEED_VY": 1.0,      # 横向最大安全速度 (m/s)
    "MAX_SAFE_OMEGA": 2.0,         # 旋转最大安全角速度 (rad/s)
    
    # 时间参数
    "MAX_DURATION": 10.0,          # 单次移动最大持续时间 (秒)
    "DEFAULT_DURATION": 1.0,       # 默认持续时间 (秒)
    "MIN_DURATION": 0.1,           # 最小持续时间 (秒)
    
    # 角度参数
    "MAX_ROTATION_DEGREES": 180,   # 单次旋转最大角度 (度)
    "MIN_ROTATION_DEGREES": -180,  # 单次旋转最小角度 (度)
}


# ===================== Function Calling 配置 =====================

FUNCTION_CALLING_CONFIG = {
    # 功能开关
    "ENABLED": True,                       # 是否启用工具调用功能
    "FALLBACK_TO_KEYWORDS": True,          # 工具调用失败时是否回退到关键词匹配
    
    # 性能参数
    "TIMEOUT": 3.0,                        # LLM 推理超时时间 (秒)
    "MAX_RETRIES": 2,                      # 调用失败时的最大重试次数
    
    # 模型配置
    "MODEL": "qwen-max",                   # 使用的模型名称 (qwen-max / qwen-plus)
    "TEMPERATURE": 0.3,                    # 温度参数 (降低随机性，提高一致性)
    "MAX_TOKENS": 500,                     # 最大生成token数
}


# ===================== 日志配置 =====================

LOGGING_CONFIG = {
    "LOG_TOOL_CALLS": True,                # 是否记录工具调用日志
    "LOG_PARAMETER_VALIDATION": True,      # 是否记录参数验证日志
    "LOG_EXECUTION_RESULTS": True,         # 是否记录执行结果日志
}


# ==================== AEC 配置 ====================

AEC_CONFIG = {
    "ENABLED": True,  # 是否启用音频回声消除
    "FRAME_SIZE": 320,  # 帧大小（20ms @ 16kHz）
    "FILTER_LENGTH": 2048,  # 自适应滤波器长度（影响效果和性能）
    "SAMPLE_RATE": 16000,  # 采样率（16kHz，与麦克风一致）
    # 注意：speexdsp 在 Linux 上可用，Windows 安装较困难
}
