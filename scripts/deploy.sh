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
echo "[1/4] 部署项目文件 ..."
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
echo "[2/4] 设置脚本执行权限 ..."
sudo chmod +x "${TARGET_DIR}/scripts/"*.sh 2>/dev/null || true
echo "[完成] 脚本权限已设置"

# 3. 创建启动脚本（处理 PulseAudio）
echo ""
echo "[3/4] 配置启动脚本 ..."
cat > "${START_SCRIPT}" << 'STARTSCRIPT'
#!/bin/bash
# 开机自启脚本

# 等待系统就绪
sleep 5

# 设置 PulseAudio 环境变量
export PULSE_SERVER=unix:/run/user/1000/pulse/native
export XDG_RUNTIME_DIR=/run/user/1000
export PYTHONPATH=/home/unitree/.local/lib/python3.8/site-packages:$PYTHONPATH

# 启动程序
cd /home/unitree/bk-main
python3 VoiceInteraction/multimodal_interaction.py >> /tmp/unitree-g1-voice.log 2>&1 &
STARTSCRIPT

chmod +x "${START_SCRIPT}"
echo "[完成] 启动脚本已创建"

# 4. 配置 crontab 开机自启
echo ""
echo "[4/4] 配置开机自启 ..."
crontab -l 2>/dev/null | grep -v "start_systemd.sh" > /tmp/current_cron || true
echo "@reboot bash ${START_SCRIPT}" >> /tmp/current_cron
crontab /tmp/current_cron
echo "[完成] crontab 已配置"

echo ""
echo "========================================="
echo "✅ 部署完成!"
echo "========================================="
echo ""
echo "🎯 预期效果:"
echo "   机器人开机 → 等待 5 秒 → 自动启动 → 直接说话"
echo ""
echo "📋 操作流程:"
echo "   1. 重启机器人: sudo reboot"
echo "   2. 等待约 15 秒程序启动"
echo "   3. 直接对麦克风说话"
echo ""
echo "🛠️  手动命令:"
echo "   查看日志: tail -f /tmp/unitree-g1-voice.log"
echo "   查看 crontab: crontab -l"
echo "   删除自启: crontab -l | grep -v 'start_systemd.sh' | crontab -"
echo ""
