# Polymarket AI Predictor — Codex 项目全景

## 1. 文件树摘要（核心文件与依赖）

### `src/`（业务主干）
- `main.py` — Telegram Bot 入口；定义 `ForecastingBot`、命令处理与 `/predict` 工作流，串联全部层级。
- `event_manager.py` — 解析用户输入、调用 Polymarket REST/GraphQL/CLOB API 与网页抓取；输出结构化 `event_data`。
- `event_analyzer.py` — `EventAnalyzer` 负责事件分类、市场趋势、舆情信号、世界温度；大量 async API（GDELT/NewsAPI/Mediastack）和缓存。
- `prompt_builder.py` — `PromptBuilder` 根据事件信息、维度映射与 `prompt_templates.py` 生成多模型提示词。
- `model_orchestrator.py` — `ModelOrchestrator` 读取 `config/models.json`，通过 AICan API 并发调用 GPT‑4o、Claude、Gemini、DeepSeek 等；封装重试、超时、fallback。
- `fusion_engine.py` — `FusionEngine` 载入 `config/base_weights_lmarena.json`，用自定义统计（不依赖 numpy）融合模型结果，并应用市场加权/校准/惩罚。
- `output_formatter.py` — `OutputFormatter` 将融合结果按候选人型/条件型模板输出 Telegram Markdown。
- `notion_logger.py` — `NotionLogger` 使用 `notion-client` 将预测写入 Notion 数据库，含限流/可用性自检。
- `news_cache.py` — 新闻聚合缓存；可调用 `services/news_fetcher`，但当前通过 `NEWS_CACHE_ENABLED=False` 默认禁用，并写入 `cache/news_cache.json`。
- `world_sentiment_engine.py` — 基于新闻缓存计算“世界温度”；同样受 `WORLD_SENTIMENT_ENABLED` 开关保护。
- `openrouter_assistant.py` — 可用 OpenRouter 免费模型生成全球新闻摘要；`OPENROUTER_ASSISTANT_ENABLED` 默认为 False。
- `ablation.py` / `metrics.py` / `test_experiments.py` — 离线实验与评估工具，复用 `FusionEngine` 与自定义指标。
- `services/`（位于 `src/` 内） — `news_fetcher` 子包：Google RSS、Reddit、GDELT、NewsData、Wikipedia 采集器及聚合器。

### `config/`
- `models.json` — 每个 AI 模型的 display name、API 源、权重、fallback、启用状态。
- `base_weights_lmarena.json` — LMArena 权重基线，供 `FusionEngine` 读取。
- `update_lmarena_weights.py` — 通过 LMArena API 更新上述权重，供 `main.py` 启动时调用。
- `experiments.yaml` — 消融实验配置（可覆盖环境变量）。

### `services/`
- `llm_clients/openrouter_layer.py` — 对 OpenRouter API 的 httpx + tenacity 包装，提供 `call_openrouter_model`、模型白名单与结果清洗。

### 运行期/资源文件
- `prompt_templates.py`、`model_roles.json` — 模型分工和 Prompt 模板。
- `sentiment_cache.json`, `rate_limit_log.json`, `cache/news_cache.json` — 舆情与新闻缓存。
- 日志与脚本：`bot_output.log`, `module_activation_report.md`, `system_summary.md` 等。

## 2. 模块职责简表

| 阶段 | 文件 / 类 | 主要职责 | 输入 | 输出 / 依赖 |
| --- | --- | --- | --- | --- |
| 入口 & 指令 | `src/main.py` / `ForecastingBot` | 注册 Telegram handlers、处理 `/predict`、路由到各层 | Telegram `Update`、`Context` | 调用链、最终回复；依赖 `python-telegram-bot` |
| 事件解析 | `event_manager.py` / `EventManager` | 解析文本或 URL、fetch Polymarket (REST/GraphQL/CLOB) 并可网页抓取 | 用户消息文本或 slug | `event_data` dict (`question`, `rules`, `outcomes`, `market_prob`, `is_multi_option`, …) |
| 事件分析 | `event_analyzer.py` / `EventAnalyzer` | 分类、市场趋势、舆情、规则摘要、世界温度集成 | `event_title`, `rules`, `market_prob`, `market_slug` | `full_analysis` dict（类别、trend、sentiment、world_temp 等）；依赖 aiohttp、News APIs、`world_sentiment_engine` |
| Prompt 生成 | `prompt_builder.py` / `PromptBuilder` | 拼接模板、注入世界温度/新闻摘要、模型特化 | `event_data`, `model_assignment` | `prompts` dict：`model_name -> prompt str` |
| 模型编排 | `model_orchestrator.py` / `ModelOrchestrator` | 读取 `config/models.json`，用 aiohttp 调用 AICan/DeepSeek API，重试+超时 | `prompts`, 模型清单 | `model_results`: `model -> {probability, confidence, reasoning}`；依赖 env API keys |
| 融合 | `fusion_engine.py` / `FusionEngine` | 基于 LMArena 权重和置信度计算加权均值/方差、市场融合、惩罚、校准 | `model_results`, `model_weights`, `market_prob` | `fusion_result` dict（`final_prob`, `model_only_prob`, `uncertainty`, `summary`, …） |
| 输出 | `output_formatter.py` / `OutputFormatter` | Markdown 格式化（候选人/条件/多选项）、转义 | `event_data`, `fusion_result`, `outcomes` | Telegram Markdown 字符串 |
| 结果持久化 | `notion_logger.py` / `NotionLogger` | 将预测写入 Notion 数据库（可选） | `event_data`, `fusion_result`, `full_analysis` | Notion page（需要 `notion-client`, token） |
| 辅助 | `news_cache.py`, `world_sentiment_engine.py`, `openrouter_assistant.py`, `services/news_fetcher/*` | 新闻抓取与缓存、世界舆情、OpenRouter 新闻摘要 | 各类 API key、缓存文件 | 用于 `event_analyzer` 与 `prompt_builder` 的上下文信息 |
| 实验 | `ablation.py`, `metrics.py`, `test_experiments.py` | 离线评估/消融、指标计算 | 历史数据 CSV / 模拟结果 | 报表、统计指标 |

