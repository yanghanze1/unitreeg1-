# -*- coding: utf-8 -*-
"""
Bridge 层：LLM 工具调用到机器人控制的转换桥梁

作用：
- 解析 LLM 返回的工具调用 JSON
- 验证参数安全性
- 将工具调用映射到实际的机器人控制指令
- 返回执行结果
"""

import math  # 数学库用于角度转换
import logging  # 日志库
from typing import List, Dict, Tuple, Any, Optional  # 类型提示
from action_manager import ActionManager  # 导入ActionManager类型定义
from config import SAFETY_CONFIG, LOGGING_CONFIG  # 导入配置参数
from tool_schema import TOOL_NAME_CN  # 导入工具名称中文映射

# 配置日志记录器
logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


# ===================== 参数验证函数 =====================

def validate_movement_params(
    vx: float, 
    vy: float, 
    vyaw: float, 
    duration: Optional[float] = None
) -> Tuple[bool, str, Dict[str, float]]:
    """
    验证运动参数是否在安全范围内，超限自动截断
    
    Args:
        vx: 前进速度 (m/s)
        vy: 横向速度 (m/s)
        vyaw: 旋转角速度 (rad/s)
        duration: 持续时间 (秒)，可选
        
    Returns:
        (是否有效, 警告信息, 修正后的参数字典)
    """
    warnings = []  # 警告信息列表
    
    # 截断速度参数到安全范围
    vx_safe = max(
        -SAFETY_CONFIG["MAX_SAFE_SPEED_VX"], 
        min(vx, SAFETY_CONFIG["MAX_SAFE_SPEED_VX"])
    )  # 限制vx在[-MAX_SAFE_SPEED_VX, MAX_SAFE_SPEED_VX]范围内
    
    vy_safe = max(
        -SAFETY_CONFIG["MAX_SAFE_SPEED_VY"], 
        min(vy, SAFETY_CONFIG["MAX_SAFE_SPEED_VY"])
    )  # 限制vy在[-MAX_SAFE_SPEED_VY, MAX_SAFE_SPEED_VY]范围内
    
    vyaw_safe = max(
        -SAFETY_CONFIG["MAX_SAFE_OMEGA"], 
        min(vyaw, SAFETY_CONFIG["MAX_SAFE_OMEGA"])
    )  # 限制vyaw在[-MAX_SAFE_OMEGA, MAX_SAFE_OMEGA]范围内
    
    # 检测是否发生截断
    if abs(vx - vx_safe) > 0.001:  # 检测vx是否被截断（浮点数比较使用阈值）
        warnings.append(f"vx={vx:.2f} 超限，已截断为 {vx_safe:.2f}")  # 添加截断警告
    if abs(vy - vy_safe) > 0.001:  # 检测vy是否被截断
        warnings.append(f"vy={vy:.2f} 超限，已截断为 {vy_safe:.2f}")  # 添加截断警告
    if abs(vyaw - vyaw_safe) > 0.001:  # 检测vyaw是否被截断
        warnings.append(f"vyaw={vyaw:.2f} 超限，已截断为 {vyaw_safe:.2f}")  # 添加截断警告
    
    # 处理持续时间参数
    if duration is not None:  # 如果提供了持续时间参数
        duration_safe = max(
            SAFETY_CONFIG["MIN_DURATION"], 
            min(duration, SAFETY_CONFIG["MAX_DURATION"])
        )  # 限制duration在[MIN_DURATION, MAX_DURATION]范围内
        
        if abs(duration - duration_safe) > 0.001:  # 检测duration是否被截断
            warnings.append(f"duration={duration:.2f} 超限，已截断为 {duration_safe:.2f}")  # 添加截断警告
    else:
        duration_safe = SAFETY_CONFIG["DEFAULT_DURATION"]  # 使用默认持续时间
    
    # 构建修正后的参数字典
    safe_params = {
        "vx": vx_safe,  # 修正后的前进速度
        "vy": vy_safe,  # 修正后的横向速度
        "vyaw": vyaw_safe,  # 修正后的旋转角速度
        "duration": duration_safe  # 修正后的持续时间
    }
    
    # 记录验证日志
    if LOGGING_CONFIG["LOG_PARAMETER_VALIDATION"] and warnings:  # 如果启用参数验证日志且有警告
        logger.warning(f"[Safety] 参数验证警告: {'; '.join(warnings)}")  # 记录警告信息
    
    # 返回验证结果
    is_valid = len(warnings) == 0  # 无警告则认为参数有效
    warning_msg = "; ".join(warnings) if warnings else ""  # 拼接警告信息
    return is_valid, warning_msg, safe_params  # 返回（是否有效, 警告信息, 修正后参数）


