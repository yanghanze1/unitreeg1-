# -*- coding: utf-8 -*-
"""
Qwen-Omni Realtime 多模态实时互动（语音+视频） + Unitree G1 本地动作控制

本版本改动点：
- 去除：模型输出/播放期间 flag=1 持续 drain 麦克风缓存
- 改为：播放期间仍然发送麦克风到服务端，监听 ASR 转写
  - 若 ASR 命中“打断/暂停/停止播放”等命令：停止当前本地播放 + 尝试 response.cancel
- 仍保留：本地播放真正结束（播放器 idle）再退出 responding 的逻辑（未被打断时）

依赖：
pip install -U dashscope pyaudio opencv-python numpy
"""

import os
import sys
import time
import base64
import json
import re  # 导入正则模块
import signal
import threading
import queue
import contextlib
import pyaudio
import logging

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from llm_api_config import DEFAULT_CONFIG  # 导入LLM API配置
from action_manager import ActionManager  # 导入ActionManager守护线程模块
from emergency_stop import start_keyboard_listener  # 导入键盘急停监听模块
from tool_schema import ROBOT_TOOLS  # 导入机器人控制工具定义
from bridge import execute_tool_call  # 导入Bridge层工具执行函数
from config import FUNCTION_CALLING_CONFIG  # 导入Function Calling配置

import dashscope
from dashscope.audio.qwen_omni import (
    OmniRealtimeConversation,
    OmniRealtimeCallback,
    MultiModality,
    AudioFormat,
)

# ===================== 统一 Key & 地域初始化 =====================
def get_dashscope_api_key() -> str:
    key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if not key:
        key = (DEFAULT_CONFIG.get("api_key") or "").strip()
    if not key:
        raise RuntimeError(
            "未找到 DashScope API Key：请设置环境变量 DASHSCOPE_API_KEY，"
            "或在 llm_api_config.py 的 DEFAULT_CONFIG['api_key'] 中配置"
        )
    os.environ["DASHSCOPE_API_KEY"] = key
    dashscope.api_key = key
    return key


def init_dashscope_endpoints():
    _ = get_dashscope_api_key()
    base_url = (DEFAULT_CONFIG.get("base_url") or "").lower()

    if "dashscope-intl" in base_url:
        dashscope.base_websocket_api_url = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
        dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"
        default_omni_ws = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"
    else:
        dashscope.base_websocket_api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
        dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"
        default_omni_ws = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"

    return default_omni_ws


# ===================== OpenAI Client Singleton =====================
_OPENAI_CLIENT = None