## 3. 数据流（输入 → 预测输出）

```
Telegram /predict
    ↓ (src/main.py → ForecastingBot.handle_predict async handler)
EventManager.parse_event_from_message()
    ↓
EventManager.fetch_polymarket_data()  [async, 25s timeout, REST/GraphQL/HTML fallbacks]
    ↓ event_data {question, rules, market_prob, outcomes, slug…}
EventAnalyzer.analyze_event_full()  [async, caching, News APIs]
    ↓ full_analysis {category, market_trend, sentiment, world_temp…}
PromptBuilder.build_prompt() per model (injects world_temp/news summaries)
    ↓ prompts dict
ModelOrchestrator.call_models_parallel()  [asyncio.gather, per-model retry/timeout]
    ↓ model_results {model: {probability(0-100), confidence, reasoning}}
FusionEngine.fuse_predictions()  (weights + market bias + calibration)
    ↓ fusion_result {final_prob, model_only_prob, uncertainty, summary, disagreement…}
OutputFormatter.format_*()  (single vs multi-option templates)
    ↓ Telegram Markdown response
NotionLogger.log_prediction()  (optional side-effect, with rate limiting)
```

**数据格式要点**
- `event_data`: dict，含 `question`, `rules`, `outcomes`(List[{name, probability?...}]), `market_prob`, `is_multi_option`, `market_slug`, `world_temp`, `news_summary`.
- `model_results`: `Dict[str, Optional[Dict[str, Any]]]`，每个结果包含 `probability` (0‑100), `confidence` (`low|medium|high`), `reasoning` (≤200 chars)。
- `fusion_result`: 包含 `final_prob`, `model_only_prob`, `uncertainty`, `summary`, `disagreement`, `model_versions`, `weight_source`, optional `demarket_applied`/`calibration_applied`.
- 输出：Markdown 字符串（候选人型/条件型/多选项），并可带多行 bullet。

## 4. 模型与外部接口

| 服务 / 模型 | 调用位置 | 作用 / 传参 |
| --- | --- | --- |
| **Telegram Bot API** | `main.py` (`Application`, handlers) | 接收 `/predict`、发送回复；需 `TELEGRAM_BOT_TOKEN`。 |
| **Polymarket APIs** | `EventManager.fetch_polymarket_data` | REST `/markets`, GraphQL `/query`, `/events?slug=`, CLOB 实时报价；当失败时 fallback HTML 抓取或 mock 数据。 |
| **Polymarket scraping** | `EventManager.scrape_market_from_url` | 解析网页 `__NEXT_DATA__`；用于 API 不可用时。 |
| **News sources** | `src/services/news_fetcher/*`, `news_cache.py`, `event_analyzer.py` | Google RSS、Reddit、GDELT、NewsAPI、Mediastack、Wikipedia；供舆情和世界温度使用。 |
| **World Sentiment** | `world_sentiment_engine.py` | 从 `news_cache` 计算 WTI；当前默认禁用。 |
| **OpenRouter free models** | `services/llm_clients/openrouter_layer.py`, `openrouter_assistant.py`, `main.py` multi-option补充 | 生成新闻摘要或多选项额外模型，需要 `OPENROUTER_API_KEY`, `tenacity`。 |
| **AICan API / DeepSeek API** | `ModelOrchestrator` | 主推理通道；使用 `aiohttp` POST OpenAI 格式请求，读取 env API keys。 |
| **LMArena API** | `config/update_lmarena_weights.py` | 更新模型基础权重，写入 `base_weights_lmarena.json`。 |
| **Notion API** | `NotionLogger` | 记录预测；需要 `NOTION_TOKEN`, `NOTION_DB_ID`。 |

