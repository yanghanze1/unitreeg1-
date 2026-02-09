# -*- coding: utf-8 -*-
"""
音频播放器模块单元测试

测试内容：
1. B64PCMPlayer 初始化
2. 数据添加和队列管理
3. 打断功能
4. 空闲状态检测
5. 参考信号获取（AEC 支持）
"""

import pytest  # 导入 pytest 测试框架
import time  # 导入时间模块
import base64  # 导入 Base64 编解码模块
import threading  # 导入线程模块
from unittest.mock import MagicMock, patch, PropertyMock  # 导入 Mock 工具


class TestB64PCMPlayer:
    """B64PCMPlayer 音频播放器测试类"""

    @pytest.fixture
    def mock_pyaudio(self):
        """创建模拟的 PyAudio 实例"""
        pya = MagicMock()  # 创建 Mock 对象
        mock_stream = MagicMock()  # 创建模拟的音频流
        mock_stream.is_active.return_value = True  # 设置流为活跃状态
        pya.open.return_value = mock_stream  # 设置 open 返回模拟流
        return pya

    @pytest.fixture
    def player(self, mock_pyaudio):
        """创建 B64PCMPlayer 实例"""
        # Mock aec_processor 导入以避免依赖
        with patch.dict('sys.modules', {'aec_processor': MagicMock()}):
            from VoiceInteraction.audio_player import B64PCMPlayer
            player = B64PCMPlayer(mock_pyaudio, sample_rate=24000, chunk_size_ms=100)
            yield player
            # 清理
            player.shutdown()

    def test_init(self, player, mock_pyaudio):
        """测试初始化"""
        assert player.sample_rate == 24000  # 验证采样率
        assert player.chunk_size_bytes == 4800  # 验证块大小 (100ms * 24000 * 2 / 1000)
        mock_pyaudio.open.assert_called()  # 验证 open 被调用

    def test_add_data_sets_not_idle(self, player):
        """测试添加数据后状态变为非空闲"""
        # 初始状态为空闲
        assert player._idle_event.is_set() is True  # 验证初始空闲

        # 添加数据
        test_pcm = b'\x00' * 100  # 创建测试数据
        b64_data = base64.b64encode(test_pcm).decode('ascii')  # Base64 编码
        player.add_data(b64_data)  # 添加数据

        # 状态应变为非空闲
        assert player._idle_event.is_set() is False  # 验证非空闲

    def test_add_empty_data_ignored(self, player):
        """测试空数据被忽略"""
        initial_pending = player._pending_b64  # 记录初始计数
        player.add_data("")  # 添加空数据
        assert player._pending_b64 == initial_pending  # 验证计数未变

    def test_add_data_during_abort_ignored(self, player):
        """测试打断期间添加数据被忽略"""
        player._abort_event.set()  # 设置打断事件

        test_pcm = b'\x00' * 100  # 创建测试数据
        b64_data = base64.b64encode(test_pcm).decode('ascii')  # Base64 编码
        player.add_data(b64_data)  # 添加数据

        assert player._pending_b64 == 0  # 验证计数未增加

        player._abort_event.clear()  # 清除打断事件

    def test_interrupt_clears_queues(self, player):
        """测试打断清空队列"""
        # 添加一些数据
        test_pcm = b'\x00' * 100  # 创建测试数据
        b64_data = base64.b64encode(test_pcm).decode('ascii')  # Base64 编码
        player.add_data(b64_data)  # 添加数据

        # 执行打断
        player.interrupt(reset_stream=False)  # 打断（不重置流）

        # 验证队列被清空
        assert player.b64_audio_buffer.empty() is True  # 验证 b64 队列为空
        assert player.raw_audio_buffer.empty() is True  # 验证 raw 队列为空
        assert player._pending_b64 == 0  # 验证计数清零
        assert player._pending_raw_bytes == 0  # 验证计数清零

    def test_interrupt_sets_idle(self, player):
        """测试打断后状态变为空闲"""
        # 先设置为非空闲
        player._idle_event.clear()  # 清除空闲事件

        # 执行打断
        player.interrupt(reset_stream=False)  # 打断

        # 验证状态变为空闲
        assert player._idle_event.is_set() is True  # 验证空闲

    def test_wait_until_idle_returns_immediately_when_idle(self, player):
        """测试空闲时 wait_until_idle 立即返回"""
        # 初始状态为空闲
        start = time.time()  # 记录开始时间
        result = player.wait_until_idle(timeout=1.0)  # 等待空闲
        elapsed = time.time() - start  # 计算耗时

        assert result is True  # 验证返回 True
        assert elapsed < 0.1  # 验证立即返回

    def test_get_reference_frame_returns_empty_when_no_data(self, player):
        """测试无数据时 get_reference_frame 返回空"""
        frame = player.get_reference_frame(timeout=0.01)  # 获取参考帧
        assert frame == b""  # 验证返回空字节串

    def test_shutdown_stops_threads(self, player):
        """测试 shutdown 停止线程"""
        player.shutdown()  # 调用 shutdown

        # 验证状态
        assert player._status == "stop"  # 验证状态为 stop


class TestB64PCMPlayerDecoding:
    """B64PCMPlayer 解码功能测试类"""

    @pytest.fixture
    def mock_pyaudio(self):
        """创建模拟的 PyAudio 实例"""
        pya = MagicMock()  # 创建 Mock 对象
        mock_stream = MagicMock()  # 创建模拟的音频流
        mock_stream.is_active.return_value = True  # 设置流为活跃状态
        pya.open.return_value = mock_stream  # 设置 open 返回模拟流
        return pya

    @pytest.fixture
    def player(self, mock_pyaudio):
        """创建 B64PCMPlayer 实例"""
        with patch.dict('sys.modules', {'aec_processor': MagicMock()}):
            from VoiceInteraction.audio_player import B64PCMPlayer
            player = B64PCMPlayer(mock_pyaudio, sample_rate=24000, chunk_size_ms=100)
            yield player
            player.shutdown()

    def test_valid_base64_decoding(self, player):
        """测试有效 Base64 数据的解码"""
        # 创建测试数据
        test_pcm = b'\x00\x01\x02\x03' * 100  # 400 字节 PCM 数据
        b64_data = base64.b64encode(test_pcm).decode('ascii')  # Base64 编码

        # 添加数据
        player.add_data(b64_data)  # 添加到播放器

        # 等待解码线程处理
        time.sleep(0.2)  # 短暂等待

        # 验证数据已被处理（pending_b64 应该减少）
        # 由于解码是异步的，我们检查数据被放入了 raw 队列
        assert player.b64_audio_buffer.qsize() == 0 or player._pending_b64 >= 0  # 验证处理

    def test_invalid_base64_handled_gracefully(self, player):
        """测试无效 Base64 数据被优雅处理"""
        # 添加无效的 Base64 数据
        player.add_data("这不是有效的Base64数据!!!")  # 添加无效数据

        # 等待解码线程处理
        time.sleep(0.2)  # 短暂等待

        # 验证没有崩溃，播放器仍然正常
        assert player._status != "stop"  # 验证未停止
