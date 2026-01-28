# Unitree G1 具身智能控制系统技术开发文档

| 文档信息     | 内容                              |
| :----------- | :-------------------------------- |
| **项目名称** | Unitree G1 Embodied AI Controller |
| **版本**     | v1.0                              |
| **最后更新** | 2026-01-22                        |
| **状态**     | 实机验证阶段                      |

---

## 1. 项目概述

本项目旨在构建一个**“大脑”与“小脑”协同**的具身智能控制架构。
- **大脑 (Brain)**：利用多模态大模型 (LLM/VLM，如 Qwen-Omni) 进行环境感知、语义理解与高层决策。
- **小脑 (Cerebellum)**：利用 Unitree SDK2 执行底层运动控制、保持平衡与执行精确动作。

该系统实现了从“自然语言/视觉输入”到“机器人物理运动”的完整闭环，解决了大模型推理延迟与机器人实时控制要求之间的矛盾。

---

## 2. 系统架构

### 2.1 三层控制架构

系统采用分层设计，确保决策的灵活性与控制的稳定性：

```mermaid
graph TD
    User[用户指令/环境输入] --> Brain
    
    subgraph "大脑层 (Brain Layer)"
        Brain[LLM/VLM (Qwen-Omni)]
        Info[环境感知 & 意图理解]
        Brain -->|JSON 指令| Bridge
    end
    
    subgraph "转换层 (Bridge Layer)"
        Bridge[Bridge Module]
        Parser[JSON 解析 & 参数验证]
        Safety[前置安全检查]
        Bridge -->|Python 方法调用| Cerebellum
    end
    
    subgraph "小脑层 (Cerebellum Layer)"
        Cerebellum[ActionManager]
        Loop[100Hz 控制循环]
        SDK[Unitree SDK2 (G1 LocoClient)]
        Robot[G1 机器人硬件]
        
        Cerebellum -->|Update Target v| Loop
        Loop -->|Move(vx, vy, yaw)| SDK
        SDK -->|DDS 通信| Robot
    end
```

### 2.2 核心模块说明

| 模块                        | 路径                            | 功能描述                                                                                |
| :-------------------------- | :------------------------------ | :-------------------------------------------------------------------------------------- |
| **VoiceInteraction**        | `VoiceInteraction/`             | 核心交互与逻辑控制包                                                                    |
| `multimodal_interaction.py` | `.../multimodal_interaction.py` | **主程序**。负责建立与 LLM 的实时会话，处理多模态输入输出，协调各子模块。               |
| `action_manager.py`         | `.../action_manager.py`         | **控制核心**。100Hz 守护线程，负责维持 SDK 心跳，实现决策与执行的频率解耦。             |
| `aec_processor.py`          | `.../aec_processor.py`          | **回声消除**。封装 speexdsp 库，实现音频回声消除，解决全双工自激问题。                  |
| `bridge.py`                 | `.../bridge.py`                 | **指令桥接**。负责将 LLM 的 Function Calling (JSON) 转换为具体的 ActionManager 调用。   |
| `tool_schema.py`            | `.../tool_schema.py`            | **工具定义**。定义了 LLM 可调用的工具集合 (Schema)，如 `move_robot`, `emergency_stop`。 |
| `config.py`                 | `.../config.py`                 | **配置管理**。包含安全限制参数（最大速度、角度）及系统配置（含 AEC_CONFIG）。           |
| `emergency_stop.py`         | `.../emergency_stop.py`         | **安全保障**。独立的键盘监听线程，提供物理急停功能。                                    |

---

## 3. 关键技术决策与实现详解

### 3.1 控制频率解耦 (ActionManager)

**背景**：
大模型推理通常需要 1-5 秒，而机器人底层控制要求极高的实时性（通常需 >20Hz 心跳）。若直接由 LLM 回调驱动 SDK，会导致 Watchdog Timeout，使机器人锁死。

**解决方案**：
引入 `ActionManager` 作为中间层，实现**决策频率与控制频率的解耦**。

*   **实现机制**：
    *   独立守护线程运行 `_control_loop()`。
    *   使用 `time.sleep()` 配合绝对时间锚点（Monotonic Time），强制维持 **100Hz** 控制频率。
    *   维护线程安全的 `target_velocity` 状态变量。
    *   LLM 仅需异步更新 `target_velocity`，不阻塞控制循环。
    *   通过 G1 专用 `LocoClient.Move()` 接口发送控制指令（而非通用的 `SportClient`）。

