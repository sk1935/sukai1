"""
融合层（Fusion Engine）：
根据 OPTIMIZATION_NOTES.md 的五层架构设计

职责：
- 对不同模型的预测进行加权融合
- 计算 AI 共识概率与市场概率的融合结果（80% AI + 20% 市场）
- 生成简短的"AI共识观点总结"（中文）
- 评估模型间的分歧程度
- 从 LMArena.ai 基础权重配置文件加载模型权重

输入：各模型的预测结果 {probability, confidence, reasoning}
输出：融合后的预测 {final_prob, model_only_prob, uncertainty, summary, disagreement}
"""
import json
import math
import time
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ValidationError, ConfigDict

from src.utils.safe_math import to_float, safe_mul, safe_add


class FusionResult(BaseModel):
    """Structured fusion output returned to higher layers."""

    model_config = ConfigDict(extra="allow")

    final_prob: float = Field(default=0.0)
    model_only_prob: Optional[float] = None
    uncertainty: float = Field(default=0.0, ge=0.0)
    summary: str = Field(default="")
    finalized_summary_text: str = Field(default="")
    disagreement: str = Field(default="未知")
    model_count: int = Field(default=0, ge=0)
    deepseek_reasoning: Optional[str] = None
    model_versions: Dict[str, Any] = Field(default_factory=dict)
    weight_source: Dict[str, Any] = Field(default_factory=dict)
    model_confidence_factor: float = Field(default=0.0)
    fusion_weights: Dict[str, float] = Field(default_factory=lambda: {"model_weight": 1.0, "market_weight": 0.0})
    total_weight: float = Field(default=0.0)
    risk_factor: Optional[float] = None

