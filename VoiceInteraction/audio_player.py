# -*- coding: utf-8 -*-
"""
音频播放器模块：Base64 PCM 流式解码与播放

功能：
1. 接收 Base64 编码的 PCM 音频数据
2. 解码后分片写入声卡
3. 支持播放打断和状态查询
4. 提供 AEC 参考信号接口

创建时间: 2026-01-29
"""

import threading  # 导入线程模块
import queue  # 导入队列模块
import base64  # 导入Base64编解码模块
import contextlib  # 导入上下文管理模块
import time  # 导入时间模块
import logging  # 导入日志模块
import pyaudio  # 导入音频处理模块

# 配置日志记录器
logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


class B64PCMPlayer:
    """
    流式播放：不断接收 b64 PCM -> 解码 -> 分片 -> write 到声卡。
    - wait_until_idle(): 判断"本地播放是否真正结束"
    - interrupt(): 立刻清空队列并重置输出流（尽可能立即停）
    """
    
    def __init__(self, pya: pyaudio.PyAudio, sample_rate=24000, chunk_size_ms=100):
        """
        初始化音频播放器
        
        Args:
            pya: PyAudio 实例
            sample_rate: 采样率（默认 24kHz）
            chunk_size_ms: 每个播放块的毫秒数（默认 100ms）
        """
        self.pya = pya  # 保存 PyAudio 实例
        self.sample_rate = sample_rate  # 原始采样率
        self.chunk_size_bytes = int(chunk_size_ms * sample_rate * 2 // 1000)  # 计算每块字节数

        self._stream_lock = threading.Lock()  # 音频流操作锁
        
        # 检测设备支持的采样率
        self._device_sample_rate = self._detect_device_sample_rate()
        logger.info(f"[Player] 原始采样率: {self.sample_rate}Hz, 设备采样率: {self._device_sample_rate}Hz")
        
        self.player_stream = self._open_stream()  # 创建输出流

        self.raw_audio_buffer: "queue.Queue[bytes]" = queue.Queue()  # 原始音频缓冲区
        self.b64_audio_buffer: "queue.Queue[str]" = queue.Queue()  # Base64 音频缓冲区

        self._status_lock = threading.Lock()  # 状态锁
        self._status = "playing"  # 播放状态

        self._cnt_lock = threading.Lock()  # 计数器锁
        self._pending_b64 = 0  # 待处理的 Base64 块计数
        self._pending_raw_bytes = 0  # 待播放的原始字节计数

        self._idle_event = threading.Event()  # 空闲事件
        self._idle_event.set()  # 初始为空闲状态

        self._abort_event = threading.Event()  # 打断事件：置位时丢弃所有待播数据

        # === AEC 支持：参考信号缓冲区 ===
        self.reference_buffer: "queue.Queue[bytes]" = queue.Queue(maxsize=100)  # 保存播放的参考信号（16kHz）
        self.resampler = None  # 重采样器实例
        self._playback_resampler = None  # 播放重采样器
        try:
            from aec_processor import AudioResampler  # 导入重采样工具
            self.resampler = AudioResampler()  # 用于 24kHz → 16kHz 重采样
            # 初始化播放重采样器（如果需要）
            if self._device_sample_rate != self.sample_rate:
                from aec_processor import AudioResampler
                self._playback_resampler = AudioResampler()  # 使用通用的重采样方法
                logger.info(f"[Player] 启用播放重采样: {self.sample_rate}Hz → {self._device_sample_rate}Hz")
        except ImportError:
            logger.warning("[Player] AEC 模块未找到，参考信号功能禁用")  # 打印警告

        # 启动解码和播放线程
        self._decoder_thread = threading.Thread(target=self._decoder_loop, daemon=True)  # 解码线程
        self._player_thread = threading.Thread(target=self._player_loop, daemon=True)  # 播放线程
        self._decoder_thread.start()  # 启动解码线程
        self._player_thread.start()  # 启动播放线程

    def _detect_device_sample_rate(self):
        """检测默认输出设备支持的采样率"""
        try:
            default_output = self.pya.get_default_output_device_info()
            device_rate = default_output['defaultSampleRate']
            device_rate = int(float(device_rate))
            logger.info(f"[Player] 默认输出设备: {default_output['name']}, 支持采样率: {device_rate}Hz")
            return device_rate
        except Exception as e:
            logger.warning(f"[Player] 无法检测设备采样率，使用默认 24000Hz: {e}")
            return self.sample_rate

    def _open_stream(self):
        """创建并返回 PyAudio 输出流（使用设备支持的采样率）"""
        try:
            return self.pya.open(
                format=pyaudio.paInt16,  # 16位 PCM 格式
                channels=1,  # 单声道
                rate=self._device_sample_rate,  # 使用设备支持的采样率
                output=True  # 输出流
            )
        except OSError as e:
            logger.error(f"[Player] 无法使用 {self._device_sample_rate}Hz 打开音频流: {e}")
            logger.info("[Player] 尝试使用 44100Hz 作为备选采样率")
            self._device_sample_rate = 44100
            return self.pya.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44100,
                output=True
            )

    def _set_not_idle(self):
        """设置为非空闲状态"""
        self._idle_event.clear()  # 清除空闲事件

    def _try_set_idle(self):
        """尝试设置为空闲状态（当所有待播数据处理完毕时）"""
        with self._cnt_lock:  # 获取计数器锁
            ok = (self._pending_b64 == 0 and self._pending_raw_bytes == 0)  # 检查是否无待处理数据
        if ok:  # 如果无待处理数据
            self._idle_event.set()  # 设置空闲事件

    def add_data(self, b64_pcm: str):
        """
        添加 Base64 编码的 PCM 数据到播放队列
        
        Args:
            b64_pcm: Base64 编码的 PCM 音频数据
        """
        if not b64_pcm:  # 检查数据是否为空
            return  # 空数据直接返回
        if self._abort_event.is_set():  # 检查是否正在被打断
            return  # 正在被打断：直接丢弃新到的音频
        self._set_not_idle()  # 设置为非空闲状态
        with self._cnt_lock:  # 获取计数器锁
            self._pending_b64 += 1  # 增加待处理计数
        self.b64_audio_buffer.put(b64_pcm)  # 放入缓冲区

    def _clear_queue(self, q: queue.Queue):
        """清空队列中的所有数据"""
        while True:  # 循环清空
            with contextlib.suppress(queue.Empty):  # 忽略队列空异常
                q.get_nowait()  # 非阻塞取出
                continue  # 继续清空
            break  # 队列已空，退出循环

    def interrupt(self, reset_stream: bool = True):
        """
        立即停止当前播放：
        - 置位 abort_event，让 decoder/player 立刻进入丢弃模式
        - 清空 b64/raw 队列 + pending 计数清零
        - 强制 stop_stream + close + reopen，尽最大可能清掉声卡缓冲
        
        Args:
            reset_stream: 是否重置音频流（默认 True）
        """
        self._abort_event.set()  # 置位打断事件
        self._set_not_idle()  # 设置为非空闲

        # 清空内部队列
        self._clear_queue(self.b64_audio_buffer)  # 清空 Base64 队列
        self._clear_queue(self.raw_audio_buffer)  # 清空原始音频队列

        with self._cnt_lock:  # 获取计数器锁
            self._pending_b64 = 0  # 清零 Base64 计数
            self._pending_raw_bytes = 0  # 清零原始字节计数

        if reset_stream:  # 如果需要重置流
            with self._stream_lock:  # 获取流操作锁
                with contextlib.suppress(Exception):  # 忽略异常
                    if self.player_stream.is_active():  # 检查流是否活跃
                        self.player_stream.stop_stream()  # 停止流
                with contextlib.suppress(Exception):  # 忽略异常
                    self.player_stream.close()  # 关闭流
                with contextlib.suppress(Exception):  # 忽略异常
                    self.player_stream = self._open_stream()  # 重新打开流

        # 立即标记 idle
        self._idle_event.set()  # 设置空闲事件

        # 解除 abort（允许后续新的 response 正常播放）
        self._abort_event.clear()  # 清除打断事件

    def _decoder_loop(self):
        """解码线程：将 Base64 编码的 PCM 解码为原始音频数据"""
        while True:  # 主循环
            with self._status_lock:  # 获取状态锁
                if self._status == "stop":  # 检查是否需要停止
                    break  # 退出循环

            if self._abort_event.is_set():  # 检查是否被打断
                time.sleep(0.01)  # 短暂休眠
                continue  # 跳过本次循环

            recv_b64 = None  # 初始化接收变量
            with contextlib.suppress(queue.Empty):  # 忽略队列空异常
                recv_b64 = self.b64_audio_buffer.get(timeout=0.1)  # 从队列取数据

            if not recv_b64:  # 如果没有数据
                self._try_set_idle()  # 尝试设置空闲
                continue  # 继续下一次循环

            with self._cnt_lock:  # 获取计数器锁
                if self._pending_b64 > 0:  # 如果有待处理计数
                    self._pending_b64 -= 1  # 减少计数

            try:
                raw = base64.b64decode(recv_b64)  # 解码 Base64
            except Exception:  # 捕获解码异常
                self._try_set_idle()  # 尝试设置空闲
                continue  # 继续下一次循环

            if self._abort_event.is_set():  # 解码后再次检查打断
                self._try_set_idle()  # 尝试设置空闲
                continue  # 跳过本次循环

            # 将解码后的数据分片放入原始音频队列
            for i in range(0, len(raw), self.chunk_size_bytes):  # 按块大小遍历
                chunk = raw[i:i + self.chunk_size_bytes]  # 提取数据块
                if not chunk:  # 如果块为空
                    continue  # 跳过
                with self._cnt_lock:  # 获取计数器锁
                    self._pending_raw_bytes += len(chunk)  # 增加原始字节计数
                self.raw_audio_buffer.put(chunk)  # 放入原始音频队列

            self._try_set_idle()  # 尝试设置空闲

    def _player_loop(self):
        """播放线程：将原始音频数据写入声卡"""
        # 细分为更短的写入粒度（40ms），让"打断"更灵敏
        sub_bytes = int(40 * self.sample_rate * 2 // 1000)  # 40ms 音频数据长度

        while True:  # 主循环
            with self._status_lock:  # 获取状态锁
                if self._status == "stop":  # 检查是否需要停止
                    break  # 退出循环

            if self._abort_event.is_set():  # 检查是否被打断
                time.sleep(0.005)  # 短暂休眠
                continue  # 跳过本次循环

            chunk = None  # 初始化数据块
            with contextlib.suppress(queue.Empty):  # 忽略队列空异常
                chunk = self.raw_audio_buffer.get(timeout=0.1)  # 从队列取数据

            if not chunk:  # 如果没有数据
                self._try_set_idle()  # 尝试设置空闲
                continue  # 继续下一次循环

            # 写入前检查打断
            if self._abort_event.is_set():  # 检查是否被打断
                with self._cnt_lock:  # 修复：Lock 对象不是 callable，不需要括号
                    self._pending_raw_bytes = max(0, self._pending_raw_bytes - len(chunk))  # 减少计数
                self._try_set_idle()  # 尝试设置空闲
                continue  # 跳过本次循环

            # === AEC 支持：播放前保存参考信号 ===
            if self.resampler is not None:  # 检查重采样器是否可用
                try:
                    # 将 24kHz 数据重采样到 16kHz，用作 AEC 参考信号
                    ref_16k = self.resampler.resample_24k_to_16k(chunk)  # 执行重采样
                    if ref_16k and not self.reference_buffer.full():  # 检查缓冲区未满
                        self.reference_buffer.put_nowait(ref_16k)  # 非阻塞放入缓冲区
                except Exception:  # 捕获异常
                    pass  # 重采样失败不影响播放

            # === 重采样到设备支持的采样率 ===
            chunk_to_play = chunk  # 默认使用原始数据
            if self._device_sample_rate != self.sample_rate and self._playback_resampler is not None:
                try:
                    chunk_to_play = self._playback_resampler.resample(chunk, self.sample_rate, self._device_sample_rate)
                except Exception:  # 如果重采样失败，使用原始数据
                    chunk_to_play = chunk

            try:
                # 把一次 chunk 再拆成更小片，避免 write 阻塞太久
                sub_bytes = int(40 * self._device_sample_rate * 2 // 1000)  # 40ms 音频数据长度（使用设备采样率）
                for i in range(0, len(chunk_to_play), sub_bytes):  # 按子块大小遍历
                    if self._abort_event.is_set():  # 检查是否被打断
                        break  # 退出循环
                    sub = chunk_to_play[i:i + sub_bytes]  # 提取子块
                    if not sub:  # 如果子块为空
                        continue  # 跳过
                    with self._stream_lock:  # 获取流操作锁
                        self.player_stream.write(sub)  # 写入音频流
            except Exception as e:  # 捕获写入异常
                logger.error(f"[Player] write failed: {e}")  # 记录错误
                time.sleep(0.01)  # 短暂休眠
            finally:
                with self._cnt_lock:  # 获取计数器锁
                    self._pending_raw_bytes = max(0, self._pending_raw_bytes - len(chunk))  # 减少计数
                self._try_set_idle()  # 尝试设置空闲

    def wait_until_idle(self, timeout: float = 10.0) -> bool:
        """
        等待播放器进入空闲状态
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            是否在超时前进入空闲状态
        """
        return self._idle_event.wait(timeout=timeout)  # 等待空闲事件

    def get_reference_frame(self, timeout: float = 0.01) -> bytes:
        """
        获取一帧参考信号（用于 AEC）
        
        Args:
            timeout: 等待超时时间（默认 10ms）
        
        Returns:
            16kHz 单声道 16-bit PCM 数据，如果队列为空返回空字节串
        """
        try:
            return self.reference_buffer.get(timeout=timeout)  # 从缓冲区获取参考帧
        except queue.Empty:  # 队列为空
            return b""  # 返回空数据

    def shutdown(self):
        """关闭播放器，释放资源"""
        with self._status_lock:  # 获取状态锁
            self._status = "stop"  # 设置停止状态
        self._decoder_thread.join(timeout=1)  # 等待解码线程结束
        self._player_thread.join(timeout=1)  # 等待播放线程结束
        with contextlib.suppress(Exception):  # 忽略异常
            with self._stream_lock:  # 获取流操作锁
                self.player_stream.close()  # 关闭音频流


# 导出公共接口
__all__ = ['B64PCMPlayer']  # 定义模块导出列表
