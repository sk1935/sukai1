"""
提示层（Prompt Builder）：
根据 OPTIMIZATION_NOTES.md 的五层架构设计

职责：
- 根据事件信息生成多模型统一提示词
- 每个模型使用同一事件描述，但可以根据模型特性调整角度
- 通过 EventAnalyzer 获取模型任务分工，生成专业化提示
- 集成世界温度和新闻摘要信息（如果可用）

输入：事件数据 {question, rules, market_prob, days_left, world_temp, news_summary}
输出：各模型的输入 prompt（字符串）
"""
import sys
from pathlib import Path
from typing import Dict, Optional
import asyncio

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from prompt_templates import PROMPT_TEMPLATE, SPECIALIZED_PROMPT_TEMPLATE, DIMENSION_TEMPLATES

# 导入新闻摘要（如果可用）
try:
    from src.openrouter_assistant import get_news_summary
    NEWS_SUMMARY_AVAILABLE = True
except ImportError:
    NEWS_SUMMARY_AVAILABLE = False


class PromptBuilder:
    """
    Builds specialized prompts for different model dimensions.
    
    根据事件数据和模型分工，构建专业化提示词。
    支持：
    - 专业化维度提示（通过 EventAnalyzer 分配任务）
    - 通用模板提示（fallback）
    - 所有提示要求模型使用中文输出
    """
    
    def __init__(self):
        pass
    
    def _build_world_temp_section(self, event_data: Dict) -> str:
        """构建世界温度部分（如果可用）- 轻量描述模式"""
        # 【轻量描述模式】world_temp 现在是描述字符串，不是数值
        world_temp = event_data.get("world_temp")  # 描述字符串，如 "全球舆情总体偏正面"
        world_sentiment_summary = event_data.get("world_sentiment_summary")
        world_temp_data = event_data.get("world_temp_data")  # 完整数据字典
        
        if world_temp:
            # 直接使用描述字符串
            section = f"- Global Sentiment: {world_temp}"
            if world_temp_data:
                positive = world_temp_data.get("positive", 0)
                negative = world_temp_data.get("negative", 0)
                neutral = world_temp_data.get("neutral", 0)
                section += f" (Positive: {positive}, Negative: {negative}, Neutral: {neutral})"
            if world_sentiment_summary:
                section += f"\n  {world_sentiment_summary}"
            return section
        elif world_sentiment_summary:
            # 如果没有描述，使用摘要
            return f"- Global Sentiment: {world_sentiment_summary}"
        return ""
    
    def _build_global_sentiment_guidance(self, event_data: Dict) -> str:
        """根据全球舆情提供对模型的决策提示"""
        world_temp_data = event_data.get("world_temp_data") or {}
        description = (event_data.get("world_temp") or event_data.get("world_sentiment_summary") or "").lower()
        positive = world_temp_data.get("positive")
        negative = world_temp_data.get("negative")
        try:
            positive = int(positive)
        except (TypeError, ValueError):
            positive = None
        try:
            negative = int(negative)
        except (TypeError, ValueError):
            negative = None
        guidance = ""
        if isinstance(positive, int) and isinstance(negative, int):
            if negative > positive * 1.2 and negative - positive >= 5:
                guidance = (
                    "- Sentiment Guidance: Global mood is risk-off. "
                    "请更关注下行风险，谨慎对待过度乐观的推断。"
                )
            elif positive > negative * 1.2 and positive - negative >= 5:
                guidance = (
                    "- Sentiment Guidance: Global mood is mildly risk-on. "
                    "可以识别潜在上行机会，但仍需验证逻辑链。"
                )
        if not guidance and description:
            if "negative" in description or "bearish" in description or "偏负" in description:
                guidance = (
                    "- Sentiment Guidance: 舆情偏负面，请降低乐观程度并多考虑防御性场景。"
                )
            elif "positive" in description or "bullish" in description or "偏正" in description:
                guidance = (
                    "- Sentiment Guidance: 舆情偏正面，可在推理中适度考虑有利因素。"
                )
        return guidance
    
    def _build_news_summary_section(self, event_data: Dict) -> str:
        """构建新闻摘要部分（如果可用）"""
        # 优先从 event_data 获取
        news_summary = event_data.get("news_summary")
        
        if news_summary:
            return f"- Recent Global News Summary:\n  {news_summary[:500]}"  # 限制长度
        
        # 如果没有，尝试从 openrouter_assistant 获取（异步）
        if NEWS_SUMMARY_AVAILABLE:
            try:
                # 注意：这里不能直接使用 await，因为 build_prompt 是同步函数
                # 可以考虑在调用 build_prompt 之前预先获取 news_summary
                pass
            except:
                pass
        
        return ""
    
    def build_prompt(self, event_data: Dict, model_name: str, model_assignment: Optional[Dict] = None) -> str:
        """
        Build a specialized prompt for a specific model.
        
        Args:
            event_data: Dict with 'question', 'rules', 'market_prob', 'days_left', 
                       'world_temp', 'news_summary' (optional)
            model_name: Name of the model
            model_assignment: Optional dict with dimension assignment from EventAnalyzer
        
        Returns:
            Formatted prompt string
        """
        # 【新增】添加调试日志
        print(f"[PromptBuilder] 🎯 为模型 {model_name} 构建提示词")
        
        # 构建世界温度和新闻摘要部分
        world_temp_section = self._build_world_temp_section(event_data)
        global_guidance_section = self._build_global_sentiment_guidance(event_data)
        news_summary_section = self._build_news_summary_section(event_data)
        
        if global_guidance_section:
            world_temp_section = "\n".join(
                part for part in [world_temp_section, global_guidance_section] if part
            )
        
        # 【新增】日志输出全球上下文信息
        # 【修复】检查 world_temp 是否为 None 再格式化
        world_temp = event_data.get("world_temp")
        if world_temp:
            print(f"[PromptBuilder] 🌍 全球情绪描述: {world_temp}")
        elif event_data.get("world_sentiment_summary"):
            print(f"[PromptBuilder] 🌍 全球情绪摘要: {event_data['world_sentiment_summary']}")
        if global_guidance_section:
            print("[PromptBuilder] 🎛️ 已根据全球舆情调整推理侧重点")
        if event_data.get("news_summary"):
            print(f"[PromptBuilder] 📰 已注入新闻摘要 ({len(event_data['news_summary'])} 字符)")
        
        # 如果都没有，使用空字符串
        if not world_temp_section and not news_summary_section:
            world_temp_section = ""
            news_summary_section = ""
        
        # If we have a specialized assignment, use it
        if model_assignment:
            prompt = SPECIALIZED_PROMPT_TEMPLATE.format(
                specialization_name=model_assignment.get("specialization", "Forecasting"),
                dimension_name=model_assignment.get("dimension_name", "General Analysis"),
                dimension_description=model_assignment.get("dimension_description", "Analyze the event"),
                event_title=event_data.get("question", ""),
                event_rules=event_data.get("rules", ""),
                market_prob=event_data.get("market_prob", 50.0),
                days_left=event_data.get("days_left", 30),
                world_temp_section=world_temp_section or "(No global sentiment data available)",
                news_summary_section=news_summary_section or "(No news summary available)"
            )
        else:
            # Fallback to generic template
            dimension = DIMENSION_TEMPLATES.get(
                model_name,
                "General forecasting analysis"
            )
            
            prompt = PROMPT_TEMPLATE.format(
                event_title=event_data.get("question", ""),
                event_rules=event_data.get("rules", ""),
                market_prob=event_data.get("market_prob", 50.0),
                days_left=event_data.get("days_left", 30),
                dimension_description=dimension,
                world_temp_section=world_temp_section or "(No global sentiment data available)",
                news_summary_section=news_summary_section or "(No news summary available)"
            )
        
        has_world_temp = world_temp is not None
        has_news_summary = bool(event_data.get("news_summary"))
        print(
            f"[PromptBuilder] ✅ 提示词生成完成 | 模型 {model_name} | "
            f"world_temp={has_world_temp} | news_summary={has_news_summary} | "
            f"长度={len(prompt)}"
        )
        
        return prompt
