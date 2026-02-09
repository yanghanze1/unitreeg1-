# -*- coding: utf-8 -*-
"""
Omni 回调处理模块单元测试

测试内容：
1. 响应模式控制逻辑
2. 丢弃输出标志管理
3. 序号管理
4. _ensure_dict 工具函数
"""

import pytest  # 导入 pytest 测试框架
import json  # 导入 JSON 模块
import threading  # 导入线程模块
from unittest.mock import MagicMock, patch  # 导入 Mock 工具


# 创建一个简化版的 OmniCallback 用于测试核心逻辑
class MockOmniCallback:
    """模拟 OmniCallback 的核心逻辑用于测试"""
    
    def __init__(self, flag_getter, flag_setter):
        """初始化"""
        self._get_flag = flag_getter
        self._set_flag = flag_setter
        
        self._respond_lock = threading.Lock()
        self._responding = False
        
        self._seq_lock = threading.Lock()
        self._resp_seq = 0
        
        self._drop_lock = threading.Lock()
        self._drop_output = False
        
        self._cool_lock = threading.Lock()
        self._last_speak_end_time = 0.0

    def _inc_seq(self) -> int:
        """增加响应序号"""
        with self._seq_lock:
            self._resp_seq += 1
            return self._resp_seq

    def _get_seq(self) -> int:
        """获取当前序号"""
        with self._seq_lock:
            return self._resp_seq

    def _set_drop_output(self, v: bool):
        """设置丢弃输出"""
        with self._drop_lock:
            self._drop_output = bool(v)

    def _should_drop_output(self) -> bool:
        """检查是否丢弃输出"""
        with self._drop_lock:
            return bool(self._drop_output)

    def is_responding(self) -> bool:
        """检查是否在响应模式"""
        with self._respond_lock:
            return bool(self._responding)

    def _enter_response_mode(self):
        """进入响应模式"""
        with self._respond_lock:
            if self._responding:
                return
            self._responding = True
        self._set_flag(1, reason="test")
        self._inc_seq()

    def _exit_response_mode_if_seq(self, seq: int, reason: str):
        """按序号退出响应模式"""
        if seq != self._get_seq():
            return
        with self._respond_lock:
            self._responding = False
        self._set_flag(0, reason=reason)

    def _force_exit_response_mode(self, reason: str):
        """强制退出响应模式"""
        with self._respond_lock:
            self._responding = False
        self._inc_seq()
        self._set_flag(0, reason=reason)

    def _ensure_dict(self, message):
        """确保消息为字典"""
        if isinstance(message, dict):
            return message
        if isinstance(message, str):
            try:
                return json.loads(message)
            except Exception:
                pass
        return {}


class TestOmniCallbackResponseMode:
    """响应模式控制测试类"""

    @pytest.fixture
    def callback(self):
        """创建 MockOmniCallback 实例"""
        return MockOmniCallback(
            flag_getter=MagicMock(return_value=0),
            flag_setter=MagicMock()
        )

    def test_is_responding_initial(self, callback):
        """测试初始响应状态"""
        assert callback.is_responding() is False  # 验证初始不在响应模式

    def test_enter_response_mode(self, callback):
        """测试进入响应模式"""
        callback._enter_response_mode()
        assert callback.is_responding() is True
        callback._set_flag.assert_called()

    def test_enter_response_mode_twice_no_double_increment(self, callback):
        """测试重复进入响应模式不会重复增加序号"""
        callback._enter_response_mode()
        seq1 = callback._get_seq()
        
        callback._enter_response_mode()  # 再次调用
        seq2 = callback._get_seq()
        
        assert seq1 == seq2  # 序号不应改变

    def test_exit_response_mode_if_seq_matches(self, callback):
        """测试序号匹配时退出响应模式"""
        callback._enter_response_mode()
        seq = callback._get_seq()
        
        callback._exit_response_mode_if_seq(seq, reason="test")
        
        assert callback.is_responding() is False

    def test_exit_response_mode_if_seq_not_matches(self, callback):
        """测试序号不匹配时保持响应模式"""
        callback._enter_response_mode()
        wrong_seq = callback._get_seq() - 1
        
        callback._exit_response_mode_if_seq(wrong_seq, reason="test")
        
        assert callback.is_responding() is True

    def test_force_exit_response_mode(self, callback):
        """测试强制退出响应模式"""
        callback._enter_response_mode()
        old_seq = callback._get_seq()
        
        callback._force_exit_response_mode(reason="force")
        
        assert callback.is_responding() is False
        assert callback._get_seq() > old_seq


class TestOmniCallbackDropOutput:
    """丢弃输出标志测试类"""

    @pytest.fixture
    def callback(self):
        """创建 MockOmniCallback 实例"""
        return MockOmniCallback(
            flag_getter=MagicMock(return_value=0),
            flag_setter=MagicMock()
        )

    def test_initial_drop_output_false(self, callback):
        """测试初始丢弃输出为 False"""
        assert callback._should_drop_output() is False

    def test_set_drop_output_true(self, callback):
        """测试设置丢弃输出为 True"""
        callback._set_drop_output(True)
        assert callback._should_drop_output() is True

    def test_set_drop_output_false(self, callback):
        """测试设置丢弃输出为 False"""
        callback._set_drop_output(True)
        callback._set_drop_output(False)
        assert callback._should_drop_output() is False


class TestOmniCallbackSequence:
    """序号管理测试类"""

    @pytest.fixture
    def callback(self):
        """创建 MockOmniCallback 实例"""
        return MockOmniCallback(
            flag_getter=MagicMock(return_value=0),
            flag_setter=MagicMock()
        )

    def test_initial_seq_is_zero(self, callback):
        """测试初始序号为 0"""
        assert callback._get_seq() == 0

    def test_inc_seq_increments(self, callback):
        """测试 _inc_seq 增加序号"""
        initial = callback._get_seq()
        new_seq = callback._inc_seq()
        
        assert new_seq == initial + 1
        assert callback._get_seq() == new_seq

    def test_multiple_inc_seq(self, callback):
        """测试多次增加序号"""
        callback._inc_seq()
        callback._inc_seq()
        callback._inc_seq()
        
        assert callback._get_seq() == 3


class TestOmniCallbackEnsureDict:
    """_ensure_dict 工具函数测试类"""

    @pytest.fixture
    def callback(self):
        """创建 MockOmniCallback 实例"""
        return MockOmniCallback(
            flag_getter=MagicMock(return_value=0),
            flag_setter=MagicMock()
        )

    def test_ensure_dict_with_dict(self, callback):
        """测试传入字典"""
        result = callback._ensure_dict({"type": "test", "data": 123})
        assert result == {"type": "test", "data": 123}

    def test_ensure_dict_with_json_string(self, callback):
        """测试传入 JSON 字符串"""
        result = callback._ensure_dict('{"type": "session.created"}')
        assert result == {"type": "session.created"}

    def test_ensure_dict_with_invalid_json(self, callback):
        """测试传入无效 JSON 字符串"""
        result = callback._ensure_dict("not valid json")
        assert result == {}

    def test_ensure_dict_with_none(self, callback):
        """测试传入 None"""
        result = callback._ensure_dict(None)
        assert result == {}

    def test_ensure_dict_with_number(self, callback):
        """测试传入数字"""
        result = callback._ensure_dict(42)
        assert result == {}

    def test_ensure_dict_with_empty_dict(self, callback):
        """测试传入空字典"""
        result = callback._ensure_dict({})
        assert result == {}
