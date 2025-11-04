"""
测试新闻抓取模块

用法：
    python test_news_fetcher.py
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.services.news_fetcher import fetch_all_free_news


async def test_news_fetcher():
    """测试新闻抓取功能"""
    print("\n" + "="*60)
    print("🧪 测试新闻抓取模块")
    print("="*60)
    
    # 测试1: 无关键词，抓取通用新闻
    print("\n📰 测试1: 抓取通用新闻（无关键词）")
    print("-" * 60)
    try:
        news = await fetch_all_free_news(keyword="", limit=10)
        print(f"✅ 成功抓取 {len(news)} 条新闻")
        for i, item in enumerate(news[:5], 1):
            print(f"\n{i}. {item['title'][:80]}")
            print(f"   来源: {item['source']}")
            print(f"   URL: {item['url'][:60]}...")
            if item.get('published'):
                print(f"   时间: {item['published']}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试2: 带关键词搜索
    print("\n\n📰 测试2: 搜索关键词 'Israel'")
    print("-" * 60)
    try:
        news = await fetch_all_free_news(keyword="Israel", limit=10)
        print(f"✅ 成功抓取 {len(news)} 条相关新闻")
        for i, item in enumerate(news[:3], 1):
            print(f"\n{i}. {item['title'][:80]}")
            print(f"   来源: {item['source']}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    
    print("\n" + "="*60)
    print("✅ 测试完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_news_fetcher())

