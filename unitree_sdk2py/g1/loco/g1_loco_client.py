import json

from ...rpc.client import Client
from .g1_loco_api import *

# FSM 状态常量定义（有限状态机状态ID）
FSM_ID_IDLE = 0           # 零力矩模式
FSM_ID_DAMP = 1           # 阻尼模式
FSM_ID_SIT = 3            # 坐下
FSM_ID_START = 200        # 启动站立
FSM_ID_RECOVERY = 702     # 从躺下恢复到站立
FSM_ID_SQUAT_UP = 706     # 深蹲起立

"""
" class SportClient
"""
class LocoClient(Client):
    def __init__(self):
        super().__init__(LOCO_SERVICE_NAME, False)
        self.first_shake_hand_stage_ = -1

    def Init(self):
        # set api version
        self._SetApiVerson(LOCO_API_VERSION)

        # regist api
        self._RegistApi(ROBOT_API_ID_LOCO_GET_FSM_ID, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_GET_FSM_MODE, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_GET_BALANCE_MODE, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_GET_SWING_HEIGHT, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_GET_STAND_HEIGHT, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_GET_PHASE, 0) # deprecated

        self._RegistApi(ROBOT_API_ID_LOCO_SET_FSM_ID, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_SET_BALANCE_MODE, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_SET_SWING_HEIGHT, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_SET_STAND_HEIGHT, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_SET_VELOCITY, 0)
        self._RegistApi(ROBOT_API_ID_LOCO_SET_ARM_TASK, 0)

    # 7101
    def SetFsmId(self, fsm_id: int):
        p = {}
        p["data"] = fsm_id
        parameter = json.dumps(p)
        code, data = self._Call(ROBOT_API_ID_LOCO_SET_FSM_ID, parameter)
        return code

    # 7102
    def SetBalanceMode(self, balance_mode: int):
        p = {}
        p["data"] = balance_mode
        parameter = json.dumps(p)
        code, data = self._Call(ROBOT_API_ID_LOCO_SET_BALANCE_MODE, parameter)
        return code

    # 7104
    def SetStandHeight(self, stand_height: float):
        p = {}
        p["data"] = stand_height
        parameter = json.dumps(p)
        code, data = self._Call(ROBOT_API_ID_LOCO_SET_STAND_HEIGHT, parameter)
        return code

    # 7105
    def SetVelocity(self, vx: float, vy: float, omega: float, duration: float = 1.0):
        p = {}
        velocity = [vx,vy,omega]
        p["velocity"] = velocity
        p["duration"] = duration
        parameter = json.dumps(p)
        code, data = self._Call(ROBOT_API_ID_LOCO_SET_VELOCITY, parameter)
        return code
    
    # 7106
    def SetTaskId(self, task_id: float):
        p = {}
        p["data"] = task_id
        parameter = json.dumps(p)
        code, data = self._Call(ROBOT_API_ID_LOCO_SET_ARM_TASK, parameter)
        return code

    # 7001
    def GetFsmId(self):
        """获取当前机器人 FSM 状态 ID
        
        Returns:
            int: 当前 FSM 状态 ID，失败时返回 -1
        """
        try:
            code, data = self._Call(ROBOT_API_ID_LOCO_GET_FSM_ID, "{}")  # 调用获取FSM状态API
            if code == 0:  # 调用成功
                result = json.loads(data)  # 解析返回的JSON数据
                return result.get("data", -1)  # 返回状态ID，默认-1表示失败
            else:
                return -1  # API调用失败，返回-1
        except Exception as e:
            print(f"[GetFsmId] 获取状态异常: {e}")  # 记录异常信息
            return -1  # 异常情况返回-1

    def Damp(self):
        self.SetFsmId(1)
    
    def Start(self):
        self.SetFsmId(200)

    def Squat2StandUp(self):
        self.SetFsmId(706)

    def Lie2StandUp(self):
        self.SetFsmId(702)

    def Sit(self):
        self.SetFsmId(3)

    def StandUp2Squat(self):
        self.SetFsmId(706)

    def ZeroTorque(self):
        self.SetFsmId(0)

    def RecoveryStand(self):
        """从异常状态（如躺下、摔倒）恢复到站立状态"""
        self.SetFsmId(FSM_ID_RECOVERY)  # 调用恢复站立FSM状态(702)

    def StopMove(self):
        self.SetVelocity(0., 0., 0.)

    def HighStand(self):
        UINT32_MAX = (1 << 32) - 1
        self.SetStandHeight(UINT32_MAX)

    def LowStand(self):
        UINT32_MIN = 0
        self.SetStandHeight(UINT32_MIN)

    def Move(self, vx: float, vy: float, vyaw: float, continous_move: bool = False):
        duration = 864000.0 if continous_move else 1
        self.SetVelocity(vx, vy, vyaw, duration)

    def BalanceStand(self, balance_mode: int):
        self.SetBalanceMode(balance_mode)

    def WaveHand(self, turn_flag: bool = False):
        self.SetTaskId(1 if turn_flag else 0)

    def ShakeHand(self, stage: int = -1):
        if stage == 0:
            self.first_shake_hand_stage_ = False
            self.SetTaskId(2)
        elif stage == 1:
            self.first_shake_hand_stage_ = True
            self.SetTaskId(3)
        else:
            self.first_shake_hand_stage_ = not self.first_shake_hand_stage_
            return self.SetTaskId(3 if self.first_shake_hand_stage_ else 2)
    