# -*- coding: utf-8 -*-
"""
命令检测模块单元测试

测试内容：
1. 打断命令检测 (is_interrupt_command)
2. 自我介绍检测 (detect_self_introduction)
3. 复杂指令检测 (is_complex_command)
4. 本地关键词执行 (try_execute_g1_by_local_keywords)3
"""

import pytest  # 导入 pytest 测试框架
from unittest.mock import MagicMock, patch  # 导入 Mock 工具

from VoiceInteraction.command_detector import (
    is_interrupt_command,
    detect_self_introduction,
    is_complex_command,
    try_execute_g1_by_local_keywords
)  # 导入被测函数


class TestIsInterruptCommand:
    """打断命令检测测试类"""

    def test_strong_interrupt_keywords(self):
        """测试强打断关键词"""
        # 强打断关键词应返回 True
        assert is_interrupt_command("打断") is True  # 验证"打断"关键词
        assert is_interrupt_command("别说了") is True  # 验证"别说了"关键词
        assert is_interrupt_command("闭嘴") is True  # 验证"闭嘴"关键词
        assert is_interrupt_command("安静") is True  # 验证"安静"关键词
        assert is_interrupt_command("停止播放") is True  # 验证"停止播放"关键词
        assert is_interrupt_command("暂停播放") is True  # 验证"暂停播放"关键词

    def test_weak_interrupt_keywords(self):
        """测试弱打断关键词（需同时包含意图和对象）"""
        # 弱打断：同时包含停止意图和语音相关词
        assert is_interrupt_command("停止说话") is True  # 验证弱打断
        assert is_interrupt_command("暂停声音") is True  # 验证弱打断
        assert is_interrupt_command("停一下播放") is True  # 验证弱打断

    def test_non_interrupt_commands(self):
        """测试非打断命令"""
        # 普通命令不应触发打断
        assert is_interrupt_command("前进") is False  # 验证普通命令
        assert is_interrupt_command("后退一米") is False  # 验证普通命令
        assert is_interrupt_command("你好") is False  # 验证问候
        assert is_interrupt_command("介绍一下自己") is False  # 验证普通请求

    def test_empty_and_none_input(self):
        """测试空输入和 None"""
        assert is_interrupt_command("") is False  # 验证空字符串
        assert is_interrupt_command(None) is False  # 验证 None
        assert is_interrupt_command("   ") is False  # 验证纯空白

    def test_case_insensitivity(self):
        """测试大小写不敏感"""
        # 中文没有大小写，但测试混合输入
        assert is_interrupt_command("  打断  ") is True  # 验证带空格的输入


class TestDetectSelfIntroduction:
    """自我介绍检测测试类"""

    def test_self_introduction_keywords(self):
        """测试自我介绍关键词"""
        assert detect_self_introduction("我是来福") is True  # 验证"我是"
        assert detect_self_introduction("我的名字叫来福") is True  # 验证"我的名字叫"
        assert detect_self_introduction("你好我是机器人") is True  # 验证"你好我是"
        assert detect_self_introduction("大家好我是来福") is True  # 验证"大家好我是"
        assert detect_self_introduction("让我介绍一下") is True  # 验证"让我介绍一下"

    def test_non_introduction_text(self):
        """测试非自我介绍文本"""
        assert detect_self_introduction("前进一米") is False  # 验证普通命令
        assert detect_self_introduction("你好") is False  # 验证问候
        assert detect_self_introduction("今天天气怎么样") is False  # 验证问题

    def test_empty_and_none_input(self):
        """测试空输入和 None"""
        assert detect_self_introduction("") is False  # 验证空字符串
        assert detect_self_introduction(None) is False  # 验证 None


class TestIsComplexCommand:
    """复杂指令检测测试类"""

    def test_arabic_numbers(self):
        """测试阿拉伯数字"""
        assert is_complex_command("前进1米") is True  # 验证包含数字
        assert is_complex_command("转90度") is True  # 验证包含数字
        assert is_complex_command("走3步") is True  # 验证包含数字

    def test_chinese_numbers_with_units(self):
        """测试中文数字量词组合"""
        assert is_complex_command("一米") is True  # 验证"一米"
        assert is_complex_command("三秒") is True  # 验证"三秒"
        assert is_complex_command("向前走半步") is True  # 验证"半"

    def test_modifier_words(self):
        """测试修饰词"""
        assert is_complex_command("慢慢前进") is True  # 验证"慢慢"
        assert is_complex_command("快速转身") is True  # 验证"快速"

    def test_compound_actions(self):
        """测试复合动作"""
        assert is_complex_command("前进然后转身") is True  # 验证"然后"
        assert is_complex_command("同时抬头") is True  # 验证"同时"

    def test_simple_commands(self):
        """测试简单命令（应返回 False）"""
        assert is_complex_command("前进") is False  # 验证简单命令
        assert is_complex_command("后退") is False  # 验证简单命令
        assert is_complex_command("停止") is False  # 验证简单命令
        assert is_complex_command("左转") is False  # 验证简单命令

    def test_empty_and_none_input(self):
        """测试空输入和 None"""
        assert is_complex_command("") is False  # 验证空字符串
        assert is_complex_command(None) is False  # 验证 None


