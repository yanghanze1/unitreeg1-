# -*- coding: utf-8 -*-
"""
API 初始化模块单元测试

测试内容：
1. DashScope API Key 获取
2. Function Calling 工具调用
"""

import pytest  # 导入 pytest 测试框架
import os  # 导入操作系统模块
from unittest.mock import MagicMock, patch  # 导入 Mock 工具


class TestCallQwenForToolUse:
    """Function Calling 工具调用测试类"""

    def test_disabled_returns_empty_list(self):
        """测试功能禁用时返回空列表"""
        mock_fc_config = {"ENABLED": False}
        
        with patch('VoiceInteraction.api_init.FUNCTION_CALLING_CONFIG', mock_fc_config):
            from VoiceInteraction.api_init import call_qwen_for_tool_use
            
            result = call_qwen_for_tool_use("前进一米", [])
            assert result == []  # 验证返回空列表

    def test_api_call_returns_tool_calls(self):
        """测试 API 调用返回工具调用"""
        mock_fc_config = {
            "ENABLED": True,
            "MODEL": "qwen-max",
            "TEMPERATURE": 0.3,
            "MAX_TOKENS": 500,
            "TIMEOUT": 3.0
        }
        
        # 创建模拟的响应
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "move_robot"
        mock_tool_call.function.arguments = '{"vx": 0.5, "vy": 0.0, "vyaw": 0.0}'
        
        mock_message = MagicMock()
        mock_message.tool_calls = [mock_tool_call]
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        
        with patch('VoiceInteraction.api_init.FUNCTION_CALLING_CONFIG', mock_fc_config):
            with patch('VoiceInteraction.api_init.get_openai_client', return_value=mock_client):
                from VoiceInteraction.api_init import call_qwen_for_tool_use
                
                result = call_qwen_for_tool_use("前进", [{"type": "function"}])
                
                # 验证返回工具调用
                assert len(result) == 1
                assert result[0]["name"] == "move_robot"
                assert result[0]["arguments"]["vx"] == 0.5

    def test_api_call_no_tool_calls_returns_empty(self):
        """测试 API 返回无工具调用时返回空列表"""
        mock_fc_config = {
            "ENABLED": True, 
            "MODEL": "qwen-max", 
            "TEMPERATURE": 0.3, 
            "MAX_TOKENS": 500, 
            "TIMEOUT": 3.0
        }
        
        mock_message = MagicMock()
        mock_message.tool_calls = None  # 无工具调用
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        
        with patch('VoiceInteraction.api_init.FUNCTION_CALLING_CONFIG', mock_fc_config):
            with patch('VoiceInteraction.api_init.get_openai_client', return_value=mock_client):
                from VoiceInteraction.api_init import call_qwen_for_tool_use
                
                result = call_qwen_for_tool_use("你好", [])
                
                # 验证返回空列表
                assert result == []

    def test_api_call_exception_handled_gracefully(self):
        """测试 API 调用异常被优雅处理"""
        mock_fc_config = {
            "ENABLED": True, 
            "MODEL": "qwen-max", 
            "TEMPERATURE": 0.3, 
            "MAX_TOKENS": 500, 
            "TIMEOUT": 3.0
        }
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        
        with patch('VoiceInteraction.api_init.FUNCTION_CALLING_CONFIG', mock_fc_config):
            with patch('VoiceInteraction.api_init.get_openai_client', return_value=mock_client):
                from VoiceInteraction.api_init import call_qwen_for_tool_use
                
                # 不应抛出异常
                result = call_qwen_for_tool_use("前进", [])
                
                # 验证返回空列表
                assert result == []


class TestGetDashscopeApiKey:
    """DashScope API Key 获取测试类"""

    def test_get_key_from_env_variable(self):
        """测试从环境变量获取 API Key"""
        test_key = "test-api-key-from-env"
        
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": test_key}):
            with patch('VoiceInteraction.api_init.DEFAULT_CONFIG', {"api_key": "", "base_url": ""}):
                with patch('VoiceInteraction.api_init.dashscope') as mock_dashscope:
                    from VoiceInteraction.api_init import get_dashscope_api_key
                    
                    key = get_dashscope_api_key()
                    assert key == test_key

    def test_get_key_from_config_when_env_empty(self):
        """测试环境变量为空时从配置获取"""
        config_key = "test-api-key-from-config"
        
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": ""}):
            with patch('VoiceInteraction.api_init.DEFAULT_CONFIG', {"api_key": config_key, "base_url": ""}):
                with patch('VoiceInteraction.api_init.dashscope') as mock_dashscope:
                    from VoiceInteraction.api_init import get_dashscope_api_key
                    
                    key = get_dashscope_api_key()
                    assert key == config_key

    def test_raises_error_when_no_key_available(self):
        """测试无 API Key 时抛出 RuntimeError"""
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": ""}):
            with patch('VoiceInteraction.api_init.DEFAULT_CONFIG', {"api_key": "", "base_url": ""}):
                from VoiceInteraction.api_init import get_dashscope_api_key
                
                with pytest.raises(RuntimeError) as exc_info:
                    get_dashscope_api_key()
                
                assert "未找到 DashScope API Key" in str(exc_info.value)


class TestInitDashscopeEndpoints:
    """DashScope 端点初始化测试类"""

    def test_domestic_endpoint_selected(self):
        """测试选择国内端点"""
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}):
            with patch('VoiceInteraction.api_init.DEFAULT_CONFIG', {
                "api_key": "test-key",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
            }):
                with patch('VoiceInteraction.api_init.dashscope') as mock_dashscope:
                    from VoiceInteraction.api_init import init_dashscope_endpoints
                    
                    url = init_dashscope_endpoints()
                    
                    # 验证返回国内端点
                    assert "dashscope.aliyuncs.com" in url
                    assert "intl" not in url

    def test_international_endpoint_selected(self):
        """测试选择国际端点"""
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}):
            with patch('VoiceInteraction.api_init.DEFAULT_CONFIG', {
                "api_key": "test-key",
                "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            }):
                with patch('VoiceInteraction.api_init.dashscope') as mock_dashscope:
                    from VoiceInteraction.api_init import init_dashscope_endpoints
                    
                    url = init_dashscope_endpoints()
                    
                    # 验证返回国际端点
                    assert "dashscope-intl.aliyuncs.com" in url
