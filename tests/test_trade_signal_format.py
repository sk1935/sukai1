"""
Test Trade Signal Formatting

Tests:
- OutputFormatter includes trade signal section with correct fields
- Normalization banner only appears when sum guard triggers
- Trade signal fields are properly formatted
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from output_formatter import OutputFormatter


def test_trade_signal_format_single_option():
    """Test trade signal formatting for single-option events"""
    formatter = OutputFormatter()
    
    # Mock fusion_result with trade signal data
    fusion_result = {
        "final_prob": 65.0,
        "model_only_prob": 60.0,
        "uncertainty": 5.0,
        "summary": "Test summary",
        "disagreement": "低",
        "ev": 0.08,
        "annualized_ev": 0.35,
        "risk_factor": 0.42,
        "signal": "BUY",
        "signal_reason": "Positive EV (0.35) with low risk (0.42)"
    }
    
    event_data = {
        "question": "Test Event",
        "market_prob": 50.0,
        "rules": "Test rules",
        "days_left": 30
    }
    
    trade_signal_data = {
        "ev": 0.08,
        "annualized_ev": 0.35,
        "risk_factor": 0.42,
        "signal": "BUY",
        "signal_reason": "Positive EV (0.35) with low risk (0.42)"
    }
    
    output = formatter.format_prediction(
        event_data=event_data,
        fusion_result=fusion_result,
        trade_signal=trade_signal_data
    )
    
    # Assertions
    assert "💰 BUY" in output, "BUY signal line should be present"
    assert "EV:" in output, "EV label should be present"
    assert "Annualized EV" in output, "Annualized EV line should be present"
    assert "Risk:" in output, "Risk line should be present"
    assert "Reason:" in output, "Reason line should be present"
    assert "Trade Signal unavailable" not in output, "Trade signal should not fall back to unavailable"
    
    print("✅ Single-option trade signal formatting test passed")


def test_trade_signal_format_multi_option():
    """Test trade signal formatting for multi-option events"""
    formatter = OutputFormatter()
    
    event_data = {
        "question": "Test Multi-Option Event",
        "rules": "Test rules",
        "days_left": 30
    }
    
    outcomes = [
        {
            "name": "Option A",
            "model_only_prob": 60.0,
            "market_prob": 50.0,
            "prediction": 58.0,
            "uncertainty": 5.0,
            "summary": "Test summary for option A"
        },
        {
            "name": "Option B",
            "model_only_prob": 40.0,
            "market_prob": 50.0,
            "prediction": 42.0,
            "uncertainty": 5.0,
            "summary": "Test summary for option B"
        }
    ]
    
    normalization_info = {
        "event_type": "mutually_exclusive",
        "normalized": True,
        "total_before": 100.0,
        "total_after": 100.0,
        "normalization_reason": "ok"
    }
    
    trade_signal_info = {
        "option": "Option A",
        "data": {
            "ev": 0.10,
            "annualized_ev": 0.40,
            "risk_factor": 0.38,
            "signal": "BUY",
            "signal_reason": "Positive EV with low risk"
        }
    }
    
    output = formatter.format_multi_option_prediction(
        event_data=event_data,
        outcomes=outcomes,
        normalization_info=normalization_info,
        fusion_result={},
        trade_signal=trade_signal_info
    )
    
    # Assertions
    assert "💰 BUY" in output, "BUY signal should be present in banner"
    assert "EV:" in output and "Annualized EV" in output, "Metric lines should be present"
    assert "Reason:" in output, "Reason line should be included"
    
    print("✅ Multi-option trade signal formatting test passed")


def test_normalization_banner_guard():
    """Test that normalization banner only appears when sum guard triggers"""
    formatter = OutputFormatter()
    
    # Test case 1: Sum guard NOT triggered (sum in range [0.95, 1.05])
    norm_info_ok = {
        "event_type": "mutually_exclusive",
        "normalized": True,
        "total_before": 98.0,  # 0.98, in range
        "total_after": 100.0,
        "reason": "type",
        "normalization_reason": "ok"
    }
    
    banner_ok = formatter._build_normalization_banner(norm_info_ok)
    assert "安全归一化已启用" not in banner_ok, "Banner should NOT show for normal normalization"
    
    # Test case 2: Sum guard triggered (sum < 0.95)
    norm_info_guard_low = {
        "event_type": "mutually_exclusive",
        "normalized": True,
        "total_before": 85.0,  # 0.85, below threshold
        "total_after": 100.0,
        "reason": "sum_guard",
        "normalization_reason": "sum_guard_scaled"
    }
    
    banner_guard_low = formatter._build_normalization_banner(norm_info_guard_low)
    assert "安全归一化已启用" in banner_guard_low, "Banner SHOULD show for sum guard (low)"
    
    # Test case 3: Sum guard triggered (sum > 1.05)
    norm_info_guard_high = {
        "event_type": "mutually_exclusive",
        "normalized": True,
        "total_before": 120.0,  # 1.20, above threshold
        "total_after": 100.0,
        "reason": "sum_guard",
        "normalization_reason": "sum_guard_scaled"
    }
    
    banner_guard_high = formatter._build_normalization_banner(norm_info_guard_high)
    assert "安全归一化已启用" in banner_guard_high, "Banner SHOULD show for sum guard (high)"
    
    print("✅ Normalization banner guard test passed")


def test_trade_signal_none_values():
    """Trade signal banner should fall back when inputs are missing"""
    formatter = OutputFormatter()

    trade_signal_none = {
        "ev": None,
        "annualized_ev": None,
        "risk_factor": None,
        "signal": "HOLD",
        "signal_reason": None
    }

    banner = formatter._build_trade_signal_banner(trade_signal_none)
    # [FIX] Banner now skips entirely when inputs are incomplete.
    assert banner == ""

    print("✅ Trade signal fallback test passed")


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Trade Signal Format Tests")
    print("=" * 60)
    
    try:
        test_trade_signal_format_single_option()
        test_trade_signal_format_multi_option()
        test_normalization_banner_guard()
        test_trade_signal_none_values()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


