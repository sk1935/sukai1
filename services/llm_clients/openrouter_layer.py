"""
OpenRouter Layer：免费模型调用层

功能：
- 使用 OpenRouter API 调用免费模型
- 仅允许白名单内的模型（防止误调用付费模型）
- 异步调用、异常处理、超时控制
- JSON 格式清洗和标准化返回

输入：模型名称、提示词
输出：标准预测结果字典 {probability, confidence, reasoning}
"""
import os
import json
import re
from typing import Dict, Optional
from datetime import datetime
from dotenv import load_dotenv

# 使用 httpx 替代 aiohttp（更现代的异步 HTTP 客户端）
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

load_dotenv()

# 免费模型白名单（OpenRouter）
FREE_MODELS = [
    "mistralai/mistral-7b-instruct",
    "meta-llama/llama-3-70b-instruct",
    "yi-large/yi-1.5-chat",
    "nousresearch/hermes-3-llama-3-8b",
    "openchat/openchat-3.5"
]

# OpenRouter API 端点
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 30.0

# 模型超时配置（基于实际响应速度）
MODEL_TIMEOUTS = {
    "mistralai/mistral-7b-instruct": 25.0,
    "meta-llama/llama-3-70b-instruct": 35.0,
    "yi-large/yi-1.5-chat": 30.0,
    "nousresearch/hermes-3-llama-3-8b": 25.0,
    "openchat/openchat-3.5": 25.0
}


class ModelPrediction:
    """
    标准模型预测结果对象（用于类型提示）
    
    实际返回为字典格式，与现有系统保持一致
    """
    def __init__(self, probability: float, confidence: str, reasoning: str):
        self.probability = probability
        self.confidence = confidence
        self.reasoning = reasoning
    
    def to_dict(self) -> Dict:
        """转换为字典格式（与现有系统兼容）"""
        return {
            "probability": self.probability,
            "confidence": self.confidence,
            "reasoning": self.reasoning
        }


def validate_model(model: str) -> bool:
    """
    验证模型是否在白名单中
    
    Args:
        model: 模型名称
        
    Returns:
        True if model is in whitelist, False otherwise
    """
    return model in FREE_MODELS


def get_model_timeout(model: str) -> float:
    """
    获取模型的自适应超时时间
    
    Args:
        model: 模型名称
        
    Returns:
        超时时间（秒）
    """
    return MODEL_TIMEOUTS.get(model, DEFAULT_TIMEOUT)


