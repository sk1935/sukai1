# 🔧 Bug修复提示词：低概率事件过滤错误

## 🧩 **目标**：

1. **修复目标**：修复 `filter_low_probability_event()` 函数中 CLOB API 概率验证缺失的问题，确保系统能够正确过滤低概率事件，避免将 0.00% 误判为有效概率。

2. **改进数据提取和回退逻辑**：确保概率数据从不同的源（如 `event_data.market_prob`、`outcomes`、`CLOB API`）正确提取，并且当某个数据源失败或返回无效值时，能够正确回退到备用源。

3. **增强日志记录**：在每个数据提取步骤中，记录详细的日志信息（包括数据源、提取的值、验证结果），以便定位和调试问题。

---

## ⚙️ **修改范围**：

1. **文件**：
   - `src/event_manager.py`

2. **修改内容**：
   - 增强 `filter_low_probability_event()` 方法中的 CLOB API 数据验证逻辑。
   - 确保 CLOB fallback 机制能够正确验证概率值（必须 > 0.0）。
   - 统一所有数据源的验证逻辑，使用 `_append_probability()` 函数进行一致性验证。
   - 增强日志输出，确保每个数据源的调用结果和验证状态都能被准确记录。

---

## 🔧 **修复步骤**：

### （1）检查并增强 `filter_low_probability_event()` 中的 CLOB 概率验证逻辑

- **目标**：确保从 CLOB API 获取的概率值经过严格验证（> 0.0 且 <= 100.0），与其他数据源（`event_data.market_prob`、`outcomes`）保持一致的处理逻辑。

- **问题位置**：`src/event_manager.py` 第 184-185 行

- **当前问题**：
  ```python
  # ❌ 当前代码（有BUG）
  if clob_prob is not None:
      probability_candidates.append(clob_prob)  # 没有验证 clob_prob > 0.0
  ```

- **解决方案**：使用统一的 `_append_probability()` 函数来验证 CLOB 概率，确保：
  1. 概率值 > 0.0（过滤掉 0.0 和负值）
  2. 概率值 <= 100.0（过滤掉超界值）
  3. 记录详细的验证日志

- **修复方向**：
  1. 将第 184-185 行的直接添加逻辑改为使用 `_append_probability()` 函数
  2. 确保与 `event_data.market_prob` 和 `outcomes` 的处理逻辑保持一致
  3. 添加更详细的日志记录，包括 CLOB API 调用结果和验证状态

**修复后的代码示例**：

