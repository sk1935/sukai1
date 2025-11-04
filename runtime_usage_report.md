# Polymarket AI Predictor - 运行时使用报告

**生成时间**: 2025-11-04 20:19:36  
**分析日志**: bot.log  
**最近一次预测**: Maduro out in 2025 (多选项事件，3个选项)

---

## 📊 模块调用状态表

| 模块名 | 文件路径 | 调用次数/行号 | 当前状态 | 日志标识 | 备注 |
|--------|----------|---------------|----------|----------|------|
| `event_manager` | `src/event_manager.py` | 2 次 (数据获取成功: 1次, 提取选项: 1次) | 已使用 | 🔍 | EventManager |
| `event_analyzer` | `src/event_analyzer.py` | 3 次 (分析完成: 1次, 类别检测: 1次) | 已使用 | 📊 | EventAnalyzer |
| `prompt_builder` | `src/prompt_builder.py` | 48 次 (构建提示词: 12次, 提示词完成: 12次) | 已使用 | 🎯 | PromptBuilder |
| `model_orchestrator` | `src/model_orchestrator.py` | 281 次 (调用所有模型: 7次, 模型调用: 255次) | 已使用 | 📤 | ModelOrchestrator |
| `fusion_engine` | `src/fusion_engine.py` | 7 次 (融合预测: 5次, 融合完成: 2次) | 已使用 | ✅ | FusionEngine |
| `output_formatter` | `src/output_formatter.py` | 1 次 (format_multi_option_prediction) | 已使用 | 📋 | OutputFormatter |
| `notion_logger` | `src/notion_logger.py` | 1 次 (log_prediction，多选项事件) | 已使用 | 📝 | NotionLogger |
| `news_cache` | `src/news_cache.py` | 3 次 (新闻缓存: 1次, 功能禁用: 2次) | 条件禁用 (NEWS_CACHE_ENABLED=False) | 📰 | None |
| `world_sentiment_engine` | `src/world_sentiment_engine.py` | 3 次 (世界情绪: 1次, 功能禁用: 1次) | 条件禁用 (WORLD_SENTIMENT_ENABLED=False) | 🌍 | None |
| `openrouter_assistant` | `src/openrouter_assistant.py` | 2 次 (功能禁用: 2次) | 条件禁用 (OPENROUTER_ASSISTANT_ENABLED=False) | 📰 | None |
| `openrouter_layer` | `src/services/llm_clients/openrouter_layer.py` | 21 次 (OpenRouter调用: 11次, Mistral模型: 8次) | 已使用 | 🆓 | None |

---

## 🔗 本次预测流程调用链

### 完整执行链路

```
main.py (handle_predict)
  ├─ EventManager.parse_event_from_message()      [✅ 已调用]
  │   └─ EventManager.fetch_polymarket_data()     [✅ 已调用，获取3个选项]
  │
  ├─ EventAnalyzer.analyze_event_full()           [✅ 已调用]
  │   ├─ EventAnalyzer._detect_category()         [✅ 已调用，类别: 地缘政治]
  │   ├─ EventAnalyzer._get_market_trend()        [✅ 已调用]
  │   ├─ EventAnalyzer._get_sentiment_signal()     [✅ 已调用，使用缓存数据]
  │   ├─ EventAnalyzer._extract_rules_summary()   [✅ 已调用]
  │   ├─ compute_world_temperature()               [❌ 条件禁用，WORLD_SENTIMENT_ENABLED=False]
  │   └─ get_news_summary()                        [❌ 条件禁用，OPENROUTER_ASSISTANT_ENABLED=False]
  │
  ├─ EventAnalyzer.analyze_event()                 [✅ 已调用，用于模型分配]
  │   └─ 模型分配: gpt-4o, claude-3-7-sonnet, deepseek-chat, gemini-2.5-pro
  │
  ├─ PromptBuilder.build_prompt()                  [✅ 已调用 12 次]
  │   ├─ 为每个选项的每个模型构建提示词
  │   ├─ world_temp=False (未使用)
  │   └─ news_summary=False (未使用)
  │
  ├─ ModelOrchestrator.call_all_models()          [✅ 已调用 3 次（每个选项1次）]
  │   ├─ GPT-4o                                    [✅ 成功，3次调用]
  │   ├─ Claude-3.7-Sonnet                         [✅ 成功，3次调用]
  │   ├─ Gemini-2.5-Pro                            [✅ 成功，3次调用]
  │   ├─ DeepSeek Chat                             [✅ 成功，3次调用]
  │   └─ OpenRouter (Mistral-7B)                   [⚠️ 部分成功，2/3次成功]
  │
  ├─ FusionEngine.fuse_predictions()               [✅ 已调用 3 次（每个选项1次）]
  │   └─ 融合结果: 23.6%, 12.1%, 45.0% (AI预测)
  │
  ├─ FusionEngine.normalize_all_predictions()      [✅ 已调用 1 次]
  │   └─ 归一化检查（条件事件检测）
  │
  ├─ OutputFormatter.format_multi_option_prediction() [✅ 已调用]
  │   └─ 生成 Markdown 格式输出
  │
  └─ NotionLogger.log_prediction()                 [✅ 已调用 1 次]
      └─ 写入 Notion 数据库
```

---

## ❌ 未参与的辅助模块

### 1. news_cache (📰)
- **状态**: 条件禁用
- **原因**: `NEWS_CACHE_ENABLED=False`（环境变量未设置或为 false）
- **日志**: `ℹ️ [NEWS_CACHE] 功能未启用，跳过预加载`
- **影响**: 新闻缓存预加载被跳过，不影响核心功能

