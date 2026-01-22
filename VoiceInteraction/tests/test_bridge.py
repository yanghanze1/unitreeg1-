
import pytest
from unittest.mock import MagicMock
from VoiceInteraction.bridge import (
    validate_movement_params, 
    validate_rotation_angle, 
    execute_tool_call,
    _execute_move_robot
)
from VoiceInteraction.config import SAFETY_CONFIG

class TestBridgeSafety:
    """测试 bridge.py 中的安全校验逻辑"""

    def test_validate_movement_params_valid(self):
        """测试安全范围内的有效参数。"""
        vx = SAFETY_CONFIG["MAX_SAFE_SPEED_VX"] * 0.5
        vy = SAFETY_CONFIG["MAX_SAFE_SPEED_VY"] * 0.5
        vyaw = SAFETY_CONFIG["MAX_SAFE_OMEGA"] * 0.5
        
        is_valid, warning, params = validate_movement_params(vx, vy, vyaw)
        
        assert is_valid is True
        assert warning == ""
        assert params["vx"] == vx
        assert params["vy"] == vy
        assert params["vyaw"] == vyaw

    def test_validate_movement_params_exceed_limit(self):
        """测试超出安全限制的参数会被截断。"""
        vx_too_high = SAFETY_CONFIG["MAX_SAFE_SPEED_VX"] * 2.0
        
        is_valid, warning, params = validate_movement_params(vx_too_high, 0.0, 0.0)
        
        assert is_valid is False  # 应该被标记为由警告 (False 表示非完全合规)
        
        assert "超限" in warning
        assert params["vx"] == SAFETY_CONFIG["MAX_SAFE_SPEED_VX"]

    def test_validate_rotation_angle_valid(self):
        """测试有效的旋转角度。"""
        degrees = 45.0
        is_valid, warning, safe_degrees = validate_rotation_angle(degrees)
        assert is_valid is True
        assert safe_degrees == degrees

    def test_validate_rotation_angle_exceed(self):
        """测试旋转角度截断。"""
        max_deg = SAFETY_CONFIG["MAX_ROTATION_DEGREES"]
        degrees = max_deg + 100.0
        
        is_valid, warning, safe_degrees = validate_rotation_angle(degrees)
        
        assert is_valid is False
        assert "超限" in warning
        assert safe_degrees == max_deg
    
    def test_validate_duration_limits(self):
        """测试持续时间参数验证和截断。"""
        # 测试超出最大持续时间
        vx = 0.5
        vy = 0.0
        vyaw = 0.0
        duration_too_long = SAFETY_CONFIG["MAX_DURATION"] * 2.0
        
        is_valid, warning, params = validate_movement_params(vx, vy, vyaw, duration_too_long)
        
        assert is_valid is False  # 应有警告
        assert "超限" in warning  # 警告信息应包含"超限"
        assert params["duration"] == SAFETY_CONFIG["MAX_DURATION"]  # 持续时间应被截断
        
        # 测试低于最小持续时间
        duration_too_short = SAFETY_CONFIG["MIN_DURATION"] * 0.5
        
        is_valid2, warning2, params2 = validate_movement_params(vx, vy, vyaw, duration_too_short)
        
        assert is_valid2 is False  # 应有警告
        assert "超限" in warning2  # 警告信息应包含"超限"
        assert params2["duration"] == SAFETY_CONFIG["MIN_DURATION"]  # 持续时间应被截断


class TestBridgeExecution:
    """测试工具执行分发逻辑。"""

    def test_execute_tool_call_not_running(self, mock_g1_client):
        """测试当 ActionManager 未运行时执行工具。"""
        mock_am = MagicMock()
        mock_am._running = False
        
        result = execute_tool_call("move_robot", {}, mock_am, mock_g1_client)
        
        assert result["status"] == "error"
        assert "未运行" in result["message"]

    def test_execute_tool_call_move_robot(self, mock_g1_client):
        """测试分发 move_robot 工具。"""
        mock_am = MagicMock()
        mock_am._running = True
        
        params = {"vx": 0.5, "duration": 1.0}
        
        result = execute_tool_call("move_robot", params, mock_am, mock_g1_client)
        
        assert result["status"] == "success"
        mock_am.update_target_velocity.assert_called_once()
        args, kwargs = mock_am.update_target_velocity.call_args
        assert kwargs["vx"] == 0.5
        assert kwargs["duration"] == 1.0

    def test_execute_tool_call_emergency_stop(self, mock_g1_client):
        """测试分发 emergency_stop 工具。"""
        mock_am = MagicMock()
        mock_am._running = True
        
        result = execute_tool_call("emergency_stop", {}, mock_am, mock_g1_client)
        
        assert result["status"] == "success"
        mock_am.emergency_stop.assert_called_once()
    
    def test_execute_rotate_angle(self, mock_g1_client):
        """测试分发 rotate_angle 工具。"""
        mock_am = MagicMock()
        mock_am._running = True
        
        params = {"degrees": 90.0}
        
        result = execute_tool_call("rotate_angle", params, mock_am, mock_g1_client)
        
        assert result["status"] == "success"  # 应该成功执行
        mock_am.update_target_velocity.assert_called_once()  # 应调用速度更新
        args, kwargs = mock_am.update_target_velocity.call_args
        assert kwargs["vyaw"] != 0  # 旋转速度应非零
    
    def test_execute_stop_robot(self, mock_g1_client):
        """测试分发 stop_robot 工具。"""
        mock_am = MagicMock()
        mock_am._running = True
        
        result = execute_tool_call("stop_robot", {}, mock_am, mock_g1_client)
        
        assert result["status"] == "success"  # 应该成功执行
        mock_am.set_idle.assert_called_once()  # 应调用设置为空闲状态
    
    def test_execute_unknown_tool(self, mock_g1_client):
        """测试未知工具调用的错误处理。"""
        mock_am = MagicMock()
        mock_am._running = True
        
        result = execute_tool_call("unknown_tool_xyz", {}, mock_am, mock_g1_client)
        
        assert result["status"] == "error"  # 应返回错误状态
        assert "未知" in result["message"] or "不支持" in result["message"]  # 错误信息应说明未知工具
    
    def test_concurrent_tool_calls(self, mock_g1_client):
        """测试并发工具调用的线程安全性（简单验证）。"""
        import threading
        
        mock_am = MagicMock()
        mock_am._running = True
        results = []
        
        def call_tool():
            result = execute_tool_call("stop_robot", {}, mock_am, mock_g1_client)
            results.append(result)
        
        # 创建多个线程同时调用工具
        threads = [threading.Thread(target=call_tool) for _ in range(5)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # 验证所有调用都成功完成
        assert len(results) == 5  # 应有5个结果
        for result in results:
            assert result["status"] == "success"  # 每个调用都应成功
