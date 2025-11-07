import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from event_manager import Event  # noqa: E402
from model_orchestrator import ModelOutput  # noqa: E402
from fusion_engine import FusionResult  # noqa: E402


def test_event_model_probability_clamp():
    evt = Event(question="Test event", market_prob=150.0)
    assert evt.market_prob == 100.0
    evt2 = Event(question="Another", market_prob=None)
    assert evt2.market_prob == 0.0


def test_model_output_confidence_defaults():
    output = ModelOutput(probability=42.0, confidence="UNKNOWN", reasoning="text")
    assert output.confidence == "medium"
    sanitized = ModelOutput(probability=42.0, reasoning="text")
    assert sanitized.probability == 42.0


def test_fusion_result_defaults():
    result = FusionResult(final_prob=55.0, summary="done")
    assert result.fusion_weights["model_weight"] == 1.0
    assert result.total_weight == 0.0
    assert result.final_prob == 55.0
