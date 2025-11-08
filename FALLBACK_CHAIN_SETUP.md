# 多层备用模型 Fallback Chain 配置说明

## 概述

系统已升级为支持多层备用模型调用机制，当主要API失败时自动切换到备用服务。

**Fallback Chain 顺序：**
```
OpenRouter → Cohere → TextRazor → 默认响应
```

---

## API Keys 配置

### 1. 在环境变量或 `.env` 文件中添加：

```bash
# OpenRouter (Primary - 主要模型)
OPENROUTER_API_KEY=sk-or-v1-xxxxxx
OPENROUTER_ASSISTANT_ENABLED=true

# Cohere (Fallback 1 - 备用模型1)
COHERE_API_KEY=MO9CFdogNwvxcIXg3Sf0tJHauuk2ciLw9zTJvCXT

# TextRazor (Fallback 2 - 备用模型2)
TEXTRAZOR_API_KEY=5a7f846688c4b176cf437da6687f036ed75e96494929aef91d50d53b
```

### 2. API Keys 获取方式

#### OpenRouter
- 网站：https://openrouter.ai/
- 注册后在 Settings → API Keys 中获取
- 免费额度：有限制，但支持多种免费模型

#### Cohere
- 网站：https://cohere.com/
- 注册后在 Dashboard → API Keys 中获取
- 免费额度：每月有一定调用次数

#### TextRazor
- 网站：https://www.textrazor.com/
- 注册后在 Account 页面获取 API Key
- 免费额度：每天500次请求

---

## 工作机制

### 调用流程

1. **尝试 OpenRouter**
   - 使用 `mistralai/mistral-7b-instruct` 模型
   - 超时：20秒
   - 如果成功：返回生成的摘要
   - 如果失败：记录警告，继续下一步

2. **尝试 Cohere**
   - 使用 `command-xlarge-nightly` 模型
   - 超时：20秒
   - 如果成功：返回生成的文本
   - 如果失败：记录警告，继续下一步

3. **尝试 TextRazor**
   - 提取文本中的实体和主题
   - 超时：20秒
   - 如果成功：返回关键主题摘要
   - 如果失败：记录错误，继续下一步

4. **返回默认响应**
   - 当所有模型都失败时
   - 返回：`"[⚠️] 所有模型调用失败。无法生成新闻摘要。"`

### 日志输出

系统会记录详细的日志：
```
[Fallback] 尝试 OpenRouter...
[Fallback] ❌ OpenRouter 失败: HTTPError: 429 Too Many Requests
[Fallback] 尝试 Cohere...
[Fallback] ✅ Cohere 成功
✅ 成功生成摘要（来源: cohere，245 字符）
```

---

## 测试验证

### 运行测试脚本

```bash
python test_fallback_chain.py
```

### 测试场景

#### 场景1：所有API keys都未配置
- 预期：所有模型失败，返回默认响应
- 结果：`{"text": "[⚠️] 所有模型调用失败...", "source": "fallback_default"}`

#### 场景2：只配置 Cohere API key
- 预期：OpenRouter失败 → Cohere成功
- 结果：`{"text": "生成的摘要...", "source": "cohere"}`

#### 场景3：只配置 TextRazor API key
- 预期：OpenRouter失败 → Cohere失败 → TextRazor成功
- 结果：`{"text": "🧩 关键主题: Apple, Microsoft, ...", "source": "textrazor"}`

---

## 代码集成说明

### 使用 Fallback Chain

```python
from src.openrouter_assistant import run_with_fallback

# 构建提示词
prompt = "请总结以下内容..."

# 调用 Fallback Chain
result = await run_with_fallback(prompt)

# 获取结果
summary_text = result.get("text")
data_source = result.get("source")

print(f"摘要（来源: {data_source}）：{summary_text}")
```

### 在现有代码中的应用

位置：`src/openrouter_assistant.py` 中的 `generate_news_summary()` 函数

已自动集成 Fallback Chain：
```python
# 使用 Fallback Chain 调用模型
result = await run_with_fallback(prompt)
summary = result.get("text", "")
source = result.get("source", "unknown")

if not summary or summary.startswith("[⚠️]"):
    # 如果是默认fallback响应，返回None
    return None
```

---

## 优势

1. **高可用性**
   - 任何单一API故障不会导致系统完全失败
   - 自动切换到备用服务

2. **成本优化**
   - 优先使用免费/便宜的服务
   - 只在必要时使用付费服务

3. **异步安全**
   - 所有调用都是异步的
   - 设置合理的超时，不阻塞主线程

4. **详细日志**
   - 记录每个模型的调用结果
   - 便于监控和调试

---

## 注意事项

1. **API限制**
   - 所有API都有调用频率限制
   - 建议合理设置缓存时间（当前：6小时）

2. **超时设置**
   - 所有API调用超时：20秒
   - 总超时时间最多：60秒（3个API各20秒）

3. **错误处理**
   - 所有异常都被捕获，不会崩溃
   - 失败时自动fallback，确保系统稳定

4. **数据质量**
   - TextRazor 只返回实体和主题，不是完整摘要
   - 建议优先配置 OpenRouter 或 Cohere

---

## 扩展性

### 添加更多备用模型

如需添加更多备用模型（如 HuggingFace、AI21），在 `run_with_fallback()` 中添加新的 try-except 块：

```python
# 4. 尝试 HuggingFace
try:
    logger.info("[Fallback] 尝试 HuggingFace...")
    result = await call_huggingface_api(prompt)
    logger.info("[Fallback] ✅ HuggingFace 成功")
    return result
except Exception as e4:
    logger.warning(f"[Fallback] ❌ HuggingFace 失败: {e4}")
```

### 可扩展的模型注册机制

未来可以改为配置驱动：

```python
# config.py
FALLBACK_MODELS = [
    {"name": "openrouter", "priority": 1, "handler": call_openrouter_api},
    {"name": "cohere", "priority": 2, "handler": call_cohere_api},
    {"name": "textrazor", "priority": 3, "handler": call_textrazor_api},
]
```

---

## 常见问题

### Q1: 为什么所有模型都失败？
A: 检查：
- API keys 是否正确配置
- 网络连接是否正常
- API服务是否可用（查看状态页）

### Q2: Cohere 返回空响应怎么办？
A: 系统会自动fallback到TextRazor，不需要手动干预

### Q3: 如何禁用某个备用模型？
A: 不配置对应的API key即可，系统会自动跳过

### Q4: 日志在哪里查看？
A: 标准输出，或配置日志文件：
```python
import logging
logging.basicConfig(filename='fallback.log', level=logging.INFO)
```

---

## 总结

✅ 已实现的功能：
- 多层备用模型调用（OpenRouter → Cohere → TextRazor）
- 自动错误处理和切换
- 详细的日志记录
- 异步安全执行

⚠️ 需要注意：
- 配置API keys
- 监控调用频率
- 关注日志输出

📝 下一步：
- 测试各个API的实际表现
- 根据成本和质量调整优先级
- 考虑添加更多备用模型




