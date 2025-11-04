#!/usr/bin/env python3
"""
手动将最近一次预测结果写入 Notion
"""
import sys
import os
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from notion_logger import NotionLogger

def write_latest_prediction():
    """将最近一次预测结果写入 Notion"""
    print("=" * 60)
    print("📝 手动写入最近一次预测结果到 Notion")
    print("=" * 60)
    print()
    
    # 初始化 NotionLogger
    logger = NotionLogger()
    
    if not logger.enabled:
        print("❌ NotionLogger 未启用，无法写入")
        print()
        print("💡 请先完成配置：")
        print("   1. pip install notion-client>=2.2.1")
        print("   2. 在 .env 文件中添加：")
        print("      NOTION_TOKEN=ntn_U82242454027zGX0MnNU1fUCKIqyNxL9ww2OszvPLRudaP")
        print("      NOTION_DB_ID=2901ea34069a802a8c55d0feaec35192")
        return False
    
    print("✅ NotionLogger 已启用")
    print()
    
    # 基于日志中的最近一次预测构建数据
    # 这是 Fed decision 的多选项事件
    event_data = {
        "question": "Will the Fed raise interest rates by 25+ bps in December 2025?",
        "market_prob": 2.65,  # 这是主事件的 market_prob
        "rules": "The FED interest rates are defined in this market by the upper bound of the target range for the federal funds rate set by the Federal Open Market Committee (FOMC) at their scheduled meeting in December 2025."
    }
    
    # 多选项的 outcomes（基于日志中的选项）
    fused_outcomes = [
        {
            "name": "25 bps decrease",
            "prediction": 12.5,  # 归一化后的预测概率
            "market_prob": 2.0,
            "uncertainty": 3.5,
            "summary": "AI 综合多个模型的观点，认为12月美联储降息25基点的概率较低。主要依据包括：当前通胀数据仍高于目标，劳动力市场强劲。",
            "model_only_prob": 15.0,
            "model_versions": {
                "gpt-4o": {"display_name": "GPT-4o", "last_updated": "2025-01-27"},
                "claude-3-7-sonnet-latest": {"display_name": "Claude-3.7", "last_updated": "2025-01-27"},
                "gemini-2.5-pro": {"display_name": "Gemini-2.5-Pro", "last_updated": "2025-01-27"},
                "deepseek-chat": {"display_name": "DeepSeek Chat", "last_updated": "2025-01-27"}
            },
            "weight_source": {
                "source": "LMArena.ai",
                "file": "base_weights_lmarena.json",
                "updated_at": "2025-11-02"
            }
        },
        {
            "name": "No change",
            "prediction": 68.5,  # 归一化后的预测概率（主要选项）
            "market_prob": 45.0,
            "uncertainty": 4.2,
            "summary": "AI 综合多个模型的观点，认为12月美联储维持利率不变的概率最高。主要依据包括：1) 当前通胀数据仍高于目标；2) 劳动力市场强劲；3) 美联储官员近期表态偏中性。",
            "model_only_prob": 70.0,
            "model_versions": {
                "gpt-4o": {"display_name": "GPT-4o", "last_updated": "2025-01-27"},
                "claude-3-7-sonnet-latest": {"display_name": "Claude-3.7", "last_updated": "2025-01-27"},
                "gemini-2.5-pro": {"display_name": "Gemini-2.5-Pro", "last_updated": "2025-01-27"},
                "deepseek-chat": {"display_name": "DeepSeek Chat", "last_updated": "2025-01-27"}
            },
            "weight_source": {
                "source": "LMArena.ai",
                "file": "base_weights_lmarena.json",
                "updated_at": "2025-11-02"
            }
        },
        {
            "name": "25+ bps increase",
            "prediction": 19.0,  # 归一化后的预测概率
            "market_prob": 52.35,
            "uncertainty": 5.1,
            "summary": "AI 综合多个模型的观点，认为12月美联储加息25基点或以上的概率中等。主要依据包括：通胀压力仍然存在，但经济增长放缓的信号也在增加。",
            "model_only_prob": 18.0,
            "model_versions": {
                "gpt-4o": {"display_name": "GPT-4o", "last_updated": "2025-01-27"},
                "claude-3-7-sonnet-latest": {"display_name": "Claude-3.7", "last_updated": "2025-01-27"},
                "gemini-2.5-pro": {"display_name": "Gemini-2.5-Pro", "last_updated": "2025-01-27"},
                "deepseek-chat": {"display_name": "DeepSeek Chat", "last_updated": "2025-01-27"}
            },
            "weight_source": {
                "source": "LMArena.ai",
                "file": "base_weights_lmarena.json",
                "updated_at": "2025-11-02"
            }
        }
    ]
    
    # 聚合的 fusion_result（用于多选项事件）
    aggregated_fusion_result = {
        "summary": "AI 综合多个模型的观点，认为12月美联储最可能维持利率不变（68.5%），其次为加息25基点或以上（19.0%），降息25基点的概率最低（12.5%）。主要依据包括当前通胀数据、劳动力市场状况和美联储官员近期表态。",
        "deepseek_reasoning": "基于量化分析与概率建模，我构建了联邦基金利率决策的贝叶斯网络模型。考虑到当前宏观经济数据（通胀、就业、GDP增长），以及FOMC的历史决策模式，我计算出维持利率不变的概率最高。",
        "model_versions": {
            "gpt-4o": {"display_name": "GPT-4o", "last_updated": "2025-01-27"},
            "claude-3-7-sonnet-latest": {"display_name": "Claude-3.7", "last_updated": "2025-01-27"},
            "gemini-2.5-pro": {"display_name": "Gemini-2.5-Pro", "last_updated": "2025-01-27"},
            "deepseek-chat": {"display_name": "DeepSeek Chat", "last_updated": "2025-01-27"}
        },
        "weight_source": {
            "source": "LMArena.ai",
            "file": "base_weights_lmarena.json",
            "updated_at": "2025-11-02"
        }
    }
    
    # 事件分析结果
    full_analysis = {
        "event_category": "economy",
        "event_category_display": "经济指标",
        "market_trend": "新市场，数据不足",
        "sentiment_trend": "neutral",
        "sentiment_score": 0.0,
        "sentiment_sample": 20,
        "sentiment_source": "GDELT",
        "rules_summary": "The FED interest rates are defined in this market by the upper bound of the target range for the federal funds rate set by the Federal Open Market Committee (FOMC) at their scheduled meeting in December 2025."
    }
    
    # 归一化信息
    normalization_info = {
        "total_before": 103.5,
        "total_after": 100.0,
        "error": 0.0,
        "skipped_count": 0
    }
    
    print("📊 准备写入以下数据：")
    print(f"   事件: {event_data['question']}")
    print(f"   选项数量: {len(fused_outcomes)}")
    print(f"   归一化前总和: {normalization_info['total_before']:.1f}%")
    print(f"   归一化后总和: {normalization_info['total_after']:.1f}%")
    print()
    
    # 写入 Notion
    print("📝 正在写入 Notion...")
    try:
        result = logger.log_prediction(
            event_data=event_data,
            fusion_result=aggregated_fusion_result,
            full_analysis=full_analysis,
            outcomes=fused_outcomes,
            normalization_info=normalization_info
        )
        
        if result:
            print()
            print("=" * 60)
            print("✅ 写入成功！")
            print("=" * 60)
            print()
            print("💡 请前往 Notion 数据库查看结果：")
            print(f"   https://www.notion.so/{logger.database_id}")
            return True
        else:
            print()
            print("❌ 写入失败（可能被限流或重复检查）")
            return False
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ 写入异常: {type(e).__name__}: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = write_latest_prediction()
    sys.exit(0 if success else 1)

