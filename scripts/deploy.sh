#!/bin/bash
# Deployment Script for Unitree G1 Voice Controller (无显示器版本)
# 用于机器人机载电脑，开机后自动运行，无需登录

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
    TARGET_DIR="${PROJECT_DIR}"
    echo "[Info] 使用当前目录作为目标目录"
fi

# 1. 先备份再复制
echo ""
echo "[1/6] 部署项目文件 ..."
if [ "${PROJECT_DIR}" = "${TARGET_DIR}" ]; then
    echo "[Info] 源目录和目标目录相同，跳过复制"
elif [ -d "${TARGET_DIR}" ]; then
    echo "[Info] 备份现有目标目录 ..."
    if [ -d "${TARGET_DIR}.backup" ]; then
        sudo rm -rf "${TARGET_DIR}.backup"
    fi
    mv "${TARGET_DIR}" "${TARGET_DIR}.backup"
fi

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
echo "[2/6] 设置脚本执行权限 ..."
sudo chmod +x "${TARGET_DIR}/scripts/"*.sh
echo "[完成] 脚本权限已设置"

# 3. 启用 systemd 用户服务
echo ""
echo "[3/6] 配置 systemd 用户服务 ..."
systemctl --user daemon-reload 2>/dev/null || echo "[警告] 无法访问 systemd user"
echo "[完成] systemd 用户服务已配置"

# 4. 启用用户服务开机自启
echo ""
echo "[4/6] 启用用户服务开机自启 ..."
sudo loginctl enable-linger unitree 2>/dev/null || echo "[警告] 无法启用 linger，请手动运行: sudo loginctl enable-linger unitree"
systemctl --user enable unitree-g1-voice.service 2>/dev/null || echo "[警告] 无法启用用户服务"
echo "[完成] 用户服务开机自启已启用"

# 5. 启动服务
echo ""
echo "[5/6] 启动语音交互服务 ..."
systemctl --user start unitree-g1-voice.service 2>/dev/null && echo "[完成] 服务已启动" || echo "[警告] 无法启动服务"

# 6. 检查状态
echo ""
echo "[6/6] 检查服务状态 ..."
systemctl --user status unitree-g1-voice.service 2>/dev/null || echo "[Info] 服务状态无法显示"

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
echo "   2. 等待约 10 秒程序启动"
echo "   3. 直接对麦克风说话"
echo ""
echo "🛠️  手动命令:"
echo "   查看状态: systemctl --user status unitree-g1-voice"
echo "   查看日志: journalctl --user -u unitree-g1-voice -f"
echo "   重启服务: systemctl --user restart unitree-g1-voice"
echo "   停止服务: systemctl --user stop unitree-g1-voice"
echo ""
echo "⚠️  如果服务启动失败，请检查:"
echo "   1. 确保已运行: sudo loginctl enable-linger unitree"
echo "   2. 查看日志: journalctl --user -u unitree-g1-voice"
echo ""
