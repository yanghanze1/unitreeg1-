# -*- coding: utf-8 -*-
"""
emergency_stop.py 模块测试

测试键盘急停监听功能
创建时间: 2026-1-21
"""

import pytest  # 导入pytest测试框架
import threading  # 导入线程模块
import time  # 导入时间模块
from unittest.mock import Mock, MagicMock, patch  # 导入Mock工具

# 导入被测模块
import sys  # 导入系统模块
import os  # 导入操作系统模块
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 添加父目录到路径

from emergency_stop import start_keyboard_listener, _on_press  # 导入键盘监听函数


class TestEmergencyStop:
    """键盘急停模块测试类"""
    
    def test_keyboard_listener_creation(self):
        """测试键盘监听线程创建"""
        # 创建Mock对象
        mock_action_manager = Mock()  # 模拟ActionManager
        mock_g1_client = Mock()  # 模拟G1客户端
        
        # 使用patch模拟pynput.keyboard.Listener
        with patch('emergency_stop.keyboard.Listener') as mock_listener_class:
            # 配置Mock行为
            mock_listener_instance = Mock()  # 模拟Listener实例
            mock_listener_class.return_value = mock_listener_instance  # 返回实例
            
            # 调用函数
            listener = start_keyboard_listener(mock_action_manager, mock_g1_client)
            
            # 验证Listener被创建
            mock_listener_class.assert_called_once()  # 验证Listener构造函数被调用一次
            
            # 验证Listener被启动
            mock_listener_instance.start.assert_called_once()  # 验证start方法被调用
            
            # 验证返回值是Listener实例
            assert listener == mock_listener_instance  # 验证返回的是正确的实例
    
    def test_emergency_stop_trigger_on_space(self):
        """测试Space键触发急停"""
        # 创建Mock对象
        mock_action_manager = Mock()  # 模拟ActionManager
        mock_g1_client = Mock()  # 模拟G1客户端
        
        # 模拟Space键事件
        from pynput.keyboard import Key  # 导入Key常量
        
        # 调用按键处理函数
        _on_press(Key.space, mock_action_manager, mock_g1_client)
        
        # 验证ActionManager的emergency_stop被调用
        mock_action_manager.emergency_stop.assert_called_once()  # 验证急停方法被调用
        
        # 验证G1客户端的Damp被调用（双重保险）
        mock_g1_client.Damp.assert_called_once()  # 验证阻尼模式被激活
    
    def test_non_space_key_ignored(self):
        """测试非Space键不触发急停"""
        # 创建Mock对象
        mock_action_manager = Mock()  # 模拟ActionManager
        mock_g1_client = Mock()  # 模拟G1客户端
        
        # 模拟其他按键事件
        from pynput.keyboard import Key  # 导入Key常量
        
        # 调用按键处理函数（测试Enter键）
        _on_press(Key.enter, mock_action_manager, mock_g1_client)
        
        # 验证ActionManager的emergency_stop未被调用
        mock_action_manager.emergency_stop.assert_not_called()  # 验证急停未触发
        
        # 验证G1客户端的Damp未被调用
        mock_g1_client.Damp.assert_not_called()  # 验证阻尼模式未激活
    
    def test_thread_lifecycle(self):
        """测试监听线程生命周期"""
        # 创建Mock对象
        mock_action_manager = Mock()  # 模拟ActionManager
        mock_g1_client = Mock()  # 模拟G1客户端
        
        # 使用patch模拟pynput.keyboard.Listener
        with patch('emergency_stop.keyboard.Listener') as mock_listener_class:
            # 配置Mock行为
            mock_listener_instance = Mock()  # 模拟Listener实例
            mock_listener_instance.daemon = False  # 初始化daemon属性
            mock_listener_class.return_value = mock_listener_instance  # 返回实例
            
            # 启动监听线程
            listener = start_keyboard_listener(mock_action_manager, mock_g1_client)
            
            # 验证线程被设置为守护线程
            assert listener.daemon == True  # 验证守护线程标志
    
    def test_exception_handling(self):
        """测试异常处理机制"""
        # 创建Mock对象（ActionManager会抛出异常）
        mock_action_manager = Mock()  # 模拟ActionManager
        mock_action_manager.emergency_stop.side_effect = Exception("Test exception")  # 模拟异常
        mock_g1_client = Mock()  # 模拟G1客户端
        
        # 模拟Space键事件
        from pynput.keyboard import Key  # 导入Key常量
        
        # 调用按键处理函数（应该捕获异常，不崩溃）
        try:
            _on_press(Key.space, mock_action_manager, mock_g1_client)
            # 如果没有抛出异常，测试通过
            assert True  # 验证异常被捕获
        except Exception:
            # 如果抛出异常，测试失败
            assert False, "异常未被正确捕获"  # 测试失败


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])  # 以详细模式运行测试
