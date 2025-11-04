# Polymarket AI Predictor - 系统诊断报告

**生成时间**：2025-11-04 07:20:05 CST  
**检测命令**：`python3 -m py_compile src/main.py`、`python3 src/main.py --list-models`、`python3 src/main.py`

---

## 📋 检测摘要
- `main.py` 可以导入并运行自检；当 Telegram 依赖缺失时会输出友好提示而非崩溃。
- 核心链路 `EventManager → EventAnalyzer → PromptBuilder → ModelOrchestrator → FusionEngine → OutputFormatter → NotionLogger` 全部可导入并执行关键路径。
- 可选模块 `news_cache`、`world_sentiment_engine`、`openrouter_assistant` 已按指示进入“瘦身模式”，保持导入成功但内部直接短路返回安全默认值。
- 由于外部依赖缺失（`python-telegram-bot`, `tenacity`, `notion-client`），整体评估为 **⚠️ 部分失效**。

---

## 🧩 模块健康状态

| 模块 | 导入测试 | 运行/调用 | 风险与说明 |
| --- | --- | --- | --- |
| `main.py` | ✅ | ⚠️ `python-telegram-bot` 未安装，启动时会提示并退出 | 需 `pip install python-telegram-bot==20.7` 才能连接 Telegram |
| `event_manager` | ✅ | ✅ | 可正常拉取/解析市场数据；网络异常时已有 mock fallback |
| `event_analyzer` | ✅ | ⚠️ | 新闻/世界温度依赖被禁用，返回默认舆情；核心分类逻辑正常 |
| `prompt_builder` | ✅ | ✅ | 仅依赖事件分析结果，无外部风险 |
| `model_orchestrator` | ✅ | ✅ | `--list-models` 命令可用；Grok 仍被标记为禁用 |
| `fusion_engine` | ✅ | ✅ | 已移除 `numpy`，使用纯 Python 加权统计，解决导入即崩溃问题 |
| `output_formatter` | ✅ | ✅ | 具备 `(value or 0.0)` 空值保护 |
| `notion_logger` | ✅ | ⚠️ 缺少 `notion-client` | 导入时提示依赖缺失，写入将被跳过 |
| `news_cache` | ✅ | 🚫（主动禁用） | `NEWS_CACHE_ENABLED=False`，直接返回空结果，避免缺失 `news_fetcher` 时的异常 |
| `world_sentiment_engine` | ✅ | 🚫（主动禁用） | `WORLD_SENTIMENT_ENABLED=False`，调用时返回 `None` 并记录日志 |
| `openrouter_assistant` | ✅ | 🚫（主动禁用） | `OPENROUTER_ASSISTANT_ENABLED=False`，并对 `tenacity` 缺失做降级 |

---

## 🛠️ 修复与瘦身措施
1. **FusionEngine 崩溃修复**  
   - 根因：系统 Python 的 `numpy` 导入触发 Segmentation Fault，导致 `fusion_engine`/`main.py` 甚至无法导入。  
   - 处理：使用 `math.fsum` 与自定义权重统计替换所有 `numpy` 依赖，并新增 `_safe_float`、 `_weighted_std` 等空值保护函数。  
   - 效果：`python3 -m py_compile src/main.py`、模块导入、融合计算均稳定。

2. **OpenRouter 依赖缺失**  
   - 根因：`services.llm_clients.openrouter_layer` 依赖 `tenacity`。  
   - 处理：`main.py` 与 `openrouter_assistant.py` 均增加 `try/except`，当依赖缺失时提供占位函数与 `OPENROUTER_*_ENABLED=False` 标志，避免 ImportError。  
   - 效果：主流程只在 OpenRouter 可用时调用，禁用后仍可预测。

3. **新闻与世界舆情模块瘦身**  
   - 根因：`news_fetcher` 缺失导致链路阻塞。  
   - 处理：`news_cache`, `world_sentiment_engine` 统一增加全局开关，禁用时立刻返回空列表/提示语；异步调用仍会记录日志但不会抛错。  
   - 效果：`/predict` 主链只在需要时创建后台任务，任务失败也不会影响用户请求。

4. **Telegram 依赖缺失提示**  
   - 根因：环境未安装 `python-telegram-bot`，过去会 ImportError。  
   - 处理：在 `main.py` 顶部包裹导入并在 `main()` 入口提前检测，给出安装指令。  
   - 效果：CLI 自检（`--list-models`）可在无 Telegram 环境运行；启动机器人时有明确提示。

5. **None / f-string / await 审计**  
   - `fusion_engine`, `event_analyzer`, `news_cache` 等涉及概率或数值输出的位置统一通过 `(value or 0.0)`、`_safe_float` 处理，避免 `NoneType.__format__`。  
   - 所有新添加的异步调用（例如 `call_openrouter_model`, `fetch_and_cache_news`）都包裹在 `try/except` 中并打印模块化日志。  
   - 返回值为 `None` 的函数（禁用模块）全部返回结构化的默认值（空列表或文案），防止上层崩溃。

---

## ❗ 未解风险与后续建议
1. **外部依赖缺失**  
   - Telegram Bot：`pip install python-telegram-bot==20.7`。  
   - Notion 日志：`pip install notion-client`。  
   - OpenRouter 重启：`pip install tenacity` 并在 `.env` 中配置 OpenRouter key，然后把 `OPENROUTER_ASSISTANT_ENABLED`/`OPENROUTER_INTEGRATION_AVAILABLE` 打开。

2. **可选模块恢复策略**  
   - 当 `news_fetcher` 或外部 API 恢复可用时，将 `NEWS_CACHE_ENABLED / WORLD_SENTIMENT_ENABLED / OPENROUTER_ASSISTANT_ENABLED` 设为 `True`，即可重新启用，不影响当前核心链路。

3. **测试建议**  
   - 在安装 Telegram 依赖后执行一次 `/predict` 流程冒烟测试，确保新的空值保护和降级逻辑覆盖真实数据。  
   - 若需部署在线服务，可新增健康检查脚本（调用 `python3 src/main.py --list-models`）以检测模型表是否正确加载。

---

## 🏁 系统整体评估
- **等级**：⚠️ 部分失效  
- **原因**：核心 AI 流程可运行，但 Telegram、Notion、OpenRouter 依赖缺失，导致部分增强功能被迫禁用。  
- **恢复路径**：安装缺失依赖即可恢复对应模块，无需改动代码；当前稳定性保护确保在依赖缺失时系统仍能生成预测结果并输出中文报告。

