# -*- coding: utf-8 -*-
"""
Omni 实时对话回调处理器

功能：
1. 处理 WebSocket 连接生命周期
2. 接收并处理 ASR 转写结果
3. 管理响应模式（speaking/idle）
4. 触发 Function Calling 和本地关键词匹配

创建时间: 2026-01-29
"""

import threading  # 导入线程模块
import time  # 导入时间模块
import json  # 导入 JSON 模块
import contextlib  # 导入上下文管理模块
import logging  # 导入日志模块
import pyaudio  # 导入音频处理模块

from dashscope.audio.qwen_omni import OmniRealtimeCallback  # 导入 Omni 回调基类

from audio_player import B64PCMPlayer  # 导入音频播放器
from command_detector import (
    is_interrupt_command,
    detect_self_introduction,
    is_complex_command,
    try_execute_g1_by_local_keywords
)  # 导入命令检测函数
from api_init import call_qwen_for_tool_use  # 导入工具调用函数
from bridge import execute_tool_call  # 导入 Bridge 层工具执行函数
from tool_schema import ROBOT_TOOLS  # 导入机器人控制工具定义
from config import FUNCTION_CALLING_CONFIG  # 导入 Function Calling 配置

# 配置日志记录器
logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器

# 麦克风采样参数
MIC_CHUNK_FRAMES = 3200  # 16kHz 下约 200ms（frames_per_buffer）


