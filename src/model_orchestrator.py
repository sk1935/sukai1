"""
推理层（Model Orchestrator）：
根据 OPTIMIZATION_NOTES.md 的五层架构设计

职责：
- 调用多个大模型 API（通过统一接口 AICanAPI）
- 支持的模型：GPT-4o、Claude、Gemini、Grok、Qwen、DeepSeek 等
- 并发调用多个模型，提高效率
- 解析模型返回的内容：判断倾向、理由说明、主观概率
- 从 config/models.json 读取模型配置
- 支持自动降级机制

输入：各模型的 prompt（字符串）
输出：各模型的预测结果 {probability, confidence, reasoning}
"""
import aiohttp
import asyncio
import json
import math
import os
import re
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

# 各模型自适应超时时间（秒）- 基于实际API响应速度
MODEL_TIMEOUTS = {
    "gpt-4o": 30,
    "claude-3-7-sonnet-latest": 50,
    "claude-3.7-sonnet": 50,
    "claude-opus-4-1": 50,
    "gemini-2.5-pro": 45,
    "gemini-2.5-flash": 40,
    "grok-4": 60,
    "grok-3": 55,
    "deepseek-chat": 35,
}


class ModelOrchestrator:
    """
    Orchestrates parallel calls to multiple AI models via AICanAPI.
    
    管理多个AI模型的并发调用：
    - 通过 AICanAPI 统一接口调用不同模型
    - 支持模型权重配置
    - 解析 JSON 格式的预测结果
    - 错误处理和超时控制
    - 从 config/models.json 读取配置
    - 支持自动降级机制
    """
    
    # 各模型自适应超时时间（秒）- 根据实际API响应速度调整
    MODEL_TIMEOUTS = {
        "gpt-4o": 30,
        "claude-3-7-sonnet-latest": 50,
        "claude-opus-4-1": 50,
        "claude-3-5-opus-latest": 50,
        "gemini-2.5-pro": 45,
        "gemini-2.5-flash": 40,
        "grok-4": 60,  # Grok响应较慢，给更多时间
        "grok-3": 60,
        "deepseek-chat": 35,
    }
    
    # 兼容旧的常量（使用最大超时作为默认值）
    SINGLE_MODEL_TIMEOUT = 60  # 默认超时（使用最大模型的超时）
    PARALLEL_CALLS_TIMEOUT = 90  # 并行调用总超时（考虑重试）
    MAX_TOTAL_WAIT_TIME = 90  # 最大总等待时间（包括重试和降级）
    
    # 重试配置
    MAX_RETRIES = 3  # 最大重试次数
    RETRY_DELAY_BASE = 5  # 基础重试延迟（秒）
    RETRY_DELAY_MAX = 10  # 最大重试延迟（秒）
    
    # 并发控制
    MAX_CONCURRENT_MODELS = 2  # 同时最多运行的模型数（可通过环境变量覆盖）
    
    # 简易 Platt Scaling 参数（根据离线校准结果，可在配置中调整）
    PLATT_PARAMS = {
        "gpt-4o": {"A": -1.15, "B": 0.25},
        "claude-3-7-sonnet-latest": {"A": -1.05, "B": 0.18},
        "gemini-2.5-pro": {"A": -0.95, "B": 0.10},
        "grok-4": {"A": -1.20, "B": 0.35},
        "deepseek-chat": {"A": -0.85, "B": 0.05},
        "default": {"A": 0.0, "B": 0.0}
    }
    
    def __init__(self):
        """Initialize ModelOrchestrator and load model configurations from JSON."""
        self.models_config = self._load_models_config()
        self.MODELS = self._build_models_dict()
        self.active_models = {}  # Track actually used models (with fallback handling)
        # 并发控制信号量，可通过环境变量 MODEL_MAX_CONCURRENCY 调整
        concurrency_limit = int(os.getenv("MODEL_MAX_CONCURRENCY", self.MAX_CONCURRENT_MODELS))
        self._concurrency_semaphore = asyncio.Semaphore(max(1, concurrency_limit))
        self.current_concurrency_limit = max(1, concurrency_limit)
        self._log_model_versions()
    
    def _load_models_config(self) -> Dict:
        """Load model configurations from config/models.json."""
        config_path = Path(__file__).parent.parent / "config" / "models.json"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except FileNotFoundError:
            print(f"⚠️ 配置文件未找到: {config_path}")
            print("   使用默认配置...")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            print(f"⚠️ 配置文件解析错误: {e}")
            print("   使用默认配置...")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Return default configuration if JSON file is not available."""
        return {
            "models": {
                "gpt-4o": {
                    "display_name": "GPT-4o",
                    "model_id": "gpt-4o",
                    "source": "aicanapi",
                    "api_key_env": "AICANAPI_KEY",
                    "weight": 3.0,
                    "is_default": True,
                    "fallback": None,
                    "last_updated": "2024-11-21"
                }
            },
            "api_endpoints": {
                "aicanapi": "https://aicanapi.com/v1/chat/completions",
                "deepseek": "https://api.deepseek.com/v1/chat/completions"
            }
        }
    
    def _build_models_dict(self) -> Dict:
        """Build MODELS dict from JSON configuration, filtering enabled models."""
        models_dict = {}
        api_endpoints = self.models_config.get("api_endpoints", {})
        enabled_models = []
        disabled_models = []
        
        for model_key, model_config in self.models_config.get("models", {}).items():
            # Check if model is enabled (default to True for backward compatibility)
            if not model_config.get("enabled", True):
                disabled_models.append(model_config.get("display_name", model_config.get("model_id", model_key)))
                # Skip disabled models and their fallbacks
                continue
                
            model_id = model_config["model_id"]
            source = model_config["source"]
            url = api_endpoints.get(source, "")
            
            enabled_models.append(model_config.get("display_name", model_id))
            
            models_dict[model_id] = {
                "display_name": model_config.get("display_name", model_id),
                "source": source,
                "url": url,
                "api_key_env": model_config["api_key_env"],
                "weight": model_config["weight"],
                "fallback": model_config.get("fallback"),
                "fallback_display_name": model_config.get("fallback_display_name"),
                "last_updated": model_config.get("last_updated", "未知"),
                "is_default": model_config.get("is_default", False)
            }
            
            # Add fallback model if exists (only if primary model is enabled)
            if model_config.get("fallback"):
                fallback_id = model_config["fallback"]
                models_dict[fallback_id] = {
                    "display_name": model_config.get("fallback_display_name", fallback_id),
                    "source": source,
                    "url": url,
                    "api_key_env": model_config["api_key_env"],
                    "weight": model_config["weight"] * 0.9,  # Slightly lower weight for fallback
                    "fallback": None,
                    "last_updated": model_config.get("last_updated", "未知"),
                    "is_default": False
                }
        
        # Print confirmation log
        if enabled_models:
            enabled_str = ", ".join(enabled_models)
            print(f"[DEBUG] Active models: {enabled_str}")
        if disabled_models:
            disabled_str = ", ".join(disabled_models)
            print(f"[DEBUG] Disabled models: {disabled_str}")
        
        return models_dict
    
    def _log_model_versions(self):
        """Log current model versions."""
        active_versions = []
        for model_key, model_config in self.models_config.get("models", {}).items():
            display_name = model_config.get("display_name", model_key)
            active_versions.append(display_name)
        
        versions_str = " / ".join(active_versions)
        print(f"📊 当前使用模型版本: {versions_str}")
    
    def get_model_info(self, model_name: str) -> Optional[Dict]:
        """Get model information including display name and version."""
        if model_name in self.MODELS:
            return {
                "model_id": model_name,
                "display_name": self.MODELS[model_name].get("display_name", model_name),
                "last_updated": self.MODELS[model_name].get("last_updated", "未知"),
                "weight": self.MODELS[model_name].get("weight", 1.0)
            }
        
        # Check if it's a fallback model
        for config in self.models_config.get("models", {}).values():
            if config.get("fallback") == model_name:
                return {
                    "model_id": model_name,
                    "display_name": config.get("fallback_display_name", model_name),
                    "last_updated": config.get("last_updated", "未知"),
                    "weight": self.MODELS.get(model_name, {}).get("weight", 1.0) if model_name in self.MODELS else 1.0
                }
        
        return None
    
    def get_active_models_summary(self) -> Dict[str, Dict]:
        """Get summary of all active models with their versions."""
        summary = {}
        for model_name in self.MODELS.keys():
            info = self.get_model_info(model_name)
            if info:
                summary[model_name] = info
        return summary
    
    def _get_model_timeout(self, model_name: str) -> float:
        """
        获取模型的自适应超时时间
        
        Args:
            model_name: 模型名称
        
        Returns:
            超时时间（秒）
        """
        # 尝试精确匹配
        if model_name.lower() in self.MODEL_TIMEOUTS:
            return self.MODEL_TIMEOUTS[model_name.lower()]
        
        # 尝试部分匹配（例如 "claude-3-7-sonnet-latest" 匹配 "claude"）
        model_lower = model_name.lower()
        for key, timeout in self.MODEL_TIMEOUTS.items():
            if key in model_lower or model_lower in key:
                return timeout
        
        # 默认超时
        return 40.0
    
    async def _call_single_model(self, model_name: str, prompt: str) -> Optional[Dict]:
        """
        单次模型调用（不包含重试逻辑）
        
        Args:
            model_name: 模型名称
            prompt: 提示词
        
        Returns:
            模型响应结果或None
        """
        return await self._call_model_internal(model_name, prompt)
    
    def _get_model_timeout(self, model_name: str) -> float:
        """
        获取模型的自适应超时时间
        
        Args:
            model_name: 模型名称
        
        Returns:
            超时时间（秒）
        """
        # 尝试精确匹配
        if model_name in MODEL_TIMEOUTS:
            return MODEL_TIMEOUTS[model_name]
        
        # 尝试小写匹配
        model_lower = model_name.lower()
        for key, timeout in MODEL_TIMEOUTS.items():
            if key.lower() in model_lower or model_lower in key.lower():
                return timeout
        
        # 默认超时
        return self.SINGLE_MODEL_TIMEOUT
    
    def _get_platt_params(self, model_name: str) -> Dict[str, float]:
        return self.PLATT_PARAMS.get(model_name, self.PLATT_PARAMS.get("default", {"A": 0.0, "B": 0.0}))
    
    def _platt_scale_probability(self, model_name: str, probability: float) -> float:
        """Apply Platt scaling to model probability to improve calibration."""
        params = self._get_platt_params(model_name)
        normalized = max(0.001, min(0.999, probability / 100.0))
        logit = math.log(normalized / (1 - normalized))
        logistic_input = params["A"] * logit + params["B"]
        try:
            scaled = 1 / (1 + math.exp(-logistic_input))
        except OverflowError:
            scaled = 0.0 if logistic_input < 0 else 1.0
        return round(max(0.0, min(1.0, scaled)) * 100.0, 2)
    
    def _apply_probability_calibration(self, model_name: str, result: Optional[Dict]) -> Optional[Dict]:
        if not result or "probability" not in result:
            return result
        calibrated = dict(result)
        raw_prob = calibrated.get("probability", 50.0)
        calibrated_prob = self._platt_scale_probability(model_name, raw_prob)
        calibrated["raw_probability"] = raw_prob
        calibrated["probability"] = calibrated_prob
        params = self._get_platt_params(model_name)
        calibrated["calibration"] = {
            "method": "platt",
            "A": params.get("A", 0.0),
            "B": params.get("B", 0.0)
        }
        return calibrated
    
    async def call_model(self, model_name: str, prompt: str, max_retries: int = None) -> Optional[Dict]:
        """
        调用单个模型（带自适应超时 + 重试机制）
        
        Args:
            model_name: 模型名称
            prompt: 提示词
            max_retries: 最大重试次数（默认使用类配置）
        
        Returns:
            Dict with 'probability', 'confidence', 'reasoning', or None on error
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES
        
        timeout_seconds = self._get_model_timeout(model_name)
        start_time = time.time()
        
        print(f"[DEBUG] Calling {model_name} (timeout={timeout_seconds}s, max_retries={max_retries})")
        
        for attempt in range(max_retries):
            attempt_start = time.time()
            try:
                # 使用 asyncio.wait_for 实现超时控制（兼容所有Python版本）
                result = await asyncio.wait_for(
                    self._call_model_internal(model_name, prompt),
                    timeout=timeout_seconds
                )
                elapsed = time.time() - start_time
                
                if result:
                    print(f"[DEBUG] ✅ {model_name} completed in {elapsed:.2f}s (attempt {attempt+1})")
                    return self._apply_probability_calibration(model_name, result)
                else:
                    print(f"[DEBUG] ⚠️ {model_name} returned None (attempt {attempt+1}/{max_retries})")
                    
            except asyncio.TimeoutError:
                attempt_elapsed = time.time() - attempt_start
                total_elapsed = time.time() - start_time
                print(f"[TIMEOUT] ⚠️ {model_name} attempt {attempt+1}/{max_retries} exceeded {timeout_seconds}s (actual: {attempt_elapsed:.2f}s, total: {total_elapsed:.2f}s)")
                
                if attempt < max_retries - 1:
                    # 计算重试延迟（递增：5s, 8s, 10s）
                    wait_time = min(self.RETRY_DELAY_BASE * (attempt + 1), self.RETRY_DELAY_MAX)
                    print(f"[RETRY] Retrying {model_name} after {wait_time}s (attempt {attempt+2}/{max_retries})...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[FAIL] ❌ {model_name} failed after {max_retries} attempts (timeout).")
                    # 返回低置信度结果，确保流程不中断
                    return self._apply_probability_calibration(model_name, {
                        "probability": 50.0,
                        "confidence": "low",
                        "reasoning": f"Timeout after {max_retries} attempts (last attempt exceeded {timeout_seconds}s)"
                    })
                    
            except Exception as e:
                attempt_elapsed = time.time() - attempt_start
                total_elapsed = time.time() - start_time
                print(f"[ERROR] {model_name} exception on attempt {attempt+1}/{max_retries}: {type(e).__name__}: {e} (elapsed: {attempt_elapsed:.2f}s)")
                traceback.print_exc()
                
                if attempt < max_retries - 1:
                    wait_time = min(3, self.RETRY_DELAY_BASE)  # 异常时使用较短延迟
                    print(f"[RETRY] Retrying {model_name} after {wait_time}s (attempt {attempt+2}/{max_retries})...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[FAIL] ❌ {model_name} failed after {max_retries} attempts (exception).")
                    return self._apply_probability_calibration(model_name, {
                        "probability": 50.0,
                        "confidence": "low",
                        "reasoning": f"Exception after {max_retries} attempts: {type(e).__name__}: {str(e)[:100]}"
                    })
        
        # 所有重试都失败（不应该到达这里，因为上面已经return了）
        total_elapsed = time.time() - start_time
        print(f"[DEBUG] {model_name} total elapsed {total_elapsed:.2f}s (all attempts failed)")
        return self._apply_probability_calibration(model_name, {
            "probability": 50.0,
            "confidence": "low",
            "reasoning": "All retry attempts failed"
        })
    
    async def _call_model_internal(self, model_name: str, prompt: str) -> Optional[Dict]:
        """Internal method to call a model API with detailed logging."""
        if model_name not in self.MODELS:
            print(f"[DEBUG] {model_name} not in MODELS dict, skipping")
            return None
        
        config = self.MODELS[model_name]
        api_key = os.getenv(config["api_key_env"], "")
        
        # 详细日志：API key检查
        has_api_key = bool(api_key)
        print(f"[DEBUG] Start calling {model_name}")
        print(f"[DEBUG] {model_name} prompt length: {len(prompt)}")
        print(f"[DEBUG] {model_name} API key loaded: {has_api_key}")
        print(f"[DEBUG] {model_name} request started at: {time.time():.2f}")
        
        if not api_key:
            print(f"⚠️ [ERROR] No API key for {model_name}, skipping")
            return None
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # AICanAPI and DeepSeek use OpenAI-compatible API format
        # Determine model identifier based on source
        if config["source"] == "deepseek":
            # DeepSeek official API uses "deepseek-chat" as model name
            model_identifier = "deepseek-chat"
        else:
            # AICanAPI uses the model_name as identifier
            model_identifier = model_name
        
        payload = {
            "model": model_identifier,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1200
        }
        
        # 记录请求开始时间
        request_start_time = time.time()
        display_name = config.get("display_name", model_name)
        url = config.get("url", "")
        
        print(f"[DEBUG] {model_name} URL: {url}")
        print(f"[DEBUG] {model_name} Model identifier: {model_identifier}")
        
        try:
            print(f"📡 Calling {display_name} ({model_name}) at {url}")
            
            # 使用硬性超时控制
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.SINGLE_MODEL_TIMEOUT)
                    ) as response:
                        response_time = time.time() - request_start_time
                        print(f"[DEBUG] {model_name} received response at: {time.time():.2f} (took {response_time:.2f}s)")
                        if response.status == 200:
                            parse_start = time.time()
                            data = await response.json()
                            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                            print(f"✅ {display_name} responded: {content[:100]}...")
                            result = self._parse_model_response(content)
                            parse_time = time.time() - parse_start
                            
                            total_time = time.time() - request_start_time
                            print(f"[DEBUG] {model_name} parse time: {parse_time:.2f}s, total: {total_time:.2f}s")
                            
                            if result:
                                print(f"✅ {display_name} parsed successfully: prob={result.get('probability')}%")
                            else:
                                print(f"⚠️ {display_name} response parsing failed")
                            return result
                        else:
                            error_text = await response.text()
                            total_time = time.time() - request_start_time
                            print(f"❌ [ERROR] API error for {display_name}: {response.status} (took {total_time:.2f}s)")
                            print(f"Error details: {error_text[:500]}")
                            return None
                except asyncio.TimeoutError:
                    total_time = time.time() - request_start_time
                    print(f"⏱️ [TIMEOUT] {display_name} took too long, returning default. (>{self.SINGLE_MODEL_TIMEOUT}s, actual: {total_time:.2f}s)")
                    # 返回默认值而不是None，让系统可以继续
                    return {
                        "probability": 50.0,
                        "confidence": "low",
                        "reasoning": f"Timeout after {total_time:.2f}s"
                    }
                except aiohttp.ClientError as e:
                    total_time = time.time() - request_start_time
                    print(f"🌐 [ERROR] Network error calling {display_name}: {type(e).__name__}: {e} (took {total_time:.2f}s)")
                    return None
                except Exception as e:
                    total_time = time.time() - request_start_time
                    print(f"❌ [ERROR] Unexpected error in {display_name} request: {type(e).__name__}: {e} (took {total_time:.2f}s)")
                    import traceback
                    traceback.print_exc()
                    return None
        except asyncio.TimeoutError:
            total_time = time.time() - request_start_time
            print(f"⏱️ [TIMEOUT] {display_name} outer timeout (>{self.SINGLE_MODEL_TIMEOUT}s, actual: {total_time:.2f}s)")
            return {
                "probability": 50.0,
                "confidence": "low",
                "reasoning": f"Timeout after {total_time:.2f}s"
            }
        except Exception as e:
            total_time = time.time() - request_start_time
            print(f"❌ [ERROR] Outer exception calling {display_name}: {type(e).__name__}: {e} (took {total_time:.2f}s)")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_model_response(self, content: str) -> Optional[Dict]:
        """Parse JSON response from model."""
        if not content or not content.strip():
            print("⚠️ Empty response content")
            return None
            
        try:
            # Try to extract JSON from response
            original_content = content
            content = content.strip()
            
            # Look for JSON block
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                if end != -1:
                    content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                if end != -1:
                    content = content[start:end].strip()
            
            # Try to find JSON object
            start_brace = content.find("{")
            end_brace = content.rfind("}")
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                content = content[start_brace:end_brace + 1]
            
            # Try to parse JSON
            data = json.loads(content)
            
            # Validate and normalize
            prob = float(data.get("probability", 50.0))
            prob = max(0.0, min(100.0, prob))  # Clamp to [0, 100]
            
            confidence = data.get("confidence", "medium").lower()
            if confidence not in ["low", "medium", "high"]:
                confidence = "medium"
            
            reasoning_candidates = [
                data.get("reasoning_long"),
                data.get("reasoning_short"),
                data.get("reasoning")
            ]
            reasoning = next((r for r in reasoning_candidates if r), None)
            if reasoning:
                reasoning = self._safe_shorten_reasoning(reasoning)
            else:
                reasoning = ""
            return {
                "probability": prob,
                "confidence": confidence,
                "reasoning": reasoning,
                "reasoning_short": data.get("reasoning_short"),
                "reasoning_long": data.get("reasoning_long")
            }
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON decode error: {e}")
            print(f"Content preview: {original_content[:300]}")
            # Try to extract probability from text if JSON parsing fails
            prob_match = re.search(r'probability["\s:]+(\d+\.?\d*)', original_content, re.IGNORECASE)
            if prob_match:
                try:
                    prob = float(prob_match.group(1))
                    prob = max(0.0, min(100.0, prob))
                    print(f"✅ Extracted probability from text: {prob}%")
                    recovered = self._extract_sentences(original_content)
                    print(f"[PARSE] recovered_unstructured (len={len(recovered)})")
                    return {
                        "probability": prob,
                        "confidence": "medium",
                        "reasoning": recovered,
                        "reasoning_short": None,
                        "reasoning_long": None
                    }
                except:
                    pass
            return None
        except Exception as e:
            print(f"⚠️ Error parsing model response: {e}")
            print(f"Content preview: {original_content[:300]}")
            recovered = self._extract_sentences(original_content)
            if recovered:
                print(f"[PARSE] recovered_unstructured (len={len(recovered)})")
                return {
                    "probability": 50.0,
                    "confidence": "medium",
                    "reasoning": recovered,
                    "reasoning_short": None,
                    "reasoning_long": None
                }
            return None

    @staticmethod
    def _safe_shorten_reasoning(text: str, limit: int = 800) -> str:
        text = text.strip()
        if len(text) <= limit:
            return text
        sentences = re.split(r'(?<=[。！？.!?])\s+', text)
        shortened = []
        total_len = 0
        for sentence in sentences:
            if not sentence:
                continue
            sentence_len = len(sentence)
            if total_len + sentence_len > limit:
                break
            shortened.append(sentence)
            total_len += sentence_len
        shortened_text = " ".join(shortened).strip()
        if not shortened_text.endswith(('。', '！', '？', '.', '!', '?')):
            shortened_text += "..."
        return shortened_text

    @staticmethod
    def _extract_sentences(text: str, limit: int = 3) -> str:
        sentences = re.split(r'(?<=[。！？.!?])\s+', text.strip())
        cleaned = [s.strip() for s in sentences if s.strip()]
        selected = cleaned[:limit]
        joined = " ".join(selected)
        if selected and not selected[-1].endswith(('。', '！', '？', '.', '!', '?')):
            joined += "..."
        return joined
    
    async def call_all_models(self, prompts: Dict[str, str]) -> Dict[str, Optional[Dict]]:
        """
        并发调用所有模型，并在 MAX_TOTAL_WAIT_TIME 后取消未完成任务。
        """
        overall_start_time = time.time()
        model_names = list(prompts.keys())
        print(f"\n[DEBUG] ========== call_all_models START ==========")
        print(f"[DEBUG] Total models: {len(model_names)} | Max concurrent: {self.current_concurrency_limit}")
        
        semaphore = self._concurrency_semaphore
        default_response = {
            "probability": 50.0,
            "confidence": "low",
            "reasoning": "No response received"
        }

        # [FIX] Guard against empty model batches so asyncio.wait isn't invoked with no tasks.
        if not model_names:
            print("[WARN] No active models to call.")
            return {}
        
        async def guarded_call(model_name: str) -> Tuple[str, Optional[Dict]]:
            async with semaphore:
                call_start = time.time()
                per_model_budget = self._get_model_timeout(model_name) + 10
                try:
                    result = await asyncio.wait_for(
                        self.call_model(model_name, prompts[model_name]),
                        timeout=per_model_budget
                    )
                    call_duration = time.time() - call_start
                    print(f"[DEBUG] {model_name} finished in {call_duration:.2f}s")
                    return model_name, result
                except asyncio.TimeoutError:
                    call_duration = time.time() - call_start
                    print(f"⏱️ [WARNING] {model_name} exceeded guarded timeout ({per_model_budget}s). Cancelling task.")
                    return model_name, {
                        "probability": 50.0,
                        "confidence": "low",
                        "reasoning": f"Guarded timeout after {call_duration:.2f}s"
                    }
                except Exception as e:
                    call_duration = time.time() - call_start
                    print(f"❌ [ERROR] 模型调用异常 – {model_name}: {type(e).__name__}: {e} (took {call_duration:.2f}s)")
                    traceback.print_exc()
                    return model_name, {
                        "probability": 50.0,
                        "confidence": "low",
                        "reasoning": f"Exception: {type(e).__name__}"
                    }
        
        tasks = [asyncio.create_task(guarded_call(name)) for name in model_names]
        # [FIX] Double-check tasks list because filters above might drop every model.
        if not tasks:
            print("[WARN] No active models to call.")
            return {}
        results_dict: Dict[str, Optional[Dict]] = {}
        
        done, pending = await asyncio.wait(
            tasks,
            timeout=self.MAX_TOTAL_WAIT_TIME,
            return_when=asyncio.ALL_COMPLETED
        )
        
        if pending:
            print(f"⏱️ [WARNING] 取消 {len(pending)} 个未完成的模型调用（总超时 {self.MAX_TOTAL_WAIT_TIME}s）")
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        for task in done:
            try:
                model_name, result = task.result()
                base = result or default_response.copy()
                results_dict[model_name] = self._apply_probability_calibration(model_name, base)
            except Exception as e:
                print(f"❌ [ERROR] 收集模型结果失败: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                # Identify associated model if possible
                model_name = "unknown"
                results_dict[model_name] = self._apply_probability_calibration(model_name, default_response.copy())
        
        for model_name in model_names:
            if model_name not in results_dict:
                results_dict[model_name] = self._apply_probability_calibration(model_name, default_response.copy())
                print(f"⚠️ [WARNING] 模型 {model_name} 未返回结果，使用默认值")
        
        success_count = sum(1 for r in results_dict.values() if r)
        total_duration = time.time() - overall_start_time
        print(f"[DEBUG] Total execution time: {total_duration:.2f}s | Success: {success_count}/{len(model_names)}")
        print(f"[DEBUG] ========== call_all_models END ==========")
        
        return results_dict
    
    def get_model_weight(self, model_name: str) -> float:
        """Get weight for a model in fusion."""
        return self.MODELS.get(model_name, {}).get("weight", 1.0)
    
    def get_available_models(self) -> List[str]:
        """Get list of models that have API keys configured."""
        available = []
        for model_name, config in self.MODELS.items():
            api_key = os.getenv(config["api_key_env"], "")
            if api_key:
                available.append(model_name)
        return available
