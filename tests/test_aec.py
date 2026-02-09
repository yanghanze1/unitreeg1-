# -*- coding: utf-8 -*-
"""
AEC 处理器单元测试

测试音频回声消除（AEC）功能是否正常工作。

运行测试：
    pytest tests/test_aec.py -v
"""

import sys
import os
import pytest
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))  # 添加VoiceInteraction目录

def test_aec_processor_import():
    """测试 AEC 处理器能否正常导入"""
    try:
        from aec_processor import AECProcessor, AudioResampler, SPEEXDSP_AVAILABLE  # 导入AEC模块
        assert True  # 导入成功
    except ImportError as e:  # 导入失败
        pytest.skip(f"AEC 模块不可用: {e}")  # 跳过测试


def test_aec_processor_initialization():
    """测试 AEC 处理器能否正常初始化"""
    try:
        from aec_processor import AECProcessor, SPEEXDSP_AVAILABLE  # 导入AEC模块
        
        if not SPEEXDSP_AVAILABLE:  # 库不可用
            pytest.skip("speexdsp 库不可用，跳过测试")  # 跳过测试
        
        # 创建 AEC 处理器
        aec = AECProcessor(
            frame_size=320,  # 20ms @ 16kHz
            filter_length=2048,  # 滤波器长度
            sample_rate=16000,  # 采样率
            enabled=True  # 启用
        )
        
        assert aec.enabled is True  # 验证已启用
        assert aec.frame_size == 320  # 验证帧大小
        assert aec.sample_rate == 16000  # 验证采样率
        
    except Exception as e:  # 捕获异常
        pytest.fail(f"AEC 初始化失败: {e}")  # 测试失败


def test_aec_processor_process_passthrough():
    """测试 AEC 处理器在禁用时的直通模式"""
    try:
        from aec_processor import AECProcessor  # 导入AEC模块
        
        # 创建禁用的 AEC 处理器
        aec = AECProcessor(enabled=False)  # 禁用AEC
        
        # 生成测试数据（320 samples * 2 bytes = 640 bytes）
        frame_size_bytes = 320 * 2  # 640字节
        test_data = b'\x00\x01' * 320  # 模拟音频数据
        
        # 处理数据
        result = aec.process(test_data, b"")  # 处理
        
        # 验证直通模式：输出应与输入完全相同
        assert result == test_data  # 验证数据未改变
        
    except ImportError:  # 导入失败
        pytest.skip("AEC 模块不可用")  # 跳过测试


def test_audio_resampler_24k_to_16k():
    """测试音频重采样功能（24kHz → 16kHz）"""
    try:
        from aec_processor import AudioResampler  # 导入重采样器
        
        # 生成 24kHz 测试数据（1秒）
        sample_rate_24k = 24000  # 24kHz
        duration_sec = 1.0  # 1秒
        num_samples_24k = int(sample_rate_24k * duration_sec)  # 24000样本
        
        # 生成正弦波
        t = np.linspace(0, duration_sec, num_samples_24k, endpoint=False)  # 时间序列
        signal_24k = np.sin(2 * np.pi * 440 * t)  # 440Hz正弦波
        signal_24k_int16 = (signal_24k * 32767 * 0.8).astype(np.int16)  # 转int16
        data_24k = signal_24k_int16.tobytes()  # 转字节
        
        # 执行重采样
        data_16k = AudioResampler.resample_24k_to_16k(data_24k)  # 重采样到16kHz
        
        # 验证输出长度约为输入的 2/3
        expected_bytes = int(len(data_24k) * 16000 / 24000)  # 期望字节数
        actual_bytes = len(data_16k)  # 实际字节数
        
        # 允许 1% 误差
        assert abs(actual_bytes - expected_bytes) / expected_bytes < 0.01  # 验证长度
        
    except ImportError:  # 导入失败
        pytest.skip("AEC 模块不可用")  # 跳过测试
    except Exception as e:  # 其他异常
        pytest.fail(f"重采样测试失败: {e}")  # 测试失败


def test_aec_processor_reset():
    """测试 AEC 处理器重置功能"""
    try:
        from aec_processor import AECProcessor, SPEEXDSP_AVAILABLE  # 导入AEC模块
        
        if not SPEEXDSP_AVAILABLE:  # 库不可用
            pytest.skip("speexdsp 库不可用，跳过测试")  # 跳过测试
        
        # 创建 AEC 处理器
        aec = AECProcessor(enabled=True)  # 启用AEC
        
        # 重置状态
        aec.reset()  # 重置
        
        # 验证重置后仍可用
        assert aec.enabled is True  # 验证仍启用
        assert aec.echo_canceller is not None  # 验证实例存在
        
    except ImportError:  # 导入失败
        pytest.skip("AEC 模块不可用")  # 跳过测试
    except Exception as e:  # 其他异常
        pytest.fail(f"重置测试失败: {e}")  # 测试失败


if __name__ == "__main__":
    # 运行所有测试
    pytest.main([__file__, "-v"])  # 执行pytest
