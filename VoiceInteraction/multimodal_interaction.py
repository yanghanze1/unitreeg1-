# -*- coding: utf-8 -*-
"""
Qwen-Omni Realtime 多模态实时互动（语音+视频） + Unitree G1 本地动作控制

主入口模块：协调各子模块完成语音交互和机器人控制

依赖模块：
- api_init: API 初始化
- audio_player: 音频播放
- omni_callback: Omni 回调处理
- command_detector: 命令检测
- action_manager: 动作控制
- bridge: 工具执行

依赖安装：
pip install -U dashscope pyaudio opencv-python numpy openai

重构时间: 2026-01-29
"""

import os  # 导入操作系统模块
import sys  # 导入系统模块
import time  # 导入时间模块
import base64  # 导入 Base64 编解码模块
import signal  # 导入信号处理模块
import threading  # 导入线程模块
import contextlib  # 导入上下文管理模块
import logging  # 导入日志模块

try:
    import cv2  # 尝试导入 OpenCV
except ImportError:
    cv2 = None  # OpenCV 不可用

# 配置日志
logging.basicConfig(
    level=logging.INFO,  # 设置日志级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # 设置日志格式
    handlers=[logging.StreamHandler(sys.stdout)]  # 输出到标准输出
)
logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器

# 导入子模块
from api_init import init_dashscope_endpoints  # 导入 API 初始化函数
from omni_callback import OmniCallback, MIC_CHUNK_FRAMES  # 导入 Omni 回调处理器
from action_manager import ActionManager  # 导入 ActionManager 守护线程模块
from emergency_stop import start_keyboard_listener  # 导入键盘急停监听模块

# 导入 DashScope Omni SDK
from dashscope.audio.qwen_omni import (
    OmniRealtimeConversation,
    MultiModality,
    AudioFormat,
)

# ===================== Flag 控制 =====================
_FLAG_LOCK = threading.Lock()  # Flag 操作锁
flag = 0  # 0=空闲；1=模型正在输出/本地正在播放


def set_flag(v: int, reason: str = ""):
    """
    设置 flag 状态
    
    Args:
        v: 新状态值（0 或 1）
        reason: 状态变更原因（用于调试）
    """
    global flag
    with _FLAG_LOCK:  # 获取锁
        newv = 1 if v else 0  # 规范化为 0 或 1
        if flag != newv:  # 如果状态发生变化
            flag = newv  # 更新状态
            if reason:  # 如果有原因
                logger.debug(f"[FLAG] flag={flag} ({reason})")  # 记录调试日志
            else:
                logger.debug(f"[FLAG] flag={flag}")  # 记录调试日志


def get_flag() -> int:
    """获取当前 flag 状态"""
    with _FLAG_LOCK:  # 获取锁
        return flag  # 返回当前状态


# ===================== Unitree G1 初始化 =====================
try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize  # 导入通道初始化模块
    UNITREE_AVAILABLE = True  # 标记 SDK 可用
except Exception as _e:
    logger.warning(f"[G1] Unitree SDK 未就绪：{_e}")  # 打印 SDK 初始化失败信息
    UNITREE_AVAILABLE = False  # 标记 SDK 不可用

g1 = None  # 全局 G1 客户端实例（LocoClient）
g1_arm = None  # 全局 G1 手臂动作客户端实例（G1ArmActionClient）
action_manager = None  # 全局 ActionManager 实例（守护线程）


