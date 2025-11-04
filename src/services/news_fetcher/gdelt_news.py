"""
GDELT News 新闻源

功能：
- 从 GDELT API 抓取全球事件新闻
- 无需API密钥（公开API）
- 支持关键词搜索
"""
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from urllib.parse import quote_plus


async def fetch_gdelt_news(keyword: str = "", limit: int = 50) -> List[Dict]:
    """
    从 GDELT API 抓取新闻。
    
    Args:
        keyword: 搜索关键词（可选）
        limit: 返回的新闻数量限制（默认50）
    
    Returns:
        List[Dict]: 新闻列表，字段：title, url, source, published, summary
        所有异常应被捕获并返回空列表（不抛出错误）。
    """
    try:
        # GDELT API 文档端点
        # 注意：GDELT API v2 需要特定的查询格式
        # 这里使用简化的方式：获取最近的新闻条目
        
        # GDELT 事件查询（如果有关键词）
        if keyword:
            query = quote_plus(keyword)
            # GDELT API v2 文档查询
            url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={query}&mode=artlist&maxrecords={min(limit, 250)}"
        else:
            # 如果没有关键词，获取最近的事件
            url = f"https://api.gdeltproject.org/api/v2/doc/doc?mode=artlist&maxrecords={min(limit, 250)}"
        
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            # GDELT 返回 CSV 或 JSON 格式
            content_type = response.headers.get("content-type", "")
            
            if "json" in content_type:
                data = response.json()
            else:
                # 如果是 CSV，解析第一行（通常是标题）
                text = response.text
                lines = text.strip().split("\n")
                if len(lines) < 2:
                    return []
                
                # 简单解析 CSV（GDELT格式可能复杂）
                news_list = []
                for line in lines[1:limit+1]:  # 跳过标题行
                    try:
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            title = parts[0].strip()
                            url = parts[1].strip() if len(parts) > 1 else ""
                            
                            if title and url:
                                news_list.append({
                                    "title": title,
                                    "url": url,
                                    "source": "GDELT",
                                    "published": None,  # GDELT CSV 可能不包含时间
                                    "summary": ""
                                })
                    except:
                        continue
                
                return news_list
        
        # JSON 格式处理
        if isinstance(data, list):
            news_list = []
            for item in data[:limit]:
                try:
                    published = None
                    if "date" in item:
                        try:
                            published = datetime.fromisoformat(item["date"].replace("Z", "+00:00"))
                        except:
                            pass
                    
                    news_item = {
                        "title": item.get("title", item.get("name", "")).strip(),
                        "url": item.get("url", item.get("url_mobile", "")).strip(),
                        "source": "GDELT",
                        "published": published,
                        "summary": item.get("summary", item.get("snippet", "")).strip()[:500]
                    }
                    
                    if news_item["title"] and news_item["url"]:
                        news_list.append(news_item)
                except:
                    continue
            
            return news_list
        
        return []
        
    except Exception:
        return []

