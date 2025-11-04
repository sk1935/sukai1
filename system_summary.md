# 🧠 Polymarket AI Predictor - 系统结构总结

## 📁 文件结构概览

```
polymarket1/
├── src/                          # 核心源代码目录
│   ├── main.py                   # 主程序入口（Telegram Bot）
│   ├── event_manager.py           # 事件层：解析输入、获取市场数据
│   ├── prompt_builder.py         # 提示层：生成模型提示词
│   ├── model_orchestrator.py     # 推理层：并发调用多个AI模型
│   ├── fusion_engine.py          # 融合层：加权融合预测结果
│   ├── output_formatter.py       # 输出层：格式化中文报告
│   ├── event_analyzer.py         # 事件分析器：类别、舆情、趋势分析
│   ├── notion_logger.py          # Notion日志记录器：自动保存预测结果
│   ├── metrics.py                # 评估指标计算模块
│   ├── ablation.py                # 消融实验模块
│   └── test_experiments.py       # 实验测试模块
│
├── config/                       # 配置文件目录
│   ├── models.json               # 模型配置（权重、API源、fallback等）
│   ├── base_weights_lmarena.json # LMArena动态权重配置
│   ├── experiments.yaml          # 实验配置
│   └── update_lmarena_weights.py # LMArena权重自动更新模块
│
├── services/                     # 外部服务集成目录
│   └── llm_clients/
│       └── openrouter_layer.py   # OpenRouter免费模型调用层
│
├── requirements.txt              # Python依赖列表
├── .env                          # 环境变量配置（API密钥等）
└── README.md                     # 项目说明文档
```

## 📦 模块说明

### 核心模块（五层架构）

#### 1. **EventManager** (`src/event_manager.py`)
- **功能**：解析用户输入（Telegram消息或Polymarket URL），从Polymarket API获取市场数据（概率、规则、趋势）
- **输入**：用户消息（文本或URL）
- **输出**：事件数据字典 `{question, market_prob, rules, outcomes, is_multi_option, ...}`

#### 2. **PromptBuilder** (`src/prompt_builder.py`)
- **功能**：根据事件信息和模型特性生成专业化提示词
- **输入**：事件数据 + 模型名称 + 模型任务分配
- **输出**：格式化提示词字符串

#### 3. **ModelOrchestrator** (`src/model_orchestrator.py`)
- **功能**：并发调用多个AI模型API（通过AICanAPI统一接口），支持超时控制和错误处理
- **输入**：各模型的提示词
- **输出**：各模型的预测结果 `{probability, confidence, reasoning}`

#### 4. **FusionEngine** (`src/fusion_engine.py`)
- **功能**：加权融合多个模型的预测，结合市场概率，生成AI共识和摘要
- **输入**：模型预测结果 + 市场概率
- **输出**：融合后的预测 `{final_prob, model_only_prob, uncertainty, summary, disagreement}`

#### 5. **OutputFormatter** (`src/output_formatter.py`)
- **功能**：将预测结果格式化为中文Markdown报告，支持单选项和多选项事件
- **输入**：事件数据 + 融合结果
- **输出**：格式化的中文Markdown字符串（Telegram消息）

### 辅助模块

#### 6. **EventAnalyzer** (`src/event_analyzer.py`)
- **功能**：全面分析事件，包括类别识别、市场趋势、舆情信号（GDELT/NewsAPI/Mediastack）、规则摘要
- **功能**：模型任务分工分配，为不同模型分配专业维度
- **输入**：事件标题、规则
- **输出**：分析结果字典 `{category, market_trend, sentiment_trend, dimensions, model_assignments}`

#### 7. **NotionLogger** (`src/notion_logger.py`)
- **功能**：自动将预测结果写入Notion数据库，支持限流和重复检查
- **输入**：事件数据 + 融合结果
- **输出**：写入Notion数据库，返回成功/失败状态

#### 8. **OpenRouter Layer** (`services/llm_clients/openrouter_layer.py`)
- **功能**：通过OpenRouter API调用免费模型（白名单控制），作为辅助层参与融合
- **输入**：模型名称、提示词
- **输出**：标准预测结果字典

#### 9. **LMArena Weight Updater** (`config/update_lmarena_weights.py`)
- **功能**：从LMArena.ai自动获取模型排行榜，更新模型权重配置
- **输入**：LMArena API响应
- **输出**：更新 `base_weights_lmarena.json` 文件

