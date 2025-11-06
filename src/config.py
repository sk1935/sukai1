"""Central configuration module for Polymarket AI Predictor.

This module centralizes constants such as fusion weights, calibration
parameters, trade signal thresholds, and model-specific settings. It also
provides lightweight environment handling so different deployments (dev/test/prod)
can share the same code base with different configuration values.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Any


def _env(name: str, default: str) -> str:
    """Fetch environment variable with fallback."""
    return os.getenv(name, default)


APP_ENV = _env("APP_ENV", "development").lower()


@dataclass
class ModelConfig:
    """Configuration for an individual model/provider."""

    model_id: str
    api_key_env: str
    enabled: bool = True
    timeout: float = 30.0
    max_tokens: int = 1200
    temperature: float = 0.7
    extra_params: Dict[str, Any] = field(default_factory=dict)

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")


@dataclass
class FusionConfig:
    """Weights and calibration knobs for fusion layer."""

    model_weight: float = float(_env("FUSION_MODEL_WEIGHT", "0.75"))
    market_weight: float = float(_env("FUSION_MARKET_WEIGHT", "0.25"))
    min_model_weight: float = 0.55
    max_model_weight: float = 0.9
    confidence_weights: Dict[str, float] = field(
        default_factory=lambda: {"low": 1.0, "medium": 2.0, "high": 3.0}
    )
    calibration_params: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            "gpt-4o": {"A": -1.15, "B": 0.25},
            "claude-3-7-sonnet-latest": {"A": -1.05, "B": 0.18},
            "gemini-2.5-pro": {"A": -0.95, "B": 0.10},
            "grok-4": {"A": -1.20, "B": 0.35},
            "deepseek-chat": {"A": -0.85, "B": 0.05},
            "default": {"A": 0.0, "B": 0.0},
        }
    )


@dataclass
class TradeSignalConfig:
    base_edge_threshold: float = float(_env("TRADE_EDGE_THRESHOLD", "0.03"))
    slippage_cost: float = float(_env("TRADE_SLIPPAGE", "0.02"))
    fee_cost: float = float(_env("TRADE_FEE", "0.01"))
    high_risk_threshold: float = float(_env("TRADE_HIGH_RISK", "0.95"))


@dataclass
class AppConfig:
    env: str
    fusion: FusionConfig
    trade: TradeSignalConfig
    model_settings: Dict[str, ModelConfig]

    def enabled_models(self) -> Dict[str, ModelConfig]:
        return {k: v for k, v in self.model_settings.items() if v.enabled}


def _base_model_settings() -> Dict[str, ModelConfig]:
    return {
        "gpt-4o": ModelConfig("gpt-4o", "AICANAPI_KEY", timeout=35.0),
        "claude-3-7-sonnet-latest": ModelConfig(
            "claude-3-7-sonnet-latest", "AICANAPI_KEY", timeout=50.0
        ),
        "gemini-2.5-pro": ModelConfig("gemini-2.5-pro", "AICANAPI_KEY", timeout=45.0),
        "deepseek-chat": ModelConfig("deepseek-chat", "DEEPSEEK_API_KEY", timeout=40.0),
        "grok-4": ModelConfig("grok-4", "XAI_API_KEY", timeout=60.0),
    }


def _apply_env_overrides(settings: Dict[str, ModelConfig]) -> None:
    if APP_ENV == "testing":
        for cfg in settings.values():
            cfg.temperature = 0.0
            cfg.enabled = cfg.model_id in {"gpt-4o", "claude-3-7-sonnet-latest"}
    elif APP_ENV == "production":
        for cfg in settings.values():
            cfg.timeout += 5
    # development keeps defaults


def load_app_config() -> AppConfig:
    fusion = FusionConfig()
    trade = TradeSignalConfig()
    model_settings = _base_model_settings()
    _apply_env_overrides(model_settings)
    return AppConfig(env=APP_ENV, fusion=fusion, trade=trade, model_settings=model_settings)


APP_CONFIG = load_app_config()
