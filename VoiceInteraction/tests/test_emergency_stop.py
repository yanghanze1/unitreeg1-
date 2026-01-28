# -*- coding: utf-8 -*-
"""
emergency_stop.py 模块测试

测试键盘急停监听功能（SSH/Headless 版）
创建时间: 2026-1-21
修改时间: 2026-1-28
"""

import pytest  # 导入pytest测试框架
import threading  # 导入线程模块
import time  # 导入时间模块
from unittest.mock import Mock, MagicMock, patch  # 导入Mock工具

# 导入被测模块
import sys  # 导入系统模块
import os  # 导入操作系统模块
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 添加父目录到路径

from emergency_stop import (  # 导入键盘监听函数
    start_keyboard_listener,
    _trigger_emergency_stop
)


class TestEmergencyStop:
    """键盘急停模块测试类"""

    def test_keyboard_listener_creation(self):
        """测试键盘监听线程创建"""
        # 创建Mock对象
        mock_action_manager = Mock()  # 模拟ActionManager
        mock_g1_client = Mock()  # 模拟G1客户端

        # 使用patch使线程函数持续运行一小段时间
        def mock_monitor(*args, **kwargs):
            time.sleep(0.2)  # 模拟监听循环运行0.2秒

        with patch('emergency_stop._monitor_terminal_input', side_effect=mock_monitor):
            # 调用函数
            thread = start_keyboard_listener(mock_action_manager, mock_g1_client)

            # 验证返回的是线程对象
            assert isinstance(thread, threading.Thread)  # 验证返回类型

            # 验证线程是守护线程
            assert thread.daemon is True  # 验证为守护线程

            # 等待一小段时间确保线程已启动
            time.sleep(0.05)  # 等待50ms

            # 验证线程已启动（由于mock函数会sleep 0.2秒，此时线程仍在运行）
            assert thread.is_alive()  # 验证线程存活

    def test_emergency_stop_trigger(self):
        """测试急停触发功能"""
        # 创建Mock对象
        mock_action_manager = Mock()  # 模拟ActionManager
        mock_g1_client = Mock()  # 模拟G1客户端

        # 调用急停触发函数
        _trigger_emergency_stop(mock_action_manager, mock_g1_client)

        # 验证ActionManager的emergency_stop被调用
        mock_action_manager.emergency_stop.assert_called_once()  # 验证急停方法被调用

        # 验证G1客户端的Damp被调用（双重保险）
        mock_g1_client.Damp.assert_called_once()  # 验证阻尼模式被激活

    def test_emergency_stop_with_none_action_manager(self):
        """测试ActionManager为None时的急停"""
        # ActionManager为None
        mock_g1_client = Mock()  # 模拟G1客户端

        # 调用急停触发函数（不应崩溃）
        _trigger_emergency_stop(None, mock_g1_client)

        # 验证G1客户端的Damp仍被调用
        mock_g1_client.Damp.assert_called_once()  # 验证阻尼模式被激活

    def test_emergency_stop_with_none_g1_client(self):
        """测试G1Client为None时的急停"""
        # G1Client为None
        mock_action_manager = Mock()  # 模拟ActionManager

        # 调用急停触发函数（不应崩溃）
        _trigger_emergency_stop(mock_action_manager, None)

        # 验证ActionManager的emergency_stop仍被调用
        mock_action_manager.emergency_stop.assert_called_once()  # 验证急停方法被调用

    def test_exception_handling(self):
        """测试异常处理机制"""
        # 创建Mock对象（ActionManager会抛出异常）
        mock_action_manager = Mock()  # 模拟ActionManager
        mock_action_manager.emergency_stop.side_effect = Exception("Test exception")  # 模拟异常
        mock_g1_client = Mock()  # 模拟G1客户端

        # 调用急停触发函数（应该捕获异常，不崩溃）
        try:
            _trigger_emergency_stop(mock_action_manager, mock_g1_client)
            # 如果没有抛出异常，测试通过
            assert True  # 验证异常被捕获
        except Exception:
            # 如果抛出异常，测试失败
            assert False, "异常未被正确捕获"  # 测试失败


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])  # 以详细模式运行测试
