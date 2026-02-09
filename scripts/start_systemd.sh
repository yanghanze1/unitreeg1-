#!/bin/bash
# 开机自启脚本 - 完整音频配置

LOG_FILE="/tmp/unitree-g1-voice.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "===== 启动脚本开始执行 ====="

# 等待系统就绪
sleep 5

# 杀掉旧的 PulseAudio 和程序
pulseaudio -k 2>/dev/null || true
pkill -9 -f multimodal_interaction.py 2>/dev/null || true
sleep 2

# 确保 /run/user/1000 存在
mkdir -p /run/user/1000
chmod 700 /run/user/1000

# 启动 PulseAudio（作为用户进程）
export XDG_RUNTIME_DIR=/run/user/1000
pulseaudio --daemonize --log-target=journal --exit-idle-time=-1

# 等待 PulseAudio 启动
log "等待 PulseAudio 启动..."
for i in {1..15}; do
    if pactl info &>/dev/null; then
        log "PulseAudio 已启动"
        break
    fi
    sleep 1
done

# 配置音频设备
if pactl info &>/dev/null; then
    # 获取设备索引
    MIC_SINK=$(pactl list sources short | grep "USB" | grep "Audio" | head -1 | awk '{print $1}')
    PLAY_SINK=$(pactl list sinks short | grep "USB" | grep "Audio" | head -1 | awk '{print $1}')
    
    if [ -n "$MIC_SINK" ]; then
        pactl set-default-source "$MIC_SINK"
        log "麦克风已设置为: $MIC_SINK"
    fi
    
    if [ -n "$PLAY_SINK" ]; then
        pactl set-default-sink "$PLAY_SINK"
        log "扬声器已设置为: $PLAY_SINK"
    fi
    
    # 设置音量
    pactl set-sink-volume "$PLAY_SINK" 100% 2>/dev/null || true
fi

# 设置环境变量
export PULSE_SERVER=unix:/run/user/1000/pulse/native
export XDG_RUNTIME_DIR=/run/user/1000
export PYTHONPATH=/home/unitree/.local/lib/python3.8/site-packages:$PYTHONPATH

# 指定麦克风设备（使用 Pulse "default" 设备）
export MIC_DEVICE_INDEX=

log "启动语音交互程序..."

# 启动程序
cd /home/unitree/bk-main
python3 VoiceInteraction/multimodal_interaction.py >> "$LOG_FILE" 2>&1 &
PID=$!
log "程序已启动，PID: $PID"

wait $PID
log "程序已退出"
