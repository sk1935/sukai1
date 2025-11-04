#!/usr/bin/env python3
"""
Polymarket AI Predictor - 辅助模块运行验证脚本

任务：
1. 检测 news_cache, world_sentiment_engine, openrouter_assistant 模块能否正常运行
2. 检查环境变量 *_ENABLED 状态
3. 执行测试并生成诊断报告
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# 加载环境变量
load_dotenv()

# 诊断结果存储
diagnostic_results = {
    "news_cache": {
        "module": "news_cache",
        "enabled": False,
        "status": "未启用",
        "result": None,
        "summary": "",
        "error": None,
        "test_time": None
    },
    "world_sentiment_engine": {
        "module": "world_sentiment_engine",
        "enabled": False,
        "status": "未启用",
        "result": None,
        "summary": "",
        "error": None,
        "test_time": None
    },
    "openrouter_assistant": {
        "module": "openrouter_assistant",
        "enabled": False,
        "status": "未启用",
        "result": None,
        "summary": "",
        "error": None,
        "test_time": None
    }
}


def check_enabled_status():
    """检查环境变量中的启用状态"""
    print("=" * 60)
    print("🔍 检查环境变量启用状态")
    print("=" * 60)
    
    # 检查 NEWS_CACHE_ENABLED
    news_cache_enabled = os.getenv("NEWS_CACHE_ENABLED", "false").lower() == "true"
    diagnostic_results["news_cache"]["enabled"] = news_cache_enabled
    print(f"📰 NEWS_CACHE_ENABLED: {news_cache_enabled}")
    
    # 检查 WORLD_SENTIMENT_ENABLED
    world_sentiment_enabled = os.getenv("WORLD_SENTIMENT_ENABLED", "false").lower() == "true"
    diagnostic_results["world_sentiment_engine"]["enabled"] = world_sentiment_enabled
    print(f"🌍 WORLD_SENTIMENT_ENABLED: {world_sentiment_enabled}")
    
    # 检查 OPENROUTER_ASSISTANT_ENABLED
    openrouter_assistant_enabled = os.getenv("OPENROUTER_ASSISTANT_ENABLED", "false").lower() == "true"
    diagnostic_results["openrouter_assistant"]["enabled"] = openrouter_assistant_enabled
    print(f"📰 OPENROUTER_ASSISTANT_ENABLED: {openrouter_assistant_enabled}")
    
    print("=" * 60)
    print()


async def test_news_cache(force_test=False):
    """测试 news_cache 模块"""
    module_name = "news_cache"
    result = diagnostic_results[module_name]
    
    if not result["enabled"] and not force_test:
        result["status"] = "未启用"
        result["summary"] = "环境变量未启用"
        print(f"⚠️ {module_name}: 未启用，跳过测试")
        return
    
    # 如果强制测试，临时启用模块
    if force_test and not result["enabled"]:
        print(f"   ⚠️ 注意: 模块未启用，但强制测试模式")
        # 临时设置环境变量
        os.environ["NEWS_CACHE_ENABLED"] = "true"
    
    print(f"\n🧪 测试 {module_name}...")
    start_time = datetime.now()
    
    try:
        from src.news_cache import fetch_and_cache_news
        print(f"   ✅ 模块导入成功")
        
        # 执行异步函数
        print(f"   🔄 调用 fetch_and_cache_news(keyword='test')...")
        await fetch_and_cache_news(keyword="test", force_refresh=False)
        
        # 检查缓存文件
        cache_file = project_root / "cache" / "news_cache.json"
        if cache_file.exists():
            import json
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            news_count = len(cache_data.get("news", []))
            file_size = cache_file.stat().st_size
            cache_time = cache_data.get("timestamp", "N/A")
            
            result["status"] = "✅ 成功"
            result["result"] = {
                "news_count": news_count,
                "file_size": file_size,
                "cache_time": cache_time
            }
            result["summary"] = f"{news_count} 条新闻，文件大小 {file_size} bytes"
            print(f"   ✅ 成功: {news_count} 条新闻，文件大小 {file_size} bytes")
        else:
            result["status"] = "⚠️ 警告"
            result["summary"] = "缓存文件不存在"
            print(f"   ⚠️ 警告: 缓存文件不存在")
        
    except ImportError as e:
        result["status"] = "❌ 失败"
        result["error"] = f"导入失败: {str(e)}"
        result["summary"] = "模块导入失败"
        print(f"   ❌ 导入失败: {e}")
    except Exception as e:
        result["status"] = "❌ 失败"
        result["error"] = f"{type(e).__name__}: {str(e)}"
        result["summary"] = f"执行失败: {type(e).__name__}"
        print(f"   ❌ 执行失败: {type(e).__name__}: {e}")
    
    result["test_time"] = (datetime.now() - start_time).total_seconds()
    print(f"   ⏱️ 耗时: {result['test_time']:.2f} 秒")


async def test_world_sentiment_engine(force_test=False):
    """测试 world_sentiment_engine 模块"""
    module_name = "world_sentiment_engine"
    result = diagnostic_results[module_name]
    
    if not result["enabled"] and not force_test:
        result["status"] = "未启用"
        result["summary"] = "环境变量未启用"
        print(f"⚠️ {module_name}: 未启用，跳过测试")
        return
    
    # 如果强制测试，临时启用模块
    if force_test and not result["enabled"]:
        print(f"   ⚠️ 注意: 模块未启用，但强制测试模式")
        # 临时设置环境变量
        os.environ["WORLD_SENTIMENT_ENABLED"] = "true"
    
    print(f"\n🧪 测试 {module_name}...")
    start_time = datetime.now()
    
    try:
        from src.world_sentiment_engine import compute_world_temperature
        print(f"   ✅ 模块导入成功")
        
        # 执行函数
        print(f"   🔄 调用 compute_world_temperature()...")
        world_temp_data = compute_world_temperature()
        
        if world_temp_data:
            description = world_temp_data.get("description", None)
            total_samples = world_temp_data.get("total_samples", 0)
            positive = world_temp_data.get("positive", 0)
            negative = world_temp_data.get("negative", 0)
            neutral = world_temp_data.get("neutral", 0)
            
            if description:
                result["status"] = "✅ 成功"
                result["result"] = {
                    "description": description,
                    "total_samples": total_samples,
                    "positive": positive,
                    "negative": negative,
                    "neutral": neutral
                }
                result["summary"] = f"{description}（正面: {positive}, 负面: {negative}, 中性: {neutral}）"
                print(f"   ✅ 成功: {description}")
                print(f"      情绪分布: 正面 {positive}, 负面 {negative}, 中性 {neutral}, 总计 {total_samples}")
            else:
                result["status"] = "⚠️ 警告"
                result["summary"] = "描述字段为 None"
                print(f"   ⚠️ 警告: 描述字段为 None")
        else:
            result["status"] = "⚠️ 警告"
            result["summary"] = "返回 None（可能缓存为空）"
            print(f"   ⚠️ 警告: 返回 None（可能缓存为空）")
        
    except ImportError as e:
        result["status"] = "❌ 失败"
        result["error"] = f"导入失败: {str(e)}"
        result["summary"] = "模块导入失败"
        print(f"   ❌ 导入失败: {e}")
    except Exception as e:
        result["status"] = "❌ 失败"
        result["error"] = f"{type(e).__name__}: {str(e)}"
        result["summary"] = f"执行失败: {type(e).__name__}"
        print(f"   ❌ 执行失败: {type(e).__name__}: {e}")
    
    result["test_time"] = (datetime.now() - start_time).total_seconds()
    print(f"   ⏱️ 耗时: {result['test_time']:.2f} 秒")


async def test_openrouter_assistant(force_test=False):
    """测试 openrouter_assistant 模块"""
    module_name = "openrouter_assistant"
    result = diagnostic_results[module_name]
    
    if not result["enabled"] and not force_test:
        result["status"] = "未启用"
        result["summary"] = "环境变量未启用"
        print(f"⚠️ {module_name}: 未启用，跳过测试")
        return
    
    # 如果强制测试，临时启用模块
    if force_test and not result["enabled"]:
        print(f"   ⚠️ 注意: 模块未启用，但强制测试模式")
        # 临时设置环境变量
        os.environ["OPENROUTER_ASSISTANT_ENABLED"] = "true"
    
    print(f"\n🧪 测试 {module_name}...")
    start_time = datetime.now()
    
    try:
        from src.openrouter_assistant import get_news_summary
        print(f"   ✅ 模块导入成功")
        
        # 执行异步函数
        print(f"   🔄 调用 get_news_summary()...")
        news_summary = await get_news_summary()
        
        if news_summary:
            summary_length = len(news_summary)
            preview = news_summary[:100] + "..." if len(news_summary) > 100 else news_summary
            
            result["status"] = "✅ 成功"
            result["result"] = {
                "summary_length": summary_length,
                "preview": preview
            }
            result["summary"] = f"{summary_length} 字符"
            print(f"   ✅ 成功: {summary_length} 字符")
            print(f"   📄 预览: {preview[:80]}...")
        else:
            result["status"] = "⚠️ 警告"
            result["summary"] = "返回空字符串或 None"
            print(f"   ⚠️ 警告: 返回空字符串或 None")
        
    except ImportError as e:
        result["status"] = "❌ 失败"
        result["error"] = f"导入失败: {str(e)}"
        result["summary"] = "模块导入失败"
        print(f"   ❌ 导入失败: {e}")
    except Exception as e:
        result["status"] = "❌ 失败"
        result["error"] = f"{type(e).__name__}: {str(e)}"
        result["summary"] = f"执行失败: {type(e).__name__}"
        print(f"   ❌ 执行失败: {type(e).__name__}: {e}")
    
    result["test_time"] = (datetime.now() - start_time).total_seconds()
    print(f"   ⏱️ 耗时: {result['test_time']:.2f} 秒")


def generate_report():
    """生成诊断报告"""
    report_path = project_root / "diagnostic_runtime.md"
    
    report = f"""# 🔍 Polymarket AI Predictor - 辅助模块运行诊断报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**测试环境**: Python {sys.version.split()[0]}

