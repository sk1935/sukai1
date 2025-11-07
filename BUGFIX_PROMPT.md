# Bug修复提示词：修复 format_multi_option_prediction 中的 NameError

## 🎯 修复目标
修复 `src/output_formatter.py` 中 `format_multi_option_prediction` 函数的 `NameError: name 'finalized_summary_text' is not defined` 错误。

## 📍 问题定位

### 错误位置
- **文件**: `src/output_formatter.py`
- **函数**: `format_multi_option_prediction` (第1023行开始)
- **错误行**: 第1310行
- **错误代码**:
  ```python
  if finalized_deepseek and finalized_summary_text:  # finalized_summary_text 未定义
  ```

### 问题原因
`finalized_summary_text` 变量在 `format_conditional_prediction` 函数中已定义（第554行），但在 `format_multi_option_prediction` 函数中未定义，却在第1310行被使用。

## 🔧 修改范围

### 必须修改的位置
**仅限修改**: `src/output_formatter.py` 文件中的 `format_multi_option_prediction` 函数

### 修改边界
- ✅ **可以修改**: `format_multi_option_prediction` 函数内部（第1023-1409行）
- ❌ **禁止修改**: 
  - `format_conditional_prediction` 函数
  - 其他任何函数或类
  - 文件的其他部分

## 📋 现有代码结构

### 函数签名
```python
def format_multi_option_prediction(
    self,
    event_data: Dict,
    outcomes: List[Dict],
    normalization_info: Dict = None,
    fusion_result: Optional[Dict] = None,
    trade_signal: Optional[Dict] = None
) -> str:
```

### 相关代码上下文

#### 1. 在 `format_conditional_prediction` 中的正确实现（参考）
```python
# 第552-566行：format_conditional_prediction 函数中
# AI逻辑摘要（使用第一个有效摘要）
first_summary = None
finalized_summary_text = ""  # ✅ 这里初始化了
for outcome in sorted_outcomes:
    summary = outcome.get('summary', '')
    if summary and len(summary) > 30 and '暂无' not in summary:
        first_summary = summary
        break

if first_summary:
    finalized_summary = self._finalize_reasoning_text(first_summary, limit=400)
    if finalized_summary:
        finalized_summary_text = finalized_summary
        summary_escaped = self.safe_markdown_text(finalized_summary)
        output += f"🧠 *AI逻辑摘要*\n\n{summary_escaped}\n\n"
```

#### 2. 问题代码位置（需要修复）
```python
# 第1298-1322行：format_multi_option_prediction 函数中
# DeepSeek insight block (multi-option)
deepseek_section = ""
deepseek_reasoning = None
if fusion_result and fusion_result.get('deepseek_reasoning'):
    deepseek_reasoning = fusion_result.get('deepseek_reasoning')
elif outcomes:
    for outcome in outcomes:
        if outcome.get('deepseek_reasoning'):
            deepseek_reasoning = outcome['deepseek_reasoning']
            break
if deepseek_reasoning:
    finalized_deepseek = self._finalize_reasoning_text(deepseek_reasoning, limit=500)
    if finalized_deepseek and finalized_summary_text:  # ❌ 错误：变量未定义
        similarity = self._reasoning_similarity(finalized_summary_text, finalized_deepseek)
        if similarity >= 0.9:
            print("[FORMAT] Skipped redundant model insight (multi-option)")
            finalized_deepseek = ""
    if finalized_deepseek:
        deepseek_text = self.safe_markdown_text(finalized_deepseek)
        deepseek_section = (
            "\n🧠 *模型洞察 \\(DeepSeek\\)*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{deepseek_text}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
```

### 函数执行流程
1. 处理空 outcomes（第1043-1056行）
2. 分类事件类型（第1058-1070行）
3. 如果是条件型，调用 `format_conditional_prediction`（第1063-1070行）
4. 候选人型事件处理（第1072行开始）
5. 排序 outcomes（第1076-1080行）
6. 构建输出（第1096-1409行）
7. **问题位置**：第1298-1322行（DeepSeek insight block）