# ===================== 摄像头视频循环 =====================
def start_camera_loop(
    conversation: OmniRealtimeConversation, 
    stop_event: threading.Event, 
    send_lock: threading.Lock,
    cap=None  # 外部注入的摄像头实例（可选，避免重连时设备索引漂移）
):
    """
    启动摄像头视频发送循环
    
    Args:
        conversation: Omni 对话实例
        stop_event: 停止事件
        send_lock: 发送锁（与音频发送共享）
        cap: 外部注入的 cv2.VideoCapture 实例（可选，避免重连时设备索引漂移）
    """
    if cv2 is None:  # 如果 OpenCV 不可用
        logger.warning("[Camera] 未安装 opencv-python，跳过视频输入")  # 记录警告
        return
    
    # 检查是否从外部注入摄像头
    external_cap = cap is not None  # 标记是否为外部摄像头
    
    if cap is None:  # 如果没有外部摄像头
        cam_id = int(os.getenv("CAMERA_ID", "0"))  # 摄像头设备 ID(默认 6)
        cap = cv2.VideoCapture(cam_id)  # 打开摄像头
        if not cap.isOpened():  # 如果打开失败
            logger.error(f"[Camera] 打开摄像头失败：id={cam_id}")  # 记录错误
            return
        logger.info(f"[Camera] started (id={cam_id}, internal)")  # 记录启动信息
    else:
        if not cap.isOpened():  # 检查外部摄像头是否可用
            logger.warning("[Camera] 外部摄像头未打开，跳过视频输入")
            return
        logger.info("[Camera] started (external cap)")  # 记录启动信息

    send_fps = float(os.getenv("SEND_FPS", "1"))  # 视频发送帧率(默认 1fps)
    interval = 1.0 / max(send_fps, 0.1)  # 计算发送间隔时间
    last = 0.0  # 上次发送时间
    
    while not stop_event.is_set():  # 主循环
        now = time.time()  # 当前时间
        if now - last < interval:  # 如果未到发送间隔
            time.sleep(0.01)  # 休眠
            continue
        last = now  # 更新上次发送时间

        ok, frame = cap.read()  # 读取帧
        if not ok:  # 如果读取失败
            continue

        frame = cv2.resize(frame, (640, 360))  # 调整分辨率
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])  # 编码为 JPEG
        if not ok:  # 如果编码失败
            continue

        jpg_bytes = buf.tobytes()  # 转换为字节
        if len(jpg_bytes) > 500 * 1024:  # 如果超过 500KB
            continue  # 跳过

        b64_jpg = base64.b64encode(jpg_bytes).decode("ascii")  # Base64 编码
        with contextlib.suppress(Exception):  # 忽略异常
            # 优化：非阻塞获取锁，如果音频正在发送（锁被占用），则丢弃当前帧
            if send_lock.acquire(blocking=False):  # 尝试获取锁
                try:
                    conversation.append_video(b64_jpg)  # 发送视频帧
                finally:
                    send_lock.release()  # 释放锁
            # 锁被占用则丢帧

    # 只有在内部创建的摄像头才释放
    if not external_cap:  # 如果是内部摄像头
        cap.release()  # 释放摄像头
    logger.info("[Camera] stopped")  # 记录停止信息


