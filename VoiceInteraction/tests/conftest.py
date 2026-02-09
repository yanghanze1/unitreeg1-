
import pytest
from unittest.mock import MagicMock
import sys
import logging

# --- 导入时模块补丁 (Top-level Patching) ---
# 必须在测试收集之前运行 (即在测试文件导入模块之前)
def _patch_modules():
    modules_to_mock = ["unitree_sdk2py", "pyaudio", "dashscope", "opencv-python", "cv2"]
    
    for mod_name in modules_to_mock:
        try:
            __import__(mod_name)
        except ImportError:
            if mod_name not in sys.modules:
                mock_module = MagicMock()
                sys.modules[mod_name] = mock_module
                
                # Mock 特定的子模块，允许 "from x import y" 写法
                if mod_name == "unitree_sdk2py":
                    sys.modules["unitree_sdk2py.core"] = MagicMock()
                    sys.modules["unitree_sdk2py.core.channel"] = MagicMock()
                    sys.modules["unitree_sdk2py.go1"] = MagicMock()
                    sys.modules["unitree_sdk2py.go1.locals"] = MagicMock()
                
                if mod_name == "dashscope":
                    sys.modules["dashscope.audio"] = MagicMock()
                    sys.modules["dashscope.audio.qwen_omni"] = MagicMock()

_patch_modules() # 执行补丁

# --- Fixtures (测试夹具) ---

@pytest.fixture(autouse=True)
def configure_logging():
    """配置日志格式 (自动使用)"""
    logging.basicConfig(level=logging.INFO)

@pytest.fixture
def mock_g1_client():
    """创建一个模拟的 G1 LocoClient 对象。"""
    client = MagicMock()
    return client
