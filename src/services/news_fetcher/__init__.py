"""
新闻抓取聚合模块

功能：
- 并发从多个免费新闻源抓取新闻
- 自动去重、过滤无效内容
- 忽略失败请求，不阻塞主流程
"""
import asyncio
import logging
from typing import Dict, List
from datetime import datetime

from .google_rss import fetch_google_rss
from .reddit_news import fetch_reddit_news
from .gdelt_news import fetch_gdelt_news
from .newsdata_io import fetch_newsdata
from .wikipedia_events import fetch_wikipedia_events

logger = logging.getLogger(__name__)


async def safe_fetch(source_func, *args, **kwargs):
    """
    安全执行新闻源抓取函数，捕获所有异常。
    
    Args:
        source_func: 新闻源抓取函数
        *args, **kwargs: 传递给函数的参数
    
    Returns:
        List[Dict]: 新闻列表，失败时返回空列表
    """
    try:
        return await source_func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"[NewsFetcher] Skipped {source_func.__name__}: {type(e).__name__}: {e}")
        return []


def deduplicate(news: List[Dict]) -> List[Dict]:
    """
    根据标题去重新闻列表。
    
    Args:
        news: 新闻列表
    
    Returns:
        List[Dict]: 去重后的新闻列表
    """
    seen = set()
    unique = []
    
    for item in news:
        title = item.get("title", "").strip()
        if title and title not in seen:
            seen.add(title)
            unique.append(item)
    
    return unique


async def fetch_all_free_news(keyword: str = "", limit: int = 50) -> List[Dict]:
    """
    并发抓取来自多个免费源的新闻。
    
    自动去重、过滤无效内容、忽略失败请求。
    
    Args:
        keyword: 搜索关键词（可选）
        limit: 每个源的新闻数量限制（默认50）
    
    Returns:
        List[Dict]: 标准结构的新闻列表
        [
            {
                "title": str,
                "url": str,
                "source": str,
                "published": datetime,
                "summary": str
            },
            ...
        ]
    """
    # 定义所有新闻源函数
    sources = [
        fetch_google_rss,
        fetch_reddit_news,
        fetch_gdelt_news,
        fetch_wikipedia_events,
        fetch_newsdata
    ]
    
    # 并发执行所有新闻源抓取
    tasks = [safe_fetch(src, keyword, limit) for src in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 合并所有结果（跳过异常）
    merged = []
    for result in results:
        if isinstance(result, list):
            merged.extend(result)
        elif isinstance(result, Exception):
            logger.debug(f"[NewsFetcher] Source returned exception: {type(result).__name__}")
    
    # 去重
    deduplicated = deduplicate(merged)
    
    # 按发布时间排序（最新的在前）
    deduplicated.sort(
        key=lambda x: x.get("published") or datetime.min,
        reverse=True
    )
    
    # 限制总数
    return deduplicated[:limit] if limit else deduplicated


__all__ = ["fetch_all_free_news", "fetch_google_rss", "fetch_reddit_news", 
           "fetch_gdelt_news", "fetch_newsdata", "fetch_wikipedia_events"]