### 2. world_sentiment_engine (🌍)
- **状态**: 条件禁用
- **原因**: `WORLD_SENTIMENT_ENABLED=False`（环境变量未设置或为 false）
- **日志**: `🛑 [WORLD_SENTIMENT] 功能已禁用，跳过世界温度计算`
- **影响**: 世界温度数据为 `None`，`world_temp=False` 在提示词中

### 3. openrouter_assistant (📰)
- **状态**: 条件禁用
- **原因**: `OPENROUTER_ASSISTANT_ENABLED=False`（环境变量未设置或为 false）
- **日志**: `ℹ️ [OPENROUTER] 功能未启用，跳过新闻摘要`
- **影响**: 新闻摘要数据为 `None`，`news_summary=False` 在提示词中

---

## ⚠️ 异常与空数据返回

### 空数据返回

1. **world_temp = None**
   - 原因: `WORLD_SENTIMENT_ENABLED=False`
   - 位置: `event_analyzer.py:289` → `compute_world_temperature()` 被跳过
   - 影响: 提示词中 `world_temp=False`，不影响预测流程

2. **news_summary = None**
   - 原因: `OPENROUTER_ASSISTANT_ENABLED=False`
   - 位置: `main.py:390-399` → `get_news_summary()` 被跳过
   - 影响: 提示词中 `news_summary=False`，不影响预测流程

3. **news_cache = 未调用**
   - 原因: `NEWS_CACHE_ENABLED=False`
   - 位置: `main.py:268-280` → `fetch_and_cache_news()` 被跳过
   - 影响: 无新闻缓存预加载，不影响预测流程

### 轻微异常

1. **Gemini-2.5-Pro JSON 解析错误** ⚠️
   - 出现次数: 3 次（每个选项1次）
   - 原因: 返回的 JSON 格式不完整（被截断）
   - 处理: 使用文本提取备用方案，成功提取概率值
   - 影响: 无，预测值正常获取

2. **OpenRouter Mistral-7B 空内容** ⚠️
   - 出现次数: 1 次（November 30, 2025 选项）
   - 原因: 模型返回空内容
   - 处理: 跳过该模型响应
   - 影响: 该选项只有 4/5 个模型响应，仍可正常融合

3. **Gemini-2.5-Pro 超时重试** ⚠️
   - 出现次数: 1 次（March 31, 2026 选项）
   - 原因: 首次调用超时（45秒）
   - 处理: 自动重试，第二次成功
   - 影响: 延迟增加，但最终成功

---

## 📈 调用统计

### 核心模块调用次数

- **EventManager**: 2 次（解析 + 获取数据）
- **EventAnalyzer**: 2 次（全面分析 + 模型分配）
- **PromptBuilder**: 12 次（3个选项 × 4个模型）
- **ModelOrchestrator**: 3 次（每个选项1次，每次调用4个主模型）
- **FusionEngine**: 4 次（3次融合 + 1次归一化）
- **OutputFormatter**: 1 次（格式化多选项输出）
- **NotionLogger**: 1 次（记录到 Notion）

### 辅助模块调用次数

- **OpenRouter Layer**: 3 次（每个选项调用1次 Mistral-7B）
  - 成功: 2 次
  - 失败: 1 次（空内容）

### 模型调用详情

- **GPT-4o**: 3 次调用，全部成功
- **Claude-3.7-Sonnet**: 3 次调用，全部成功
- **Gemini-2.5-Pro**: 3 次调用，全部成功（但有 JSON 解析警告）
- **DeepSeek Chat**: 3 次调用，全部成功
- **OpenRouter Mistral-7B**: 3 次调用，2 次成功，1 次失败

---

## 🔍 关键发现

### ✅ 正常工作的模块

1. **核心链路完全正常**
   - EventManager → EventAnalyzer → PromptBuilder → ModelOrchestrator → FusionEngine → OutputFormatter → NotionLogger
   - 所有核心模块都成功执行

2. **多选项事件处理正常**
   - 成功识别 3 个选项
   - 为每个选项独立调用模型
   - 成功融合和归一化

3. **模型调用成功率高**
   - 主模型（GPT-4o, Claude, Gemini, DeepSeek）: 100% 成功率
   - 辅助模型（OpenRouter Mistral）: 66.7% 成功率

### ⚠️ 需要注意的点

1. **辅助模块全部禁用**
   - `news_cache`, `world_sentiment_engine`, `openrouter_assistant` 都被条件禁用
   - 这是预期的瘦身模式，不影响核心功能

2. **Gemini JSON 解析问题**
   - 需要改进 JSON 解析逻辑，或要求 Gemini 返回完整 JSON

3. **OpenRouter 稳定性**
   - 部分调用返回空内容，需要添加重试机制

---

## 📝 结论

**本次预测流程状态**: ✅ **成功完成**

- ✅ 核心模块链路完全正常，所有模块都按预期工作
- ✅ 多选项事件处理正确，成功为 3 个选项生成预测
- ⚠️ 辅助模块（新闻缓存、世界温度、新闻摘要）被条件禁用，这是预期的瘦身模式
- ⚠️ 部分模型响应有轻微异常（JSON 解析、空内容），但都有备用处理方案
- ✅ 最终输出成功生成并写入 Notion

**建议**:
- 如需启用辅助功能，设置环境变量 `NEWS_CACHE_ENABLED=true`, `WORLD_SENTIMENT_ENABLED=true`, `OPENROUTER_ASSISTANT_ENABLED=true`
- 改进 Gemini JSON 解析逻辑，处理不完整的 JSON 响应
- 为 OpenRouter 调用添加重试机制

---

**报告生成时间**: 2025-11-04 20:19:36
