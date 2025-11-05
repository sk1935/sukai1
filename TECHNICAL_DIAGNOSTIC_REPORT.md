# 🔍 Polymarket AI Predictor - Technical Diagnostic Report

**Generated:** 2025-01-27  
**Project:** Polymarket AI Predictor  
**Analysis Scope:** Complete codebase analysis

---

## 📋 Project Overview

### What This Program Does

**Polymarket AI Predictor** is a Telegram bot that provides AI-powered probability predictions for Polymarket prediction markets. The system:

1. **Receives** user queries via Telegram (`/predict` command) with event descriptions or Polymarket URLs
2. **Fetches** market data from Polymarket API (probabilities, rules, outcomes)
3. **Analyzes** events (category, sentiment, market trends)
4. **Calls** multiple AI models concurrently (GPT-4o, Claude, Gemini, DeepSeek, OpenRouter models)
5. **Fuses** predictions using weighted averaging and market probability blending
6. **Normalizes** multi-option events (mutually exclusive vs conditional)
7. **Formats** output as Chinese Markdown reports
8. **Logs** results to Notion database (optional)

### Major Components

#### Core Architecture (5-Layer Design)

1. **Event Layer** (`event_manager.py`)
   - Parses user input (text/URL)
   - Fetches Polymarket market data via GraphQL/REST APIs
   - Filters active markets, handles multi-option events

2. **Prompt Layer** (`prompt_builder.py`)
   - Generates specialized prompts per model
   - Includes world sentiment, news summaries
   - Model-specific dimension assignments

3. **Inference Layer** (`model_orchestrator.py`)
   - Concurrent calls to multiple AI models via AICanAPI
   - Timeout handling, retry logic, fallback models
   - JSON response parsing

4. **Fusion Layer** (`fusion_engine.py`)
   - Weighted fusion of model predictions
   - Market probability blending (80% AI + 20% market)
   - Multi-option normalization (mutually exclusive vs conditional)
   - Trade signal evaluation (EV, risk factor, BUY/HOLD/SELL)

5. **Output Layer** (`output_formatter.py`)
   - Formats predictions as Telegram Markdown
   - Handles single-option, multi-option, conditional events
   - Trade signal display
   - Reasoning text sanitization

#### Auxiliary Modules

- **EventAnalyzer** (`event_analyzer.py`): Category detection, sentiment analysis, model task assignment
- **NotionLogger** (`notion_logger.py`): Async logging to Notion database
- **NewsCache** (`news_cache.py`): News fetching and caching (6-hour cache)
- **WorldSentimentEngine** (`world_sentiment_engine.py`): Global sentiment calculation (descriptive mode)
- **OpenRouterAssistant** (`openrouter_assistant.py`): Free model integration via OpenRouter API
- **LMArena Updater** (`config/update_lmarena_weights.py`): Dynamic model weight updates from LMArena.ai

---

## 🔗 Dependency Graph

### Module Import Relationships

```
main.py
├── event_manager.py
├── event_analyzer.py
│   ├── world_sentiment_engine.py
│   │   └── news_cache.py
│   └── openrouter_assistant.py
│       └── news_cache.py
├── prompt_builder.py
│   └── openrouter_assistant.py
├── model_orchestrator.py
├── fusion_engine.py
│   └── model_orchestrator.py (for version info)
├── output_formatter.py
│   └── fusion_engine.py (for constants)
└── notion_logger.py

External Dependencies:
├── services/llm_clients/openrouter_layer.py
└── config/update_lmarena_weights.py
```

### External API Dependencies

1. **Telegram Bot API** (`python-telegram-bot`)
2. **Polymarket API** (GraphQL, REST, CLOB)
3. **AICanAPI** (Unified model interface)
4. **OpenRouter API** (Free models)
5. **Notion API** (`notion-client`)
6. **LMArena.ai API** (Model leaderboard)
7. **GDELT/NewsAPI/Mediastack** (Sentiment APIs, optional)

---

## 🐛 Detected Bugs (by Severity)

### 🔴 Critical Runtime Errors

#### 1. **Type Safety Issues in `.replace()` Calls**

**Location:** `src/fusion_engine.py:394`, `src/output_formatter.py:123`

**Issue:** The `_sanitize_reasoning_fragment()` and `_sanitize_reasoning_text()` methods accept `Optional[str]` but are called with values that may be dict/list from `result.get(key)`. While they do `str(value)`, this converts dict to string representation like `"{'key': 'value'}"` rather than JSON.

