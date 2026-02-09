
import pytest  # 导入pytest测试框架
from unittest.mock import MagicMock  # 导入Mock工具
from VoiceInteraction.bridge import (  # 导入被测函数
    validate_movement_params,
    validate_rotation_angle,
    execute_tool_call,
    _execute_move_robot
)
from VoiceInteraction.config import SAFETY_CONFIG  # 导入安全配置


class TestBridgeSafety:
    """测试 bridge.py 中的安全校验逻辑"""

    def test_validate_movement_params_valid(self):
        """测试安全范围内的有效参数。"""
        vx = SAFETY_CONFIG["MAX_SAFE_SPEED_VX"] * 0.5  # 取限制值的一半
        vy = SAFETY_CONFIG["MAX_SAFE_SPEED_VY"] * 0.5  # 取限制值的一半
        vyaw = SAFETY_CONFIG["MAX_SAFE_OMEGA"] * 0.5  # 取限制值的一半

        is_valid, warning, params = validate_movement_params(vx, vy, vyaw)  # 验证参数

        assert is_valid is True  # 参数有效
        assert warning == ""  # 无警告
        assert params["vx"] == vx  # vx未变
        assert params["vy"] == vy  # vy未变
        assert params["vyaw"] == vyaw  # vyaw未变

    def test_validate_movement_params_exceed_limit(self):
        """测试超出安全限制的参数会被截断。"""
        vx_too_high = SAFETY_CONFIG["MAX_SAFE_SPEED_VX"] * 2.0  # 超出限制的vx

        is_valid, warning, params = validate_movement_params(vx_too_high, 0.0, 0.0)  # 验证参数

        assert is_valid is False  # 参数被截断
        assert "超限" in warning  # 警告信息包含"超限"
        assert params["vx"] == SAFETY_CONFIG["MAX_SAFE_SPEED_VX"]  # vx被截断

    def test_validate_rotation_angle_valid(self):
        """测试有效的旋转角度。"""
        degrees = 45.0  # 有效角度
        is_valid, warning, safe_degrees = validate_rotation_angle(degrees)  # 验证角度
        assert is_valid is True  # 角度有效
        assert safe_degrees == degrees  # 角度未变

    def test_validate_rotation_angle_exceed(self):
        """测试旋转角度截断。"""
        max_deg = SAFETY_CONFIG["MAX_ROTATION_DEGREES"]  # 最大角度
        degrees = max_deg + 100.0  # 超出限制的角度

        is_valid, warning, safe_degrees = validate_rotation_angle(degrees)  # 验证角度

        assert is_valid is False  # 角度被截断
        assert "超限" in warning  # 警告信息包含"超限"
        assert safe_degrees == max_deg  # 角度被截断到最大值

    def test_validate_duration_limits(self):
        """测试持续时间参数验证和截断。"""
        # 测试超出最大持续时间
        vx = 0.5  # 有效速度
        vy = 0.0  # 无横向速度
        vyaw = 0.0  # 无旋转
        duration_too_long = SAFETY_CONFIG["MAX_DURATION"] * 2.0  # 超出最大时间

        is_valid, warning, params = validate_movement_params(vx, vy, vyaw, duration_too_long)  # 验证

        assert is_valid is False  # 参数被截断
        assert "超限" in warning  # 警告信息包含"超限"
        assert params["duration"] == SAFETY_CONFIG["MAX_DURATION"]  # 时间被截断

        # 测试低于最小持续时间
        duration_too_short = SAFETY_CONFIG["MIN_DURATION"] * 0.5  # 低于最小时间

        is_valid2, warning2, params2 = validate_movement_params(vx, vy, vyaw, duration_too_short)  # 验证

        assert is_valid2 is False  # 参数被截断
        assert "超限" in warning2  # 警告信息包含"超限"
        assert params2["duration"] == SAFETY_CONFIG["MIN_DURATION"]  # 时间被截断


