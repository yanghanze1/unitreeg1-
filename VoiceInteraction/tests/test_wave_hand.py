# -*- coding: utf-8 -*-
"""
挥手功能单元测试

测试范围：
- 工具定义验证
- Bridge 层执行逻辑 (使用 G1ArmActionClient)
- 关键词匹配 (修正全局变量依赖)
- 自我介绍检测
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from tool_schema import TOOL_WAVE_HAND, ROBOT_TOOLS, TOOL_NAME_CN
from bridge import execute_tool_call, _execute_wave_hand
from multimodal_interaction import (
    try_execute_g1_by_local_keywords,
    _detect_self_introduction
)

# ===================== 工具定义测试 =====================

def test_wave_hand_tool_schema():
    """验证挥手工具定义符合 OpenAI 标准"""
    assert TOOL_WAVE_HAND["type"] == "function"
    assert TOOL_WAVE_HAND["function"]["name"] == "wave_hand"
    assert "description" in TOOL_WAVE_HAND["function"]
    assert TOOL_WAVE_HAND["function"]["parameters"]["type"] == "object"


def test_wave_hand_in_robot_tools():
    """验证挥手工具已注册到机器人工具列表"""
    tool_names = [tool["function"]["name"] for tool in ROBOT_TOOLS]
    assert "wave_hand" in tool_names


def test_wave_hand_chinese_name():
    """验证挥手工具的中文名称映射"""
    assert "wave_hand" in TOOL_NAME_CN
    assert TOOL_NAME_CN["wave_hand"] == "挥手动作"


# ===================== Bridge 层测试 =====================

def test_execute_wave_hand_success():
    """测试挥手执行函数成功场景"""
    mock_g1_arm = Mock()  # 创建 mock 手臂客户端
    mock_g1_arm.ExecuteAction = Mock()  # mock ExecuteAction 方法
    
    result = _execute_wave_hand(mock_g1_arm)  # 执行挥手
    
    assert result["status"] == "success"
    assert "挥手动作已执行" in result["message"]
    assert result["data"]["type"] == "face_wave"
    # 验证调用 Action ID 25 (face wave)
    mock_g1_arm.ExecuteAction.assert_called_once_with(25)


def test_execute_wave_hand_g1_arm_client_none():
    """测试 g1_arm_client 为 None 的错误处理"""
    result = _execute_wave_hand(None)
    
    assert result["status"] == "error"
    assert "未初始化" in result["message"]


def test_execute_wave_hand_exception():
    """测试挥手执行时的异常处理"""
    mock_g1_arm = Mock()
    mock_g1_arm.ExecuteAction = Mock(side_effect=Exception("SDK Error"))
    
    result = _execute_wave_hand(mock_g1_arm)
    
    assert result["status"] == "error"
    assert "执行失败" in result["message"]


def test_execute_tool_call_wave_hand():
    """测试通过 execute_tool_call 调用挥手"""
    mock_action_manager = Mock()
    mock_action_manager._running = True
    mock_g1 = Mock()      # 移动客户端
    mock_g1_arm = Mock()  # 手臂客户端
    mock_g1_arm.ExecuteAction = Mock()
    
    result = execute_tool_call(
        tool_name="wave_hand",
        params={},
        action_manager=mock_action_manager,
        g1_client=mock_g1,
        g1_arm_client=mock_g1_arm  # 传入手臂客户端
    )
    
    assert result["status"] == "success"
    mock_g1_arm.ExecuteAction.assert_called_once_with(25)


# ===================== 关键词匹配测试 =====================

@pytest.mark.parametrize("keyword", [
    "挥手", "招招手", "打个招呼", "挥挥手", "招手",
])
def test_wave_hand_keyword_matching(keyword):
    """测试挥手关键词匹配"""
    mock_action_manager = Mock()
    mock_action_manager._running = True
    
    # patch multimodal_interaction 中的全局 g1_arm 和 g1
    # 注意：我们的代码里也检查 g1/g1_arm 是否存在
    with patch('multimodal_interaction.g1_arm') as mock_g1_arm, \
         patch('multimodal_interaction.g1') as mock_g1:
        
        mock_g1_arm.ExecuteAction = Mock()
        
        # 模拟 g1 和 g1_arm 都已经初始化
        # try_execute_g1_by_local_keywords 内部只检查 g1 (实际上它不检查 g1_arm? 
        # 等等，之前的代码片段我把本地关键词也改成检查 g1_arm 了)
        # 所以必须 mock g1_arm
        
        result = try_execute_g1_by_local_keywords(keyword, mock_action_manager)
        
        assert result is True
        mock_g1_arm.ExecuteAction.assert_called_once_with(25)


def test_wave_hand_keyword_not_matched():
    """测试移动指令不触发挥手"""
    mock_action_manager = Mock()
    mock_action_manager._running = True
    
    with patch('multimodal_interaction.g1_arm') as mock_g1_arm, \
         patch('multimodal_interaction.g1') as mock_g1:
        
        # "前进" 命中移动逻辑，不应触发挥手
        result = try_execute_g1_by_local_keywords("前进", mock_action_manager)
        
        assert result is True  # 被处理了
        mock_g1_arm.ExecuteAction.assert_not_called()
        # 移动逻辑会调用 update_target_velocity，这里我们只需确保护手没被调用


# ===================== 自我介绍检测测试 =====================

@pytest.mark.parametrize("intro_text, expected", [
    ("我是机器人", True),
    ("我的名字是小明", True),
    ("我叫 Unitree G1", True),
    ("你好我是你的助手", True),
    ("大家好我是演示机器人", True),
    ("你可以叫我G1", True),
    ("我的名字叫机器人", True),
    ("让我介绍一下自己", True),
    ("我来介绍我的功能", True),
    ("这是自我介绍环节", True),
    ("今天天气真好", False),
    ("请向前走", False),
    ("", False),
])
def test_detect_self_introduction(intro_text, expected):
    """测试自我介绍检测准确性"""
    result = _detect_self_introduction(intro_text)
    assert result == expected


def test_detect_self_introduction_empty():
    """测试空文本不触发自我介绍检测"""
    assert _detect_self_introduction("") is False
    assert _detect_self_introduction(None) is False
    assert _detect_self_introduction("   ") is False


# ===================== 集成测试 =====================

def test_wave_hand_full_pipeline():
    """测试挥手功能完整流程"""
    mock_action_manager = Mock()
    mock_action_manager._running = True
    mock_g1 = Mock()
    mock_g1_arm = Mock()
    mock_g1.WaveHand = Mock() # 不应被调用
    mock_g1_arm.ExecuteAction = Mock()
    
    # 场景1: 关键词触发
    with patch('multimodal_interaction.g1_arm', mock_g1_arm), \
         patch('multimodal_interaction.g1', mock_g1):
        result = try_execute_g1_by_local_keywords("挥手", mock_action_manager)
        assert result is True
    
    # 场景2: 工具调用触发
    result = execute_tool_call(
        tool_name="wave_hand",
        params={},
        action_manager=mock_action_manager,
        g1_client=mock_g1,
        g1_arm_client=mock_g1_arm
    )
    assert result["status"] == "success"
    
    # 验证总共调用了 2 次 ExecuteAction(25)
    # mock_g1_arm 在上面被重用吗？
    # 注意：Scenario 1 用的是 patch 的 mock_g1_arm。Scenario 2 传入的是 mock_g1_arm。
    # 如果两个对象是同一个（这里代码写的是同一个对象），那么计数累加。
    # 但是 patch 的 mock_g1_arm 和外部定义的 mock_g1_arm 变量是不是同一个？
    # patch 传入了 new=mock_g1_arm，所以是同一个。
    
    assert mock_g1_arm.ExecuteAction.call_count == 2
    mock_g1.WaveHand.assert_not_called()
