# Bug 分析报告：条件事件的归一化逻辑问题

## 问题描述

当输入条件事件（如 "Fed decision in December?" 或 "Will Israel strike Lebanon on..."）时：
- ❌ **实际输出**：显示 `📊 归一化检查：ΣAI预测 = XX%`
- ✅ **期望输出**：只显示 `ℹ️ 条件事件为独立市场（概率未归一化）`，不显示归一化检查

---

## 代码流程分析

### 1️⃣ `fusion_engine.py` - `normalize_all_predictions()`

**位置**：第 730-796 行

**当前逻辑**：
```python
# 第 767 行：识别事件类型
event_type = FusionEngine.classify_multi_option_event(event_title or "", filtered_outcomes)

# 第 771 行：判断是否归一化
should_normalize = (event_type == "mutually_exclusive")

# 第 773-796 行：条件事件处理
if not should_normalize:
    # ... 标记 normalized = False
    total_before = sum(...)  # 计算总和
    return {
        "normalized_outcomes": marked_outcomes,
        "total_before": round(total_before, 2),
        "total_after": round(total_before, 2),  # ⚠️ 仍然返回了 total_after
        "normalized": False,
        "event_type": event_type  # ✅ 正确返回了事件类型
    }
```

**问题**：
- ✅ 正确识别了事件类型（`event_type = "conditional"`）
- ✅ 正确设置了 `normalized = False`
- ❌ **但仍然返回了 `total_after` 值**（计算了总和）
- ❌ **没有日志输出** "[FusionEngine] 条件事件检测到，跳过归一化。"

---

### 2️⃣ `output_formatter.py` - `format_conditional_prediction()`

**位置**：第 163-188 行

**当前逻辑**：
```python
if normalization_info:
    total_after = normalization_info.get("total_after", 0)
    event_type = normalization_info.get("event_type", "unknown")
    
    # ⚠️ 无条件输出归一化检查
    output += f"📊 *归一化检查：* ΣAI预测 = {total_after:.2f}%\n"
    
    # ✅ 然后才检查是否归一化
    if not is_normalized:
        output += f"⚠️ *条件事件为独立市场，概率未归一化。*\n"
```

**问题**：
- ❌ **没有先检查 `event_type == "conditional"`**
- ❌ **无条件输出了 `📊 归一化检查：ΣAI预测 = XX%`**
- ✅ 虽然之后输出了警告，但用户在警告之前已经看到了归一化检查

---

### 3️⃣ `output_formatter.py` - `format_multi_option_prediction()`

**位置**：第 659-662 行

**当前逻辑**：
```python
if normalization_info:
    total_after = normalization_info.get("total_after", 0)
    output += f"📊 *归一化检查：* ΣAI预测 = {total_after:.2f}%\n\n"
```

**问题**：
- ❌ **同样的问题**：没有检查事件类型，无条件输出归一化检查

---

## 根本原因

1. **`fusion_engine.py`**：
   - 条件事件时，虽然设置了 `normalized=False`，但仍然返回了 `total_after` 值
   - 这导致 `output_formatter.py` 收到了 `total_after`，认为应该显示归一化检查

2. **`output_formatter.py`**：
   - 没有先检查 `event_type == "conditional"` 来跳过归一化检查的输出
   - 无条件输出了 `📊 归一化检查：ΣAI预测 = XX%`

---

## 修复方案

### 方案1：在 `fusion_engine.py` 中
- 条件事件时，`total_after = None`（或明确标记为不显示）
- 添加日志：`[FusionEngine] 条件事件检测到，跳过归一化。`

### 方案2：在 `output_formatter.py` 中
- 先检查 `event_type == "conditional"`
- 如果是条件事件，跳过归一化检查的输出，直接显示提示信息

### 推荐：结合方案1和方案2
1. **`fusion_engine.py`**：
   - 条件事件时，`total_after = None`（或特殊标记值）
   - 添加日志输出

2. **`output_formatter.py`**：
   - 先检查 `event_type == "conditional"`
   - 条件事件：显示 `ℹ️ 条件事件为独立市场（概率未归一化）`
   - 互斥事件：显示 `📊 归一化检查：ΣAI预测 = XX%`

---

## 影响范围

- ✅ `format_conditional_prediction()`：需要修改（第 163-188 行）
- ✅ `format_multi_option_prediction()`：需要修改（第 659-662 行）
- ✅ `normalize_all_predictions()`：需要添加日志和调整返回值（第 773-796 行）

---

## 验证标准

修复后，当输入条件事件时：
- ✅ 输出应包含：`ℹ️ 条件事件为独立市场（概率未归一化）`
- ❌ 输出应**不包含**：`📊 归一化检查：ΣAI预测 = XX%`
- ✅ 控制台日志应包含：`[FusionEngine] 条件事件检测到，跳过归一化。`

---