**Risk:** Medium-High - Will work but may produce ugly string representations instead of proper JSON serialization.

**Current Implementation:**
```python
# fusion_engine.py:395-398
def _sanitize_reasoning_fragment(value: Optional[str], context: str = "fusion") -> str:
    if value is None:
        return ""
    cleaned = str(value)  # ⚠️ Converts dict to "{'key': 'value'}" instead of JSON
```

**Fix Required:**
- Add `isinstance(value, (dict, list))` check and use `json.dumps()` for proper serialization
- Ensure type annotation matches actual usage (should be `Optional[Union[str, dict, list]]`)

#### 2. **Missing Type Conversion in `_sanitize_reasoning_fragment()`**

**Location:** `src/fusion_engine.py:404-428`

**Issue:** The method accepts `Optional[str]` but `value` parameter may be dict/list from `result.get(key)`. The method does `str(value)` but doesn't handle JSON serialization for dict/list.

**Risk:** High - Will produce string representation like `"{'key': 'value'}"` instead of JSON.

**Fix Required:**
- Add `isinstance(value, (dict, list))` check and use `json.dumps()` before string conversion

#### 3. **Potential NoneType in Trade Signal Calculation**

**Location:** `src/fusion_engine.py:1150-1175`

**Issue:** `days_to_resolution` may be None or invalid type, causing float conversion to fail silently or produce incorrect EV calculations.

**Risk:** Medium - May produce incorrect trade signals.

**Status:** Partially fixed - recent code adds try/except but may need more robust validation.

### 🟡 Medium Severity Issues

#### 4. **Inconsistent Trade Signal Data Structure**

**Location:** `src/main.py:779-787`, `src/output_formatter.py:33-89`

**Issue:** Trade signal data is passed in nested format `{"data": {...}}` in some places and flat format `{...}` in others. The `_extract_trade_signal_data()` method handles this, but inconsistencies may cause issues.

**Risk:** Medium - May cause trade signal display to fail or show incorrect data.

**Fix Required:**
- Standardize trade signal data structure across all modules
- Ensure `fusion_result["trade_signal"]` always contains the same structure

#### 5. **Missing Error Handling in Normalization Banner Logic**

**Location:** `src/output_formatter.py:132-164`

**Issue:** `total_before` may be None or 0, causing division by zero or incorrect guard_fraction calculation.

**Risk:** Low-Medium - May show incorrect normalization banners.

**Current Code:**
```python
guard_fraction = (total_before / 100.0) if total_before else 0.0
```
This is safe, but `total_before` could be None, causing TypeError.

**Fix Required:**
- Add explicit None check: `total_before = normalization_info.get("total_before") or 0.0`

#### 6. **Potential Race Condition in Notion Logger**

**Location:** `src/notion_logger.py:322-325`

**Issue:** Rate limiting uses `time.time()` but doesn't use locks. Concurrent async calls may bypass 5-second rate limit.

**Risk:** Low-Medium - May cause Notion API rate limit errors.

**Fix Required:**
- Use `asyncio.Lock()` for rate limiting in async context

### 🟢 Low Severity / Code Quality Issues

#### 7. **Deprecated `apscheduler` Usage**

**Location:** `src/main.py:26-60`

**Issue:** Code patches `apscheduler.util.astimezone` to handle `zoneinfo` timezones. This is a workaround for Python 3.13 compatibility.

**Risk:** Low - Works but relies on monkey-patching.

**Recommendation:** Consider upgrading `apscheduler` or using alternative scheduling library.

#### 8. **Unused Backup Files**

**Location:** Multiple `.bak` files in `src/` directory

**Issue:** Backup files (`*.bak`) are present but not needed in production:
- `src/main.py.bak`
- `src/fusion_engine.py.bak`
- `src/output_formatter.py.bak`
- etc.

**Risk:** Low - No runtime impact, but clutters codebase.

**Recommendation:** Remove or move to archive directory.

#### 9. **Missing Type Hints in Some Functions**

**Location:** Various files

**Issue:** Some functions lack type hints, making static analysis difficult.

**Risk:** Low - Code works but less maintainable.

**Example:**
```python
# output_formatter.py:33
def _extract_trade_signal_data(trade_data: Optional[Dict]) -> Dict:
    # Should specify Dict[str, Any] or more specific types
```

---

## 🔒 Security & Configuration Issues

### 1. **Environment Variable Dependencies**

**Location:** `.env` file (not accessible, but referenced in code)

