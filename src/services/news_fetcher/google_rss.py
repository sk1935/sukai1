"""
Google News RSS 新闻源

功能：
- 从 Google News RSS 抓取新闻
- 无需API密钥
- 支持关键词搜索
"""
import feedparser
import asyncio
from datetime import datetime
from typing import Dict, List
from urllib.parse import quote_plus


async def fetch_google_rss(keyword: str = "", limit: int = 50) -> List[Dict]:
    """
    从 Google News RSS 抓取新闻。
    
    Args:
        keyword: 搜索关键词（可选）
        limit: 返回的新闻数量限制（默认50）
    
    Returns:
        List[Dict]: 新闻列表，字段：title, url, source, published, summary
        所有异常应被捕获并返回空列表（不抛出错误）。
    """
    try:
        # 构建 RSS URL
        if keyword:
            query = quote_plus(keyword)
            url = f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
        else:
            url = "https://news.google.com/rss?hl=en&gl=US&ceid=US:en"
        
        # 在线程池中执行 feedparser.parse（因为它是同步的）
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, url)
        
        # 检查是否有错误
        if feed.bozo and feed.bozo_exception:
            return []
        
        news_list = []
        for entry in feed.entries[:limit]:
            try:
                # 解析发布时间
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6])
                    except:
                        pass
                elif hasattr(entry, "published"):
                    try:
                        from dateutil import parser
                        published = parser.parse(entry.published)
                    except:
                        pass
                
                news_item = {
                    "title": getattr(entry, "title", "").strip(),
                    "url": getattr(entry, "link", "").strip(),
                    "source": "Google News",
                    "published": published,
                    "summary": getattr(entry, "summary", "").strip()[:500]  # 限制摘要长度
                }
                
                # 只添加有效的新闻（必须有标题和URL）
                if news_item["title"] and news_item["url"]:
                    news_list.append(news_item)
            except Exception as e:
                # 跳过单个条目的错误
                continue
        
        return news_list
        
    except Exception:
        return []