class OmniCallback(OmniRealtimeCallback):
    """
    Omni 实时对话回调处理器
    
    处理 WebSocket 事件和音频数据流
    """
    
    def __init__(self, flag_getter, flag_setter, g1_client=None, g1_arm_client=None,
                 pya=None, mic_stream=None, player=None):
        """
        初始化回调处理器
        
        Args:
            flag_getter: 获取 flag 状态的函数
            flag_setter: 设置 flag 状态的函数
            g1_client: G1 机器人客户端实例
            g1_arm_client: G1 手臂动作客户端实例
            pya: 外部注入的 PyAudio 实例（可选，避免重连时重建）
            mic_stream: 外部注入的麦克风流（可选，避免重连时重建）
            player: 外部注入的播放器实例（可选，避免重连时重建）
        """
        super().__init__()  # 调用父类初始化
        self.conversation = None  # Omni 对话实例
        self.pya = pya  # PyAudio 实例（可从外部注入）
        self.mic_stream = mic_stream  # 麦克风输入流（可从外部注入）
        self.player = player  # 音频播放器实例（可从外部注入）
        self.action_manager = None  # ActionManager 实例（依赖注入）
        
        # 标记音频设备是否为外部注入（重连时不销毁）
        self._audio_externally_managed = (pya is not None)  # 外部管理标志
        
        # Flag 控制函数
        self._get_flag = flag_getter  # 获取 flag 的函数
        self._set_flag = flag_setter  # 设置 flag 的函数
        
        # G1 客户端引用
        self.g1_client = g1_client  # G1 机器人客户端
        self.g1_arm_client = g1_arm_client  # G1 手臂动作客户端

        self._respond_lock = threading.Lock()  # 响应状态锁
        self._responding = False  # 是否正在响应

        # 响应序号：避免旧 response 的收尾线程影响新一轮
        self._seq_lock = threading.Lock()  # 序号锁
        self._resp_seq = 0  # 响应序号

        # 打断后：丢弃当前 response 后续的音频 delta（直到 done）
        self._drop_lock = threading.Lock()  # 丢弃状态锁
        self._drop_output = False  # 是否丢弃输出
        
        # 冷却时间：机器人说完话后的一小段时间内忽略 ASR（防止回声自激）
        self._cool_lock = threading.Lock()  # 冷却状态锁
        self._last_speak_end_time = 0.0  # 上次说话结束时间
        
        # 连接状态标志：用于检测连接是否断开
        self._connection_alive = True  # WebSocket 连接活跃状态
        
        # 保活回调：由 main 函数注入，用于更新活动时间
        self._update_activity_time = None  # 活动时间更新函数（外部注入）

    def _inc_seq(self) -> int:
        """增加响应序号并返回新序号"""
        with self._seq_lock:  # 获取序号锁
            self._resp_seq += 1  # 增加序号
            return self._resp_seq  # 返回新序号

    def _get_seq(self) -> int:
        """获取当前响应序号"""
        with self._seq_lock:  # 获取序号锁
            return self._resp_seq  # 返回当前序号

    def _set_drop_output(self, v: bool):
        """设置是否丢弃输出"""
        with self._drop_lock:  # 获取丢弃状态锁
            self._drop_output = bool(v)  # 设置丢弃状态

    def _should_drop_output(self) -> bool:
        """检查是否应该丢弃输出"""
        with self._drop_lock:  # 获取丢弃状态锁
            return bool(self._drop_output)  # 返回丢弃状态

    def is_responding(self) -> bool:
        """检查是否正在响应"""
        with self._respond_lock:  # 获取响应状态锁
            return bool(self._responding)  # 返回响应状态

    def _enter_response_mode(self):
        """进入响应模式"""
        with self._respond_lock:  # 获取响应状态锁
            if self._responding:  # 如果已在响应模式
                return  # 直接返回
            self._responding = True  # 设置响应状态

        self._set_flag(1, reason="model_output_start")  # 设置 flag
        self._inc_seq()  # 增加序号
        
        # 更新活动时间（收到响应表示连接活跃）
        if callable(self._update_activity_time):  # 检查回调是否已注入
            self._update_activity_time()  # 更新活动时间

    def _exit_response_mode_if_seq(self, seq: int, reason: str):
        """如果序号匹配则退出响应模式"""
        if seq != self._get_seq():  # 检查序号是否匹配
            return  # 不匹配则返回
        with self._respond_lock:  # 获取响应状态锁
            self._responding = False  # 清除响应状态
        self._set_flag(0, reason=reason)  # 清除 flag

    def _force_exit_response_mode(self, reason: str):
        """
        强制退出响应模式，并将 seq+1，使旧的收尾线程失效
        """
        with self._respond_lock:  # 获取响应状态锁
            self._responding = False  # 清除响应状态
        self._inc_seq()  # 增加序号使旧线程失效
        self._set_flag(0, reason=reason)  # 清除 flag
        # 强制退出时也更新结束时间（防止打断后的余音触发）
        with self._cool_lock:  # 获取冷却状态锁
            self._last_speak_end_time = time.time()  # 记录结束时间

    def _ensure_dict(self, message):
        """确保消息为字典格式"""
        if isinstance(message, dict):  # 如果已是字典
            return message  # 直接返回
        if isinstance(message, str):  # 如果是字符串
            with contextlib.suppress(Exception):  # 忽略解析异常
                return json.loads(message)  # 尝试解析 JSON
        return {}  # 返回空字典

    def on_open(self) -> None:
        """WebSocket 连接打开回调"""
        logger.info("[Omni] connection opened; init microphone & player")

        # 如果音频设备未从外部注入，则在此初始化
        if self.pya is None:
            self.pya = pyaudio.PyAudio()
            self._audio_externally_managed = False
        
        # 如果麦克风流未初始化
        if self.mic_stream is None:
            import os
            
            # 查找可用的麦克风设备
            mic_device_index = None
            pulse_device_index = None
            
            for i in range(self.pya.get_device_count()):
                info = self.pya.get_device_info_by_index(i)
                # 优先找 PulseAudio 设备
                if info['maxInputChannels'] > 0:
                    if 'pulse' in info['name'].lower():
                        pulse_device_index = i
                        logger.info(f"[Omni] 找到 Pulse 设备: {i} ({info['name']})")
                    # 找 Jieli USB 麦克风
                    if 'jieli' in info['name'].lower() and mic_device_index is None:
                        mic_device_index = i
                        logger.info(f"[Omni] 找到 Jieli 麦克风: {i} ({info['name']})")
            
            # 优先使用 Pulse 设备
            if pulse_device_index is not None:
                device_to_use = pulse_device_index
            elif mic_device_index is not None:
                device_to_use = mic_device_index
            else:
                # 使用系统默认
                try:
                    device_to_use = self.pya.get_default_input_device_info()['index']
                    logger.info(f"[Omni] 使用系统默认设备: {device_to_use}")
                except:
                    device_to_use = None
            
            try:
                if device_to_use is not None:
                    self.mic_stream = self.pya.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        input_device_index=device_to_use,
                        frames_per_buffer=MIC_CHUNK_FRAMES,
                    )
                    logger.info(f"[Omni] 麦克风流已创建 (设备: {device_to_use})")
                else:
                    # 尝试不指定设备
                    self.mic_stream = self.pya.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        frames_per_buffer=MIC_CHUNK_FRAMES,
                    )
                    logger.info("[Omni] 麦克风已创建 (使用自动选择)")
            except Exception as e:
                logger.error(f"[Omni] 麦克风创建失败: {e}")
                # 最后尝试：只打开流，不指定设备
                try:
                    self.mic_stream = self.pya.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        frames_per_buffer=MIC_CHUNK_FRAMES,
                    )
                    logger.info("[Omni] 麦克风已使用后备方式创建")
                except Exception as e2:
                    logger.error(f"[Omni] 麦克风最终失败: {e2}")
                    self.mic_stream = None
        
        # 播放器每次都需要重建（因为它依赖于当前会话的输出流）
        if self.player is None:  # 只有在没有播放器时才创建
            self.player = B64PCMPlayer(self.pya, sample_rate=24000, chunk_size_ms=100)  # 创建播放器

        self._set_flag(0, reason="init_ready")  # 初始化完成
        
        # 重置连接状态
        self._connection_alive = True  # 标记连接活跃

    def on_close(self, close_status_code, close_msg) -> None:
        """WebSocket 连接关闭回调"""
        logger.info(f"[Omni] connection closed: code={close_status_code}, msg={close_msg}")  # 记录日志
        self._cleanup()  # 清理资源
        self._connection_alive = False  # 标记连接已断开，触发主循环退出

    def _cleanup(self):
        """
        清理音频资源
        
        注意：如果音频设备是外部注入的（_audio_externally_managed=True），
        则不关闭相关资源，以避免重连时设备索引漂移。
        """
        # 只有在音频设备由内部管理时才销毁
        if not self._audio_externally_managed:  # 检查是否为外部管理
            with contextlib.suppress(Exception):  # 忽略异常
                if self.player:  # 如果播放器存在
                    self.player.shutdown()  # 关闭播放器
                    self.player = None
            with contextlib.suppress(Exception):  # 忽略异常
                if self.mic_stream:  # 如果麦克风流存在
                    self.mic_stream.close()  # 关闭麦克风流
                    self.mic_stream = None  # 清空引用
            with contextlib.suppress(Exception):  # 忽略异常
                if self.pya:  # 如果 PyAudio 存在
                    self.pya.terminate()  # 终止 PyAudio
                    self.pya = None  # 清空引用

    def _try_cancel_server_response(self):
        """
        尝试取消服务端响应
        
        文档支持 client event: response.cancel。
        SDK 若暴露 cancel_response()，则调用；否则忽略。
        """
        if not self.conversation:  # 如果对话实例不存在
            return  # 直接返回
        fn = getattr(self.conversation, "cancel_response", None)  # 获取取消方法
        if callable(fn):  # 如果方法存在
            with contextlib.suppress(Exception):  # 忽略异常
                fn()  # 调用取消方法
                logger.info("[Omni] response.cancel sent")  # 记录日志
        # SDK 不一定暴露该方法；不强依赖

    def _interrupt_playback(self, transcript: str):
        """
        打断当前播放
        
        Args:
            transcript: 触发打断的转写文本
        """
        logger.info(f"[ASR-INTERRUPT] {transcript}")  # 记录打断日志
        self._set_drop_output(True)  # 设置丢弃输出

        # 1) 本地立刻停（清队列+重置输出流）
        if self.player:  # 如果播放器存在
            with contextlib.suppress(Exception):  # 忽略异常
                self.player.interrupt(reset_stream=True)  # 打断播放

        # 2) 尝试让服务端也取消当前 response
        self._try_cancel_server_response()  # 尝试取消服务端响应

        # 3) 立即退出 responding，允许继续对话
        self._force_exit_response_mode(reason="interrupted_by_user")  # 强制退出响应模式

    def _execute_tool_command(self, transcript: str):
        """
        执行工具调用逻辑 (Function Calling)
        
        Args:
            transcript: 用户语音转写文本
        """
        # 检查功能开关
        if not FUNCTION_CALLING_CONFIG.get("ENABLED", True):  # 如果未启用
            return  # 直接返回

        try:
            # 调用 Qwen API
            logger.info(f"[G1-Tool] 开始处理指令: {transcript}")  # 记录日志
            tool_calls = call_qwen_for_tool_use(transcript, ROBOT_TOOLS)  # 调用 LLM
            
            if tool_calls:  # 如果有工具调用
                for tool_call in tool_calls:  # 遍历工具调用
                    result = execute_tool_call(
                        tool_name=tool_call["name"],  # 工具名称
                        params=tool_call["arguments"],  # 工具参数
                        action_manager=self.action_manager,  # 动作管理器
                        g1_client=self.g1_client,  # G1 客户端
                        g1_arm_client=self.g1_arm_client  # G1 手臂客户端
                    )
                    if result["status"] == "success":  # 如果成功
                        logger.info(f"[G1] 工具调用成功: {result['message']}")  # 记录日志
                    elif result["status"] == "success_with_warning":  # 如果成功但有警告
                        logger.warning(f"[G1] 工具调用成功（有警告）: {result['message']} | {result.get('warning', '')}")  # 记录警告
                    else:  # 如果失败
                        logger.error(f"[G1] 工具调用失败: {result['message']}")  # 记录错误
                
                # 语音确认
                with contextlib.suppress(Exception):  # 忽略异常
                    self.conversation.create_response(
                        instructions=(
                            f"用户下达了动作指令：{transcript}。"
                            "请用一句简短中文确认你已执行，不要解释原理。"
                        )
                    )  # 创建确认响应
            else:
                logger.debug(f"[G1] 未生成工具调用: {transcript}")  # 记录调试信息

        except Exception as e:  # 捕获异常
            logger.error(f"[G1] 工具执行异常: {e}")  # 记录错误

    def on_event(self, message) -> None:
        """
        处理 WebSocket 事件
        
        Args:
            message: 事件消息
        """
        resp = self._ensure_dict(message)  # 转换为字典格式
        etype = resp.get("type", "")  # 获取消息类型
        
        # ========= 自我介绍检测与自动挥手 =========
        if etype == "response.audio_transcript.delta":  # 音频转写文本增量
            delta_text = resp.get("delta", "")  # 获取文本增量
            if delta_text and detect_self_introduction(delta_text):  # 检测是否为自我介绍
                logger.info(f"[Callback] 检测到自我介绍关键词：{delta_text[:50]}...")  # 记录日志
                
                # 延迟 0.5 秒后执行挥手（与语音播放同步）
                def delayed_wave():
                    time.sleep(0.5)  # 延迟 0.5 秒
                    if self.g1_arm_client:  # 检查手臂客户端是否可用
                        try:
                            self.g1_arm_client.ExecuteAction(25)  # 执行 face wave 动作
                            logger.info("[Callback] 自我介绍自动挥手执行成功")  # 记录成功日志
                        except Exception as e:  # 捕获执行异常
                            logger.error(f"[Callback] 自我介绍自动挥手失败: {e}")  # 记录错误日志
                    else:
                        logger.warning("[Callback] g1_arm 客户端未初始化，自动挥手跳过")  # 记录警告
                
                # 在独立线程中执行，不阻塞音频播放
                wave_thread = threading.Thread(target=delayed_wave, daemon=True)  # 创建守护线程
                wave_thread.start()  # 启动线程

        if etype == "session.created":  # 会话创建事件
            sid = (resp.get("session") or {}).get("id", "")  # 获取会话 ID
            logger.info(f"[Omni] session.created: {sid}")  # 记录日志
            return

        if etype == "session.updated":  # 会话更新事件
            logger.info("[Omni] session.updated")  # 记录日志
            return

        # 输入语音转写完成
        if etype == "conversation.item.input_audio_transcription.completed":
            transcript = (resp.get("transcript") or "").strip()  # 获取转写文本
            if not transcript:  # 如果文本为空
                return  # 直接返回

            # 若当前模型正在输出/播放：
            # 1. 监听"打断类命令"（强打断）
            # 2. 监听"复杂控制指令"（如"前进一米"），视为打断并执行
            if self.is_responding() or self._get_flag() == 1:
                # 检测是否为复杂指令
                is_complex_cmd = is_complex_command(transcript)  # 使用命令检测函数

                if is_interrupt_command(transcript) or is_complex_cmd:  # 如果是打断或复杂指令
                    logger.info(f"[ASR-Interrupt] 触发打断 (Complex={is_complex_cmd}): {transcript}")  # 记录日志
                    self._interrupt_playback(transcript)  # 打断播放
                    
                    # 安全修复：如果包含停止意图，立即停止机器人运动
                    stop_keywords = ["停", "急停", "别动", "站住"]  # 停止关键词
                    is_stop = any(x in transcript for x in stop_keywords)  # 检测停止意图
                    
                    if is_stop:  # 如果包含停止意图
                        logger.warning(
                            f"[Safety] 检测到打断指令包含停止意图: {transcript}，"
                            "强制停止运动"
                        )
                        if self.action_manager:  # 如果 action_manager 存在
                            if "急停" in transcript:  # 如果是急停
                                self.action_manager.emergency_stop()  # 执行急停
                                logger.warning("[Safety] 触发 ActionManager.emergency_stop()")
                            else:
                                self.action_manager.set_idle()  # 设置空闲
                                logger.info("[Safety] 触发 ActionManager.set_idle()")
                    
                    # 修复：如果是复杂指令且不是纯粹的停止，执行工具调用
                    if is_complex_cmd and not is_stop:  # 复杂指令且非停止
                        logger.info(f"[G1-Interrupt] 这是一个复杂动作指令，启动执行线程: {transcript}")
                        threading.Thread(
                            target=self._execute_tool_command, 
                            args=(transcript,), 
                            daemon=True
                        ).start()  # 启动执行线程
                else:
                    # 非打断命令：只打印（可按需关闭）
                    print(f"[ASR-IGNORED] {transcript}")  # 打印忽略的文本
                return

            # 空闲态：正常打印 + 本地动作指令
            
            # 检查冷却时间（防止回声自激）
            with self._cool_lock:  # 获取冷却状态锁
                cool_time = 1.5  # 1.5秒冷却期
                if time.time() - self._last_speak_end_time < cool_time:  # 如果在冷却期内
                    logger.info(f"[ASR-COOLED] 处于回声冷却期，忽略输入: {transcript}")  # 记录日志
                    return  # 返回

            logger.info(f"[ASR] {transcript}")  # 记录 ASR 结果
            
            # 更新活动时间（用户说话表示连接活跃）
            if callable(self._update_activity_time):  # 检查回调是否已注入
                self._update_activity_time()  # 更新活动时间

            def _do_g1():
                """执行 G1 动作的内部函数"""
                try:
                    t = (transcript or "").strip()  # 获取文本
                    
                    # 检测复杂指令
                    if is_complex_command(t):  # 如果是复杂指令
                        logger.info(f"[G1] 检测到复杂指令，跳过关键词匹配: {transcript}")
                        self._execute_tool_command(transcript)  # 执行工具调用
                        return
                    
                    # 简单指令使用本地关键词匹配（快速路径）
                    executed = try_execute_g1_by_local_keywords(
                        transcript, 
                        self.action_manager,
                        self.g1_arm_client
                    )
                    if executed:  # 如果关键词匹配成功
                        logger.info("[G1] 本地关键词指令已执行")  # 记录日志
                        with contextlib.suppress(Exception):  # 忽略异常
                            self.conversation.create_response(
                                instructions=(
                                    f"用户下达了动作指令：{transcript}。"
                                    "请用一句简短中文确认你已执行，不要解释原理。"
                                )
                            )  # 创建确认响应
                        return
                    
                    # 关键词未匹配，尝试调用 LLM 工具推理
                    self._execute_tool_command(transcript)  # 执行工具调用
                    
                except Exception as e:  # 捕获异常
                    logger.error(f"[G1] 执行失败：{e}")  # 记录错误

            threading.Thread(target=_do_g1, daemon=True).start()  # 启动执行线程
            return

        # ====== 模型开始输出（文本/音频任一到来）-> flag=1 ======
        if etype == "response.audio_transcript.delta":  # 音频转写增量
            delta = resp.get("delta", "")  # 获取增量
            if delta:  # 如果有增量
                if not self._should_drop_output():  # 如果不应丢弃
                    self._enter_response_mode()  # 进入响应模式
                    print(delta, end="", flush=True)  # 打印增量
            return

        if etype == "response.audio.delta":  # 音频增量
            b64_pcm = resp.get("delta", "")  # 获取 Base64 PCM 数据
            if b64_pcm:  # 如果有数据
                if not self._should_drop_output():  # 如果不应丢弃
                    self._enter_response_mode()  # 进入响应模式
                    if self.player:  # 如果播放器存在
                        self.player.add_data(b64_pcm)  # 添加数据到播放器
            return

        if etype == "response.audio_transcript.done":  # 转写完成
            print("\n[Omni] transcript done")  # 打印完成信息
            return

        # 兼容：音频生成结束（文档有 response.audio.done）
        if etype == "response.audio.done":  # 音频生成完成
            print("\n[Omni] response.audio.done")  # 打印完成信息
            return

        # ====== 服务端输出结束：未被打断时，等本地播放 idle 后再 flag=0 ======
        if etype == "response.done":  # 响应完成
            rid = ""  # 初始化响应 ID
            with contextlib.suppress(Exception):  # 忽略异常
                rid = self.conversation.get_last_response_id()  # 获取响应 ID
            print(f"\n[Omni] response.done (id={rid})")  # 打印完成信息

            # 若刚发生打断：直接恢复输入，不再等 idle（播放器已被清空）
            if self._should_drop_output():  # 如果应丢弃输出
                self._set_drop_output(False)  # 清除丢弃状态
                self._force_exit_response_mode(reason="server_done_after_interrupt")  # 强制退出
                return

            seq = self._get_seq()  # 获取当前序号

            def _finish_after_local_playback(local_seq: int):
                """等待本地播放完成后退出响应模式"""
                if self.player:  # 如果播放器存在
                    self.player.wait_until_idle(timeout=10.0)  # 等待空闲
                self._exit_response_mode_if_seq(local_seq, reason="local_playback_end")  # 退出响应模式
                # 更新说话结束时间，开启冷却窗口
                with self._cool_lock:  # 获取冷却状态锁
                    self._last_speak_end_time = time.time()  # 记录结束时间

            threading.Thread(
                target=_finish_after_local_playback, args=(seq,), daemon=True
            ).start()  # 启动等待线程
            return


# 导出公共接口
__all__ = ['OmniCallback', 'MIC_CHUNK_FRAMES']  # 定义模块导出列表
