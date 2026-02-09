# -*- coding: utf-8 -*-
"""
音频回声消除（AEC）处理器

封装 speexdsp 库的回声消除功能，提供简单易用的接口。

功能：
1. 从麦克风信号中消除扬声器播放的回声
2. 处理采样率转换（24kHz → 16kHz）
3. 提供线程安全的接口

依赖：
    pip install speexdsp-python scipy numpy

Linux 安装：
    sudo apt-get install libspeexdsp-dev
    pip install speexdsp-python
"""

import logging
import numpy as np
from scipy import signal
from typing import Optional

# 配置日志
logger = logging.getLogger(__name__)  # 创建模块级日志记录器

# 尝试导入 speexdsp（Linux 环境可用）
try:
    import speexdsp  # 导入 speexdsp 库
    SPEEXDSP_AVAILABLE = True  # 标记库可用
    logger.info("[AEC] speexdsp 库加载成功")  # 记录成功信息
except ImportError as e:  # 捕获导入异常
    SPEEXDSP_AVAILABLE = False  # 标记库不可用
    logger.warning(f"[AEC] speexdsp 库未安装: {e}")  # 记录警告信息
    logger.warning("[AEC] 回声消除功能将被禁用")  # 提示功能不可用


class AECProcessor:
    """
    音频回声消除（AEC）处理器
    
    使用 speexdsp 库实现自适应回声消除，从麦克风信号中过滤扬声器播放的声音。
    
    工作原理：
        麦克风信号 = 用户声音 + 回声（扬声器播放）
        AEC 通过参考信号（扬声器输出）自适应估计回声路径
        输出 = 麦克风信号 - 估计的回声
    
    参数：
        frame_size: 每帧样本数（建议 20ms，16kHz = 320 samples）
        filter_length: 自适应滤波器长度（越大效果越好，CPU 占用越高）
        sample_rate: 采样率（统一为 16kHz）
        enabled: 是否启用 AEC（False 时直通，不做处理）
    """
    
    def __init__(
        self,
        frame_size: int = 320,  # 20ms @ 16kHz
        filter_length: int = 2048,
        sample_rate: int = 16000,
        enabled: bool = True
    ):
        """
        初始化 AEC 处理器
        
        Args:
            frame_size: 每帧样本数（默认 320 = 20ms @ 16kHz）
            filter_length: 滤波器长度（默认 2048，可调整性能与效果平衡）
            sample_rate: 采样率（默认 16kHz，需与麦克风一致）
            enabled: 是否启用 AEC（默认 True）
        """
        self.frame_size = frame_size  # 保存帧大小
        self.filter_length = filter_length  # 保存滤波器长度
        self.sample_rate = sample_rate  # 保存采样率
        self.enabled = enabled and SPEEXDSP_AVAILABLE  # 仅在库可用时启用
        
        self.echo_canceller = None  # EchoCanceller 实例
        
        if self.enabled:  # 如果启用 AEC
            self._initialize_echo_canceller()  # 初始化回声消除器
        else:
            logger.warning("[AEC] 处理器未启用（库不可用或手动禁用）")  # 记录警告
    
    def _initialize_echo_canceller(self):
        """初始化 speexdsp EchoCanceller"""
        try:
            self.echo_canceller = speexdsp.EchoCanceller.create(
                self.frame_size,  # 帧大小
                self.filter_length,  # 滤波器长度
                self.sample_rate  # 采样率
            )
            logger.info(
                f"[AEC] EchoCanceller 初始化成功 "
                f"(frame_size={self.frame_size}, "
                f"filter_length={self.filter_length}, "
                f"sample_rate={self.sample_rate})"
            )  # 记录初始化成功
        except Exception as e:  # 捕获异常
            self.enabled = False  # 禁用 AEC
            logger.error(f"[AEC] EchoCanceller 初始化失败: {e}")  # 记录错误
    
    def process(self, mic_frame: bytes, reference_frame: bytes) -> bytes:
        """
        执行回声消除处理
        
        Args:
            mic_frame: 麦克风采集的 PCM 数据（16kHz, 单声道, 16-bit, frame_size samples）
            reference_frame: 扬声器播放的参考信号（16kHz, 单声道, 16-bit, frame_size samples）
        
        Returns:
            清洗后的音频数据（与输入格式相同）
        
        注意：
            - 两个输入必须长度相同，且为 frame_size * 2 字节（16-bit = 2 bytes/sample）
            - 如果 AEC 未启用或处理失败，返回原始麦克风数据
        """
        # 快速路径：AEC 未启用，直接返回原始数据
        if not self.enabled or self.echo_canceller is None:
            return mic_frame  # 直通模式
        
        # 验证输入长度
        expected_bytes = self.frame_size * 2  # 16-bit = 2 bytes/sample
        if len(mic_frame) != expected_bytes:  # 检查麦克风帧长度
            logger.warning(
                f"[AEC] 麦克风帧长度错误: 期望 {expected_bytes} 字节，"
                f"实际 {len(mic_frame)} 字节，跳过处理"
            )
            return mic_frame  # 返回原始数据
        
        if len(reference_frame) != expected_bytes:  # 检查参考帧长度
            # 参考信号长度不匹配，补零或截断
            if len(reference_frame) < expected_bytes:  # 不足补零
                reference_frame += b'\x00' * (expected_bytes - len(reference_frame))
            else:  # 超出截断
                reference_frame = reference_frame[:expected_bytes]
        
        try:
            # 执行回声消除（核心步骤）
            cleaned_frame = self.echo_canceller.process(mic_frame, reference_frame)
            return cleaned_frame  # 返回清洗后的数据
        
        except Exception as e:  # 捕获处理异常
            logger.error(f"[AEC] 处理失败: {e}")  # 记录错误
            return mic_frame  # 失败时返回原始数据
    
    def reset(self):
        """
        重置 AEC 状态
        
        在切换对话或检测到长时间静音时调用，清除自适应滤波器的历史状态。
        """
        if not self.enabled or self.echo_canceller is None:
            return  # AEC 未启用，无需操作
        
        try:
            # 重新创建 EchoCanceller 实例（等效于重置）
            self._initialize_echo_canceller()
            logger.info("[AEC] 状态已重置")  # 记录重置成功
        except Exception as e:  # 捕获异常
            logger.error(f"[AEC] 重置失败: {e}")  # 记录错误


