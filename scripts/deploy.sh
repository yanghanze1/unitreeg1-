#!/bin/bash
# Deployment Script for Unitree G1 Voice Controller (无显示器版本)
# 使用 crontab @reboot 实现开机自启，延迟启动确保 PulseAudio 就绪

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="bk-main"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
TARGET_DIR="/home/unitree/${PROJECT_NAME}"
START_SCRIPT="${TARGET_DIR}/scripts/start_systemd.sh"

echo "========================================="
echo "Unitree G1 Voice Controller 部署脚本"
echo "========================================="

# 检查是否在宇树机器人上运行
if [ ! -d "/home/unitree" ]; then
    echo "[警告] 未检测到 /home/unitree 目录"
    read -p "是否继续部署? (y/n): " confirm
    if [ "$confirm" != "y" ]; then
        exit 0
    fi
    TARGET_DIR="${PROJECT_DIR}"
fi

# 1. 复制项目文件
echo ""
echo "[1/4] 部署项目文件 ..."
if [ "${PROJECT_DIR}" != "${TARGET_DIR}" ]; then
    if [ -d "${TARGET_DIR}" ] && [ "${TARGET_DIR}" != "${PROJECT_DIR}" ]; then
        mv "${TARGET_DIR}" "${TARGET_DIR}.backup" 2>/dev/null || true
    fi
    if [ "${PROJECT_DIR}" != "${TARGET_DIR}" ]; then
        sudo mkdir -p /home/unitree
        sudo cp -r "${PROJECT_DIR}" "${TARGET_DIR}"
        sudo chown -R unitree:unitree "${TARGET_DIR}" 2>/dev/null || true
        rm -rf "${TARGET_DIR}.backup" 2>/dev/null || true
    fi
fi

# 2. 设置执行权限
echo ""
echo "[2/4] 设置脚本执行权限 ..."
sudo chmod +x "${TARGET_DIR}/scripts/"*.sh 2>/dev/null || true

# 3. 配置 crontab（延迟 30 秒启动，确保 PulseAudio 就绪）
echo ""
echo "[3/4] 配置开机自启 ..."
crontab -l 2>/dev/null | grep -v "start_systemd.sh" > /tmp/current_cron || true
# 延迟 30 秒启动，等 PulseAudio 完全就绪
echo "@reboot sleep 30 && bash ${START_SCRIPT}" >> /tmp/current_cron
crontab /tmp/current_cron
echo "[完成] crontab 已配置（延迟 30 秒启动）"

# 4. 停止旧进程并启动
echo ""
echo "[4/4] 启动服务 ..."
pkill -f "multimodal_interaction.py" 2>/dev/null || true
sleep 2
bash "${START_SCRIPT}" &
echo "[完成] 服务已启动"

echo ""
echo "========================================="
echo "✅ 部署完成!"
echo "========================================="
echo ""
echo "🎯 预期效果:"
echo "   开机 → 等待 30 秒 → 自动启动 → 直接说话"
echo ""
echo "🛠️  命令:"
echo "   查看日志: tail -f /tmp/unitree-g1-voice.log"
echo "   查看 crontab: crontab -l"
echo ""