# ===================== 主函数 =====================
def main():
    """主入口函数（带自动重连机制）"""
    global action_manager  # 声明使用全局变量
    
    # 初始化 DashScope 端点
    default_omni_ws = init_dashscope_endpoints()  # 获取默认 WebSocket 端点

    # 获取配置
    model = os.getenv("OMNI_MODEL", "qwen3-omni-flash-realtime")  # 模型名称
    voice = os.getenv("OMNI_VOICE", "Cherry")  # 语音名称
    url = (os.getenv("OMNI_WS_URL") or "").strip() or default_omni_ws  # WebSocket 端点
    
    # 配置系统指令（全局复用）
    instructions = (
        "你叫来福，是来自厦门博智科技的机器人。"
        "你是一个实体机器人，拥有控制自己移动的能力。"
        "我们在厦门博智科技的展厅。"
        "非常期待和各位专家会后进行更深一步的交流。"
        "用户下达移动指令（如前进、后退、转弯、走几米）时，**必须**调用工具 "
        "`move_robot` 或 `rotate_robot` 来执行。"
        "**严禁**在不调用工具的情况下，仅通过文字回复说'正在移动'。"
        "如果调用了工具，请只回复一句简短的确认，如'收到，执行中'。"
        "你可以挥手，如果用户让你挥挥手，请回答：你好！"
        "如果用户明确问你是谁、或者让你介绍自己时，你才回答："
        "'您好，我是来自厦门博智科技的机器人来福，有什么问题大家可以问我！'"
        "如果用户只是简单的打招呼（如说'你好'），你只需要简短回复：'你好！'或"
        "'我在，请说。'，千万不要长篇大论介绍自己。"
        "如果用户直接问具体问题（如'今天天气怎么样'），直接回答问题，不要自我介绍。"
        "如果用户让你介绍博智科技，请完整回答：厦门博智科技由留法博士团队于2019年创立，"
        "专注于具身智能、群体智能和垂直领域大模型的产业化应用，致力于将人工智能深度融入"
        "物理实体，如机器人和机器狗等，赋予其感知、学习和与环境动态交互的能力。"
        "目前是国家高新技术企业、厦门市重点上市后备企业等。"
        "当介绍陈龙彪博士时，请完整回答：陈龙彪博士，厦门大学信息学院副教授、博导，"
        "国家级海外高层次人才、福建省高层次人才A类、厦门市双百人才。"
        "主要研究方向是：群体智能、具身智能、人工智能等。"
        "当问你还有什么其它技能时，请完整回答：除了和大家打招呼、互动，我在公司还能"
        "针对封闭园区进行自主导航训练，为来访的客人提供引导服务，保证大家能顺利找到"
        "目的地。而且，我们团队还会针对不同行业，为我训练特定的语料库，像金融知识、"
        "法律常识等领域的内容我都有所涉猎，能为不同行业的用户提供专业的信息咨询服务。"
        "用中文回答问题，回答问题基于事实要准确，语气正式，每次回答不超过200个字。"
    )
    
    # 初始化 AEC 处理器（全局复用）
    aec_processor = None
    try:
        from aec_processor import AECProcessor, SPEEXDSP_AVAILABLE
        if SPEEXDSP_AVAILABLE:
            aec_processor = AECProcessor(
                frame_size=320,  # 20ms @ 16kHz
                filter_length=2048,
                sample_rate=16000,
                enabled=True
            )
            logger.info("[AEC] 回声消除处理器已启动")
        else:
            logger.warning("[AEC] speexdsp 库不可用，AEC 功能禁用")
    except Exception as e:
        logger.error(f"[AEC] 初始化失败: {e}")
        aec_processor = None
    
    # 初始化并启动 ActionManager 守护线程（全局，只启动一次）
    if UNITREE_AVAILABLE and g1:  # 检查 SDK 和 g1 客户端是否就绪
        action_manager = ActionManager(g1)  # 创建 ActionManager 实例
        action_manager.start()  # 启动 100Hz 控制循环守护线程
        logger.info("[ActionManager] 已启动（100Hz 心跳维持）")  # 记录日志
        
        # 启动键盘急停监听线程
        start_keyboard_listener(action_manager, g1)  # 绑定 Space 键为急停
        logger.info("[EmergencyStop] 键盘急停监听已启动（按 Space 键紧急停止）")
    else:
        logger.warning("[ActionManager] 未启动（G1 客户端未就绪）")
    
    # 全局停止事件（用于 Ctrl+C 退出）
    global_stop_event = threading.Event()
    
    # ===================== 音频设备初始化（重连循环外，只初始化一次）=====================
    # 这样可以避免重连时 Linux 设备索引漂移问题
    import pyaudio  # 导入 PyAudio
    
    logger.info("[Audio] 初始化音频设备...")
    
    # 创建 PyAudio 实例
    global_pya = pyaudio.PyAudio()
    
    # 查找 PulseAudio hostapi
    pulse_hostapi = None
    for i in range(global_pya.get_host_api_count()):
        api_info = global_pya.get_host_api_info_by_index(i)
        if api_info['type'] == pyaudio.paInDevelopment:  # paInDevelopment = 2 可能是 PulseAudio
            if 'pulse' in api_info['name'].lower():
                pulse_hostapi = i
                logger.info(f"[Audio] 找到 PulseAudio hostapi: {i} ({api_info['name']})")
                break
    
    # 如果有 PulseAudio，尝试使用它
    if pulse_hostapi is not None:
        logger.info(f"[Audio] 尝试使用 PulseAudio hostapi: {pulse_hostapi}")
    
    # 列出所有音频设备，帮助调试
    logger.info("[Audio] 可用音频输入设备:")
    default_input_device = None
    for i in range(global_pya.get_device_count()):
        dev_info = global_pya.get_device_info_by_index(i)
        if dev_info['maxInputChannels'] > 0:  # 只显示输入设备
            is_default = "(默认)" if i == global_pya.get_default_input_device_info()['index'] else ""
            logger.info(f"  [{i}] {dev_info['name']} {is_default}")
            if default_input_device is None:
                default_input_device = i
    
    # 从环境变量获取麦克风设备索引
    mic_device_index = os.getenv("MIC_DEVICE_INDEX", None)  # 麦克风设备索引
    if mic_device_index is not None:
        mic_device_index = int(mic_device_index)
        logger.info(f"[Audio] 使用指定麦克风设备索引: {mic_device_index}")
    else:
        logger.info("[Audio] 使用默认麦克风设备")
    
    # 创建全局麦克风流
    try:
        global_mic_stream = global_pya.open(
            format=pyaudio.paInt16,  # 16位 PCM 格式
            channels=1,  # 单声道
            rate=48000,  # 48kHz 采样率（与麦克风匹配）
            input=True,  # 输入流
            input_device_index=mic_device_index,  # 指定设备索引（None 表示默认）
            frames_per_buffer=MIC_CHUNK_FRAMES,  # 每次读取 3200 帧(约 200ms)
        )
    except Exception as mic_err:
        logger.warning(f"[Audio] 麦克风打开失败，尝试使用 PulseAudio: {mic_err}")
        # 如果直接打开失败，尝试使用 PulseAudio 设备
        try:
            global_mic_stream = global_pya.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=48000,
                input=True,
                input_device_index=global_pya.get_default_input_device_info()['index'],
                frames_per_buffer=MIC_CHUNK_FRAMES,
            )
            logger.info("[Audio] 麦克风已使用默认设备打开 (48000Hz)")
        except Exception as e2:
            logger.error(f"[Audio] 麦克风打开最终失败: {e2}")
            global_mic_stream = None
    logger.info("[Audio] 麦克风流已创建")
    
    # 导入 B64PCMPlayer (确保这里可见)
    from omni_callback import B64PCMPlayer
    
    # 创建全局播放器
    logger.info("[Audio] 初始化播放器...")
    global_player = B64PCMPlayer(global_pya, sample_rate=24000, chunk_size_ms=100)
    logger.info("[Audio] 播放器已创建")
    
    # ===================== 摄像头初始化（重连循环外，只初始化一次）=====================
    global_cam = None
    if cv2 is not None:
        cam_id = int(os.getenv("CAMERA_ID", "0"))  # 摄像头设备 ID
        
        # 尝试打开摄像头
        global_cam = cv2.VideoCapture(cam_id)
        if global_cam.isOpened():
            logger.info(f"[Camera] 摄像头已打开: id={cam_id}")
        else:
            logger.warning(f"[Camera] 无法打开摄像头: id={cam_id}")
            global_cam = None
    
    # 重连配置
    RECONNECT_DELAY = 3  # 重连延迟（秒）
    MAX_RECONNECT_ATTEMPTS = 0  # 最大重连次数（0 表示无限重连）
    reconnect_count = 0  # 重连计数器
    
    # 信号处理函数
    def _sigint(sig, frame):
        """Ctrl+C 信号处理函数，优雅退出程序"""
        print("\n[System] Ctrl+C pressed, closing ...")
        global_stop_event.set()  # 设置全局停止事件
        
        # 停止 ActionManager 控制循环
        if action_manager:
            with contextlib.suppress(Exception):
                action_manager.stop()
                print("[ActionManager] 已停止")
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, _sigint)  # 注册信号处理

    print("===== Omni Realtime 已启动（支持自动重连）=====")
    print("Press Ctrl+C to stop.")
    
    # ===================== 自动重连主循环 =====================
    while not global_stop_event.is_set():
        callback = None
        conversation = None
        session_stop_event = threading.Event()  # 本次会话的停止事件
        send_lock = threading.Lock()  # 发送锁
        cam_thread = None
        
        try:
            # 创建回调处理器（注入全局音频设备，避免重连时设备索引漂移）
            callback = OmniCallback(
                flag_getter=get_flag,  # 传入 flag 获取函数
                flag_setter=set_flag,  # 传入 flag 设置函数
                g1_client=g1,  # 传入 G1 客户端
                g1_arm_client=g1_arm,  # 传入 G1 手臂客户端
                pya=global_pya,  # 注入全局 PyAudio 实例
                mic_stream=global_mic_stream,  # 注入全局麦克风流
                player=global_player  # 注入全局播放器实例
            )
            
            # 注入 ActionManager
            if action_manager:
                callback.action_manager = action_manager
            
            # 创建 Omni 对话实例
            conversation = OmniRealtimeConversation(model=model, callback=callback, url=url)
            callback.conversation = conversation  # 将 conversation 实例绑定到 callback
            
            # 连接 WebSocket
            if reconnect_count > 0:
                logger.info(f"[Omni] 正在重连（第 {reconnect_count} 次）...")
            else:
                logger.info("[Omni] connecting ...")
            
            conversation.connect()  # 建立连接
            
            # 更新会话配置
            conversation.update_session(
                output_modalities=[MultiModality.AUDIO, MultiModality.TEXT],  # 输出模态
                voice=voice,  # 语音
                input_audio_format=AudioFormat.PCM_16000HZ_MONO_16BIT,  # 输入音频格式
                output_audio_format=AudioFormat.PCM_24000HZ_MONO_16BIT,  # 输出音频格式
                enable_input_audio_transcription=True,  # 启用输入音频转写
                input_audio_transcription_model="gummy-realtime-v1",  # 转写模型
                enable_turn_detection=True,  # 启用轮次检测
                turn_detection_type="server_vad",  # 使用服务端 VAD
                turn_detection_config={  # VAD 配置
                    "silence_duration_ms": 600000,  # 静音超时 10 分钟
                    "prefix_padding_ms": 300,  # 前缓冲 300ms
                    "threshold": 0.5  # VAD 阈值
                },
                instructions=instructions,  # 系统指令
            )
            
            # 启动摄像头线程（使用全局摄像头实例，避免重连时设备索引漂移）
            cam_thread = threading.Thread(
                target=start_camera_loop, 
                args=(conversation, session_stop_event, send_lock, global_cam),  # 传入全局摄像头
                daemon=True
            )
            cam_thread.start()  # 启动线程
            
            if reconnect_count > 0:
                logger.info(f"[Omni] 重连成功！（第 {reconnect_count} 次）")
            
            # 重置重连计数（连接成功后）
            reconnect_count = 0
            
            # 本次会话的主循环：读取麦克风数据并发送
            while not global_stop_event.is_set():
                # 检查连接状态
                if not callback._connection_alive:  # 连接已断开
                    logger.warning("[System] WebSocket 连接已断开，准备重连...")
                    break  # 退出内层循环，触发重连
                
                if not callback.mic_stream:  # 麦克风流未就绪
                    time.sleep(0.05)
                    continue

                try:
                    # 读取麦克风数据
                    if callback.mic_stream.is_active():
                        audio_data = callback.mic_stream.read(MIC_CHUNK_FRAMES, exception_on_overflow=False)
                    else:
                        raise OSError("Stream not active")
                except Exception as e:
                    logger.error(f"[Mic] 读取麦克风失败: {e}")
                    
                    # 尝试重建麦克风流
                    logger.info("[Mic] 尝试重建麦克风流...")
                    try:
                        # 尝试关闭旧流
                        with contextlib.suppress(Exception):
                            global_mic_stream.stop_stream()
                            global_mic_stream.close()
                        
                        # 重新打开流
                        global_mic_stream = global_pya.open(
                            format=pyaudio.paInt16,  # 16位 PCM 格式
                            channels=1,  # 单声道
                            rate=16000,  # 16kHz 采样率
                            input=True,  # 输入流
                            input_device_index=mic_device_index,  # 指定设备索引
                            frames_per_buffer=MIC_CHUNK_FRAMES,  # 每次读取 3200 帧
                        )
                        # 更新 callback 中的流引用
                        callback.mic_stream = global_mic_stream
                        logger.info("[Mic] 麦克风流重建成功")
                        continue  # 重试本次循环
                    except Exception as recreate_e:
                        logger.error(f"[Mic] 麦克风流重建失败: {recreate_e}")
                        break  # 如果重建也失败，则退出触发完整重连

                # AEC 处理
                if aec_processor and hasattr(aec_processor, 'enabled') and aec_processor.enabled:
                    frame_size_bytes = 320 * 2  # 640 bytes per frame
                    cleaned_chunks = []
                    
                    for i in range(0, len(audio_data), frame_size_bytes):
                        mic_frame = audio_data[i:i + frame_size_bytes]
                        
                        # 不足一帧，补零
                        if len(mic_frame) < frame_size_bytes:
                            mic_frame += b'\x00' * (frame_size_bytes - len(mic_frame))
                        
                        # 获取参考帧
                        ref_frame = b""
                        if callback.player:
                            ref_frame = callback.player.get_reference_frame(timeout=0.001)
                        
                        # 参考帧长度不足，补零
                        if len(ref_frame) < frame_size_bytes:
                            ref_frame += b'\x00' * (frame_size_bytes - len(ref_frame))
                        
                        # 执行 AEC
                        cleaned_frame = aec_processor.process(mic_frame, ref_frame)
                        cleaned_chunks.append(cleaned_frame)
                    
                    audio_data = b"".join(cleaned_chunks)

                # 发送音频
                try:
                    audio_b64 = base64.b64encode(audio_data).decode("ascii")
                    with send_lock:
                        conversation.append_audio(audio_b64)
                except Exception as e:
                    logger.error(f"[Audio] 发送音频失败: {e}")
                    break  # 发送失败，触发重连
                    
        except Exception as e:
            logger.error(f"[Session] 会话异常: {e}")
        
        finally:
            # 清理本次会话资源
            session_stop_event.set()  # 通知摄像头线程停止
            
            with contextlib.suppress(Exception):
                if conversation:
                    conversation.close()
            
            with contextlib.suppress(Exception):
                if callback and callback.player:
                    callback.player.shutdown()
            
            with contextlib.suppress(Exception):
                if callback and callback.mic_stream:
                    callback.mic_stream.close()
            
            with contextlib.suppress(Exception):
                if callback and callback.pya:
                    callback.pya.terminate()
        
        # 检查是否应该退出（而非重连）
        if global_stop_event.is_set():
            logger.info("[System] 收到退出信号，停止重连")
            break
        
        # 重连逻辑
        reconnect_count += 1
        
        # 检查最大重连次数
        if MAX_RECONNECT_ATTEMPTS > 0 and reconnect_count > MAX_RECONNECT_ATTEMPTS:
            logger.error(f"[Reconnect] 已达到最大重连次数 ({MAX_RECONNECT_ATTEMPTS})，退出程序")
            break
        
        logger.info(f"[Reconnect] 将在 {RECONNECT_DELAY} 秒后尝试重连...")
        time.sleep(RECONNECT_DELAY)  # 等待后重连
    
    logger.info("[System] 程序已退出")


# ===================== 入口点 =====================
if __name__ == "__main__":
    try:
        if UNITREE_AVAILABLE:
            # 1. 初始化通道
            net_if = sys.argv[1] if len(sys.argv) >= 2 else "eth0"
            print(f"[G1] 初始化通道，网卡：{net_if}")
            ChannelFactoryInitialize(0, net_if)

            # 2. 实例化 G1 LocoClient
            try:
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
                
                # 发送零速度指令以激活控制权
                print("[G1] 默认已站立，发送零速度指令以激活控制权...")
                g1.Move(0.0, 0.0, 0.0)
                
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