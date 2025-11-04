# Polymarket AI Predictor — System Bug Report (Codex)

## 1. Potential Runtime Errors

1. **Telegram SDK missing stops the bot entirely**  
   - File/line: `src/main.py:21-53`, `src/main.py:1019-1023`  
   - Cause: `python-telegram-bot` is not installed; the guarded import falls back to dummy classes and `main()` immediately aborts with “🛑 Telegram 依赖未安装…”。  
   - Impact: No Telegram handler, meaning `/predict` cannot be served at all.  
   - Suggested fix: Install `python-telegram-bot==20.7` (per `requirements.txt`) or wrap the CLI so diagnostics can still run when Telegram is absent.

2. **OpenRouter layer permanently disabled because `tenacity` is missing**  
   - File/line: `services/llm_clients/openrouter_layer.py:21-34`, `src/openrouter_assistant.py:25-41`  
   - Cause: `from tenacity import …` raises `ModuleNotFoundError`, so `OPENROUTER_LAYER_AVAILABLE` is set to `False` and `OPENROUTER_ASSISTANT_ENABLED` immediately returns `None`.  
   - Impact: `main.py:274-295` still awaits `get_news_summary()`, but the coroutine always short-circuits, so the OpenRouter fallback models and news summaries never run.  
   - Suggested fix: `pip install tenacity>=8.2.0` and re-enable the assistant via configuration instead of hard-coded booleans.

3. **News fetching stack can’t start because `feedparser` (and related parsers) are absent**  
   - File/line: `src/services/news_fetcher/google_rss.py:9`, bubbling to `src/news_cache.py:21-51`  
   - Cause: Importing `news_fetcher` fails when `feedparser` isn’t installed, triggering the “⚠️ news_fetcher 模块不可用” fallback which replaces all grabbers with empty async stubs.  
   - Impact: `news_cache.fetch_and_cache_news()` and all downstream features (`EventAnalyzer` sentiment boosts, `world_sentiment_engine`, `openrouter_assistant`) never receive real news data.  
   - Suggested fix: Install `feedparser`, `beautifulsoup4`, `python-dateutil`, etc., then remove/relax the hardcoded `NEWS_CACHE_ENABLED=False`.

4. **Notion logging silently disabled**  
   - File/line: `src/notion_logger.py:17-45`  
   - Cause: `notion-client` import fails, `NOTION_AVAILABLE=False`, so `ForecastingBot` always sets `self.notion_logger = None`.  
   - Impact: Any expectation of `/predict` writes to Notion fails without explicit notice beyond the warning log.  
   - Suggested fix: Install `notion-client>=2.2.1` or gate Notion usage behind config flags so users understand logging is optional.

## 2. Logic Defects / Unused Paths

1. **News cache worker is effectively a no-op**  
   - File/line: `src/news_cache.py:59`, `src/news_cache.py:182-186`, `src/main.py:158-167`  
   - Cause: `NEWS_CACHE_ENABLED` is hard-coded to `False`; `fetch_and_cache_news()` immediately returns `[]`, yet `handle_predict()` still spawns a background task.  
   - Impact: Extra `create_task` overhead with no caching; functions such as `_save_sentiment_cache` are never exercised.  
   - Suggested fix: Drive the flag via environment/config and only schedule the task when the pipeline is actually enabled.

2. **World temperature and OpenRouter assistant are permanently disabled**  
   - File/line: `src/world_sentiment_engine.py:23-46`, `src/openrouter_assistant.py:19-43`  
   - Cause: `WORLD_SENTIMENT_ENABLED` and `OPENROUTER_ASSISTANT_ENABLED` default to `False` with no runtime override.  
   - Impact: `EventAnalyzer.analyze_event_full()` always receives `None` for `world_temp`, and `main.py` spends time awaiting `get_news_summary()` even though it always returns `None`.  
   - Suggested fix: Replace the hard-coded booleans with config/env switches so these modules can operate once dependencies are present.

