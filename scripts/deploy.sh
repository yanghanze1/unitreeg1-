#!/bin/bash
# Deployment Script for Unitree G1 Voice Controller (无显示器版本)
# 使用 crontab @reboot 实现开机自启

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
    read -p "是否继续部署到当前系统? (y/n): " confirm
    if [ "$confirm" != "y" ]; then
        echo "已取消部署"
        exit 0
    fi
    TARGET_DIR="${PROJECT_DIR}"
    echo "[Info] 使用当前目录: ${TARGET_DIR}"
fi

# 1. 复制项目文件
echo ""
echo "[1/5] 部署项目文件 ..."
if [ "${PROJECT_DIR}" != "${TARGET_DIR}" ]; then
    if [ -d "${TARGET_DIR}" ]; then
        if [ "${TARGET_DIR}" != "${PROJECT_DIR}" ]; then
            mv "${TARGET_DIR}" "${TARGET_DIR}.backup" 2>/dev/null || true
        fi
    fi
    
    if [ "${PROJECT_DIR}" != "${TARGET_DIR}" ]; then
        sudo mkdir -p /home/unitree
        sudo cp -r "${PROJECT_DIR}" "${TARGET_DIR}"
        sudo chown -R unitree:unitree "${TARGET_DIR}" 2>/dev/null || true
        rm -rf "${TARGET_DIR}.backup" 2>/dev/null || true
        echo "[完成] 项目已部署到 ${TARGET_DIR}"
    fi
else
    echo "[完成] 使用当前目录"
fi

# 2. 设置执行权限
echo ""
echo "[2/5] 设置脚本执行权限 ..."
sudo chmod +x "${TARGET_DIR}/scripts/"*.sh 2>/dev/null || true
echo "[完成] 脚本权限已设置"

# 3. 清理旧的 PulseAudio 配置
echo ""
echo "[3/5] 清理旧配置 ..."
rm -rf /etc/pulse/daemon.conf 2>/dev/null || true
rm -rf /etc/pulse/client.conf 2>/dev/null || true
echo "[完成] 旧配置已清理"

# 4. 配置 crontab 开机自启
echo ""
echo "[4/5] 配置开机自启 ..."
crontab -l 2>/dev/null | grep -v "start_systemd.sh" > /tmp/current_cron || true
echo "@reboot bash ${START_SCRIPT}" >> /tmp/current_cron
crontab /tmp/current_cron
echo "[完成] crontab 已配置"

# 5. 停止旧进程并启动新进程
echo ""
echo "[5/5] 启动服务 ..."
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
echo "   机器人开机 → 等待 15 秒 → 自动启动 → 直接说话"
echo ""
echo "📋 操作流程:"
echo "   1. 重启机器人: sudo reboot"
echo "   2. 等待约 20 秒程序启动"
echo "   3. 直接对麦克风说话"
echo ""
echo "🛠️  手动命令:"
echo "   查看日志: tail -f /tmp/unitree-g1-voice.log"
echo "   查看 crontab: crontab -l"
echo ""
