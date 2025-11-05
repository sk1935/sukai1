# Trade Signal Integration - Validation Plan

## End-to-End Dry Run Commands

### 1. Single-Option Event Test

**Command** (in Telegram bot):
```
/predict Will Bitcoin reach $100k by Dec 2024?
```

**Expected Output**:
- Trade signal block appears after fusion prediction
- Format: `📊 *交易信号:* 💰 BUY` (or ⚠️ HOLD / ❌ SELL)
- Table with EV, Annualized EV, Risk Factor, Signal
- Console log: `[TRADE] Signal=BUY, EV=..., Annualized=..., Risk=...`

**Validation Checks**:
- [ ] Trade signal banner appears
- [ ] Trade signal table is present
- [ ] All values are formatted correctly (no NoneType errors)
- [ ] Notion page includes trade signal fields (if enabled)

### 2. Multi-Option Event Test

**Command** (in Telegram bot):
```
/predict https://polymarket.com/event/fed-decision-december
```

**Expected Output**:
- Trade signal block appears after outcomes list, before rules
- Normalization logic still works correctly
- Trade signal based on option with largest AI-market gap

**Validation Checks**:
- [ ] Trade signal appears in correct position
- [ ] Normalization check still displays correctly
- [ ] Conditional vs mutually_exclusive formatting preserved
- [ ] Notion logging includes trade signal for top option

### 3. Conditional Event Test

**Command**:
```
/predict Will X happen on Oct 30, Nov 15, or Dec 1?
```

**Expected Output**:
- Trade signal appears before AI summary
- Conditional event banner still shows: "ℹ️ *条件事件为独立市场（概率未归一化）*"
- No normalization check displayed

**Validation Checks**:
- [ ] Trade signal doesn't interfere with conditional formatting
- [ ] Event type classification still correct
- [ ] All outcomes display correctly

## Console Log Verification

Look for these log messages:
```
[TRADE] Signal=BUY, EV=5.234, Annualized=45.678, Risk=0.450
```

## Notion Database Verification

If Notion is enabled, check that properties include:
- `EV` (number)
- `Annualized EV` (number)
- `Risk Factor` (number)
- `Signal` (select: BUY/HOLD/SELL)
- `Signal Reason` (rich_text)

**Note**: Properties are only added if values exist (safe fallback).

## Error Handling Tests

### Test 1: Missing Trade Signal
- Event with no trade signal calculation
- Should: Display output without trade signal block (no error)

### Test 2: None Values
- Trade signal with None values
- Should: Display "—" in table for missing values

### Test 3: Missing Notion Properties
- Notion database missing trade signal fields
- Should: Skip missing properties gracefully (no API error)

## Quick Validation Script

```python
# Quick test (run in Python REPL)
from src.fusion_engine import FusionEngine

engine = FusionEngine()
result = engine.evaluate_trade_signal(
    ai_prob=65.0,
    market_prob=50.0,
    days_to_resolution=30,
    event_uncertainty=5.0
)

print(result)
# Expected: {'signal': 'BUY', 'ev': 15.0, 'annualized_ev': 182.5, 'risk_factor': 0.35, 'signal_reason': '...'}
assert 'signal_reason' in result
assert result['signal'] in ['BUY', 'HOLD', 'SELL']
```

## Success Criteria

✅ **All criteria met**:
1. Trade signal appears in all output formats (single, multi, conditional)
2. No TypeError: NoneType.__format__ errors
3. Normalization logic unchanged
4. Notion logging includes trade signal fields (if enabled)
5. Missing values handled gracefully ("—" in output, skipped in Notion)