*   **代码特征**：
    *   使用 `threading.Lock` 保护共享状态。
    *   即使 LLM 卡顿，机器人也会平滑地维持上一指令或进入安全状态，不会触发底层超时。

### 3.2 从关键词升级为 Function Calling

**背景**：
早期的 `try_execute_g1_by_local_keywords` 仅能通过正则匹配简单指令（“前进”、“停止”），无法处理复杂语义（如“慢慢向左转 30 度”、“向前走 2 米”）。

**解决方案**：
集成 OpenAI 格式的 **Function Calling**。

*   **Tool Schema 定义 (`tool_schema.py`)**：
    *   `move_robot(vx, vy, vyaw, duration)`: 精确控制移动向量和持续时间。
    *   `rotate_angle(angle)`: 原地旋转。
    *   `emergency_stop()`: 急停。
    
*   **混合路由策略 (`multimodal_interaction.py`)**：
    *   **Level 1 (快速响应)**：保留高频关键词（“停”、“别动”）的本地匹配，实现 <200ms 的极速打断。
    *   **Level 2 (智能决策)**：对于其他指令，调用 LLM 进行工具推理，支持复杂意图解析。

### 3.3 多重安全机制

**具身智能的首要原则是安全性**。系统实现了三道安全防线：

1.  **参数验证层 (`bridge.py` + `config.py`)**：
    *   在执行任何指令前，强制校验 `vx`, `vy`, `vyaw` 是否在安全范围内（如 `MAX_SAFE_SPEED = 1.0 m/s`）。
    *   超限参数会被自动截断并记录警告日志。

2.  **软件急停层 (`action_manager.py`)**：
    *   LLM 或关键词触发 `emergency_stop` 时，ActionManager 立即发送速度为 0 的指令，并切换机器人至**阻尼模式 (Damp)**。
    *   采用 **Double-Check Locking** 机制，防止急停指令在竞态条件下被旧的移动指令覆盖。

3.  **物理急停层 (`emergency_stop.py`)**：
    *   运行独立的键盘监听线程。
    *   只要按下 **Space (空格键)**，无视任何上层逻辑，直接强制覆盖控制信号，确保在系统失控时有人工接管能力。

### 3.4 音频回声消除（AEC）

**背景**：
在全双工对话模式下，机器人播放语音时麦克风会采集到扬声器的声音（回声），导致 ASR 可能将播放内容识别为用户指令，形成"自激"现象（机器人被自己控制）。

**解决方案**：
实现基于 speexdsp 的自适应回声消除系统。

*   **核心模块（`aec_processor.py`）**：
    *   **AECProcessor 类**：封装 `speexdsp.EchoCanceller`，提供帧级回声消除接口。
    *   **AudioResampler 类**：使用 `scipy.signal.resample` 将播放器的 24kHz 音频重采样到 16kHz，以匹配麦克风采样率。

*   **参考信号缓冲（`B64PCMPlayer` 扩展）**：
    *   在播放器 `_player_loop` 中，播放前将音频数据重采样为 16kHz 并保存到 `reference_buffer` 队列。
    *   提供 `get_reference_frame()` 方法供 AEC 处理器获取参考信号。

*   **主循环集成**：
    *   将麦克风数据（200ms）分割为 10 个 20ms 帧（320 samples/帧）。
    *   对每帧执行 `aec_processor.process(mic_frame, ref_frame)`，输出清洗后的音频。
    *   合并所有清洗后的帧，发送到 Qwen-Omni ASR。

*   **配置项（`config.py::AEC_CONFIG`）**：
    ```python
    {
        "ENABLED": True,          # 是否启用 AEC
        "FRAME_SIZE": 320,        # 20ms @ 16kHz
        "FILTER_LENGTH": 2048,    # 滤波器长度（影响效果与性能）
        "SAMPLE_RATE": 16000      # 采样率
    }
    ```

*   **效果**：
    *   机器人播放时不会响应播放内容中的控制指令。
    *   用户打断功能仍然正常工作。
    *   延迟增加 < 100ms（可调整滤波器长度优化）。