## 5. 缓存与状态机制

- **新闻缓存** (`cache/news_cache.json`): `news_cache.fetch_and_cache_news` 读取/写入，包含 `timestamp` 与 `news`；当前 `NEWS_CACHE_ENABLED=False`，调用直接返回空列表。
- **舆情缓存** (`sentiment_cache.json`): `EventAnalyzer._check_cache/_save_to_cache` 存储最近 3 小时的舆情分析；命中时跳过外部 API。
- **限流日志** (`rate_limit_log.json`): 记录 NewsAPI / Mediastack 调用时间与计数，控制 `RATE_LIMIT_INTERVAL` 和每小时配额。
- **世界温度** (`world_sentiment_engine`): 依赖新闻缓存数据；`WORLD_SENTIMENT_ENABLED=False` 时返回 `None`。
- **LMArena 权重** (`config/base_weights_lmarena.json`): `FusionEngine` 初始化读取；`main.py` 启动时可调用 `update_lmarena_weights.should_update()` 决定是否刷新。
- **Model 配置** (`config/models.json` + env API keys): 控制启用模型、权重、接口；`ModelOrchestrator` 在初始化时一次性加载。
- **Notion 限流**: `NotionLogger` 通过 `last_write_time` 确保 ≥5s 间隔。
- **Fallback & None 处理**: 各模块在缺失依赖时返回默认结构（如 50% 概率、空新闻、`world_temp=None`），避免 `NoneType.__format__`。

## 6. 异步逻辑与风险点

- **`ForecastingBot.handle_predict`**：全链路 `async`；使用 `asyncio.create_task` 异步预加载新闻缓存，并通过 `add_done_callback` 捕获异常；主要 await 点：
  - `EventManager.fetch_polymarket_data()` — 多次 HTTP 调用串行执行，单次 `asyncio.wait_for(..., timeout=25s)`，若全失败则生成 mock 市场。
  - `EventAnalyzer.analyze_event_full()` — 内部再等待 `_get_market_trend`、`_get_sentiment_signal` 等；整体 `await asyncio.wait_for(..., timeout=15s)`，超时返回默认分析。
  - `ModelOrchestrator` 调用 — 每个模型 `asyncio.wait_for` + 重试 + `asyncio.sleep` 回退；`call_models_parallel` 使用 `asyncio.gather` 和信号量控制并发，仍可能受到慢 API 阻塞。
  - `asyncio.wait_for` 用于多选项模型调用与 OpenRouter 补充层。
- **`news_cache` 与 `world_sentiment_engine`**：即使禁用也保持 async 签名，立即返回空结果，避免卡死；启用后需注意多个网络调用并发，建议配合 `asyncio.gather`.
- **`ModelOrchestrator` 风险**：
  - 依赖环境变量中的 API Key；缺失时返回 `None`，导致成功模型数量减少。
  - `aiohttp.ClientSession` 在每次调用中创建/关闭；大量调用可能增加开销。
  - 网络异常/超时会返回低置信度 50% 默认值，影响 `FusionEngine` 结果。
- **依赖缺失 degrade**：
  - `python-telegram-bot`, `tenacity`, `notion-client`, `news_fetcher` 任一缺失都会触发日志并禁用相应模块，而不会崩溃；需要手动安装重新启用。
- **潜在阻塞/错误点**：
  - Polymarket API 若持续失败将触发 HTML 抓取（单线程），可能耗时较长。
  - NewsAPI/Mediastack 配额耗尽 -> `_check_rate_limit` 返回 False，舆情只能依赖缓存/默认值。
  - `config/update_lmarena_weights` 使用 `httpx` 同步调用，如运行在主线程需注意超时（10s）。

## 7. 补充说明

- **模型链路**：默认链路 `EventManager → EventAnalyzer → PromptBuilder → ModelOrchestrator → FusionEngine → OutputFormatter → NotionLogger`；附加 OpenRouter/新闻/世界温度会在 `EventAnalyzer` 与 `PromptBuilder` 中注入额外上下文。
- **多选项市场**：`main.py` 会为每个 outcome 复用 prompts 并调用模型预测，之后使用 `FusionEngine` 对每个 outcome 的 `model_results` 做独立融合，再通过 `OutputFormatter.format_multi_option_prediction` 汇总。
- **实验与监控**：`ablation.py`/`metrics.py` 支持 Brier Score、LogLoss、ECE、Sharpness 和 t-test；`module_activation_report.md`, `system_summary.md` 提供运行期人工记录。
- **依赖管理**：`requirements.txt` 列出所有第三方依赖；numpy 已从运行管线移除，但仍用于实验脚本，可按需安装合适版本。

> 本文档仅分析现有实现，未对代码进行任何修改。需要更深入的函数级别说明，可结合 `SYSTEM_SPEC.md`、`OPTIMIZATION_NOTES.md` 与各模块 docstring 阅读。