def clean_json_response(content: str) -> Optional[Dict]:
    """
    清洗和解析 JSON 格式的模型响应
    
    Args:
        content: 原始响应内容
        
    Returns:
        解析后的 JSON 字典，或 None 如果解析失败
    """
    if not content or not content.strip():
        return None
    
    try:
        original_content = content.strip()
        
        # 提取 JSON 代码块
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end != -1:
                content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end != -1:
                content = content[start:end].strip()
        
        # 查找 JSON 对象
        start_brace = content.find("{")
        end_brace = content.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            content = content[start_brace:end_brace + 1]
        
        # 解析 JSON
        data = json.loads(content)
        
        # 验证和标准化字段
        # 支持多种可能的字段名
        prob = None
        for key in ["prob_yes", "probability", "prob", "prediction"]:
            if key in data:
                prob = float(data.get(key))
                break
        
        if prob is None:
            # 尝试从文本中提取
            prob_match = re.search(r'(?:probability|prob_yes|prediction)[":\s]+(\d+\.?\d*)', original_content, re.IGNORECASE)
            if prob_match:
                prob = float(prob_match.group(1))
            else:
                prob = 50.0  # 默认值
        
        # 限制概率范围
        prob = max(0.0, min(100.0, prob))
        
        # 获取置信度
        confidence = data.get("confidence", "medium").lower()
        if confidence not in ["low", "medium", "high"]:
            confidence = "medium"
        
        # 获取理由（支持多种字段名）
        reasoning = (
            data.get("rationale") or 
            data.get("reasoning") or 
            data.get("explanation") or 
            data.get("reason") or
            "No reasoning provided."
        )
        
        # 截断过长的理由
        if len(reasoning) > 200:
            reasoning = reasoning[:197] + "..."
        
        return {
            "probability": prob,
            "confidence": confidence,
            "reasoning": reasoning
        }
        
    except json.JSONDecodeError as e:
        print(f"⚠️ [OpenRouter] JSON decode error: {e}")
        # 尝试从文本中提取概率
        prob_match = re.search(r'(?:probability|prob_yes|prediction)[":\s]+(\d+\.?\d*)', original_content, re.IGNORECASE)
        if prob_match:
            try:
                prob = float(prob_match.group(1))
                prob = max(0.0, min(100.0, prob))
                print(f"✅ [OpenRouter] Extracted probability from text: {prob}%")
                return {
                    "probability": prob,
                    "confidence": "medium",
                    "reasoning": "Parsed from unstructured response."
                }
            except:
                pass
        return None
        
    except Exception as e:
        print(f"⚠️ [OpenRouter] Error cleaning JSON response: {e}")
        return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, httpx.RequestError))
)
async def call_openrouter_model(model: str, prompt: str) -> Optional[Dict]:
    """
    调用 OpenRouter API 的异步函数
    
    Args:
        model: 模型名称（必须在 FREE_MODELS 白名单中）
        prompt: 提示词
        
    Returns:
        标准预测结果字典 {probability, confidence, reasoning}，或 None 如果失败
        
    Raises:
        ValueError: 如果模型不在白名单中
    """
    # 验证模型在白名单中
    if not validate_model(model):
        raise ValueError(
            f"模型 '{model}' 不在免费模型白名单中。"
            f"允许的模型: {', '.join(FREE_MODELS)}"
        )
    
    # 获取 API 密钥
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("⚠️ [OpenRouter] OPENROUTER_API_KEY 未设置，跳过调用")
        return None
    
    # 获取超时时间
    timeout_seconds = get_model_timeout(model)
    
    # 构建请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://polymarket-predictor.com",  # Optional: for analytics
        "X-Title": "Polymarket AI Predictor"  # Optional: for analytics
    }
    
    # 构建请求体
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }
    
    print(f"📡 [OpenRouter] Calling {model} (timeout: {timeout_seconds}s)")
    
    try:
        # 使用 httpx.AsyncClient 进行异步调用
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if not content:
                    print(f"⚠️ [OpenRouter] {model} 返回空内容")
                    return None
                
                print(f"✅ [OpenRouter] {model} responded: {content[:100]}...")
                
                # 清洗和解析 JSON
                result = clean_json_response(content)
                
                if result:
                    print(f"✅ [OpenRouter] {model} parsed successfully: prob={result.get('probability')}%")
                else:
                    print(f"⚠️ [OpenRouter] {model} response parsing failed")
                
                return result
            else:
                error_text = response.text
                print(f"❌ [OpenRouter] API error for {model}: {response.status_code}")
                print(f"Error details: {error_text[:500]}")
                return None
                
    except httpx.TimeoutException:
        print(f"⏱️ [OpenRouter] {model} timeout after {timeout_seconds}s")
        # 返回默认值而不是 None，让系统可以继续
        return {
            "probability": 50.0,
            "confidence": "low",
            "reasoning": f"OpenRouter timeout after {timeout_seconds}s"
        }
    except httpx.NetworkError as e:
        print(f"🌐 [OpenRouter] Network error calling {model}: {type(e).__name__}: {e}")
        raise  # 让 tenacity 重试
    except httpx.RequestError as e:
        print(f"❌ [OpenRouter] Request error calling {model}: {type(e).__name__}: {e}")
        raise  # 让 tenacity 重试
    except Exception as e:
        print(f"❌ [OpenRouter] Unexpected error calling {model}: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def call_multiple_openrouter_models(
    models: list[str],
    prompt: str
) -> Dict[str, Optional[Dict]]:
    """
    并发调用多个 OpenRouter 模型
    
    Args:
        models: 模型名称列表
        prompt: 提示词
        
    Returns:
        字典映射 model_name -> 预测结果
    """
    import asyncio
    
    # 过滤掉不在白名单中的模型
    valid_models = [m for m in models if validate_model(m)]
    invalid_models = [m for m in models if m not in valid_models]
    
    if invalid_models:
        print(f"⚠️ [OpenRouter] 以下模型不在白名单中，将被忽略: {', '.join(invalid_models)}")
    
    if not valid_models:
        print("⚠️ [OpenRouter] 没有有效的模型可调用")
        return {}
    
    # 并发调用所有模型
    tasks = {model: call_openrouter_model(model, prompt) for model in valid_models}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    # 组装结果字典
    result_dict = {}
    for i, (model, result) in enumerate(zip(tasks.keys(), results)):
        if isinstance(result, Exception):
            print(f"❌ [OpenRouter] {model} 调用异常: {type(result).__name__}: {result}")
            result_dict[model] = None
        else:
            result_dict[model] = result
    
    return result_dict


# 便捷函数：获取所有可用的免费模型列表
def get_available_models() -> list[str]:
    """
    获取所有可用的免费模型列表
    
    Returns:
        模型名称列表
    """
    return FREE_MODELS.copy()


# 便捷函数：检查 OpenRouter 是否可用
def is_openrouter_available() -> bool:
    """
    检查 OpenRouter 是否可用（API 密钥是否配置）
    
    Returns:
        True if API key is configured, False otherwise
    """
    return bool(os.getenv("OPENROUTER_API_KEY"))


if __name__ == "__main__":
    # 测试代码
    import asyncio
    
    async def test():
        test_prompt = """
        请分析以下事件，并返回 JSON 格式的预测结果：
        {
            "prob_yes": <0-100之间的数字>,
            "confidence": "low" | "medium" | "high",
            "rationale": "<你的分析理由>"
        }
        
        事件：Will Maduro be out of power in Venezuela by 2025?
        """
        
        print("🧪 测试 OpenRouter 调用...")
        print(f"可用模型: {', '.join(get_available_models())}")
        print(f"OpenRouter 可用: {is_openrouter_available()}")
        
        if is_openrouter_available():
            # 测试单个模型
            result = await call_openrouter_model(
                "mistralai/mistral-7b-instruct",
                test_prompt
            )
            print(f"\n测试结果: {result}")
        else:
            print("⚠️ OPENROUTER_API_KEY 未设置，无法测试")
    
    asyncio.run(test())

