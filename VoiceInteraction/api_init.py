# -*- coding: utf-8 -*-
"""
API 初始化模块：DashScope 和 OpenAI 客户端管理

功能：
1. 统一 API Key 管理
2. DashScope 端点初始化
3. OpenAI 兼容客户端单例
4. Function Calling 接口封装

创建时间: 2026-01-29
"""

import os  # 导入操作系统模块
import json  # 导入 JSON 模块
import logging  # 导入日志模块
from typing import List, Dict, Any  # 导入类型提示

import dashscope  # 导入 DashScope SDK

try:
    from openai import OpenAI  # 尝试导入 OpenAI 库
except ImportError:
    OpenAI = None  # 标记 OpenAI 不可用

from llm_api_config import DEFAULT_CONFIG  # 导入 LLM API 配置
from config import FUNCTION_CALLING_CONFIG  # 导入 Function Calling 配置

# 配置日志记录器
logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器

# OpenAI 客户端单例
_OPENAI_CLIENT = None  # 全局 OpenAI 客户端实例


def get_dashscope_api_key() -> str:
    """
    获取 DashScope API Key
    
    优先级：环境变量 > 配置文件
    
    Returns:
        API Key 字符串
        
    Raises:
        RuntimeError: 未找到 API Key 时抛出
    """
    key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()  # 从环境变量获取
    if not key:  # 如果环境变量为空
        key = (DEFAULT_CONFIG.get("api_key") or "").strip()  # 从配置文件获取
    if not key:  # 如果仍为空
        raise RuntimeError(
            "未找到 DashScope API Key：请设置环境变量 DASHSCOPE_API_KEY，"
            "或在 llm_api_config.py 的 DEFAULT_CONFIG['api_key'] 中配置"
        )
    os.environ["DASHSCOPE_API_KEY"] = key  # 设置环境变量
    dashscope.api_key = key  # 设置 DashScope API Key
    return key  # 返回 API Key


def init_dashscope_endpoints() -> str:
    """
    初始化 DashScope 端点配置
    
    根据配置文件中的 base_url 自动选择国内/国际端点
    
    Returns:
        默认的 Omni WebSocket 端点 URL
    """
    _ = get_dashscope_api_key()  # 确保 API Key 已设置
    base_url = (DEFAULT_CONFIG.get("base_url") or "").lower()  # 获取 base_url

    if "dashscope-intl" in base_url:  # 如果是国际端点
        dashscope.base_websocket_api_url = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"  # 设置 WebSocket 端点
        dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"  # 设置 HTTP 端点
        default_omni_ws = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"  # 设置 Omni 端点
    else:  # 使用国内端点
        dashscope.base_websocket_api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"  # 设置 WebSocket 端点
        dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"  # 设置 HTTP 端点
        default_omni_ws = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"  # 设置 Omni 端点

    return default_omni_ws  # 返回默认 Omni 端点


def get_openai_client():
    """
    获取 OpenAI 兼容客户端（单例模式）
    
    Returns:
        OpenAI 客户端实例
        
    Raises:
        ImportError: openai 库未安装时抛出
    """
    global _OPENAI_CLIENT  # 声明使用全局变量
    if _OPENAI_CLIENT is None:  # 如果实例不存在
        if OpenAI is None:  # 如果 OpenAI 未导入
            raise ImportError("缺少 openai 库，请运行: pip install openai")
        
        _OPENAI_CLIENT = OpenAI(
            api_key=get_dashscope_api_key(),  # 使用 DashScope API Key
            base_url=DEFAULT_CONFIG.get(
                "base_url", 
                "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),  # 设置兼容模式 base_url
        )
    return _OPENAI_CLIENT  # 返回客户端实例


def call_qwen_for_tool_use(user_message: str, tools: List[Dict]) -> List[Dict[str, Any]]:
    """
    调用标准 Qwen API 进行工具调用推理
    
    Args:
        user_message: 用户消息
        tools: 工具定义列表
        
    Returns:
        工具调用列表，格式: [{"name": "tool_name", "arguments": {...}}, ...]
        如果调用失败或无工具调用，返回空列表
    """
    # 检查功能开关
    if not FUNCTION_CALLING_CONFIG.get("ENABLED", True):  # 检查是否启用 Function Calling
        return []  # 未启用则返回空列表
    
    try:
        # 使用单例客户端，避免重复创建连接
        client = get_openai_client()  # 获取 OpenAI 客户端
        
        # 构建消息
        messages = [    
            {
                "role": "system",
                "content": (
                    "你是一个机器人控制助手。根据用户指令，选择合适的工具来控制机器人移动。"
                    "只在用户明确表达了移动意图时才调用工具。"
                )
            },  # 系统提示
            {"role": "user", "content": user_message}  # 用户消息
        ]
        
        # 调用 API
        response = client.chat.completions.create(
            model=FUNCTION_CALLING_CONFIG.get("MODEL", "qwen-max"),  # 使用配置的模型
            messages=messages,  # 消息列表
            tools=tools,  # 工具定义列表
            tool_choice="auto",  # 自动选择是否调用工具
            temperature=FUNCTION_CALLING_CONFIG.get("TEMPERATURE", 0.3),  # 温度参数
            max_tokens=FUNCTION_CALLING_CONFIG.get("MAX_TOKENS", 500),  # 最大 token 数
            timeout=FUNCTION_CALLING_CONFIG.get("TIMEOUT", 3.0),  # 超时时间
        )
        
        # 提取工具调用
        tool_calls = []  # 初始化工具调用列表
        message = response.choices[0].message  # 获取响应消息
        
        if hasattr(message, 'tool_calls') and message.tool_calls:  # 检查是否有工具调用
            for tool_call in message.tool_calls:  # 遍历所有工具调用
                tool_calls.append({
                    "name": tool_call.function.name,  # 工具名称
                    "arguments": json.loads(tool_call.function.arguments),  # 工具参数
                })  # 添加到工具调用列表
            
            logger.info(f"[FunctionCalling] LLM 生成了 {len(tool_calls)} 个工具调用")  # 记录日志
        
        return tool_calls  # 返回工具调用列表
    
    except ImportError:  # 捕获 openai 库未安装的异常
        logger.error("[FunctionCalling] 缺少 openai 库，请运行: pip install openai")  # 记录错误
        return []  # 返回空列表
    
    except Exception as e:  # 捕获所有其他异常
        logger.error(f"[FunctionCalling] 调用 Qwen API 失败: {e}")  # 记录错误
        return []  # 返回空列表


# 导出公共接口
__all__ = [
    'get_dashscope_api_key',
    'init_dashscope_endpoints',
    'get_openai_client',
    'call_qwen_for_tool_use'
]  # 定义模块导出列表
