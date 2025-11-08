"""
OpenRouter 助手 - 新闻摘要生成（支持多层备用模型 Fallback Chain）

功能：
- 使用多层备用模型生成新闻摘要
- Fallback Chain: OpenRouter → Cohere → TextRazor
- 输入：news_cache 的最新新闻（前 10 条）
- 输出：综合摘要文本，保存到 cache/news_summary.txt
"""
import asyncio
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict
import sys
import aiohttp

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置
OPENROUTER_ASSISTANT_ENABLED = os.getenv("OPENROUTER_ASSISTANT_ENABLED", "false").lower() == "true"
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
TEXTRAZOR_API_KEY = os.getenv("TEXTRAZOR_API_KEY", "")

# 日志配置
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# 相对导入（同目录）
from src.news_cache import get_cached_news

try:
    from services.llm_clients.openrouter_layer import (
        call_openrouter_model,
        get_available_models,
        is_openrouter_available
    )
    OPENROUTER_LAYER_AVAILABLE = True
except Exception as import_err:
    OPENROUTER_LAYER_AVAILABLE = False
    print(f"⚠️ OpenRouter 层导入失败，自动禁用: {import_err}")
    
    async def call_openrouter_model(*args, **kwargs):
        raise RuntimeError("OpenRouter layer unavailable")
    
    def get_available_models():
        return []
    
    def is_openrouter_available():
        return False

# 缓存配置
CACHE_DIR = Path(__file__).parent.parent / "cache"
SUMMARY_FILE = CACHE_DIR / "news_summary.txt"


def ensure_cache_dir():
    """确保缓存目录存在"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def call_cohere_api(prompt: str) -> Dict[str, str]:
    """
    调用 Cohere API 生成文本
    
    Args:
        prompt: 输入提示词
    
    Returns:
        Dict with "text" key containing the generated text
    
    Raises:
        Exception: 如果API调用失败
    """
    if not COHERE_API_KEY:
        raise ValueError("COHERE_API_KEY not configured")
    
    url = "https://api.cohere.ai/v1/generate"
    headers = {
        "Authorization": f"Bearer {COHERE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "command-xlarge-nightly",
        "prompt": prompt,
        "max_tokens": 300,
        "temperature": 0.7
    }
    
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            text = data.get("generations", [{}])[0].get("text", "").strip()
            if not text:
                raise ValueError("Cohere returned empty response")
            return {"text": text, "source": "cohere"}


async def call_textrazor_api(prompt: str) -> Dict[str, str]:
    """
    调用 TextRazor API 提取关键信息
    
    Args:
        prompt: 输入文本
    
    Returns:
        Dict with "text" key containing extracted entities and topics
    
    Raises:
        Exception: 如果API调用失败
    """
    if not TEXTRAZOR_API_KEY:
        raise ValueError("TEXTRAZOR_API_KEY not configured")
    
    url = "https://api.textrazor.com"
    headers = {"x-textrazor-key": TEXTRAZOR_API_KEY}
    data = {
        "text": prompt[:2000],  # TextRazor 有长度限制
        "extractors": "entities,topics"
    }
    
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, data=data) as resp:
            resp.raise_for_status()
            result = await resp.json()
            
            # 提取实体和主题
            response_data = result.get("response", {})
            entities = [e.get("entityId", "") for e in response_data.get("entities", [])]
            topics = [t.get("label", "") for t in response_data.get("topics", [])]
            
            # 合并结果
            combined = ", ".join(filter(None, (entities[:5] + topics[:5])))
            if not combined:
                raise ValueError("TextRazor returned no entities or topics")
            
            summary_text = f"🧩 关键主题: {combined}"
            return {"text": summary_text, "source": "textrazor"}


async def run_with_fallback(prompt: str) -> Dict[str, str]:
    """
    使用多层备用模型调用链
    
    Fallback Chain: OpenRouter → Cohere → TextRazor
    
    Args:
        prompt: 输入提示词
    
    Returns:
        Dict with "text" key containing the generated text and "source" key
    """
    # 1. 尝试 OpenRouter
    try:
        logger.info("[Fallback] 尝试 OpenRouter...")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not configured")
        
        import httpx
        timeout_seconds = 20.0
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://polymarket-predictor.com",
            "X-Title": "Polymarket AI Predictor"
        }
        
        # 使用快速模型
        payload = {
            "model": "mistralai/mistral-7b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if content:
                logger.info("[Fallback] ✅ OpenRouter 成功")
                return {"text": content.strip(), "source": "openrouter"}
            else:
                raise ValueError("OpenRouter returned empty content")
                
    except Exception as e1:
        logger.warning(f"[Fallback] ❌ OpenRouter 失败: {type(e1).__name__}: {str(e1)[:100]}")
    
    # 2. 尝试 Cohere
    try:
        logger.info("[Fallback] 尝试 Cohere...")
        result = await call_cohere_api(prompt)
        logger.info("[Fallback] ✅ Cohere 成功")
        return result
    except Exception as e2:
        logger.warning(f"[Fallback] ❌ Cohere 失败: {type(e2).__name__}: {str(e2)[:100]}")
    
    # 3. 尝试 TextRazor
    try:
        logger.info("[Fallback] 尝试 TextRazor...")
        result = await call_textrazor_api(prompt)
        logger.info("[Fallback] ✅ TextRazor 成功")
        return result
    except Exception as e3:
        logger.error(f"[Fallback] ❌ TextRazor 失败: {type(e3).__name__}: {str(e3)[:100]}")
    
    # 4. 所有模型都失败，返回默认响应
    logger.error("[Fallback] ❌ 所有模型调用失败，返回默认响应")
    return {
        "text": "[⚠️] 所有模型调用失败。无法生成新闻摘要。",
        "source": "fallback_default"
    }


def build_summary_prompt(news_list: List[Dict]) -> str:
    """
    构建摘要生成提示词
    
    Args:
        news_list: 新闻列表（前 10 条）
    
    Returns:
        str: 格式化的提示词
    """
    # 构建新闻文本
    news_text = ""
    for i, news in enumerate(news_list[:10], 1):
        news_text += f"{i}. [{news.get('source', 'Unknown')}] {news.get('title', '')}\n"
        if news.get('summary'):
            news_text += f"   摘要: {news.get('summary', '')[:100]}\n"
        news_text += "\n"
    
    prompt = f"""请分析以下全球新闻，生成一份综合摘要。

