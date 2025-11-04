"""
Prompt templates for multi-model forecasting system.
"""

# New specialized prompt template for dimension-based analysis
# 优化：要求模型使用中文输出reasoning，确保后续融合和输出都是中文
SPECIALIZED_PROMPT_TEMPLATE = """
You are an expert forecaster specializing in {specialization_name}.

You are part of a multi-model ensemble prediction system. Each model focuses on a different dimension of the event.

**Your Specialized Dimension: {dimension_name}**

**Your Task: {dimension_description}**

**Event Information:**
- Event: {event_title}
- Rules: {event_rules}
- Current Market Probability: {market_prob}%
- Time until resolution: {days_left} days

**Global Context (Optional):**
{world_temp_section}
{news_summary_section}

**Important:** 
Focus ONLY on your specialized dimension ({dimension_name}). 
Analyze how this specific aspect affects the event outcome.
Provide a probability based primarily on your dimension's analysis.
Other models will cover other aspects, so don't try to cover everything.

**Language Requirement:**
Please provide your reasoning in Chinese (简体中文) to ensure consistency with the final report.

Output JSON:
{{
  "probability": <number 0-100>,
  "confidence": "<low|medium|high>",
  "reasoning": "<brief explanation in Chinese (简体中文) focusing on your dimension>"
}}
"""

# Fallback template (kept for backward compatibility)
# 优化：添加中文输出要求
PROMPT_TEMPLATE = """
You are an expert forecaster contributing to a multi-model ensemble prediction system.

Event: {event_title}
Rules: {event_rules}
Market probability: {market_prob}%
Time until resolution: {days_left} days
Your dimension: {dimension_description}

**Global Context (Optional):**
{world_temp_section}
{news_summary_section}

**Language Requirement:**
Please provide your reasoning in Chinese (简体中文).

Output JSON:
{{"probability": <number>, "confidence": "<low|medium|high>", "reasoning": "<brief explanation in Chinese (简体中文)>" }}
"""

DIMENSION_TEMPLATES = {
    "gpt-4o": "Multi-perspective analysis & logical reasoning",
    "claude-3-7-sonnet-latest": "Critical thinking & risk assessment",
    "gemini-2.5-flash": "Fast analysis & pattern recognition",
    "grok-3": "Alternative perspective & creative reasoning",
    "gpt-4o-mini": "Rapid analysis & consistency check"
}

