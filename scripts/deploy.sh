#!/bin/bash
# Deployment Script for Unitree G1 Voice Controller
# 一键部署开机自启服务（完全自动化，无需手动操作）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="bk-main"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"  # scripts 的父目录
TARGET_DIR="/home/unitree/${PROJECT_NAME}"

echo "========================================="
echo "Unitree G1 Voice Controller 部署脚本"
echo "========================================="
echo "[Info] 源目录: ${PROJECT_DIR}"
echo "[Info] 目标目录: ${TARGET_DIR}"

# 检查是否在宇树机器人上运行
if [ ! -d "/home/unitree" ]; then
    echo "[警告] 未检测到 /home/unitree 目录"
    echo "[警告] 似乎不是在宇树机载电脑上运行"
    read -p "是否继续部署到当前系统? (y/n): " confirm
    if [ "$confirm" != "y" ]; then
        echo "已取消部署"
        exit 0
    fi
    # 如果不是宇树机器人，直接在当前目录使用
    TARGET_DIR="${PROJECT_DIR}"
    echo "[Info] 使用当前目录作为目标目录"
fi

# 1. 先备份再复制（避免删除源目录）
echo ""
echo "[1/5] 部署项目文件 ..."
if [ "${PROJECT_DIR}" = "${TARGET_DIR}" ]; then
    echo "[Info] 源目录和目标目录相同，跳过复制"
elif [ -d "${TARGET_DIR}" ]; then
    echo "[Info] 备份现有目标目录 ..."
    if [ -d "${TARGET_DIR}.backup" ]; then
        sudo rm -rf "${TARGET_DIR}.backup"
    fi
    mv "${TARGET_DIR}" "${TARGET_DIR}.backup"
fi

# 执行复制
if [ "${PROJECT_DIR}" != "${TARGET_DIR}" ]; then
    sudo mkdir -p /home/unitree
    sudo cp -r "${PROJECT_DIR}" "${TARGET_DIR}"
    sudo chown -R unitree:unitree "${TARGET_DIR}"
    if [ -d "${TARGET_DIR}.backup" ]; then
        rm -rf "${TARGET_DIR}.backup"
    fi
    echo "[完成] 项目已部署到 ${TARGET_DIR}"
else
    echo "[完成] 使用当前目录"
fi

# 2. 设置执行权限
echo ""
echo "[2/5] 设置脚本执行权限 ..."
sudo chmod +x "${TARGET_DIR}/scripts/"*.sh
echo "[完成] 脚本权限已设置"

# 3. 配置用户登录后自动启动（这是关键！）
echo ""
echo "[3/5] 配置用户登录后自动启动 ..."
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/unitree-g1-voice.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Unitree G1 Voice
Comment=自动启动宇树G1语音交互系统
Exec=bash /home/unitree/bk-main/scripts/start_user.sh
Terminal=false
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
echo "[完成] 用户登录后自动启动语音交互程序"

# 4. 设置音频设备自动配置
echo ""
echo "[4/5] 配置音频设备自动设定 ..."
# 确保用户有权限使用 PulseAudio
if ! grep -q "autospawn = yes" ~/.config/pulse/client.conf 2>/dev/null; then
    mkdir -p ~/.config/pulse
    echo "autospawn = yes" >> ~/.config/pulse/client.conf
    echo "daemon-binary = /usr/bin/pulseaudio" >> ~/.config/pulse/client.conf
fi
echo "[完成] 音频设备自动配置已启用"

# 5. 禁用 systemd 服务（因为不需要，登录后直接运行）
echo ""
echo "[5/5] 禁用 systemd 服务（使用用户登录启动） ..."
sudo systemctl disable unitree-g1-voice.service 2>/dev/null || true
echo "[完成] systemd 服务已禁用（改用用户登录启动）"

echo ""
echo "========================================="
echo "✅ 部署完成!"
echo "========================================="
echo ""
echo "🎯 预期效果:"
echo "   机器人开机 → 用户登录 → 自动启动语音交互 → 直接说话"
echo ""
echo "📋 操作流程:"
echo "   1. 重启机器人: sudo reboot"
echo "   2. 登录用户 (unitree)"
echo "   3. 等待程序自动启动（约5秒）"
echo "   4. 看到 'Listening for commands...' 后直接说话"
echo ""
echo "🛠️  手动命令:"
echo "   启动: bash /home/unitree/bk-main/scripts/start_user.sh"
echo "   停止: 按 Ctrl+C"
echo "   查看日志: tail -f /tmp/unitree-g1-voice.log"
echo ""
