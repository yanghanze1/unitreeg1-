#!/bin/bash
# 开机自启脚本 - 带 PulseAudio 等待

# 等待系统就绪
sleep 10

# 等待 PulseAudio 就绪
echo "[$(date)] 等待 PulseAudio 就绪..." >> /tmp/unitree-g1-voice.log
for i in {1..30}; do
    if pactl info &>/dev/null; then
        echo "[$(date)] PulseAudio 已就绪" >> /tmp/unitree-g1-voice.log
        break
    fi
    sleep 1
done

# 设置环境变量
export PULSE_SERVER=unix:/run/user/1000/pulse/native
export XDG_RUNTIME_DIR=/run/user/1000
export PYTHONPATH=/home/unitree/.local/lib/python3.8/site-packages:$PYTHONPATH

echo "[$(date)] 启动语音交互程序..." >> /tmp/unitree-g1-voice.log

# 启动程序
cd /home/unitree/bk-main
python3 VoiceInteraction/multimodal_interaction.py >> /tmp/unitree-g1-voice.log 2>&1
