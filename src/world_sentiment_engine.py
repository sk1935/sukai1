"""
世界情绪引擎（轻量描述模式）

功能：
- 从 news_cache.json 读取新闻数据
- 通过关键词判断整体情绪倾向
- 返回描述性字符串（如 "全球舆情总体偏正面"）
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, List
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 相对导入（同目录）
from src.news_cache import CACHE_FILE, load_cache

WORLD_SENTIMENT_ENABLED = os.getenv("WORLD_SENTIMENT_ENABLED", "false").lower() == "true"


def compute_world_temperature() -> Optional[Dict]:
    """
    计算全球舆情温度（轻量描述模式）
    
    通过关键词判断情绪倾向，返回描述性字符串
    
    Returns:
        Dict: {
            "description": str,  # 描述性字符串，如 "全球舆情总体偏正面"
            "positive": int,      # 正面新闻数量
            "negative": int,      # 负面新闻数量
            "neutral": int,       # 中性新闻数量
            "total_samples": int  # 总样本数
        }
        如果缓存为空，返回 None
    """
    if not WORLD_SENTIMENT_ENABLED:
        print("🛑 [WORLD_SENTIMENT] 功能已禁用，跳过世界温度计算")
        return None
    
    try:
        # 加载缓存
        cached_data = load_cache()
        
        if not cached_data or not cached_data.get("news"):
            print("⚠️ 新闻缓存为空，无法计算世界温度")
            return None
        
        news_list = cached_data["news"]
        
        # 定义关键词列表
        positive_keywords = [
            "growth", "peace", "agreement", "stable", "increase", "rise", "gain",
            "success", "progress", "improvement", "recovery", "boost", "surge",
            "victory", "achievement", "breakthrough", "expansion", "prosperity",
            "增长", "和平", "稳定", "提升", "成功", "进步", "改善", "复苏"
        ]
        
        negative_keywords = [
            "war", "decline", "conflict", "inflation", "protest", "crisis", "crash",
            "fall", "drop", "loss", "failure", "threat", "attack", "violence",
            "recession", "unemployment", "debt", "default", "collapse", "strike",
            "战争", "冲突", "危机", "崩溃", "失败", "威胁", "攻击", "暴力",
            "衰退", "失业", "债务", "违约", "崩溃", "罢工"
        ]
        
        # 统计情绪
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        
        for news in news_list:
            # 获取标题和摘要
            title = (news.get("title", "") or "").lower()
            summary = (news.get("summary", "") or "").lower()
            text = f"{title} {summary}"
            
            # 检查关键词
            has_positive = any(keyword.lower() in text for keyword in positive_keywords)
            has_negative = any(keyword.lower() in text for keyword in negative_keywords)
            
            if has_positive and not has_negative:
                positive_count += 1
            elif has_negative and not has_positive:
                negative_count += 1
            elif has_positive and has_negative:
                # 同时包含正负面关键词，根据数量判断
                pos_matches = sum(1 for kw in positive_keywords if kw.lower() in text)
                neg_matches = sum(1 for kw in negative_keywords if kw.lower() in text)
                if pos_matches > neg_matches:
                    positive_count += 1
                elif neg_matches > pos_matches:
                    negative_count += 1
                else:
                    neutral_count += 1
            else:
                neutral_count += 1
        
        total_samples = len(news_list)
        
        if total_samples == 0:
            print("⚠️ 新闻列表为空，无法计算世界温度")
            return None
        
        # 生成描述性字符串
        positive_ratio = positive_count / total_samples
        negative_ratio = negative_count / total_samples
        neutral_ratio = neutral_count / total_samples
        
        # 判断主要情绪倾向
        if positive_ratio > 0.4:
            if negative_ratio < 0.2:
                description = "全球舆情总体偏正面"
            elif negative_ratio > 0.3:
                description = "全球情绪中性偏正"
            else:
                description = "全球舆情总体偏正面"
        elif negative_ratio > 0.4:
            if positive_ratio < 0.2:
                description = "全球舆情总体偏负面"
            elif positive_ratio > 0.3:
                description = "全球情绪中性偏负"
            else:
                description = "全球舆情总体偏负面"
        elif neutral_ratio > 0.5:
            description = "全球情绪中性为主"
        elif abs(positive_ratio - negative_ratio) < 0.1:
            description = "全球情绪中性偏平衡"
        else:
            description = "暂无显著情绪信号"
        
        print(f"🌍 世界温度计算完成（描述模式）: {description}")
        print(f"   情绪分布: 正面 {positive_count}, 负面 {negative_count}, 中性 {neutral_count}")
        
        return {
            "description": description,
            "positive": positive_count,
            "negative": negative_count,
            "neutral": neutral_count,
            "total_samples": total_samples
        }
        
    except Exception as e:
        print(f"❌ 计算世界温度时出错: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_world_temperature_summary(world_temp_data: Optional[Dict]) -> str:
    """
    获取世界温度的文本摘要（轻量描述模式）
    
    Args:
        world_temp_data: compute_world_temperature() 的返回结果
    
    Returns:
        str: 格式化的文本摘要
    """
    if not WORLD_SENTIMENT_ENABLED:
        return "世界温度数据暂未启用"
    
    if not world_temp_data:
        return "世界温度数据不可用"
    
    description = world_temp_data.get("description", "未知")
    positive = world_temp_data.get("positive", 0)
    negative = world_temp_data.get("negative", 0)
    neutral = world_temp_data.get("neutral", 0)
    
    summary = f"{description}（正面: {positive}, 负面: {negative}, 中性: {neutral}）"
    
    return summary


# 导出函数
__all__ = [
    "compute_world_temperature",
    "get_world_temperature_summary"
]