```python
async def filter_low_probability_event(
    self,
    event_data: Optional[Dict[str, Any]],
    threshold: float = None
) -> Optional[Dict[str, float]]:
    """Return details when event probabilities fall below threshold, otherwise None."""
    if not event_data or event_data.get("is_mock"):
        return None

    try:
        threshold_value = float(threshold) if threshold is not None else float(
            os.getenv("LOW_PROBABILITY_THRESHOLD", "1.0")
        )
    except (TypeError, ValueError):
        threshold_value = 1.0

    try:
        probability_candidates: List[float] = []

        def _append_probability(value: Any, source: str) -> None:
            """统一的概率验证函数，确保所有数据源使用相同的验证逻辑"""
            if value is None:
                return
            try:
                prob_value = float(value)
            except (TypeError, ValueError):
                logger.debug(f"[LowProbFilter] {source} 不是有效数字: %s", value)
                return
            if prob_value <= 0.0:
                logger.debug(f"[LowProbFilter] 忽略 {source} 的 0 或负值: %.2f", prob_value)
                return
            if prob_value > 100.0:
                logger.debug(f"[LowProbFilter] 忽略 {source} 超界值: %.2f", prob_value)
                return
            probability_candidates.append(prob_value)
            logger.debug(f"[LowProbFilter] 使用 {source} = {prob_value:.2f}%")

        # 步骤1：优先使用 event_data 中的 market_prob
        _append_probability(event_data.get("market_prob"), "event_data.market_prob")

        # 步骤2：备用：从 outcomes 中提取
        if not probability_candidates:
            outcomes = event_data.get("outcomes")
            if isinstance(outcomes, list) and outcomes:
                logger.debug(f"[LowProbFilter] market_prob 不可用，检查 {len(outcomes)} 个 outcomes")
                for idx, outcome in enumerate(outcomes):
                    if not isinstance(outcome, dict):
                        continue
                    for key in ("model_only_prob", "prediction", "probability", "market_prob"):
                        value = outcome.get(key)
                        if value is None:
                            continue
                        _append_probability(value, f"outcomes[{idx}].{key}")

        # 步骤3：备用：尝试 CLOB 实时数据
        if not probability_candidates:
            metadata = event_data.get("metadata") or {}
            market_id = (
                event_data.get("market_id")
                or event_data.get("id")
                or metadata.get("market_id")
                or metadata.get("id")
            )
            slug = (
                event_data.get("slug")
                or metadata.get("slug")
            )
            market_id_str = str(market_id) if market_id else None

            if not market_id_str and not slug:
                logger.warning(
                    "[LowProbFilter] ❌ 无法触发 CLOB fallback，缺少 market_id/slug (keys=%s)",
                    list(event_data.keys())
                )
            else:
                logger.info(
                    "[LowProbFilter] 所有来源失败，尝试 CLOB fallback (market_id=%s, slug=%s)",
                    market_id_str,
                    slug
                )
                try:
                    clob_prob = await self._fetch_clob_probability(
                        market_id_str,
                        slug=slug
                    )
                    # ✅ 修复：使用统一的验证函数，而不是直接添加
                    _append_probability(clob_prob, "clob_api")
                    if clob_prob is not None and clob_prob > 0.0:
                        logger.info(
                            "[LowProbFilter] ✅ CLOB API 返回有效概率: %.2f%% (market_id=%s, slug=%s)",
                            clob_prob,
                            market_id_str,
                            slug
                        )
                    elif clob_prob is not None:
                        logger.warning(
                            "[LowProbFilter] ⚠️ CLOB API 返回无效概率 (0.0 或负值): %.2f%% (market_id=%s, slug=%s)",
                            clob_prob,
                            market_id_str,
                            slug
                        )
                except Exception as exc:
                    logger.warning(
                        "[LowProbFilter] ❌ CLOB API 调用异常 (market_id=%s, slug=%s): %s",
                        market_id_str,
                        slug,
                        exc
                    )

        if not probability_candidates:
            logger.debug("[LowProbFilter] 未找到任何概率数据，不执行过滤")
            return None

        max_prob = max(probability_candidates)
        min_prob = min(probability_candidates)

        logger.debug(
            f"[LowProbFilter] 概率范围: {min_prob:.2f}% - {max_prob:.2f}%, 阈值: {threshold_value:.2f}%"
        )

        if max_prob < threshold_value:
            logger.warning(
                "过滤事件：所有概率低于阈值 (max=%.2f, threshold=%.2f)",
                max_prob,
                threshold_value
            )
            return {
                "threshold": threshold_value,
                "max_probability": max_prob,
                "min_probability": min_prob,
            }

        return None
    except Exception as exc:
        logger.exception("评估低概率事件时发生异常: %s", exc)
        return None
```

---

## 📋 **关键修复点**：

1. **统一验证逻辑**：
   - 所有数据源（`event_data.market_prob`、`outcomes`、`CLOB API`）都使用 `_append_probability()` 函数进行验证
   - 确保 0.0 和负值被正确过滤
   - 确保超界值（> 100.0）被正确过滤

2. **CLOB API 验证增强**：
   - 将第 184-185 行的直接添加改为使用 `_append_probability(clob_prob, "clob_api")`
   - 添加额外的日志记录，明确记录 CLOB API 返回的值和验证结果

3. **日志增强**：
   - 每个数据源的调用结果都有详细日志
   - 验证失败的原因都有明确记录
   - 最终的概率范围和阈值比较都有日志输出

---

## ✅ **验证标准**：

修复后，系统应该能够：
1. ✅ 正确过滤掉 0.0 概率值，即使 CLOB API 返回 0.0
2. ✅ 正确识别有效的市场概率（> 0.0），避免误判为低概率事件
3. ✅ 在所有数据源都失败时，正确返回 `None`（不执行过滤）
4. ✅ 提供详细的日志记录，便于调试和问题定位

---

## 🧪 **测试场景**：

1. **场景1**：CLOB API 返回 0.0
   - 预期：0.0 被过滤，不添加到 `probability_candidates`
   - 预期：如果所有数据源都失败，返回 `None`（不执行过滤）

2. **场景2**：CLOB API 返回有效概率（如 5.5%）
   - 预期：概率被正确添加，事件不被过滤

3. **场景3**：`event_data.market_prob` 存在且有效
   - 预期：优先使用 `event_data.market_prob`，不调用 CLOB API

4. **场景4**：所有数据源都返回 None 或 0.0
   - 预期：返回 `None`（不执行过滤），而不是错误地触发低概率过滤


