#!/bin/bash
# 完全重置音频权限脚本（兼容旧版 PulseAudio）
# 解决 PulseAudio 和 PyAudio 麦克风权限问题

set -e

echo "========================================="
echo "音频权限完全重置"
echo "========================================="

# 检查是否 root
if [ "$EUID" -ne 0 ]; then
    echo "错误: 请使用 sudo 运行"
    echo "sudo bash $0"
    exit 1
fi

echo ""
echo "[1/6] 停止所有音频相关进程..."
pulseaudio -k 2>/dev/null || true
pkill -9 -f pulseaudio 2>/dev/null || true
pkill -9 -f multimodal_interaction 2>/dev/null || true
sleep 1

echo ""
echo "[2/6] 清理旧的 PulseAudio 配置..."
rm -rf /etc/pulse/daemon.conf 2>/dev/null || true
rm -rf /etc/pulse/client.conf 2>/dev/null || true
rm -rf /run/pulse 2>/dev/null || true
rm -rf ~/.config/pulse 2>/dev/null || true
mkdir -p /run/pulse
mkdir -p ~/.config/pulse
chmod 755 /run/pulse

echo ""
echo "[3/6] 创建 PulseAudio 配置（兼容旧版本）..."
# 最小配置，兼容所有版本
cat > /etc/pulse/daemon.conf << 'EOF'
daemonize = yes
flat-volumes = no
exit-idle-time = -1
EOF

cat > /etc/pulse/client.conf << 'EOF'
autospawn = yes
daemon-binary = /usr/bin/pulseaudio
EOF

chmod 644 /etc/pulse/daemon.conf
chmod 644 /etc/pulse/client.conf

echo ""
echo "[4/6] 配置用户权限..."
usermod -aG audio unitree 2>/dev/null || echo "[警告] 无法加入 audio 组"
usermod -aG pulse-access unitree 2>/dev/null || echo "[警告] 无法加入 pulse-access 组"

echo ""
echo "[5/6] 设置 PulseAudio 运行时目录权限..."
mkdir -p /run/user/1000
chmod 700 /run/user/1000
chown unitree:unitree /run/user/1000

echo ""
echo "[6/6] 启动 PulseAudio..."
# 先杀掉旧进程
pulseaudio -k 2>/dev/null || true
sleep 1

# 启动 PulseAudio（不指定配置文件，使用默认）
sudo -u unitree XDG_RUNTIME_DIR=/run/user/1000 pulseaudio --daemonize --exit-idle-time=-1 2>&1 || \
pulseaudio --daemonize --exit-idle-time=-1 2>&1 || true

sleep 2

echo ""
echo "========================================="
echo "✅ 音频权限重置完成!"
echo "========================================="
echo ""
echo "验证步骤:"
echo "  1. pactl info"
echo "  2. arecord -l"
echo "  3. python3 -c \"import pyaudio; print('PyAudio OK')\""
echo ""
