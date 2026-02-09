#!/bin/bash
# 麦克风诊断和修复脚本

echo "===== 麦克风诊断 ====="

echo ""
echo "1. 检查 PulseAudio 状态..."
pactl info | grep -E "(Server|Default Source|Default Sink)"

echo ""
echo "2. 检查 ALSA 设备..."
arecord -l 2>&1 | head -5

echo ""
echo "3. 杀掉可能占用麦克风的进程..."
# 杀掉可能占用麦克风的进程
pkill -9 -f multimodal 2>/dev/null || true
pulseaudio -k 2>/dev/null || true
sleep 2

echo ""
echo "4. 重启 PulseAudio..."
# 以用户身份启动 PulseAudio
sudo -u unitree XDG_RUNTIME_DIR=/run/user/1000 pulseaudio --daemonize --exit-idle-time=-1 2>/dev/null || \
pulseaudio --daemonize --exit-idle-time=-1 2>/dev/null || true
sleep 2

echo ""
echo "5. 设置音频设备..."
# 设置麦克风（Jieli USB）
pactl set-default-source alsa_input.usb-Jieli_Technology_USB_Composite_Device_853A4D1988FD7053-00.mono-fallback 2>/dev/null && echo "✓ 麦克风已设置为 Jieli USB"

# 设置扬声器
pactl set-default-sink alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 2>/dev/null && echo "✓ 扬声器已设置为 C-Media USB"

echo ""
echo "6. 测试麦克风..."
# 尝试直接用 ALSA 设备录音
timeout 2 arecord -D hw:1 -f cd -r 48000 -c 1 /tmp/mic_test.wav 2>&1 && echo "✓ ALSA 录音成功" || echo "✗ ALSA 录音失败"

echo ""
echo "7. 检查 PyAudio 设备..."
# 列出 PyAudio 可见的设备
python3 << 'PYEOF'
import pyaudio
p = pyaudio.PyAudio()
print("\n可用音频输入设备:")
for i in range(min(10, p.get_device_count())):
    try:
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            default = " (默认)" if i == p.get_default_input_device_info()['index'] else ""
            print(f"  [{i}] {info['name']}{default}")
    except:
        pass
p.terminate()
PYEOF

echo ""
echo "===== 完成 ====="
echo ""
echo "如果 ALSA 录音失败，可能是设备被占用或权限问题。"
echo "请尝试手动运行: pulseaudio -k && sleep 2 && pulseaudio --daemonize"