def validate_rotation_angle(degrees: float) -> Tuple[bool, str, float]:
    """
    验证旋转角度是否在安全范围内
    
    Args:
        degrees: 旋转角度 (度)
        
    Returns:
        (是否有效, 警告信息, 修正后的角度)
    """
    # 截断角度到安全范围
    degrees_safe = max(
        SAFETY_CONFIG["MIN_ROTATION_DEGREES"], 
        min(degrees, SAFETY_CONFIG["MAX_ROTATION_DEGREES"])
    )  # 限制degrees在[MIN_ROTATION_DEGREES, MAX_ROTATION_DEGREES]范围内
    
    # 检测是否发生截断
    warning = ""  # 初始化警告信息
    if abs(degrees - degrees_safe) > 0.001:  # 检测degrees是否被截断
        warning = f"角度={degrees:.1f}° 超限，已截断为 {degrees_safe:.1f}°"  # 生成警告信息
        if LOGGING_CONFIG["LOG_PARAMETER_VALIDATION"]:  # 如果启用参数验证日志
            logger.warning(f"[Safety] {warning}")  # 记录警告
    
    is_valid = warning == ""  # 无警告则认为角度有效
    return is_valid, warning, degrees_safe  # 返回（是否有效, 警告信息, 修正后角度）


# ===================== 工具执行函数 =====================

def execute_tool_calls_sequential(
    tool_calls: List[Dict[str, Any]], 
    action_manager: ActionManager, 
    g1_client: Any
) -> List[Dict[str, Any]]:
    """
    顺序执行多个工具调用（添加到任务队列）
    
    Args:
        tool_calls: 工具调用列表 [{"name": "...", "arguments": {...}}, ...]
        action_manager: ActionManager 实例
        g1_client: G1 客户端实例
        
    Returns:
        执行结果列表，每个元素对应一个工具调用的结果
    """
    results = []  # 初始化结果列表
    
    if not tool_calls:  # 检查工具调用列表是否为空
        logger.warning("[Bridge] 工具调用列表为空")  # 记录警告
        return results  # 返回空结果列表
    
    logger.info(f"[Bridge] 开始顺序执行 {len(tool_calls)} 个工具调用")  # 记录日志
    
    for idx, tool_call in enumerate(tool_calls):  # 遍历工具调用列表
        tool_name = tool_call.get("name", "unknown")  # 获取工具名称
        params = tool_call.get("arguments", {})  # 获取工具参数
        
        logger.info(f"[Bridge] 执行工具 {idx+1}/{len(tool_calls)}: {tool_name}")  # 记录当前执行进度
        
        # 调用单个工具执行函数
        result = execute_tool_call(tool_name, params, action_manager, g1_client)  # 执行工具
        results.append(result)  # 添加结果到列表
        
        # 如果执行失败，记录错误但继续执行后续工具（可选：根据策略决定是否继续）
        if result.get("status") == "error":  # 检查执行结果
            logger.error(f"[Bridge] 工具 {tool_name} 执行失败: {result.get('message')}")  # 记录错误
            # 这里可以选择：continue (继续) 或 break (停止)
            # 当前策略：继续执行后续工具
    
    logger.info(f"[Bridge] 所有工具调用已添加到队列，共 {len(results)} 个")  # 记录完成日志
    return results  # 返回结果列表



