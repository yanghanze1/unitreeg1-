#!/bin/bash
# Audio Device Setup Script for Unitree G1 Robot
# 自动设定音频输入输出设备

set -e

echo "[Setup] 检查并设定音频设备..."

# 检查 PulseAudio 是否运行
if pactl info &>/dev/null; then
    echo "[Setup] PulseAudio 运行中，设定音频设备..."
    
    # 设置默认输入设备（USB 麦克风）
    pactl set-default-source alsa_input.usb-Jieli_Technology_USB_Composite_Device_853A4D1988FD7053-00.mono-fallback 2>/dev/null && \
        echo "[Setup] 默认输入设备已设置" || \
        echo "[Setup] 警告: 无法设置默认输入设备"
    
    # 设置默认输出设备（USB 扬声器）
    pactl set-default-sink alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 2>/dev/null && \
        echo "[Setup] 默认输出设备已设置" || \
        echo "[Setup] 警告: 无法设置默认输出设备"
    
    # 设置输出音量 100%
    pactl set-sink-volume alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 100% 2>/dev/null && \
        echo "[Setup] 音量已设置为 100%" || \
        echo "[Setup] 警告: 无法设置音量"
    
    echo "[Setup] 音频设备设定完成"
else
    echo "[Setup] PulseAudio 不可用，跳过设备设定"
    echo "[Setup] 程序将使用默认音频设备"
fi

echo "[Setup] 启动语音交互程序..."
