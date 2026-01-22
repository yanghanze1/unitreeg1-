# -*- coding: utf-8 -*-
"""
测试 tool_schema.py 工具定义模块
验证工具 Schema 格式正确性和完整性
"""

import pytest
from VoiceInteraction.tool_schema import (
    ROBOT_TOOLS,
    TOOL_MOVE_ROBOT,
    TOOL_STOP_ROBOT,
    TOOL_ROTATE_ANGLE,
    TOOL_EMERGENCY_STOP,
    TOOL_NAME_CN
)
from VoiceInteraction.config import SAFETY_CONFIG


class TestToolSchemaFormat:
    """测试工具 Schema 格式正确性"""
    
    def test_robot_tools_is_list(self):
        """验证 ROBOT_TOOLS 是列表"""
        assert isinstance(ROBOT_TOOLS, list)  # 确保是列表类型
        assert len(ROBOT_TOOLS) > 0  # 至少包含一个工具
    
    def test_all_tools_have_required_fields(self):
        """验证所有工具都包含必需字段"""
        for tool in ROBOT_TOOLS:
            assert "type" in tool  # 必须有 type 字段
            assert tool["type"] == "function"  # type 必须是 function
            assert "function" in tool  # 必须有 function 字段
            
            func = tool["function"]
            assert "name" in func  # 必须有 name 字段
            assert "description" in func  # 必须有 description 字段
            assert "parameters" in func  # 必须有 parameters 字段
    
    def test_tool_parameters_format(self):
        """验证工具参数格式正确"""
        for tool in ROBOT_TOOLS:
            params = tool["function"]["parameters"]
            assert "type" in params  # 参数必须有 type 字段
            assert params["type"] == "object"  # 参数类型必须是 object
            assert "properties" in params  # 必须有 properties 字段


class TestMoveRobotTool:
    """测试 move_robot 工具定义"""
    
    def test_move_robot_name(self):
        """验证工具名称"""
        assert TOOL_MOVE_ROBOT["function"]["name"] == "move_robot"  # 名称应为 move_robot
    
    def test_move_robot_has_required_params(self):
        """验证必需参数已定义"""
        params = TOOL_MOVE_ROBOT["function"]["parameters"]
        required = params.get("required", [])
        
        assert "vx" in required  # vx 是必需参数
        assert "vy" in required  # vy 是必需参数
        assert "vyaw" in required  # vyaw 是必需参数
    
    def test_move_robot_param_descriptions(self):
        """验证参数描述包含范围信息"""
        props = TOOL_MOVE_ROBOT["function"]["parameters"]["properties"]
        
        assert "vx" in props  # vx 参数必须存在
        assert "description" in props["vx"]  # vx 必须有描述
        assert str(SAFETY_CONFIG['MAX_SAFE_SPEED_VX']) in props["vx"]["description"]  # 描述中应包含最大速度值
        
        assert "vyaw" in props  # vyaw 参数必须存在
        assert "description" in props["vyaw"]  # vyaw 必须有描述
        assert str(SAFETY_CONFIG['MAX_SAFE_OMEGA']) in props["vyaw"]["description"]  # 描述中应包含最大角速度值


class TestRotateAngleTool:
    """测试 rotate_angle 工具定义"""
    
    def test_rotate_angle_name(self):
        """验证工具名称"""
        assert TOOL_ROTATE_ANGLE["function"]["name"] == "rotate_angle"  # 名称应为 rotate_angle
    
    def test_rotate_angle_has_degrees_param(self):
        """验证 degrees 参数已定义"""
        params = TOOL_ROTATE_ANGLE["function"]["parameters"]
        required = params.get("required", [])
        props = params["properties"]
        
        assert "degrees" in required  # degrees 是必需参数
        assert "degrees" in props  # degrees 参数必须存在
        assert "type" in props["degrees"]  # degrees 必须有类型定义
        assert props["degrees"]["type"] == "number"  # degrees 类型必须是 number


class TestStopRobotTool:
    """测试 stop_robot 工具定义"""
    
    def test_stop_robot_name(self):
        """验证工具名称"""
        assert TOOL_STOP_ROBOT["function"]["name"] == "stop_robot"  # 名称应为 stop_robot
    
    def test_stop_robot_no_params(self):
        """验证停止工具无参数"""
        props = TOOL_STOP_ROBOT["function"]["parameters"]["properties"]
        assert len(props) == 0  # 停止工具不应有参数


class TestEmergencyStopTool:
    """测试 emergency_stop 工具定义"""
    
    def test_emergency_stop_name(self):
        """验证工具名称"""
        assert TOOL_EMERGENCY_STOP["function"]["name"] == "emergency_stop"  # 名称应为 emergency_stop
    
    def test_emergency_stop_no_params(self):
        """验证紧急停止工具无参数"""
        props = TOOL_EMERGENCY_STOP["function"]["parameters"]["properties"]
        assert len(props) == 0  # 紧急停止工具不应有参数


class TestToolNameMapping:
    """测试工具名称映射"""
    
    def test_all_tools_have_cn_name(self):
        """验证所有工具都有中文名称映射"""
        for tool in ROBOT_TOOLS:
            tool_name = tool["function"]["name"]
            assert tool_name in TOOL_NAME_CN  # 每个工具都应有中文名称
            assert isinstance(TOOL_NAME_CN[tool_name], str)  # 中文名称应为字符串
            assert len(TOOL_NAME_CN[tool_name]) > 0  # 中文名称不应为空
    
    def test_cn_names_are_meaningful(self):
        """验证中文名称有意义"""
        assert "移动" in TOOL_NAME_CN["move_robot"]  # move_robot 应包含"移动"
        assert "停止" in TOOL_NAME_CN["stop_robot"]  # stop_robot 应包含"停止"
        assert "旋转" in TOOL_NAME_CN["rotate_angle"] or "角度" in TOOL_NAME_CN["rotate_angle"]  # rotate_angle 应包含"旋转"或"角度"
        assert "紧急" in TOOL_NAME_CN["emergency_stop"] or "急停" in TOOL_NAME_CN["emergency_stop"]  # emergency_stop 应包含"紧急"或"急停"