class TestTryExecuteG1ByLocalKeywords:
    """本地关键词执行测试类"""

    @pytest.fixture
    def mock_action_manager(self):
        """创建模拟的 ActionManager"""
        manager = MagicMock()  # 创建 Mock 对象
        manager._running = True  # 设置为运行状态
        return manager

    @pytest.fixture
    def mock_g1_arm(self):
        """创建模拟的 G1 手臂客户端"""
        arm = MagicMock()  # 创建 Mock 对象
        return arm

    def test_emergency_stop(self, mock_action_manager):
        """测试急停关键词"""
        result = try_execute_g1_by_local_keywords("急停", mock_action_manager)  # 调用被测函数
        assert result is True  # 验证返回 True
        mock_action_manager.emergency_stop.assert_called_once()  # 验证 emergency_stop 被调用

    def test_forward_movement(self, mock_action_manager):
        """测试前进关键词"""
        result = try_execute_g1_by_local_keywords("前进", mock_action_manager)  # 调用被测函数
        assert result is True  # 验证返回 True
        mock_action_manager.update_target_velocity.assert_called_once()  # 验证方法被调用
        args, kwargs = mock_action_manager.update_target_velocity.call_args  # 获取调用参数
        assert kwargs.get("vx") == 0.5  # 验证 vx 参数

    def test_backward_movement(self, mock_action_manager):
        """测试后退关键词"""
        result = try_execute_g1_by_local_keywords("后退", mock_action_manager)  # 调用被测函数
        assert result is True  # 验证返回 True
        args, kwargs = mock_action_manager.update_target_velocity.call_args  # 获取调用参数
        assert kwargs.get("vx") == -0.5  # 验证 vx 为负值

    def test_left_turn(self, mock_action_manager):
        """测试左转关键词"""
        result = try_execute_g1_by_local_keywords("左转", mock_action_manager)  # 调用被测函数
        assert result is True  # 验证返回 True
        args, kwargs = mock_action_manager.update_target_velocity.call_args  # 获取调用参数
        assert kwargs.get("vyaw") == 0.8  # 验证 vyaw 正值（左转）

    def test_right_turn(self, mock_action_manager):
        """测试右转关键词"""
        result = try_execute_g1_by_local_keywords("右转", mock_action_manager)  # 调用被测函数
        assert result is True  # 验证返回 True
        args, kwargs = mock_action_manager.update_target_velocity.call_args  # 获取调用参数
        assert kwargs.get("vyaw") == -0.8  # 验证 vyaw 负值（右转）

    def test_stop_movement(self, mock_action_manager):
        """测试停止关键词"""
        result = try_execute_g1_by_local_keywords("停止", mock_action_manager)  # 调用被测函数
        assert result is True  # 验证返回 True
        mock_action_manager.set_idle.assert_called_once()  # 验证 set_idle 被调用

    def test_wave_hand(self, mock_action_manager, mock_g1_arm):
        """测试挥手关键词"""
        result = try_execute_g1_by_local_keywords(
            "挥手", mock_action_manager, mock_g1_arm
        )  # 调用被测函数
        assert result is True  # 验证返回 True
        mock_g1_arm.ExecuteAction.assert_called_once_with(25)  # 验证 ExecuteAction(25) 被调用

    def test_unknown_command(self, mock_action_manager):
        """测试未知命令"""
        result = try_execute_g1_by_local_keywords("跳舞", mock_action_manager)  # 调用被测函数
        assert result is False  # 验证返回 False

    def test_action_manager_not_running(self, mock_action_manager):
        """测试 ActionManager 未运行"""
        mock_action_manager._running = False  # 设置为未运行状态
        result = try_execute_g1_by_local_keywords("前进", mock_action_manager)  # 调用被测函数
        assert result is False  # 验证返回 False

    def test_action_manager_none(self):
        """测试 ActionManager 为 None"""
        result = try_execute_g1_by_local_keywords("前进", None)  # 调用被测函数
        assert result is False  # 验证返回 False
