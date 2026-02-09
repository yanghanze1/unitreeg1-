# -*- coding: utf-8 -*-
"""
测试 config.py 配置模块
验证所有配置项存在、类型正确、值合理
"""

import pytest
from VoiceInteraction.config import (
    SAFETY_CONFIG,
    FUNCTION_CALLING_CONFIG,
    LOGGING_CONFIG
)


class TestSafetyConfig:
    """测试安全参数配置"""
    
    def test_safety_config_exists(self):
        """验证安全配置存在"""
        assert SAFETY_CONFIG is not None  # 安全配置不应为 None
        assert isinstance(SAFETY_CONFIG, dict)  # 安全配置应为字典类型
    
    def test_speed_limits_exist(self):
        """验证速度限制参数存在"""
        assert "MAX_SAFE_SPEED_VX" in SAFETY_CONFIG  # 必须有前进速度限制
        assert "MAX_SAFE_SPEED_VY" in SAFETY_CONFIG  # 必须有横向速度限制
        assert "MAX_SAFE_OMEGA" in SAFETY_CONFIG  # 必须有旋转速度限制
    
    def test_speed_limits_types(self):
        """验证速度限制参数类型"""
        assert isinstance(SAFETY_CONFIG["MAX_SAFE_SPEED_VX"], (int, float))  # vx 限制应为数值类型
        assert isinstance(SAFETY_CONFIG["MAX_SAFE_SPEED_VY"], (int, float))  # vy 限制应为数值类型
        assert isinstance(SAFETY_CONFIG["MAX_SAFE_OMEGA"], (int, float))  # omega 限制应为数值类型
    
    def test_speed_limits_positive(self):
        """验证速度限制为正值"""
        assert SAFETY_CONFIG["MAX_SAFE_SPEED_VX"] > 0  # vx 限制应大于 0
        assert SAFETY_CONFIG["MAX_SAFE_SPEED_VY"] > 0  # vy 限制应大于 0
        assert SAFETY_CONFIG["MAX_SAFE_OMEGA"] > 0  # omega 限制应大于 0
    
    def test_speed_limits_reasonable(self):
        """验证速度限制在合理范围内（防止过大或过小）"""
        assert SAFETY_CONFIG["MAX_SAFE_SPEED_VX"] <= 5.0  # vx 不应超过 5 m/s（人形机器人）
        assert SAFETY_CONFIG["MAX_SAFE_SPEED_VY"] <= 5.0  # vy 不应超过 5 m/s
        assert SAFETY_CONFIG["MAX_SAFE_OMEGA"] <= 10.0  # omega 不应超过 10 rad/s
        
        assert SAFETY_CONFIG["MAX_SAFE_SPEED_VX"] >= 0.1  # vx 不应小于 0.1 m/s（太小无意义）
        assert SAFETY_CONFIG["MAX_SAFE_SPEED_VY"] >= 0.1  # vy 不应小于 0.1 m/s
        assert SAFETY_CONFIG["MAX_SAFE_OMEGA"] >= 0.1  # omega 不应小于 0.1 rad/s
    
    def test_duration_params_exist(self):
        """验证持续时间参数存在"""
        assert "MAX_DURATION" in SAFETY_CONFIG  # 必须有最大持续时间
        assert "DEFAULT_DURATION" in SAFETY_CONFIG  # 必须有默认持续时间
        assert "MIN_DURATION" in SAFETY_CONFIG  # 必须有最小持续时间
    
    def test_duration_params_types(self):
        """验证持续时间参数类型"""
        assert isinstance(SAFETY_CONFIG["MAX_DURATION"], (int, float))  # 最大持续时间应为数值
        assert isinstance(SAFETY_CONFIG["DEFAULT_DURATION"], (int, float))  # 默认持续时间应为数值
        assert isinstance(SAFETY_CONFIG["MIN_DURATION"], (int, float))  # 最小持续时间应为数值
    
    def test_duration_params_positive(self):
        """验证持续时间参数为正值"""
        assert SAFETY_CONFIG["MAX_DURATION"] > 0  # 最大持续时间应大于 0
        assert SAFETY_CONFIG["DEFAULT_DURATION"] > 0  # 默认持续时间应大于 0
        assert SAFETY_CONFIG["MIN_DURATION"] > 0  # 最小持续时间应大于 0
    
    def test_duration_params_logical(self):
        """验证持续时间参数逻辑正确（MIN < DEFAULT < MAX）"""
        assert SAFETY_CONFIG["MIN_DURATION"] < SAFETY_CONFIG["DEFAULT_DURATION"]  # 最小 < 默认
        assert SAFETY_CONFIG["DEFAULT_DURATION"] <= SAFETY_CONFIG["MAX_DURATION"]  # 默认 <= 最大
    
    def test_rotation_params_exist(self):
        """验证旋转角度参数存在"""
        assert "MAX_ROTATION_DEGREES" in SAFETY_CONFIG  # 必须有最大旋转角度
        assert "MIN_ROTATION_DEGREES" in SAFETY_CONFIG  # 必须有最小旋转角度
    
    def test_rotation_params_types(self):
        """验证旋转角度参数类型"""
        assert isinstance(SAFETY_CONFIG["MAX_ROTATION_DEGREES"], (int, float))  # 最大角度应为数值
        assert isinstance(SAFETY_CONFIG["MIN_ROTATION_DEGREES"], (int, float))  # 最小角度应为数值
    
    def test_rotation_params_symmetric(self):
        """验证旋转角度对称（MIN = -MAX）"""
        assert SAFETY_CONFIG["MIN_ROTATION_DEGREES"] == -SAFETY_CONFIG["MAX_ROTATION_DEGREES"]  # 应对称