*   **环境要求**：
    *   Linux 系统需先安装 `libspeexdsp-dev`。
    *   安装 Python 依赖：`pip install speexdsp-python scipy`。

### 3.5 连接保活与优雅退出机制

**背景**：
在原始实现中，当用户长时间不说话时，DashScope 服务端会因 VAD（语音活动检测）判定对话结束而主动关闭 WebSocket 连接。此时 `on_close` 回调中的 `os._exit(0)` 会强制杀死整个进程，导致资源无法正确释放。

**问题分析**：

1.  **强制退出隐患**：`os._exit(0)` 跳过所有清理逻辑，可能导致文件句柄泄漏、线程僵死等问题。
2.  **VAD 超时过短**：默认 `silence_duration_ms` 约 2-3 秒，无法满足长时间待机场景（如展厅演示）。
3.  **状态不可观测**：主循环无法感知连接已断开，可能进入未定义状态。

**解决方案**：

*   **优雅退出模式（`MyCallback` 修改）**：
    ```python
    # 初始化时添加连接状态标志
    self._connection_alive = True
    
    # on_close 修改为设置标志，而非强制退出
    def on_close(self, close_status_code, close_msg) -> None:
        logger.info(f"[Omni] connection closed: code={close_status_code}, msg={close_msg}")
        self._cleanup()  # 清理资源
        self._connection_alive = False  # 标记连接已断开
    ```

*   **延长 VAD 静音超时（`main()` 配置修改）**：
    ```python
    conversation.update_session(
        # ... 其他参数 ...
        enable_turn_detection=True,
        turn_detection_type="server_vad",
        turn_detection_config={  # 新增配置
            "silence_duration_ms": 600000,  # 10分钟（600秒 * 1000ms）
            "prefix_padding_ms": 300,       # 保留前缓冲300ms
            "threshold": 0.5                # VAD检测阈值
        },
        instructions=instructions,
    )
    ```

*   **主循环状态检测**：
    ```python
    while True:
        # 检查连接状态，断开则退出循环
        if not callback._connection_alive:
            logger.warning("[System] WebSocket 连接已断开，程序退出")
            break
        # ... 原有逻辑 ...
    ```

**技术细节**：

*   **线程安全性**：`_connection_alive` 仅在初始化（`True`）和 `on_close`（`False`）两处修改，无需加锁（单次赋值原子性）。
*   **资源清理顺序**：`on_close` → `_cleanup()`（关播放器、麦克风）→ 设置标志 → 主循环退出 → Ctrl+C 处理器最终清理。
*   **超时时间选择**：10 分钟满足展厅演示需求；实际部署可根据场景调整（如家用场景可设为 30-60 分钟）。

**验证方法**：
1.  启动程序后保持 10 分钟静音，观察连接是否保持活跃。
2.  手动触发断连（如网络中断），检查日志是否正确记录 `[System] WebSocket 连接已断开`。
3.  确认进程正确退出，无僵死线程（`ps aux | grep python`）。

---

## 4. 开发日志与里程碑

### [2026-01-20] 阶段一：架构重构与频率解耦

*   **核心突破**：完成了 `ActionManager` 的开发与集成，成功解决了“心跳超时”这一致命系统瓶颈。
*   **关键修复**：
    *   **音视频并发锁**：修复了视频发送阻塞音频线程的问题，采用非阻塞锁 (`acquire(blocking=False)`) 优先保障音频流畅性。
    *   **API Key 安全**：移除硬编码 Key，全面支持环境变量 `DASHSCOPE_API_KEY`。
*   **夜间优化 (Night Session)**：
    *   重构：文件重命名 `mutimodel_interrution.py` -> `multimodal_interaction.py`。
    *   安全补丁：在 ASR 回调中增加“打断即停止”逻辑，用户喊“停”时强制切断电机动力，而不仅仅是停止播报。

### [2026-01-21] 阶段二：智能升级与安全加固

*   **功能实现**：
    *   全量接入 **Function Calling**，支持 `bridge` 层解析。
    *   新增 `emergency_stop` 模块，实现键盘物理急停。
*   **测试验收**：
    *   建立完整的单元测试套件 (`tests/`)，覆盖率 100%。
    *   `test_bridge.py`: 验证复杂指令参数截断逻辑。
    *   `test_emergency_stop.py`: 验证急停线程生命周期。
