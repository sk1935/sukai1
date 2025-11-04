"""
OpenRouter 助手 - 新闻摘要生成

功能：
- 使用 OpenRouter 免费模型生成新闻摘要
- 输入：news_cache 的最新新闻（前 10 条）
- 输出：综合摘要文本，保存到 cache/news_summary.txt
"""
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

OPENROUTER_ASSISTANT_ENABLED = os.getenv("OPENROUTER_ASSISTANT_ENABLED", "false").lower() == "true"

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
    生成新闻摘要
    
    Args:
        force_refresh: 是否强制刷新（忽略已存在的摘要）
    
    Returns:
        str: 生成的摘要文本，失败返回 None
    """
    if not OPENROUTER_ASSISTANT_ENABLED:
        print("🛑 [OPENROUTER_ASSISTANT] 功能已禁用，跳过摘要生成")
        return None
    
    if not OPENROUTER_LAYER_AVAILABLE:
        print("🛑 [OPENROUTER_ASSISTANT] OpenRouter 层不可用")
        return None
    
    # 检查是否已有摘要且未过期
    if not force_refresh and SUMMARY_FILE.exists():
        try:
            # 检查文件修改时间（如果小于6小时，直接返回）
            file_time = datetime.fromtimestamp(SUMMARY_FILE.stat().st_mtime, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            
            if (now - file_time).total_seconds() < 6 * 3600:  # 6小时有效期
                print(f"✅ 使用缓存的新闻摘要（剩余有效期：{int((6 * 3600 - (now - file_time).total_seconds()) / 3600)} 小时）")
                with open(SUMMARY_FILE, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            print(f"⚠️ 读取缓存摘要失败: {e}")
    
    # 检查 OpenRouter 是否可用
    if not is_openrouter_available():
        print("⚠️ OpenRouter API 不可用，跳过摘要生成")
        return None
    
    # 获取可用模型
    available_models = get_available_models()
    if not available_models:
        print("⚠️ 没有可用的 OpenRouter 模型")
        return None
    
    # 获取缓存的新闻
    news_list = get_cached_news()
    if not news_list:
        print("⚠️ 没有可用的新闻数据，无法生成摘要")
        return None
    
    print(f"📝 开始生成新闻摘要（使用 {len(news_list)} 条新闻）...")
    
    # 构建提示词
    prompt = build_summary_prompt(news_list)
    
    # 尝试多个模型（按优先级）
    models_to_try = [
        "meta-llama/llama-3-70b-instruct",  # 首选：Llama-3-70B
        "mistralai/mistral-7b-instruct",   # 备选：Mistral-7B
        "yi-large/yi-1.5-chat"            # 备选：Yi-Large
    ]
    
    summary = None
    
    for model_name in models_to_try:
        if model_name not in available_models:
            continue
        
        try:
            print(f"🤖 尝试使用模型: {model_name}")
            
            # 对于摘要任务，我们需要直接获取原始文本响应
            # 调用 OpenRouter API 获取原始响应
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                print("⚠️ OPENROUTER_API_KEY 未设置")
                continue
            
            import httpx
            timeout_seconds = 35.0
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://polymarket-predictor.com",
                "X-Title": "Polymarket AI Predictor"
            }
            
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 1000  # 增加 token 限制以获取完整摘要
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    if content:
                        summary = content.strip()
                        print(f"✅ 成功使用 {model_name} 生成摘要（{len(summary)} 字符）")
                        break
                    else:
                        print(f"⚠️ {model_name} 返回空内容")
                else:
                    print(f"❌ {model_name} API 错误: {response.status_code}")
                    error_text = response.text[:200]
                    print(f"   错误详情: {error_text}")
                    
        except Exception as e:
            print(f"⚠️ {model_name} 调用失败: {type(e).__name__}: {e}")
            continue
    
    if not summary:
        print("❌ 所有模型调用失败，无法生成摘要")
        return None
    
    # 保存摘要到文件
    try:
        ensure_cache_dir()
        with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"✅ 新闻摘要已保存: {SUMMARY_FILE}")
        return summary
        
    except Exception as e:
        print(f"❌ 保存摘要失败: {e}")
        return summary  # 即使保存失败，也返回摘要内容


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
    "SUMMARY_FILE"
]
