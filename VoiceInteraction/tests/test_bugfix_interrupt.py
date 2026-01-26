import unittest
from unittest.mock import MagicMock, patch
import threading
import time
import json
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from multimodal_interaction import MyCallback, set_flag, get_flag

class TestInterruptLogic(unittest.TestCase):
    def setUp(self):
        self.callback = MyCallback()
        self.callback.conversation = MagicMock()
        self.callback.action_manager = MagicMock()
        # Mock global config and tools
        patchER = patch.dict('multimodal_interaction.FUNCTION_CALLING_CONFIG', {'ENABLED': True})
        patchER.start()
        self.addCleanup(patchER.stop)
        
        # Reset flag
        set_flag(0)

    @patch('multimodal_interaction.call_qwen_for_tool_use')
    @patch('multimodal_interaction.execute_tool_call')
    def test_complex_interrupt_triggers_execution(self, mock_execute, mock_call_qwen):
        """测试在 Responding 状态下，复杂指令中断是否触发了执行逻辑"""
        
        # 1. Simulate Responding state
        self.callback._enter_response_mode()
        self.assertTrue(self.callback.is_responding())
        
        # Mock call_qwen to return a tool call
        mock_call_qwen.return_value = [{
            "name": "move_robot",
            "arguments": {"vx": 0.5, "vy": 0.0, "vyaw": 0.5, "duration": 2.0}
        }]
        
        mock_execute.return_value = {"status": "success", "message": "Moving"}

        # 2. Simulate User Input Event (Complex Command: "左转90度")
        # "90" regex matches \d+, so is_complex=True
        transcript = "左转90度"
        message = {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": transcript
        }
        
        # Mock player interrupt
        self.callback.player = MagicMock()
        
        # 3. Call execution
        # Note: on_event spawns a thread for _execute_tool_command, so we need to wait
        self.callback.on_event(message)
        
        # 4. Verify results
        # Wait a bit for thread
        time.sleep(1)
        
        # Verify player interrupt was called
        self.callback.player.interrupt.assert_called()
        
        # Verify tool logic was called
        mock_call_qwen.assert_called_with(transcript, unittest.mock.ANY)
        mock_execute.assert_called()
        
        # Verify response was aborted
        self.assertFalse(self.callback.is_responding(), "Should exit responding mode after interrupt")

    @patch('multimodal_interaction.call_qwen_for_tool_use')
    def test_simple_interrupt_does_not_trigger_execution(self, mock_call_qwen):
        """测试简单打断指令（如'闭嘴'）不触发工具执行"""
        self.callback._enter_response_mode()
        
        transcript = "闭嘴"
        message = {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": transcript
        }
        
        self.callback.on_event(message)
        
        time.sleep(0.5)
        # Should NOT call qwen for tools
        mock_call_qwen.assert_not_called()
        
    @patch('multimodal_interaction.call_qwen_for_tool_use') 
    def test_stop_command_safe_check(self, mock_call_qwen):
        """测试'急停'指令虽然包含复杂部分（假设），但因包含停止关键词，优先由安全检查处理，不走工具调用"""
        # "急停" is specific. Let's try "急停一下" -> "一下" is complex marker? "一" is blocked?
        # Let's use "向左急停" -> "向左" is simple? "急停" stop.
        # Let's try "急停并且报警" -> "并且" is complex. "急停" is stop.
        
        self.callback._enter_response_mode()
        transcript = "急停并且停止"
        message = {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": transcript
        }
        
        self.callback.on_event(message)
        time.sleep(0.5)
        
        # Should be handled by safety check, NOT tool call
        self.callback.action_manager.emergency_stop.assert_called()
        mock_call_qwen.assert_not_called()

if __name__ == '__main__':
    unittest.main()
