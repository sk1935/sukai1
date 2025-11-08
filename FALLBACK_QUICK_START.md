# 🚀 Fallback Chain 快速开始指南

## 5分钟快速配置

### 第1步：配置API Keys

在 `.env` 文件中添加（至少配置一个）：

```bash
# 主要模型（推荐）
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_ASSISTANT_ENABLED=true

# 备用模型1（可选，提高可用性）
COHERE_API_KEY=MO9CFdogNwvxcIXg3Sf0tJHauuk2ciLw9zTJvCXT

# 备用模型2（可选，提高可用性）
TEXTRAZOR_API_KEY=5a7f846688c4b176cf437da6687f036ed75e96494929aef91d50d53b
```

### 第2步：验证配置

运行测试脚本（可选）：

```bash
python3 test_fallback_chain.py
```

### 第3步：使用

无需额外代码修改！系统已自动集成 Fallback Chain。

---

## 💡 工作原理

当调用新闻摘要生成时：

1. **首先尝试 OpenRouter**（3-15秒）
   - 使用 mistralai/mistral-7b-instruct
   - 失败则自动继续

2. **然后尝试 Cohere**（+20秒）
   - 使用 command-xlarge-nightly
   - 失败则自动继续

3. **最后尝试 TextRazor**（+20秒）
   - 提取关键实体和主题
   - 失败则返回默认响应

4. **所有失败时**
   - 返回：`"[⚠️] 所有模型调用失败"`
   - 系统继续运行，不会崩溃

---

## 📊 日志示例

### 成功场景（OpenRouter工作）
```
[Fallback] 尝试 OpenRouter...
[Fallback] ✅ OpenRouter 成功
✅ 成功生成摘要（来源: openrouter，312 字符）
```

### Fallback场景（OpenRouter失败，Cohere成功）
```
[Fallback] 尝试 OpenRouter...
[Fallback] ❌ OpenRouter 失败: HTTPError: 429 Too Many Requests
[Fallback] 尝试 Cohere...
[Fallback] ✅ Cohere 成功
✅ 成功生成摘要（来源: cohere，245 字符）
```

### 全部失败场景
```
[Fallback] 尝试 OpenRouter...
[Fallback] ❌ OpenRouter 失败: ValueError: OPENROUTER_API_KEY not configured
[Fallback] 尝试 Cohere...
[Fallback] ❌ Cohere 失败: ValueError: COHERE_API_KEY not configured
[Fallback] 尝试 TextRazor...
[Fallback] ❌ TextRazor 失败: ValueError: TEXTRAZOR_API_KEY not configured
[Fallback] ❌ 所有模型调用失败，返回默认响应
❌ 所有模型调用失败，无法生成摘要
```

---

## ⚙️ 配置选项

### 最小配置（仅OpenRouter）
```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_ASSISTANT_ENABLED=true
```
- 优点：简单，免费
- 缺点：无备用方案

### 推荐配置（OpenRouter + Cohere）
```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxx
COHERE_API_KEY=your_cohere_key
OPENROUTER_ASSISTANT_ENABLED=true
```
- 优点：高可用性，成本合理
- 缺点：需要两个账号

### 最高可用性配置（所有三个）
```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxx
COHERE_API_KEY=your_cohere_key
TEXTRAZOR_API_KEY=your_textrazor_key
OPENROUTER_ASSISTANT_ENABLED=true
```
- 优点：最高可用性
- 缺点：需要管理三个API账号

---

## 🧪 测试方法

### 手动测试

```bash
# 1. 配置API keys（在.env文件中）

# 2. 运行测试脚本
python3 test_fallback_chain.py

# 3. 查看输出，确认fallback机制工作正常
```

### 在实际系统中测试

```bash
# 启动bot
python3 src/main.py

# 发送预测请求，观察日志
# 日志会显示使用了哪个模型来源
```

---

## ❓ 常见问题

### Q: 如果我只配置了 Cohere，会怎样？
A: OpenRouter会自动失败，然后直接使用Cohere，不影响功能。

### Q: Fallback 会增加延迟吗？
A: 只有在前面的模型失败时才会fallback，每个模型有20秒超时。最坏情况下总延迟约60秒。

### Q: 如何禁用 Fallback 功能？
A: 设置 `OPENROUTER_ASSISTANT_ENABLED=false`

### Q: TextRazor 返回的不是完整摘要？
A: 是的，TextRazor 主要用于实体提取。它返回的是关键主题列表，而不是自然语言摘要。

---

## 🎉 完成

✅ Fallback Chain 已成功实施！

**下一步：**
1. 配置至少一个 API key
2. 启动系统并测试
3. 观察日志，确认工作正常

**文档参考：**
- `FALLBACK_CHAIN_SETUP.md` - 详细配置说明
- `FALLBACK_IMPLEMENTATION_SUMMARY.md` - 完整实施报告
- `test_fallback_chain.py` - 测试脚本

---

## ⚠️ 重要提醒

本次修改 **只解决了API可用性问题**，不解决数据时效性问题。

如需解决"模型使用过时数据"的问题（如Apple市值过时），需要另外实施实时数据获取机制。

详见之前的 Bug 分析报告。




