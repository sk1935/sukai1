import sys
from pathlib import Path

import types

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

# Provide lightweight stubs so importing main.py does not require optional deps.
apscheduler_stub = types.ModuleType("apscheduler")
apscheduler_util_stub = types.ModuleType("apscheduler.util")
apscheduler_util_stub.astimezone = lambda tz: tz
sys.modules.setdefault("apscheduler", apscheduler_stub)
sys.modules.setdefault("apscheduler.util", apscheduler_util_stub)

import main  # noqa: E402

telegram_call_with_retry = main.telegram_call_with_retry  # noqa: E402
TimedOut = getattr(main, "TimedOut", RuntimeError)


@pytest.mark.asyncio
async def test_telegram_call_with_retry_recovers_after_timeouts():
    attempts = {"count": 0}

    async def _success():
        return "ok"

    def factory():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TimedOut("timeout")
        return _success()

    result = await telegram_call_with_retry(factory, "reply_text.test", retries=3, delay=0.01, timeout=0.1)
    assert result == "ok"
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_telegram_call_with_retry_raises_after_max_attempts():
    def factory():
        raise TimedOut("timeout")

    with pytest.raises(TimedOut):
        await telegram_call_with_retry(factory, "reply_text.fail", retries=2, delay=0.01, timeout=0.05)
