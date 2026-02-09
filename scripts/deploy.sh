#!/bin/bash
# Deployment Script for Unitree G1 Voice Controller
# 一键部署开机自启服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
SERVICE_FILE="${SCRIPT_DIR}/deploy/unitree-g1-voice.service"
AUDIO_SCRIPT="${SCRIPT_DIR}/scripts/setup_audio.sh"

echo "========================================="
echo "Unitree G1 Voice Controller 部署脚本"
echo "========================================="

# 检查是否在宇树机器人上运行
if [ ! -d "/home/unitree" ]; then
    echo "[警告] 未检测到 /home/unitree 目录"
    echo "[警告] 似乎不是在宇树机载电脑上运行"
    read -p "是否继续部署到当前系统? (y/n): " confirm
    if [ "$confirm" != "y" ]; then
        echo "已取消部署"
        exit 0
    fi
    PROJECT_DIR=$(pwd)
    echo "[Info] 使用当前目录: ${PROJECT_DIR}"
fi

# 1. 复制项目到机载电脑
echo ""
echo "[1/4] 复制项目到 /home/unitree/bk-main ..."
if [ -d "/home/unitree/bk-main" ]; then
    read -p "目标目录已存在，是否覆盖? (y/n): " confirm
    if [ "$confirm" == "y" ]; then
        sudo rm -rf /home/unitree/bk-main
    else
        echo "已取消部署"
        exit 0
    fi
fi
sudo mkdir -p /home/unitree
sudo cp -r "${PROJECT_DIR}" /home/unitree/bk-main
sudo chown -R unitree:unitree /home/unitree/bk-main
echo "[完成] 项目已复制到 /home/unitree/bk-main"

# 2. 设置执行权限
echo ""
echo "[2/4] 设置脚本执行权限 ..."
sudo chmod +x "${AUDIO_SCRIPT}"
sudo chmod +x "${SCRIPT_DIR}/scripts/"*.sh 2>/dev/null || true
echo "[完成] 脚本权限已设置"

# 3. 安装 systemd 服务
echo ""
echo "[3/4] 安装 systemd 服务 ..."
sudo cp "${SERVICE_FILE}" /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/unitree-g1-voice.service
sudo systemctl daemon-reload
echo "[完成] 服务已安装"

# 4. 启用开机自启
echo ""
echo "[4/4] 启用开机自启 ..."
sudo systemctl enable unitree-g1-voice.service
echo "[完成] 开机自启已启用"

echo ""
echo "========================================="
echo "部署完成!"
echo "========================================="
echo ""
echo "常用命令:"
echo "  启动服务:     sudo systemctl start unitree-g1-voice"
echo "  停止服务:     sudo systemctl stop unitree-g1-voice"
echo "  查看状态:     sudo systemctl status unitree-g1-voice"
echo "  查看日志:     journalctl -u unitree-g1-voice -f"
echo "  禁用开机:     sudo systemctl disable unitree-g1-voice"
echo ""