## 🔧 核心函数

### EventManager

```python
parse_event_from_message(message_text: str) -> Dict[str, str]
# 解析Telegram消息，提取事件查询或Polymarket URL slug

async fetch_polymarket_data(event_info: Dict[str, str]) -> Optional[Dict]
# 从Polymarket API获取市场数据（支持GraphQL、REST API、网页抓取fallback）

_filter_active_child_markets(child_markets: List[Dict]) -> List[Dict]
# 过滤活跃子市场（排除已结束、已结算、重复项、无效价格）
```

### ModelOrchestrator

```python
async call_all_models(prompts: Dict[str, str]) -> Dict[str, Optional[Dict]]
# 并发调用所有模型，返回各模型的预测结果

async call_model(model_name: str, prompt: str) -> Optional[Dict]
# 调用单个模型API，解析JSON响应，返回 {probability, confidence, reasoning}

get_model_weight(model_name: str) -> float
# 从config/models.json获取模型权重
```

### FusionEngine

```python
fuse_predictions(model_results: Dict, model_weights: Dict, market_prob: float) -> Dict
# 加权融合多个模型预测，结合市场概率（80% AI + 20% 市场）

@staticmethod
normalize_all_predictions(outcomes: List[Dict], event_title: str = "") -> Dict
# 归一化多选项事件概率（仅互斥事件归一化到100%，条件事件保持原值）

@staticmethod
classify_multi_option_event(event_title: str, outcomes: List[Dict]) -> str
# 识别事件类型：mutually_exclusive（互斥） / conditional（条件） / hybrid（混合）

@staticmethod
filter_invalid_outcomes(outcomes: List[Dict]) -> List[Dict]
# 过滤无效/过期选项（已结束日期、无效价格、重复项）
```

### EventAnalyzer

```python
analyze_event(event_title: str, event_rules: str, available_models: List[str]) -> Dict
# 分析事件类别，分配模型任务维度，返回模型分工

async analyze_event_full(event_title: str, event_rules: str) -> Dict
# 全面分析事件：类别、市场趋势、舆情信号、规则摘要

_get_sentiment_signal(keyword: str) -> Dict
# 获取舆情信号（GDELT/NewsAPI/Mediastack，支持缓存和限流）
```

### OutputFormatter

```python
format_prediction(event_data: Dict, fusion_result: Dict) -> str
# 格式化单选项事件预测输出（Markdown）

format_multi_option_prediction(event_data: Dict, outcomes: List[Dict], normalization_info: Dict) -> str
# 格式化多选项事件预测输出，自动区分候选人型和条件型

format_conditional_prediction(event_data: Dict, outcomes: List[Dict], normalization_info: Dict) -> str
# 格式化条件型事件输出（时间、价格、地理分组等）
```

### NotionLogger

```python
log_prediction(event_data: Dict, fusion_result: Dict, outcomes: List[Dict] = None) -> bool
# 异步后台写入预测结果到Notion数据库
```

### OpenRouter Layer

```python
async call_openrouter_model(model_name: str, prompt: str) -> Optional[Dict]
# 调用OpenRouter API的单个模型（仅限白名单免费模型）

async call_multiple_openrouter_models(model_names: List[str], prompt: str) -> Dict[str, Optional[Dict]]
# 并发调用多个OpenRouter模型
```

## 🌐 外部依赖

### API服务

1. **Telegram Bot API**
   - 用途：接收用户命令，发送预测结果
   - 库：`python-telegram-bot`

2. **Polymarket API**
   - GraphQL API：`https://gamma-api.polymarket.com/query`
   - REST API：`https://gamma-api.polymarket.com/markets`
   - CLOB API：`https://clob.polymarket.com/markets`
   - 用途：获取市场数据、概率、规则、多选项市场

3. **AICanAPI**（统一模型接口）
   - 支持的模型：GPT-4o, Claude-3.7-Sonnet, Gemini-2.5-Pro, DeepSeek Chat, Grok-4
   - 用途：统一调用多个AI模型

4. **OpenRouter API**
   - 端点：`https://openrouter.ai/api/v1/chat/completions`
   - 用途：调用免费模型（Mistral-7B, Llama-3-70B, Yi-Large, Nous-Hermes, OpenChat）
   - 限制：仅白名单内的免费模型

