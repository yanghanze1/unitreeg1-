
import pytest
import time
import threading
from unittest.mock import MagicMock, patch, call
from VoiceInteraction.action_manager import ActionManager, ActionType

class TestActionManager:
    
    @pytest.fixture
    def manager(self, mock_g1_client):
        """ActionManager 实例的 fixture"""
        return ActionManager(mock_g1_client)

    def test_init(self, manager):
        """测试初始化状态"""
        assert manager._current_action == ActionType.IDLE
        assert manager._target_vx == 0.0
        assert manager._running is False

    def test_update_target_velocity(self, manager):
        """测试目标速度更新逻辑"""
        manager.update_target_velocity(0.5, 0.1, -0.2, duration=2.0)
        
        state = manager.get_current_state()
        assert state["vx"] == 0.5
        assert state["vy"] == 0.1
        assert state["vyaw"] == -0.2
        assert state["action"] == "MOVE"
        assert manager._move_duration == 2.0

    def test_emergency_stop(self, manager, mock_g1_client):
        """测试紧急停止逻辑 (High Priority)"""
        # 设置初始状态
        manager.update_target_velocity(1.0, 0.0, 0.0)
        
        # 触发急停
        manager.emergency_stop()
        
        # 验证内部状态
        state = manager.get_current_state()
        assert state["action"] == "EMERGENCY"
        assert state["emergency"] is True
        assert state["vx"] == 0.0
        
        # 验证 SDK 调用
        mock_g1_client.StopMove.assert_called()
        mock_g1_client.Damp.assert_called()

    def test_recover_from_emergency(self, manager, mock_g1_client):
        """测试从急停状态恢复"""
        manager.emergency_stop()
        assert manager._emergency_flag is True
        
        success = manager.recover_from_emergency()
        
        assert success is True
        assert manager._emergency_flag is False
        assert manager._current_action == ActionType.IDLE
        mock_g1_client.RecoveryStand.assert_called()

    @patch('time.sleep')
    @patch('time.time')
    def test_control_loop_integration(self, mock_time, mock_sleep, manager, mock_g1_client):
        """
        测试控制循环逻辑 (集成测试)。
        使用 mock 模拟时间流逝和 sleep，防止无限循环。
        """
        # 模拟设置
        manager._running = True
        manager.update_target_velocity(0.8, 0.0, 0.0)
        
        # Mock time.time 以返回递增的值
        # 我们使用 side_effect 函数来处理任意次数的调用（例如来自日志记录的调用）
        self._current_sim_time = 0.0
        self._time_call_count = 0
        def time_side_effect():
            self._time_call_count += 1
            if self._time_call_count > 20: 
                manager._running = False # 安全网：防止死循环
            
            self._current_sim_time += 0.005 # 小幅递增
            return self._current_sim_time
        mock_time.side_effect = time_side_effect
        
        # Mock sleep 
        # 我们使用闭包来修改状态
        def sleep_side_effect(seconds):
            # 将模拟时间向前推进
            self._current_sim_time += seconds
            if mock_sleep.call_count >= 3:
                manager._running = False

        
        mock_sleep.side_effect = sleep_side_effect
        
        # 直接运行循环（同步运行），避免多线程问题
        manager._control_loop()
        
        # 验证 Move 是否被调用
        # 注意：取决于具体逻辑，大约被调用 3 次
        assert mock_g1_client.Move.call_count >= 3
        
        # 检查最后一次调用的参数
        args, kwargs = mock_g1_client.Move.call_args
        assert args[0] == 0.8 # vx
        assert kwargs['continous_move'] is True

    @patch('time.sleep')
    @patch('time.time')
    def test_control_loop_emergency_priority(self, mock_time, mock_sleep, manager, mock_g1_client):
        """验证紧急停止在控制循环中具有最高优先级（不发送移动指令）"""
        manager._running = True
        manager.emergency_stop() # 设置为 EMERGENCY 状态
        
        
        # 无限时间 mock (带安全网)
        self._time_call_count_2 = 0
        def time_side_effect_2():
            self._time_call_count_2 += 1
            if self._time_call_count_2 > 20:
                manager._running = False
            return 0.01

        mock_time.side_effect = time_side_effect_2
        # sleep 时直接终止循环
        mock_sleep.side_effect = lambda s: setattr(manager, '_running', False)
        
        manager._control_loop()
        
        # Move 不应被调用
        mock_g1_client.Move.assert_not_called()
        # StopMove 应该被调用 (在 emergency 状态的循环内)
        assert mock_g1_client.StopMove.call_count >= 1
