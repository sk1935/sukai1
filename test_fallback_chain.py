"""
测试 Fallback Chain 机制

测试场景：
1. OpenRouter 正常 → 应直接返回结果
2. OpenRouter 失败，Cohere 成功 → 应切换到 Cohere
3. 所有模型失败 → 应返回默认响应
"""
import asyncio
import os
from unittest.mock import patch, AsyncMock
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.openrouter_assistant import run_with_fallback, call_cohere_api, call_textrazor_api


async def test_openrouter_success():
    """测试场景1：OpenRouter 正常"""
    print("\n" + "="*60)
    print("测试场景1：OpenRouter 正常")
    print("="*60)
    
    # 设置环境变量
    os.environ["OPENROUTER_API_KEY"] = "test_key"
    
    prompt = "请总结以下新闻..."
    
    try:
        result = await run_with_fallback(prompt)
        print(f"✅ 测试完成")
        print(f"   来源: {result.get('source')}")
        print(f"   文本长度: {len(result.get('text', ''))}")
        print(f"   文本预览: {result.get('text', '')[:100]}...")
        return result.get('source') == 'openrouter'
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_openrouter_fail_cohere_success():
    """测试场景2：OpenRouter 失败，Cohere 成功"""
    print("\n" + "="*60)
    print("测试场景2：OpenRouter 失败 → Cohere 成功")
    print("="*60)
    
    # 模拟 OpenRouter 失败
    os.environ["OPENROUTER_API_KEY"] = "invalid_key"
    os.environ["COHERE_API_KEY"] = "test_cohere_key"
    
    prompt = "请总结以下新闻..."
    
    try:
        result = await run_with_fallback(prompt)
        print(f"✅ 测试完成")
        print(f"   来源: {result.get('source')}")
        print(f"   文本长度: {len(result.get('text', ''))}")
        print(f"   文本预览: {result.get('text', '')[:100]}...")
        return result.get('source') == 'cohere'
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_all_fail():
    """测试场景3：所有模型都失败"""
    print("\n" + "="*60)
    print("测试场景3：所有模型都失败 → 返回默认响应")
    print("="*60)
    
    # 清空所有API keys
    os.environ["OPENROUTER_API_KEY"] = ""
    os.environ["COHERE_API_KEY"] = ""
    os.environ["TEXTRAZOR_API_KEY"] = ""
    
    prompt = "请总结以下新闻..."
    
    try:
        result = await run_with_fallback(prompt)
        print(f"✅ 测试完成")
        print(f"   来源: {result.get('source')}")
        print(f"   文本: {result.get('text')}")
        return result.get('source') == 'fallback_default' and "[⚠️]" in result.get('text', '')
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_cohere_api():
    """测试 Cohere API 直接调用"""
    print("\n" + "="*60)
    print("测试：Cohere API 直接调用")
    print("="*60)
    
    # 需要真实的 API key
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        print("⚠️ COHERE_API_KEY 未设置，跳过测试")
        return None
    
    prompt = "Summarize: AI technology is advancing rapidly."
    
    try:
        result = await call_cohere_api(prompt)
        print(f"✅ Cohere API 调用成功")
        print(f"   来源: {result.get('source')}")
        print(f"   文本: {result.get('text', '')[:200]}...")
        return True
    except Exception as e:
        print(f"❌ Cohere API 调用失败: {type(e).__name__}: {e}")
        return False


async def test_textrazor_api():
    """测试 TextRazor API 直接调用"""
    print("\n" + "="*60)
    print("测试：TextRazor API 直接调用")
    print("="*60)
    
    # 需要真实的 API key
    api_key = os.getenv("TEXTRAZOR_API_KEY")
    if not api_key:
        print("⚠️ TEXTRAZOR_API_KEY 未设置，跳过测试")
        return None
    
    prompt = "Apple and Microsoft are the largest companies by market cap. Tesla is also growing."
    
    try:
        result = await call_textrazor_api(prompt)
        print(f"✅ TextRazor API 调用成功")
        print(f"   来源: {result.get('source')}")
        print(f"   文本: {result.get('text')}")
        return True
    except Exception as e:
        print(f"❌ TextRazor API 调用失败: {type(e).__name__}: {e}")
        return False


async def main():
    """运行所有测试"""
    print("\n🧪 开始测试 Fallback Chain 机制")
    print("="*60)
    
    # 注意：测试1和测试2需要真实的API keys才能完全验证
    # 如果没有API keys，会直接fallback到下一个或返回默认响应
    
    # 测试3：所有模型失败（不需要API keys）
    result3 = await test_all_fail()
    
    # 如果有 Cohere API key，测试 Cohere
    if os.getenv("COHERE_API_KEY"):
        await test_cohere_api()
    
    # 如果有 TextRazor API key，测试 TextRazor
    if os.getenv("TEXTRAZOR_API_KEY"):
        await test_textrazor_api()
    
    print("\n" + "="*60)
    print("测试总结：")
    print(f"  测试3（所有失败）: {'✅ 通过' if result3 else '❌ 失败'}")
    print("="*60)
    
    print("\n💡 提示：")
    print("  - 要完整测试 OpenRouter 和 Cohere，请设置相应的 API keys")
    print("  - 当前测试验证了 fallback 到默认响应的逻辑")
    print("  - Fallback Chain: OpenRouter → Cohere → TextRazor → Default")


if __name__ == "__main__":
    asyncio.run(main())




