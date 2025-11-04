"""
Event Analyzer: 全面升级版
包含：市场趋势、事件类别、舆情信号、规则摘要、世界温度
支持缓存和限流机制以节省API额度
"""
import re
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from urllib.parse import quote_plus
import os
import sys
from dotenv import load_dotenv

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

# 导入世界情绪引擎和新闻摘要
try:
    from src.world_sentiment_engine import compute_world_temperature, get_world_temperature_summary
    from src.openrouter_assistant import get_news_summary
    WORLD_TEMP_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 世界温度模块导入失败: {e}")
    WORLD_TEMP_AVAILABLE = False


class EventAnalyzer:
    """全面升级的事件分析器，包含市场趋势、事件类别、舆情信号、规则摘要"""
    
    # Model specialization mapping
    MODEL_SPECIALIZATIONS = {
        "gpt-4o": {
            "name": "综合逻辑分析",
            "dimensions": ["逻辑推理", "综合分析", "可能性评估"],
            "weight": 3.0
        },
        "claude-3-7-sonnet-latest": {
            "name": "风险与批判性思维",
            "dimensions": ["风险评估", "批判性分析", "陷阱识别"],
            "weight": 2.5
        },
        "claude-3-5-opus-latest": {
            "name": "风险与批判性思维 (Opus)",
            "dimensions": ["风险评估", "批判性分析", "陷阱识别"],
            "weight": 2.25
        },
        "deepseek-chat": {
            "name": "深度推理与量化分析",
            "dimensions": ["深度推理", "量化分析", "数学建模", "逻辑链分析"],
            "weight": 2.0
        },
        "gemini-2.5-pro": {
            "name": "模式识别与数据",
            "dimensions": ["历史模式", "数据类比", "趋势识别"],
            "weight": 2.0
        },
        "gemini-2.5-flash": {
            "name": "模式识别与数据 (Flash)",
            "dimensions": ["历史模式", "数据类比", "趋势识别"],
            "weight": 1.8
        },
        "grok-4": {
            "name": "另类视角",
            "dimensions": ["市场情绪", "另类观点", "黑天鹅因素"],
            "weight": 2.0
        },
        "grok-3": {
            "name": "另类视角 (v3)",
            "dimensions": ["市场情绪", "另类观点", "黑天鹅因素"],
            "weight": 1.8
        }
    }
    
    # Event category keywords mapping (中文 -> 英文)
    EVENT_CATEGORIES = {
        "geopolitics": {
            "keywords": ["election", "president", "russia", "china", "war", "conflict", "ceasefire", 
                        "ukraine", "taiwan", "israel", "palestine", "geopolitical", "jinping", "xi",
                        "trump", "biden", "leader", "government", "political", "power"],
            "display_name": "地缘政治"
        },
        "economy": {
            "keywords": ["gdp", "inflation", "rate", "fed", "unemployment", "economy", "market", 
                        "stock", "crypto", "bitcoin", "financial"],
            "display_name": "经济指标"
        },
        "tech": {
            "keywords": ["apple", "google", "gpt", "ai", "gemini", "release", "launch", "product", 
                        "iphone", "app store", "technology"],
            "display_name": "科技产品"
        },
        "social": {
            "keywords": ["protest", "pandemic", "health", "disaster", "earthquake", "disease"],
            "display_name": "社会事件"
        },
        "sports": {
            "keywords": ["world cup", "olympics", "championship", "tournament", "nba", "nfl"],
            "display_name": "体育赛事"
        }
    }
    
    # API配置
    GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
    NEWSAPI_URL = "https://newsapi.org/v2/everything"
    MEDIASTACK_URL = "http://api.mediastack.com/v1/news"
    
    NEWSAPI_KEY = "f085b39aba844082b0c4485ca5772467"
    MEDIASTACK_KEY = "1798203edaccb3399bdb738bf0cc10fe"
    
    # 限流配置
    RATE_LIMIT_INTERVAL = 30  # 秒
    NEWSAPI_HOURLY_LIMIT = 20
    MEDIASTACK_HOURLY_LIMIT = 20
    
    # 缓存配置
    CACHE_DURATION_HOURS = 3
    CACHE_FILE = Path(__file__).parent.parent / "sentiment_cache.json"
    
    def __init__(self):
        """初始化EventAnalyzer，加载缓存和限流记录"""
        self.sentiment_cache = self._load_sentiment_cache()
        self.rate_limit_log = self._load_rate_limit_log()
        self.last_api_call = {}  # {api_name: timestamp}
        
    def _load_sentiment_cache(self) -> Dict:
        """加载舆情缓存"""
        try:
            if self.CACHE_FILE.exists():
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载缓存失败: {e}")
        return {}
    
    def _save_sentiment_cache(self):
        """保存舆情缓存"""
        try:
            with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.sentiment_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存缓存失败: {e}")
    
    def _load_rate_limit_log(self) -> Dict:
        """加载限流记录"""
        rate_file = Path(__file__).parent.parent / "rate_limit_log.json"
        try:
            if rate_file.exists():
                with open(rate_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {
            "newsapi": {"calls": [], "hourly_count": 0, "reset_time": None},
            "mediastack": {"calls": [], "hourly_count": 0, "reset_time": None}
        }
    
    def _save_rate_limit_log(self):
        """保存限流记录"""
        rate_file = Path(__file__).parent.parent / "rate_limit_log.json"
        try:
            with open(rate_file, 'w', encoding='utf-8') as f:
                json.dump(self.rate_limit_log, f, indent=2)
        except Exception as e:
            print(f"⚠️ 保存限流记录失败: {e}")
    
    def _check_cache(self, keyword: str) -> Optional[Dict]:
        """检查缓存，3小时内有效"""
        if keyword not in self.sentiment_cache:
            return None
        
        cached = self.sentiment_cache[keyword]
        timestamp = datetime.fromisoformat(cached["timestamp"])
        now = datetime.now()
        
        if (now - timestamp).total_seconds() < self.CACHE_DURATION_HOURS * 3600:
            print(f"✅ 使用缓存数据（关键词：{keyword}）")
            return cached
        
        # 缓存过期，删除
        del self.sentiment_cache[keyword]
        return None
    
    def _check_rate_limit(self, api_name: str) -> bool:
        """检查限流"""
        if api_name not in self.rate_limit_log:
            return True
        
        log = self.rate_limit_log[api_name]
        now = datetime.now()
        
        # 检查是否超过最小间隔
        if api_name in self.last_api_call:
            elapsed = (now - self.last_api_call[api_name]).total_seconds()
            # 【防御】确保 elapsed 不为 None
            elapsed = elapsed or 0.0
            if elapsed is None:
                print("⚙️ [SAFE] 修复空值保护: elapsed")
                elapsed = 0.0
            if elapsed < self.RATE_LIMIT_INTERVAL:
                print(f"⏸️ {api_name} 限流：距离上次调用仅 {(elapsed or 0.0):.1f} 秒")
                return False
        
        # 检查每小时调用次数
        if log.get("reset_time"):
            reset_time = datetime.fromisoformat(log["reset_time"])
            if now > reset_time:
                # 重置计数器
                log["calls"] = []
                log["hourly_count"] = 0
        
        hourly_limit = self.NEWSAPI_HOURLY_LIMIT if api_name == "newsapi" else self.MEDIASTACK_HOURLY_LIMIT
        
        if log.get("hourly_count", 0) >= hourly_limit:
            print(f"⏸️ {api_name} 限流：已达到每小时 {hourly_limit} 次限制")
            return False
        
        return True
    
    def _update_rate_limit(self, api_name: str):
        """更新限流记录"""
        if api_name not in self.rate_limit_log:
            self.rate_limit_log[api_name] = {"calls": [], "hourly_count": 0, "reset_time": None}
        
        log = self.rate_limit_log[api_name]
        now = datetime.now()
        
        log["calls"].append(now.isoformat())
        log["hourly_count"] = len([c for c in log["calls"] 
                                  if (now - datetime.fromisoformat(c)).total_seconds() < 3600])
        
        # 设置重置时间（下一个整点）
        reset_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        log["reset_time"] = reset_time.isoformat()
        
        self.last_api_call[api_name] = now
        self._save_rate_limit_log()
    
    async def analyze_event_full(
        self,
        event_title: str,
        event_rules: str = "",
        market_prob: Optional[float] = None,
        market_slug: Optional[str] = None
    ) -> Dict:
        """
        全面分析事件，返回所有信号
        
        Returns:
            {
                "event_title": str,
                "event_category": str,  # geopolitics, economy, tech, social, sports, general
                "market_trend": str,    # "+12.4%" or "数据不足"
                "sentiment_trend": str,  # "positive", "negative", "neutral", "unknown"
                "sentiment_score": float,
                "sentiment_sample": int,
                "sentiment_source": str,  # "GDELT", "NewsAPI", "Mediastack"
                "rules_summary": str,
                "current_market_prob": float
            }
        """
        event_lower = event_title.lower()
        
        # 1. 事件类别
        event_category = self._detect_category(event_lower)
        
        # 2. 市场趋势（异步，可能需要一些时间）
        market_trend = await self._get_market_trend(market_slug, market_prob) if market_slug else "数据不足，无法计算"
        
        # 3. 舆情信号（异步，带缓存）
        # 优化：根据样本数量调整舆情信号的影响力权重
        sentiment_data = await self._get_sentiment_signal(event_title)
        
        # 权重已在 _get_sentiment_signal() 中计算，这里不再重复计算
        
        # 4. 规则摘要
        rules_summary = self._extract_rules_summary(event_rules)
        
        # 5. 世界温度计算（新增）
        world_temp_data = None
        world_sentiment_summary = None
        if WORLD_TEMP_AVAILABLE:
            try:
                world_temp_data = compute_world_temperature()
                if world_temp_data:
                    world_sentiment_summary = get_world_temperature_summary(world_temp_data)
            except Exception as e:
                print(f"⚠️ 计算世界温度时出错: {type(e).__name__}: {e}")
                world_temp_data = None
                world_sentiment_summary = None
        
        result = {
            "event_title": event_title,
            "event_category": event_category,
            "market_trend": market_trend,
            "sentiment_trend": sentiment_data.get("sentiment", "unknown"),
            "sentiment_score": sentiment_data.get("score", 0.0),
            "sentiment_sample": sentiment_data.get("sample_count", 0),
            "sentiment_source": sentiment_data.get("source", "未知"),
            "rules_summary": rules_summary,
            "current_market_prob": market_prob,
            # 【轻量描述模式】world_temp 现在存储描述字符串，而不是数值
            "world_temp": world_temp_data.get("description") if world_temp_data else None,
            "world_temp_data": world_temp_data,  # 完整数据（包含 description, positive, negative, neutral）
            "world_sentiment_summary": world_sentiment_summary
        }
        
        return result
    
    def _detect_category(self, event_text: str) -> str:
        """
        检测事件类别，优化后的版本，扩展了 geopolitics 类关键词
        """
        event_text = event_text.lower()
        
        categories = {
            "geopolitics": [
                "war", "conflict", "invasion", "president", "election",
                "government", "military", "coup", "regime", "dictator",
                "venezuela", "maduro", "putin", "xi jinping", "biden",
                "sanction", "parliament"
            ],
            "economy": [
                "gdp", "inflation", "unemployment", "rate", "market",
                "recession", "interest", "fed", "stocks", "bond"
            ],
            "tech": [
                "launch", "release", "product", "ai", "openai", "gemini",
                "gpt", "apple", "tesla", "meta", "chip"
            ],
            "social": [
                "disaster", "pandemic", "health", "disease", "education",
                "crime", "migration", "protest"
            ],
            "sports": [
                "world cup", "olympics", "championship", "tournament"
            ],
        }
        
        for category, keywords in categories.items():
            if any(k in event_text for k in keywords):
                return category
        
        return "general"
    
    def _get_category_display_name(self, category_id: str) -> str:
        """获取类别显示名称"""
        return self.EVENT_CATEGORIES.get(category_id, {}).get("display_name", "通用事件")
    
    async def _get_market_trend(self, market_slug: str, current_prob: Optional[float]) -> str:
        """
        获取市场趋势（过去7天）
        快速失败机制：若数据不足或接口慢，立即返回，不阻塞主流程
        """
        if not market_slug or current_prob is None:
            return "新市场，数据不足"
        
        try:
            # 设置快速超时（5秒），避免长时间等待历史数据
            TREND_TIMEOUT = 5
            
            # 尝试从Polymarket API获取历史数据
            # 注意：Polymarket API可能不直接提供历史价格，这里使用简化逻辑
            # 实际实现可能需要通过CLOB API或其他数据源
            
            # 暂时返回占位符，实际需要实现历史数据获取逻辑
            # TODO: 实现真实的历史价格获取
            
            # 快速检查：如果是新市场（slug包含特定标识），立即返回
            # 这里可以添加实际的历史数据获取逻辑，但必须有超时保护
            await asyncio.sleep(0.1)  # 占位符，实际应该是API调用
            
            # 模拟：假设我们无法获取真实历史数据
            return "新市场，数据不足"
            
        except asyncio.TimeoutError:
            print(f"⏱️ [WARNING] 市场趋势数据获取超时，跳过")
            return "新市场，数据不足"
        except Exception as e:
            print(f"⚠️ [WARNING] 获取市场趋势失败: {type(e).__name__}: {e}")
            return "新市场，数据不足"
    
    async def _get_sentiment_signal(self, event_title: str) -> Dict:
        """
        获取舆情信号，优先级：GDELT → NewsAPI → Mediastack
        添加快速失败机制，避免长时间等待
        """
        # 提取关键词（简化：使用事件标题的主要部分）
        keywords = self._extract_keywords(event_title)
        keyword_str = " ".join(keywords[:3])  # 使用前3个关键词
        
        # 检查缓存（优先使用缓存，避免API调用）
        cached = self._check_cache(keyword_str)
        if cached:
            print(f"📊 使用缓存的舆情数据: {cached['source']}")
            sentiment_data = {
                "sentiment": cached["sentiment"],
                "score": cached["score"],
                "sample_count": cached.get("sample_count", 0),
                "source": cached["source"]
            }
            # 根据样本数量调整权重和计算调整后的趋势
            sample_count = sentiment_data.get("sample_count", 0)
            if sample_count < 30:
                sentiment_data["weight"] = 0.2
            elif sample_count < 100:
                sentiment_data["weight"] = 0.6
            else:
                sentiment_data["weight"] = 1.0
            
            sentiment_data["adjusted_trend"] = sentiment_data["score"] * sentiment_data["weight"]
            return sentiment_data
        
        # 设置每个API调用的超时时间（快速失败）
        API_TIMEOUT = 8  # 每个API最多等待8秒
        
        # 按优先级尝试各个API（快速失败机制）
        async def fetch_with_timeout(source_name: str, coro):
            try:
                data = await asyncio.wait_for(coro, timeout=API_TIMEOUT)
                return source_name, data
            except asyncio.TimeoutError:
                print(f"⏱️ [WARNING] {source_name.upper()} API 超时（>{API_TIMEOUT}s），跳过")
                return source_name, None
            except Exception as e:
                print(f"⚠️ [WARNING] {source_name.upper()} API 失败: {type(e).__name__}: {e}")
                return source_name, None
        
        source_results = {}
        tasks = []
        # Always attempt GDELT
        tasks.append(fetch_with_timeout("gdelt", self._fetch_gdelt_sentiment(keyword_str)))
        
        # Conditionally schedule NewsAPI / Mediastack based on rate limits
        newsapi_allowed = self._check_rate_limit("newsapi")
        mediastack_allowed = self._check_rate_limit("mediastack")
        if newsapi_allowed:
            tasks.append(fetch_with_timeout("newsapi", self._fetch_newsapi_sentiment(keyword_str)))
        else:
            source_results["newsapi"] = None
        if mediastack_allowed:
            tasks.append(fetch_with_timeout("mediastack", self._fetch_mediastack_sentiment(keyword_str)))
        else:
            source_results["mediastack"] = None
        
        fetched = await asyncio.gather(*tasks, return_exceptions=False)
        for source_name, data in fetched:
            source_results[source_name] = data
        
        def prepare_result(data: Optional[Dict]) -> Optional[Dict]:
            if not data:
                return None
            sample_count = data.get("sample_count", 0)
            if sample_count < 30:
                data["weight"] = 0.2
            elif sample_count < 100:
                data["weight"] = 0.6
            else:
                data["weight"] = 1.0
            data["adjusted_trend"] = data.get("score", 0.0) * data["weight"]
            return data
        
        # Priority order
        if source_results.get("gdelt") and source_results["gdelt"].get("sample_count", 0) >= 5:
            prepared = prepare_result(source_results["gdelt"])
            if prepared:
                self._save_to_cache(keyword_str, prepared)
                return prepared
        
        if newsapi_allowed and source_results.get("newsapi"):
            prepared = prepare_result(source_results["newsapi"])
            if prepared:
                self._update_rate_limit("newsapi")
                self._save_to_cache(keyword_str, prepared)
                return prepared
        
        if mediastack_allowed and source_results.get("mediastack"):
            prepared = prepare_result(source_results["mediastack"])
            if prepared:
                self._update_rate_limit("mediastack")
                self._save_to_cache(keyword_str, prepared)
                return prepared
        
        # 所有API都失败或超时，返回默认值（不阻塞流程）
        print(f"⚠️ 所有舆情API调用失败，使用默认值")
        sentiment_data = {
            "sentiment": "unknown",
            "score": 0.0,
            "sample_count": 0,
            "source": "未知"
        }
        
        # 根据样本数量调整权重和计算调整后的趋势
        sample_count = sentiment_data.get("sample_count", 0)
        if sample_count < 30:
            sentiment_data["weight"] = 0.2
        elif sample_count < 100:
            sentiment_data["weight"] = 0.6
        else:
            sentiment_data["weight"] = 1.0
        
        sentiment_data["adjusted_trend"] = sentiment_data["score"] * sentiment_data["weight"]
        
        return sentiment_data
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从事件标题提取关键词"""
        # 移除标点，转为小写，分词
        clean_text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = clean_text.split()
        
        # 移除常见停用词
        stopwords = {'will', 'be', 'in', 'by', 'the', 'a', 'an', 'and', 'or', 'to', 'of', 'for'}
        keywords = [w for w in words if len(w) > 2 and w not in stopwords]
        
        return keywords[:5]  # 返回前5个关键词
    
    async def _fetch_gdelt_sentiment(self, keyword: str) -> Optional[Dict]:
        """从GDELT获取舆情"""
        try:
            url = f"{self.GDELT_URL}?query={quote_plus(keyword)}&mode=ArtList&format=json&maxrecords=20"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        articles = data.get("articles", [])
                        
                        if len(articles) >= 5:
                            # 简化：计算平均情感（GDELT可能不直接提供情感分数）
                            # 这里使用文章数量作为代理指标
                            score = 0.0  # 默认中性
                            sentiment = "neutral"
                            
                            return {
                                "sentiment": sentiment,
                                "score": score,
                                "sample_count": len(articles),
                                "source": "GDELT"
                            }
        except Exception as e:
            print(f"⚠️ GDELT API错误: {e}")
        
        return None
    
    async def _fetch_newsapi_sentiment(self, keyword: str) -> Optional[Dict]:
        """从NewsAPI获取舆情"""
        try:
            url = f"{self.NEWSAPI_URL}?q={quote_plus(keyword)}&language=en&sortBy=publishedAt&apiKey={self.NEWSAPI_KEY}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        articles = data.get("articles", [])
                        
                        if articles:
                            # 简化：计算平均情感（NewsAPI不直接提供情感分数，需要NLP分析）
                            # 这里使用占位逻辑
                            score = 0.05  # 示例：轻微正面
                            sentiment = "neutral"
                            
                            return {
                                "sentiment": sentiment,
                                "score": score,
                                "sample_count": len(articles),
                                "source": "NewsAPI"
                            }
                    else:
                        print(f"⚠️ NewsAPI返回状态码: {response.status}")
        except Exception as e:
            print(f"⚠️ NewsAPI错误: {e}")
        
        return None
    
    async def _fetch_mediastack_sentiment(self, keyword: str) -> Optional[Dict]:
        """从Mediastack获取舆情"""
        try:
            url = f"{self.MEDIASTACK_URL}?access_key={self.MEDIASTACK_KEY}&keywords={keyword}&languages=en"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        articles = data.get("data", [])
                        
                        if articles:
                            # 简化：计算平均情感
                            score = -0.1  # 示例：轻微负面
                            sentiment = "neutral"
                            
                            return {
                                "sentiment": sentiment,
                                "score": score,
                                "sample_count": len(articles),
                                "source": "Mediastack"
                            }
        except Exception as e:
            print(f"⚠️ Mediastack错误: {e}")
        
        return None
    
    def _save_to_cache(self, keyword: str, result: Dict):
        """保存结果到缓存"""
        self.sentiment_cache[keyword] = {
            "keyword": keyword,
            "sentiment": result["sentiment"],
            "score": result["score"],
            "sample_count": result.get("sample_count", 0),
            "source": result["source"],
            "timestamp": datetime.now().isoformat()
        }
        self._save_sentiment_cache()
    
    def _extract_rules_summary(self, rules: str) -> str:
        """
        提取规则摘要，优化版本：提取完整句子
        """
        if not rules:
            return "⚠️ 未找到市场规则"
        
        rules = re.sub(r'\s+', ' ', rules.strip())
        
        match = re.search(r'([A-Z][^.?!]*[.?!])', rules)
        if match:
            summary = match.group(1)
        else:
            summary = rules[:180] + ("..." if len(rules) > 180 else "")
        
        return summary
    
    # 保留原有的 analyze_event 方法以保持兼容性
    def analyze_event(self, event_title: str, event_rules: str = "", available_models: List[str] = None, orchestrator=None) -> Dict:
        """
        原有的分析方法（保持向后兼容）
        
        Args:
            event_title: Event title to analyze
            event_rules: Event rules/description (optional)
            available_models: Optional list of available model IDs (from orchestrator, already filtered)
            orchestrator: Optional ModelOrchestrator instance to auto-fetch enabled models
        
        Returns:
            Dict with model assignments and specialized prompts
        """
        # Auto-fetch available models from orchestrator if not provided
        if available_models is None:
            if orchestrator is not None and hasattr(orchestrator, 'MODELS'):
                available_models = list(orchestrator.MODELS.keys())
                print(f"[DEBUG] Auto-fetched {len(available_models)} models from orchestrator: {available_models}")
            else:
                # Default fallback list (commonly enabled models)
                available_models = ["gpt-4o", "claude-3-7-sonnet-latest", "gemini-2.5-pro", "deepseek-chat"]
                print(f"[DEBUG] Using default model list (orchestrator not available): {available_models}")
        
        event_lower = event_title.lower()
        event_category = self._detect_category(event_lower)
        dimensions = self._get_dimensions_for_category(event_category, event_lower)
        # Filter by available_models to skip disabled models (e.g., Grok)
        model_assignments = self._assign_models_to_dimensions(dimensions, available_models=available_models)
        
        return {
            "category": self._get_category_display_name(event_category),
            "category_id": event_category,
            "dimensions": dimensions,
            "model_assignments": model_assignments
        }
    
    def _get_dimensions_for_category(self, category: str, event_text: str) -> List[str]:
        """Get relevant dimensions based on event category."""
        # 映射英文类别到中文
        category_map = {
            "geopolitics": "地缘政治",
            "economy": "经济指标",
            "tech": "科技产品",
            "social": "社会事件",
            "sports": "体育赛事",
            "general": "通用事件"
        }
        chinese_category = category_map.get(category, "通用事件")
        
        dimension_map = {
            "地缘政治": [
                {
                    "name": "政治因素分析",
                    "description": "分析相关的政治因素，包括政策变化、领导人决策、国际关系等",
                    "model": "gpt-4o"
                },
                {
                    "name": "风险评估",
                    "description": "评估冲突升级、意外事件、黑天鹅事件的风险",
                    "model": "claude-3-7-sonnet-latest"
                },
                {
                    "name": "深度推理与逻辑链分析",
                    "description": "通过深度推理和逻辑链分析，量化评估政治事件的可能性",
                    "model": "deepseek-chat"
                },
                {
                    "name": "历史模式对比",
                    "description": "对比类似历史事件的结果模式，寻找可类比的情况",
                    "model": "gemini-2.5-pro"
                },
                {
                    "name": "市场情绪与另类视角",
                    "description": "分析市场情绪、舆论走向、以及可能被忽视的另类因素",
                    "model": "grok-4"
                }
            ],
            "科技产品": [
                {
                    "name": "技术可行性分析",
                    "description": "分析技术实现的可行性、时间线、技术障碍等",
                    "model": "gpt-4o"
                },
                {
                    "name": "量化分析与数学建模",
                    "description": "通过量化分析和数学建模，精确评估技术实现的时间概率和市场影响",
                    "model": "deepseek-chat"
                },
                {
                    "name": "市场反应预测",
                    "description": "预测产品发布后的市场反应、用户接受度、竞争影响",
                    "model": "grok-4"
                },
                {
                    "name": "历史发布模式",
                    "description": "对比类似产品的历史发布模式、延迟原因、成功因素",
                    "model": "gemini-2.5-pro"
                },
                {
                    "name": "风险评估",
                    "description": "识别可能的技术风险、市场风险、监管风险",
                    "model": "claude-3-7-sonnet-latest"
                }
            ],
            "经济指标": [
                {
                    "name": "宏观经济分析",
                    "description": "分析宏观经济因素、政策影响、市场环境",
                    "model": "gpt-4o"
                },
                {
                    "name": "量化分析与概率建模",
                    "description": "通过量化分析和概率建模，精确计算经济指标的可能性分布",
                    "model": "deepseek-chat"
                },
                {
                    "name": "风险因子识别",
                    "description": "识别经济下行风险、意外因素、市场波动风险",
                    "model": "claude-3-7-sonnet-latest"
                },
                {
                    "name": "历史数据模式",
                    "description": "分析历史数据趋势、周期性模式、季节性因素",
                    "model": "gemini-2.5-pro"
                },
                {
                    "name": "市场情绪分析",
                    "description": "分析市场预期、投资者情绪、情绪驱动的波动",
                    "model": "grok-4"
                }
            ],
            "通用事件": [
                {
                    "name": "综合分析",
                    "description": "全面分析事件的各种可能因素和逻辑推理",
                    "model": "gpt-4o"
                },
                {
                    "name": "深度推理与量化分析",
                    "description": "通过深度推理和量化分析，精确评估事件发生的可能性",
                    "model": "deepseek-chat"
                },
                {
                    "name": "风险评估",
                    "description": "评估事件可能的风险和不确定性",
                    "model": "claude-3-7-sonnet-latest"
                },
                {
                    "name": "模式识别",
                    "description": "识别类似历史事件和模式",
                    "model": "gemini-2.5-pro"
                },
                {
                    "name": "另类视角",
                    "description": "提供另类视角和可能被忽视的因素",
                    "model": "grok-4"
                }
            ]
        }
        
        return dimension_map.get(chinese_category, dimension_map["通用事件"])
    
    def _assign_models_to_dimensions(self, dimensions: List[Dict], available_models: List[str] = None) -> Dict[str, Dict]:
        """
        Assign models to dimensions.
        
        Args:
            dimensions: List of dimension dicts with 'model' key
            available_models: Optional list of available model IDs (if None, assign all)
        
        Returns:
            Dict mapping model_id -> assignment dict
        """
        assignments = {}
        
        for dim in dimensions:
            model_name = dim["model"]
            # Skip if model is not available (disabled or not in orchestrator)
            if available_models and model_name not in available_models:
                continue
            # Skip if model is not in specializations (e.g., fallback models)
            if model_name not in self.MODEL_SPECIALIZATIONS:
                continue
                
            if model_name not in assignments:
                assignments[model_name] = {
                    "dimension_name": dim["name"],
                    "dimension_description": dim["description"],
                    "weight": self.MODEL_SPECIALIZATIONS[model_name]["weight"],
                    "specialization": self.MODEL_SPECIALIZATIONS[model_name]["name"]
                }
        
        return assignments
