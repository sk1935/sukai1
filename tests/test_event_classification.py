import math
import sys
from pathlib import Path

# Ensure src is on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fusion_engine import FusionEngine


def test_fomc_event_classification_and_normalization():
    event_title = "What will the upper bound of the federal funds target range be after the next FOMC meeting?"
    rules = (
        "Each contract resolves based on the upper bound of the target federal funds range. "
        "Exactly one outcome will resolve YES."
    )
    outcomes = [
        {"name": "25 bps decrease", "model_only_prob": 65.8, "market_prob": 60.1},
        {"name": "No change", "model_only_prob": 59.4, "market_prob": 25.0},
        {"name": "25+ bps increase", "model_only_prob": 8.0, "market_prob": 8.0},
        {"name": "50+ bps decrease", "model_only_prob": 8.9, "market_prob": 6.9},
    ]
    now_probs = [o["market_prob"] for o in outcomes]

    classification = FusionEngine.classify_multi_option_event(
        event_title,
        outcomes,
        event_rules=rules,
        now_probs=now_probs,
    )
    assert classification == "mutually_exclusive"

    normalization = FusionEngine.normalize_all_predictions(
        outcomes,
        event_title=event_title,
        event_rules=rules,
        now_probabilities=now_probs,
    )

    assert normalization["event_type"] == "mutually_exclusive"
    assert normalization["normalized"] is True
    assert normalization["reason"] in {"type", "sum_guard"}
    assert math.isclose(normalization["total_after"], 100.0, rel_tol=1e-6)
