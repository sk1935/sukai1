"""
Wikipedia Current Events 新闻源

功能：
- 从 Wikipedia Current Events Portal 抓取全球要闻
- 无需API密钥
- 获取今日/本周重要事件
"""
import httpx
import re
from datetime import datetime
from typing import Dict, List

# BeautifulSoup 是可选的，如果没有安装则使用正则表达式fallback
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


async def fetch_wikipedia_events(keyword: str = "", limit: int = 50) -> List[Dict]:
    """
    从 Wikipedia Current Events Portal 抓取新闻。
    
    Args:
        keyword: 搜索关键词（可选，但Wikipedia不支持关键词搜索，会被忽略）
        limit: 返回的新闻数量限制（默认50）
    
    Returns:
        List[Dict]: 新闻列表，字段：title, url, source, published, summary
        所有异常应被捕获并返回空列表（不抛出错误）。
    """
    try:
        # Wikipedia Current Events Portal
        url = "https://en.wikipedia.org/wiki/Portal:Current_events"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NewsFetcher/1.0)"
        }
        
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
        
        # 使用 BeautifulSoup 解析HTML（如果没有安装，使用正则表达式fallback）
        news_list = []
        
        if HAS_BS4:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 查找当前事件条目
            # Wikipedia Current Events 通常使用特定的HTML结构
            # 查找包含日期的部分和事件列表
            event_sections = soup.find_all(['h3', 'h4'], class_=lambda x: x and 'date-header' in str(x))
            
            count = 0
            for section in event_sections[:10]:  # 限制搜索的章节数
                if count >= limit:
                    break
                
                # 获取日期标题
                date_text = section.get_text().strip()
                published = None
                
                # 尝试解析日期
                try:
                    # 提取日期部分（如 "December 2024" 或 "30 December 2024"）
                    date_match = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_text)
                    if date_match:
                        from dateutil import parser
                        published = parser.parse(date_match.group(0))
                except:
                    pass
                
                # 查找该章节下的事件列表
                next_sibling = section.find_next_sibling(['ul', 'div'])
                if next_sibling:
                    list_items = next_sibling.find_all('li')
                    for item in list_items:
                        if count >= limit:
                            break
                        
                        # 提取事件文本和链接
                        link = item.find('a', href=True)
                        if link:
                            title = link.get_text().strip()
                            href = link.get('href', '')
                            
                            # 构建完整URL
                            if href.startswith('/'):
                                url_full = f"https://en.wikipedia.org{href}"
                            elif href.startswith('http'):
                                url_full = href
                            else:
                                continue
                            
                            # 获取事件摘要（li标签的文本，去除链接文本）
                            summary = item.get_text().strip()
                            if title in summary:
                                summary = summary.replace(title, "", 1).strip()
                            
                            news_item = {
                                "title": title,
                                "url": url_full,
                                "source": "Wikipedia Current Events",
                                "published": published,
                                "summary": summary[:500]
                            }
                            
                            if news_item["title"] and news_item["url"]:
                                news_list.append(news_item)
                                count += 1
        else:
            # 如果没有 BeautifulSoup，使用正则表达式fallback
            # 简单的正则表达式提取链接
            link_pattern = r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
            matches = re.findall(link_pattern, html)
            
            count = 0
            for href, title in matches[:limit]:
                if count >= limit:
                    break
                
                # 过滤Wikipedia内部链接
                if href.startswith('/wiki/') and not href.startswith('/wiki/File:'):
                    url_full = f"https://en.wikipedia.org{href}"
                    news_item = {
                        "title": title.strip(),
                        "url": url_full,
                        "source": "Wikipedia Current Events",
                        "published": None,  # 无法从正则表达式提取日期
                        "summary": ""
                    }
                    
                    if news_item["title"]:
                        news_list.append(news_item)
                        count += 1
        
        return news_list
        
    except Exception:
        return []

