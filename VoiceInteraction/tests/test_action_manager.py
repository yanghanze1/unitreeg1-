
import pytest  # 导入pytest测试框架
import time  # 导入时间模块
import threading  # 导入线程模块
from unittest.mock import MagicMock, patch, call  # 导入Mock工具
from VoiceInteraction.action_manager import ActionManager, ActionType  # 导入被测模块


class TestActionManager:
    """ActionManager 动作管理器测试类"""

    @pytest.fixture
    def manager(self, mock_g1_client):
        """ActionManager 实例的 fixture"""
        return ActionManager(mock_g1_client)  # 创建ActionManager实例

    def test_init(self, manager):
        """测试初始化状态"""
        assert manager._current_action == ActionType.IDLE  # 验证初始动作为空闲
        assert manager._target_vx == 0.0  # 验证初始速度为0
        assert manager._running is False  # 验证初始未运行

    def test_update_target_velocity(self, manager):
        """测试目标速度更新逻辑"""
        manager.update_target_velocity(0.5, 0.1, -0.2, duration=2.0)  # 更新目标速度

        state = manager.get_current_state()  # 获取当前状态
        assert state["vx"] == 0.5  # 验证vx已更新
        assert state["vy"] == 0.1  # 验证vy已更新
        assert state["vyaw"] == -0.2  # 验证vyaw已更新
        assert state["action"] == "MOVE"  # 验证动作类型为移动
        assert manager._move_duration == 2.0  # 验证持续时间已设置

    def test_emergency_stop(self, manager, mock_g1_client):
        """测试紧急停止逻辑 (High Priority)"""
        # 设置初始状态
        manager.update_target_velocity(1.0, 0.0, 0.0)  # 设置初始速度

        # 触发急停
        manager.emergency_stop()  # 调用急停方法

        # 验证内部状态
        state = manager.get_current_state()  # 获取当前状态
        assert state["action"] == "EMERGENCY"  # 验证动作类型为紧急停止
        assert state["emergency"] is True  # 验证急停标志为True
        assert state["vx"] == 0.0  # 验证速度已归零

        # 验证 SDK 调用 - 实际实现调用的是 Damp() 而非 StopMove()
        mock_g1_client.Damp.assert_called()  # 验证Damp被调用（阻尼模式）

    def test_recover_from_emergency(self, manager, mock_g1_client):
        """测试从急停状态恢复"""
        manager.emergency_stop()  # 先触发急停
        assert manager._emergency_flag is True  # 验证急停标志

        success = manager.recover_from_emergency()  # 尝试恢复

        assert success is True  # 验证恢复成功
        assert manager._emergency_flag is False  # 验证急停标志已清除
        assert manager._current_action == ActionType.IDLE  # 验证动作类型为空闲
        # 实际实现调用的是 Squat2StandUp() 而非 RecoveryStand()
        mock_g1_client.Squat2StandUp.assert_called()  # 验证起立指令被调用

    @patch('time.sleep')
    @patch('time.time')
    def test_control_loop_integration(self, mock_time, mock_sleep, manager, mock_g1_client):
        """
        测试控制循环逻辑 (集成测试)。
        使用 mock 模拟时间流逝和 sleep，防止无限循环。
        """
        # 模拟设置
        manager._running = True  # 设置为运行状态
        manager.update_target_velocity(0.8, 0.0, 0.0)  # 设置目标速度

        # Mock time.time 以返回递增的值
        self._current_sim_time = 0.0  # 初始化模拟时间
        self._time_call_count = 0  # 初始化调用计数

        def time_side_effect():
            self._time_call_count += 1  # 增加调用计数
            if self._time_call_count > 20:  # 安全网：防止死循环
                manager._running = False  # 停止循环

            self._current_sim_time += 0.005  # 小幅递增模拟时间
            return self._current_sim_time  # 返回模拟时间

        mock_time.side_effect = time_side_effect  # 设置side_effect

        # Mock sleep
        def sleep_side_effect(seconds):
            self._current_sim_time += seconds  # 将模拟时间向前推进
            if mock_sleep.call_count >= 3:  # 经过3次sleep后
                manager._running = False  # 停止循环

        mock_sleep.side_effect = sleep_side_effect  # 设置side_effect

        # 直接运行循环（同步运行），避免多线程问题
        manager._control_loop()  # 运行控制循环

        # 验证 Move 是否被调用
        assert mock_g1_client.Move.call_count >= 3  # 验证Move被调用至少3次

        # 检查最后一次调用的参数 - 实际实现 Move() 只接收位置参数，没有 continous_move
        args, kwargs = mock_g1_client.Move.call_args  # 获取最后一次调用的参数
        assert args[0] == 0.8  # 验证vx参数正确
        # 注意: 实际实现不使用 continous_move 关键字参数

    @patch('time.sleep')
    @patch('time.time')
    def test_control_loop_emergency_priority(self, mock_time, mock_sleep, manager, mock_g1_client):
        """验证紧急停止在控制循环中具有最高优先级（不发送移动指令）"""
        manager._running = True  # 设置为运行状态
        manager.emergency_stop()  # 设置为 EMERGENCY 状态

        # 无限时间 mock (带安全网)
        self._time_call_count_2 = 0  # 初始化调用计数

        def time_side_effect_2():
            self._time_call_count_2 += 1  # 增加调用计数
            if self._time_call_count_2 > 20:  # 安全网
                manager._running = False  # 停止循环
            return 0.01  # 返回固定时间

        mock_time.side_effect = time_side_effect_2  # 设置side_effect
        # sleep 时直接终止循环
        mock_sleep.side_effect = lambda s: setattr(manager, '_running', False)  # 设置side_effect

        manager._control_loop()  # 运行控制循环

        # Move 不应被调用
        mock_g1_client.Move.assert_not_called()  # 验证Move未被调用
        # 实际实现在 EMERGENCY 状态下调用 Damp() 而非 StopMove()
        assert mock_g1_client.Damp.call_count >= 1  # 验证Damp被调用
