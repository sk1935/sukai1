# 辅助模块诊断报告

## 模块导入状态

- ✅ news_cache: 可导入
- ✅ world_sentiment_engine: 可导入
- ✅ openrouter_assistant: 可导入

## 环境变量
- NEWS_CACHE_ENABLED = 未定义
- WORLD_SENTIMENT_ENABLED = 未定义
- OPENROUTER_ASSISTANT_ENABLED = 未定义

## 功能自检结果
| 模块 | 状态 | 说明 | 错误 |
| --- | --- | --- | --- |
| news_cache | 跳过 | NEWS_CACHE_ENABLED=False |  |
| world_sentiment_engine | 跳过 | WORLD_SENTIMENT_ENABLED=False |  |
| openrouter_assistant | 跳过 | OPENROUTER_ASSISTANT_ENABLED=False |  |

## 总结
⚪ news_cache: 已跳过 (disabled)
⚪ world_sentiment_engine: 已跳过 (disabled)
⚪ openrouter_assistant: 已跳过 (disabled)

✅ 所有辅助功能正常