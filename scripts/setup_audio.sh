#!/bin/bash
# Audio Device Setup Script for Unitree G1 Robot
# 自动设定音频输入输出设备

set -e

echo "[Setup] 正在设定音频设备..."

# 设置默认输入设备（USB 麦克风）
pactl set-default-source alsa_input.usb-Jieli_Technology_USB_Composite_Device_853A4D1988FD7053-00.mono-fallback

# 设置默认输出设备（USB 扬声器）
pactl set-default-sink alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo

# 设置输出音量 100%
pactl set-sink-volume alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 100%

echo "[Setup] 音频设备设定完成"
