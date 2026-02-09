#!/bin/bash
# Audio Device Setup Script for Unitree G1 Robot
# 自动设定音频输入输出设备
# 跳过系统启动阶段，在用户登录后自动运行

set -e

echo "[Setup] 检查音频设备..."

# 检查 PulseAudio 是否可用
if ! pactl info &>/dev/null; then
    echo "[Setup] PulseAudio 不可用，跳过音频设备设定"
    echo "[Setup] 请在用户会话中手动运行: source /home/unitree/bk-main/scripts/setup_audio.sh"
    exit 0
fi

# 设置默认输入设备（USB 麦克风）
echo "[Setup] 设定默认输入设备..."
pactl set-default-source alsa_input.usb-Jieli_Technology_USB_Composite_Device_853A4D1988FD7053-00.mono-fallback 2>/dev/null || echo "[Setup] 警告: 无法设置输入设备"

# 设置默认输出设备（USB 扬声器）
echo "[Setup] 设定默认输出设备..."
pactl set-default-sink alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 2>/dev/null || echo "[Setup] 警告: 无法设置输出设备"

# 设置输出音量 100%
echo "[Setup] 设定音量..."
pactl set-sink-volume alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 100% 2>/dev/null || echo "[Setup] 警告: 无法设置音量"

echo "[Setup] 音频设备设定完成"