def execute_tool_call(
    tool_name: str, 
    params: Dict[str, Any], 
    action_manager: ActionManager, 
    g1_client: Any,
    g1_arm_client: Any = None
) -> Dict[str, Any]:
    """
    执行单个工具调用
    
    Args:
        tool_name: 工具名称
        params: 工具参数字典
        action_manager: ActionManager 实例
        g1_client: G1 客户端实例 (当前未使用，预留扩展)
        g1_arm_client: G1 手臂动作客户端实例 (用于挥手等动作)
        
    Returns:
        执行结果字典 {"status": "success/error", "message": "...", "data": {...}}
    """
    # 检查 ActionManager 是否就绪
    if not action_manager:  # 检查action_manager是否为None
        error_msg = "ActionManager 未初始化"  # 错误信息
        logger.error(f"[Bridge] {error_msg}")  # 记录错误日志
        return {"status": "error", "message": error_msg}  # 返回错误结果
    
    if not action_manager._running:  # 检查ActionManager是否正在运行
        error_msg = "ActionManager 未运行"  # 错误信息
        logger.error(f"[Bridge] {error_msg}")  # 记录错误日志
        return {"status": "error", "message": error_msg}  # 返回错误结果
    
    # 记录工具调用日志
    tool_name_cn = TOOL_NAME_CN.get(tool_name, tool_name)  # 获取工具的中文名称
    if LOGGING_CONFIG["LOG_TOOL_CALLS"]:  # 如果启用工具调用日志
        logger.info(f"[Bridge] 执行工具: {tool_name_cn} ({tool_name}), 参数: {params}")  # 记录工具调用信息
    
    try:
        # 根据工具名称分发执行
        if tool_name == "move_robot":  # 移动机器人工具
            return _execute_move_robot(params, action_manager)  # 调用移动机器人函数
        
        elif tool_name == "stop_robot":  # 停止机器人工具
            return _execute_stop_robot(action_manager)  # 调用停止机器人函数
        
        elif tool_name == "rotate_angle":  # 旋转角度工具
            return _execute_rotate_angle(params, action_manager)  # 调用旋转角度函数
        
        elif tool_name == "emergency_stop":  # 紧急停止工具
            return _execute_emergency_stop(action_manager)  # 调用紧急停止函数
        
        elif tool_name == "wave_hand":  # 挥手动作
            return _execute_wave_hand(g1_arm_client)
        
        else:  # 未知工具名称
            error_msg = f"未知工具: {tool_name}"  # 错误信息
            logger.error(f"[Bridge] {error_msg}")  # 记录错误日志
            return {"status": "error", "message": error_msg}  # 返回错误结果
    
    except Exception as e:  # 捕获所有异常
        error_msg = f"执行工具 {tool_name} 时发生异常: {str(e)}"  # 错误信息
        logger.exception(f"[Bridge] {error_msg}")  # 记录异常日志（包含堆栈）
        return {"status": "error", "message": error_msg}  # 返回错误结果


# ===================== 具体工具实现 =====================

def _execute_move_robot(params: Dict[str, Any], action_manager: ActionManager) -> Dict[str, Any]:
    """执行移动机器人指令"""
    # 提取参数
    vx = float(params.get("vx", 0.0))  # 前进速度，默认0
    vy = float(params.get("vy", 0.0))  # 横向速度，默认0
    vyaw = float(params.get("vyaw", 0.0))  # 旋转角速度，默认0
    duration = params.get("duration")  # 持续时间，可能为None
    if duration is not None:  # 如果提供了持续时间
        duration = float(duration)  # 转换为浮点数
    
    # 参数验证
    is_valid, warning, safe_params = validate_movement_params(vx, vy, vyaw, duration)  # 验证并修正参数
    
    # 使用任务队列（新增）
    task_id = action_manager.add_task(
        task_type="move",  # 任务类型
        parameters={
            "vx": safe_params["vx"],  # 使用修正后的前进速度
            "vy": safe_params["vy"],  # 使用修正后的横向速度
            "vyaw": safe_params["vyaw"]  # 使用修正后的旋转角速度
        },
        duration=safe_params["duration"]  # 使用修正后的持续时间
    )
    
    # 构建返回结果
    # 构建返回结果
    msg = f"机器人移动任务已添加: vx={safe_params['vx']:.2f}, vy={safe_params['vy']:.2f}, vyaw={safe_params['vyaw']:.2f}, duration={safe_params['duration']:.2f}s (task_id: {task_id})"
    if warning:
        msg += f" (已截断参数: {warning})"

    result = {
        "status": "success" if is_valid else "success_with_warning",  # 状态：成功或成功但有警告
        "message": msg,  # 执行信息
        "data": {
            "task_id": task_id,  # 任务ID
            **safe_params  # 实际执行的参数
        }
    }
    
    if warning:  # 如果有警告信息
        result["warning"] = warning  # 添加警告字段
    
    if LOGGING_CONFIG["LOG_EXECUTION_RESULTS"]:  # 如果启用执行结果日志
        logger.info(f"[Bridge] {result['message']}")  # 记录执行结果
    
    return result  # 返回执行结果


def _execute_stop_robot(action_manager: ActionManager) -> Dict[str, Any]:
    """执行停止机器人指令"""
    # 调用 ActionManager 的停止方法
    action_manager.set_idle()  # 设置为空闲状态（速度归零）
    
    # 构建返回结果
    result = {
        "status": "success",  # 状态：成功
        "message": "机器人已停止运动",  # 执行信息
        "data": {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}  # 停止后的速度
    }
    
    if LOGGING_CONFIG["LOG_EXECUTION_RESULTS"]:  # 如果启用执行结果日志
        logger.info(f"[Bridge] {result['message']}")  # 记录执行结果
    
    return result  # 返回执行结果