5. **Notion API**
   - 用途：自动保存预测结果到Notion数据库
   - 库：`notion-client`

6. **LMArena.ai API**
   - 端点：`https://lmarena.ai/api/leaderboard`
   - 用途：动态获取模型排行榜，自动更新模型权重

7. **舆情API**（可选）
   - **GDELT**：全球事件数据
   - **NewsAPI**：新闻数据（需API密钥）
   - **Mediastack**：媒体数据（需API密钥）
   - 用途：获取事件相关的舆情信号

### Python依赖库

```
python-telegram-bot==20.7    # Telegram Bot框架
aiohttp==3.9.1               # 异步HTTP客户端
httpx>=0.28.0                # 现代异步HTTP客户端（OpenRouter使用）
tenacity>=8.2.0              # 重试机制库
numpy==1.26.2                # 数值计算
pandas==2.1.4                # 数据处理
python-dotenv==1.0.0         # 环境变量管理
notion-client>=2.2.1         # Notion API客户端
scipy>=1.9.0                 # 科学计算
pyyaml>=6.0                  # YAML配置解析
```

## 🔄 模块交互流程

### 单选项事件流程

```
用户输入 (/predict 事件)
    ↓
[EventManager] 解析消息 → 获取Polymarket数据
    ↓
[EventAnalyzer] 分析事件 → 类别识别、模型任务分配
    ↓
[PromptBuilder] 生成提示词 → 专业化提示（每个模型不同维度）
    ↓
[ModelOrchestrator] 并发调用模型
    ├─ GPT-4o (综合逻辑分析)
    ├─ Claude-3.7-Sonnet (风险评估)
    ├─ Gemini-2.5-Pro (模式识别)
    ├─ DeepSeek Chat (量化分析)
    └─ OpenRouter模型 (辅助层，可选)
    ↓
[FusionEngine] 融合预测
    ├─ 加权平均（模型权重 × 置信度权重）
    ├─ 结合市场概率（80% AI + 20% 市场）
    └─ 生成AI共识摘要
    ↓
[OutputFormatter] 格式化输出 → Markdown中文报告
    ↓
[NotionLogger] 异步写入Notion（后台执行）
    ↓
Telegram回复用户
```

### 多选项事件流程

```
用户输入 (/predict 多选项事件)
    ↓
[EventManager] 解析 → 获取多选项市场数据
    ↓
[EventAnalyzer] 分析 → 事件类别、模型分配
    ↓
对每个选项循环：
    [PromptBuilder] 生成选项提示词
        ↓
    [ModelOrchestrator] 并发调用模型（可选：共享模型结果）
        ↓
    [FusionEngine] 融合该选项的预测
        ↓
    [OpenRouter Layer] 辅助模型调用（可选）
        ↓
收集所有选项的融合结果
    ↓
[FusionEngine.normalize_all_predictions()]
    ├─ 识别事件类型（conditional / mutually_exclusive）
    ├─ 过滤无效/过期选项
    ├─ 互斥事件：归一化到100%
    └─ 条件事件：保持原值（不归一化）
    ↓
[OutputFormatter] 格式化多选项输出
    ├─ 自动识别候选人型 vs 条件型
    ├─ 使用不同模板
    └─ 显示归一化状态
    ↓
[NotionLogger] 为每个选项写入Notion记录
    ↓
Telegram回复用户
```

## 🚀 程序入口

### 主入口：`src/main.py`

```python
def main():
    """主程序入口点"""
    load_dotenv()
    
    # 检查并更新LMArena权重（启动时自动检查）
    if should_update():
        update_lmarena_weights()
    
    # 初始化Telegram Bot
    bot = ForecastingBot()
    
    # 创建Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # 注册命令处理器
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("predict", bot.handle_predict))
    
    # 启动Bot
    application.run_polling()

if __name__ == "__main__":
    main()
```

### 启动方式

1. **直接运行**：
   ```bash
   python src/main.py
   ```

2. **后台运行**：
   ```bash
   nohup python src/main.py > bot_output.log 2>&1 &
   ```

3. **使用启动脚本**：
   ```bash
   ./start_bot.sh
   ```

### 主流程：`ForecastingBot.handle_predict()`

