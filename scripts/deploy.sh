#!/bin/bash
# Deployment Script for Unitree G1 Voice Controller (无显示器版本)
# 用于机器人机载电脑，开机后自动运行，无需登录

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="bk-main"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
TARGET_DIR="/home/unitree/${PROJECT_NAME}"
SERVICE_FILE="${TARGET_DIR}/deploy/unitree-g1-voice.service"

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
        if [ "${TARGET_DIR}" = "${PROJECT_DIR}" ]; then
            echo "[Info] 源目录和目标目录相同，跳过复制"
        else
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

# 3. 复制并安装 systemd 服务
echo ""
echo "[3/5] 安装 systemd 服务 ..."
sudo cp "${SERVICE_FILE}" /etc/systemd/system/unitree-g1-voice.service
sudo chmod 644 /etc/systemd/system/unitree-g1-voice.service
sudo systemctl daemon-reload
echo "[完成] systemd 服务已安装"

# 4. 启用开机自启
echo ""
echo "[4/5] 启用开机自启 ..."
sudo systemctl enable unitree-g1-voice.service
echo "[完成] 开机自启已启用"

# 5. 启动服务
echo ""
echo "[5/5] 启动服务 ..."
sudo systemctl start unitree-g1-voice.service
echo "[完成] 服务已启动"

echo ""
echo "========================================="
echo "✅ 部署完成!"
echo "========================================="
echo ""
echo "🎯 预期效果:"
echo "   机器人开机 → 电源启动 → 自动运行 → 直接说话"
echo ""
echo "📋 操作流程:"
echo "   1. 重启机器人: sudo reboot"
echo "   2. 等待约 15 秒程序启动"
echo "   3. 直接对麦克风说话"
echo ""
echo "🛠️  手动命令:"
echo "   查看状态: sudo systemctl status unitree-g1-voice"
echo "   查看日志: journalctl -u unitree-g1-voice -f"
echo "   重启服务: sudo systemctl restart unitree-g1-voice"
echo "   停止服务: sudo systemctl stop unitree-g1-voice"
echo "   禁用开机: sudo systemctl disable unitree-g1-voice"
echo ""