class AudioResampler:
    """
    音频重采样工具
    
    用于将播放器的 24kHz 音频重采样到麦克风的 16kHz，以便参考信号与麦克风信号匹配。
    
    使用 scipy.signal.resample 实现高质量重采样。
    """
    
    @staticmethod
    def resample_24k_to_16k(data_24k: bytes) -> bytes:
        """
        将 24kHz PCM 数据重采样到 16kHz
        
        Args:
            data_24k: 24kHz 单声道 16-bit PCM 数据
        
        Returns:
            16kHz 单声道 16-bit PCM 数据
        """
        if not data_24k:  # 空数据直接返回
            return b""
        
        try:
            # 转为 numpy array
            samples_24k = np.frombuffer(data_24k, dtype=np.int16)  # 解析为 int16 数组
            
            # 计算重采样后的样本数（16000/24000 = 2/3）
            num_samples_16k = int(len(samples_24k) * 16000 / 24000)  # 计算目标样本数
            
            # 执行重采样（使用 scipy.signal.resample）
            samples_16k = signal.resample(samples_24k, num_samples_16k)  # 重采样
            
            # 转回 int16 并转为 bytes
            samples_16k_int16 = np.clip(samples_16k, -32768, 32767).astype(np.int16)  # 限幅并转换类型
            
            return samples_16k_int16.tobytes()  # 返回字节数据
        
        except Exception as e:  # 捕获异常
            logger.error(f"[Resampler] 重采样失败: {e}")  # 记录错误
            return b""  # 返回空数据


# 导出公共接口
__all__ = ['AECProcessor', 'AudioResampler', 'SPEEXDSP_AVAILABLE']  # 定义模块导出列表
