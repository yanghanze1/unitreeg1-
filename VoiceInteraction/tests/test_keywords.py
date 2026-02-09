
import pytest  # 导入pytest测试框架
from unittest.mock import MagicMock  # 导入Mock工具
from VoiceInteraction.command_detector import try_execute_g1_by_local_keywords  # 导入被测函数（已迁移到 command_detector 模块）


class TestKeywords:
    """本地关键字匹配测试类"""

    def test_forward_command(self, mock_g1_client):
        """测试 '前进' 指令匹配。"""
        # Mock ActionManager
        action_manager = MagicMock()  # 创建Mock ActionManager
        action_manager._running = True  # 设置为运行状态

        # Test "前进"
        text = "请向前进一点"  # 测试文本
        result = try_execute_g1_by_local_keywords(text, action_manager)  # 执行关键字匹配

        assert result is True  # 应匹配成功
        action_manager.update_target_velocity.assert_called_once()  # 验证调用
        kwargs = action_manager.update_target_velocity.call_args[1]  # 获取关键字参数
        # 实际实现使用 vx=0.5（安全速度）而非 vx=1.0
        assert kwargs["vx"] == 0.5  # 验证vx为0.5

    def test_emergency_stop_command(self):
        """测试 '急停' 指令匹配 (最高优先级)。"""
        action_manager = MagicMock()  # 创建Mock ActionManager
        action_manager._running = True  # 设置为运行状态

        text = "马上急停！"  # 测试文本
        result = try_execute_g1_by_local_keywords(text, action_manager)  # 执行关键字匹配

        assert result is True  # 应匹配成功
        action_manager.emergency_stop.assert_called_once()  # 验证emergency_stop被调用

    def test_no_match(self):
        """测试无匹配指令的情况。"""
        action_manager = MagicMock()  # 创建Mock ActionManager
        action_manager._running = True  # 设置为运行状态

        text = "今天天气不错"  # 非指令文本
        result = try_execute_g1_by_local_keywords(text, action_manager)  # 执行关键字匹配

        assert result is False  # 应不匹配
        action_manager.update_target_velocity.assert_not_called()  # 验证未调用

    def test_manager_not_running(self):
        """测试 ActionManager 未运行时的行为。"""
        action_manager = MagicMock()  # 创建Mock ActionManager
        action_manager._running = False  # 设置为未运行状态

        result = try_execute_g1_by_local_keywords("前进", action_manager)  # 执行关键字匹配

        assert result is False  # 应不执行
        action_manager.update_target_velocity.assert_not_called()  # 验证未调用