要求：
1. 总结主要话题趋势（用2-3句话）
2. 用一句话描述"当前全球情绪基调"

新闻列表：
{news_text}

请用中文输出，格式：
【主要话题趋势】
...
【全球情绪基调】
...
"""
    
    return prompt


async def generate_news_summary(force_refresh: bool = False) -> Optional[str]:
    """
    生成新闻摘要（支持多层备用模型 Fallback Chain）
    
    Args:
        force_refresh: 是否强制刷新（忽略已存在的摘要）
    
    Returns:
        str: 生成的摘要文本，失败返回 None
    """
    if not OPENROUTER_ASSISTANT_ENABLED:
        logger.info("🛑 [OPENROUTER_ASSISTANT] 功能已禁用，跳过摘要生成")
        return None
    
    # 检查是否已有摘要且未过期
    if not force_refresh and SUMMARY_FILE.exists():
        try:
            # 检查文件修改时间（如果小于6小时，直接返回）
            file_time = datetime.fromtimestamp(SUMMARY_FILE.stat().st_mtime, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            
            if (now - file_time).total_seconds() < 6 * 3600:  # 6小时有效期
                remaining_hours = int((6 * 3600 - (now - file_time).total_seconds()) / 3600)
                logger.info(f"✅ 使用缓存的新闻摘要（剩余有效期：{remaining_hours} 小时）")
                with open(SUMMARY_FILE, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            logger.warning(f"⚠️ 读取缓存摘要失败: {e}")
    
    # 获取缓存的新闻
    news_list = get_cached_news()
    if not news_list:
        logger.warning("⚠️ 没有可用的新闻数据，无法生成摘要")
        return None
    
    logger.info(f"📝 开始生成新闻摘要（使用 {len(news_list)} 条新闻）...")
    
    # 构建提示词
    prompt = build_summary_prompt(news_list)
    
    # 使用 Fallback Chain 调用模型
    try:
        result = await run_with_fallback(prompt)
        summary = result.get("text", "")
        source = result.get("source", "unknown")
        
        if not summary or summary.startswith("[⚠️]"):
            # 如果是默认fallback响应，返回None
            logger.error("❌ 所有模型调用失败，无法生成摘要")
            return None
        
        logger.info(f"✅ 成功生成摘要（来源: {source}，{len(summary)} 字符）")
        
        # 保存摘要到文件
        try:
            ensure_cache_dir()
            with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
                f.write(summary)
            
            logger.info(f"✅ 新闻摘要已保存: {SUMMARY_FILE}")
            return summary
            
        except Exception as e:
            logger.error(f"❌ 保存摘要失败: {e}")
            return summary  # 即使保存失败，也返回摘要内容
    
    except Exception as e:
        logger.error(f"❌ Fallback chain 执行失败: {type(e).__name__}: {e}")
        return None


async def get_news_summary() -> Optional[str]:
    """
    获取新闻摘要（优先从缓存读取）
    
    Returns:
        str: 摘要文本，如果不存在或过期返回 None
    """
    if not OPENROUTER_ASSISTANT_ENABLED:
        return None
    return await generate_news_summary(force_refresh=False)


# 导出函数
__all__ = [
    "generate_news_summary",
    "get_news_summary",
    "build_summary_prompt",
    "run_with_fallback",
    "call_cohere_api",
    "call_textrazor_api",
    "SUMMARY_FILE"
]
