"""
Reddit News 新闻源

功能：
- 从 Reddit /r/worldnews 抓取热门新闻
- 无需API密钥
- 支持关键词搜索（通过Reddit搜索）
"""
import httpx
import asyncio
from datetime import datetime
from typing import Dict, List
from urllib.parse import quote_plus


async def fetch_reddit_news(keyword: str = "", limit: int = 50) -> List[Dict]:
    """
    从 Reddit /r/worldnews 抓取新闻。
    
    Args:
        keyword: 搜索关键词（可选，通过Reddit搜索）
        limit: 返回的新闻数量限制（默认50）
    
    Returns:
        List[Dict]: 新闻列表，字段：title, url, source, published, summary
        所有异常应被捕获并返回空列表（不抛出错误）。
    """
    try:
        # Reddit JSON API URL
        if keyword:
            # 使用Reddit搜索
            query = quote_plus(keyword)
            url = f"https://www.reddit.com/r/worldnews/search.json?q={query}&sort=top&limit={min(limit, 100)}"
        else:
            # 热门新闻
            url = f"https://www.reddit.com/r/worldnews/top.json?limit={min(limit, 100)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NewsFetcher/1.0)"
        }
        
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        news_list = []
        if "data" in data and "children" in data["data"]:
            for child in data["data"]["children"][:limit]:
                try:
                    post = child.get("data", {})
                    
                    # 解析发布时间（Unix时间戳）
                    published = None
                    created_utc = post.get("created_utc")
                    if created_utc:
                        try:
                            published = datetime.fromtimestamp(created_utc)
                        except:
                            pass
                    
                    news_item = {
                        "title": post.get("title", "").strip(),
                        "url": post.get("url", "").strip(),
                        "source": "Reddit /r/worldnews",
                        "published": published,
                        "summary": post.get("selftext", "").strip()[:500]  # 限制摘要长度
                    }
                    
                    # 只添加有效的新闻（必须有标题和URL）
                    if news_item["title"] and news_item["url"]:
                        news_list.append(news_item)
                except Exception:
                    # 跳过单个条目的错误
                    continue
        
        return news_list
        
    except Exception:
        return []