class FusionEngine:
    """
    Fuses multiple model predictions with weighted averaging.
    
    融合多个模型的预测结果：
    - 使用模型权重和置信度权重计算加权平均
    - 将AI共识（80%）与市场概率（20%）融合
    - 生成中文摘要
    - 评估分歧程度
    - 从 LMArena.ai 配置文件加载基础权重
    """
    
    CONFIDENCE_WEIGHTS = {
        "low": 1.0,
        "medium": 2.0,
        "high": 3.0
    }
    
    MARKET_WEIGHT = 0.2  # Legacy default
    MODEL_WEIGHT = 0.8   # Legacy default
    MIN_MODEL_WEIGHT = 0.55
    MAX_MODEL_WEIGHT = 0.9
    
    # Model name mapping: actual model_id -> LMArena config key
    MODEL_NAME_MAPPING = {
        "gpt-4o": "gpt-4o-latest",
        "claude-3-7-sonnet-latest": "claude-opus-4-1",  # Map to closest match
        "claude-3-5-opus-latest": "claude-opus-4-1",
        "gemini-2.5-pro": "gemini-2.5-pro",
        "gemini-2.5-flash": "gemini-2.5-pro",  # Fallback to pro if flash not found
        "grok-4": "grok-4-fast",
        "grok-3": "grok-4-fast",  # Fallback
        "deepseek-chat": "deepseek-v3.2-exp"
    }
    
    def __init__(self, experiment_config=None):
        """
        Initialize FusionEngine and load LMArena base weights.
        
        Args:
            experiment_config: Optional ExperimentConfig instance for ablation studies
        """
        self.lmarena_config = self._load_lmarena_config()
        self.base_weights = self.lmarena_config.get("weights", {})
        self.metadata = self.lmarena_config.get("metadata", {})
        self.fusion_config = self.lmarena_config.get("fusion", {})
        
        # Experiment configuration (for ablation studies)
        self.experiment_config = experiment_config
        
        # Update confidence weights from config if available
        if "default_confidence_multiplier" in self.fusion_config:
            self.CONFIDENCE_WEIGHTS.update(self.fusion_config["default_confidence_multiplier"])
        
        # Log weights on initialization
        self._log_base_weights()
        
        # Calibration state (for binning/platt calibration)
        self.calibration_map = None  # Will be fitted during calibration
    
    def _load_lmarena_config(self) -> Dict:
        """Load base weights from LMArena configuration file."""
        config_path = Path(__file__).parent.parent / "config" / "base_weights_lmarena.json"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except FileNotFoundError:
            print(f"⚠️ LMArena权重配置文件未找到: {config_path}")
            print("   使用默认权重配置...")
            return {
                "metadata": {"source": "默认配置", "updated_at": "未知"},
                "weights": {},
                "fusion": {}
            }
        except json.JSONDecodeError as e:
            print(f"⚠️ LMArena权重配置文件解析错误: {e}")
            print("   使用默认权重配置...")
            return {
                "metadata": {"source": "默认配置", "updated_at": "未知"},
                "weights": {},
                "fusion": {}
            }
    
    def _log_base_weights(self):
        """Log base weights information on startup."""
        source = self.metadata.get("source", "未知来源")
        updated_at = self.metadata.get("updated_at", "未知")
        
        print(f"📊 模型基础权重来源：{source}")
        
        # Collect weight info for active models
        weight_info = []
        for model_key, config in self.base_weights.items():
            base_weight = config.get("base_weight", 1.0) or 0.0
            # 【防御】确保 base_weight 不为 None
            if base_weight is None:
                print(f"⚠️ base_weight is None for {model_key}, using default 0.0")
                base_weight = 0.0
            # Find display name (simplified)
            if "gemini" in model_key:
                weight_info.append(f"Gemini {(base_weight or 0.0):.2f}")
            elif "claude" in model_key:
                weight_info.append(f"Claude {(base_weight or 0.0):.2f}")
            elif "gpt" in model_key:
                weight_info.append(f"GPT-4o {(base_weight or 0.0):.2f}")
            elif "grok" in model_key:
                weight_info.append(f"Grok {(base_weight or 0.0):.2f}")
            elif "deepseek" in model_key:
                weight_info.append(f"DeepSeek {(base_weight or 0.0):.2f}")
        
        if weight_info:
            print(" / ".join(weight_info))
        else:
            print("未加载到权重配置")
    
    def _get_base_weight(self, model_name: str) -> float:
        """
        Get base weight for a model from LMArena config.
        
        Args:
            model_name: Actual model ID used in the system
            
        Returns:
            Base weight from LMArena config, or 1.0 if not found
        """
        # Map model name to LMArena config key
        lmarena_key = self.MODEL_NAME_MAPPING.get(model_name, model_name)
        
        # Try exact match first
        if lmarena_key in self.base_weights:
            return self.base_weights[lmarena_key].get("base_weight", 1.0)
        
        # Try partial match (e.g., "claude-3-7-sonnet" might match "claude-opus-4-1")
        for key, config in self.base_weights.items():
            if model_name in key or key in model_name:
                return config.get("base_weight", 1.0)
        
        # Fallback: return 1.0
        return 1.0
    
    def fuse_predictions(
        self,
        model_results: Dict[str, Optional[Dict]],
        model_weights: Dict[str, float],
        market_prob: float,
        orchestrator=None  # Optional: pass orchestrator instance to avoid creating new one
    ) -> Dict:
        """
        Fuse predictions from multiple models.
        
        Args:
            model_results: Dict mapping model_name -> {probability, confidence, reasoning}
            model_weights: Dict mapping model_name -> weight
            market_prob: Market probability from Polymarket
        
        Returns:
            Dict with final_prob, uncertainty, summary, disagreement
        """
        start_time = time.time()
        print(f"[DEBUG] ========== fuse_predictions START ==========")
        print(f"[DEBUG] Model results count: {len(model_results)}")
        print(f"[DEBUG] Market prob: {market_prob}")
        market_prob_raw = market_prob
        market_prob = to_float(market_prob, 0.0)  # 防止 NoneType 导致 TypeError
        market_prob_missing = market_prob_raw is None
        # Filter out None results
        valid_results = {
            name: result
            for name, result in model_results.items()
            if result is not None
        }
        
        if not valid_results:
            # Fallback if no models responded
            return {
                "final_prob": market_prob,
                "model_only_prob": None,  # No model prediction available
                "uncertainty": 10.0,
                "summary": "没有可用的模型响应。使用市场概率。",
                "disagreement": "高",
                "model_count": 0
            }
        
        # Calculate weighted probabilities
        probabilities: List[float] = []
        weights: List[float] = []
        reasonings = []
        confidence_factors: List[float] = []
        deepseek_reasoning = None  # Store DeepSeek's reasoning separately
        
        for model_name, result in valid_results.items():
            prob = self._safe_float(result.get("probability"))
            confidence = result.get("confidence")
            if confidence not in self.CONFIDENCE_WEIGHTS:
                print("[fuse_predictions] missing confidence, defaulting to 'medium'")
                confidence = "medium"
            reasoning = self._combine_reasonings(result)
            
            # Use LMArena base weight instead of model_weights parameter
            base_weight = self._get_base_weight(model_name)
            confidence_weight = self.CONFIDENCE_WEIGHTS.get(confidence, 2.0)
            confidence_factor = self._compute_model_confidence_factor(model_name, base_weight, confidence_weight, result)
            base_component = to_float(base_weight, 0.0)
            confidence_component = to_float(confidence_weight, 1.0) or 1.0  # 防止 NoneType 导致 TypeError
            confidence_factor_value = to_float(confidence_factor, 0.0)
            blend_component = 0.5 + confidence_factor_value / 2.0
            if confidence_factor is None:
                print("[fuse_predictions] blend_component is None, defaulting to 1.0")
                blend_component = 1.0
            total_weight = safe_mul(
                safe_mul(base_component, confidence_component),
                blend_component
            )
            
            probabilities.append(prob)
            weights.append(to_float(total_weight, 0.0))
            # Only add reasoning, not model name
            reasonings.append(reasoning)
            confidence_factors.append(confidence_factor_value)
            
            # Extract DeepSeek reasoning separately
            if model_name == "deepseek-chat":
                deepseek_reasoning = reasoning
        
        # Weighted mean / variance without numpy (防止 numpy 导入导致崩溃)
        weighted_mean = self._weighted_mean(probabilities, weights)
        uncertainty = self._weighted_std(probabilities, weights, weighted_mean)
        
        # Apply consensus coefficient if enabled
        if self._should_use_consensus_coef():
            consensus_weight = weighted_mean
        else:
            # If consensus_coef is disabled, use simple average
            consensus_weight = self._mean(probabilities)
        
        # Combine with market probability (if market_bias enabled)
        if self._should_use_market_bias():
            if market_prob_missing:
                print("[fuse_predictions] market_prob is None, falling back to AI-only weights")
                dynamic_model_weight = 1.0
                dynamic_market_weight = 0.0
                final_prob = consensus_weight
            else:
                avg_conf_factor = self._mean(confidence_factors) if confidence_factors else 0.5
                dynamic_model_weight, dynamic_market_weight = self._compute_dynamic_fusion_weights(
                    avg_conf_factor,
                    uncertainty,
                    market_prob
                )
                final_prob = safe_add(
                    safe_mul(dynamic_model_weight, consensus_weight),
                    safe_mul(dynamic_market_weight, market_prob)
                )
        else:
            dynamic_model_weight = 1.0
            dynamic_market_weight = 0.0
            final_prob = consensus_weight
        
        # Apply de-marketization penalty (if enabled)
        demarket_applied = False
        if self._should_use_demarket_penalty():
            penalty_result = self._apply_demarket_penalty(
                final_prob, consensus_weight, market_prob, valid_results
            )
            if penalty_result:
                final_prob = penalty_result["adjusted_prob"]
                demarket_applied = True
        
        # Apply post-calibration if enabled
        calibration_applied = False
        calibration_method = self._get_calibration_method()
        if calibration_method and calibration_method != "none":
            calibrated_prob = self._apply_calibration(final_prob, calibration_method)
            if calibrated_prob is not None:
                final_prob = calibrated_prob
                calibration_applied = True
        
        # Calculate disagreement level
        disagreement = self._calculate_disagreement(probabilities, uncertainty)
        
        # Generate summary
        summary = self._generate_summary(reasonings, consensus_weight, market_prob)
        # Bugfix: ensure finalized_summary_text always exists to avoid NameError downstream
        finalized_summary_text = summary or ""
        if not finalized_summary_text.strip():
            finalized_summary_text = "暂无详细推理信息。"
        assert isinstance(finalized_summary_text, str), "finalized_summary_text must be a string"
        
        # Add weight source information
        weight_source = {
            "file": "base_weights_lmarena.json",
            "source": self.metadata.get("source", "未知"),
            "updated_at": self.metadata.get("updated_at", "未知")
        }
        
        result = {
            "final_prob": round(final_prob, 2),
            "model_only_prob": round(consensus_weight, 2),  # Pure model prediction before market fusion
            "uncertainty": round(uncertainty, 2),
            "summary": summary,
            "finalized_summary_text": finalized_summary_text,
            "disagreement": disagreement,
            "model_count": len(valid_results),
            "deepseek_reasoning": deepseek_reasoning,  # DeepSeek's reasoning for separate display
            "model_versions": self._get_model_versions(valid_results, orchestrator),  # Add model versions info
            "weight_source": weight_source,  # Add weight source info
            "model_confidence_factor": round(self._mean(confidence_factors) if confidence_factors else 0.5, 3),
            "fusion_weights": {
                "model_weight": round(dynamic_model_weight, 3),
                "market_weight": round(dynamic_market_weight, 3)
            },
            "total_weight": float(sum(weights)) if weights else 0.0
        }
        
        # Add experiment flags if applicable
        if demarket_applied:
            result["demarket_applied"] = True
            result["demarket_note"] = "Applied de-marketization penalty to avoid pure tracking."
        if calibration_applied:
            result["calibration_applied"] = True
            result["calibration_method"] = calibration_method
        
        total_time = time.time() - start_time
        # 【防御】确保 total_time 不为 None
        total_time = total_time or 0.0
        if total_time is None:
            print("⚠️ total_time is None, using default 0.0")
            total_time = 0.0
        print(f"[DEBUG] Total model fusion time: {(total_time or 0.0):.2f}s")
        print(f"[DEBUG] ========== fuse_predictions END ==========")
        
        try:
            fusion_model = FusionResult(**result)
            return fusion_model.model_dump()
        except ValidationError as exc:
            print(f"[FusionEngine] FusionResult validation failed: {exc}")
            return result
    
    def _get_model_versions(self, model_results: Dict[str, Optional[Dict]], orchestrator=None) -> Dict[str, Dict]:
        """Get model version information from ModelOrchestrator."""
        try:
            # Use provided orchestrator if available, otherwise create a new one
            if orchestrator is None:
                from src.model_orchestrator import ModelOrchestrator
                orchestrator = ModelOrchestrator()
            
            versions = {}
            for model_name in model_results.keys():
                if model_results[model_name] is not None:  # Only for successful calls
                    info = orchestrator.get_model_info(model_name)
                    if info:
                        versions[model_name] = {
                            "display_name": info["display_name"],
                            "last_updated": info.get("last_updated", "未知")
                        }
            
            return versions
        except Exception as e:
            print(f"⚠️ 获取模型版本信息失败: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _calculate_disagreement(self, probabilities: List[float], uncertainty: float) -> str:
        """Calculate disagreement level based on uncertainty."""
        # Handle edge case: single model or zero uncertainty
        if len(probabilities) <= 1 or uncertainty == 0.0:
            return "低"
        elif uncertainty < 3.0:
            return "低"
        elif uncertainty < 8.0:
            return "中"
        else:
            return "高"
    
    def _generate_summary(self, reasonings: List[str], model_prob: float, market_prob: float) -> str:
        """
        Generate a brief summary from model reasonings.
        优化：确保生成的摘要更简洁，突出关键观点，且为中文。
        """
        if not reasonings:
            return "暂无详细推理信息。"
        
        # Combine first few reasonings (already cleaned, no model names)
        # 优先使用前2个模型的推理，如果都是中文则直接合并
        summary_parts = reasonings[:2]  # Use first 2 models' reasoning
        
        # 检查是否包含中文字符
        has_chinese = any(any('\u4e00' <= char <= '\u9fff' for char in part) for part in summary_parts)
        
        if has_chinese:
            # 如果包含中文，直接合并
            summary = " ".join(summary_parts)
        else:
            # 如果都是英文，添加提示说明这是英文推理
            # 实际使用中，由于prompt要求中文，这里应该不会触发
            summary = "模型推理：" + " ".join(summary_parts)
        
        # Truncate if too long (保持简洁)
        summary = self._safe_shorten_text(summary, limit=800)

        return summary

    def _combine_reasonings(self, result: Dict) -> str:
        pieces = []
        for key in ("reasoning_short", "reasoning_long", "reasoning"):
            value = result.get(key)
            if value:
                cleaned = self._sanitize_reasoning_fragment(value, context=f"fusion_{key}")
                cleaned = cleaned.replace("Parsed from unstructured response.", "").replace("Parsed from unstructured response", "").strip()
                if cleaned:
                    pieces.append(cleaned)
        combined = " ".join(pieces).strip()
        if not combined:
            combined = "暂无详细推理信息。"
        combined = self._safe_shorten_text(combined, limit=800)
        print(f"[COMBINE] reasoning_merged (final_len={len(combined)})")
        return combined

    @staticmethod
    def _sanitize_reasoning_fragment(
        value: Optional[Union[str, Dict[str, Any], List[Any]]],
        context: str = "fusion"
    ) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            try:
                cleaned = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                cleaned = str(value)
        else:
            cleaned = str(value)
        original = cleaned
        changed = False
        fence_pattern = re.compile(r"```(?:json)?[\s\S]*?```", re.IGNORECASE)
        new_cleaned = fence_pattern.sub("", cleaned)
        if new_cleaned != cleaned:
            cleaned = new_cleaned
            changed = True
        json_pattern = re.compile(r"\{[^{}]*:[^{}]*\}")
        while True:
            new_cleaned = json_pattern.sub("", cleaned)
            if new_cleaned == cleaned:
                break
            cleaned = new_cleaned
            changed = True
        if cleaned.count("{") > cleaned.count("}"):
            idx = cleaned.rfind("{")
            if idx != -1:
                cleaned = cleaned[:idx]
                changed = True
        cleaned = cleaned.replace("```", "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and cleaned[-1] in "{[,:":
            terminators = [cleaned.rfind(ch) for ch in "。！？.!?"]
            terminators = [idx for idx in terminators if idx != -1]
            if terminators:
                cleaned = cleaned[: max(terminators) + 1]
                changed = True
        if changed and cleaned != original:
            print(f"[CLEANUP] Removed JSON artifacts ({context})")
        return cleaned
    
    @staticmethod
    def classify_multi_option_event(
        event_title: str,
        outcomes: List[Dict],
        event_rules: str = "",
        now_probs: Optional[List[float]] = None
    ) -> str:
        """Use layered signals to classify multi-option events."""
        if not outcomes:
            return "hybrid"

        event_title_lower = (event_title or "").lower()
        rules_lower = (event_rules or "").lower()
        option_names = [
            (outcome.get("name") or "").strip().lower()
            for outcome in outcomes
            if outcome.get("name")
        ]
        now_prob_values = now_probs or [
            outcome.get("market_prob")
            for outcome in outcomes
            if outcome.get("market_prob") is not None
        ]
        now_prob_values = [p for p in now_prob_values if p is not None]
        sum_market_fraction = None
        if now_prob_values:
            max_prob = max(now_prob_values)
            divisor = 100.0 if max_prob and max_prob > 1 else 1.0
            if divisor:
                sum_market_fraction = sum(now_prob_values) / divisor

        def log_decision(decision_type: str, source: str) -> str:
            extra = ""
            if sum_market_fraction is not None:
                extra = f" sum_market={sum_market_fraction:.3f}"
            print(f"[CLASSIFY] type={decision_type} source={source}{extra}")
            return decision_type

        # Signal 1: Rules pattern
        if rules_lower:
            mutually_patterns = [
                r"exactly one", r"only one", r"upper bound of the target federal funds range",
                r"wins the", r"which candidate", r"which party"
            ]
            conditional_patterns = [
                r"each option resolves", r"per contract", r"per date", r"resolves independently",
                r"for each date", r"multiple settlement"
            ]
            if any(re.search(pattern, rules_lower) for pattern in mutually_patterns):
                return log_decision("mutually_exclusive", "rules")
            if any(re.search(pattern, rules_lower) for pattern in conditional_patterns):
                return log_decision("conditional", "rules")

        # Signal 2: Option-set lexicon
        def _matches(name: str, keywords: List[str]) -> bool:
            return any(keyword in name for keyword in keywords)

        rate_keywords = ["bps", "basis points", "increase", "decrease", "no change", "cut", "hike"]
        candidate_keywords = ["trump", "biden", "harris", "newsom", "candidate", "party", "democrat", "republican"]
        if option_names:
            rate_ratio = sum(1 for name in option_names if _matches(name, rate_keywords)) / len(option_names)
            candidate_ratio = sum(1 for name in option_names if _matches(name, candidate_keywords)) / len(option_names)
            if rate_ratio >= 0.7:
                return log_decision("mutually_exclusive", "option_set_rate")
            if candidate_ratio >= 0.6:
                return log_decision("mutually_exclusive", "option_set_candidate")

        # Signal 3: Date buckets from option names
        date_patterns = [
            r'\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?',
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}',
            r'\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*'
        ]
        if option_names:
            date_hits = sum(1 for name in option_names if any(re.search(pattern, name) for pattern in date_patterns))
            if date_hits / len(option_names) >= 0.5:
                return log_decision("conditional", "date_bucket")

        # Signal 4: Sum-of-probabilities window
        if sum_market_fraction is not None and 0.95 <= sum_market_fraction <= 1.05:
            return log_decision("mutually_exclusive", "sum_window")

        # Signal 5: Structure hints
        structure_mutual_keywords = ["who will", "which of", "candidate", "federal funds", "champion"]
        structure_conditional_keywords = ["per day", "per date", "each day", "per outcome", "range"]
        if any(keyword in event_title_lower for keyword in structure_mutual_keywords):
            return log_decision("mutually_exclusive", "structure_title")
        if rules_lower and any(keyword in rules_lower for keyword in structure_conditional_keywords):
            return log_decision("conditional", "structure_rules")

        # Fallback heuristic
        price_patterns = [
            r'price\s+(above|below|over|under|at least|at most)\s+',
            r'\$\d+',
            r'\d+\s*(million|billion|trillion|k|m|b)\s*(usd|eur|€|¥)?',
        ]
        if any(re.search(pattern, event_title_lower, re.IGNORECASE) for pattern in price_patterns):
            return log_decision("conditional", "fallback_price")

        conditional_keywords = {
            "time": [
                "oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                "october", "november", "december", "january", "february", "march", "april",
                "june", "july", "august", "september",
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                "mon", "tue", "wed", "thu", "fri", "sat", "sun",
                "2024", "2025", "2026", "2027", "2028", "2029", "2030",
                "day", "month", "year", "q1", "q2", "q3", "q4", "h1", "h2",
                "before", "after", "by", "until", "deadline",
                r'\d{1,2}[/-]\d{1,2}',
                r'\d{1,2}[/-]\d{1,2}[/-]\d{4}',
            ]
        }
        conditional_score = 0
        for keywords in conditional_keywords.values():
            for kw in keywords:
                if isinstance(kw, str) and kw in event_title_lower:
                    conditional_score += 2
                elif isinstance(kw, str) and kw.startswith('\\') and re.search(kw, event_title_lower):
                    conditional_score += 2
        if conditional_score >= 2:
            return log_decision("conditional", "fallback_title")

        return log_decision("mutually_exclusive", "fallback_default")

    @staticmethod
    def filter_invalid_outcomes(outcomes: List[Dict]) -> List[Dict]:
        """
        自动跳过已过期或无效的子市场。
        
        过滤规则：
        - 时间型：日期早于当前 UTC 日期
        - 价格型：条件逻辑无效（如 "above 1000000%"）
        - 其他无效项：重复或空标题
        
        Args:
            outcomes: 选项列表
        
        Returns:
            过滤后的有效选项列表
        """
        if not outcomes:
            return []
        
        valid_outcomes = []
        seen_names = set()
        now_utc = datetime.now(timezone.utc)
        
        # 日期模式匹配
        date_patterns = [
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # MM/DD/YYYY or DD/MM/YYYY
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2}),?\s+(\d{4})',  # Month DD, YYYY
            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY/MM/DD
        ]
        
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        
        for outcome in outcomes:
            name = outcome.get('name', '').strip()
            
            # 过滤空标题
            if not name:
                continue
            
            # 过滤重复项
            name_normalized = name.lower().strip()
            if name_normalized in seen_names:
                print(f"[DEBUG] 跳过重复选项: {name}")
                continue
            seen_names.add(name_normalized)
            
            # 尝试解析日期（时间型选项）
            is_expired = False
            name_lower = name.lower()
            
            for pattern in date_patterns:
                match = re.search(pattern, name_lower, re.IGNORECASE)
                if match:
                    try:
                        if 'jan' in name_lower or 'feb' in name_lower:  # 月份名称格式
                            month_name = match.group(1).lower()[:3]
                            day = int(match.group(2))
                            year = int(match.group(3))
                            month = month_map.get(month_name)
                            if month:
                                option_date = datetime(year, month, day, tzinfo=timezone.utc)
                                if option_date < now_utc:
                                    is_expired = True
                                    print(f"[DEBUG] 跳过过期选项: {name} (日期: {option_date.date()})")
                        else:  # 数字格式日期
                            parts = match.groups()
                            if len(parts) == 3:
                                # 尝试不同的日期格式
                                try:
                                    # MM/DD/YYYY
                                    month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                                    if month <= 12 and day <= 31:
                                        option_date = datetime(year, month, day, tzinfo=timezone.utc)
                                        if option_date < now_utc:
                                            is_expired = True
                                            print(f"[DEBUG] 跳过过期选项: {name} (日期: {option_date.date()})")
                                except:
                                    try:
                                        # DD/MM/YYYY
                                        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                                        if month <= 12 and day <= 31:
                                            option_date = datetime(year, month, day, tzinfo=timezone.utc)
                                            if option_date < now_utc:
                                                is_expired = True
                                                print(f"[DEBUG] 跳过过期选项: {name} (日期: {option_date.date()})")
                                    except:
                                        pass
                    except:
                        pass
                    break
            
            if is_expired:
                continue
            
            # 过滤无效价格条件（如 "above 1000000%" 这种明显不合理的情况）
            if '%' in name or '$' in name or 'usd' in name_lower:
                # 检查是否有极端数值
                numbers = re.findall(r'[\d,]+\.?\d*', name)
                for num_str in numbers:
                    try:
                        num = float(num_str.replace(',', ''))
                        # 如果百分比超过 1000% 或价格超过合理范围，可能是无效选项
                        if '%' in name and num > 1000:
                            print(f"[DEBUG] 跳过无效价格选项: {name} (数值异常: {num}%)")
                            is_expired = True
                            break
                    except:
                        pass
            
            if is_expired:
                continue
            
            # 所有检查通过，添加有效选项
            valid_outcomes.append(outcome)
        
        if len(outcomes) != len(valid_outcomes):
            print(f"[DEBUG] 过滤无效选项: {len(outcomes)} → {len(valid_outcomes)}")
        
        return valid_outcomes
    
    @staticmethod
    def normalize_all_predictions(
        outcomes: List[Dict],
        event_title: str = "",
        event_rules: str = "",
        now_probabilities: Optional[List[float]] = None
    ) -> Dict:
        """
        对所有 outcome 的 AI 预测概率进行归一化，使其总和等于 100%。
        
        功能：
        1. 根据事件类型判断是否需要归一化（互斥事件归一化，条件事件不归一化）
        2. 过滤无效/过期选项
        3. 传入规则与最新市场报价，提升分类准确度
        4. 若 Σ(AI_probs) ≠ 100，按比例缩放；当 Σ(AI) 不在 [0.90, 1.10]，触发安全归一化
        5. 同时归一化不确定度（uncertainty），保持相对比例
        6. 处理异常值（>100 或 <0）自动裁剪至 [0,100]
        7. 容错处理：None 值使用回退方案（市场价格→均分）
        
        Args:
            outcomes: outcome 列表，包含 prediction / market_prob / model_only_prob 等字段
            event_title: 事件标题，用于判断事件类型
            event_rules: 市场规则文本
            now_probabilities: 最新市场报价列表（用于总和窗判断）
        
        Returns:
            Dict with:
                - "normalized_outcomes": List[Dict]
                - "total_before": float (归一化前的总和)
                - "total_after": float (归一化后的总和)
                - "error": float
                - "skipped_count": int
                - "normalized": bool
                - "event_type": str
                - "reason": Optional[str] ("type" | "sum_guard" | None)
        """
        if not outcomes or len(outcomes) == 0:
            return {
                "normalized_outcomes": [],
                "total_before": 0.0,
                "total_after": 0.0,
                "error": 0.0,
                "skipped_count": 0,
                "normalized": False,
                "event_type": "hybrid",
                "reason": None
            }
        
        # 【新增】过滤无效/过期选项
        filtered_outcomes = FusionEngine.filter_invalid_outcomes(outcomes)
        if len(filtered_outcomes) != len(outcomes):
            print(f"[DEBUG] 过滤后选项数量: {len(outcomes)} → {len(filtered_outcomes)}")
        
        # 【新增】识别事件类型
        if not event_title:
            print(f"[WARNING] event_title 为空，可能影响事件类型识别")
        derived_now_probs = now_probabilities or [
            outcome.get("market_prob")
            for outcome in filtered_outcomes
            if outcome.get("market_prob") is not None
        ]
        event_type = FusionEngine.classify_multi_option_event(
            event_title or "",
            filtered_outcomes,
            event_rules=event_rules,
            now_probs=derived_now_probs
        )
        print(f"[DEBUG] 最终事件类型: {event_type} (事件: {(event_title or '')[:50]}...)")
        
        # 【关键改进】根据事件类型决定是否归一化
        normalize_reason: Optional[str] = None
        should_normalize = (event_type == "mutually_exclusive")
        if should_normalize:
            normalize_reason = "type"

        # Sum guard：AI 总和超出 [0.9, 1.1] 强制归一化
        ai_values_for_guard = [
            outcome.get("model_only_prob")
            for outcome in filtered_outcomes
            if outcome.get("model_only_prob") is not None
        ]
        ai_sum_guard = sum(ai_values_for_guard) if ai_values_for_guard else 0.0
        guard_fraction = (ai_sum_guard / 100.0) if filtered_outcomes else None
        sum_guard_triggered = False
        if filtered_outcomes and guard_fraction is not None:
            if guard_fraction < 0.90 or guard_fraction > 1.10:
                should_normalize = True
                normalize_reason = "sum_guard"
                sum_guard_triggered = True
        if sum_guard_triggered:
            print(f"[FusionEngine] Sum guard triggered: ΣAI={guard_fraction:.3f}, 强制归一化。")
        
        if not should_normalize:
            # 条件事件或混合事件：不归一化，只添加 normalized 标记
            if event_type == "conditional":
                print(f"[FusionEngine] 条件事件检测到，跳过归一化。")
            
            marked_outcomes = []
            for outcome in filtered_outcomes:
                marked_outcome = outcome.copy()
                marked_outcome["normalized"] = False
                marked_outcomes.append(marked_outcome)
            
            # 计算总和（仅用于调试，不返回给输出层）
            total_before = sum(
                outcome.get("model_only_prob") or 0
                for outcome in filtered_outcomes
                if outcome.get("model_only_prob") is not None
            )
            
            return {
                "normalized_outcomes": marked_outcomes,
                "total_before": round(total_before, 2),
                "total_after": None,  # 【修复】条件事件不返回 total_after，表示不应显示归一化检查
                "error": 0.0,
                "skipped_count": len(outcomes) - len(filtered_outcomes),
                "normalized": False,
                "event_type": event_type,
                "reason": None,
                "normalization_reason": "ok"  # 条件事件不归一化，标记为 "ok"
            }
        
        # 互斥事件：执行归一化（原有逻辑）
        outcomes = filtered_outcomes  # 使用过滤后的选项
        
        # 提取所有有效的 AI 预测值（优先使用 model_only_prob，如果没有则尝试从 prediction 推算）
        valid_outcomes = []
        ai_probs = []
        uncertainties = []
        skipped_indices = []
        
        fallback_mode = normalize_reason == "sum_guard"
        equal_split_value = (100.0 / len(outcomes)) if outcomes else 0.0

        for i, outcome in enumerate(outcomes):
            ai_prob = outcome.get("model_only_prob")
            if ai_prob is None and fallback_mode:
                fallback_prob = outcome.get("market_prob")
                if fallback_prob is None:
                    fallback_prob = equal_split_value
                try:
                    ai_prob = float(fallback_prob)
                except (TypeError, ValueError):
                    ai_prob = equal_split_value
                print(f"[FusionEngine] Sum guard fallback使用 {'market_prob' if outcome.get('market_prob') is not None else 'equal-split'}: {outcome.get('name', i)} = {ai_prob:.2f}%")

            if ai_prob is None:
                skipped_indices.append(i)
                continue
            
            # 裁剪异常值到 [0, 100]
            ai_prob = max(0.0, min(100.0, float(ai_prob)))
            
            uncertainty = outcome.get("uncertainty", 0.0)
            if uncertainty is None:
                uncertainty = 0.0
            
            valid_outcomes.append(outcome)
            ai_probs.append(ai_prob)
            uncertainties.append(float(uncertainty))
        
        # 检查是否有有效数据
        if len(valid_outcomes) == 0:
            # 所有选项都无效，返回原数据
            return {
                "normalized_outcomes": outcomes,
                "total_before": 0.0,
                "total_after": 0.0,
                "error": 0.0,
                "skipped_count": len(outcomes),
                "event_type": event_type,
                "normalized": False,
                "reason": None
            }
        
        # 计算总和
        total_before = sum(ai_probs)
        
        # 【关键改进】互斥事件：归一化处理
        if total_before == 0:
            # 全为 0 的情况：均分（避免除零）
            normalized_probs = [100.0 / len(ai_probs)] * len(ai_probs)
            # 不确定度保持原值（已经是相对值）
            normalized_uncertainties = uncertainties
            total_after = 100.0
        else:
            # 按比例缩放
            scale_factor = 100.0 / total_before
            normalized_probs = [safe_mul(prob, scale_factor) for prob in ai_probs]
            
            # 归一化不确定度：保持相对比例，但需要相应缩放
            # 由于概率被缩放，不确定度也应该按相同比例缩放（保持相对关系）
            normalized_uncertainties = [safe_mul(unc, scale_factor) for unc in uncertainties]
            
            # 验证总和
            total_after = sum(normalized_probs)
        
        # 计算误差
        error = abs(total_after - 100.0)
        
        # 更新 outcomes
        normalized_outcomes = []
        valid_idx = 0
        
        # 【Bug修复】添加验证，确保 valid_idx 不会越界
        if len(normalized_probs) != len(ai_probs):
            print(f"⚠️ [WARNING] 归一化数组长度不匹配：normalized_probs={len(normalized_probs)}, ai_probs={len(ai_probs)}")
        
        for i, outcome in enumerate(outcomes):
            if i in skipped_indices:
                # 跳过的选项，保持原样（确保 model_only_prob 保持为 None）
                skipped_outcome = outcome.copy()
                # 【Bug修复】明确确保跳过的选项的 model_only_prob 为 None
                if skipped_outcome.get("model_only_prob") is not None:
                    print(f"[DEBUG] 跳过选项 {outcome.get('name', i)}，但 model_only_prob 不为 None，强制设为 None")
                skipped_outcome["model_only_prob"] = None
                normalized_outcomes.append(skipped_outcome)
            else:
                # 更新 AI 预测概率（需要同时更新 prediction，因为它是融合后的值）
                if valid_idx >= len(normalized_probs):
                    print(f"⚠️ [ERROR] valid_idx ({valid_idx}) >= normalized_probs 长度 ({len(normalized_probs)})")
                    # Fallback: 保持原样，但不更新 model_only_prob
                    normalized_outcomes.append(outcome.copy())
                else:
                    updated_outcome = outcome.copy()
                    
                    # 更新 model_only_prob（纯AI预测，归一化后的值）
                    normalized_value = round(normalized_probs[valid_idx], 2)
                    updated_outcome["model_only_prob"] = normalized_value
                    
                    # 【Bug修复】验证归一化值是否合理
                    if normalized_value < 0 or normalized_value > 100:
                        print(f"⚠️ [WARNING] 归一化值异常：{outcome.get('name', i)} = {normalized_value}%")
                    
                    # 更新 prediction（融合后的概率）：需要重新融合
                    market_prob = to_float(outcome.get("market_prob", 0.0), 0.0)  # 防止 NoneType 导致 TypeError
                    updated_prediction = safe_add(
                        safe_mul(FusionEngine.MODEL_WEIGHT, normalized_probs[valid_idx]),
                        safe_mul(FusionEngine.MARKET_WEIGHT, market_prob)
                    )
                    updated_outcome["prediction"] = round(updated_prediction, 2)
                    
                    # 更新不确定度
                    updated_outcome["uncertainty"] = round(normalized_uncertainties[valid_idx], 2)
                    
                    # 【新增】添加归一化标记
                    updated_outcome["normalized"] = True
                    
                    normalized_outcomes.append(updated_outcome)
                
                valid_idx += 1
        
        # 【新增】为跳过的选项也添加 normalized 标记
        for i, outcome in enumerate(normalized_outcomes):
            if outcome.get("normalized") is None:
                outcome["normalized"] = False  # 跳过的选项未归一化
        
        # 【修复】添加 normalization_reason: "sum_guard_scaled" 或 "ok"
        normalization_reason_value = "ok"
        if normalize_reason == "sum_guard":
            normalization_reason_value = "sum_guard_scaled"
        elif normalize_reason == "type":
            normalization_reason_value = "ok"  # 正常归一化
        
        return {
            "normalized_outcomes": normalized_outcomes,
            "total_before": round(total_before, 2),
            "total_after": round(total_after, 2),
            "error": round(error, 4),
            "skipped_count": len(skipped_indices),
            "normalized": True,  # 标记已归一化
            "event_type": event_type,
            "reason": normalize_reason,
            "normalization_reason": normalization_reason_value  # 新增字段
        }
    
    def _should_use_consensus_coef(self) -> bool:
        """
        决定是否启用共识加权（consensus coefficient）。
        
        Returns:
            True if consensus coefficient should be used (default), False otherwise
        """
        if self.experiment_config is None:
            return True  # Default: use consensus weighting
        
        try:
            # Handle ExperimentConfig object or dict
            if hasattr(self.experiment_config, 'config'):
                config = self.experiment_config.config
            else:
                config = self.experiment_config
            
            return config.get("FUSION", {}).get("consensus_coef", True)
        except Exception:
            return True  # Default on error
    
    def _should_use_market_bias(self) -> bool:
        """
        决定是否启用市场偏差融合（market bias）。
        
        Returns:
            True if market bias should be used (default), False otherwise
        """
        if self.experiment_config is None:
            return True  # Default: use market bias
        
        try:
            # Handle ExperimentConfig object or dict
            if hasattr(self.experiment_config, 'config'):
                config = self.experiment_config.config
            else:
                config = self.experiment_config
            
            return config.get("FUSION", {}).get("market_bias", True)
        except Exception:
            return True  # Default on error
    
    def _should_use_demarket_penalty(self) -> bool:
        """
        决定是否启用反市场跟踪惩罚（de-marketization penalty）。
        
        Returns:
            True if de-marketization penalty should be applied, False otherwise (default: False for experiments)
        """
        if self.experiment_config is None:
            return False  # Default: disabled (experimental feature)
        
        try:
            # Handle ExperimentConfig object or dict
            if hasattr(self.experiment_config, 'config'):
                config = self.experiment_config.config
            else:
                config = self.experiment_config
            
            return config.get("FUSION", {}).get("demarket_penalty", False)
        except Exception:
            return False  # Default on error
    
    def _get_calibration_method(self) -> Optional[str]:
        """
        获取后校准方法。
        
        Returns:
            Calibration method: "none", "binning", "platt", or None
        """
        if self.experiment_config is None:
            return "none"  # Default: no calibration
        
        try:
            # Handle ExperimentConfig object or dict
            if hasattr(self.experiment_config, 'config'):
                config = self.experiment_config.config
            else:
                config = self.experiment_config
            
            method = config.get("CALIBRATION", {}).get("post_calibration", "none")
            if method in ["none", "binning", "platt"]:
                return method
            return "none"
        except Exception:
            return "none"  # Default on error
    
    def _apply_demarket_penalty(
        self,
        final_prob: float,
        consensus_weight: float,
        market_prob: float,
        model_results: Dict[str, Dict]
    ) -> Optional[Dict]:
        """
        应用反市场跟踪惩罚：如果AI预测与市场概率过于接近且共识度高，添加小扰动避免纯跟踪。
        
        Args:
            final_prob: 当前融合后的概率
            consensus_weight: 模型共识概率
            market_prob: 市场价格
            model_results: 模型结果字典
        
        Returns:
            Dict with "adjusted_prob" if penalty applied, None otherwise
        """
        # Check if AI prediction is too close to market (within 2%)
        ai_market_diff = abs(consensus_weight - market_prob)
        
        if ai_market_diff < 0.02:  # Less than 2% difference
            # Calculate consensus (model agreement)
            probs = [r["probability"] for r in model_results.values()]
            if len(probs) > 1:
                avg_prob = self._mean(probs)
                if avg_prob > 0:
                    consensus = 1.0 - (self._std(probs) / avg_prob)
                else:
                    consensus = 0.0
            else:
                consensus = 1.0
            
            # Only apply penalty if consensus is high (>0.8)
            if consensus > 0.8:
                # Determine perturbation direction based on minority opinion
                # Use DeepSeek or Grok if available for minority signal
                perturbation = 0.015  # ±1.5% perturbation
                
                # Try to get minority opinion (DeepSeek or Grok)
                minority_prob = None
                for model_name in ["deepseek-chat", "grok-4", "grok-3"]:
                    if model_name in model_results:
                        minority_prob = model_results[model_name]["probability"]
                        break
                
                # If minority opinion exists and differs from consensus, use it for direction
                if minority_prob is not None:
                    if minority_prob > consensus_weight:
                        adjusted_prob = final_prob + perturbation
                    else:
                        adjusted_prob = final_prob - perturbation
                else:
                    # Default: random direction (but deterministic based on prob value)
                    adjusted_prob = final_prob + perturbation if (final_prob % 0.02) > 0.01 else final_prob - perturbation
                
                # Clip to [0, 100]
                adjusted_prob = max(0.0, min(100.0, adjusted_prob))
                
                return {
                    "adjusted_prob": adjusted_prob,
                    "original_prob": final_prob,
                    "perturbation": perturbation
                }
        
        return None  # No penalty applied

    @staticmethod
    def _safe_shorten_text(text: str, limit: int = 800) -> str:
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        sentences = re.split(r'(?<=[。！？.!?])\s+', text)
        shortened = []
        total = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if total + len(sentence) > limit:
                break
            shortened.append(sentence)
            total += len(sentence)
        result = " ".join(shortened).strip()
        if not result:
            result = text[:limit]
        if not result.endswith(('。', '！', '？', '.', '!', '?')):
            result = result.rstrip('…') + "..."
        return result

    @staticmethod
    def _safe_float(value: Optional[float], default: float = 0.0, label: Optional[str] = None) -> float:
        """Convert value to float safely with default fallback."""
        if value is None and label:
            print(f"[SAFE] {label} is None, using default {default}")
            return default
        safe_value = to_float(value, default)
        if safe_value == default and value not in (default, None):
            # 防止 NoneType 导致 TypeError
            if label:
                print(f"[SAFE] {label} invalid ({value}), using default {default}")
        return safe_value

    @staticmethod
    def _mean(values: List[float]) -> float:
        """Return arithmetic mean with empty guard."""
        if not values:
            return 0.0
        return math.fsum(values) / len(values)

    @classmethod
    def _std(cls, values: List[float]) -> float:
        """Return population standard deviation using safe math."""
        if not values:
            return 0.0
        mean_value = cls._mean(values)
        variance = math.fsum((val - mean_value) ** 2 for val in values) / len(values)
        return math.sqrt(variance)

    @classmethod
    def _weighted_mean(cls, values: List[float], weights: List[float]) -> float:
        """Compute weighted mean with graceful fallback."""
        if not values:
            return 0.0
        total_weight = math.fsum(to_float(weight, 0.0) for weight in (weights or []))
        if total_weight <= 0:
            return cls._mean(values)
        weighted_sum = math.fsum(
            safe_mul(
                to_float(val, 0.0),
                to_float(weight, 0.0)
            )
            for val, weight in zip(values, weights)
        )
        return weighted_sum / total_weight

    @classmethod
    def _weighted_std(cls, values: List[float], weights: List[float], mean_value: float) -> float:
        """Compute weighted standard deviation with safe defaults."""
        if not values:
            return 0.0
        total_weight = math.fsum(to_float(weight, 0.0) for weight in (weights or []))
        if total_weight <= 0:
            # Fall back to unweighted std
            return cls._std(values)
        variance = math.fsum(
            safe_mul(
                FusionEngine._safe_float(weight, 0.0, label="weighted_std_weight"),
                (FusionEngine._safe_float(val, 0.0, label="weighted_std_value") - mean_value) ** 2
            )
            for val, weight in zip(values, weights)
        ) / total_weight
        variance = max(variance, 0.0)
        return math.sqrt(variance)
    
    def _compute_model_confidence_factor(
        self,
        model_name: str,
        base_weight: float,
        confidence_weight: float,
        result: Dict
    ) -> float:
        """Combine historical性能 and实时置信度得到模型贡献系数 (0-1)."""
        max_conf = max(self.CONFIDENCE_WEIGHTS.values())
        historical_factor = min(1.0, self._safe_float(base_weight, 0.0, label=f"{model_name}_base_weight") / 3.0)
        realtime_factor = min(
            1.0,
            self._safe_float(confidence_weight, 0.0, label=f"{model_name}_confidence_weight") / max_conf if max_conf else 0.0
        )
        stability_bonus = 0.05 if result.get("calibration") else 0.0
        factor = safe_add(
            safe_add(
                safe_mul(0.5, realtime_factor),
                safe_mul(0.4, historical_factor)
            ),
            stability_bonus
        )
        return round(max(0.0, min(1.0, factor)), 4)
    
    def _compute_dynamic_fusion_weights(
        self,
        avg_conf_factor: float,
        consensus_uncertainty: float,
        market_prob: float
    ) -> Tuple[float, float]:
        """根据模型置信度和市场波动动态调整 AI/Market 权重。"""
        market_prob = to_float(market_prob, 0.0)  # 防止 NoneType 导致 TypeError
        volatility_component = self._estimate_market_volatility_component(market_prob)
        uncertainty_component = min(1.0, self._safe_float(consensus_uncertainty) / 25.0)
        # 模型权重基础值在 0.55 - 0.9 之间
        avg_conf = self._safe_float(avg_conf_factor, 0.0, label="avg_conf_factor")
        weight = self.MIN_MODEL_WEIGHT
        weight = safe_add(weight, safe_mul(0.35, avg_conf))
        weight = safe_add(weight, -safe_mul(0.2, volatility_component))
        weight = safe_add(weight, -safe_mul(0.1, uncertainty_component))
        weight = max(self.MIN_MODEL_WEIGHT, min(self.MAX_MODEL_WEIGHT, weight))
        return weight, 1.0 - weight
    
    @staticmethod
    def _estimate_market_volatility_component(market_prob: Optional[float]) -> float:
        """使用市场概率远离 0/100 的程度估算波动性 (0-1)."""
        prob = FusionEngine._safe_float(market_prob, default=50.0, label="market_prob_volatility")
        prob = max(0.0, min(100.0, prob))
        variability = safe_mul(prob, (100.0 - prob))  # 抛物线, 在 50% 时最大
        return min(1.0, variability / 2500.0)
    
    @staticmethod
    def _estimate_price_impact_component(ai_prob: float, market_prob: float) -> float:
        """根据 AI 与市场差值及流动性粗估价格冲击。"""
        safe_ai = FusionEngine._safe_float(ai_prob, 0.0, label="ai_prob_price_impact")
        safe_market = FusionEngine._safe_float(market_prob, 0.0, label="market_prob_price_impact")
        gap = abs(safe_ai - safe_market) / 100.0
        liquidity_proxy = 1.0 - min(1.0, abs(50.0 - safe_market) / 50.0)
        liquidity_proxy = max(0.2, liquidity_proxy)
        impact = min(1.0, gap / liquidity_proxy)
        return impact

    @staticmethod
    def evaluate_trade_signal(
        ai_prob: Optional[float],
        market_prob: Optional[float],
        days_to_resolution: Optional[int],
        event_uncertainty: Optional[float],
        volatility_coefficient: float = 0.01
    ) -> Dict[str, Union[str, float]]:
        """Evaluate a simple trade signal using EV and risk heuristics."""
        ai_val = FusionEngine._safe_float(ai_prob, label="trade_ai_prob")
        market_val = FusionEngine._safe_float(market_prob, label="trade_market_prob")
        days = FusionEngine._safe_float(days_to_resolution, default=1.0, label="days_to_resolution")
        if days <= 0:
            print("[SAFE] days_to_resolution <= 0, defaulting to 1.0")
            days = 1.0
        ev = ai_val - market_val
        edge_fraction = ev / 100.0
        try:
            annualized_ev = edge_fraction / max((days / 365.0), 0.01)
        except Exception:
            annualized_ev = 0.0
        uncertainty = FusionEngine._safe_float(event_uncertainty, label="event_uncertainty")
        volatility_component = FusionEngine._estimate_market_volatility_component(market_val)
        price_impact_component = FusionEngine._estimate_price_impact_component(ai_val, market_val)
        uncertainty_component = min(1.0, uncertainty / 25.0 if uncertainty else 0.0)
        # 调整权重，放大高波动场景的风险占比，确保更符合交易直觉
        risk_factor = safe_add(
            safe_add(
                safe_mul(0.40, uncertainty_component),
                safe_mul(0.40, volatility_component)
            ),
            safe_mul(0.20, price_impact_component)
        )

        signal = "HOLD"
        signal_reason = "Await better edge"
        volatility_coefficient = FusionEngine._safe_float(
            volatility_coefficient,
            default=0.01,
            label="volatility_coefficient"
        ) or 0.01
        slippage_cost = 0.02  # 2% slippage buffer
        fee_cost = 0.01       # 1% fee buffer
        base_edge_threshold = 0.03  # Require at least 3% raw edge before costs
        dynamic_threshold = safe_add(
            safe_add(
                safe_add(base_edge_threshold, safe_add(slippage_cost, fee_cost)),
                safe_mul(risk_factor, 0.04)
            ),
            safe_mul(volatility_coefficient, 2)
        )
        if edge_fraction > dynamic_threshold and risk_factor < 0.85:
            signal = "BUY"
            signal_reason = (
                f"Edge {edge_fraction*100:.2f}% exceeds threshold {dynamic_threshold*100:.2f}%, "
                f"risk {risk_factor:.2f}"
            )
        elif edge_fraction < -dynamic_threshold:
            signal = "SELL"
            signal_reason = (
                f"Negative edge {edge_fraction*100:.2f}% (threshold {dynamic_threshold*100:.2f}%), "
                f"favorable to sell"
            )
        elif risk_factor > 0.95:
            signal = "SELL"
            signal_reason = f"Risk factor extremely high ({risk_factor:.2f}), prefer capital preservation"
        print(
            f"[TRADE] Signal={signal}, EV={(ev or 0.0):.3f}, "
            f"Annualized={(annualized_ev or 0.0):.3f}, Risk={(risk_factor or 0.0):.2f}"
        )
        return {
            "signal": signal,
            "ev": round(ev or 0.0, 4),
            "annualized_ev": round(annualized_ev or 0.0, 4),
            "risk_factor": round(risk_factor or 0.0, 3),
            "signal_reason": signal_reason,
            "edge_threshold": round(dynamic_threshold, 4),
            "slippage_fee": round(slippage_cost + fee_cost, 3)
        }
    
    def _apply_calibration(self, prob: float, method: str) -> Optional[float]:
        """
        应用后校准（binning 或 platt scaling）。
        
        Args:
            prob: 原始概率值 (0-100)
            method: 校准方法 ("binning" or "platt")
        
        Returns:
            校准后的概率值，如果校准未启用或失败则返回 None
        """
        if method == "none" or self.calibration_map is None:
            return None  # No calibration configured
        
        try:
            if method == "binning":
                # Equal-frequency binning calibration
                # calibration_map should be a dict: {bin_index: calibrated_prob}
                # For simplicity, use linear interpolation if calibration_map is a function
                if callable(self.calibration_map):
                    return self.calibration_map(prob)
                elif isinstance(self.calibration_map, dict):
                    # Simple bin-based lookup (would need proper binning logic)
                    # For now, return original (proper implementation would need historical data)
                    return None
                else:
                    return None
            
            elif method == "platt":
                # Platt scaling (logistic regression calibration)
                # calibration_map should be fitted logistic regression parameters
                # For now, placeholder - would need historical data to fit
                return None
            
            return None
        except Exception as e:
            print(f"⚠️ 校准应用失败: {e}")
            return None
    
    def fit_calibration(self, historical_data: Optional[List[Tuple[float, int]]] = None):
        """
        使用历史数据拟合校准模型（binning 或 platt scaling）。
        
        Args:
            historical_data: List of (predicted_prob, true_label) tuples
        """
        # Placeholder for calibration fitting
        # This would be implemented when historical data is available
        calibration_method = self._get_calibration_method()
        if calibration_method != "none" and historical_data:
            # Fit calibration model here
            # For now, calibration_map remains None
            pass


def evaluate_trade_signal(
    ai_prob: Optional[float],
    market_prob: Optional[float],
    days_to_resolution: Optional[int] = None,
    event_uncertainty: Optional[float] = None,
    volatility_coefficient: float = 0.01
) -> Dict[str, Union[str, float]]:
    """
    Module-level wrapper to match external call expectations.
    
    # 防止 NoneType 导致 TypeError
    """
    return FusionEngine.evaluate_trade_signal(
        ai_prob=ai_prob,
        market_prob=market_prob,
        days_to_resolution=days_to_resolution,
        event_uncertainty=event_uncertainty,
        volatility_coefficient=volatility_coefficient
    )
