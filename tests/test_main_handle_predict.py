from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.main import ForecastingBot


class StubEventManager:
    def __init__(self, filter_response=None):
        self.filter_response = filter_response
        self.parse_called = False

    def parse_event_from_message(self, message_text: str):
        self.parse_called = True
        return {"query": message_text.replace("/predict", "").strip()}

    async def fetch_polymarket_data(self, event_info):
        return {"question": "Stub Event", "outcomes": [{"model_only_prob": 0.5}]}

    def filter_low_probability_event(self, event_data, threshold=None):
        return self.filter_response

    def _create_mock_market_data(self, query):
        return {"question": query or "Mock Event", "is_mock": True}


class StubOutputFormatter:
    def __init__(self):
        self.low_probability_calls = []

    def format_low_probability_notice(self, event_data, threshold, max_probability):
        self.low_probability_calls.append((event_data, threshold, max_probability))
        return "⚠️ 低概率事件"

    def format_error(self, message):
        return f"error:{message}"


class DummyMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class DummyBot:
    async def send_chat_action(self, chat_id, action):
        return None


def _build_update(message_text="/predict test"):
    message = DummyMessage(message_text)
    update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))
    return update, message


def _build_context():
    return SimpleNamespace(bot=DummyBot())


@pytest.mark.asyncio
async def test_handle_predict_filters_low_probability_event():
    filter_details = {"threshold": 1.0, "max_probability": 0.5, "min_probability": 0.5}
    event_manager = StubEventManager(filter_response=filter_details)
    output_formatter = StubOutputFormatter()

    bot = ForecastingBot(
        event_manager=event_manager,
        prompt_builder=SimpleNamespace(),
        model_orchestrator=SimpleNamespace(get_available_models=lambda: []),
        fusion_engine=SimpleNamespace(),
        output_formatter=output_formatter,
        event_analyzer=SimpleNamespace(),
        notion_logger=None,
    )

    bot._prepare_prediction_context = AsyncMock(return_value="/predict test")
    bot._fetch_event_data = AsyncMock(return_value={"question": "Stub Event", "outcomes": []})
    bot._analyze_event = AsyncMock()

    update, message = _build_update()
    context = _build_context()

    await bot.handle_predict(update, context)

    assert event_manager.parse_called is True
    assert bot._analyze_event.await_count == 0
    assert output_formatter.low_probability_calls
    assert message.replies
    reply_text, _ = message.replies[0]
    assert "低概率事件" in reply_text


@pytest.mark.asyncio
async def test_handle_predict_logs_and_returns_error(caplog):
    event_manager = StubEventManager(filter_response=None)
    output_formatter = StubOutputFormatter()

    bot = ForecastingBot(
        event_manager=event_manager,
        prompt_builder=SimpleNamespace(),
        model_orchestrator=SimpleNamespace(get_available_models=lambda: ["model-a"]),
        fusion_engine=SimpleNamespace(),
        output_formatter=output_formatter,
        event_analyzer=SimpleNamespace(),
        notion_logger=None,
    )

    bot._prepare_prediction_context = AsyncMock(return_value="/predict test")
    bot._fetch_event_data = AsyncMock(return_value={"question": "Stub Event", "outcomes": []})
    bot._analyze_event = AsyncMock(side_effect=RuntimeError("test failure"))

    update, message = _build_update()
    context = _build_context()

    with caplog.at_level("ERROR"):
        await bot.handle_predict(update, context)

    assert any("handle_predict 处理异常" in record.message for record in caplog.records)
    reply_text, _ = message.replies[-1]
    assert reply_text.startswith("error:")

