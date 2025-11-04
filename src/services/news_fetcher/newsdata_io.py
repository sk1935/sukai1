"""
NewsData.io 新闻源

功能：
- 从 NewsData.io API 抓取新闻
- 需要免费API密钥（从环境变量读取）
- 支持关键词搜索
"""
import httpx
import os
from datetime import datetime
from typing import Dict, List
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


async def fetch_newsdata(keyword: str = "", limit: int = 50) -> List[Dict]:
    """
    从 NewsData.io API 抓取新闻。
    
    Args:
        keyword: 搜索关键词（可选）
        limit: 返回的新闻数量限制（默认50）
    
    Returns:
        List[Dict]: 新闻列表，字段：title, url, source, published, summary
        所有异常应被捕获并返回空列表（不抛出错误）。
    """
    try:
        # 获取API密钥（可选，如果未配置则跳过）
        api_key = os.getenv("NEWSDATA_API_KEY", "").strip()
        if not api_key:
            return []  # 如果没有API密钥，直接返回空列表
        
        # 构建API URL
        base_url = "https://newsdata.io/api/1/news"
        params = {
            "apikey": api_key,
            "language": "en",
            "size": min(limit, 100)  # NewsData.io 最大支持100
        }
        
        if keyword:
            params["q"] = keyword
        
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(base_url, params=params)
            
            # 检查API密钥错误
            if response.status_code == 401:
                return []  # API密钥无效，静默返回空列表
            
            response.raise_for_status()
            data = response.json()
        
        news_list = []
        if "results" in data:
            for item in data["results"][:limit]:
                try:
                    # 解析发布时间
                    published = None
                    pub_date = item.get("pubDate")
                    if pub_date:
                        try:
                            published = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        except:
                            try:
                                from dateutil import parser
                                published = parser.parse(pub_date)
                            except:
                                pass
                    
                    news_item = {
                        "title": item.get("title", "").strip(),
                        "url": item.get("link", item.get("url", "")).strip(),
                        "source": item.get("source_id", "NewsData.io"),
                        "published": published,
                        "summary": item.get("description", item.get("content", "")).strip()[:500]
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

