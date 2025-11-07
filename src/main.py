"""
主程序（Main）：
根据 OPTIMIZATION_NOTES.md 的五层架构设计

系统架构：
1. 事件层（EventManager）→ 解析输入、获取市场数据
2. 提示层（PromptBuilder）→ 生成模型提示词
3. 推理层（ModelOrchestrator）→ 并发调用多个AI模型
4. 融合层（FusionEngine）→ 加权融合预测结果
5. 输出层（OutputFormatter）→ 格式化中文报告

本模块负责协调五层架构，实现完整的预测流程。
"""
import asyncio
import inspect
import logging
import os
from dotenv import load_dotenv
import signal
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

TELEGRAM_AVAILABLE = True
TELEGRAM_BACKEND = "application"

# 【修复】在导入 telegram.ext 之前修补 apscheduler 的时区问题
# Python 3.13 的 zoneinfo 与 apscheduler 不兼容
try:
    import pytz
    import apscheduler.util
    # 创建 pytz 时区对象
    try:
        default_tz = pytz.timezone('Asia/Shanghai')
    except:
        default_tz = pytz.UTC
    
    # 修补 astimezone 函数，让它接受 zoneinfo 时区并转换为 pytz
    original_astimezone = apscheduler.util.astimezone
    def patched_astimezone(tz):
        if tz is None:
            return default_tz
        # 如果已经是 pytz 时区，直接返回
        if isinstance(tz, pytz.BaseTzInfo):
            return tz
        # 如果是 zoneinfo 时区，转换为 pytz
        try:
            from zoneinfo import ZoneInfo
            if isinstance(tz, ZoneInfo):
                # 获取时区名称
                tz_name = str(tz).split('/')[-1] if '/' in str(tz) else str(tz)
                # 尝试转换为 pytz 时区
                try:
                    return pytz.timezone(tz_name)
                except:
                    return default_tz
        except:
            pass
        # 其他情况，尝试原始函数
        try:
            return original_astimezone(tz)
        except:
            return default_tz
    
    apscheduler.util.astimezone = patched_astimezone
    print(f"✅ 已修补 apscheduler 时区函数，默认时区: {default_tz}")
except Exception as e:
    print(f"⚠️ 修补 apscheduler 时区函数失败: {e}")
    import traceback
    traceback.print_exc()

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
except ImportError:
    try:
        from telegram import Update
        from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

        TELEGRAM_BACKEND = "legacy"
        ContextTypes = SimpleNamespace(DEFAULT_TYPE=CallbackContext)
        filters = SimpleNamespace(TEXT=Filters.text, COMMAND=Filters.command)

        class LegacyApplication:
            """Shim to provide Application-like interface on top of Updater."""

            def __init__(self, updater):
                self.updater = updater
                self.dispatcher = updater.dispatcher

            @classmethod
            def builder(cls):
                return LegacyApplicationBuilder()

            def add_handler(self, handler, group=0):
                self.dispatcher.add_handler(handler, group=group)

            def add_error_handler(self, handler):
                self.dispatcher.add_error_handler(handler)

            def run_polling(self, **kwargs):
                self.updater.start_polling()
                self.updater.idle()

        class LegacyApplicationBuilder:
            def __init__(self):
                self._token = None

            def token(self, token):
                self._token = token
                return self

            def build(self):
                if not self._token:
                    raise ValueError("TELEGRAM_BOT_TOKEN 未配置")
                updater = Updater(token=self._token, use_context=True)
                return LegacyApplication(updater)

        Application = LegacyApplication  # type: ignore
    except ImportError as telegram_import_err:
        TELEGRAM_AVAILABLE = False
        TELEGRAM_IMPORT_ERROR = telegram_import_err
        
        class _DummyUpdate:
            ALL_TYPES = []
        Update = _DummyUpdate  # type: ignore
        
        class _DummyContextTypes:
            DEFAULT_TYPE = object
        ContextTypes = _DummyContextTypes  # type: ignore
        
        class _DummyFilters:
            TEXT = object()
            COMMAND = object()
        filters = _DummyFilters()
        
        class Application:  # type: ignore
            @classmethod
            def builder(cls):
                raise RuntimeError("Telegram dependency unavailable")
        
        class CommandHandler:  # type: ignore
            def __init__(self, *args, **kwargs):
                raise RuntimeError("Telegram dependency unavailable")
        
        class MessageHandler:  # type: ignore
            def __init__(self, *args, **kwargs):
                raise RuntimeError("Telegram dependency unavailable")

# Ensure local src imports always resolve
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from event_manager import EventManager
from prompt_builder import PromptBuilder
from model_orchestrator import ModelOrchestrator
from fusion_engine import FusionEngine
from output_formatter import OutputFormatter
from event_analyzer import EventAnalyzer
from notion_logger import NotionLogger

# OpenRouter 集成
try:
    from services.llm_clients.openrouter_layer import (
        call_openrouter_model,
        call_multiple_openrouter_models,
        get_available_models as get_openrouter_models,
        is_openrouter_available
    )
    OPENROUTER_INTEGRATION_AVAILABLE = True
except Exception as import_err:
    print(f"⚠️ OpenRouter 集成不可用: {import_err}")
    OPENROUTER_INTEGRATION_AVAILABLE = False
    
    async def call_openrouter_model(*args, **kwargs):
        raise RuntimeError("OpenRouter integration disabled")
    
    async def call_multiple_openrouter_models(*args, **kwargs):
        return {}
    
    def get_openrouter_models():
        return []
    
    def is_openrouter_available():
        return False

# LMArena 动态权重更新
try:
    from config.update_lmarena_weights import update_lmarena_weights, should_update
    LMARENA_UPDATE_AVAILABLE = True
except ImportError:
    print("⚠️ LMArena 权重更新模块未找到，跳过自动更新")
    LMARENA_UPDATE_AVAILABLE = False

load_dotenv()


