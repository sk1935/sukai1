"""Historical regression tests ensure calibration changes keep legacy metrics stable."""
from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fusion_engine import FusionEngine  # noqa: E402


HISTORICAL_SAMPLES = [
    {"ai_prob": 0.62, "market_prob": 0.55, "truth": 1},
    {"ai_prob": 0.41, "market_prob": 0.48, "truth": 0},
    {"ai_prob": 0.73, "market_prob": 0.60, "truth": 1},
    {"ai_prob": 0.28, "market_prob": 0.40, "truth": 0},
]


def compute_backtest_metrics(samples):
    preds = [s["ai_prob"] for s in samples]
    truths = [s["truth"] for s in samples]
    brier = sum((pred - truth) ** 2 for pred, truth in zip(preds, truths)) / len(samples)
    mean_pred = statistics.fmean(preds)
    sharpness = math.sqrt(sum((pred - mean_pred) ** 2 for pred in preds) / len(preds))
    accuracy = sum(int((pred >= 0.5) == truth) for pred, truth in zip(preds, truths)) / len(samples)
    return {
        "brier": brier,
        "sharpness": sharpness,
        "accuracy": accuracy,
    }


def test_historical_backtest_metrics_regression():
    metrics = compute_backtest_metrics(HISTORICAL_SAMPLES)
    # These baselines should change only when intentional calibration updates happen.
    assert pytest.approx(metrics["brier"], rel=1e-3) == 0.0737
    assert pytest.approx(metrics["sharpness"], rel=1e-3) == 0.1640
    assert metrics["accuracy"] == 0.75


def test_trade_signal_history_consistency():
    sample = HISTORICAL_SAMPLES[0]
    trade = FusionEngine.evaluate_trade_signal(
        ai_prob=sample["ai_prob"] * 100,
        market_prob=sample["market_prob"] * 100,
        days_to_resolution=45,
        event_uncertainty=6.5,
    )
    assert trade["signal"] in {"BUY", "HOLD", "SELL"}
    assert 0.0 <= trade["risk_factor"] <= 2.0
