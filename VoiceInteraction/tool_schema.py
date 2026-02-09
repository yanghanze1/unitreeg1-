# -*- coding: utf-8 -*-
"""
工具定义模块：机器人控制工具的 JSON Schema

作用：
- 定义可供 LLM 调用的工具函数（运动控制、姿态控制、交互动作）
- 使用 OpenAI Function Calling 标准格式
- 提供详细的参数说明，帮助 LLM 正确生成调用请求
"""

from config import SAFETY_CONFIG  # 导入安全配置参数


# ===================== 运动控制工具 =====================

TOOL_MOVE_ROBOT = {
    "type": "function",  # 工具类型
    "function": {
        "name": "move_robot",  # 工具名称
        "description": "控制机器人移动。可设置前进/后退速度、横向速度、旋转速度和持续时间。",  # 工具描述
        "parameters": {  # 参数定义
            "type": "object",
            "properties": {
                "vx": {
                    "type": "number",  # 参数类型
                    "description": f"前进速度 (m/s)，正值为前进，负值为后退。范围: [{-SAFETY_CONFIG['MAX_SAFE_SPEED_VX']}, {SAFETY_CONFIG['MAX_SAFE_SPEED_VX']}]",  # 参数说明
                },
                "vy": {
                    "type": "number",
                    "description": f"横向速度 (m/s)，正值为向左，负值为向右。范围: [{-SAFETY_CONFIG['MAX_SAFE_SPEED_VY']}, {SAFETY_CONFIG['MAX_SAFE_SPEED_VY']}]",
                },
                "vyaw": {
                    "type": "number",
                    "description": f"旋转角速度 (rad/s)，正值为逆时针（左转），负值为顺时针（右转）。范围: [{-SAFETY_CONFIG['MAX_SAFE_OMEGA']}, {SAFETY_CONFIG['MAX_SAFE_OMEGA']}]",
                },
                "duration": {
                    "type": "number",
                    "description": f"持续时间 (秒)。范围: [{SAFETY_CONFIG['MIN_DURATION']}, {SAFETY_CONFIG['MAX_DURATION']}]，默认: {SAFETY_CONFIG['DEFAULT_DURATION']}",
                    "default": SAFETY_CONFIG['DEFAULT_DURATION'],  # 默认值
                }
            },
            "required": ["vx", "vy", "vyaw"],  # 必需参数
        }
    }
}


TOOL_STOP_ROBOT = {
    "type": "function",
    "function": {
        "name": "stop_robot",  # 停止机器人运动
        "description": "立即停止机器人的所有运动。将速度设置为零。",
        "parameters": {
            "type": "object",
            "properties": {},  # 无参数
        }
    }
}


TOOL_ROTATE_ANGLE = {
    "type": "function",
    "function": {
        "name": "rotate_angle",  # 旋转指定角度
        "description": "让机器人旋转指定角度。正值为逆时针（左转），负值为顺时针（右转）。",
        "parameters": {
            "type": "object",
            "properties": {
                "degrees": {
                    "type": "number",
                    "description": f"旋转角度 (度)。范围: [{SAFETY_CONFIG['MIN_ROTATION_DEGREES']}, {SAFETY_CONFIG['MAX_ROTATION_DEGREES']}]",
                }
            },
            "required": ["degrees"],
        }
    }
}


# ===================== 紧急控制工具 =====================

TOOL_EMERGENCY_STOP = {
    "type": "function",
    "function": {
        "name": "emergency_stop",  # 紧急停止
        "description": "紧急停止！立即切换到阻尼模式并停止所有运动。用于危险情况。",
        "parameters": {
            "type": "object",
            "properties": {},  # 无参数
        }
    }
}


# ===================== 交互动作工具 =====================

TOOL_WAVE_HAND = {
    "type": "function",  # 工具类型
    "function": {
        "name": "wave_hand",  # 工具名称
        "description": "让机器人挥手打招呼。用于友好互动场景。",  # 工具描述
        "parameters": {  # 参数定义
            "type": "object",
            "properties": {},  # 无参数（默认左手挥手）
        }
    }
}


# ===================== 工具列表（注册到 LLM）=====================

ROBOT_TOOLS = [
    TOOL_MOVE_ROBOT,      # 移动机器人
    TOOL_STOP_ROBOT,      # 停止机器人
    TOOL_ROTATE_ANGLE,    # 旋转指定角度
    TOOL_EMERGENCY_STOP,  # 紧急停止
    TOOL_WAVE_HAND,       # 挥手打招呼
]


# ===================== 工具名称到中文的映射（用于日志）=====================

TOOL_NAME_CN = {
    "move_robot": "移动机器人",
    "stop_robot": "停止运动",
    "rotate_angle": "旋转角度",
    "emergency_stop": "紧急停止",
    "wave_hand": "挥手动作",
}