def get_openai_client():
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        if OpenAI is None:
            raise ImportError("缺少 openai 库，请运行: pip install openai")
        
        _OPENAI_CLIENT = OpenAI(
            api_key=get_dashscope_api_key(),
            base_url=DEFAULT_CONFIG.get(
                "base_url", 
                "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
        )
    return _OPENAI_CLIENT



# ===================== flag 控制 =====================
MIC_CHUNK_FRAMES = 3200  # 16kHz 下约 200ms（frames_per_buffer）
_FLAG_LOCK = threading.Lock()
flag = 0  # 0=空闲；1=模型正在输出/本地正在播放


def set_flag(v: int, reason: str = ""):
    global flag
    with _FLAG_LOCK:
        newv = 1 if v else 0
        if flag != newv:
            flag = newv
            if reason:
                logger.debug(f"[FLAG] flag={flag} ({reason})")
            else:
                logger.debug(f"[FLAG] flag={flag}")


def get_flag() -> int:
    with _FLAG_LOCK:
        return flag


# ========= Unitree G1（保留你原逻辑）=========
try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize  # 导入通道初始化模块
    UNITREE_AVAILABLE = True  # 标记SDK可用
except Exception as _e:
    logger.warning(f"[G1] Unitree SDK 未就绪：{_e}")  # 打印SDK初始化失败信息
    UNITREE_AVAILABLE = False  # 标记SDK不可用

g1 = None  # 全局G1客户端实例（LocoClient）
g1_arm = None  # 全局G1手臂动作客户端实例（G1ArmActionClient）
action_manager = None  # 全局ActionManager实例（守护线程）


# ===================== Function Calling 工具调用 =====================

def call_qwen_for_tool_use(user_message: str, tools: list) -> list:
    """
    调用标准 Qwen API 进行工具调用推理
    
    Args:
        user_message: 用户消息
        tools: 工具定义列表
        
    Returns:
        工具调用列表，格式: [{"name": "tool_name", "arguments": {...}}, ...]
        如果调用失败或无工具调用，返回空列表
    """
    # 检查功能开关
    if not FUNCTION_CALLING_CONFIG.get("ENABLED", True):  # 检查是否启用Function Calling
        return []  # 未启用则返回空列表
    
    try:
        # 使用单例客户端，避免重复创建连接
        client = get_openai_client()
        
        # 构建消息
        messages = [    
            {
                "role": "system",
                "content": (
                    "你是一个机器人控制助手。根据用户指令，选择合适的工具来控制机器人移动。"
                    "只在用户明确表达了移动意图时才调用工具。"
                )
            },  # 系统提示
            {"role": "user", "content": user_message}  # 用户消息
        ]
        
        # 调用 API
        response = client.chat.completions.create(
            model=FUNCTION_CALLING_CONFIG.get("MODEL", "qwen-max"),  # 使用配置的模型
            messages=messages,  # 消息列表
            tools=tools,  # 工具定义列表
            tool_choice="auto",  # 自动选择是否调用工具
            temperature=FUNCTION_CALLING_CONFIG.get("TEMPERATURE", 0.3),  # 温度参数
            max_tokens=FUNCTION_CALLING_CONFIG.get("MAX_TOKENS", 500),  # 最大token数
            timeout=FUNCTION_CALLING_CONFIG.get("TIMEOUT", 3.0),  # 超时时间
        )
        
        # 提取工具调用
        tool_calls = []  # 初始化工具调用列表
        message = response.choices[0].message  # 获取响应消息
        
        if hasattr(message, 'tool_calls') and message.tool_calls:  # 检查是否有工具调用
            for tool_call in message.tool_calls:  # 遍历所有工具调用
                # import json  # 已在顶部导入
                tool_calls.append({
                    "name": tool_call.function.name,  # 工具名称
                    "arguments": json.loads(tool_call.function.arguments),  # 工具参数（JSON字符串转字典）
                })  # 添加到工具调用列表
            
            logger.info(f"[FunctionCalling] LLM 生成了 {len(tool_calls)} 个工具调用")  # 记录工具调用数量
        
        return tool_calls  # 返回工具调用列表
    
    except ImportError:  # 捕获 openai 库未安装的异常
        logger.error("[FunctionCalling] 缺少 openai 库，请运行: pip install openai")  # 记录错误
        return []  # 返回空列表
    
    except Exception as e:  # 捕获所有其他异常
        logger.error(f"[FunctionCalling] 调用 Qwen API 失败: {e}")  # 记录错误
        return []  # 返回空列表


def try_execute_g1_by_local_keywords(text: str, action_manager: ActionManager) -> bool:
    """
    基于本地关键词匹配执行G1机器人动作
    
    Args:
        text: 用户语音转写文本
        action_manager: 动作管理器实例
        
    Returns:
        是否成功匹配并执行了动作指令
    """
    # 依赖注入：不再依赖全局 action_manager 和 g1
    # 检查依赖是否有效
    if not (UNITREE_AVAILABLE and action_manager):
        return False
    
    # 检查 ActionManager 是否正在运行
    if not action_manager._running:
        logger.warning("[G1] ActionManager 未运行，指令被忽略")
        return False
    
    t = (text or "").strip()  # 去除文本两端空白字符
    
    if "急停" in t or "停止电机" in t or "别动" in t:
        action_manager.emergency_stop()
        return True
    
    # 挥手关键词检测（新增）
    if any(kw in t for kw in ["挥手", "招招手", "打个招呼", "挥挥手", "招手"]):
        logger.info(f"[Local] 检测到挥手指令: {t}")  # 记录检测到挥手指令
        if g1_arm:  # 检查 g1_arm 手臂动作客户端是否可用
            try:
                # 使用 G1ArmActionClient 执行挥手动作（face wave = 25, high wave = 26）
                g1_arm.ExecuteAction(25)  # 调用SDK执行face wave动作
                logger.info("[Local] 挥手动作执行成功（face wave）")  # 记录成功日志
            except Exception as e:  # 捕获执行异常
                logger.error(f"[Local] 挥手动作执行失败: {e}")  # 记录错误日志
        else:
            logger.warning("[Local] g1_arm 客户端未初始化，无法执行挥手")  # 记录警告
        return True
    
    # 把 "向前", "往前", "走" 都算作前进
    if "前进" in t or "向前" in t or "往前" in t:
        # 默认给个稍微慢点的速度
        action_manager.update_target_velocity(vx=0.5, vy=0.0, vyaw=0.0, duration=2.0)
        return True
    
    if "后退" in t or "往后" in t or "向后" in t:
        action_manager.update_target_velocity(vx=-0.5, vy=0.0, vyaw=0.0, duration=2.0)
        return True
    
    if "左转" in t or "向左" in t:
        action_manager.update_target_velocity(vx=0.0, vy=0.0, vyaw=0.8, duration=2.0)
        return True
    
    if "右转" in t or "向右" in t:
        action_manager.update_target_velocity(vx=0.0, vy=0.0, vyaw=-0.8, duration=2.0)
        return True
    
    if "停止" in t or "停车" in t or "站住" in t:
        action_manager.set_idle()
        return True
        
    return False


# ========= “打断/停止播放” 命令识别（可按需扩展）=========
def is_interrupt_command(transcript: str) -> bool:
    """
    只在“模型正在播放/输出中”时启用：
    - 强触发：打断 / 别说了 / 闭嘴 / 安静 / 停止播放 / 停止回答 / 暂停播放 等
    - 弱触发：出现“停止/暂停/停一下”且同时包含“说/讲/回答/播放/声音”
    """
    t = (transcript or "").strip().lower()
    if not t:
        return False

    strong = [
        "打断", "别说了", "不要说了", "闭嘴", "安静",
        "停止播放", "暂停播放", "停止回答", "停止讲", "停止说话",
        "停播", "停一下声音", "不要播了", "停止",
    ]
    for k in strong:
        if k in t:
            return True

    if ("停止" in t or "暂停" in t or "停一下" in t or "停" == t) and any(
        x in t for x in ["说", "讲", "回答", "播放", "声音", "语音"]
    ):
        return True

    return False


def _detect_self_introduction(text: str) -> bool:
    """
    检测文本是否为自我介绍
    
    Args:
        text: LLM 输出的文本内容
        
    Returns:
        bool: 是否为自我介绍
    """
    if not text:  # 检查文本是否为空
        return False  # 空文本不是自我介绍
    
    t = text.strip()  # 去除文本两端空白字符
    
    # 自我介绍关键词列表
    intro_keywords = [
        "我是", "我的名字", "我叫", "你好我是", 
        "大家好我是", "你可以叫我", "我的名字叫",
        "让我介绍一下", "我来介绍", "自我介绍"
    ]
    
    # 检查是否包含任何自我介绍关键词
    return any(kw in t for kw in intro_keywords)


# ========= 音频播放器（Base64 PCM -> PyAudio，带 idle 判定 + interrupt）=========
class B64PCMPlayer:
    """
    流式播放：不断接收 b64 PCM -> 解码 -> 分片 -> write 到声卡。
    - wait_until_idle(): 判断“本地播放是否真正结束”
    - interrupt(): 立刻清空队列并重置输出流（尽可能立即停）
    """
    def __init__(self, pya: pyaudio.PyAudio, sample_rate=24000, chunk_size_ms=100):
        self.pya = pya
        self.sample_rate = sample_rate
        self.chunk_size_bytes = int(chunk_size_ms * sample_rate * 2 // 1000)

        self._stream_lock = threading.Lock()
        self.player_stream = self._open_stream()

        self.raw_audio_buffer: "queue.Queue[bytes]" = queue.Queue()
        self.b64_audio_buffer: "queue.Queue[str]" = queue.Queue()

        self._status_lock = threading.Lock()
        self._status = "playing"

        self._cnt_lock = threading.Lock()
        self._pending_b64 = 0
        self._pending_raw_bytes = 0

        self._idle_event = threading.Event()
        self._idle_event.set()

        self._abort_event = threading.Event()  # interrupt 时置位：丢弃所有待播数据

        # === AEC 支持：参考信号缓冲区 ===
        self.reference_buffer: "queue.Queue[bytes]" = queue.Queue(maxsize=100)  # 保存播放的参考信号（16kHz）
        try:
            from aec_processor import AudioResampler  # 导入重采样工具
            self.resampler = AudioResampler()  # 用于 24kHz → 16kHz 重采样
        except ImportError:
            self.resampler = None  # 重采样器不可用
            logger.warning("[Player] AEC 模块未找到，参考信号功能禁用")  # 打印警告

        self._decoder_thread = threading.Thread(target=self._decoder_loop, daemon=True)
        self._player_thread = threading.Thread(target=self._player_loop, daemon=True)
        self._decoder_thread.start()
        self._player_thread.start()

    def _open_stream(self):
        """创建并返回PyAudio输出流"""
        return self.pya.open(
            format=pyaudio.paInt16,  # 16位PCM格式
            channels=1,  # 单声道
            rate=self.sample_rate,  # 采样率24kHz
            output=True  # 输出流
        )

    def _set_not_idle(self):
        self._idle_event.clear()

    def _try_set_idle(self):
        with self._cnt_lock:
            ok = (self._pending_b64 == 0 and self._pending_raw_bytes == 0)
        if ok:
            self._idle_event.set()

    def add_data(self, b64_pcm: str):
        if not b64_pcm:
            return
        if self._abort_event.is_set():
            # 正在被打断：直接丢弃新到的音频
            return
        self._set_not_idle()
        with self._cnt_lock:
            self._pending_b64 += 1
        self.b64_audio_buffer.put(b64_pcm)

    def _clear_queue(self, q: queue.Queue):
        while True:
            with contextlib.suppress(queue.Empty):
                q.get_nowait()
                continue
            break

    def interrupt(self, reset_stream: bool = True):
        """
        立即停止当前播放：
        - 置位 abort_event，让 decoder/player 立刻进入丢弃模式
        - 清空 b64/raw 队列 + pending 计数清零
        - 强制 stop_stream + close + reopen，尽最大可能清掉声卡缓冲
        """
        self._abort_event.set()
        self._set_not_idle()

        # 清空内部队列
        self._clear_queue(self.b64_audio_buffer)
        self._clear_queue(self.raw_audio_buffer)

        with self._cnt_lock:
            self._pending_b64 = 0
            self._pending_raw_bytes = 0

        if reset_stream:
            with self._stream_lock:
                with contextlib.suppress(Exception):
                    if self.player_stream.is_active():
                        self.player_stream.stop_stream()
                with contextlib.suppress(Exception):
                    self.player_stream.close()
                with contextlib.suppress(Exception):
                    self.player_stream = self._open_stream()

        # 立即标记 idle
        self._idle_event.set()

        # 解除 abort（允许后续新的 response 正常播放）
        self._abort_event.clear()

    def _decoder_loop(self):
        while True:
            with self._status_lock:
                if self._status == "stop":
                    break

            if self._abort_event.is_set():
                time.sleep(0.01)
                continue

            recv_b64 = None
            with contextlib.suppress(queue.Empty):
                recv_b64 = self.b64_audio_buffer.get(timeout=0.1)

            if not recv_b64:
                self._try_set_idle()
                continue

            with self._cnt_lock:
                if self._pending_b64 > 0:
                    self._pending_b64 -= 1

            try:
                raw = base64.b64decode(recv_b64)
            except Exception:
                self._try_set_idle()
                continue

            if self._abort_event.is_set():
                self._try_set_idle()
                continue

            for i in range(0, len(raw), self.chunk_size_bytes):
                chunk = raw[i:i + self.chunk_size_bytes]
                if not chunk:
                    continue
                with self._cnt_lock:
                    self._pending_raw_bytes += len(chunk)
                self.raw_audio_buffer.put(chunk)

            self._try_set_idle()

    def _player_loop(self):
        # 额外再细分为更短的写入粒度（例如 10ms），让“打断”更灵敏
        # sub_bytes = int(10 * self.sample_rate * 2 // 1000)  # 10ms * 24k * 2bytes
        # B64PCMPlayer._player_loop 里
        sub_bytes = int(40 * self.sample_rate * 2 // 1000)  # 40ms音频数据长度(样本数*2字节)

        while True:
            with self._status_lock:
                if self._status == "stop":
                    break

            if self._abort_event.is_set():
                time.sleep(0.005)
                continue

            chunk = None
            with contextlib.suppress(queue.Empty):
                chunk = self.raw_audio_buffer.get(timeout=0.1)

            if not chunk:
                self._try_set_idle()
                continue

            # 写入前就检查一次
            if self._abort_event.is_set():
                with self._cnt_lock():
                    self._pending_raw_bytes = max(0, self._pending_raw_bytes - len(chunk))
                self._try_set_idle()
                continue

            # === AEC 支持：播放前保存参考信号 ===
            if self.resampler is not None:  # 检查重采样器是否可用
                try:
                    # 将 24kHz 数据重采样到 16kHz，用作 AEC 参考信号
                    ref_16k = self.resampler.resample_24k_to_16k(chunk)  # 执行重采样
                    if ref_16k and not self.reference_buffer.full():  # 检查缓冲区未满
                        self.reference_buffer.put_nowait(ref_16k)  # 非阻塞放入缓冲区
                except Exception as e:  # 捕获异常
                    # 重采样失败不影响播放
                    pass

            try:
                # 关键：把一次 chunk 再拆成更小片，避免 write 阻塞太久
                for i in range(0, len(chunk), sub_bytes):
                    if self._abort_event.is_set():
                        break
                    sub = chunk[i:i + sub_bytes]
                    if not sub:
                        continue
                    with self._stream_lock:
                        self.player_stream.write(sub)
            except Exception as e:
                print("[Player] write failed:", e)
                time.sleep(0.01)
            finally:
                with self._cnt_lock:
                    self._pending_raw_bytes = max(0, self._pending_raw_bytes - len(chunk))
                self._try_set_idle()

    def wait_until_idle(self, timeout: float = 10.0) -> bool:
        return self._idle_event.wait(timeout=timeout)

    def get_reference_frame(self, timeout: float = 0.01) -> bytes:
        """
        获取一帧参考信号（用于 AEC）
        
        Args:
            timeout: 等待超时时间（默认10ms）
        
        Returns:
            16kHz 单声道 16-bit PCM 数据，如果队列为空返回空字节串
        """
        try:
            return self.reference_buffer.get(timeout=timeout)  # 从缓冲区获取参考帧
        except queue.Empty:  # 队列为空
            return b""  # 返回空数据

    def shutdown(self):
        with self._status_lock:
            self._status = "stop"
        self._decoder_thread.join(timeout=1)
        self._player_thread.join(timeout=1)
        with contextlib.suppress(Exception):
            with self._stream_lock:
                self.player_stream.close()


# ========= Omni 回调 =========
class MyCallback(OmniRealtimeCallback):
    def __init__(self):
        super().__init__()
        self.conversation = None
        self.pya = None
        self.mic_stream = None
        self.player = None
        self.action_manager = None  # 依赖注入 ActionManager

        self._respond_lock = threading.Lock()
        self._responding = False

        # 响应序号：避免旧 response 的收尾线程影响新一轮
        self._seq_lock = threading.Lock()
        self._resp_seq = 0

        # 打断后：丢弃当前 response 后续的音频 delta（直到 done）
        self._drop_lock = threading.Lock()
        self._drop_output = False
        
        # 冷却时间：机器人说完话后的一小段时间内忽略 ASR（防止回声自激）
        self._cool_lock = threading.Lock()
        self._last_speak_end_time = 0.0
        
        # 连接状态标志：用于检测连接是否断开
        self._connection_alive = True  # WebSocket连接活跃状态

    def _inc_seq(self) -> int:
        with self._seq_lock:
            self._resp_seq += 1
            return self._resp_seq

    def _get_seq(self) -> int:
        with self._seq_lock:
            return self._resp_seq

    def _set_drop_output(self, v: bool):
        with self._drop_lock:
            self._drop_output = bool(v)

    def _should_drop_output(self) -> bool:
        with self._drop_lock:
            return bool(self._drop_output)

    def is_responding(self) -> bool:
        with self._respond_lock:
            return bool(self._responding)

    def _enter_response_mode(self):
        with self._respond_lock:
            if self._responding:
                return
            self._responding = True

        set_flag(1, reason="model_output_start")
        self._inc_seq()

    def _exit_response_mode_if_seq(self, seq: int, reason: str):
        if seq != self._get_seq():
            return
        with self._respond_lock:
            self._responding = False
        set_flag(0, reason=reason)

    def _force_exit_response_mode(self, reason: str):
        """
        立即退出 responding，并将 seq+1，使旧的收尾线程失效
        """
        with self._respond_lock:
            self._responding = False
        self._inc_seq()
        set_flag(0, reason=reason)
        # 强制退出时也更新结束时间（防止打断后的余音触发）
        with self._cool_lock:
            self._last_speak_end_time = time.time()

    def _ensure_dict(self, message):
        if isinstance(message, dict):
            return message
        if isinstance(message, str):
            with contextlib.suppress(Exception):
                return json.loads(message)
        return {}

    def on_open(self) -> None:
        logger.info("[Omni] connection opened; init microphone & player")

        self.pya = pyaudio.PyAudio()
        self.mic_stream = self.pya.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=MIC_CHUNK_FRAMES,  # 每次读取3200帧(约200ms)
        )
        self.player = B64PCMPlayer(self.pya, sample_rate=24000, chunk_size_ms=100)

        set_flag(0, reason="init_ready")

    def on_close(self, close_status_code, close_msg) -> None:
        logger.info(f"[Omni] connection closed: code={close_status_code}, msg={close_msg}")
        self._cleanup()  # 清理资源
        self._connection_alive = False  # 标记连接已断开，触发主循环退出

    def _cleanup(self):
        with contextlib.suppress(Exception):
            if self.player:
                self.player.shutdown()
        with contextlib.suppress(Exception):
            if self.mic_stream:
                self.mic_stream.close()
        with contextlib.suppress(Exception):
            if self.pya:
                self.pya.terminate()

    def _try_cancel_server_response(self):
        """
        文档支持 client event: response.cancel。
        SDK 若暴露 cancel_response()，则调用；否则忽略。
        """
        if not self.conversation:
            return
        fn = getattr(self.conversation, "cancel_response", None)
        if callable(fn):
            with contextlib.suppress(Exception):
                fn()
                print("[Omni] response.cancel sent")
        else:
            # SDK 不一定暴露该方法；不强依赖
            pass

    def _interrupt_playback(self, transcript: str):
        logger.info(f"[ASR-INTERRUPT] {transcript}")
        self._set_drop_output(True)

        # 1) 本地立刻停（清队列+重置输出流）
        if self.player:
            with contextlib.suppress(Exception):
                self.player.interrupt(reset_stream=True)

        # 2) 尝试让服务端也取消当前 response
        self._try_cancel_server_response()

        # 3) 立即退出 responding，允许继续对话
        self._force_exit_response_mode(reason="interrupted_by_user")

    def _execute_tool_command(self, transcript: str):
        """执行工具调用逻辑 (Function Calling)"""
        # 检查功能开关
        if not FUNCTION_CALLING_CONFIG.get("ENABLED", True):
            return

        try:
            # 调用 Qwen API
            logger.info(f"[G1-Tool] 开始处理指令: {transcript}")
            tool_calls = call_qwen_for_tool_use(transcript, ROBOT_TOOLS)
            
            if tool_calls:
                for tool_call in tool_calls:
                    result = execute_tool_call(
                        tool_name=tool_call["name"],
                        params=tool_call["arguments"],
                        action_manager=self.action_manager,
                        g1_client=g1,
                        g1_arm_client=g1_arm
                    )
                    if result["status"] == "success":
                        logger.info(f"[G1] 工具调用成功: {result['message']}")
                    elif result["status"] == "success_with_warning":
                        logger.warning(f"[G1] 工具调用成功（有警告）: {result['message']} | {result.get('warning', '')}")
                    else:
                        logger.error(f"[G1] 工具调用失败: {result['message']}")
                
                # 语音确认
                with contextlib.suppress(Exception):
                    self.conversation.create_response(
                        instructions=(
                            f"用户下达了动作指令：{transcript}。"
                            "请用一句简短中文确认你已执行，不要解释原理。"
                        )
                    )
            else:
                logger.debug(f"[G1] 未生成工具调用: {transcript}")

        except Exception as e:
            logger.error(f"[G1] 工具执行异常: {e}")

    def on_event(self, message) -> None:
        resp = self._ensure_dict(message)  # 转换为字典格式
        etype = resp.get("type", "")  # 获取消息类型
        
        # ========= 新增：自我介绍检测与自动挥手 =========
        if etype == "response.audio_transcript.delta":  # 音频转写文本增量
            delta_text = resp.get("delta", "")  # 获取文本增量
            if delta_text and _detect_self_introduction(delta_text):  # 检测是否为自我介绍
                logger.info(f"[Callback] 检测到自我介绍关键词：{delta_text[:50]}...")  # 记录检测日志（截取前50字符）
                
                # 延迟 0.5 秒后执行挥手（与语音播放同步）
                def delayed_wave():
                    time.sleep(0.5)  # 延迟 0.5 秒
                    if g1_arm:  # 检查 g1_arm 手臂动作客户端是否可用
                        try:
                            # 使用 G1ArmActionClient 执行挥手动作（face wave = 25）
                            g1_arm.ExecuteAction(25)  # 调用SDK执行face wave动作
                            logger.info("[Callback] 自我介绍自动挥手执行成功")  # 记录成功日志
                        except Exception as e:  # 捕获执行异常
                            logger.error(f"[Callback] 自我介绍自动挥手失败: {e}")  # 记录错误日志
                    else:
                        logger.warning("[Callback] g1_arm 客户端未初始化，自动挥手跳过")
                
                # 在独立线程中执行，不阻塞音频播放
                wave_thread = threading.Thread(target=delayed_wave, daemon=True)  # 创建守护线程
                wave_thread.start()  # 启动线程

        if etype == "session.created":
            sid = (resp.get("session") or {}).get("id", "")
            logger.info(f"[Omni] session.created: {sid}")
            return
        if etype == "session.updated":
            logger.info("[Omni] session.updated")
            return

        # 输入语音转写完成
        if etype == "conversation.item.input_audio_transcription.completed":
            transcript = (resp.get("transcript") or "").strip()
            if not transcript:
                return

            # 若当前模型正在输出/播放：
            # 1. 监听“打断类命令”（强打断）
            # 2. 监听“复杂控制指令”（如“前进一米”），视为打断并执行
            if self.is_responding() or get_flag() == 1:
                # 检测是否为复杂指令
                is_complex_cmd = False
                t_check = (transcript or "").strip()
                if t_check:
                    if re.search(r'\d+', t_check):
                        is_complex_cmd = True
                    else:
                        complex_markers = [
                            "一米", "一度", "一秒", "一步", "一圈",
                            "二", "三", "四", "五", "六", "七", "八", "九", "十", "半",
                            "慢慢", "快速", "缓缓", "稍微", "一点",
                            "并且", "同时", "然后",
                        ]
                        if any(marker in t_check for marker in complex_markers):
                            is_complex_cmd = True

                if is_interrupt_command(transcript) or is_complex_cmd:
                    logger.info(f"[ASR-Interrupt] 触发打断 (Complex={is_complex_cmd}): {transcript}")
                    self._interrupt_playback(transcript)
                    
                    # 安全修复：如果包含停止意图，立即停止机器人运动
                    # 检查 "停"、"急停"、"别动"、"站住"
                    stop_keywords = ["停", "急停", "别动", "站住"]
                    is_stop = any(x in transcript for x in stop_keywords)
                    
                    if is_stop:
                         logger.warning(
                             f"[Safety] 检测到打断指令包含停止意图: {transcript}，"
                             "强制停止运动"
                         )
                         if self.action_manager:
                             # 如果是明确的急停关键词，执行硬急停
                             if "急停" in transcript:
                                 self.action_manager.emergency_stop()
                                 logger.warning(
                                     "[Safety] 触发 ActionManager.emergency_stop()"
                                 )
                             else:
                                 self.action_manager.set_idle()
                                 logger.info("[Safety] 触发 ActionManager.set_idle()")
                    
                    # 修复：如果是复杂指令且不是纯粹的停止，执行工具调用
                    if is_complex_cmd and not is_stop:
                        logger.info(f"[G1-Interrupt] 这是一个复杂动作指令，启动执行线程: {transcript}")
                        threading.Thread(
                            target=self._execute_tool_command, 
                            args=(transcript,), 
                            daemon=True
                        ).start()
                else:
                    # 非打断命令：只打印（可按需关闭）
                    print(f"[ASR-IGNORED] {transcript}")
                return

            # 空闲态：正常打印 + 本地动作指令
            
            # 检查冷却时间（防止回声自激）
            with self._cool_lock:
                cool_time = 1.5  # 1.5秒冷却期
                if time.time() - self._last_speak_end_time < cool_time:
                    logger.info(f"[ASR-COOLED] 处于回声冷却期，忽略输入: {transcript}")
                    return

            logger.info(f"[ASR] {transcript}")

            def _do_g1():
                try:
                    # 步骤0: 检测指令复杂度（包含数字、修饰词、复合动作等）
                    # 复杂指令跳过关键词匹配，直接使用 Function Calling
                    # import re  # 已在顶部导入
                    t = (transcript or "").strip()
                    is_complex = False
                    if t:
                        # 检测数字
                        if re.search(r'\d+', t):
                            is_complex = True
                        # 检测中文数字和修饰词
                        complex_markers = [
                            # "一" 太容易误触（如“介绍一下”），改为更明确的量词搭配
                            "一米", "一度", "一秒", "一步", "一圈",
                            "二", "三", "四", "五", "六", "七", "八", "九", "十", "半",
                            "慢慢", "快速", "缓缓", "稍微", "一点",
                            "并且", "同时", "然后",
                        ]
                        if any(marker in t for marker in complex_markers):
                            is_complex = True
                    
                    if is_complex:
                        logger.info(
                            f"[G1] 检测到复杂指令，跳过关键词匹配: {transcript}"
                        )
                        # 直接使用 Function Calling (复用方法)
                        self._execute_tool_command(transcript)
                        return
                    
                    # 步骤1: 简单指令使用本地关键词匹配（快速路径）
                    executed = try_execute_g1_by_local_keywords(transcript, self.action_manager)  # 使用本地关键词匹配
                    if executed:  # 如果关键词匹配成功
                        logger.info("[G1] 本地关键词指令已执行")  # 记录执行日志
                        with contextlib.suppress(Exception):  # 捕获并忽略异常
                            self.conversation.create_response(
                                instructions=(
                                    f"用户下达了动作指令：{transcript}。"
                                    "请用一句简短中文确认你已执行，不要解释原理。"
                                )
                            )  # 生成确认响应
                        return  # 提前返回，不再执行工具调用
                    
                    # 步骤2: 关键词未匹配，尝试调用 LLM 工具推理
                    self._execute_tool_command(transcript)
                    
                except Exception as e:  # 捕获所有异常
                    logger.error(f"[G1] 执行失败：{e}")  # 记录错误

            threading.Thread(target=_do_g1, daemon=True).start()
            return

        # ====== 模型开始输出（文本/音频任一到来）-> flag=1 ======
        if etype == "response.audio_transcript.delta":
            delta = resp.get("delta", "")
            if delta:
                if not self._should_drop_output():
                    self._enter_response_mode()
                    print(delta, end="", flush=True)
            return

        if etype == "response.audio.delta":
            b64_pcm = resp.get("delta", "")
            if b64_pcm:
                if not self._should_drop_output():
                    self._enter_response_mode()
                    if self.player:
                        self.player.add_data(b64_pcm)
            return

        if etype == "response.audio_transcript.done":
            print("\n[Omni] transcript done")
            return

        # 兼容：音频生成结束（文档有 response.audio.done）
        if etype == "response.audio.done":
            print("\n[Omni] response.audio.done")
            return

        # ====== 服务端输出结束：未被打断时，等本地播放 idle 后再 flag=0 ======
        if etype == "response.done":
            rid = ""
            with contextlib.suppress(Exception):
                rid = self.conversation.get_last_response_id()
            print(f"\n[Omni] response.done (id={rid})")

            # 若刚发生打断：直接恢复输入，不再等 idle（播放器已被清空）
            if self._should_drop_output():
                self._set_drop_output(False)
                self._force_exit_response_mode(reason="server_done_after_interrupt")
                return

            seq = self._get_seq()

            def _finish_after_local_playback(local_seq: int):
                if self.player:
                    self.player.wait_until_idle(timeout=10.0)
                self._exit_response_mode_if_seq(local_seq, reason="local_playback_end")
                # 更新说话结束时间，开启冷却窗口
                with self._cool_lock:
                    self._last_speak_end_time = time.time()

            threading.Thread(
                target=_finish_after_local_playback, args=(seq,), daemon=True
            ).start()
            return


def start_camera_loop(conversation: OmniRealtimeConversation, stop_event: threading.Event, send_lock: threading.Lock):
    if cv2 is None:
        logger.warning("[Camera] 未安装 opencv-python，跳过视频输入")
        return

    cam_id = int(os.getenv("CAMERA_ID", "6"))  # 摄像头设备ID(默认6)
    send_fps = float(os.getenv("SEND_FPS", "1"))  # 视频发送帧率(默认1fps)
    interval = 1.0 / max(send_fps, 0.1)  # 计算发送间隔时间

    cap = cv2.VideoCapture(cam_id)
    if not cap.isOpened():
        print(f"[Camera] 打开摄像头失败：id={cam_id}")
        return

    print(f"[Camera] started (id={cam_id}, fps={send_fps})")
    last = 0.0
    while not stop_event.is_set():
        now = time.time()
        if now - last < interval:
            time.sleep(0.01)
            continue
        last = now

        ok, frame = cap.read()
        if not ok:
            continue

        frame = cv2.resize(frame, (640, 360))
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            continue

        jpg_bytes = buf.tobytes()
        if len(jpg_bytes) > 500 * 1024:
            continue

        b64_jpg = base64.b64encode(jpg_bytes).decode("ascii")
        with contextlib.suppress(Exception):
            # 优化：非阻塞获取锁，如果音频正在发送（锁被占用），则丢弃当前帧，优先保证音频实时性
            if send_lock.acquire(blocking=False):
                try:
                    conversation.append_video(b64_jpg)
                finally:
                    send_lock.release()
            else:
                # 锁被占用，丢帧
                pass

    cap.release()
    print("[Camera] stopped")


def main():
    default_omni_ws = init_dashscope_endpoints()

    model = os.getenv("OMNI_MODEL", "qwen3-omni-flash-realtime")
    voice = os.getenv("OMNI_VOICE", "Cherry")
    url = (os.getenv("OMNI_WS_URL") or "").strip() or default_omni_ws

    callback = MyCallback()  # 创建Omni回调处理器实例
    conversation = OmniRealtimeConversation(model=model, callback=callback, url=url)  # 创建Omni实时对话实例
    callback.conversation = conversation  # 将conversation实例绑定到callback，以便回调中访问

    # 初始化并启动ActionManager守护线程
    global action_manager  # 声明使用全局变量
    if UNITREE_AVAILABLE and g1:  # 检查SDK和g1客户端是否就绪
        action_manager = ActionManager(g1)  # 创建ActionManager实例，传入g1客户端
        action_manager.start()  # 启动100Hz控制循环守护线程
        callback.action_manager = action_manager  # 注入 ActionManager 到回调实例
        logger.info("[ActionManager] 已启动（100Hz心跳维持）")  # 打印启动成功日志
        
        # 启动键盘急停监听线程
        emergency_listener = start_keyboard_listener(action_manager, g1)  # 启动键盘监听，绑定Space键为急停
        logger.info("[EmergencyStop] 键盘急停监听已启动（按 Space 键紧急停止）")  # 打印启动成功日志
    else:
        logger.warning("[ActionManager] 未启动（G1客户端未就绪）")  # 打印未启动原因

    logger.info("[Omni] connecting ...")  # 打印Omni连接提示
    conversation.connect()  # 建立WebSocket连接

    instructions = (
        "你叫来福，是来自厦门博智科技的机器人。"
        "你是一个实体机器人，拥有控制自己移动的能力。"
        "我们在厦门火炬滴灌科创基金首批投资项目签约仪式暨项目路演现场。非常期待和各位专家会后进行更深一步的交流。"
        "用户下达移动指令（如前进、后退、转弯、走几米）时，**必须**调用工具 `move_robot` 或 `rotate_robot` 来执行。"
        "**严禁**在不调用工具的情况下，仅通过文字回复说'正在移动'。"
        "如果调用了工具，请只回复一句简短的确认，如'收到，执行中'。"
        
        # --- 修改重点：把“当是要你...”改成“只有当用户问你...” ---
        "如果用户明确问你是谁、或者让你介绍自己时，你才回答：'您好，我是来自厦门博智科技的机器人来福，有什么问题大家可以问我！'"
        "如果用户只是简单的打招呼（如说'你好'），你只需要简短回复：'你好！'或'我在，请说。'，千万不要长篇大论介绍自己。"
        "如果用户直接问具体问题（如'今天天气怎么样'），直接回答问题，不要自我介绍。"
        "如果用户让你介绍博智科技，请完整回答：厦门博智科技由留法博士团队于2019年创立，专注于具身智能、群体智能和垂直领域大模型的产业化应用，致力于将人工智能深度融入物理实体，如机器人和机器狗等，赋予其感知、学习和与环境动态交互的能力。目前是国家高新技术企业、厦门市重点上市后备企业等。"
        "当介绍陈龙彪博士时，请完整回答：陈龙彪博士，厦门大学信息学院副教授、博导，国家级海外高层次人才、福建省高层次人才A类、厦门市双百人才。主要研究方向是：群体智能、具身智能、人工智能等。" 
        "当问你还有什么其它技能时，请完整回答：除了和大家打招呼、互动，我在公司还能针对封闭园区进行自主导航训练，为来访的客人提供引导服务，保证大家能顺利找到目的地。而且，我们团队还会针对不同行业，为我训练特定的语料库，像金融知识、法律常识等领域的内容我都有所涉猎，能为不同行业的用户提供专业的信息咨询服务。" 
        # ---------------------
        "用中文回答问题，回答问题基于事实要准确，语气正式，每次回答不超过200个字。"
    )

    conversation.update_session(
        output_modalities=[MultiModality.AUDIO, MultiModality.TEXT],
        voice=voice,
        input_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,
        output_audio_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
        enable_input_audio_transcription=True,
        input_audio_transcription_model="gummy-realtime-v1",
        enable_turn_detection=True,  
        turn_detection_type="server_vad",
        turn_detection_config={  # 配置VAD参数防止长时间静音断连
            "silence_duration_ms": 600000,  # 静音超时时间设为10分钟(600秒)
            "prefix_padding_ms": 300,  # 保留前缓冲300ms
            "threshold": 0.5  # VAD检测阈值
        },
        instructions=instructions,
    )

    stop_event = threading.Event()
    send_lock = threading.Lock()

    cam_thread = threading.Thread(
        target=start_camera_loop, args=(conversation, stop_event, send_lock), daemon=True
    )
    cam_thread.start()

    def _sigint(sig, frame):
        """Ctrl+C信号处理函数，优雅退出程序"""
        print("\n[System] Ctrl+C pressed, closing ...")  # 打印退出提示
        stop_event.set()  # 设置停止事件，通知摄像头线程退出
        
        # 停止ActionManager控制循环
        global action_manager  # 声明使用全局变量
        if action_manager:  # 检查ActionManager是否已初始化
            with contextlib.suppress(Exception):  # 捕获并忽略所有异常
                action_manager.stop()  # 停止控制循环并发送停止指令
                print("[ActionManager] 已停止")  # 打印停止成功日志
        
        with contextlib.suppress(Exception):  # 捕获并忽略所有异常
            conversation.close()  # 关闭Omni WebSocket连接
        with contextlib.suppress(Exception):  # 捕获并忽略所有异常
            if callback.player:  # 检查播放器是否存在
                callback.player.shutdown()  # 关闭音频播放器
        sys.exit(0)  # 退出程序

    signal.signal(signal.SIGINT, _sigint)

    print("===== Omni Realtime 已启动（播放期间仍送麦克风做 ASR；命中打断口令则停止播放）=====")
    print("Press Ctrl+C to stop.")

    # === 初始化 AEC 处理器 ===
    aec_processor = None  # AEC 处理器实例
    try:
        from aec_processor import AECProcessor, SPEEXDSP_AVAILABLE  # 导入 AEC 处理器
        if SPEEXDSP_AVAILABLE:  # 检查 speexdsp 库是否可用
            aec_processor = AECProcessor(
                frame_size=320,  # 20ms @ 16kHz = 320 samples
                filter_length=2048,  # 滤波器长度（可调整性能与效果平衡）
                sample_rate=16000,  # 采样率（与麦克风一致）
                enabled=True  # 启用 AEC
            )
            logger.info("[AEC] 回声消除处理器已启动")  # 记录启动成功
        else:
            logger.warning("[AEC] speexdsp 库不可用，AEC 功能禁用")  # 记录警告
    except Exception as e:  # 捕获异常
        logger.error(f"[AEC] 初始化失败: {e}")  # 记录错误
        aec_processor = None  # 禁用 AEC

    while True:
        # 检查连接状态，如果已断开则退出主循环
        if not callback._connection_alive:  # 检查WebSocket连接是否断开
            logger.warning("[System] WebSocket 连接已断开，程序退出")  # 记录连接断开事件
            break  # 退出主循环
        
        if not callback.mic_stream:  # 检查麦克风流是否就绪
            time.sleep(0.05)  # 等待麦克风初始化
            continue  # 继续下一次循环

        # 始终 read
        audio_data = callback.mic_stream.read(MIC_CHUNK_FRAMES, exception_on_overflow=False)

        # === AEC 处理：分帧消除回声 ===
        if aec_processor and hasattr(aec_processor, 'enabled') and aec_processor.enabled:  # 检查 AEC 是否启用
            # 将 200ms 数据（6400 bytes）分割为 10 个 20ms 帧（320 samples * 2 bytes = 640 bytes）
            frame_size_bytes = 320 * 2  # 320 samples * 2 bytes = 640 bytes
            cleaned_chunks = []  # 存储清洗后的帧
            
            for i in range(0, len(audio_data), frame_size_bytes):  # 遍历每一帧
                mic_frame = audio_data[i:i + frame_size_bytes]  # 提取麦克风帧
                
                # 不足一帧，补零
                if len(mic_frame) < frame_size_bytes:
                    mic_frame += b'\x00' * (frame_size_bytes - len(mic_frame))
                
                # 获取对应的参考帧（播放器输出）
                ref_frame = b""  # 初始化参考帧
                if callback.player:  # 检查播放器是否存在
                    ref_frame = callback.player.get_reference_frame(timeout=0.001)  # 获取参考信号（1ms超时）
                
                # 参考帧长度不足，补零
                if len(ref_frame) < frame_size_bytes:
                    ref_frame += b'\x00' * (frame_size_bytes - len(ref_frame))
                
                # 执行 AEC（核心步骤）
                cleaned_frame = aec_processor.process(mic_frame, ref_frame)  # 回声消除
                cleaned_chunks.append(cleaned_frame)  # 添加到结果列表
           
            # 合并所有清洗后的帧
            audio_data = b"".join(cleaned_chunks)  # 拼接为完整音频数据

        # 关键修改：不再因为 flag=1 就丢弃麦克风数据
        # 仍然发送，让服务端 ASR 能识别“打断口令”
        audio_b64 = base64.b64encode(audio_data).decode("ascii")
        
        # 音频发送必须可靠，使用阻塞获取锁
        with send_lock:
            conversation.append_audio(audio_b64)


if __name__ == "__main__":
    try:
        if UNITREE_AVAILABLE:
            # 1. 初始化通道 (G1 必须用 eth0)
            net_if = sys.argv[1] if len(sys.argv) >= 2 else "eth0"  # 从命令行参数获取网卡名称(默认eth0)
            print(f"[G1] 初始化通道，网卡：{net_if}")  # 打印网卡配置信息
            ChannelFactoryInitialize(0, net_if)  # 初始化Unitree SDK通道工厂

            # 2. 实例化 G1 LocoClient
            try:
                # 确保导入了正确的类
                from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
                
                print("[G1] 正在实例化 G1 LocoClient...")
                g1 = LocoClient() 
                g1.SetTimeout(10.0)
                g1.Init()
                
                print("[G1] 正在实例化 G1ArmActionClient...")
                from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient
                g1_arm = G1ArmActionClient()
                g1_arm.SetTimeout(10.0)
                g1_arm.Init()
                
                print("[G1] 客户端实例化成功！")
                
                # === 修改重点：直接接管控制 ===
                # 既然已经是站立模式，直接发送 0 速度指令。
                # 这有两个作用：
                # 1. 告诉底层“SDK 已上线，准备接管”
                # 2. 保持当前站立姿态不动
                print("[G1] 默认已站立，发送零速度指令以激活控制权...")
                g1.Move(0.0, 0.0, 0.0)
                
                # 稍微等一秒让控制权同步
                time.sleep(1)
                print("[G1] 控制系统已就绪，随时可以响应语音！")
                
            except ImportError:
                print("[G1] 错误：SDK 版本不匹配，找不到 LocoClient")
            except Exception as e:
                print(f"[G1] 客户端连接失败: {e}")

        else:
            print("[G1] 未启用（Unitree SDK 不可用）")
            
    except Exception as e:
        print(f"[G1] 初始化失败：{e}")

    # 启动主程序
    main()