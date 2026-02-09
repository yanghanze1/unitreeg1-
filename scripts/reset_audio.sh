#!/bin/bash
# 完全重置音频权限脚本
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
echo "[3/6] 创建宽松的 PulseAudio 系统配置..."
cat > /etc/pulse/daemon.conf << 'EOF'
daemonize = yes
fail = yes
allow-module-preload = yes
allow-exit = yes
use-pid-file = yes
system-instance = no
local-server-type = user
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
# 将 unitree 用户加入 audio 组
usermod -aG audio unitree 2>/dev/null || echo "[警告] 无法将 unitree 加入 audio 组"
usermod -aG pulse-access unitree 2>/dev/null || echo "[警告] 无法将 unitree 加入 pulse-access 组"
usermod -aG pulse 2>/dev/null || echo "[警告] 无法将 unitree 加入 pulse 组"

echo ""
echo "[5/6] 设置 PulseAudio 运行时目录权限..."
mkdir -p /run/user/1000
chmod 700 /run/user/1000
chown unitree:unitree /run/user/1000

echo ""
echo "[6/6] 启动 PulseAudio..."
# 以用户身份启动 PulseAudio
su - unitree -c "export XDG_RUNTIME_DIR=/run/user/1000 && pulseaudio --daemonize --exit-idle-time=-1" || \
pulseaudio --daemonize --exit-idle-time=-1

sleep 2

echo ""
echo "========================================="
echo "✅ 音频权限重置完成!"
echo "========================================="
echo ""
echo "验证步骤:"
echo "  1. 检查 PulseAudio: pactl info"
echo "  2. 测试麦克风: arecord -d 3 -f cd -r 48000 /tmp/test.wav"
echo "  3. 测试扬声器: aplay /tmp/test.wav"
echo ""
echo "如果还有问题，请运行:"
echo "  sudo chmod 777 /run/user/1000"
echo ""
