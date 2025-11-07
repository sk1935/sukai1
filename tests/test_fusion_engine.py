"""Unit tests for FusionEngine weighting, calibration, and risk heuristics."""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
# Ensure both project root and src are on the path for package imports
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from fusion_engine import FusionEngine, evaluate_trade_signal  # noqa: E402


@pytest.fixture()
def fusion_engine():
    return FusionEngine()


def test_fuse_predictions_respects_confidence_and_dynamic_weights(fusion_engine):
    model_results = {
        "model_high": {
            "probability": 72.0,
            "confidence": "high",
            "reasoning": "High conviction signal"
        },
        "model_low": {
            "probability": 35.0,
            "confidence": "low",
            "reasoning": "Low confidence hedge"
        }
    }
    # Explicit weights are still required by the API but internal logic relies on base weights
    model_weights = {"model_high": 1.0, "model_low": 1.0}
    market_prob = 55.0

    result = fusion_engine.fuse_predictions(model_results, model_weights, market_prob)

    assert 50.0 < result["final_prob"] < 72.0, "Final probability should sit between market and strongest model"
    assert result["model_confidence_factor"] >= 0.0
    fusion_weights = result["fusion_weights"]
    assert fusion_weights["model_weight"] >= FusionEngine.MIN_MODEL_WEIGHT
    assert pytest.approx(fusion_weights["model_weight"] + fusion_weights["market_weight"], rel=1e-3) == 1.0


def test_evaluate_trade_signal_risk_changes_with_volatility():
    low_vol = FusionEngine.evaluate_trade_signal(
        ai_prob=60.0,
        market_prob=15.0,
        days_to_resolution=60,
        event_uncertainty=5.0,
    )
    high_vol = FusionEngine.evaluate_trade_signal(
        ai_prob=60.0,
        market_prob=50.0,
        days_to_resolution=60,
        event_uncertainty=5.0,
    )
    assert high_vol["risk_factor"] > low_vol["risk_factor"]
    assert low_vol["signal"] in {"BUY", "HOLD", "SELL"}


def test_evaluate_trade_signal_handles_none_samples():
    samples = [
        {'ai_prob': None, 'market_prob': 0.6, 'confidence': 0.9},
        {'ai_prob': 0.7, 'market_prob': None, 'confidence': 0.8},
        {'ai_prob': 0.7, 'market_prob': 0.6, 'confidence': None},
    ]
    for sample in samples:
        payload = {
            "ai_prob": sample.get("ai_prob"),
            "market_prob": sample.get("market_prob"),
            "days_to_resolution": sample.get("days_to_resolution", 30),
            "event_uncertainty": sample.get("event_uncertainty", 5.0),
        }
        result = evaluate_trade_signal(**payload)
        print(result)  # 匹配指令要求输出结果
        assert isinstance(result, dict)


def test_fuse_predictions_market_none_single_missing_confidence(fusion_engine, capfd):
    model_results = {
        "model_primary": {
            "probability": 70.0,
            "confidence": None,
            "reasoning": "Primary model lacking confidence"
        },
        "model_backup": {
            "probability": 45.0,
            "confidence": "low",
            "reasoning": "Backup model with low confidence"
        }
    }
    model_weights = {"model_primary": 1.0, "model_backup": 1.0}
    result = fusion_engine.fuse_predictions(model_results, model_weights, market_prob=None)
    captured = capfd.readouterr()
    assert "[fuse_predictions] market_prob is None" in captured.out
    assert isinstance(result["final_prob"], float)
    assert isinstance(result["fusion_weights"]["model_weight"], float)
    assert result["fusion_weights"]["market_weight"] == 0.0


def test_fuse_predictions_market_none_multi_missing_confidence(fusion_engine, capfd):
    model_results = {
        "model_a": {
            "probability": 60.0,
            "confidence": None,
            "reasoning": "Model A missing confidence"
        },
        "model_b": {
            "probability": 55.0,
            "confidence": None,
            "reasoning": "Model B missing confidence"
        }
    }
    model_weights = {"model_a": 1.0, "model_b": 1.0}
    result = fusion_engine.fuse_predictions(model_results, model_weights, market_prob=None)
    captured = capfd.readouterr()
    assert "missing confidence" in captured.out
    assert isinstance(result["final_prob"], float)
    assert isinstance(result["fusion_weights"]["model_weight"], float)


def test_fuse_predictions_with_partial_market_and_missing_confidence(fusion_engine, capfd):
    model_results = {
        "model_a": {
            "probability": 68.0,
            "confidence": None,
            "reasoning": "Model missing confidence but market present"
        },
        "model_b": {
            "probability": 33.0,
            "confidence": "high",
            "reasoning": "High confidence model"
        }
    }
    model_weights = {"model_a": 1.0, "model_b": 1.0}
    result = fusion_engine.fuse_predictions(model_results, model_weights, market_prob=62.0)
    captured = capfd.readouterr()
    assert isinstance(result["final_prob"], float)
    assert isinstance(result["fusion_weights"]["model_weight"], float)
    assert isinstance(result["fusion_weights"]["market_weight"], float)
    assert "missing confidence" in captured.out
