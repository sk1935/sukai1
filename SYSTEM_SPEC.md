# 🧠 Multi-Model Forecasting System (Telegram + Polymarket + OpenRouter + DeepSeek)

## 🎯 Goal

构建一个 Telegram Bot，自动预测 Polymarket 事件。

- 用户输入事件；
- 系统抓取市场数据与规则；xian z
- 调用多个模型（DeepSeek + OpenRouter）；
- 融合概率与分析结果；
- 输出解释性预测报告。

---

## 🧩 System Architecture

### Modules

| 模块 | 职责 |
|------|------|
| **Event Manager** | 解析 Telegram 输入，抓取 Polymarket API 数据（概率、规则、趋势） |
| **Prompt Builder** | 拼接 Prompt（含规则、市场概率、时间等） |
| **Model Orchestrator** | 并行调用多个模型 API（DeepSeek + OpenRouter） |
| **Fusion Engine** | 聚合模型输出，加权平均并结合市场概率 |
| **Output Formatter** | 生成 Telegram 输出（Markdown） |
| **Scheduler (可选)** | 定时任务 / 预测校准 |

---

## ⚙️ Tech Stack

- Python 3.11+
- `python-telegram-bot`
- `aiohttp` + `asyncio`
- `numpy`, `pandas`
- `.env` + `dotenv`
- Polymarket API
- DeepSeek API + OpenRouter API

---

## 🧠 Prompt Template

```python
PROMPT_TEMPLATE = """
You are an expert forecaster contributing to a multi-model ensemble prediction system.

Event: {event_title}
Rules: {event_rules}
Market probability: {market_prob}%
Time until resolution: {days_left} days
Your dimension: {dimension_description}

Output JSON:
{{"probability": <number>, "confidence": "<low|medium|high>", "reasoning": "<brief>" }}
"""
```

---

## 📊 Output Format

```
📊 Event: {event_title}

🧠 Model Consensus: {final_prob}% ± {uncertainty}
📈 Polymarket: {market_prob}% ({trend})
💬 Summary: {summary}
⚖️ Disagreement: {disagreement}
📜 Rules: {short_rules}
```

---

## 🔧 Project Structure

```
/project
 ├── src/
 │   ├── event_manager.py
 │   ├── prompt_builder.py
 │   ├── model_orchestrator.py
 │   ├── fusion_engine.py
 │   ├── output_formatter.py
 │   └── main.py
 ├── prompt_templates.py
 ├── model_roles.json
 ├── .env
 └── SYSTEM_SPEC.md
```





