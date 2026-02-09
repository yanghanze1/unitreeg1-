#!/bin/bash
# 开机自启脚本 - 使用 PulseAudio 麦克风

PROJECT_DIR="/home/unitree/bk-main"
LOG_FILE="$PROJECT_DIR/unitree-g1-voice.log"

touch "$LOG_FILE"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "===== 启动脚本开始执行 ====="

# 等待系统就绪
sleep 5

# 杀掉旧进程
pkill -9 -f multimodal_interaction.py 2>/dev/null || true
sleep 2

# 配置环境
export XDG_RUNTIME_DIR=/run/user/1000
export PULSE_SERVER=unix:/run/user/1000/pulse/native
export PYTHONPATH=/home/unitree/.local/lib/python3.8/site-packages:$PYTHONPATH

# 启动 PulseAudio
pulseaudio --daemonize --exit-idle-time=-1 2>/dev/null || true
sleep 2

# 等待 PulseAudio
for i in {1..10}; do
    if pactl info &>/dev/null; then
        log "PulseAudio 已就绪"
        break
    fi
    sleep 1
done

# 设置默认麦克风（Jieli Technology USB Composite Device - 单声道设备）
pactl set-default-source alsa_input.usb-Jieli_Technology_USB_Composite_Device_853A4D1988FD7053-00.mono-fallback 2>/dev/null && log "麦克风已设置为 Jieli USB" || log "无法设置默认麦克风"

# 设置默认扬声器
pactl set-default-sink alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 2>/dev/null || true

log "启动语音交互程序..."

# 进入项目目录
cd "$PROJECT_DIR"

# 启动程序 - 不指定 MIC_DEVICE_INDEX，让它用 PulseAudio 默认
unset MIC_DEVICE_INDEX
python3 VoiceInteraction/multimodal_interaction.py >> "$LOG_FILE" 2>&1 &
PID=$!
log "程序已启动，PID: $PID"

wait $PID
log "程序已退出"
