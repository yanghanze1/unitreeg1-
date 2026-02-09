# API配置文件
# 大语言模型API配置
# ⚠️ 安全警告：请勿将真实 API Key 提交到代码仓库！
# 请优先使用环境变量设置 API Key，例如：export DASHSCOPE_API_KEY="sk-..."

# 阿里云通义千问API配置
QWEN_API_CONFIG = {
    'api_key': 'sk-2a523e5c07dd4a0b9993ba36242a1f38',  # 请替换为您的API密钥，或使用环境变量
    'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'model_name': 'qwen-turbo-latest'  # 可选: qwen-max, qwen-plus, qwen-turbo
}

# OpenAI API配置 (备用)
OPENAI_API_CONFIG = {
    'api_key': 'YOUR_OPENAI_API_KEY',
    'base_url': 'https://api.openai.com/v1',
    'model_name': 'gpt-3.5-turbo'
}

# 硅基流动api配置
SILICON_FLOW_API_CONFIG = {
    'api_key': 'sk-qdzcjjfrcvnqglbpuptgtqedqtwtvtrmgwbcfxevwndukbtd',
    'base_url': 'https://api.siliconflow.cn/v1',
    'model_voice': 'FunAudioLLM/CosyVoice2-0.5B', 
    'voice_name': 'FunAudioLLM/CosyVoice2-0.5B:david'
}


# 其他API配置
OTHER_API_CONFIG = {
    'api_key': 'your-api-key',
    'base_url': 'your-base-url',
    'model_name': 'your-model-name'
}

# 默认使用的配置
DEFAULT_CONFIG = QWEN_API_CONFIG
