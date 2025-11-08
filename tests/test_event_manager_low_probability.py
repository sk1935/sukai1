import pytest

from src.event_manager import EventManager


@pytest.fixture
def event_manager():
    return EventManager()


@pytest.mark.asyncio
async def test_filter_low_probability_event_returns_details(event_manager, caplog):
    event_data = {
        "question": "Test Event",
        "outcomes": [
            {"model_only_prob": 0.5},
            {"market_prob": 0.8},
        ],
    }

    with caplog.at_level("WARNING"):
        decision = await event_manager.filter_low_probability_event(event_data, threshold=1.0)

    assert decision is not None
    assert decision["max_probability"] == pytest.approx(0.8)
    assert decision["threshold"] == pytest.approx(1.0)
    assert any("过滤事件" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_filter_low_probability_event_allows_higher_probability(event_manager):
    event_data = {
        "question": "Another Event",
        "outcomes": [
            {"model_only_prob": 5.2},
            {"market_prob": 35.7},
        ],
    }

    decision = await event_manager.filter_low_probability_event(event_data, threshold=5.0)

    assert decision is None


@pytest.mark.asyncio
async def test_filter_low_probability_event_handles_missing_data(event_manager):
    event_data = {"question": "No Probabilities"}

    assert await event_manager.filter_low_probability_event(event_data, threshold=5.0) is None
