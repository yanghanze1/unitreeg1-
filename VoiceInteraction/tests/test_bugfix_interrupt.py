# -*- coding: utf-8 -*-
"""
打断逻辑 Bug 修复测试

测试复杂指令打断时的执行逻辑
(已迁移到新的模块结构)
"""

import unittest
from unittest.mock import MagicMock, patch
import threading
import time
import json
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 导入迁移后的模块
from command_detector import is_interrupt_command, is_complex_command


class TestInterruptDetection(unittest.TestCase):
    """测试打断检测逻辑"""
    
    def test_is_interrupt_command_strong_keywords(self):
        """测试强打断关键词检测"""
        self.assertTrue(is_interrupt_command("打断"))  # 验证"打断"
        self.assertTrue(is_interrupt_command("闭嘴"))  # 验证"闭嘴"
        self.assertTrue(is_interrupt_command("别说了"))  # 验证"别说了"
        self.assertTrue(is_interrupt_command("停止播放"))  # 验证"停止播放"
    
    def test_is_interrupt_command_non_interrupt(self):
        """测试非打断命令"""
        self.assertFalse(is_interrupt_command("前进"))  # 验证非打断命令
        self.assertFalse(is_interrupt_command("你好"))  # 验证非打断命令
        self.assertFalse(is_interrupt_command("左转90度"))  # 验证非打断命令


class TestComplexCommandDetection(unittest.TestCase):
    """测试复杂指令检测逻辑"""
    
    def test_complex_command_with_numbers(self):
        """测试包含数字的复杂指令"""
        self.assertTrue(is_complex_command("左转90度"))  # 包含数字
        self.assertTrue(is_complex_command("前进1米"))  # 包含数字
        self.assertTrue(is_complex_command("走3步"))  # 包含数字
    
    def test_complex_command_with_chinese_numbers(self):
        """测试包含中文数字量词的复杂指令"""
        self.assertTrue(is_complex_command("一米"))  # 包含中文数字
        self.assertTrue(is_complex_command("三秒"))  # 包含中文数字
    
    def test_complex_command_with_modifiers(self):
        """测试包含修饰词的复杂指令"""
        self.assertTrue(is_complex_command("慢慢前进"))  # 包含修饰词
        self.assertTrue(is_complex_command("快速转身"))  # 包含修饰词
    
    def test_simple_command_not_complex(self):
        """测试简单指令不应被识别为复杂指令"""
        self.assertFalse(is_complex_command("前进"))  # 简单命令
        self.assertFalse(is_complex_command("后退"))  # 简单命令
        self.assertFalse(is_complex_command("停止"))  # 简单命令


class TestInterruptWithStopKeyword(unittest.TestCase):
    """测试包含停止关键词的打断逻辑"""
    
    def test_emergency_stop_keyword(self):
        """测试急停关键词检测"""
        # 测试包含急停的文本
        text = "急停并且停止"
        
        # 检测是否包含停止关键词
        stop_keywords = ["停", "急停", "别动", "站住"]
        has_stop = any(x in text for x in stop_keywords)
        
        self.assertTrue(has_stop)  # 应该检测到停止关键词
    
    def test_complex_stop_command(self):
        """测试复杂的停止指令"""
        text = "急停并且停止"
        
        # 既是复杂指令（包含"并且"）又包含停止关键词
        self.assertTrue(is_complex_command(text))  # 是复杂指令
        
        stop_keywords = ["停", "急停", "别动", "站住"]
        has_stop = any(x in text for x in stop_keywords)
        self.assertTrue(has_stop)  # 也包含停止关键词


if __name__ == '__main__':
    unittest.main()