---

## 📊 模块测试结果

| 模块 | 启用状态 | 测试结果 | 返回值摘要 | 错误 | 耗时 |
|------|-----------|-----------|-------------|------|------|
"""
    
    for module_name, result in diagnostic_results.items():
        enabled = "✅ True" if result["enabled"] else "❌ False"
        status = result["status"]
        summary = result["summary"] or "N/A"
        error = result["error"] or "None"
        test_time = f"{result['test_time']:.2f}s" if result["test_time"] else "N/A"
        
        report += f"| `{module_name}` | {enabled} | {status} | {summary} | {error} | {test_time} |\n"
    
    report += f"""
---

## 📋 详细测试信息

"""
    
    for module_name, result in diagnostic_results.items():
        report += f"""### {module_name}

- **启用状态**: {'✅ 已启用' if result['enabled'] else '❌ 未启用'}
- **测试结果**: {result['status']}
- **返回值摘要**: {result['summary'] or 'N/A'}
- **错误信息**: {result['error'] or '无'}
- **测试耗时**: {f"{result['test_time']:.2f} 秒" if result['test_time'] else 'N/A'}

"""
        
        if result["result"]:
            report += "**返回数据详情**:\n"
            report += "```json\n"
            import json
            report += json.dumps(result["result"], indent=2, ensure_ascii=False)
            report += "\n```\n\n"
    
    report += f"""