## ✅ 修复要求

### 1. 变量初始化
在 `format_multi_option_prediction` 函数中，**在 DeepSeek insight block 之前**（建议在第1298行之前），添加 `finalized_summary_text` 的初始化逻辑：

**参考实现**（基于 `format_conditional_prediction` 的逻辑）：
- 初始化 `finalized_summary_text = ""`
- 从 `sorted_outcomes` 中提取第一个有效摘要
- 使用 `self._finalize_reasoning_text()` 处理摘要
- 将结果赋值给 `finalized_summary_text`

### 2. 代码位置
- **初始化位置**: 在第1298行（`# DeepSeek insight block (multi-option)`）之前
- **使用位置**: 第1310行（保持不变，但确保变量已定义）

### 3. 逻辑一致性
确保与 `format_conditional_prediction` 函数中的逻辑保持一致：
- 使用相同的摘要提取逻辑
- 使用相同的 `_finalize_reasoning_text()` 方法
- 使用相同的 limit 参数（400）

### 4. 模块化要求
- **只修改**: `format_multi_option_prediction` 函数内部
- **不修改**: 其他函数、类方法、导入语句
- **保持**: 函数签名、返回值类型不变
- **保持**: 现有的代码风格和注释

## 🧪 测试和验证步骤

### 1. 代码检查
- [ ] 确认 `finalized_summary_text` 在第1310行之前已定义
- [ ] 确认变量初始化逻辑与 `format_conditional_prediction` 一致
- [ ] 确认没有修改其他函数或类

### 2. 功能测试
测试场景：
- [ ] **多选项事件**：发送包含多个选项的预测请求
- [ ] **有 DeepSeek reasoning**：确保 deepseek_section 正常生成
- [ ] **无 DeepSeek reasoning**：确保不会报错
- [ ] **有 summary**：确保 finalized_summary_text 正确提取
- [ ] **无 summary**：确保 finalized_summary_text 为空字符串，不报错

### 3. 错误验证
- [ ] 运行机器人，发送 `/predict` 命令
- [ ] 确认不再出现 `NameError: name 'finalized_summary_text' is not defined`
- [ ] 检查日志文件 `bot_debug.log`，确认无相关错误

### 4. 回归测试
- [ ] 确认 `format_conditional_prediction` 函数仍然正常工作
- [ ] 确认其他格式化函数不受影响
- [ ] 确认输出格式保持一致

## 📝 修复后的预期行为

### 正常流程
1. 函数开始执行 `format_multi_option_prediction`
2. 在处理 DeepSeek insight 之前，初始化 `finalized_summary_text`
3. 第1310行检查 `finalized_deepseek and finalized_summary_text` 时，两个变量都已定义
4. 如果相似度 >= 0.9，跳过冗余的模型洞察
5. 否则，正常生成 `deepseek_section`

### 边界情况处理
- **outcomes 为空**: `finalized_summary_text` 应为空字符串
- **无有效摘要**: `finalized_summary_text` 应为空字符串
- **摘要太短**: 不提取，`finalized_summary_text` 应为空字符串

## ⚠️ 注意事项

1. **不要修改函数签名**：保持参数和返回值不变
2. **不要修改其他函数**：只修改 `format_multi_option_prediction`
3. **保持代码风格**：使用相同的缩进、注释风格
4. **保持逻辑一致性**：与 `format_conditional_prediction` 中的实现保持一致
5. **防御性编程**：确保所有边界情况都得到处理

## 🎯 成功标准

修复完成后，应该满足：
- ✅ 不再出现 `NameError: name 'finalized_summary_text' is not defined`
- ✅ 多选项预测功能正常工作
- ✅ DeepSeek insight 正常显示或正确跳过
- ✅ 代码逻辑与 `format_conditional_prediction` 保持一致
- ✅ 没有破坏现有功能

---

**提示词使用说明**：
将此提示词提供给 AI 助手，要求它按照上述要求修复 bug。强调：
1. 只修改指定函数
2. 参考现有代码结构
3. 保持模块化和一致性
4. 完成修复后进行测试验证

