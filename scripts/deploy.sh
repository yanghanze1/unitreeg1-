#!/bin/bash
# Deployment Script for Unitree G1 Voice Controller
# 一键部署开机自启服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="bk-main"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"  # scripts 的父目录
TARGET_DIR="/home/unitree/${PROJECT_NAME}"
TEMP_DIR="/tmp/bk-main-deploy-$$"

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

# 1. 先复制到临时目录（避免删除源目录）
echo ""
echo "[1/4] 准备部署文件 ..."
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
    # 清理备份（如果存在）
    if [ -d "${TARGET_DIR}.backup" ]; then
        rm -rf "${TARGET_DIR}.backup"
    fi
    echo "[完成] 项目已部署到 ${TARGET_DIR}"
else
    echo "[完成] 使用当前目录"
fi

# 2. 设置执行权限
echo ""
echo "[2/4] 设置脚本执行权限 ..."
sudo chmod +x "${TARGET_DIR}/scripts/"*.sh
echo "[完成] 脚本权限已设置"

# 3. 安装 systemd 服务
echo ""
echo "[3/4] 安装 systemd 服务 ..."
sudo cp "${TARGET_DIR}/deploy/unitree-g1-voice.service" /etc/systemd/system/
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