**Issues:**
- Multiple API keys required: `TELEGRAM_BOT_TOKEN`, `AICANAPI_KEY`, `OPENROUTER_API_KEY`, `NOTION_TOKEN`, etc.
- Missing `.env` file or missing keys will cause runtime failures
- No validation of required environment variables at startup

**Risk:** Medium - Silent failures if keys are missing.

**Recommendation:**
- Add startup validation to check all required environment variables
- Provide clear error messages for missing keys

### 2. **API Key Exposure Risk**

**Location:** Code references API keys but doesn't hardcode them (good)

**Status:** ✅ Safe - Uses environment variables

### 3. **Rate Limiting**

**Location:** `src/notion_logger.py`, `src/event_analyzer.py`

**Status:** ✅ Implemented - 5-second rate limit for Notion, API-specific limits for sentiment APIs

---

## 🏗️ Architecture & Design Issues

### 1. **Tight Coupling Between Modules**

**Issue:** Some modules have circular or tight dependencies:
- `fusion_engine.py` imports `model_orchestrator.py` for version info
- `event_analyzer.py` imports multiple auxiliary modules

**Risk:** Low - Works but makes testing harder.

**Recommendation:** Consider dependency injection for better testability.

### 2. **Mixed Synchronous and Asynchronous Code**

**Location:** `src/main.py`, `src/event_manager.py`

**Issue:** Some functions are async, some are sync. Wrapper functions (`maybe_await`, `wrap_async_handler`) handle this, but it's complex.

**Risk:** Low - Works but error-prone.

**Status:** ✅ Mitigated - Wrapper functions handle async/sync conversion

### 3. **Large Function Complexity**

**Location:** `src/main.py:handle_predict()` (~400+ lines), `src/event_manager.py:fetch_polymarket_data()` (~800+ lines)

**Issue:** Some functions are very long and handle multiple responsibilities.

**Risk:** Low - Works but harder to maintain.

**Recommendation:** Consider breaking into smaller functions.

---

## 📦 Unused Modules & Dead Code

### Unused/Dead Code Detected

1. **Backup Files** (`.bak` files)
   - `src/main.py.bak`
   - `src/fusion_engine.py.bak`
   - `src/output_formatter.py.bak`
   - `src/event_analyzer.py.bak`
   - `src/model_orchestrator.py.bak`
   - `src/notion_logger.py.bak`
   - `src/news_cache.py.bak`
   - `src/openrouter_assistant.py.bak`
   - `src/world_sentiment_engine.py.bak`

2. **Test/Utility Scripts** (May be used manually, not in main flow)
   - `test_auxiliary_modules.py`
   - `test_news_fetcher.py`
   - `explain_fusion.py`
   - `check_notion_access.py`
   - `debug_notion_properties.py`
   - `manual_notion_write.py`

3. **Potentially Unused Imports**
   - Need static analysis to verify, but some imports may be unused in specific files

### Conditionally Disabled Modules

1. **News Cache** (`NEWS_CACHE_ENABLED` flag)
   - May be disabled via environment variable
   - Module still imported but not used if disabled

2. **World Sentiment Engine** (`WORLD_SENTIMENT_ENABLED` flag)
   - May be disabled via environment variable

3. **OpenRouter Assistant** (`OPENROUTER_ASSISTANT_ENABLED` flag)
   - May be disabled via environment variable

**Status:** ✅ Intentional - Feature flags allow graceful degradation

---

## ⚡ Optimization Recommendations

### 1. **Performance Optimizations**

#### a. Caching Improvements
- **Current:** News cache (6 hours), sentiment cache (3 hours)
- **Recommendation:** Add cache for Polymarket API responses (market data changes slowly)
- **Impact:** Reduce API calls, faster response times

#### b. Concurrent Model Calls
- **Current:** Uses `asyncio.gather` with Semaphore(5)
- **Status:** ✅ Good - Already optimized

#### c. Database Queries (Notion)
- **Current:** Sequential writes for multi-option events
- **Recommendation:** Batch writes if Notion API supports it
- **Impact:** Faster Notion logging

### 2. **Code Quality Improvements**

#### a. Type Safety
- Add comprehensive type hints
- Use `mypy` for static type checking
- Add runtime type validation for critical functions

#### b. Error Handling
- Add more specific exception types
- Improve error messages with context
- Add retry logic for transient failures

#### c. Testing
- Add unit tests for core functions
- Add integration tests for full prediction flow
- Add mock data for testing without API calls

### 3. **Maintainability**

#### a. Configuration Management
- Centralize all configuration in `config/` directory
- Use configuration classes instead of dicts
- Validate configuration at startup

