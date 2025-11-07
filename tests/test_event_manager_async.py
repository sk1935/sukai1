import asyncio
import sys
from pathlib import Path

import aiohttp
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

import event_manager as event_mgr  # noqa: E402
from event_manager import EventManager  # noqa: E402


@pytest.mark.asyncio
async def test_fetch_primary_sources_concurrently_uses_first(monkeypatch):
    manager = EventManager()

    async def fake_slug(session, slug):
        await asyncio.sleep(0)
        return None

    async def fake_markets(session, query, slug):
        return {"question": "Q", "market_prob": 55.0}

    async def fake_graphql(session, query, slug):
        raise RuntimeError("boom")

    monkeypatch.setattr(manager, "_fetch_via_slug", fake_slug)
    monkeypatch.setattr(manager, "_fetch_via_markets", fake_markets)
    monkeypatch.setattr(manager, "_fetch_via_graphql", fake_graphql)

    result = await manager._fetch_primary_sources_concurrently("test", "slug123")
    assert result["market_prob"] == 55.0


@pytest.mark.asyncio
async def test_request_with_backoff_retries(monkeypatch):
    manager = EventManager()
    delays = []

    async def fake_sleep(duration):
        delays.append(duration)

    monkeypatch.setattr(event_mgr.asyncio, "sleep", fake_sleep)

    class FakeResponse:
        def __init__(self):
            self.status = 200
            self.headers = {"Content-Type": "application/json"}

        async def json(self):
            return {"question": "ok"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def request(self, method, url, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise aiohttp.ClientError("temporary failure")
            return FakeResponse()

    session = FakeSession()
    result = await manager._request_with_backoff(session, "GET", "http://example.com", retries=3, base_delay=1.0)
    assert result == {"question": "ok"}
    assert delays == [1.0, 2.0]
