"""Regression tests for OutputFormatter markdown formatting."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from output_formatter import OutputFormatter  # noqa: E402


def build_sample_trade_signal():
    return {
        "signal": "BUY",
        "ev": 0.0825,
        "annualized_ev": 0.315,
        "risk_factor": 0.42,
        "signal_reason": "Edge remains after slippage",
        "edge_threshold": 0.06,
        "slippage_fee": 0.03,
    }


def test_format_prediction_numeric_precision_and_sanitization():
    formatter = OutputFormatter()
    event_data = {
        "question": "Test _Event_ (Sample)",
        "market_prob": 47.338,
        "rules": "Sample rules with extra description",
        "days_left": 30,
        "world_sentiment_summary": "Global mood slightly negative",
        "full_analysis": {
            "event_category": "economy",
            "market_trend": "+1.23%",
            "sentiment_trend": "negative",
            "sentiment_score": -0.23,
            "sentiment_sample": 65,
            "sentiment_source": "NewsAPI",
            "rules_summary": "Rates decision likely postponed"
        }
    }
    fusion_result = {
        "final_prob": 62.347,
        "model_only_prob": 64.889,
        "uncertainty": 7.812,
        "summary": "Model reasoning with _special_ chars that should be escaped.",
        "disagreement": "Low",
        "model_count": 3,
        "deepseek_reasoning": "DeepSeek insight",
        "model_versions": {"model_high": {"display_name": "High", "last_updated": "2024-05-01"}},
        "weight_source": {"file": "weights.json", "updated_at": "2024-05-01"},
        "fusion_weights": {"model_weight": 0.72, "market_weight": 0.28},
        "model_confidence_factor": 0.61
    }
    trade_signal = build_sample_trade_signal()

    output = formatter.format_prediction(event_data, fusion_result, trade_signal)

    # Numbers should have two decimals consistently
    assert "62.35%" in output
    assert "64.89%" in output
    assert "47.34%" in output
    # Reasoning should not contain bare underscores
    assert "_special_" not in output
    assert "信号依据" in output
    assert "BUY" in output


def test_trade_signal_warning_for_missing_data():
    formatter = OutputFormatter()
    warning_section = formatter._render_trade_signal_section(None, None, None)
    assert "暂无信号" in warning_section


@pytest.mark.parametrize(
    "input_text, expected",
    [
        ("Contains _underscores_ and *stars*", "Contains underscores and stars"),
        ("Plain text", "Plain text"),
    ],
)
def test_reasoning_sanitization_strips_markdown(input_text, expected):
    cleaned = OutputFormatter._sanitize_reasoning_text(input_text)
    assert expected in cleaned


def test_multi_option_deepseek_without_summary_stays_safe():
    formatter = OutputFormatter()
    event_data = {"question": "Test multi option"}
    outcomes = [
        {
            "name": "Option A",
            "model_only_prob": 60.0,
            "prediction": 60.0,
            "market_prob": 45.0,
            "summary": "",
            "uncertainty": 4.0
        },
        {
            "name": "Option B",
            "model_only_prob": 40.0,
            "prediction": 40.0,
            "market_prob": 55.0,
            "summary": "",
            "uncertainty": 4.0
        }
    ]
    fusion_result = {"deepseek_reasoning": "DeepSeek standalone reasoning text."}

    output = formatter.format_multi_option_prediction(
        event_data,
        outcomes,
        normalization_info={"event_type": "mutually_exclusive"},
        fusion_result=fusion_result
    )
    assert "模型洞察" in output


def test_conditional_deepseek_without_summary_stays_safe():
    formatter = OutputFormatter()
    event_data = {"question": "Date condition event"}
    outcomes = [
        {
            "name": "Before Dec",
            "model_only_prob": 0.0,
            "prediction": 0.0,
            "market_prob": 30.0,
            "summary": "",
            "uncertainty": 0.0
        }
    ]
    fusion_result = {"deepseek_reasoning": "DeepSeek reasoning for conditional."}

    output = formatter.format_conditional_prediction(
        event_data,
        outcomes,
        normalization_info={"event_type": "conditional"},
        fusion_result=fusion_result
    )
    assert "模型洞察" in output
