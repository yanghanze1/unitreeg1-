
import pytest
from unittest.mock import MagicMock
from VoiceInteraction.multimodal_interaction import try_execute_g1_by_local_keywords

class TestKeywords:
    
    def test_forward_command(self, mock_g1_client):
        """测试 '前进' 指令匹配。"""
        # Mock ActionManager
        action_manager = MagicMock()
        action_manager._running = True
        
        # Test "前进"
        text = "请向前进一点"
        result = try_execute_g1_by_local_keywords(text, action_manager)
        
        assert result is True
        action_manager.update_target_velocity.assert_called_once()
        kwargs = action_manager.update_target_velocity.call_args[1]
        assert kwargs["vx"] == 1.0

    def test_emergency_stop_command(self):
        """测试 '急停' 指令匹配 (最高优先级)。"""
        action_manager = MagicMock()
        action_manager._running = True
        
        text = "马上急停！"
        result = try_execute_g1_by_local_keywords(text, action_manager)
        
        assert result is True
        action_manager.emergency_stop.assert_called_once()

    def test_no_match(self):
        """测试无匹配指令的情况。"""
        action_manager = MagicMock()
        action_manager._running = True
        
        text = "今天天气不错"
        result = try_execute_g1_by_local_keywords(text, action_manager)
        
        assert result is False
        action_manager.update_target_velocity.assert_not_called()

    def test_manager_not_running(self):
        """测试 ActionManager 未运行时的行为。"""
        action_manager = MagicMock()
        action_manager._running = False
        
        result = try_execute_g1_by_local_keywords("前进", action_manager)
        
        assert result is False
        action_manager.update_target_velocity.assert_not_called()