#### b. Logging
- Use structured logging (JSON format)
- Add log levels (DEBUG, INFO, WARNING, ERROR)
- Add request IDs for tracing

#### c. Documentation
- Add docstrings to all public functions
- Add inline comments for complex logic
- Generate API documentation

---

## 🔧 Refactor Plan for Codex

### Priority 1: Critical Fixes (Must Fix)

1. **Fix Type Safety in Reasoning Sanitization**
   - **Files:** `src/fusion_engine.py`, `src/output_formatter.py`
   - **Action:** Add type checks and JSON serialization for dict/list values
   - **Lines:** `fusion_engine.py:404-428`, `output_formatter.py:93-104`

2. **Fix Trade Signal Data Structure Consistency**
   - **Files:** `src/main.py`, `src/output_formatter.py`
   - **Action:** Standardize trade signal format across all modules
   - **Lines:** `main.py:779-787`, `output_formatter.py:33-89`

3. **Add None Checks in Normalization Banner**
   - **Files:** `src/output_formatter.py`
   - **Action:** Add explicit None checks for `total_before`
   - **Lines:** `output_formatter.py:139-144`

### Priority 2: Important Improvements (Should Fix)

4. **Add Environment Variable Validation**
   - **Files:** `src/main.py`
   - **Action:** Add startup check for required environment variables
   - **Lines:** `main.py:main()` function

5. **Improve Notion Rate Limiting**
   - **Files:** `src/notion_logger.py`
   - **Action:** Use `asyncio.Lock()` for async-safe rate limiting
   - **Lines:** `notion_logger.py:322-325`

6. **Remove Backup Files**
   - **Action:** Delete or archive all `.bak` files
   - **Files:** Multiple `.bak` files in `src/`

### Priority 3: Code Quality (Nice to Have)

7. **Add Type Hints**
   - **Files:** All core modules
   - **Action:** Add comprehensive type hints
   - **Tool:** Use `mypy --strict` to validate

8. **Break Down Large Functions**
   - **Files:** `src/main.py`, `src/event_manager.py`
   - **Action:** Extract smaller functions from `handle_predict()` and `fetch_polymarket_data()`

9. **Add Unit Tests**
   - **Action:** Create test suite for core functions
   - **Files:** `tests/test_*.py`

---

## 📊 Code Statistics

- **Total Python Files:** ~40 files
- **Core Modules:** 8 files
- **Auxiliary Modules:** 5 files
- **Test Files:** 3 files
- **Configuration Files:** 4 files
- **Lines of Code (estimated):** ~15,000+ lines

### Module Complexity (Estimated)

| Module | Lines | Complexity | Status |
|--------|-------|------------|--------|
| `main.py` | ~1400 | High | ✅ Functional |
| `event_manager.py` | ~1900 | Very High | ✅ Functional |
| `fusion_engine.py` | ~1200 | High | ⚠️ Type issues |
| `output_formatter.py` | ~1250 | High | ⚠️ Type issues |
| `model_orchestrator.py` | ~700 | Medium | ✅ Functional |
| `event_analyzer.py` | ~600 | Medium | ✅ Functional |
| `prompt_builder.py` | ~200 | Low | ✅ Functional |
| `notion_logger.py` | ~500 | Medium | ✅ Functional |

---

## ✅ What's Working Well

1. **Architecture:** Clean 5-layer separation of concerns
2. **Concurrency:** Well-implemented async/await patterns
3. **Error Handling:** Comprehensive try/except blocks
4. **Caching:** Effective caching for news and sentiment
5. **Modularity:** Good separation of concerns
6. **Documentation:** System summary document exists

---

## 🎯 Summary

### Critical Issues: 3
- Type safety in reasoning sanitization (HIGH)
- Trade signal data structure inconsistency (MEDIUM)
- Missing None checks (LOW-MEDIUM)

### Important Issues: 3
- Environment variable validation
- Notion rate limiting (async safety)
- Backup file cleanup

### Code Quality: 3
- Type hints
- Function complexity
- Testing coverage

### Overall Assessment

**Status:** ⚠️ **Functional with Known Issues**

The codebase is **production-ready** but has **critical type safety issues** that need immediate attention. The architecture is solid, and the code works, but the recent refactoring of reasoning sanitization removed type safety checks that could cause runtime crashes.

**Recommendation:** Fix Priority 1 issues before deploying to production.

---

**Report Generated:** 2025-01-27  
**Next Steps:** Apply Priority 1 fixes, then proceed with Priority 2 improvements.

