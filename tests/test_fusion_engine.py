"""Unit tests for FusionEngine weighting, calibration, and risk heuristics."""
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fusion_engine import FusionEngine  # noqa: E402


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
    assert fusion_weights["model_weight"] > 0.55
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
