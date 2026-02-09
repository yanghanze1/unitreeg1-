# -*- coding: utf-8 -*-
"""
键盘急停监听模块 (SSH/Headless 版)

功能: 监听终端键盘按键，提供物理急停能力。
      专为 SSH 远程连接或无头模式设计，不依赖图形界面 (X Server)。
修改时间: 2026-1-21
"""

import threading
import logging
import sys
import platform
import time  # 移至顶部：避免在循环内部重复导入

# 根据操作系统导入不同的键盘监听库
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import msvcrt
else:
    import termios
    import tty
    import select

# 配置日志记录器
logger = logging.getLogger(__name__)

def start_keyboard_listener(action_manager, g1_client):
    """
    启动终端键盘监听线程
    
    注意：在 SSH 模式下，必须保持终端窗口处于激活状态按键才有效。
    """
    logger.info("[EmergencyStop] 正在启动终端键盘监听线程...")
    
    # 创建并启动守护线程
    t = threading.Thread(
        target=_monitor_terminal_input,
        args=(action_manager, g1_client),
        daemon=True  # 守护线程，主程序退出时自动关闭
    )
    t.start()
    
    logger.info("[EmergencyStop] 键盘监听已启动 (请保持终端窗口激活，按 Space 键急停)")
    return t

def _monitor_terminal_input(action_manager, g1_client):
    """
    监听标准输入流 (stdin) 的空格键
    支持 Windows (msvcrt) 和 Linux (termios)
    """
    if IS_WINDOWS:
        _monitor_windows(action_manager, g1_client)
    else:
        _monitor_linux(action_manager, g1_client)

def _monitor_windows(action_manager, g1_client):
    """Windows 平台监听逻辑"""
    try:
        while True:
            # kbhit() 检测是否有按键按下
            if msvcrt.kbhit():
                # getch() 读取一个字符（字节）
                key = msvcrt.getch()
                try:
                    char_key = key.decode('utf-8')
                except:
                    continue
                
                if char_key == ' ':
                    _trigger_emergency_stop(action_manager, g1_client)
            else:
                time.sleep(0.1)  # time 已在文件顶部导入
    except Exception as e:
        logger.error(f"[EmergencyStop] Windows 监听异常: {e}")

def _monitor_linux(action_manager, g1_client):
    """Linux 平台监听逻辑"""
    # 获取标准输入的文件描述符
    fd = sys.stdin.fileno()
    
    # 保存旧的终端设置，以便退出时恢复
    old_settings = termios.tcgetattr(fd)
    
    try:
        # 将终端设置为 cbreak 模式：不需要按回车就能读取字符，但保留 Ctrl+C 功能
        tty.setcbreak(fd)
        
        while True:
            # 使用 select 检测是否有输入，避免阻塞 CPU
            if select.select([sys.stdin], [], [], 0.1)[0]:
                key = sys.stdin.read(1) # 读取一个字符
                
                # 检测空格键 (Space)
                if key == ' ':
                    _trigger_emergency_stop(action_manager, g1_client)
                    
    except Exception as e:
        logger.error(f"[EmergencyStop] Linux 监听异常: {e}")
    finally:
        # 非常重要：程序结束前必须恢复终端设置，否则终端会乱码
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def _trigger_emergency_stop(action_manager, g1_client):
    """执行急停逻辑"""
    logger.warning("=" * 60)
    logger.warning("[EmergencyStop] 检测到 Space 键，执行紧急停止！")
    logger.warning("=" * 60)

    try:
        # 1. ActionManager 急停
        if action_manager:
            action_manager.emergency_stop()
            logger.info("[EmergencyStop] ActionManager 急停已触发")
        
        # 2. SDK 直接阻尼 (双重保险)
        if g1_client:
            g1_client.Damp()
            logger.info("[EmergencyStop] SDK Damp 模式已激活（双重保险）")
            
        logger.warning("[EmergencyStop] 紧急停止完成，机器人已进入安全状态")
        
    except Exception as e:
        logger.error(f"[EmergencyStop] 执行急停失败: {e}")