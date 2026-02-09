#!/bin/bash
# User-level startup script for Unitree G1 Voice Controller
# 在用户登录后自动运行，设定音频设备并启动程序

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "Unitree G1 Voice Controller 用户启动"
echo "========================================="

# 等待 PulseAudio 启动
sleep 2

# 设定音频设备
echo "[1/2] 设定音频设备..."
if [ -f "${SCRIPT_DIR}/setup_audio.sh" ]; then
    source "${SCRIPT_DIR}/setup_audio.sh"
else
    echo "[警告] setup_audio.sh 不存在"
fi

# 启动主程序（在前台运行）
echo "[2/2] 启动语音交互程序..."
echo "[Info] 按 Ctrl+C 停止程序"
echo ""

cd "${SCRIPT_DIR}/.."
python3 VoiceInteraction/multimodal_interaction.py
