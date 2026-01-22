# -*- coding: utf-8 -*-
"""
ActionManager 守护线程模块

功能: 维持 100Hz 高频心跳与 Unitree SDK 通信, 防止大模型推理时心跳超时
创建时间: 2026-1-20
"""

import threading  # 导入线程模块
import time  # 导入时间模块
import sys  # 导入系统模块
import traceback  # 导入堆栈追踪模块
import logging  # 导入日志模块
from enum import Enum  # 导入枚举类
from dataclasses import dataclass, field  # 导入数据类装饰器
from collections import deque  # 导入双端队列
from typing import Optional, Dict, Any  # 导入类型提示

# 配置日志: 移除 basicConfig, 避免与主程序冲突
logger = logging.getLogger(__name__)  # 创建日志记录器


class ActionType(Enum):
    """动作类型枚举"""
    IDLE = 0  # 空闲状态
    MOVE = 1  # 移动状态
    STOP = 2  # 停止状态
    EMERGENCY = 3  # 紧急停止状态


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class RobotTask:
    """机器人任务数据类"""
    task_id: str  # 任务唯一标识符
    task_type: str  # 任务类型：'move', 'rotate', 'stop'
    parameters: Dict[str, Any]  # 任务参数字典
    duration: float  # 持续时间（秒）
    status: TaskStatus = field(default=TaskStatus.PENDING)  # 任务状态，默认为待执行
    created_time: float = field(default_factory=time.time)  # 创建时间戳，默认为当前时间
    start_time: Optional[float] = None  # 开始执行时间戳
    end_time: Optional[float] = None  # 结束时间戳