1. 接收Telegram `/predict` 命令
2. 解析事件信息（`EventManager.parse_event_from_message()`）
3. 获取Polymarket市场数据（`EventManager.fetch_polymarket_data()`）
4. 全面分析事件（`EventAnalyzer.analyze_event_full()` + `EventAnalyzer.analyze_event()`）
5. 生成模型提示词（`PromptBuilder.build_prompt()`）
6. 并发调用AI模型（`ModelOrchestrator.call_all_models()`）
7. 融合预测结果（`FusionEngine.fuse_predictions()`）
8. 多选项事件：归一化处理（`FusionEngine.normalize_all_predictions()`）
9. 格式化输出（`OutputFormatter.format_prediction()` 或 `format_multi_option_prediction()`）
10. 异步写入Notion（`NotionLogger.log_prediction()`）
11. 发送Telegram回复

## 📊 数据流

### 数据流图

```
Telegram消息
    ↓
EventManager → event_data: {question, market_prob, rules, outcomes, ...}
    ↓
EventAnalyzer → analysis: {category, dimensions, model_assignments, sentiment, ...}
    ↓
PromptBuilder → prompts: {model_name: prompt_string}
    ↓
ModelOrchestrator → model_results: {model_name: {probability, confidence, reasoning}}
    ↓
FusionEngine → fusion_result: {final_prob, model_only_prob, uncertainty, summary, ...}
    ↓
[多选项] normalize_all_predictions → normalized_outcomes: [{name, model_only_prob, prediction, ...}]
    ↓
OutputFormatter → markdown_string
    ↓
Telegram回复 + Notion数据库（异步）
```

## 🔑 配置说明

### 环境变量（`.env`）

```
# Telegram
TELEGRAM_BOT_TOKEN=your_token

# AI模型API
AICANAPI_KEY=your_key          # 统一模型接口（GPT-4o, Claude, Gemini, DeepSeek等）
OPENROUTER_API_KEY=your_key    # OpenRouter免费模型

# 外部服务（可选）
NOTION_TOKEN=your_token        # Notion集成令牌
NOTION_DB_ID=your_database_id  # Notion数据库ID

POLYMARKET_API_KEY=your_key    # Polymarket API密钥（可选）

# 舆情API（可选）
NEWSAPI_KEY=your_key
MEDIASTACK_API_KEY=your_key
```

### 配置文件

- **`config/models.json`**：模型配置（权重、API源、fallback、启用状态）
- **`config/base_weights_lmarena.json`**：LMArena动态权重（自动更新）
- **`config/experiments.yaml`**：实验配置（消融实验）

## 🎯 关键特性

### 1. 五层架构
- **事件层**：数据获取和解析
- **提示层**：专业化提示词生成
- **推理层**：多模型并发调用
- **融合层**：智能加权融合
- **输出层**：中文报告格式化

### 2. 多模型融合
- **主模型**：GPT-4o, Claude-3.7-Sonnet, Gemini-2.5-Pro, DeepSeek Chat
- **辅助模型**：OpenRouter免费模型（Mistral-7B, Llama-3-70B等）
- **权重来源**：LMArena.ai动态权重 + 配置权重
- **融合策略**：加权平均 + 置信度调整 + 市场概率融合

### 3. 事件类型识别
- **互斥事件**（Mutually Exclusive）：归一化到100%（如选举、候选人）
- **条件事件**（Conditional）：不归一化（如时间、价格、地理分组）
- **混合事件**（Hybrid）：默认不归一化（保守策略）

### 4. 性能优化
- **并发调用**：`asyncio.gather` 实现多模型并发
- **超时控制**：每个模型独立超时（12-15秒），不阻塞其他模型
- **并发限制**：`asyncio.Semaphore` 限制最大并发数为5
- **缓存机制**：舆情API响应缓存（3小时有效）
- **异步写入**：Notion写入使用 `asyncio.create_task()` 后台执行

### 5. 错误处理
- **API超时**：自动跳过，不阻塞其他模型
- **API失败**：自动降级到fallback模型
- **数据缺失**：使用mock数据继续预测
- **网络错误**：自动重试（tenacity库）

### 6. 自动记录
- **Notion集成**：自动保存所有预测结果
- **限流保护**：每次写入间隔≥5秒
- **重复检查**：避免重复写入相同事件

---

**最后更新**：2025-01-27  
**版本**：v2.0（支持条件事件识别、LMArena动态权重、OpenRouter集成）
