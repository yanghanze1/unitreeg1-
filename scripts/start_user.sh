#!/bin/bash
# User-level startup script for Unitree G1 Voice Controller
# 在用户登录后自动运行，设定音频设备并启动程序
# 日志输出到 /tmp/unitree-g1-voice.log

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/unitree-g1-voice.log"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "Unitree G1 Voice Controller 启动脚本"
log "========================================="

# 检查是否已经运行
if pgrep -f "multimodal_interaction.py" > /dev/null 2>&1; then
    log "程序已在运行中，跳过启动"
    exit 0
fi

# 等待 PulseAudio 启动
log "等待音频系统就绪..."
sleep 3

# 设定音频设备
log "设定音频设备..."
if [ -f "${SCRIPT_DIR}/setup_audio.sh" ]; then
    bash "${SCRIPT_DIR}/setup_audio.sh" >> "$LOG_FILE" 2>&1
else
    log "警告: setup_audio.sh 不存在"
fi

# 启动主程序
log "启动语音交互程序..."
log "--- 程序输出开始 ---"

cd "${SCRIPT_DIR}/.."
python3 VoiceInteraction/multimodal_interaction.py 2>&1 | tee -a "$LOG_FILE"

log "--- 程序已退出 ---"
log "如需重新启动，请重新登录或运行: bash ${SCRIPT_DIR}/start_user.sh"