class TestBridgeExecution:
    """测试工具执行分发逻辑。"""

    def test_execute_tool_call_not_running(self, mock_g1_client):
        """测试当 ActionManager 未运行时执行工具。"""
        mock_am = MagicMock()  # 创建Mock ActionManager
        mock_am._running = False  # 设置为未运行状态

        result = execute_tool_call("move_robot", {}, mock_am, mock_g1_client)  # 执行工具

        assert result["status"] == "error"  # 应返回错误
        assert "未运行" in result["message"]  # 错误信息包含"未运行"

    def test_execute_tool_call_move_robot(self, mock_g1_client):
        """测试分发 move_robot 工具。"""
        mock_am = MagicMock()  # 创建Mock ActionManager
        mock_am._running = True  # 设置为运行状态

        params = {"vx": 0.5, "duration": 1.0}  # 移动参数

        result = execute_tool_call("move_robot", params, mock_am, mock_g1_client)  # 执行工具

        assert result["status"] == "success"  # 应返回成功
        # 实际实现使用任务队列，调用的是 add_task 而非 update_target_velocity
        mock_am.add_task.assert_called_once()  # 验证add_task被调用
        args, kwargs = mock_am.add_task.call_args  # 获取调用参数
        assert kwargs["task_type"] == "move"  # 验证任务类型
        assert kwargs["parameters"]["vx"] == 0.5  # 验证vx参数

    def test_execute_tool_call_emergency_stop(self, mock_g1_client):
        """测试分发 emergency_stop 工具。"""
        mock_am = MagicMock()  # 创建Mock ActionManager
        mock_am._running = True  # 设置为运行状态

        result = execute_tool_call("emergency_stop", {}, mock_am, mock_g1_client)  # 执行工具

        assert result["status"] == "success"  # 应返回成功
        mock_am.emergency_stop.assert_called_once()  # 验证emergency_stop被调用

    def test_execute_rotate_angle(self, mock_g1_client):
        """测试分发 rotate_angle 工具。"""
        mock_am = MagicMock()  # 创建Mock ActionManager
        mock_am._running = True  # 设置为运行状态

        params = {"degrees": 90.0}  # 旋转参数

        result = execute_tool_call("rotate_angle", params, mock_am, mock_g1_client)  # 执行工具

        assert result["status"] == "success"  # 应返回成功
        # 实际实现使用任务队列，调用的是 add_task 而非 update_target_velocity
        mock_am.add_task.assert_called_once()  # 验证add_task被调用
        args, kwargs = mock_am.add_task.call_args  # 获取调用参数
        assert kwargs["task_type"] == "rotate"  # 验证任务类型
        assert kwargs["parameters"]["vyaw"] != 0  # 验证旋转速度非零

    def test_execute_stop_robot(self, mock_g1_client):
        """测试分发 stop_robot 工具。"""
        mock_am = MagicMock()  # 创建Mock ActionManager
        mock_am._running = True  # 设置为运行状态

        result = execute_tool_call("stop_robot", {}, mock_am, mock_g1_client)  # 执行工具

        assert result["status"] == "success"  # 应返回成功
        mock_am.set_idle.assert_called_once()  # 验证set_idle被调用

    def test_execute_unknown_tool(self, mock_g1_client):
        """测试未知工具调用的错误处理。"""
        mock_am = MagicMock()  # 创建Mock ActionManager
        mock_am._running = True  # 设置为运行状态

        result = execute_tool_call("unknown_tool_xyz", {}, mock_am, mock_g1_client)  # 执行未知工具

        assert result["status"] == "error"  # 应返回错误
        assert "未知" in result["message"] or "不支持" in result["message"]  # 错误信息

    def test_concurrent_tool_calls(self, mock_g1_client):
        """测试并发工具调用的线程安全性（简单验证）。"""
        import threading  # 导入线程模块

        mock_am = MagicMock()  # 创建Mock ActionManager
        mock_am._running = True  # 设置为运行状态
        results = []  # 结果列表

        def call_tool():
            result = execute_tool_call("stop_robot", {}, mock_am, mock_g1_client)  # 执行工具
            results.append(result)  # 添加结果

        # 创建多个线程同时调用工具
        threads = [threading.Thread(target=call_tool) for _ in range(5)]  # 创建5个线程

        for t in threads:  # 启动所有线程
            t.start()

        for t in threads:  # 等待所有线程完成
            t.join()

        # 验证所有调用都成功完成
        assert len(results) == 5  # 应有5个结果
        for result in results:  # 验证每个结果
            assert result["status"] == "success"  # 每个调用都应成功
