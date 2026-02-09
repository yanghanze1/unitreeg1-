#!/bin/bash
# 开机自启脚本 - 带 PulseAudio 等待和配置

LOG_FILE="/tmp/unitree-g1-voice.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "启动脚本开始执行..."

# 等待系统就绪
sleep 5

# 配置 PulseAudio（最小配置）
mkdir -p ~/.config/pulse
cat > ~/.config/pulse/client.conf << 'EOF'
autospawn = yes
daemon-binary = /usr/bin/pulseaudio
EOF

# 等待 PulseAudio 就绪
log "等待 PulseAudio 就绪..."
for i in {1..30}; do
    if pactl info &>/dev/null; then
        log "PulseAudio 已就绪"
        break
    fi
    sleep 1
done

# 设置默认音频设备（使用 USB 麦克风）
if pactl info &>/dev/null; then
    pactl set-default-source alsa_input.usb-Jieli_Technology_USB_Composite_Device_853A4D1988FD7053-00.mono-fallback 2>/dev/null || true
    pactl set-default-sink alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 2>/dev/null || true
    log "音频设备已设置"
fi

# 设置环境变量
export PULSE_SERVER=unix:/run/user/1000/pulse/native
export XDG_RUNTIME_DIR=/run/user/1000
export PYTHONPATH=/home/unitree/.local/lib/python3.8/site-packages:$PYTHONPATH

log "启动语音交互程序..."

# 启动程序
cd /home/unitree/bk-main
python3 VoiceInteraction/multimodal_interaction.py >> "$LOG_FILE" 2>&1 &
PID=$!
log "程序已启动，PID: $PID"

wait $PID
log "程序已退出"
