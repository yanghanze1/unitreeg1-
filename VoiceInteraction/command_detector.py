# -*- coding: utf-8 -*-
"""
命令检测模块：语音命令识别与分类

功能：
1. 打断命令检测（停止播放、闭嘴等）
2. 自我介绍检测（触发挥手）
3. 本地关键词匹配（前进、后退、急停等）

创建时间: 2026-01-29
"""

import re  # 导入正则表达式模块
import logging  # 导入日志模块
from typing import TYPE_CHECKING  # 导入类型检查

if TYPE_CHECKING:
    from action_manager import ActionManager  # 仅用于类型提示

# 配置日志记录器
logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


def is_interrupt_command(transcript: str) -> bool:
    """
    检测是否为打断命令
    
    只在"模型正在播放/输出中"时启用：
    - 强触发：打断 / 别说了 / 闭嘴 / 安静 / 停止播放 / 停止回答 / 暂停播放 等
    - 弱触发：出现"停止/暂停/停一下"且同时包含"说/讲/回答/播放/声音"
    
    Args:
        transcript: 用户语音转写文本
        
    Returns:
        是否为打断命令
    """
    t = (transcript or "").strip().lower()  # 转换为小写并去除空白
    if not t:  # 如果文本为空
        return False  # 返回 False

    # 强触发关键词列表
    strong = [
        "打断", "别说了", "不要说了", "闭嘴", "安静",
        "停止播放", "暂停播放", "停止回答", "停止讲", "停止说话",
        "停播", "停一下声音", "不要播了", "停止",
    ]
    for k in strong:  # 遍历强触发关键词
        if k in t:  # 如果包含关键词
            return True  # 返回 True

    # 弱触发：同时包含停止意图和语音相关词
    if ("停止" in t or "暂停" in t or "停一下" in t or "停" == t) and any(
        x in t for x in ["说", "讲", "回答", "播放", "声音", "语音"]
    ):
        return True  # 返回 True

    return False  # 未匹配到打断命令


def detect_self_introduction(text: str) -> bool:
    """
    检测文本是否为自我介绍
    
    Args:
        text: LLM 输出的文本内容
        
    Returns:
        是否为自我介绍
    """
    if not text:  # 检查文本是否为空
        return False  # 空文本不是自我介绍
    
    t = text.strip()  # 去除文本两端空白字符
    
    # 自我介绍关键词列表
    intro_keywords = [
        "我是", "我的名字", "我叫", "你好我是", 
        "大家好我是", "你可以叫我", "我的名字叫",
        "让我介绍一下", "我来介绍", "自我介绍"
    ]
    
    # 检查是否包含任何自我介绍关键词
    return any(kw in t for kw in intro_keywords)


def is_complex_command(text: str) -> bool:
    """
    检测指令是否为复杂指令（需要 Function Calling 处理）
    
    复杂指令特征：
    - 包含数字
    - 包含中文数字或量词
    - 包含修饰词或复合动作关键词
    
    Args:
        text: 用户语音转写文本
        
    Returns:
        是否为复杂指令
    """
    t = (text or "").strip()  # 去除两端空白
    if not t:  # 如果文本为空
        return False  # 返回 False
    
    # 检测阿拉伯数字
    if re.search(r'\d+', t):  # 如果包含数字
        return True  # 返回 True
    
    # 检测中文数字和修饰词
    complex_markers = [
        # "一" 太容易误触（如"介绍一下"），改为更明确的量词搭配
        "一米", "一度", "一秒", "一步", "一圈",
        "二", "三", "四", "五", "六", "七", "八", "九", "十", "半",
        "慢慢", "快速", "缓缓", "稍微", "一点",
        "并且", "同时", "然后",
    ]
    if any(marker in t for marker in complex_markers):  # 如果包含复杂标记
        return True  # 返回 True
    
    return False  # 非复杂指令


def try_execute_g1_by_local_keywords(
    text: str, 
    action_manager: "ActionManager",
    g1_arm=None
) -> bool:
    """
    基于本地关键词匹配执行 G1 机器人动作
    
    Args:
        text: 用户语音转写文本
        action_manager: 动作管理器实例
        g1_arm: G1 手臂动作客户端实例（可选）
        
    Returns:
        是否成功匹配并执行了动作指令
    """
    # 检查依赖是否有效
    if not action_manager:  # 如果 action_manager 为 None
        return False  # 返回 False
    
    # 检查 ActionManager 是否正在运行
    if not action_manager._running:  # 如果未运行
        logger.warning("[G1] ActionManager 未运行，指令被忽略")  # 记录警告
        return False  # 返回 False
    
    t = (text or "").strip()  # 去除文本两端空白字符
    
    # 急停关键词检测
    if "急停" in t or "停止电机" in t or "别动" in t:  # 检测急停关键词
        action_manager.emergency_stop()  # 执行急停
        return True  # 返回 True
    
    # 挥手关键词检测
    if any(kw in t for kw in ["挥手", "招招手", "打个招呼", "挥挥手", "招手"]):  # 检测挥手关键词
        logger.info(f"[Local] 检测到挥手指令: {t}")  # 记录检测到挥手指令
        if g1_arm:  # 检查 g1_arm 手臂动作客户端是否可用
            try:
                # 使用 G1ArmActionClient 执行挥手动作（face wave = 25, high wave = 26）
                g1_arm.ExecuteAction(25)  # 调用 SDK 执行 face wave 动作
                logger.info("[Local] 挥手动作执行成功（face wave）")  # 记录成功日志
            except Exception as e:  # 捕获执行异常
                logger.error(f"[Local] 挥手动作执行失败: {e}")  # 记录错误日志
        else:
            logger.warning("[Local] g1_arm 客户端未初始化，无法执行挥手")  # 记录警告
        return True  # 返回 True
    
    # 前进关键词检测
    if "前进" in t or "向前" in t or "往前" in t:  # 检测前进关键词
        action_manager.update_target_velocity(vx=0.5, vy=0.0, vyaw=0.0, duration=2.0)  # 设置前进速度
        return True  # 返回 True
    
    # 后退关键词检测
    if "后退" in t or "往后" in t or "向后" in t:  # 检测后退关键词
        action_manager.update_target_velocity(vx=-0.5, vy=0.0, vyaw=0.0, duration=2.0)  # 设置后退速度
        return True  # 返回 True
    
    # 左转关键词检测
    if "左转" in t or "向左" in t:  # 检测左转关键词
        action_manager.update_target_velocity(vx=0.0, vy=0.0, vyaw=0.8, duration=2.0)  # 设置左转速度
        return True  # 返回 True
    
    # 右转关键词检测
    if "右转" in t or "向右" in t:  # 检测右转关键词
        action_manager.update_target_velocity(vx=0.0, vy=0.0, vyaw=-0.8, duration=2.0)  # 设置右转速度
        return True  # 返回 True
    
    # 停止关键词检测
    if "停止" in t or "停车" in t or "站住" in t:  # 检测停止关键词
        action_manager.set_idle()  # 设置空闲状态
        return True  # 返回 True
        
    return False  # 未匹配到任何关键词


# 导出公共接口
__all__ = [
    'is_interrupt_command',
    'detect_self_introduction', 
    'is_complex_command',
    'try_execute_g1_by_local_keywords'
]  # 定义模块导出列表