---

## 🔍 环境变量检查

- `NEWS_CACHE_ENABLED`: {os.getenv('NEWS_CACHE_ENABLED', '未设置')}
- `WORLD_SENTIMENT_ENABLED`: {os.getenv('WORLD_SENTIMENT_ENABLED', '未设置')}
- `OPENROUTER_ASSISTANT_ENABLED`: {os.getenv('OPENROUTER_ASSISTANT_ENABLED', '未设置')}

---

## 📝 测试总结

"""
    
    # 统计结果
    enabled_count = sum(1 for r in diagnostic_results.values() if r["enabled"])
    success_count = sum(1 for r in diagnostic_results.values() if r["status"] == "✅ 成功")
    failed_count = sum(1 for r in diagnostic_results.values() if "❌" in r["status"])
    warning_count = sum(1 for r in diagnostic_results.values() if "⚠️" in r["status"])
    
    report += f"""
- **已启用模块**: {enabled_count} / 3
- **测试成功**: {success_count} / {enabled_count}
- **测试失败**: {failed_count} / {enabled_count}
- **测试警告**: {warning_count} / {enabled_count}

"""
    
    if enabled_count == 0:
        report += "⚠️ **所有辅助模块均未启用**。如需启用，请在 `.env` 文件中设置相应的环境变量。\n"
    elif success_count == enabled_count:
        report += "✅ **所有启用的模块测试通过**。\n"
    else:
        report += "⚠️ **部分模块测试失败或出现警告**，请检查错误信息。\n"
    
    report += f"""
---

**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    # 写入文件
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("\n" + "=" * 60)
    print(f"✅ 诊断报告已生成: {report_path}")
    print("=" * 60)


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="辅助模块运行验证脚本")
    parser.add_argument("--force", action="store_true", help="强制测试所有模块（即使未启用）")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("🚀 Polymarket AI Predictor - 辅助模块运行验证")
    if args.force:
        print("⚠️ 强制测试模式（即使模块未启用）")
    print("=" * 60)
    print()
    
    # 1. 检查启用状态
    check_enabled_status()
    
    # 2. 测试各个模块
    print("=" * 60)
    print("🧪 开始模块测试")
    print("=" * 60)
    
    await test_news_cache(force_test=args.force)
    await test_world_sentiment_engine(force_test=args.force)
    await test_openrouter_assistant(force_test=args.force)
    
    # 3. 生成报告
    print("\n" + "=" * 60)
    print("📄 生成诊断报告")
    print("=" * 60)
    generate_report()
    
    print("\n✅ 验证完成！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 程序异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