def _execute_rotate_angle(params: Dict[str, Any], action_manager: ActionManager) -> Dict[str, Any]:
    """执行旋转角度指令"""
    # 提取角度参数
    degrees = float(params.get("degrees", 0.0))  # 旋转角度（度），默认0
    
    # 参数验证
    is_valid, warning, degrees_safe = validate_rotation_angle(degrees)  # 验证并修正角度
    
    # 计算旋转所需的角速度和时间
    # 策略：使用固定角速度 1.0 rad/s，根据角度计算持续时间
    omega = 1.0  # 固定角速度 (rad/s)
    radians = math.radians(degrees_safe)  # 将角度转换为弧度
    duration = abs(radians) / omega  # 计算持续时间（秒）
    vyaw = omega if radians > 0 else -omega  # 根据角度正负确定旋转方向
    
    # 限制持续时间在安全范围内
    duration = max(
        SAFETY_CONFIG["MIN_DURATION"], 
        min(duration, SAFETY_CONFIG["MAX_DURATION"])
    )  # 限制duration在[MIN_DURATION, MAX_DURATION]范围内
    
    # 使用任务队列（新增）
    task_id = action_manager.add_task(
        task_type="rotate",  # 任务类型
        parameters={
            "vyaw": vyaw,  # 旋转角速度
            "degrees": degrees_safe  # 旋转角度（保存以便记录）
        },
        duration=duration  # 持续时间
    )
    
    # 构建返回结果
    # 构建返回结果
    msg = f"机器人旋转任务已添加: {degrees_safe:.1f}° (vyaw={vyaw:.2f} rad/s, duration={duration:.2f}s, task_id: {task_id})"
    if warning:
        msg += f" (已截断参数: {warning})"

    result = {
        "status": "success" if is_valid else "success_with_warning",  # 状态：成功或成功但有警告
        "message": msg,  # 执行信息
        "data": {
            "task_id": task_id,  # 任务ID
            "degrees": degrees_safe,  # 实际旋转角度
            "radians": radians,  # 弧度值
            "vyaw": vyaw,  # 角速度
            "duration": duration  # 持续时间
        }
    }
    
    if warning:  # 如果有警告信息
        result["warning"] = warning  # 添加警告字段
    
    if LOGGING_CONFIG["LOG_EXECUTION_RESULTS"]:  # 如果启用执行结果日志
        logger.info(f"[Bridge] {result['message']}")  # 记录执行结果
    
    return result  # 返回执行结果


def _execute_emergency_stop(action_manager: ActionManager) -> Dict[str, Any]:
    """执行紧急停止指令"""
    # 调用 ActionManager 的紧急停止方法
    action_manager.emergency_stop()  # 立即切换到阻尼模式并停止运动
    
    # 构建返回结果
    result = {
        "status": "success",  # 状态：成功
        "message": "执行紧急停止！机器人已进入阻尼模式",  # 执行信息
        "data": {"emergency": True}  # 紧急停止标志
    }
    
    if LOGGING_CONFIG["LOG_EXECUTION_RESULTS"]:  # 如果启用执行结果日志
        logger.warning(f"[Bridge] {result['message']}")  # 记录执行结果（使用warning级别强调）
    
    return result  # 返回执行结果


def _execute_wave_hand(g1_arm_client: Any) -> Dict[str, Any]:
    """执行挥手动作指令"""
    # 检查 g1_arm_client 是否可用
    if not g1_arm_client:  # 检查 g1_arm_client 是否为 None
        error_msg = "G1 手臂动作客户端未初始化"  # 错误信息
        logger.error(f"[Bridge] {error_msg}")  # 记录错误日志
        return {"status": "error", "message": error_msg}  # 返回错误结果
    
    try:
        # 调用 SDK 挥手接口 (face wave = 25)
        g1_arm_client.ExecuteAction(25)
        
        # 构建返回结果
        result = {
            "status": "success",  # 状态：成功
            "message": "挥手动作已执行",  # 执行信息
            "data": {"action": "wave_hand", "type": "face_wave"}  # 动作详情
        }
        
        if LOGGING_CONFIG["LOG_EXECUTION_RESULTS"]:  # 如果启用执行结果日志
            logger.info(f"[Bridge] {result['message']}")  # 记录执行结果
        
        return result  # 返回执行结果
    
    except Exception as e:  # 捕获所有异常
        error_msg = f"挥手动作执行失败: {str(e)}"  # 错误信息
        logger.error(f"[Bridge] {error_msg}", exc_info=True)  # 记录异常日志（包含堆栈）
        return {"status": "error", "message": error_msg}  # 返回错误结果