3. **`ModelOrchestrator.call_all_models()` contains dead code**  
   - File/line: `src/model_orchestrator.py:639-717`  
   - Cause: The method immediately `return`s `await self.call_models_parallel(...)`, so the subsequent `call_with_timeout` helper, `asyncio.create_task`, and global timeout/cancellation logic never execute.  
   - Impact: The intended coarse-grained timeout protection (cancelling pending tasks, filling defaults) is unreachable, making future maintenance harder and leaving duplicate, confusing logic.  
   - Suggested fix: Remove the early return and consolidate on either the batch-based implementation or the task-based one.

4. **OpenRouter news summary never reaches prompt builder through fallback**  
   - File/line: `src/prompt_builder.py:64-90`  
   - Cause: `_build_news_summary_section()` only reads `event_data["news_summary"]`; the code path that should invoke `get_news_summary()` is a commented `pass`.  
   - Impact: Even after the main handler obtains a summary, prompts built elsewhere (e.g., offline callers) cannot leverage the assistant, and the helper function is misleadingly incomplete.  
   - Suggested fix: Implement the intended async retrieval or remove the placeholder to avoid confusion.

## 3. Async / Await Issues

1. **Coroutine returned by `get_cached_news()` is never awaited**  
   - File/line: `src/openrouter_assistant.py:135` vs. `src/news_cache.py:261-269`; runtime proof in `bot_output.log:1-3`  
   - Cause: `get_cached_news` is declared `async` but called synchronously, producing the warning “RuntimeWarning: coroutine 'get_cached_news' was never awaited” and leaving `news_list` as a coroutine object.  
   - Impact: `generate_news_summary()` immediately hits the “没有可用的新闻数据” branch, so OpenRouter summarisation can never proceed even if cache files exist.  
   - Suggested fix: either `await get_cached_news()` or make `get_cached_news` synchronous since it only performs disk I/O.

2. **Intended timeout-aware task orchestration is never reached**  
   - File/line: `src/model_orchestrator.py:639-717`  
   - Cause: Because of the early return, the `asyncio.create_task` + `asyncio.wait` branch never runs; hence there is no layer that cancels straggling tasks after `MAX_TOTAL_WAIT_TIME`.  
   - Impact: Long-running batches rely solely on per-model `asyncio.wait_for`, so if a coroutine wedges before hitting the timeout (e.g., DNS stall), the outer `call_all_models` provides no extra safety.  
   - Suggested fix: Rewire `call_all_models` so the task-based controller actually executes or delete it to avoid false confidence.

3. **Sequential sentiment API calls can exceed the outer timeout**  
   - File/line: `src/event_analyzer.py:387-511`  
   - Cause: `_get_sentiment_signal()` calls GDELT, then NewsAPI, then Mediastack sequentially with `await asyncio.wait_for(..., timeout=8)` each. In the worst case the coroutine needs ~24s, while `handle_predict()` wraps `analyze_event_full()` with a 15 s `asyncio.wait_for`.  
   - Impact: When the outer wait times out, the inner coroutines keep running until their individual timeouts fire, flooding logs with warnings and delaying loop responsiveness.  
   - Suggested fix: run the sentiment fetchers concurrently (e.g., `asyncio.gather`) or shorten the per-source timeouts so the total cannot exceed the outer guard.

4. **Background news cache task still spawns despite no-op body**  
   - File/line: `src/main.py:158-167`, `src/news_cache.py:182-186`  
   - Cause: `asyncio.create_task(fetch_and_cache_news(...))` is launched every `/predict`, but the coroutine returns immediately because of the disabled flag.  
   - Impact: The task scheduling overhead remains while providing no benefit; future maintainers may assume caching is active even though the coroutine exits instantly.  
   - Suggested fix: gate the `create_task` on `NEWS_CACHE_ENABLED` (or on dependency availability) to avoid spawning inert tasks.

---

*This report lists only analysis findings; no code changes were applied.*  