*   **文档简化**：大幅精简 `bk-main.md`，聚焦核心架构。

### [2026-01-22] 阶段四：全双工对话与软件打断机制

*   **核心突破**：实现真正的全双工对话，用户可在机器人播报时随时打断。
*   **关键实现**：
    *   **全双工模式**：播放期间不再 drain 麦克风，而是持续发送音频到服务端进行 ASR 转写。
    *   **ASR 驱动打断**：`is_interrupt_command()` 识别强触发词（"打断"、"闭嘴"、"停止播放"）+ 弱触发词组合（"停止" + "说话"）。
    *   **播放器优化**：`B64PCMPlayer` 引入 sub-chunking（40ms 粒度 write），配合 `interrupt()` 方法实现极低延迟停止（\u003c200ms）。
    *   **安全加固**：打断指令若包含运动停止意图（"停"、"急停"、"别动"），同步触发 `ActionManager.emergency_stop()` 或 `set_idle()`。
*   **接口标准化**：
    *   明确 G1 使用 `LocoClient`（`Move`, `Damp`, `Squat2StandUp`），区别于 Go2/B2 的 `SportClient`。
    *   代码注释完善，符合 PEP 8 + 简体中文注释规范。

### [2026-01-22] 阶段五：音频回声消除（AEC）

*   **核心突破**：实现音频回声消除（AEC），彻底解决全双工自激问题。
*   **关键实现**：
    *   **AEC 处理器**：创建 `aec_processor.py` 模块，封装 `speexdsp.EchoCanceller` 自适应滤波器。
    *   **参考信号系统**：修改 `B64PCMPlayer`，播放前保存 16kHz 参考信号到缓冲区。
    *   **分帧处理**：主循环以 20ms/帧粒度执行回声消除，保持低延迟。
    *   **音频重采样**：使用 `scipy.signal.resample` 实现 24kHz → 16kHz 高质量转换。
*   **验收标准**：
    *   机器人播放时不响应播放内容中的控制指令（如播放"前进"时不会移动）。
    *   用户打断功能正常（用户说"打断"仍能立即停止播放）。
    *   延迟增加可控（< 100ms）。
*   **测试**：
    *   创建 `tests/test_aec.py` 单元测试文件。
    *   测试覆盖：初始化、处理、重采样、重置等核心功能。

### [2026-01-28] 阶段七：连接保活机制优化

*   **核心突破**：彻底解决长时间静音自动退出问题，支持 10 分钟无语音交互不断连。
*   **关键实现**：
    *   **优雅退出**：移除 `on_close` 中的 `os._exit(0)`，改为设置 `_connection_alive = False` 标志。
    *   **VAD 超时延长**：配置 `turn_detection_config`，将 `silence_duration_ms` 从默认 2-3 秒延长到 600,000 毫秒（10 分钟）。
    *   **状态检测**：主循环每次迭代检查 `_connection_alive`，连接断开时记录日志并优雅退出。
    *   **资源管理**：确保播放器、麦克风、线程等资源在断连时正确释放，无进程僵死。
*   **代码修改位置**：
    *   `MyCallback.__init__()`: 添加 `_connection_alive` 标志初始化。
    *   `MyCallback.on_close()`: 替换强制退出为状态标记。
    *   `main()`: 添加 `turn_detection_config` 配置项。
    *   主循环（1090-1101 行）: 添加连接状态检查逻辑。
*   **验收标准**：
    *   启动后保持 10 分钟静音，连接不断开。
    *   手动断网或服务端断连时，程序正确记录日志并退出。
    *   无资源泄漏或僵尸线程。

---

## 5. 待办事项 (Roadmap)

*   [ ] **实机长程验证**：在真实 G1 机器人上进行 >30 分钟的连续交互测试，验证 100Hz 循环的长期稳定性。
*   [ ] **状态自动恢复**：完善 `RecoveryStand` 逻辑，在机器人跌倒或急停后能通过语音指令自动站起。
*   [ ] **视觉闭环**：引入 VLM (Vision Language Model) 的实时分析，不仅用于对话，还用于避障（目前仅作数据流传输，未参与控制决策）。