def _configure_logging() -> logging.Logger:
    """Configure application-wide logging once and return module logger."""
    level_name = os.getenv("POLYMARKET_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    return logging.getLogger("polymarket")


BOT_LOGGER = _configure_logging()


async def maybe_await(result):
    """Await result if it is awaitable, otherwise return it directly."""
    if inspect.isawaitable(result):
        return await result
    return result


def wrap_async_handler(handler):
    """Wrap async handler for legacy (synchronous) telegram backends."""
    if TELEGRAM_AVAILABLE and TELEGRAM_BACKEND == "legacy" and inspect.iscoroutinefunction(handler):
        def _wrapper(update, context):
            asyncio.run(handler(update, context))
        return _wrapper
    return handler


class ForecastingBot:
    """
    Main bot class that orchestrates all components.
    
    预测机器人主类：
    - 协调五层架构的完整流程
    - 处理 Telegram 消息和命令
    - 支持单选项和多选项市场预测
    - 所有输出均为中文
    """
    
    def __init__(
        self,
        event_manager: Optional[EventManager] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        model_orchestrator: Optional[ModelOrchestrator] = None,
        fusion_engine: Optional[FusionEngine] = None,
        output_formatter: Optional[OutputFormatter] = None,
        event_analyzer: Optional[EventAnalyzer] = None,
        notion_logger: Optional[NotionLogger] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger or BOT_LOGGER.getChild("bot")
        self.event_manager = event_manager or EventManager()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.model_orchestrator = model_orchestrator or ModelOrchestrator()
        self.fusion_engine = fusion_engine or FusionEngine()
        self.output_formatter = output_formatter or OutputFormatter()
        self.event_analyzer = event_analyzer or EventAnalyzer()

        # 初始化 Notion Logger（如果配置了环境变量）
        if notion_logger is not None:
            self.notion_logger = notion_logger
        else:
            try:
                self.notion_logger = NotionLogger()
                if self.notion_logger and self.notion_logger.enabled:
                    self.logger.info("Notion Logger 已启用，预测结果将自动保存到 Notion")
                elif self.notion_logger:
                    self.logger.warning("Notion Logger 已创建但未启用（请检查配置）")
            except Exception as e:
                self.logger.exception("Notion Logger 初始化异常: %s", e)
                import traceback
                traceback.print_exc()
                self.notion_logger = None
    
    async def _prepare_prediction_context(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> Optional[str]:
        """Validate update, show typing indicator, and preload news cache."""
        if not update.message:
            print("⚠️ handle_predict: No message in update")
            return None

        message_text = update.message.text or ""
        print(f"\n{'='*60}")
        print(f"📨 收到消息: {message_text[:100]}...")
        print(f"{'='*60}")

        try:
            await maybe_await(context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            ))
        except Exception as e:
            print(f"⚠️ 发送typing indicator失败: {e}")

        try:
            from src.news_cache import fetch_and_cache_news, NEWS_CACHE_ENABLED
            if NEWS_CACHE_ENABLED:
                print("📰 [NEWS_CACHE] 开始预加载新闻缓存...")
                try:
                    await asyncio.wait_for(
                        fetch_and_cache_news(keyword="", force_refresh=False),
                        timeout=15.0
                    )
                    print("✅ [NEWS_CACHE] 新闻缓存预加载完成")
                except asyncio.TimeoutError:
                    print("⏱️ [NEWS_CACHE] 预加载超时，继续执行（使用旧缓存）")
                except Exception as e:
                    print(f"⚠️ [NEWS_CACHE] 预加载失败: {type(e).__name__}: {e}，继续执行")
            else:
                print("ℹ️ [NEWS_CACHE] 功能未启用，跳过预加载")
        except ImportError as e:
            print(f"⚠️ [NEWS_CACHE] 模块导入失败: {e}")
        except Exception as e:
            print(f"⚠️ [NEWS_CACHE] 预加载异常: {type(e).__name__}: {e}")

        return message_text

    async def _fetch_event_data(
        self,
        update: Update,
        event_info: Dict[str, str]
    ) -> Dict:
        """Fetch Polymarket data with timeout and mock fallbacks."""
        await maybe_await(update.message.reply_text("🔍 正在获取市场数据..."))
        print(f"🔍 开始获取市场数据，event_info: {event_info}")
        event_data: Optional[Dict] = None
        try:
            event_data = await asyncio.wait_for(
                self.event_manager.fetch_polymarket_data(event_info),
                timeout=25.0
            )
            if event_data:
                print("✅ 成功获取市场数据:")
                print(f"  question: {event_data.get('question', 'N/A')[:80]}")
                print(f"  market_prob: {event_data.get('market_prob', 'N/A')}")
                print(f"  is_mock: {event_data.get('is_mock', False)}")
            else:
                print("⚠️ event_data 为 None")
        except asyncio.TimeoutError:
            print("⏱️ 获取市场数据超时")
            await maybe_await(update.message.reply_text(
                "⏱️ 获取市场数据超时，将使用 AI 模型进行预测。",
                parse_mode="Markdown"
            ))
            event_data = self.event_manager._create_mock_market_data(event_info.get('query', ''))
            event_data["is_mock"] = True
            return event_data
        except Exception as exc:
            print(f"⚠️ 获取市场数据异常: {type(exc).__name__}: {exc}")

        if not event_data:
            print("❌ 未能获取市场数据，创建mock数据")
            await maybe_await(update.message.reply_text(
                self.output_formatter.format_error(
                    "获取市场数据失败，将使用 AI 模型进行预测。"
                ),
                parse_mode="Markdown"
            ))
            event_data = self.event_manager._create_mock_market_data(event_info.get('query', ''))
            event_data["is_mock"] = True

        return event_data

    async def _analyze_event(
        self,
        event_data: Dict,
        event_info: Dict[str, str]
    ) -> Tuple[Dict, Dict, Optional[str], List[str]]:
        """Run full event analysis, news summary, and model selection."""
        market_slug = event_info.get('slug')
        try:
            full_analysis = await asyncio.wait_for(
                self.event_analyzer.analyze_event_full(
                    event_title=event_data.get("question", ""),
                    event_rules=event_data.get("rules", ""),
                    market_prob=event_data.get("market_prob"),
                    market_slug=market_slug
                ),
                timeout=15.0
            )
            print("✅ 完整事件分析完成（包含市场趋势、舆情、规则摘要）")
        except asyncio.TimeoutError:
            print("⏱️ [WARNING] 事件分析超时，使用默认值")
            full_analysis = {
                "event_category": "general",
                "event_category_display": "通用",
                "market_trend": "数据不足",
                "sentiment_trend": "unknown",
                "sentiment_score": 0.0,
                "sentiment_sample": 0,
                "sentiment_source": "未知",
                "rules_summary": event_data.get("rules", "")[:100] if event_data.get("rules") else "无规则信息"
            }
        except Exception as e:
            print(f"⚠️ 完整事件分析失败: {type(e).__name__}: {e}，使用基础分析")
            full_analysis = {
                "event_category": event_data.get("category", "unknown"),
                "event_category_display": event_data.get("category", "unknown"),
                "market_trend": "分析失败",
                "sentiment_trend": "unknown",
                "sentiment_score": 0.0,
                "sentiment_sample": 0,
                "sentiment_source": "未知",
                "rules_summary": event_data.get("rules", "")[:100] if event_data.get("rules") else "无规则信息"
            }

        print("\n📊 事件全面分析:")
        print(f"  类别: {full_analysis['event_category']} ({full_analysis.get('event_category_display', '未知')})")
        print(f"  市场趋势: {full_analysis['market_trend']}")
        sentiment_score = full_analysis.get('sentiment_score') or 0.0
        print(
            f"  舆情: {full_analysis.get('sentiment_trend', 'unknown')} ({sentiment_score:+.2f}), "
            f"样本: {full_analysis.get('sentiment_sample', 0)} ({full_analysis.get('sentiment_source', '未知')})"
        )
        print(f"  规则摘要: {full_analysis.get('rules_summary', '')[:60]}...")
        world_temp_data = full_analysis.get("world_temp_data")
        if world_temp_data:
            description = world_temp_data.get("description", "未知")
            positive = world_temp_data.get("positive", 0)
            negative = world_temp_data.get("negative", 0)
            neutral = world_temp_data.get("neutral", 0)
            print(f"  🧠 世界情绪: {description}（正面: {positive}, 负面: {negative}, 中性: {neutral}）")
        elif full_analysis.get("world_sentiment_summary"):
            print(f"  🧠 世界情绪: {full_analysis['world_sentiment_summary'][:80]}...")

        news_summary = None
        try:
            from src.openrouter_assistant import get_news_summary, OPENROUTER_ASSISTANT_ENABLED
            if OPENROUTER_ASSISTANT_ENABLED:
                news_summary = await asyncio.wait_for(
                    get_news_summary(),
                    timeout=10.0
                )
                if news_summary:
                    print(f"  📰 新闻摘要: 已获取（{len(news_summary)} 字符）")
            else:
                print("  ℹ️ [OPENROUTER] 功能未启用，跳过新闻摘要")
        except asyncio.TimeoutError:
            print("  ⏱️ [OPENROUTER] 获取新闻摘要超时（>10s），跳过")
        except ImportError as e:
            print(f"  ⚠️ [OPENROUTER] 模块导入失败: {e}")
        except Exception as e:
            print(f"  ⚠️ [OPENROUTER] 获取新闻摘要失败: {type(e).__name__}: {e}")

        event_analysis = self.event_analyzer.analyze_event(
            event_data.get("question", ""),
            event_data.get("rules", ""),
            available_models=None,
            orchestrator=self.model_orchestrator
        )
        print(f"\n📊 Event Category: {event_analysis['category']}")
        print(f"📐 Dimensions: {len(event_analysis['dimensions'])}")
        model_names = [
            model for model in event_analysis["model_assignments"].keys()
            if model in self.model_orchestrator.get_available_models()
        ]
        event_data["full_analysis"] = full_analysis
        event_data["world_temp"] = full_analysis.get("world_temp")
        event_data["world_temp_data"] = full_analysis.get("world_temp_data")
        event_data["world_sentiment_summary"] = full_analysis.get("world_sentiment_summary")
        event_data["news_summary"] = news_summary
        return event_analysis, full_analysis, news_summary, model_names

    def _build_binary_prompts(
        self,
        event_data: Dict,
        model_assignments: Dict,
        model_names: List[str]
    ) -> Dict[str, str]:
        """Construct per-model prompts for binary predictions."""
        prompts: Dict[str, str] = {}
        for model_name in model_names:
            assignment = model_assignments.get(model_name)
            prompt = self.prompt_builder.build_prompt(
                event_data,
                model_name,
                model_assignment=assignment
            )
            prompts[model_name] = prompt
            if assignment:
                print(f"  ✅ {model_name}: {assignment['dimension_name']}")
        return prompts

    async def _call_binary_models(
        self,
        update: Update,
        prompts: Dict[str, str]
    ) -> Optional[Dict[str, Optional[Dict[str, Any]]]]:
        """Call orchestrator models (plus OpenRouter) with shared timeout and fallbacks."""
        await maybe_await(update.message.reply_text("🤖 正在查询 AI 模型..."))
        print(f"\n📞 Calling {len(prompts)} models: {list(prompts.keys())}")

        try:
            timeout = self.model_orchestrator.MAX_TOTAL_WAIT_TIME
            model_results = await asyncio.wait_for(
                self.model_orchestrator.call_all_models(prompts),
                timeout=float(timeout)
            )

            success_count = sum(1 for r in model_results.values() if r is not None)

            if OPENROUTER_INTEGRATION_AVAILABLE and is_openrouter_available():
                print(f"\n🆓 [OpenRouter] 调用免费模型作为辅助层...")
                openrouter_models = get_openrouter_models()
                selected_models = openrouter_models[:2] if len(openrouter_models) >= 2 else openrouter_models

                if selected_models:
                    common_prompt = list(prompts.values())[0] if prompts else ""

                    try:
                        openrouter_results = await asyncio.wait_for(
                            call_multiple_openrouter_models(selected_models, common_prompt),
                            timeout=30.0
                        )

                        openrouter_success = 0
                        for model_name, result in openrouter_results.items():
                            if result:
                                display_name = model_name.split('/')[-1]
                                model_results[f"openrouter_{display_name}"] = result
                                openrouter_success += 1

                        if openrouter_success > 0:
                            print(f"✅ [OpenRouter] {openrouter_success}/{len(selected_models)} 个模型调用成功")
                            success_count += openrouter_success
                        else:
                            print("⚠️ [OpenRouter] 所有模型调用失败")

                    except asyncio.TimeoutError:
                        print("⏱️ [OpenRouter] 调用超时，跳过")
                    except Exception as e:
                        print(f"⚠️ [OpenRouter] 调用异常: {type(e).__name__}: {e}")
            else:
                print("ℹ️ [OpenRouter] API 密钥未配置，跳过免费模型调用")

            if success_count == 0:
                print("⚠️ [WARNING] 所有模型调用失败，使用市场价格作为fallback")
                await maybe_await(update.message.reply_text(
                    "⚠️ AI模型暂时无响应，将使用市场价格进行预测。",
                    parse_mode="Markdown"
                ))
            elif success_count < len(prompts):
                print(f"⚠️ [WARNING] 部分模块响应慢：{success_count}/{len(prompts)} 个模型成功")

            return model_results

        except asyncio.TimeoutError:
            timeout = self.model_orchestrator.MAX_TOTAL_WAIT_TIME
            print(f"⏱️ [ERROR] 模型查询总超时（>{timeout}s）")
            import traceback
            print("[DEBUG] Timeout exception traceback:")
            traceback.print_exc()

            try:
                model_results = {
                    name: {
                        "probability": 50.0,
                        "confidence": "low",
                        "reasoning": "Overall timeout"
                    }
                    for name in prompts.keys()
                }
                await maybe_await(update.message.reply_text(
                    "⚠️ 部分模块响应延迟，结果可能不完全准确。",
                    parse_mode="Markdown"
                ))
                return model_results
            except Exception as e:
                print(f"❌ [ERROR] 处理超时异常失败: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                await maybe_await(update.message.reply_text(
                    "⏱️ 模型查询超时，请稍后重试。",
                    parse_mode="Markdown"
                ))
                return None

    async def _finalize_binary_prediction(
        self,
        update: Update,
        event_data: Dict,
        model_results: Dict[str, Optional[Dict[str, Any]]],
        model_names: List[str],
        full_analysis: Dict
    ) -> None:
        """Fuse model outputs, compute trade signal, format output, and log to Notion."""
        print(f"\n📊 Model Results:")
        for model_name, result in model_results.items():
            if result:
                print(f"  ✅ {model_name}: {result.get('probability')}% ({result.get('confidence')})")
            else:
                print(f"  ❌ {model_name}: No response")

        model_weights = {
            model_name: self.model_orchestrator.get_model_weight(model_name)
            for model_name in model_names
        }

        if OPENROUTER_INTEGRATION_AVAILABLE and is_openrouter_available():
            openrouter_models = get_openrouter_models()
            for model_name in openrouter_models[:2]:
                display_name = model_name.split('/')[-1]
                openrouter_key = f"openrouter_{display_name}"
                if openrouter_key in model_results and model_results[openrouter_key]:
                    model_weights[openrouter_key] = 0.5

        fusion_result = self.fusion_engine.fuse_predictions(
            model_results=model_results,
            model_weights=model_weights,
            market_prob=event_data["market_prob"],
            orchestrator=self.model_orchestrator
        )

        trade_signal_data = None
        if fusion_result:
            ai_prob_trade = fusion_result.get("model_only_prob")
            if ai_prob_trade is None:
                ai_prob_trade = fusion_result.get("final_prob")
            market_prob_trade = event_data.get("market_prob")
            market_prob_trade = (
                market_prob_trade if market_prob_trade is not None else fusion_result.get("final_prob")
            )
            days_to_resolution = event_data.get("days_left") or 30
            uncertainty_ratio = (fusion_result.get("uncertainty") or 0.0) / 100.0
            trade_signal_data = self.fusion_engine.evaluate_trade_signal(
                ai_prob_trade,
                market_prob_trade,
                days_to_resolution,
                uncertainty_ratio
            )
            print(
                f"[TRADE_SIGNAL] computed event={event_data.get('question', 'N/A')} "
                f"signal={trade_signal_data.get('signal')} ev={trade_signal_data.get('ev')}"
            )
            fusion_result["trade_signal"] = trade_signal_data
            fusion_result["ev"] = trade_signal_data.get("ev")
            fusion_result["annualized_ev"] = trade_signal_data.get("annualized_ev")
            fusion_result["risk_factor"] = trade_signal_data.get("risk_factor")
            fusion_result["signal"] = trade_signal_data.get("signal")
            fusion_result["signal_reason"] = trade_signal_data.get("signal_reason")

        output = self.output_formatter.format_prediction(
            event_data=event_data,
            fusion_result=fusion_result,
            trade_signal=trade_signal_data
        )

        await maybe_await(update.message.reply_text(
            output,
            parse_mode="Markdown"
        ))

        if self.notion_logger:
            if not self.notion_logger.enabled:
                print("⚠️ Notion Logger 未启用，跳过记录（单选项事件）")
        if self.notion_logger and self.notion_logger.enabled:
            try:
                event_data_for_notion = event_data.copy()
                if full_analysis:
                    event_data_for_notion["category"] = full_analysis.get(
                        "event_category_display",
                        full_analysis.get("event_category", "-")
                    )
                if "outcomes" not in event_data_for_notion:
                    event_data_for_notion["outcomes"] = ["Yes"]

                fusion_result_for_notion = fusion_result.copy()
                if "models" not in fusion_result_for_notion:
                    model_versions = fusion_result.get("model_versions", {})
                    if model_versions:
                        fusion_result_for_notion["models"] = [
                            info.get("display_name", model_id)
                            for model_id, info in model_versions.items()
                        ]
                    else:
                        fusion_result_for_notion["models"] = model_names
                if "run_id" not in fusion_result_for_notion:
                    import uuid
                    fusion_result_for_notion["run_id"] = str(uuid.uuid4())

                self.notion_logger.log_prediction(
                    event_data=event_data_for_notion,
                    fusion_result=fusion_result_for_notion,
                    full_analysis=full_analysis,
                    outcomes=None,
                    normalization_info=None,
                    trade_signal=None
                )
            except Exception as e:
                print(f"⚠️ Notion Logger 记录失败: {e}")

    def _gather_multi_option_prompts(
        self,
        event_data: Dict,
        model_assignments: Dict,
        model_names: List[str],
        outcome: Dict
    ) -> Dict[str, str]:
        """Build prompts for a single multi-option outcome."""
        outcome_name = outcome.get("name", "未知选项")
        print(f"[MULTI_FLOW] Building prompts for outcome: {outcome_name}")
        prompts: Dict[str, str] = {}
        for model_name in model_names:
            assignment = model_assignments.get(model_name)
            option_event_data = event_data.copy()
            option_event_data["question"] = f"{event_data.get('question', '')} - {outcome_name}"
            option_event_data["market_prob"] = outcome.get("market_prob")
            prompt = self.prompt_builder.build_prompt(
                option_event_data,
                model_name,
                model_assignment=assignment
            )
            prompts[model_name] = prompt
            if assignment:
                print(f"   - {model_name}: {assignment['dimension_name']}")
        if not prompts:
            print(f"[MULTI_FLOW] No prompts constructed for {outcome_name}")
        return prompts

    async def _run_multi_option_models(
        self,
        outcome_name: str,
        prompts: Dict[str, str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Call models (with retries + OpenRouter) for a single outcome."""
        if not prompts:
            return {}

        print(f"[MULTI_FLOW] Running models for outcome: {outcome_name} ({len(prompts)} prompts)")
        max_retries = 2
        timeout = min(
            self.model_orchestrator.MAX_TOTAL_WAIT_TIME,
            30.0
        )
        model_results: Dict[str, Optional[Dict[str, Any]]] = {}

        for retry in range(max_retries):
            try:
                print(f"📤 调用 {len(prompts)} 个模型（尝试 {retry + 1}/{max_retries}）")
                model_results = await asyncio.wait_for(
                    self.model_orchestrator.call_all_models(prompts),
                    timeout=timeout
                )
                success_count = sum(1 for r in model_results.values() if r)
                if success_count > 0:
                    break
                if retry < max_retries - 1 and success_count == 0:
                    print(f"  ⚠️ {outcome_name} 首次调用无结果，等待 1 秒后重试...")
                    await asyncio.sleep(1)
                    continue
            except asyncio.TimeoutError:
                if retry < max_retries - 1:
                    print(f"  ⏱️ {outcome_name} 超时（>{timeout}s），重试 {retry + 1}/{max_retries}...")
                    await asyncio.sleep(1)
                    continue
                print(f"  ⏱️ [ERROR] {outcome_name} 重试后仍超时（>{timeout}s），使用市场价格")
                model_results = {}
                break
            except Exception as e:
                if retry < max_retries - 1:
                    print(f"  ⚠️ {outcome_name} 调用异常 ({type(e).__name__})，重试 {retry + 1}/{max_retries}...")
                    await asyncio.sleep(1)
                    continue
                print(f"  ❌ [ERROR] {outcome_name} 重试后仍异常: {type(e).__name__}: {e}")
                model_results = {}
                break

        if OPENROUTER_INTEGRATION_AVAILABLE and is_openrouter_available():
            openrouter_models = get_openrouter_models()
            if openrouter_models:
                selected_model = openrouter_models[0]
                option_prompt = list(prompts.values())[0] if prompts else ""
                try:
                    openrouter_result = await asyncio.wait_for(
                        call_openrouter_model(selected_model, option_prompt),
                        timeout=25.0
                    )
                    if openrouter_result:
                        display_name = selected_model.split('/')[-1]
                        model_results[f"openrouter_{display_name}"] = openrouter_result
                        print(f"✅ [OpenRouter] {display_name} 调用成功（{outcome_name}）")
                except Exception as e:
                    print(f"⚠️ [OpenRouter] {outcome_name} 调用异常: {type(e).__name__}")

        success_count = sum(1 for r in model_results.values() if r)
        expected_count = len(prompts) + (
            1 if OPENROUTER_INTEGRATION_AVAILABLE and is_openrouter_available() and get_openrouter_models() else 0
        )
        print(f"📥 {outcome_name} 收到 {success_count}/{expected_count} 个模型响应")
        if success_count == 0:
            print(f"  ⚠️ [WARNING] {outcome_name} 所有模型调用失败，将使用市场价格")
            print(f"  [DEBUG] 模型结果详情: {model_results}")
            print(f"  [DEBUG] 是否有结果: {bool(model_results)}, 结果数量: {len(model_results)}")
        else:
            print(f"  ✅ {outcome_name} 成功获得 {success_count} 个模型响应")

        return model_results

    def _fuse_multi_option_outcome(
        self,
        outcome: Dict,
        outcome_results: Dict[str, Optional[Dict[str, Any]]],
        model_weights: Dict[str, float],
        current_reasoning: Optional[str]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Fuse predictions (or fallback) for a single outcome."""
        outcome_name = outcome.get("name", "未知选项")
        print(f"[MULTI_FLOW] Fusing outcome: {outcome_name}")
        valid_count = sum(1 for r in outcome_results.values() if r is not None)

        if valid_count > 0:
            fusion_result = self.fusion_engine.fuse_predictions(
                model_results=outcome_results,
                model_weights=model_weights,
                market_prob=outcome["market_prob"],
                orchestrator=self.model_orchestrator
            )
            if not current_reasoning and fusion_result.get("deepseek_reasoning"):
                current_reasoning = fusion_result.get("deepseek_reasoning")

            final_prob = fusion_result.get("final_prob") or 0.0
            if final_prob is None:
                print(f"⚠️ final_prob is None for {outcome_name}, using default 0.0")
                final_prob = 0.0

            model_only_prob_value = fusion_result.get("model_only_prob")
            if model_only_prob_value is None:
                model_only_prob_display = "N/A"
            else:
                model_only_prob_value = model_only_prob_value or 0.0
                if model_only_prob_value is None:
                    print("⚙️ [SAFE] 修复空值保护: model_only_prob_display")
                    model_only_prob_value = 0.0
                model_only_prob_display = f"{(model_only_prob_value or 0.0):.1f}%"

            print(f"  ✅ 融合完成: {outcome_name} = {(final_prob or 0.0):.1f}% (AI: {model_only_prob_display})")

            fused_outcome = {
                "name": outcome_name,
                "prediction": fusion_result["final_prob"],
                "market_prob": outcome["market_prob"],
                "uncertainty": fusion_result["uncertainty"],
                "summary": fusion_result["summary"],
                "model_only_prob": fusion_result.get("model_only_prob"),
                "model_versions": fusion_result.get("model_versions", {}),
                "weight_source": fusion_result.get("weight_source", {}),
                "deepseek_reasoning": fusion_result.get("deepseek_reasoning")
            }
            return fused_outcome, current_reasoning

        if not outcome_results:
            reason = "无模型结果"
        elif valid_count == 0:
            reason = "所有模型调用失败/超时"
        else:
            reason = "无有效模型结果"

        market_prob = outcome.get("market_prob") or 0.0
        if market_prob is None:
            print(f"⚠️ market_prob is None for {outcome_name}, using default 0.0")
            market_prob = 0.0
        print(f"  ⚠️ 无AI预测: {outcome_name}（{reason}，有效结果数: {valid_count}），使用市场价格 {(market_prob or 0.0):.1f}%")

        fused_outcome = {
            "name": outcome_name,
            "prediction": outcome["market_prob"],
            "market_prob": outcome["market_prob"],
            "uncertainty": 10.0,
            "summary": f"⚠️ {reason}，暂无 AI 模型预测，显示市场价格",
            "model_only_prob": None
        }
        return fused_outcome, current_reasoning

    async def _finalize_multi_option_response(
        self,
        update: Update,
        event_data: Dict,
        fused_outcomes: List[Dict[str, Any]],
        raw_outcomes: List[Dict[str, Any]],
        full_analysis: Dict,
        deepseek_reasoning: Optional[str],
        model_names: List[str]
    ) -> None:
        """Normalize, format, and log multi-option predictions."""
        print("[MULTI_FLOW] Finalizing multi-option response")
        if not fused_outcomes and raw_outcomes:
            print(f"⚠️ fused_outcomes 为空，从原始 outcomes 创建 fallback 数据...")
            fused_outcomes.extend([{
                "name": outcome["name"],
                "prediction": outcome["market_prob"],
                "market_prob": outcome["market_prob"],
                "uncertainty": 10.0,
                "summary": "暂无 AI 模型预测，显示市场价格。",
                "model_only_prob": None
            } for outcome in raw_outcomes])
            print(f"✅ 创建了 {len(fused_outcomes)} 个 fallback outcomes")
        elif not fused_outcomes:
            print("❌ 严重错误：既没有 fused_outcomes 也没有 outcomes！")

        print(f"📊 归一化前 fused_outcomes 数量: {len(fused_outcomes)}")
        event_title = event_data.get("question", "")
        normalization_result = self.fusion_engine.normalize_all_predictions(
            fused_outcomes,
            event_title=event_title,
            event_rules=event_data.get("rules", ""),
            now_probabilities=[
                outcome.get("market_prob")
                for outcome in fused_outcomes
                if outcome.get("market_prob") is not None
            ]
        )

        fused_outcomes = normalization_result["normalized_outcomes"]

        print(f"📊 归一化结果:")
        total_before = normalization_result.get('total_before')
        total_after = normalization_result.get('total_after')
        error = normalization_result.get('error', 0)
        skipped_count = normalization_result.get('skipped_count', 0)

        try:
            if total_before is not None:
                total_before = total_before or 0.0
                if total_before is None:
                    print("⚙️ [SAFE] 修复空值保护: total_before")
                    total_before = 0.0
                print(f"   归一化前总和: {float(total_before or 0.0):.2f}%")
            else:
                print(f"   归一化前总和: N/A")

            if total_after is not None:
                total_after = total_after or 0.0
                if total_after is None:
                    print("⚙️ [SAFE] 修复空值保护: total_after")
                    total_after = 0.0
                print(f"   归一化后总和: {float(total_after or 0.0):.2f}%")
            else:
                print(f"   归一化后总和: N/A（条件事件未归一化）")

            if error is not None:
                error = error or 0.0
                if error is None:
                    print("⚙️ [SAFE] 修复空值保护: error")
                    error = 0.0
                print(f"   误差: {float(error or 0.0):.4f}%")
            else:
                print(f"   误差: N/A")

            print(f"   跳过选项: {skipped_count} 个")
        except (TypeError, ValueError):
            print("  ⚠️ 归一化结果数据格式错误，跳过格式化")
            print(f"   跳过选项: {skipped_count} 个")

        if normalization_result.get('total_after', 0) == 0 and normalization_result.get('total_before', 0) > 0:
            print(f"⚠️ [WARNING] 归一化异常：total_before={normalization_result['total_before']}，但 total_after=0")
        print(f"[DEBUG] normalization_result keys: {list(normalization_result.keys())}")
        print(f"[DEBUG] normalization_result['total_after'] = {normalization_result.get('total_after')}")

        print(f"📊 归一化后 fused_outcomes 数量: {len(fused_outcomes)}")

        trade_signal_info = None
        if fused_outcomes:
            def _diff_metric(outcome):
                ai_val = outcome.get("model_only_prob")
                if ai_val is None:
                    ai_val = outcome.get("prediction", 0.0)
                return abs((ai_val or 0.0) - (outcome.get("market_prob") or 0.0))

            top_outcome = max(fused_outcomes, key=_diff_metric)
            ai_prob_trade = top_outcome.get("model_only_prob")
            if ai_prob_trade is None:
                ai_prob_trade = top_outcome.get("prediction")
            market_prob_trade = top_outcome.get("market_prob")
            days_to_resolution = event_data.get("days_left") or 30
            uncertainty_ratio = (top_outcome.get("uncertainty") or 0.0) / 100.0
            trade_data = self.fusion_engine.evaluate_trade_signal(
                ai_prob_trade,
                market_prob_trade,
                days_to_resolution,
                uncertainty_ratio
            )
            print(
                f"[TRADE_SIGNAL] computed option={top_outcome.get('name', 'N/A')} "
                f"signal={trade_data.get('signal')} ev={trade_data.get('ev')}"
            )
            trade_signal_info = {
                **trade_data,
                "option": top_outcome.get("name", "N/A"),
                "option_id": top_outcome.get("id"),
                "option_slug": top_outcome.get("slug")
            }

        multi_option_fusion_result: Dict[str, Any] = {"deepseek_reasoning": deepseek_reasoning}
        if trade_signal_info:
            multi_option_fusion_result["trade_signal"] = trade_signal_info
            multi_option_fusion_result["ev"] = trade_signal_info.get("ev")
            multi_option_fusion_result["annualized_ev"] = trade_signal_info.get("annualized_ev")
            multi_option_fusion_result["risk_factor"] = trade_signal_info.get("risk_factor")
            multi_option_fusion_result["signal"] = trade_signal_info.get("signal")
            multi_option_fusion_result["signal_reason"] = trade_signal_info.get("signal_reason")

        output = self.output_formatter.format_multi_option_prediction(
            event_data=event_data,
            outcomes=fused_outcomes,
            normalization_info=normalization_result,
            fusion_result=multi_option_fusion_result,
            trade_signal=trade_signal_info
        )

        print(f"📤 准备发送输出，长度: {len(output)} 字符")
        await maybe_await(update.message.reply_text(
            output,
            parse_mode="Markdown"
        ))

        if self.notion_logger:
            if not self.notion_logger.enabled:
                print("⚠️ Notion Logger 未启用，跳过记录（多选项事件）")
        if self.notion_logger and self.notion_logger.enabled:
            try:
                aggregated_fusion_result = {
                    "summary": fused_outcomes[0].get("summary", "暂无摘要") if fused_outcomes else "暂无摘要",
                    "deepseek_reasoning": deepseek_reasoning,
                    "model_versions": None,
                    "weight_source": None
                }

                if fused_outcomes and len(fused_outcomes) > 0:
                    first_outcome = fused_outcomes[0]
                    if "model_versions" in first_outcome:
                        aggregated_fusion_result["model_versions"] = first_outcome["model_versions"]
                    if "weight_source" in first_outcome:
                        aggregated_fusion_result["weight_source"] = first_outcome["weight_source"]

                if "models" not in aggregated_fusion_result:
                    model_versions = aggregated_fusion_result.get("model_versions", {})
                    if model_versions:
                        aggregated_fusion_result["models"] = [
                            info.get("display_name", model_id)
                            for model_id, info in model_versions.items()
                        ]
                    else:
                        aggregated_fusion_result["models"] = model_names

                if "run_id" not in aggregated_fusion_result:
                    import uuid
                    aggregated_fusion_result["run_id"] = str(uuid.uuid4())

                event_data_for_notion = event_data.copy()
                if full_analysis:
                    event_data_for_notion["category"] = full_analysis.get(
                        "event_category_display",
                        full_analysis.get("event_category", "-")
                    )
                if "outcomes" not in event_data_for_notion and fused_outcomes:
                    event_data_for_notion["outcomes"] = [outcome.get("name", "-") for outcome in fused_outcomes[:1]]

                self.notion_logger.log_prediction(
                    event_data=event_data_for_notion,
                    fusion_result=aggregated_fusion_result,
                    full_analysis=full_analysis,
                    outcomes=fused_outcomes,
                    normalization_info=normalization_result,
                    trade_signal=None
                )
            except Exception as e:
                print(f"⚠️ Notion Logger 记录失败: {e}")

    async def handle_predict(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /predict command."""
        message_text = await self._prepare_prediction_context(update, context)
        if message_text is None:
            return

        self.logger.info("收到 /predict 请求: %s", message_text.strip()[:120])

        try:
            # Parse event
            event_info = self.event_manager.parse_event_from_message(message_text)
            
            if not event_info.get('query'):
                await maybe_await(update.message.reply_text(
                    "请提供要预测的事件。\n"
                    "用法: /predict <事件描述>\n"
                    "或: /predict <Polymarket链接>"
                ))
                return
            
            event_data = await self._fetch_event_data(update, event_info)

            low_probability_info = self.event_manager.filter_low_probability_event(event_data)
            if low_probability_info:
                notice_text = self.output_formatter.format_low_probability_notice(
                    event_data,
                    threshold=low_probability_info["threshold"],
                    max_probability=low_probability_info["max_probability"]
                )
                self.logger.warning(
                    "事件被过滤，原因：低概率 (question=%s, max_prob=%.2f, threshold=%.2f)",
                    event_data.get("question", "未知事件"),
                    low_probability_info["max_probability"],
                    low_probability_info["threshold"]
                )
                await maybe_await(update.message.reply_text(
                    notice_text,
                    parse_mode="Markdown"
                ))
                return

            (
                event_analysis,
                full_analysis,
                news_summary,
                model_names
            ) = await self._analyze_event(event_data, event_info)
            
            # Get model assignments from analysis
            # 全面分析事件（包含市场趋势、事件类别、舆情信号、规则摘要）
            # 添加超时保护，避免分析步骤阻塞主流程
            market_slug = event_info.get('slug')
            try:
                full_analysis = await asyncio.wait_for(
                    self.event_analyzer.analyze_event_full(
                        event_title=event_data.get("question", ""),
                        event_rules=event_data.get("rules", ""),
                        market_prob=event_data.get("market_prob"),
                        market_slug=market_slug
                    ),
                    timeout=15.0  # 分析步骤最多等待15秒
                )
            except asyncio.TimeoutError:
                print(f"⏱️ [WARNING] 事件分析超时，使用默认值")
                # 使用默认分析结果，不阻塞主流程
                full_analysis = {
                    "event_category": "general",
                    "event_category_display": "通用",
                    "market_trend": "数据不足，无法计算",
                    "sentiment_trend": "unknown",
                    "sentiment_score": 0.0,
                    "sentiment_sample": 0,
                    "sentiment_source": "未知",
                    "rules_summary": event_data.get("rules", "")[:100] if event_data.get("rules") else "无规则信息"
                }
            
            # 打印分析结果
            print(f"\n📊 事件全面分析:")
            print(f"  类别: {full_analysis['event_category']} ({full_analysis.get('event_category_display', '未知')})")
            print(f"  市场趋势: {full_analysis['market_trend']}")
            # 【防御】确保 sentiment_score 不为 None
            sentiment_score = full_analysis.get('sentiment_score') or 0.0
            if sentiment_score is None:
                print("⚠️ sentiment_score is None, using default 0.0")
                sentiment_score = 0.0
            print(f"  舆情: {full_analysis['sentiment_trend']} ({(sentiment_score or 0.0):+.2f}), "
                  f"样本: {full_analysis['sentiment_sample']} ({full_analysis['sentiment_source']})")
            print(f"  规则摘要: {full_analysis['rules_summary'][:60]}...")
            
            # 打印世界温度信息（如果可用）- 轻量描述模式
            world_temp_data = full_analysis.get("world_temp_data")
            if world_temp_data:
                description = world_temp_data.get("description", "未知")
                positive = world_temp_data.get("positive", 0)
                negative = world_temp_data.get("negative", 0)
                neutral = world_temp_data.get("neutral", 0)
                print(f"  🧠 世界情绪: {description}（正面: {positive}, 负面: {negative}, 中性: {neutral}）")
            elif full_analysis.get("world_sentiment_summary"):
                print(f"  🧠 世界情绪: {full_analysis['world_sentiment_summary'][:80]}...")
            
            # 异步获取新闻摘要（如果可用）
            # 【稳定性保护】添加超时和异常处理
            news_summary = None
            try:
                from src.openrouter_assistant import get_news_summary, OPENROUTER_ASSISTANT_ENABLED
                if OPENROUTER_ASSISTANT_ENABLED:
                    news_summary = await asyncio.wait_for(
                        get_news_summary(),
                        timeout=10.0  # 最多等待10秒
                    )
                    if news_summary:
                        print(f"  📰 新闻摘要: 已获取（{len(news_summary)} 字符）")
                else:
                    print("  ℹ️ [OPENROUTER] 功能未启用，跳过新闻摘要")
            except asyncio.TimeoutError:
                print(f"  ⏱️ [OPENROUTER] 获取新闻摘要超时（>10s），跳过")
                news_summary = None
            except ImportError as e:
                print(f"  ⚠️ [OPENROUTER] 模块导入失败: {e}")
                news_summary = None
            except Exception as e:
                print(f"  ⚠️ [OPENROUTER] 获取新闻摘要失败: {type(e).__name__}: {e}")
                news_summary = None
            
            # 保留原有的事件分析（用于模型分配）
            # Pass orchestrator to auto-fetch enabled models
            event_analysis = self.event_analyzer.analyze_event(
                event_data.get("question", ""),
                event_data.get("rules", ""),
                available_models=None,  # 让 analyze_event 自动从 orchestrator 获取
                orchestrator=self.model_orchestrator
            )
            
            print(f"\n📊 Event Category: {event_analysis['category']}")
            print(f"📐 Dimensions: {len(event_analysis['dimensions'])}")
            
            # Get model assignments from analysis
            model_assignments = event_analysis["model_assignments"]
            
            # 将全面分析结果添加到event_data中，供PromptBuilder和OutputFormatter使用
            event_data["full_analysis"] = full_analysis
            # 【集成】添加世界温度和新闻摘要到 event_data（供 prompt_builder 和 output_formatter 使用）
            # 轻量描述模式：world_temp 现在是描述字符串
            event_data["world_temp"] = full_analysis.get("world_temp")  # 描述字符串
            event_data["world_temp_data"] = full_analysis.get("world_temp_data")  # 完整数据
            event_data["world_sentiment_summary"] = full_analysis.get("world_sentiment_summary")
            event_data["news_summary"] = news_summary
            
            # Get available models (only those with API keys)
            all_models = list(model_assignments.keys())
            model_names = [
                model for model in all_models
                if model in self.model_orchestrator.get_available_models()
            ]
            
            if not model_names:
                await maybe_await(update.message.reply_text(
                    self.output_formatter.format_error(
                        "没有可用的 AI 模型。请至少配置一个 API 密钥。"
                    ),
                    parse_mode="Markdown"
                ))
                return
            
            # Check if this is a multi-option event
            if event_data.get("is_multi_option", False):
                # Multi-option event: predict each option separately
                outcomes = event_data.get("outcomes", [])
                print(f"\n🎯 多选项事件检测:")
                print(f"  is_multi_option: {event_data.get('is_multi_option', False)}")
                print(f"  outcomes数量: {len(outcomes)}")
                if len(outcomes) == 0:
                    print(f"  ⚠️ 警告：多选项事件但outcomes为空！")
                    print(f"  event_data keys: {list(event_data.keys())}")
                    # Try to reconstruct from markets if available
                    # This shouldn't happen, but let's add a fallback
                else:
                    print(f"  ✅ 前3个选项: {[o.get('name', 'N/A') for o in outcomes[:3]]}")
                
                await maybe_await(update.message.reply_text(
                    f"🔍 检测到多选项事件，共有 {len(outcomes)} 个选项\n"
                    f"🤖 正在为每个选项进行预测..."
                ))
                
                # Sequentially call models for each outcome
                outcome_predictions: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {}
                for outcome in outcomes:
                    outcome_name = outcome["name"]
                    print(f"\n🎯 处理选项: {outcome_name}")
                    prompts = self._gather_multi_option_prompts(
                        event_data=event_data,
                        model_assignments=model_assignments,
                        model_names=model_names,
                        outcome=outcome
                    )
                    if not prompts:
                        print("   ⚠️ 无可用模型，使用市场价格")
                        outcome_predictions[outcome_name] = {}
                        continue
                    
                    outcome_predictions[outcome_name] = await self._run_multi_option_models(
                        outcome_name=outcome_name,
                        prompts=prompts
                    )
                    await asyncio.sleep(0.5)
                
                # Fuse predictions for each outcome
                model_weights = {
                    model_name: self.model_orchestrator.get_model_weight(model_name)
                    for model_name in model_names
                }
                
                fused_outcomes: List[Dict[str, Any]] = []
                deepseek_reasoning: Optional[str] = None
                
                for outcome in outcomes:
                    outcome_name = outcome["name"]
                    outcome_results = outcome_predictions.get(outcome_name, {})
                    fused_outcome, deepseek_reasoning = self._fuse_multi_option_outcome(
                        outcome=outcome,
                        outcome_results=outcome_results,
                        model_weights=model_weights,
                        current_reasoning=deepseek_reasoning
                    )
                    fused_outcomes.append(fused_outcome)
                
                await self._finalize_multi_option_response(
                    update=update,
                    event_data=event_data,
                    fused_outcomes=fused_outcomes,
                    raw_outcomes=outcomes,
                    full_analysis=full_analysis,
                    deepseek_reasoning=deepseek_reasoning,
                    model_names=model_names
                )
            else:
                prompts = self._build_binary_prompts(
                    event_data=event_data,
                    model_assignments=model_assignments,
                    model_names=model_names
                )
                
                model_results = await self._call_binary_models(update, prompts)
                if model_results is None:
                    return
                
                await self._finalize_binary_prediction(
                    update=update,
                    event_data=event_data,
                    model_results=model_results,
                    model_names=model_names,
                    full_analysis=full_analysis
                )
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            self.logger.exception("handle_predict 处理异常: %s", error_msg)

            await maybe_await(update.message.reply_text(
                self.output_formatter.format_error(
                    f"处理请求时出错: {error_type}: {error_msg}"
                ),
                parse_mode="Markdown"
            ))
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_message = """
🤖 *Polymarket 预测机器人*

我可以使用多个 AI 模型预测 Polymarket 事件！

*使用方法:*
/predict <事件描述>

*示例:*
/predict Sora 会在 10 月 31 日成为美国 Apple App Store 免费应用排行榜第一名吗？

机器人将：
1. 从 Polymarket 获取市场数据
2. 查询多个 AI 模型（DeepSeek + OpenRouter）
3. 融合预测结果与市场概率
4. 提供详细的预测报告
        """
        await maybe_await(update.message.reply_text(
            welcome_message,
            parse_mode="Markdown"
        ))
    
    async def handle_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ping command for testing."""
        await maybe_await(update.message.reply_text("✅ Bot 正常运行！"))
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_message = """
*命令:*
/start - 启动机器人
/help - 显示帮助信息
/predict <事件> - 预测一个 Polymarket 事件

*工作原理:*
机器人使用多个 AI 模型的集成来进行预测：
- DeepSeek: 核心量化推理
- NVIDIA Nemotron: 市场分析
- DeepSeek (OpenRouter): 量化推理与市场分析

结果会与 Polymarket 市场概率融合，以提高准确性。
        """
        await maybe_await(update.message.reply_text(
            help_message,
            parse_mode="Markdown"
        ))


def list_models():
    """List all configured models and their versions."""
    from model_orchestrator import ModelOrchestrator
    
    orchestrator = ModelOrchestrator()
    
    print("=" * 80)
    print("🤖 当前配置的模型版本".center(80))
    print("=" * 80)
    
    models_summary = orchestrator.get_active_models_summary()
    
    print(f"\n{'模型名称':<25} {'模型ID':<30} {'更新时间':<12} {'权重':<8}")
    print("-" * 80)
    
    for model_id, info in models_summary.items():
        display_name = info.get("display_name", model_id)
        last_updated = info.get("last_updated", "未知")
        weight = info.get("weight", 0)
        print(f"{display_name:<25} {model_id:<30} {last_updated:<12} {weight:<8.1f}")
    
    print("\n" + "=" * 80)
    print("📊 模型统计".center(80))
    print("=" * 80)
    print(f"总模型数: {len(models_summary)}")
    
    # Show default model
    default_models = [
        model_id for model_id, info in orchestrator.MODELS.items()
        if info.get("is_default", False)
    ]
    if default_models:
        print(f"默认模型: {', '.join(default_models)}")
    
    print("\n" + "=" * 80)


REQUIRED_ENV_VARS = (
    "TELEGRAM_BOT_TOKEN",
    "AICANAPI_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
    "NOTION_TOKEN",
    "NOTION_DB_ID"
    # POLYMARKET_API_KEY is optional - system works without it
)


def _validate_required_environment() -> None:
    """Ensure all critical environment variables exist before bootstrapping."""
    missing = [key for key in REQUIRED_ENV_VARS if not os.environ.get(key)]
    if missing:
        missing_list = ", ".join(missing)
        sys.exit(f"Error: Missing required environment variable(s): {missing_list}")


def main():
    """Main entry point."""
    load_dotenv()
    _validate_required_environment()
    
    # Check for --list-models command early to support offline diagnostics
    if len(sys.argv) > 1 and sys.argv[1] == "--list-models":
        list_models()
        return
    
    if not TELEGRAM_AVAILABLE:
        print("🛑 Telegram 依赖未安装，机器人无法启动。请运行: pip install python-telegram-bot==13.15")
        print(f"   原始错误: {TELEGRAM_IMPORT_ERROR}")
        return
    
    # 【新增】检查并更新 LMArena 权重（仅在启动时）
    if LMARENA_UPDATE_AVAILABLE:
        try:
            if should_update():
                print(f"\n[LMArena] 检测到权重文件需要更新，开始刷新...")
                update_success = update_lmarena_weights()
                if not update_success:
                    print(f"[LMArena] 拉取失败，使用旧权重")
            else:
                print(f"[LMArena] 权重文件仍然有效，跳过更新")
        except Exception as e:
            print(f"⚠️ [LMArena] 自动更新权重时出错: {type(e).__name__}: {e}")
            print(f"   继续使用现有权重文件")
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment variables.")
        print("Please create a .env file with your Telegram bot token.")
        return
    
    # Create bot instance
    bot = ForecastingBot()
    
    # Create application
    try:
        # apscheduler 时区问题已在模块导入时修补
        builder = Application.builder().token(token)
        application = builder.build()
        
        # Register handlers
        application.add_handler(CommandHandler("start", wrap_async_handler(bot.handle_start)))
        application.add_handler(CommandHandler("help", wrap_async_handler(bot.handle_help)))
        application.add_handler(CommandHandler("ping", wrap_async_handler(bot.handle_ping)))
        application.add_handler(CommandHandler("predict", wrap_async_handler(bot.handle_predict)))
        
        # Handle direct Polymarket URLs - check both text and entities
        async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle messages containing Polymarket URLs."""
            print(f"\n🔍 [URL Handler] 收到消息，检查是否为 URL...")
            
            if not update.message:
                print(f"⚠️ [URL Handler] update.message 为空")
                return
            
            text = update.message.text or ""
            print(f"📝 [URL Handler] 消息文本: {text[:100]}...")
            print(f"📝 [URL Handler] 消息文本长度: {len(text)}")
            
            # Method 1: Check text content directly
            has_polymarket_url = False
            if text:
                try:
                    has_polymarket_url = 'polymarket.com' in text.lower()
                    if has_polymarket_url:
                        print(f"✅ [URL Handler] 从文本内容检测到 Polymarket URL")
                except Exception as e:
                    print(f"⚠️ [URL Handler] 检查文本内容时出错: {e}")
            
            # Method 2: Check message entities (URL links, text links, etc.)
            if not has_polymarket_url and update.message.entities:
                print(f"🔍 [URL Handler] 检查消息实体，数量: {len(update.message.entities)}")
                try:
                    from telegram import MessageEntity
                    for entity in update.message.entities:
                        print(f"   - 实体类型: {entity.type}, offset: {entity.offset}, length: {entity.length}")
                        if entity.type in [MessageEntity.URL, MessageEntity.TEXT_LINK]:
                            # Extract URL from entity
                            if entity.type == MessageEntity.URL:
                                url_text = text[entity.offset:entity.offset + entity.length]
                                print(f"   ✅ 找到 URL 实体: {url_text[:80]}")
                            elif entity.type == MessageEntity.TEXT_LINK:
                                url_text = entity.url
                                print(f"   ✅ 找到 TEXT_LINK 实体: {url_text[:80]}")
                            else:
                                continue
                            
                            if url_text and 'polymarket.com' in url_text.lower():
                                has_polymarket_url = True
                                print(f"✅ [URL Handler] 从消息实体检测到 URL: {url_text[:80]}")
                                break
                except Exception as e:
                    print(f"⚠️ [URL Handler] 检查消息实体时出错: {e}")
                    import traceback
                    traceback.print_exc()
            
            if has_polymarket_url:
                print(f"✅ [URL Handler] 检测到 Polymarket URL，开始处理...")
                try:
                    await bot.handle_predict(update, context)
                except Exception as e:
                    print(f"❌ [URL Handler] 调用 handle_predict 时出错: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"ℹ️ [URL Handler] 未检测到 Polymarket URL，跳过处理")
        
        # Add handler for URLs - register with lower priority (group=1)
        application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                wrap_async_handler(handle_url_message)
            ),
            group=1
        )
        
        # Add error handler
        async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
            """Log the error and send a message to the user."""
            import traceback
            error = context.error
            print(f"\n❌ Exception while handling an update:")
            print(f"   错误类型: {type(error).__name__}")
            print(f"   错误信息: {error}")
            traceback.print_exc()
            
            # Try to send error message to user if possible
            if update and hasattr(update, 'message') and update.message:
                try:
                    await maybe_await(context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text=f"❌ 处理消息时出错: {type(error).__name__}\n请稍后重试或使用 /help 查看帮助。"
                    ))
                except:
                    pass
        
        application.add_error_handler(wrap_async_handler(error_handler))
        
        # Start bot
        print("=" * 50)
        print("🤖 Polymarket 预测机器人")
        print("=" * 50)
        print(f"✅ Bot Token: {token[:10]}...")
        print("✅ 机器人正在启动...")
        print("✅ 等待消息...")
        print("=" * 50)
        print("\n💡 提示：在 Telegram 中找到你的 Bot 并发送 /start")
        print("=" * 50)
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except Exception as e:
        print(f"❌ 启动机器人时出错: {e}")
        import traceback
        traceback.print_exc()
        print("\n请检查：")
        print("1. Bot Token 是否正确")
        print("2. 网络连接是否正常")
        print("3. 是否能够访问 Telegram API")


def test_notion_write():
    """测试 Notion 写入功能"""
    print("\n" + "=" * 60)
    print("🧪 测试 Notion 写入功能")
    print("=" * 60)
    
    try:
        from notion_logger import NotionLogger
        
        notion_logger = NotionLogger(
            notion_token=os.getenv("NOTION_TOKEN"),
            database_id=os.getenv("NOTION_DB_ID")
        )
        
        if not notion_logger.enabled:
            print("⚠️ Notion Logger 未启用，跳过测试")
            return
        
        print("✅ Notion Logger 已初始化")
        
        # 测试数据
        test_event_data = {
            "question": "Notion 测试写入",
            "market_prob": 0.25,
            "category": "system",
            "rules": "写入测试"
        }
        
        test_fusion_result = {
            "model_only_prob": 0.35,
            "final_prob": 0.33,
            "summary": "测试是否能成功写入 Notion。",
            "model_versions": {
                "gpt-4o": {"display_name": "GPT-4o"},
                "claude-3-7-sonnet-latest": {"display_name": "Claude"}
            },
            "run_id": "test-001"
        }
        
        print(f"📝 正在写入测试数据...")
        result = notion_logger.log_prediction(
            event_data=test_event_data,
            fusion_result=test_fusion_result,
            full_analysis={"event_category": "system", "rules_summary": "写入测试"},
            outcomes=None,
            normalization_info=None,
            trade_signal=None
        )
        
        if result:
            print(f"✅ 成功写入 Notion: {test_event_data.get('question')}")
            print(f"💡 请前往数据库查看: https://www.notion.so/{notion_logger.database_id}")
        else:
            print(f"❌ 写入失败")
            
    except Exception as e:
        print(f"❌ 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 检查是否有命令行参数来运行测试
    if len(sys.argv) > 1 and sys.argv[1] == "--test-notion":
        test_notion_write()
    else:
        main()
