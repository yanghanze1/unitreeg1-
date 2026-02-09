#!/bin/bash
# 开机自启脚本 - 完整音频配置

LOG_FILE="/tmp/unitree-g1-voice.log"
PROJECT_DIR="/home/unitree/bk-main"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE" 2>/dev/null || echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "===== 启动脚本开始执行 ====="
log "工作目录: $PROJECT_DIR"

# 确保日志文件可写
touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/home/unitree/bk-main/unitree-g1-voice.log"
touch "$LOG_FILE" 2>/dev/null || LOG_FILE="./unitree-g1-voice.log"
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 等待系统就绪
sleep 5

# 杀掉旧的进程
pulseaudio -k 2>/dev/null || true
pkill -9 -f multimodal_interaction.py 2>/dev/null || true
sleep 2

# 确保目录存在
mkdir -p /run/user/1000 2>/dev/null || true

# 配置环境变量
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

# 设置默认设备
if pactl info &>/dev/null; then
    pactl set-default-source alsa_input.usb-Jieli_Technology_USB_Composite_Device_853A4D1988FD7053-00.mono-fallback 2>/dev/null || true
    pactl set-default-sink alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 2>/dev/null || true
fi

log "启动语音交互程序..."

# 进入项目目录
cd "$PROJECT_DIR"

# 启动程序
python3 VoiceInteraction/multimodal_interaction.py >> "$LOG_FILE" 2>&1 &
PID=$!
log "程序已启动，PID: $PID"

wait $PID
log "程序已退出"
