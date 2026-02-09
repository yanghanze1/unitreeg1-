#!/bin/bash
# Setup PulseAudio for systemd service (root user)
# 配置系统级 PulseAudio

set -e

echo "========================================="
echo "PulseAudio 系统级配置"
echo "========================================="

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行"
    exit 1
fi

# 1. 创建 PulseAudio 配置目录
echo "[1/4] 创建 PulseAudio 配置..."
mkdir -p /etc/pulse
mkdir -p /run/pulse

# 2. 创建系统级 PulseAudio 配置
cat > /etc/pulse/daemon.conf << 'EOF'
daemonize = yes
fail = yes
allow-module-preload = yes
allow-exit = yes
use-pid-file = yes
system-instance = yes
local-server-type = user
enable-shm = yes
flat-volumes = no
exit-idle-time = -1
EOF

# 3. 创建 client.conf
cat > /etc/pulse/client.conf << 'EOF'
autospawn = yes
daemon-binary = /usr/bin/pulseaudio
EOF

# 4. 设置权限
chmod 644 /etc/pulse/daemon.conf
chmod 644 /etc/pulse/client.conf
chmod 755 /run/pulse

echo "[完成] PulseAudio 配置完成"

echo ""
echo "========================================="
echo "启动 PulseAudio..."
echo "========================================="

# 启动 PulseAudio（如果还没运行）
if ! pgrep -x pulseaudio > /dev/null; then
    pulseaudio --daemonize --exit-idle-time=-1 --system --log-target=journal
    echo "[完成] PulseAudio 已启动"
else
    echo "[Info] PulseAudio 已在运行"
fi

echo ""
echo "测试音频设备..."
pactl info 2>/dev/null && echo "[完成] PulseAudio 正常" || echo "[警告] PulseAudio 测试失败"

echo ""
echo "========================================="
echo "配置完成!"
echo "========================================="
echo ""
echo "如果遇到权限问题，请运行:"
echo "  sudo usermod -aG audio unitree"
echo "  sudo usermod -aG pulse-access unitree"
echo ""