class TestFunctionCallingConfig:
    """测试 Function Calling 配置"""
    
    def test_function_calling_config_exists(self):
        """验证 Function Calling 配置存在"""
        assert FUNCTION_CALLING_CONFIG is not None  # 配置不应为 None
        assert isinstance(FUNCTION_CALLING_CONFIG, dict)  # 配置应为字典类型
    
    def test_enabled_flag_exists(self):
        """验证启用标志存在"""
        assert "ENABLED" in FUNCTION_CALLING_CONFIG  # 必须有 ENABLED 标志
        assert isinstance(FUNCTION_CALLING_CONFIG["ENABLED"], bool)  # ENABLED 应为布尔类型
    
    def test_fallback_flag_exists(self):
        """验证回退标志存在"""
        assert "FALLBACK_TO_KEYWORDS" in FUNCTION_CALLING_CONFIG  # 必须有回退标志
        assert isinstance(FUNCTION_CALLING_CONFIG["FALLBACK_TO_KEYWORDS"], bool)  # 回退标志应为布尔类型
    
    def test_timeout_exists(self):
        """验证超时参数存在"""
        assert "TIMEOUT" in FUNCTION_CALLING_CONFIG  # 必须有超时参数
        assert isinstance(FUNCTION_CALLING_CONFIG["TIMEOUT"], (int, float))  # 超时应为数值
        assert FUNCTION_CALLING_CONFIG["TIMEOUT"] > 0  # 超时应大于 0
        assert FUNCTION_CALLING_CONFIG["TIMEOUT"] <= 30  # 超时不应超过 30 秒（太长会影响用户体验）
    
    def test_max_retries_exists(self):
        """验证最大重试次数存在"""
        assert "MAX_RETRIES" in FUNCTION_CALLING_CONFIG  # 必须有最大重试次数
        assert isinstance(FUNCTION_CALLING_CONFIG["MAX_RETRIES"], int)  # 重试次数应为整数
        assert FUNCTION_CALLING_CONFIG["MAX_RETRIES"] >= 0  # 重试次数应 >= 0
        assert FUNCTION_CALLING_CONFIG["MAX_RETRIES"] <= 5  # 重试次数不应太多（影响性能）
    
    def test_model_exists(self):
        """验证模型名称存在"""
        assert "MODEL" in FUNCTION_CALLING_CONFIG  # 必须有模型名称
        assert isinstance(FUNCTION_CALLING_CONFIG["MODEL"], str)  # 模型名称应为字符串
        assert len(FUNCTION_CALLING_CONFIG["MODEL"]) > 0  # 模型名称不应为空
    
    def test_temperature_exists(self):
        """验证温度参数存在"""
        assert "TEMPERATURE" in FUNCTION_CALLING_CONFIG  # 必须有温度参数
        assert isinstance(FUNCTION_CALLING_CONFIG["TEMPERATURE"], (int, float))  # 温度应为数值
        assert 0 <= FUNCTION_CALLING_CONFIG["TEMPERATURE"] <= 2  # 温度应在 [0, 2] 范围内
    
    def test_max_tokens_exists(self):
        """验证最大 token 数存在"""
        assert "MAX_TOKENS" in FUNCTION_CALLING_CONFIG  # 必须有最大 token 数
        assert isinstance(FUNCTION_CALLING_CONFIG["MAX_TOKENS"], int)  # token 数应为整数
        assert FUNCTION_CALLING_CONFIG["MAX_TOKENS"] > 0  # token 数应大于 0


class TestLoggingConfig:
    """测试日志配置"""
    
    def test_logging_config_exists(self):
        """验证日志配置存在"""
        assert LOGGING_CONFIG is not None  # 日志配置不应为 None
        assert isinstance(LOGGING_CONFIG, dict)  # 日志配置应为字典类型
    
    def test_log_flags_exist(self):
        """验证日志标志存在"""
        assert "LOG_TOOL_CALLS" in LOGGING_CONFIG  # 必须有工具调用日志标志
        assert "LOG_PARAMETER_VALIDATION" in LOGGING_CONFIG  # 必须有参数验证日志标志
        assert "LOG_EXECUTION_RESULTS" in LOGGING_CONFIG  # 必须有执行结果日志标志
    
    def test_log_flags_types(self):
        """验证日志标志类型"""
        assert isinstance(LOGGING_CONFIG["LOG_TOOL_CALLS"], bool)  # 工具调用日志应为布尔类型
        assert isinstance(LOGGING_CONFIG["LOG_PARAMETER_VALIDATION"], bool)  # 参数验证日志应为布尔类型
        assert isinstance(LOGGING_CONFIG["LOG_EXECUTION_RESULTS"], bool)  # 执行结果日志应为布尔类型