class ActionManager:
    """
    动作管理器守护线程
    
    核心功能: 
    1. 以 100Hz 高频维持 SDK 心跳, 防止 Watchdog 超时
    2. 异步接收大模型的目标速度指令
    3. 提供急停与状态查询接口
    """
    
    def __init__(self, g1_client):
        """
        初始化动作管理器
        
        Args:
            g1_client: LocoClient 实例, 用于控制 G1 机器人
        """
        if g1_client is None:
            raise ValueError("g1_client 不能为 None")
            
        self.g1_client = g1_client  # 保存 G1 客户端实例
        
        # 线程安全的状态变量
        self._lock = threading.Lock()  # 创建线程锁保护共享状态
        self._target_vx = 0.0  # 目标前进速度(单位: m/s)
        self._target_vy = 0.0  # 目标横向速度(单位: m/s)
        self._target_vyaw = 0.0  # 目标旋转速度(单位: rad/s)
        self._current_action = ActionType.IDLE  # 当前动作类型
        self._emergency_flag = False  # 急停标志位
        
        # 控制循环相关
        self._running = False  # 控制循环运行标志
        self._control_thread = None  # 控制循环线程对象
        self._loop_count = 0  # 循环计数器, 用于日志输出频率控制
        
        # 自动停止相关
        self._move_start_time = 0.0  # 移动开始时间戳，用于计算运动持续时间
        self._move_duration = None  # None 表示持续移动, float 表示移动持续时间(秒)
        
        # 频率统计相关
        self._last_report_time = time.time()  # 上次输出频率统计日志的时间戳
        
        # 任务队列相关（新增）
        self._task_queue = deque()  # 任务队列，使用双端队列实现线程安全的FIFO
        self._current_task = None  # 当前正在执行的任务
        self._task_lock = threading.Lock()  # 任务队列专用锁
        self._next_task_id = 0  # 任务ID计数器
        self._task_executor_thread = None  # 任务执行器线程对象
        self._task_executor_running = False  # 任务执行器运行标志
        self._completed_tasks = {}  # 已完成任务的历史记录（task_id -> RobotTask）
        self._max_history_size = 100  # 最大历史记录数量，防止内存泄漏
        
        logger.info("ActionManager 初始化完成")  # 记录初始化日志
    
    def start(self):
        """启动控制循环守护线程"""
        if self._running:  # 检查是否已经在运行
            logger.warning("ActionManager 已经在运行中, 无需重复启动")  # 记录警告日志
            return  # 直接返回, 避免重复启动
        
        self._running = True  # 设置运行标志为 True
        
        # 启动控制循环线程
        self._control_thread = threading.Thread(
            target=self._control_loop,  # 设置线程执行的目标函数
            daemon=True,  # 设置为守护线程, 主线程退出时自动结束
            name="ActionManager-ControlLoop"  # 设置线程名称便于调试
        )
        self._control_thread.start()  # 启动线程
        logger.info("ActionManager 控制循环已启动(100Hz)")  # 记录启动日志
        
        # 启动任务执行器线程（新增）
        self._task_executor_running = True  # 设置任务执行器运行标志
        self._task_executor_thread = threading.Thread(
            target=self._task_executor_loop,  # 设置线程执行的目标函数
            daemon=True,  # 设置为守护线程
            name="ActionManager-TaskExecutor"  # 设置线程名称
        )
        self._task_executor_thread.start()  # 启动线程
        logger.info("ActionManager 任务执行器已启动")  # 记录启动日志
    
    def stop(self):
        """停止控制循环守护线程"""
        if not self._running:  # 检查是否在运行
            logger.warning("ActionManager 未在运行, 无需停止")  # 记录警告日志
            return  # 直接返回
        
        # 停止任务执行器线程（新增）
        if self._task_executor_running:  # 检查任务执行器是否在运行
            self._task_executor_running = False  # 设置运行标志为 False
            if self._task_executor_thread is not None:  # 检查线程对象是否存在
                self._task_executor_thread.join(timeout=2.0)  # 等待线程结束
                if self._task_executor_thread.is_alive():  # 检查线程是否真正退出
                    logger.error("⚠️ 任务执行器线程未能在2秒内退出！")  # 记录错误
                else:
                    logger.info("ActionManager 任务执行器已停止")  # 记录停止日志
        
        # 停止控制循环线程
        self._running = False  # 设置运行标志为 False, 通知控制循环退出
        
        if self._control_thread is not None:  # 检查线程对象是否存在
            self._control_thread.join(timeout=2.0)  # 等待线程结束, 最多等待 2 秒
            
            # 检查线程是否真正退出
            if self._control_thread.is_alive():
                logger.error("⚠️ 控制循环线程未能在2秒内退出, 可能存在死锁！")
                logger.error(f"线程状态: is_alive=True, daemon=True")
                # 记录堆栈跟踪以便调试
                for tid, frame in sys._current_frames().items():
                    if tid == self._control_thread.ident:
                        logger.error("线程堆栈: \n" + "".join(traceback.format_stack(frame)))
            else:
                logger.info("ActionManager 控制循环已停止")  # 记录停止日志
        
        # 停止前发送一次停止指令
        try:
            self.g1_client.Move(0.0, 0.0, 0.0)  # 调用 SDK 停止运动方法
            logger.info("已发送停止运动指令至机器人")  # 记录停止指令日志
        except Exception as e:  # 捕获异常
            logger.error(f"发送停止指令失败: {e}")  # 记录错误日志
    
    def update_target_velocity(self, vx: float, vy: float, vyaw: float, duration: float = None):
        """
        异步更新目标速度(大模型调用接口)
        
        Args:
            vx: 前进速度(单位: m/s, 范围: -1.0 ~ 1.0)
            vy: 横向速度(单位: m/s, 范围: -1.0 ~ 1.0)
            vyaw: 旋转速度(单位: rad/s, 范围: -1.5 ~ 1.5)
            duration: 持续时间(秒), None 表示持续移动直到收到新指令
        """
        # 参数验证与截断
        if not (-1.0 <= vx <= 1.0):
            logger.warning(f"vx 超出安全范围: {vx}, 已截断至 [-1.0, 1.0]")
            vx = max(-1.0, min(1.0, vx))
        
        if not (-1.0 <= vy <= 1.0):
            logger.warning(f"vy 超出安全范围: {vy}, 已截断至 [-1.0, 1.0]")
            vy = max(-1.0, min(1.0, vy))
        
        if not (-1.5 <= vyaw <= 1.5):
            logger.warning(f"vyaw 超出安全范围: {vyaw}, 已截断至 [-1.5, 1.5]")
            vyaw = max(-1.5, min(1.5, vyaw))

        with self._lock:  # 获取锁, 保证线程安全
            self._target_vx = vx  # 更新目标前进速度
            self._target_vy = vy  # 更新目标横向速度
            self._target_vyaw = vyaw  # 更新目标旋转速度
            self._current_action = ActionType.MOVE  # 设置当前动作类型为移动
            self._emergency_flag = False  # 清除急停标志
            
            # 设置持续时间和开始时间
            self._move_duration = duration  # 保存持续时间参数
            self._move_start_time = time.time() if duration else 0.0  # 仅当指定持续时间时记录开始时间戳
        
        logger.info(f"目标速度已更新: vx={vx:.2f}, vy={vy:.2f}, vyaw={vyaw:.2f}")  # 记录速度更新日志
    
    def emergency_stop(self):
        """紧急停止(最高优先级)"""
        # 清空任务队列（新增）
        self.clear_task_queue()  # 清空所有未执行的任务
        
        with self._lock:  # 获取锁, 保证线程安全
            self._target_vx = 0.0  # 将目标前进速度清零
            self._target_vy = 0.0  # 将目标横向速度清零
            self._target_vyaw = 0.0  # 将目标旋转速度清零
            self._current_action = ActionType.EMERGENCY  # 设置当前动作类型为紧急停止
            self._emergency_flag = True  # 设置急停标志为 True
        
        # 立即发送停止指令(不等待下一个控制循环周期)
        try:
            self.g1_client.Damp()  # 调用 SDK 阻尼模式(FSM ID=1)
            logger.warning("紧急停止已触发！机器人已切换至阻尼模式")  # 记录紧急停止日志
        except Exception as e:  # 捕获异常
            logger.error(f"紧急停止失败: {e}")  # 记录错误日志

    def recover_from_emergency(self) -> bool:
        """从紧急停止状态恢复"""
        with self._lock:
            if self._current_action != ActionType.EMERGENCY:
                logger.warning("当前不在紧急状态, 无需恢复")
                return False
            
            self._current_action = ActionType.IDLE
            self._emergency_flag = False
        
        try:
            # 重新启动FSM(优先尝试 RecoveryStand 以应对倒地情况)
            # self.g1_client.Start() 
            self.g1_client.Squat2StandUp()  # G1 专用起立指令
            logger.info("已从紧急停止状态恢复 (Squat2StandUp)")
            return True
        except Exception as e:
            logger.error(f"从紧急状态恢复失败: {e}")
            return False
    
    def set_idle(self):
        """设置为空闲状态(停止运动)"""
        with self._lock:  # 获取锁, 保证线程安全
            self._target_vx = 0.0  # 将目标前进速度清零
            self._target_vy = 0.0  # 将目标横向速度清零
            self._target_vyaw = 0.0  # 将目标旋转速度清零
            self._current_action = ActionType.IDLE  # 设置当前动作类型为空闲
            self._emergency_flag = False  # 清除急停标志
        
        logger.info("已切换至空闲状态")  # 记录状态切换日志
    
    def get_current_state(self) -> dict:
        """
        获取当前状态(线程安全)
        
        Returns:
            包含当前速度 动作类型 急停标志的字典
        """
        with self._lock:  # 获取锁, 保证线程安全
            state = {  # 构建状态字典
                "vx": self._target_vx,  # 当前目标前进速度
                "vy": self._target_vy,  # 当前目标横向速度
                "vyaw": self._target_vyaw,  # 当前目标旋转速度
                "action": self._current_action.name,  # 当前动作类型名称
                "emergency": self._emergency_flag  # 急停标志状态
            }
        return state  # 返回状态字典
    
    def _control_loop(self):
        """
        核心控制循环（运行在守护线程中）
        
        频率: 100Hz (10ms 间隔)
        功能: 发送 Move 命令以维持 SDK 心跳
        """
        logger.info("控制循环线程已启动")  # 记录控制循环启动日志
        
        loop_interval = 0.01  # 循环间隔时间(单位: 秒), 对应 100Hz
        next_target_time = time.time()  # 初始化基准时间锚点
        
        while self._running:  # 控制循环主体, 直到 _running 为 False
            # 基于绝对时间计算, 消除累积误差
            next_target_time += loop_interval
            
            try:
                # 获取当前目标速度(线程安全)
                with self._lock:  # 获取锁
                    vx = self._target_vx  # 读取目标前进速度
                    vy = self._target_vy  # 读取目标横向速度
                    vyaw = self._target_vyaw  # 读取目标旋转速度
                    action = self._current_action  # 读取当前动作类型
                
                # 发送控制指令至机器人
                if action == ActionType.EMERGENCY:  # 如果是紧急停止状态
                    self.g1_client.Damp()  # G1 维持阻尼状态
                
                elif action == ActionType.MOVE or action == ActionType.IDLE:  # 如果是移动或空闲状态
                    # 关键修复: 二次检查 EMERGENCY 状态, 防止竞态条件
                    # 如果在释放锁后的一瞬间变为 EMERGENCY, 这里会拦截
                    with self._lock:
                        if self._current_action == ActionType.EMERGENCY:
                            self.g1_client.Damp()
                            logger.warning("在指令发送前检测到急停信号, 已拦截移动指令")
                            continue  # 跳过本次循环的 Move 调用
                    
                    # 检查是否超时自动停止
                    if action == ActionType.MOVE:
                        with self._lock:
                            duration = self._move_duration
                            start_time = self._move_start_time
                        
                        if duration is not None and (time.time() - start_time > duration):  # 检查是否超过指定持续时间
                            self.set_idle()
                            logger.info(f"动作执行完成 ({duration}s), 自动切换至空闲状态")
                            # 移除 continue，确保本次循环发送 StopMove/0速度 以维持心跳

                    # 发送移动指令到G1机器人（由守护线程100Hz持续发送以维持心跳）
                    self.g1_client.Move(vx, vy, vyaw)  # 调用SDK Move方法
                
                # 循环计数器自增
                self._loop_count += 1  # 增加循环计数
                
                # 每秒输出一次状态日志(100次循环 = 1秒)
                # 优化: 改为每 10 秒输出一次 (1000次循环)
                if self._loop_count % 1000 == 0:  # 每 1000 次循环
                    # 优化频率计算公式: 使用两次报告间的实际时间差
                    current_time = time.time()
                    elapsed = current_time - self._last_report_time
                    actual_freq = 1000.0 / elapsed if elapsed > 0 else 0.0  # 计算实际循环频率(Hz)
                    self._last_report_time = current_time
                    
                    # 已禁用 FSM 状态查询（每次查询耗时较长，影响100Hz循环频率）
                    # fsm_id = -1
                    # try:
                        # fsm_id = self.g1_client.GetFsmId()
                    # except Exception:
                        # pass
                    
                    logger.info(
                        f"[心跳] 循环计数: {self._loop_count}, "  # 记录循环计数
                        f"频率: {actual_freq:.1f}Hz, "  # 记录实际频率
                        # f"FSM: {fsm_id}, "  # 记录机器人物理状态
                        f"状态: {action.name}, "  # 记录当前动作类型
                        f"速度: ({vx:.2f}, {vy:.2f}, {vyaw:.2f})"  # 记录当前速度
                    )
                
            except Exception as e:  # 捕获所有异常, 防止线程崩溃
                logger.error(f"控制循环异常: {e}", exc_info=True)  # 记录详细错误日志(包含堆栈)
            
            # 精确控制循环频率(基于绝对时间)
            current_time = time.time()
            sleep_time = next_target_time - current_time  # 计算由于耗时导致的剩余休眠时间
            
            if sleep_time > 0:  # 如果需要休眠
                time.sleep(sleep_time)  # 休眠指定时间
            else:  # 如果本次循环耗时超过目标周期
                lag = -sleep_time
                # 仅当滞后超过 100ms 时才重置锚点，允许轻微抖动自动追赶
                if lag > 0.1:  # 滞后超过100ms
                    logger.warning(f"循环严重滞后 {lag*1000:.1f}ms, 重置时间锚点")
                    next_target_time = current_time
                # 否则不重置，下一次循环将尝试追赶
        
        logger.info("控制循环线程已退出")  # 记录控制循环退出日志
    
    # ==================== 任务队列管理方法（新增） ====================
    
    def add_task(self, task_type: str, parameters: Dict[str, Any], duration: float) -> str:
        """
        添加任务到执行队列
        
        Args:
            task_type: 任务类型 ('move', 'rotate', 'stop')
            parameters: 任务参数字典
            duration: 持续时间（秒）
            
        Returns:
            task_id: 任务唯一标识符
        """
        with self._task_lock:  # 获取任务队列锁
            task_id = f"task_{self._next_task_id}"  # 生成任务ID
            self._next_task_id += 1  # ID计数器自增
            
            # 创建任务对象
            task = RobotTask(
                task_id=task_id,  # 任务ID
                task_type=task_type,  # 任务类型
                parameters=parameters,  # 任务参数
                duration=duration,  # 持续时间
                status=TaskStatus.PENDING  # 初始状态为待执行
            )
            
            # 添加到队列
            self._task_queue.append(task)  # 加入队列末尾
            logger.info(f"[TaskQueue] 任务已添加: {task_id} ({task_type}), 队列长度: {len(self._task_queue)}")  # 记录日志
        
        return task_id  # 返回任务ID
    
    def clear_task_queue(self) -> int:
        """
        清空任务队列（用于急停或打断）
        
        Returns:
            清空的任务数量
        """
        with self._task_lock:  # 获取任务队列锁
            # 将所有未执行的任务标记为已取消
            cancelled_count = 0  # 取消计数器
            while self._task_queue:  # 遍历队列
                task = self._task_queue.popleft()  # 从队列头部取出任务
                task.status = TaskStatus.CANCELLED  # 标记为已取消
                task.end_time = time.time()  # 记录取消时间
                self._completed_tasks[task.task_id] = task  # 保存到历史记录
                cancelled_count += 1  # 计数器增加
            
            # 如果当前有正在执行的任务，也标记为取消
            if self._current_task:  # 检查当前任务
                self._current_task.status = TaskStatus.CANCELLED  # 标记为已取消
                self._current_task.end_time = time.time()  # 记录取消时间
                self._completed_tasks[self._current_task.task_id] = self._current_task  # 保存到历史记录
                self._current_task = None  # 清空当前任务
                logger.info(f"[TaskQueue] 当前任务已取消")  # 记录日志
            
            logger.info(f"[TaskQueue] 队列已清空，共取消 {cancelled_count} 个待执行任务")  # 记录日志
        
        return cancelled_count  # 返回取消的任务数量
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        查询任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态字典，包含 task_id, task_type, status, created_time等信息
            如果任务不存在，返回 None
        """
        with self._task_lock:  # 获取任务队列锁
            # 检查当前任务
            if self._current_task and self._current_task.task_id == task_id:  # 如果是当前任务
                return self._task_to_dict(self._current_task)  # 返回任务信息
            
            # 检查队列中的任务
            for task in self._task_queue:  # 遍历队列
                if task.task_id == task_id:  # 找到目标任务
                    return self._task_to_dict(task)  # 返回任务信息
            
            # 检查已完成的任务
            if task_id in self._completed_tasks:  # 检查历史记录
                return self._task_to_dict(self._completed_tasks[task_id])  # 返回任务信息
        
        return None  # 任务不存在，返回None
    
    def _task_to_dict(self, task: RobotTask) -> Dict[str, Any]:
        """
        将 RobotTask 对象转换为字典格式
        
        Args:
            task: RobotTask 对象
            
        Returns:
            任务信息字典
        """
        return {
            "task_id": task.task_id,  # 任务ID
            "task_type": task.task_type,  # 任务类型
            "parameters": task.parameters,  # 任务参数
            "duration": task.duration,  # 持续时间
            "status": task.status.value,  # 任务状态（转换为字符串）
            "created_time": task.created_time,  # 创建时间
            "start_time": task.start_time,  # 开始时间
            "end_time": task.end_time  # 结束时间
        }
    
    def _task_executor_loop(self):
        """
        任务执行器线程（独立于100Hz控制循环）
        
        功能：
        1. 从任务队列中取出任务
        2. 顺序执行每个任务
        3. 更新任务状态
        4. 支持任务超时保护
        """
        logger.info("[TaskExecutor] 任务执行器线程已启动")  # 记录启动日志
        
        while self._task_executor_running:  # 主循环
            try:
                current_task = None  # 初始化当前任务
                
                # 从队列中取出任务（线程安全）
                with self._task_lock:  # 获取任务队列锁
                    if len(self._task_queue) > 0:  # 检查队列是否有任务
                        current_task = self._task_queue.popleft()  # 从队列头部取出任务
                        self._current_task = current_task  # 设置为当前任务
                        current_task.status = TaskStatus.RUNNING  # 标记为执行中
                        current_task.start_time = time.time()  # 记录开始时间
                
                # 如果有任务，执行它
                if current_task:  # 检查是否取到任务
                    logger.info(f"[TaskExecutor] 开始执行任务: {current_task.task_id} ({current_task.task_type})")  # 记录日志
                    
                    try:
                        # 根据任务类型执行相应操作
                        if current_task.task_type == "move":  # 移动任务
                            self._execute_move_task(current_task)  # 执行移动任务
                        
                        elif current_task.task_type == "rotate":  # 旋转任务
                            self._execute_rotate_task(current_task)  # 执行旋转任务
                        
                        elif current_task.task_type == "stop":  # 停止任务
                            self._execute_stop_task(current_task)  # 执行停止任务
                        
                        else:  # 未知任务类型
                            logger.error(f"[TaskExecutor] 未知任务类型: {current_task.task_type}")  # 记录错误
                            current_task.status = TaskStatus.FAILED  # 标记为失败
                        
                        # 任务执行完成
                        if current_task.status == TaskStatus.RUNNING:  # 如果仍在执行中（未被取消）
                            current_task.status = TaskStatus.COMPLETED  # 标记为已完成
                            logger.info(f"[TaskExecutor] 任务完成: {current_task.task_id}")  # 记录日志
                    
                    except Exception as e:  # 捕获任务执行异常
                        logger.error(f"[TaskExecutor] 任务执行失败: {current_task.task_id}, 错误: {e}", exc_info=True)  # 记录错误
                        current_task.status = TaskStatus.FAILED  # 标记为失败
                    
                    finally:  # 无论成功或失败都执行
                        current_task.end_time = time.time()  # 记录结束时间
                        
                        # 保存到历史记录（线程安全）
                        with self._task_lock:  # 获取任务队列锁
                            self._completed_tasks[current_task.task_id] = current_task  # 保存到历史记录
                            self._current_task = None  # 清空当前任务
                            
                            # 限制历史记录大小，防止内存泄漏
                            if len(self._completed_tasks) > self._max_history_size:  # 检查历史记录大小
                                # 移除最早的任务记录
                                oldest_task_id = min(self._completed_tasks.keys(), key=lambda k: self._completed_tasks[k].created_time)  # 找到最早的任务
                                del self._completed_tasks[oldest_task_id]  # 删除
                
                else:  # 队列为空
                    time.sleep(0.05)  # 休眠50ms，避免空转消耗CPU
            
            except Exception as e:  # 捕获所有异常
                logger.error(f"[TaskExecutor] 执行器循环异常: {e}", exc_info=True)  # 记录错误
                time.sleep(0.1)  # 发生异常时休眠100ms
        
        logger.info("[TaskExecutor] 任务执行器线程已退出")  # 记录退出日志
    
    def _execute_move_task(self, task: RobotTask):
        """
        执行移动任务
        
        Args:
            task: RobotTask 对象
        """
        params = task.parameters  # 获取任务参数
        vx = params.get("vx", 0.0)  # 前进速度
        vy = params.get("vy", 0.0)  # 横向速度
        vyaw = params.get("vyaw", 0.0)  # 旋转速度
        duration = task.duration  # 持续时间
        
        logger.info(f"[TaskExecutor] 移动: vx={vx:.2f}, vy={vy:.2f}, vyaw={vyaw:.2f}, duration={duration:.2f}s")  # 记录日志
        
        # 调用现有的控制接口
        self.update_target_velocity(vx, vy, vyaw, duration)  # 设置目标速度
        
        # 等待执行完成
        time.sleep(duration)  # 休眠等待
    
    def _execute_rotate_task(self, task: RobotTask):
        """
        执行旋转任务
        
        Args:
            task: RobotTask 对象
        """
        params = task.parameters  # 获取任务参数
        vyaw = params.get("vyaw", 0.0)  # 旋转速度
        duration = task.duration  # 持续时间
        
        logger.info(f"[TaskExecutor] 旋转: vyaw={vyaw:.2f}, duration={duration:.2f}s")  # 记录日志
        
        # 调用现有的控制接口
        self.update_target_velocity(0.0, 0.0, vyaw, duration)  # 设置旋转速度
        
        # 等待执行完成
        time.sleep(duration)  # 休眠等待
    
    def _execute_stop_task(self, task: RobotTask):
        """
        执行停止任务
        
        Args:
            task: RobotTask 对象
        """
        logger.info(f"[TaskExecutor] 停止机器人")  # 记录日志
        self.set_idle()  # 调用停止方法

