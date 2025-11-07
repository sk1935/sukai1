"""
事件层（Event Manager）：
根据 OPTIMIZATION_NOTES.md 的五层架构设计

职责：
- 接收并解析用户输入的事件描述（Telegram 消息、URL等）
- 从 Polymarket API 获取市场数据
- 输出：事件标题、描述、结算规则、当前市场概率等

输入：用户消息（文本或 Polymarket URL）
输出：事件数据字典 {question, market_prob, rules, outcomes, is_multi_option, ...}
"""
import aiohttp
import json
import asyncio
import re
import html
import logging
import traceback
from datetime import datetime
from typing import Dict, Optional, List, Any
from urllib.parse import quote_plus
import os
from pydantic import BaseModel, Field, field_validator, ValidationError, ConfigDict, ValidationInfo
from dotenv import load_dotenv

load_dotenv()


logger = logging.getLogger(__name__)


class Event(BaseModel):
    """Validated event payload passed between layers."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    event_id: Optional[str] = Field(default=None)
    slug: Optional[str] = None
    question: str = Field(default="Unknown event", min_length=1)
    title: Optional[str] = None
    market_prob: float = Field(default=0.0, ge=0.0, le=100.0)
    rules: Optional[str] = None
    description: Optional[str] = None
    outcomes: List[Dict[str, Any]] = Field(default_factory=list)
    is_multi_option: bool = False
    source: Optional[str] = None
    days_left: Optional[int] = Field(default=None, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("question", mode="before")
    def _ensure_question(cls, value, info: ValidationInfo):
        if isinstance(value, str) and value.strip():
            return value.strip()
        title = None
        if info and info.data:
            title = info.data.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        return "Unknown event"

    @field_validator("market_prob", mode="before")
    def _clamp_prob(cls, value):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(100.0, numeric))


class EventManager:
    """
    Manages event parsing and Polymarket data fetching.
    
    事件数据管理：
    - 解析用户输入（URL、文本描述等）
    - 从 Polymarket API 获取市场数据（支持多选项市场）
    - 网页抓取作为 fallback
    - 支持单选项和多选项市场的识别与提取
    """
    
    POLYMARKET_GRAPHQL_URL = "https://gamma-api.polymarket.com/query"
    POLYMARKET_REST_URL = "https://gamma-api.polymarket.com/markets"  # REST API (no auth needed!)
    POLYMARKET_CLOB_URL = "https://clob.polymarket.com/markets"  # CLOB API for real-time market data
    
    def __init__(self):
        self.api_key = os.getenv("POLYMARKET_API_KEY", "")

    def filter_low_probability_event(
        self,
        event_data: Optional[Dict[str, Any]],
        threshold: float = None
    ) -> Optional[Dict[str, float]]:
        """Return details when event probabilities fall below threshold, otherwise None."""
        if not event_data or event_data.get("is_mock"):
            return None

        try:
            threshold_value = float(threshold) if threshold is not None else float(
                os.getenv("LOW_PROBABILITY_THRESHOLD", "1.0")
            )
        except (TypeError, ValueError):
            threshold_value = 1.0

        try:
            outcomes = event_data.get("outcomes") if isinstance(event_data, dict) else None
            probability_candidates: List[float] = []

            if isinstance(outcomes, list) and outcomes:
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue
                    for key in ("model_only_prob", "prediction", "probability", "market_prob"):
                        value = outcome.get(key)
                        if value is None:
                            continue
                        try:
                            probability_candidates.append(float(value))
                            break
                        except (TypeError, ValueError):
                            continue
            else:
                for key in ("market_prob", "probability"):
                    value = event_data.get(key) if isinstance(event_data, dict) else None
                    if value is None:
                        continue
                    try:
                        probability_candidates.append(float(value))
                        break
                    except (TypeError, ValueError):
                        continue

            if not probability_candidates:
                return None

            max_prob = max(probability_candidates)
            min_prob = min(probability_candidates)
            if max_prob < threshold_value:
                logger.warning(
                    "过滤事件：所有概率低于阈值 (max=%.2f, threshold=%.2f)",
                    max_prob,
                    threshold_value
                )
                return {
                    "threshold": threshold_value,
                    "max_probability": max_prob,
                    "min_probability": min_prob,
                }

            return None
        except Exception as exc:
            logger.exception("评估低概率事件时发生异常: %s", exc)
            return None
    
    def parse_event_from_message(self, message_text: str) -> Dict[str, str]:
        """
        Extract event query from Telegram message.
        Returns dict with 'query' and optionally 'slug' if Polymarket URL is provided.
        Example: '/predict Will Sora be...' -> {'query': 'Will Sora be...'}
        Example: '/predict https://polymarket.com/event/...' -> {'query': '...', 'slug': '...'}
        """
        # Remove /predict command if present
        if message_text.startswith('/predict'):
            event = message_text.replace('/predict', '').strip()
        else:
            event = message_text.strip()
        
        # Check if it's a Polymarket URL
        if 'polymarket.com' in event:
            # Extract slug from URL (handles both /event/ and query parameters)
            slug_match = re.search(r'/event/([^/?\s]+)', event)
            if slug_match:
                slug = slug_match.group(1)
                print(f"📎 检测到 Polymarket URL，slug: {slug}")
                return {'query': event, 'slug': slug}
        
        # Try to extract/generate slug from query text
        # Polymarket slugs are typically: lowercase, words separated by hyphens, no special chars except dots in numbers
        # Example: "Russia x Ukraine ceasefire in 2025?" -> "russia-x-ukraine-ceasefire-in-2025"
        # Example: "Gemini 3.0 released by..." -> "gemini-30-released-by" (dots removed) or keep as "gemini-3-0"
        clean_text = event.lower()
        # Preserve dots in numbers (like "3.0") but remove other punctuation
        # Replace "x" with "-x-" for better matching
        clean_text = re.sub(r'\b([0-9]+)\.([0-9]+)\b', r'\1-\2', clean_text)  # "3.0" -> "3-0"
        clean_text = re.sub(r'[^\w\s]', '', clean_text)  # Remove remaining special chars
        potential_slug = '-'.join(clean_text.split())  # Join words with hyphens
        
        # If the query looks like a question format that might match a Polymarket slug
        # (e.g., contains "x" which might be part of slug like "russia-x-ukraine")
        if len(potential_slug) > 10:
            print(f"🔍 Trying to use generated slug: {potential_slug}")
            return {'query': event, 'slug': potential_slug}
        
        return {'query': event}
    
    async def scrape_market_from_url(self, url: str) -> Optional[Dict]:
        """
        Scrape market data directly from Polymarket webpage.
        Polymarket is a SPA, so data is embedded in JavaScript/JSON.
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Set user agent to avoid blocking
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Try to extract JSON data from script tags or __NEXT_DATA__
                        market_prob = None
                        question = None
                        rules = None
                        
                        # Method 1: Look for __NEXT_DATA__ or similar JSON embedded in HTML
                        json_patterns = [
                            r'__NEXT_DATA__\s*=\s*({.+?});',
                            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                            r'"market":\s*({[^}]+"price"[^}]+})',
                            r'"outcomes":\s*\[({[^}]+"price"[^}]+})\]',
                        ]
                        
                        for pattern in json_patterns:
                            matches = re.finditer(pattern, html, re.DOTALL)
                            for match in matches:
                                try:
                                    json_str = match.group(1)
                                    # Try to parse JSON
                                    data = json.loads(json_str)
                                    # Navigate nested structure to find price
                                    if isinstance(data, dict):
                                        # Try various paths
                                        if 'market' in data:
                                            market = data['market']
                                            if 'currentPrice' in market:
                                                market_prob = float(market['currentPrice']) * 100
                                            elif 'outcomes' in market:
                                                for outcome in market['outcomes']:
                                                    if outcome.get('name', '').lower() == 'yes':
                                                        market_prob = float(outcome.get('price', 0)) * 100
                                                        break
                                except:
                                    continue
                        
                        # Method 2: Look for price in JSON/JavaScript (most accurate)
                        if market_prob is None:
                            # Look for Yes outcome price in JSON
                            price_patterns = [
                                r'"name"\s*:\s*"Yes"[^}]*"price"\s*:\s*"?(\d+\.?\d*)"?',
                                r'"Yes"[^}]*"price"\s*:\s*"?(\d+\.?\d*)"?',
                                r'"outcomes"\s*:\s*\[[^\]]*"name"\s*:\s*"Yes"[^\]]*"price"\s*:\s*"?(\d+\.?\d*)"?',
                            ]
                            for pattern in price_patterns:
                                match = re.search(pattern, html, re.IGNORECASE)
                                if match:
                                    try:
                                        prob = float(match.group(1))
                                        # If it's a decimal (0-1), convert to percentage
                                        if prob < 1:
                                            market_prob = prob * 100
                                        else:
                                            market_prob = prob
                                        print(f"✅ Extracted price from JSON: {market_prob}%")
                                        break
                                    except:
                                        continue
                        
                        # Method 3: Look for percentage in text (e.g., "8% chance")
                        if market_prob is None:
                            prob_text_patterns = [
                                r'(\d+(?:\.\d+)?)%\s*chance',
                                r'(\d+(?:\.\d+)?)%\s*Yes',
                                r'"(\d+(?:\.\d+)?)%"',
                            ]
                            for pattern in prob_text_patterns:
                                matches = re.findall(pattern, html, re.IGNORECASE)
                                if matches:
                                    try:
                                        # Take the first reasonable percentage (likely the Yes outcome)
                                        for match in matches:
                                            prob = float(match)
                                            if 0 <= prob <= 100:
                                                market_prob = prob
                                                print(f"✅ Extracted percentage from text: {market_prob}%")
                                                break
                                        if market_prob is not None:
                                            break
                                    except:
                                        continue
                        
                        # Extract question/title
                        title_match = re.search(r'<title>([^<]+)</title>', html)
                        if title_match:
                            raw_title = title_match.group(1).split('|')[0].split('-')[0].strip()
                            question = self._clean_html_fragment(raw_title)
                        
                        # Look for question in h1 or main heading
                        if not question:
                            h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
                            if h1_match:
                                question = self._clean_html_fragment(h1_match.group(1))
                        
                        # Extract rules - look for "Rules" section
                        rules_patterns = [
                            r'Rules[^>]*>([^<]{50,500})',
                            r'"rules":\s*"([^"]+)"',
                            r'Rules.*?<p[^>]*>([^<]+)</p>',
                        ]
                        for pattern in rules_patterns:
                            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                            if match:
                                rules = self._clean_html_fragment(match.group(1))[:200]
                                break
                        
                        # For multi-option markets, try to extract all outcomes
                        outcome_list = []
                        is_multi_option = False
                        
                        # Look for outcomes in JSON data
                        outcomes_patterns = [
                            r'"outcomes"\s*:\s*\[([^\]]+)\]',
                            r'outcomes.*?\[(.*?)\]',
                        ]
                        
                        # Try to find outcome names and prices from HTML
                        # Look for outcome names in the page
                        outcome_name_pattern = r'(?:OUTCOME|Market icon|buy Yes)[^>]*>([A-Za-z0-9\s\-\/\.]+?)(?:</|Vol\.|%)'
                        outcome_names = re.findall(outcome_name_pattern, html, re.IGNORECASE)
                        
                        # Look for percentages near outcome names
                        prob_pattern = r'(\d+(?:\.\d+)?)%'
                        
                        # Try to extract from structured data (__NEXT_DATA__)
                        try:
                            # Look for __NEXT_DATA__ - this contains all market data
                            next_data_match = re.search(r'__NEXT_DATA__\s*=\s*({.+?})</script>', html, re.DOTALL)
                            if next_data_match:
                                next_data_str = next_data_match.group(1)
                                next_data = json.loads(next_data_str)
                                
                                # Recursively search for market with outcomes
                                def find_market_recursive(obj, depth=0):
                                    if depth > 10:  # Prevent infinite recursion
                                        return None
                                    
                                    if isinstance(obj, dict):
                                        # Check if this looks like a market object
                                        if 'outcomes' in obj and isinstance(obj.get('outcomes'), list):
                                            outcomes = obj['outcomes']
                                            if len(outcomes) > 2:  # Multi-option market
                                                question = obj.get('question') or obj.get('title') or question
                                                return obj
                                        
                                        # Search in nested structures
                                        for key in ['props', 'pageProps', 'market', 'markets', 'data', 'query']:
                                            if key in obj:
                                                result = find_market_recursive(obj[key], depth + 1)
                                                if result:
                                                    return result
                                        
                                        # Search all values
                                        for value in obj.values():
                                            result = find_market_recursive(value, depth + 1)
                                            if result:
                                                return result
                                    
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            result = find_market_recursive(item, depth + 1)
                                            if result:
                                                return result
                                    
                                    return None
                                
                                market_data = find_market_recursive(next_data)
                                
                                if market_data:
                                    outcomes = market_data.get('outcomes', [])
                                    if isinstance(outcomes, list) and len(outcomes) > 2:
                                        is_multi_option = True
                                        question = market_data.get('question') or market_data.get('title') or question
                                        
                                        # Extract all outcomes
                                        for outcome in outcomes:
                                            if isinstance(outcome, dict):
                                                name = outcome.get('name', '')
                                                price = outcome.get('price', outcome.get('probability', 0))
                                                
                                                # Handle price format
                                                if isinstance(price, str):
                                                    try:
                                                        price = float(price)
                                                    except:
                                                        price = 0
                                                
                                                if isinstance(price, (int, float)) and price > 0:
                                                    prob = float(price) * 100 if price <= 1 else price
                                                    outcome_list.append({
                                                        "name": name.strip(),
                                                        "probability": round(prob, 2),
                                                        "market_prob": round(prob, 2)
                                                    })
                                        
                                        if outcome_list:
                                            print(f"✅ Extracted {len(outcome_list)} outcomes from __NEXT_DATA__")
                        except Exception as e:
                            print(f"⚠️ Could not extract outcomes from JSON: {e}")
                            import traceback
                            traceback.print_exc()
                        
                        # If we found multi-option data, return it
                        if is_multi_option and outcome_list:
                            print(f"✅ Scraped multi-option market from URL: {len(outcome_list)} outcomes")
                            return {
                                "question": question or "从网页获取的市场",
                                "market_prob": round(outcome_list[0]["market_prob"], 2) if outcome_list else None,
                                "rules": rules or "规则信息在网页中，请访问原链接查看",
                                "volume": 0,
                                "days_left": 30,
                                "trend": "→",
                                "is_mock": False,
                                "source": "web_scraping",
                                "is_multi_option": True,
                                "outcomes": outcome_list
                            }
                        
                        # Fallback to single probability
                        if market_prob is not None:
                            print(f"✅ Scraped market data from URL: {market_prob}%")
                            return {
                                "question": question or "从网页获取的市场",
                                "market_prob": round(market_prob, 2),
                                "rules": rules or "规则信息在网页中，请访问原链接查看",
                                "volume": 0,
                                "days_left": 30,
                                "trend": "→",
                                "is_mock": False,
                                "source": "web_scraping"
                            }
                        else:
                            print(f"⚠️ Could not extract market probability from webpage")
        except Exception as e:
            print(f"Error scraping from URL: {e}")
            import traceback
            traceback.print_exc()
        return None
    
    async def fetch_polymarket_data(self, event_info: Dict[str, str]) -> Optional[Dict]:
        """Public wrapper that guards Polymarket fetches with fail-safe handling."""
        event_query = event_info.get('query', '')
        try:
            return await self._fetch_polymarket_data_core(event_info)
        except Exception as exc:
            logger.exception("fetch_polymarket_data failed: %s", exc)
            fallback = self._create_mock_market_data(event_query or "未知事件")
            fallback["source"] = "fetch_polymarket_data_error"
            return self._validate_event_payload(fallback, "fetch_polymarket_data.exception")

    async def _fetch_polymarket_data_core(self, event_info: Dict[str, str]) -> Optional[Dict]:
        """
        Fetch market data from Polymarket API.
        Returns market info including probability, rules, volume, etc.
        
        Args:
            event_info: Dict with 'query' and optionally 'slug'
        """
        event_query = event_info.get('query', '')
        slug = event_info.get('slug')
        
        # Try concurrent primary sources first (slugs + search + graphql)
        primary_payload = await self._fetch_primary_sources_concurrently(event_query, slug)
        if primary_payload:
            return primary_payload
        
        # If we have a slug (especially from URL), prioritize API over scraping
        # URL provides exact slug, so API lookup is most reliable and accurate
        if slug:
            async with aiohttp.ClientSession() as session:
                # Method 0: Try /events endpoint first (this works for multi-option markets!)
                try:
                    events_url = f"https://gamma-api.polymarket.com/events?slug={slug}"
                    print(f"🔍 Trying Gamma API /events: {events_url}")
                    async with session.get(
                        events_url,
                        headers={"Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=8)  # Reduced from 10s for faster failover
                    ) as response:
                        if response.status == 200:
                            events = await response.json()
                            if isinstance(events, list) and len(events) > 0:
                                # Find exact slug match
                                matched_event = None
                                exact_match_is_child = False
                                for evt in events:
                                    if evt.get('slug', '').lower() == slug.lower():
                                        matched_event = evt
                                        # Check if this exact match is actually a child market (has date in slug)
                                        if re.search(r'-(november|december|october|january|february|march|april|may|june|july|august|september)-\d+(-\d+)?$', slug, re.IGNORECASE):
                                            exact_match_is_child = True
                                            print(f"📍 Exact match found, but appears to be a child market (contains date): {slug}")
                                        break
                                
                                # If no exact match, or exact match is a child market, try to find parent event
                                # e.g., if slug is "us-x-venezuela-military-engagement-by" 
                                # but actual slugs are "us-x-venezuela-military-engagement-by-october-31"
                                # Or: slug is "russia-x-ukraine-ceasefire-by-november-30-513"
                                # but parent is "russia-x-ukraine-ceasefire-by..."
                                # Find the event that contains the slug as prefix
                                if not matched_event or exact_match_is_child:
                                    slug_parts = slug.split('-')
                                    # Remove date patterns and numeric suffixes from slug to find parent
                                    # Pattern: remove month names (november, december, etc.) and dates (30, 31, etc.)
                                    month_names = ['january', 'february', 'march', 'april', 'may', 'june',
                                                  'july', 'august', 'september', 'october', 'november', 'december']
                                    cleaned_parts = []
                                    skip_next = False
                                    for i, part in enumerate(slug_parts):
                                        if skip_next:
                                            skip_next = False
                                            continue
                                        # Skip month names and dates (like "november", "30", "513")
                                        if part.lower() in month_names:
                                            skip_next = True  # Skip the date number after month
                                            continue
                                        # Skip pure numbers that are likely dates or IDs
                                        if part.isdigit() and (len(part) <= 3 or part.startswith('20')):  # Dates like "30" or "2025"
                                            continue
                                        cleaned_parts.append(part)
                                    
                                    # Try multiple prefix strategies
                                    prefix_strategies = []
                                    if len(slug_parts) >= 5:
                                        prefix_strategies.append('-'.join(slug_parts[:5]))  # First 5 parts
                                    if len(slug_parts) >= 4:
                                        prefix_strategies.append('-'.join(slug_parts[:4]))  # First 4 parts
                                    if len(cleaned_parts) >= 4:
                                        prefix_strategies.append('-'.join(cleaned_parts[:4]))  # Cleaned prefix
                                    
                                    # Store the child event if we had an exact match
                                    child_event = matched_event if exact_match_is_child else None
                                    
                                    # Try each prefix strategy to find parent
                                    parent_event = None
                                    for prefix in prefix_strategies:
                                        for evt in events:
                                            evt_slug = evt.get('slug', '').lower()
                                            evt_id = evt.get('id', '')
                                            # Skip the child event itself
                                            if child_event and evt_id == child_event.get('id'):
                                                continue
                                            # Check if this is a parent event (slug is shorter, without date details)
                                            # Parent should match prefix but not have date suffix
                                            if evt_slug.startswith(prefix) or prefix.startswith(evt_slug):
                                                # Additional check: parent should not have date in its slug
                                                if not re.search(r'-(november|december|october|january|february|march|april|may|june|july|august|september)-\d+', evt_slug, re.IGNORECASE):
                                                    parent_event = evt
                                                    print(f"💡 Found parent event via prefix '{prefix}': {evt_slug}")
                                                    break
                                        if parent_event:
                                            break
                                    
                                    # Use parent event if found, otherwise keep child/matched event
                                    if parent_event:
                                        matched_event = parent_event
                                    elif not matched_event:
                                        # No match at all
                                        matched_event = None
                                
                                if matched_event:
                                    event = matched_event
                                    event_id = event.get('id')
                                    event_title = event.get('title') or event.get('question') or ''
                                    if not event_title:
                                        # Try to reconstruct from slug
                                        event_title = slug.replace('-', ' ').title()
                                    print(f"✅ Found event via Gamma API /events (slug): {event_title}")
                                else:
                                    # No exact match, but we have events - might be a close match
                                    print(f"⚠️ No exact slug match, found {len(events)} events.")
                                    # Before falling through, try one more strategy: look for events with similar structure
                                    # For date-based slugs, try removing the date part completely
                                    slug_without_date = re.sub(r'-(november|december|october|january|february|march|april|may|june|july|august|september)-\d+(-\d+)?$', '', slug, flags=re.IGNORECASE)
                                    if slug_without_date != slug:
                                        print(f"🔍 Trying slug without date: {slug_without_date}")
                                        for evt in events:
                                            evt_slug = evt.get('slug', '').lower()
                                            # Check if event slug matches the pattern (parent event)
                                            if slug_without_date.lower() in evt_slug or evt_slug in slug_without_date.lower():
                                                matched_event = evt
                                                print(f"💡 Found event by removing date pattern: {evt.get('slug', 'N/A')}")
                                                break
                                    
                                    if not matched_event:
                                        print(f"   Trying text search or other methods...")
                                    # Fall through to text search below if still no match
                                    
                                if matched_event:
                                    event_id = event.get('id')
                                    
                                    # Get full event details to access markets
                                    if event_id:
                                        detail_url = f"https://gamma-api.polymarket.com/events/{event_id}"
                                        try:
                                            async with session.get(
                                                detail_url,
                                                timeout=aiohttp.ClientTimeout(total=6)  # Limit detail fetch time
                                            ) as detail_response:
                                                if detail_response.status == 200:
                                                    event_detail = await detail_response.json()
                                                    # Get event title first - needed for all code paths
                                                    event_title = event_detail.get('title') or event_detail.get('question') or event.get('question', '')
                                                    
                                                    # Event may contain markets with outcomes
                                                    # For multi-option events, extract options from individual markets
                                                    if 'markets' in event_detail:
                                                        markets = event_detail['markets']
                                                        
                                                        # Check if this is a grouped market (has groupItemTitle in any market)
                                                        is_grouped_market = False
                                                        if isinstance(markets, list) and len(markets) > 0:
                                                            for mkt in markets:
                                                                if mkt.get('groupItemTitle'):
                                                                    is_grouped_market = True
                                                                    print(f"🔍 Detected grouped market via groupItemTitle: {mkt.get('groupItemTitle')}")
                                                                    break
                                                        
                                                        # Multi-option detection: len(markets) > 2 OR has groupItemTitle OR title has placeholder
                                                        is_multi_option_candidate = (
                                                            (isinstance(markets, list) and len(markets) > 2) or
                                                            is_grouped_market or
                                                            self._is_parent_event_title(event_title)
                                                        )
                                                        
                                                        if is_multi_option_candidate and isinstance(markets, list) and len(markets) >= 1:
                                                            # This is likely a multi-option event
                                                            print(f"🎯 Multi-option event detected: markets={len(markets)}, grouped={is_grouped_market}, title_placeholder={self._is_parent_event_title(event_title)}")
                                                            
                                                            # If grouped market or has placeholder, fetch all child markets
                                                            if (is_grouped_market or self._is_parent_event_title(event_title)) and len(markets) < 3:
                                                                print(f"🔄 Fetching all child markets for grouped/parent event...")
                                                                parent_id = event_detail.get('id') or event.get('id')
                                                                child_markets = await self._fetch_child_markets_by_title(event_title, parent_id)
                                                                
                                                                if len(child_markets) > len(markets):
                                                                    print(f"✅ Found {len(child_markets)} child markets (was {len(markets)})")
                                                                    markets = child_markets
                                                            
                                                            # Extract option names and probabilities from each market
                                                            outcome_list = []
                                                            
                                                            for market in markets:
                                                                question = market.get('question', '')
                                                                
                                                                # Try to get option name from groupItemTitle first (most reliable)
                                                                option_name = market.get('groupItemTitle')
                                                                
                                                                # If no groupItemTitle, extract from question
                                                                if not option_name:
                                                                    option_name = self._extract_option_name(question)
                                                                
                                                                if option_name and len(option_name) > 1:
                                                                    # Get Yes probability from outcomePrices
                                                                    outcome_prices = market.get('outcomePrices', [])
                                                                    if isinstance(outcome_prices, str):
                                                                        try:
                                                                            outcome_prices = json.loads(outcome_prices)
                                                                        except:
                                                                            outcome_prices = []
                                                                    
                                                                    if isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
                                                                        yes_price = float(outcome_prices[0]) if isinstance(outcome_prices[0], str) else outcome_prices[0]
                                                                        prob = yes_price * 100 if yes_price <= 1 else yes_price
                                                                        # Skip if probability is too low (might be noise)
                                                                        if prob > 0.01:  # At least 0.01%
                                                                            outcome_list.append({
                                                                                "name": option_name,
                                                                                "probability": round(prob, 2),
                                                                                "market_prob": round(prob, 2)
                                                                            })
                                                            
                                                            if len(outcome_list) > 2:
                                                                print(f"✅ Extracted {len(outcome_list)} options from event markets")
                                                                # Calculate total volume safely
                                                                total_volume = 0
                                                                for m in markets:
                                                                    if isinstance(m, dict):
                                                                        vol = m.get('volume', 0)
                                                                        try:
                                                                            total_volume += float(vol)
                                                                        except:
                                                                            pass
                                                                
                                                                return self._validate_event_payload({
                                                                    "question": event_title or "从 Event 提取的多选项市场",
                                                                    "market_prob": outcome_list[0]["market_prob"] if outcome_list else None,
                                                                    "rules": event_detail.get('description', ''),
                                                                    "volume": int(total_volume),
                                                                    "days_left": 30,
                                                                    "trend": "→",
                                                                    "is_mock": False,
                                                                    "source": "gamma_api_events",
                                                                    "is_multi_option": True,
                                                                    "outcomes": outcome_list
                                                                }, "fetch_polymarket_data.event_detail_grouped_parent")
                                                            elif len(markets) >= 1:
                                                                # This code path should rarely be reached now due to is_multi_option_candidate check above
                                                                # But keep as fallback
                                                                print(f"⚠️ Fallback: Only extracted {len(outcome_list)} options from {len(markets)} markets")
                                                                
                                                                # Check if event title indicates this is a parent event
                                                                # If so, we should fetch child markets even if we only have 1 market here
                                                                if self._is_parent_event_title(event_title):
                                                                    print(f"🔍 Event title contains placeholder, this is likely a parent event: {event_title}")
                                                                    # Try to fetch child markets
                                                                    parent_id = event_detail.get('id') or event.get('id')
                                                                    child_markets = await self._fetch_child_markets_by_title(event_title, parent_id)
                                                                    
                                                                    if len(child_markets) > 2:
                                                                        print(f"✅ Found {len(child_markets)} child markets for parent event")
                                                                        # Process as multi-option market
                                                                        outcome_list = []
                                                                        for child_mkt in child_markets:
                                                                            child_question = child_mkt.get('question', '')
                                                                            option_name = self._extract_option_name(child_question)
                                                                            
                                                                            if option_name:
                                                                                # Get price
                                                                                outcome_prices = child_mkt.get('outcomePrices', [])
                                                                                if isinstance(outcome_prices, str):
                                                                                    try:
                                                                                        outcome_prices = json.loads(outcome_prices)
                                                                                    except:
                                                                                        outcome_prices = []
                                                                                
                                                                                prob = 0.0
                                                                                if isinstance(outcome_prices, list) and len(outcome_prices) > 0:
                                                                                    try:
                                                                                        prob = float(outcome_prices[0])
                                                                                        if prob <= 1:
                                                                                            prob = prob * 100
                                                                                    except:
                                                                                        pass
                                                                                
                                                                                outcome_list.append({
                                                                                    "name": option_name,
                                                                                    "probability": round(prob, 2),
                                                                                    "market_prob": round(prob, 2)
                                                                                })
                                                                        
                                                                        if len(outcome_list) > 2:
                                                                            print(f"✅ Successfully extracted {len(outcome_list)} options from parent event")
                                                                            total_volume = sum(float(m.get('volume', 0)) for m in child_markets)
                                                                            return self._validate_event_payload({
                                        "question": event_title,
                                        "market_prob": outcome_list[0]["market_prob"] if outcome_list else 0.0,
                                        "rules": event_detail.get('description', ''),
                                        "volume": int(total_volume),
                                        "days_left": 30,
                                        "trend": "→",
                                        "is_mock": False,
                                        "source": "gamma_api_parent_event_direct",
                                        "is_multi_option": True,
                                        "outcomes": outcome_list
                                    }, "fetch_polymarket_data.parent_event_direct")
                                                                
                                                                # Try to get outcomes directly from markets if available
                                                                # Some markets might have outcomes array directly
                                                                all_outcomes_found = []
                                                                for mkt in markets:
                                                                    # Check if market has outcomes array
                                                                    mkt_outcomes = mkt.get('outcomes', [])
                                                                    if isinstance(mkt_outcomes, str):
                                                                        try:
                                                                            mkt_outcomes = json.loads(mkt_outcomes)
                                                                        except:
                                                                            mkt_outcomes = []
                                                                    if isinstance(mkt_outcomes, list) and len(mkt_outcomes) > 0:
                                                                        # Found outcomes in market structure
                                                                        all_outcomes_found.extend([o for o in mkt_outcomes if isinstance(o, str)])
                                                                
                                                                if len(all_outcomes_found) > 2:
                                                                    # We found multiple outcomes, process as multi-option
                                                                    outcome_list = []
                                                                    outcome_prices_all = []
                                                                    for mkt in markets:
                                                                        prices = mkt.get('outcomePrices', [])
                                                                        if isinstance(prices, str):
                                                                            try:
                                                                                prices = json.loads(prices)
                                                                            except:
                                                                                prices = []
                                                                        outcome_prices_all.append(prices)
                                                                    
                                                                    # Match outcomes with prices
                                                                    for i, outcome_name in enumerate(all_outcomes_found):
                                                                        prob = 0.0
                                                                        # Try to find price for this outcome across markets
                                                                        for prices in outcome_prices_all:
                                                                            if i < len(prices) and prices[i] is not None:
                                                                                try:
                                                                                    prob = float(prices[i])
                                                                                    if prob <= 1:
                                                                                        prob = prob * 100
                                                                                    break
                                                                                except:
                                                                                    pass
                                                                        
                                                                        outcome_list.append({
                                                                            "name": outcome_name.strip(),
                                                                            "probability": round(prob, 2),
                                                                            "market_prob": round(prob, 2)
                                                                        })
                                                                    
                                                                    if len(outcome_list) > 2:
                                                                        print(f"✅ Extracted {len(outcome_list)} options from market outcomes structure")
                                                                        total_volume = 0
                                                                        for m in markets:
                                                                            if isinstance(m, dict):
                                                                                vol = m.get('volume', 0)
                                                                                try:
                                                                                    total_volume += float(vol)
                                                                                except:
                                                                                    pass
                                                                        return self._validate_event_payload({
                                    "question": event_title or "从 Event 提取的多选项市场",
                                    "market_prob": outcome_list[0]["market_prob"] if outcome_list else None,
                                    "rules": event_detail.get('description', ''),
                                    "volume": int(total_volume),
                                    "days_left": 30,
                                    "trend": "→",
                                    "is_mock": False,
                                    "source": "gamma_api_events",
                                    "is_multi_option": True,
                                    "outcomes": outcome_list
                                }, "fetch_polymarket_data.event_detail_default")
                                                                
                                                                # Fallback: use first market if not enough options extracted
                                                                market = markets[0]
                                                                print(f"✅ Got market from event details")
                                                                # Ensure question is set from event if market doesn't have it
                                                                if not market.get('question') and event_title:
                                                                    market['question'] = event_title
                                                                
                                                                # Parse the market - allow fetch_children to work
                                                                # Don't pass fetch_children=False to allow parent event detection
                                                                result = self._parse_rest_market_data(market)
                                                                
                                                                # If this is a parent event, try to fetch its children
                                                                if result.get('_is_parent_event'):
                                                                    print(f"🔄 父事件检测，尝试获取子市场...")
                                                                    parent_id = result.get('_parent_id')
                                                                    parent_title = result.get('_parent_title')
                                                                    
                                                                    # Fetch child markets
                                                                    child_markets = await self._fetch_child_markets_by_title(parent_title, parent_id)
                                                                    
                                                                    if len(child_markets) > 2:
                                                                        # Process as multi-option market
                                                                        outcome_list = []
                                                                        for child_mkt in child_markets:
                                                                            child_question = child_mkt.get('question', '')
                                                                            option_name = self._extract_option_name(child_question)
                                                                            
                                                                            if option_name:
                                                                                # Get price
                                                                                outcome_prices = child_mkt.get('outcomePrices', [])
                                                                                if isinstance(outcome_prices, str):
                                                                                    try:
                                                                                        outcome_prices = json.loads(outcome_prices)
                                                                                    except:
                                                                                        outcome_prices = []
                                                                                
                                                                                prob = 0.0
                                                                                if isinstance(outcome_prices, list) and len(outcome_prices) > 0:
                                                                                    try:
                                                                                        prob = float(outcome_prices[0])
                                                                                        if prob <= 1:
                                                                                            prob = prob * 100
                                                                                    except:
                                                                                        pass
                                                                                
                                                                                outcome_list.append({
                                                                                    "name": option_name,
                                                                                    "probability": round(prob, 2),
                                                                                    "market_prob": round(prob, 2)
                                                                                })
                                                                        
                                                                        if len(outcome_list) > 2:
                                                                            print(f"✅ 从父事件提取了 {len(outcome_list)} 个子选项")
                                                                            total_volume = sum(float(m.get('volume', 0)) for m in child_markets)
                                                                            return self._validate_event_payload({
                                        "question": parent_title,
                                        "market_prob": outcome_list[0]["market_prob"] if outcome_list else 0.0,
                                        "rules": result.get('rules', ''),
                                        "volume": int(total_volume),
                                        "days_left": 30,
                                        "trend": "→",
                                        "is_mock": False,
                                        "source": "gamma_api_parent_event",
                                        "is_multi_option": True,
                                        "outcomes": outcome_list
                                    }, "fetch_polymarket_data.parent_event")
                                                                
                                                                return result
                                        except asyncio.TimeoutError:
                                            print(f"⏱️ Event detail fetch timeout, using event data directly")
                                            # Fallback: use event data directly without details
                                            if not event.get('question') and event_title:
                                                event['question'] = event_title
                                            result = self._parse_rest_market_data(event, fetch_children=False)
                                            
                                            # Check if parent event
                                            if result.get('_is_parent_event'):
                                                print(f"🔄 Timeout fallback 检测到父事件，尝试获取子市场...")
                                                parent_id = result.get('_parent_id')
                                                parent_title = result.get('_parent_title')
                                                # 添加超时保护，避免子市场获取阻塞
                                                try:
                                                    child_markets = await asyncio.wait_for(
                                                        self._fetch_child_markets_by_title(parent_title, parent_id),
                                                        timeout=10.0  # 子市场获取最多10秒
                                                    )
                                                except asyncio.TimeoutError:
                                                    print(f"⏱️ [WARNING] 子市场获取超时，使用父事件数据")
                                                    child_markets = []
                                                except Exception as e:
                                                    print(f"⚠️ [WARNING] 子市场获取失败: {e}")
                                                    child_markets = []
                                                
                                                if len(child_markets) > 2:
                                                    outcome_list = []
                                                    for child_mkt in child_markets:
                                                        child_question = child_mkt.get('question', '')
                                                        option_name = self._extract_option_name(child_question)
                                                        if option_name:
                                                            outcome_prices = child_mkt.get('outcomePrices', [])
                                                            if isinstance(outcome_prices, str):
                                                                try:
                                                                    outcome_prices = json.loads(outcome_prices)
                                                                except:
                                                                    outcome_prices = []
                                                            prob = 0.0
                                                            if isinstance(outcome_prices, list) and len(outcome_prices) > 0:
                                                                try:
                                                                    prob = float(outcome_prices[0])
                                                                    if prob <= 1:
                                                                        prob = prob * 100
                                                                except:
                                                                    pass
                                                            outcome_list.append({
                                                                "name": option_name,
                                                                "probability": round(prob, 2),
                                                                "market_prob": round(prob, 2)
                                                            })
                                                    
                                                    if len(outcome_list) > 2:
                                                        print(f"✅ Timeout fallback 提取了 {len(outcome_list)} 个子选项")
                                                        total_volume = sum(float(m.get('volume', 0)) for m in child_markets)
                                                        return self._validate_event_payload({
                        "question": parent_title,
                        "market_prob": outcome_list[0]["market_prob"] if outcome_list else 0.0,
                        "rules": result.get('rules', ''),
                        "volume": int(total_volume),
                        "days_left": 30,
                        "trend": "→",
                        "is_mock": False,
                        "source": "gamma_api_parent_event_timeout",
                        "is_multi_option": True,
                        "outcomes": outcome_list
                    }, "fetch_polymarket_data.parent_event_timeout")
                                            
                                            return result
                                    # Fallback: use event data directly
                                    # Ensure question is set
                                    if not event.get('question') and event_title:
                                        event['question'] = event_title
                                    result = self._parse_rest_market_data(event, fetch_children=False)
                                    
                                    # Check if parent event in final fallback
                                    if result.get('_is_parent_event'):
                                        print(f"🔄 Final fallback 检测到父事件，尝试获取子市场...")
                                        parent_id = result.get('_parent_id')
                                        parent_title = result.get('_parent_title')
                                        child_markets = await self._fetch_child_markets_by_title(parent_title, parent_id)
                                        
                                        if len(child_markets) > 2:
                                            outcome_list = []
                                            for child_mkt in child_markets:
                                                child_question = child_mkt.get('question', '')
                                                option_name = self._extract_option_name(child_question)
                                                if option_name:
                                                    outcome_prices = child_mkt.get('outcomePrices', [])
                                                    if isinstance(outcome_prices, str):
                                                        try:
                                                            outcome_prices = json.loads(outcome_prices)
                                                        except:
                                                            outcome_prices = []
                                                    prob = 0.0
                                                    if isinstance(outcome_prices, list) and len(outcome_prices) > 0:
                                                        try:
                                                            prob = float(outcome_prices[0])
                                                            if prob <= 1:
                                                                prob = prob * 100
                                                        except:
                                                            pass
                                                    outcome_list.append({
                                                        "name": option_name,
                                                        "probability": round(prob, 2),
                                                        "market_prob": round(prob, 2)
                                                    })
                                            
                                            if len(outcome_list) > 2:
                                                print(f"✅ Final fallback 提取了 {len(outcome_list)} 个子选项")
                                                total_volume = sum(float(m.get('volume', 0)) for m in child_markets)
                                                return self._validate_event_payload({
                            "question": parent_title,
                            "market_prob": outcome_list[0]["market_prob"] if outcome_list else 0.0,
                            "rules": result.get('rules', ''),
                            "volume": int(total_volume),
                            "days_left": 30,
                            "trend": "→",
                            "is_mock": False,
                            "source": "gamma_api_parent_event_final",
                            "is_multi_option": True,
                            "outcomes": outcome_list
                        }, "fetch_polymarket_data.parent_event_final")
                                    
                                    return result
                                # If matched_event is None after all checks, break out to try next method
                                else:
                                    print(f"⚠️ No matching event found in /events endpoint, trying next method...")
                except (asyncio.TimeoutError, aiohttp.ClientError, aiohttp.ClientConnectorError) as e:
                    error_type = type(e).__name__
                    print(f"⏱️ [WARNING] Gamma API /events failed ({error_type}): {e}")
                    print(f"🔄 Auto-fallback to REST API...")
                    # Continue to next method (REST API) instead of failing immediately
                except Exception as e:
                    error_type = type(e).__name__
                    print(f"❌ [ERROR] Gamma API /events exception ({error_type}): {e}")
                    print(f"🔄 Auto-fallback to REST API...")
                    # Continue to next method
                
                # Method 0b: Try /markets endpoint with slug (fallback after /events)
                try:
                    gamma_api_url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
                    print(f"🔍 Trying Gamma API /markets: {gamma_api_url}")
                    async with session.get(
                        gamma_api_url,
                        headers={"Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=8)  # Reduced timeout for faster failover
                    ) as response:
                        if response.status == 200:
                            markets = await response.json()
                            if isinstance(markets, list):
                                # Find exact slug match
                                for market in markets:
                                    if market.get('slug', '').lower() == slug.lower():
                                        print(f"✅ Found market via Gamma API /markets: {market.get('question', 'Unknown')}")
                                        # If market has ID, try to get full details (but limit time)
                                        market_id = market.get('id')
                                        if market_id:
                                            try:
                                                detail_url = f"https://gamma-api.polymarket.com/markets/{market_id}"
                                                async with session.get(
                                                    detail_url,
                                                    timeout=aiohttp.ClientTimeout(total=5)
                                                ) as detail_response:
                                                    if detail_response.status == 200:
                                                        market_detail = await detail_response.json()
                                                        print(f"✅ Got full market details via Gamma API")
                                                        return self._parse_rest_market_data(market_detail)
                                            except (asyncio.TimeoutError, Exception) as e:
                                                print(f"⚠️ Could not get market details, using basic market data: {e}")
                                                # Return basic market data instead of failing
                                        return self._parse_rest_market_data(market)
                            elif isinstance(markets, dict):
                                # Single market object
                                if markets.get('slug', '').lower() == slug.lower():
                                    print(f"✅ Found market via Gamma API /markets (direct): {markets.get('question', 'Unknown')}")
                                    return self._parse_rest_market_data(markets)
                        else:
                            print(f"⚠️ Gamma API /markets returned {response.status}")
                except (asyncio.TimeoutError, aiohttp.ClientError, aiohttp.ClientConnectorError) as e:
                    error_type = type(e).__name__
                    print(f"⏱️ [WARNING] Gamma API /markets failed ({error_type}): {e}")
                    print(f"🔄 Auto-fallback to REST API...")
                except Exception as e:
                    error_type = type(e).__name__
                    print(f"❌ [ERROR] Gamma API /markets exception ({error_type}): {e}")
                    print(f"🔄 Auto-fallback to REST API...")
                
                # Method 1: Try REST API slug parameter (fallback after Gamma API failures)
                try:
                    rest_url = f"{self.POLYMARKET_REST_URL}?slug={slug}"
                    print(f"🔍 Trying REST API (fallback): {rest_url}")
                    async with session.get(
                        rest_url,
                        headers={"Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=8)  # Reduced timeout
                    ) as response:
                        if response.status == 200:
                            markets = await response.json()
                            if markets and len(markets) > 0:
                                market = markets[0]
                                # Verify it's the right market by checking slug
                                if market.get('slug', '').lower() == slug.lower():
                                    print(f"✅ Found market via REST API (slug): {market.get('question', 'Unknown')}")
                                    return self._parse_rest_market_data(market)
                        else:
                            print(f"⚠️ REST API slug parameter returned {response.status}")
                except asyncio.TimeoutError:
                    print(f"⏱️ Method 1 (REST API slug) timeout, trying next method...")
                except Exception as e:
                    print(f"Error with REST API slug query: {e}")
                
                # Method 1b: Try using slug as query with multiple variations (limit to first 2 for speed)
                query_variations = [
                    slug.replace('-', ' '),  # "1 searched person on google this year"
                    slug.replace('-', ' ').replace(' this year', ''),  # Remove time qualifier
                    # Only try first 2 variations to save time
                ]
                
                for query_text in query_variations[:2]:  # Limit to 2 variations
                    try:
                        encoded_query = quote_plus(query_text)
                        rest_url = f"{self.POLYMARKET_REST_URL}?query={encoded_query}&limit=50"
                        
                        async with session.get(
                            rest_url,
                            headers={"Accept": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=6)  # Reduced timeout
                        ) as response:
                            if response.status == 200:
                                markets = await response.json()
                                if markets:
                                    # Find exact slug match (critical for correctness)
                                    for market in markets:
                                        market_slug = market.get('slug', '').lower()
                                        if market_slug == slug.lower():
                                            print(f"✅ Found exact slug match via REST API (query: '{query_text}'): {market.get('question', 'Unknown')}")
                                            return self._parse_rest_market_data(market)
                                    
                                    # Log if we got close but don't continue searching
                                    if markets:
                                        close_match = markets[0]
                                        close_slug = close_match.get('slug', '').lower()
                                        slug_words = set(slug.split('-'))
                                        close_words = set(close_slug.split('-'))
                                        overlap = len(slug_words & close_words)
                                        if overlap >= 3:
                                            print(f"💡 Found similar slug ({overlap} words match): {close_slug}, but requiring exact match")
                    except asyncio.TimeoutError:
                        print(f"⏱️ Query variation '{query_text}' timeout, trying next...")
                        continue
                    except Exception as e:
                        print(f"Error with query variation '{query_text}': {e}")
                        continue
                
                # Method 2: Fallback to GraphQL
                query_by_slug = f"""query {{
                  market(slug: "{slug}") {{
                    slug
                    question
                    currentPrice
                    volume
                    outcomes {{
                      name
                      price
                    }}
                    rules
                    endDate
                    createdAt
                  }}
                }}"""
                
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                    # Add API key if available
                    if self.api_key:
                        headers["Authorization"] = f"Bearer {self.api_key}"
                    
                    async with session.post(
                        self.POLYMARKET_GRAPHQL_URL,
                        json={"query": query_by_slug},
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=6)  # Reduced timeout
                    ) as response:
                        response_text = await response.text()
                        if response.status == 200:
                            try:
                                data = await response.json()
                                if "errors" not in data:
                                    market_data = data.get("data", {}).get("market")
                                    if market_data:
                                        print(f"✅ Found Polymarket market by slug: {market_data.get('question', 'Unknown')}")
                                        return self._parse_market_data(market_data)
                                    else:
                                        print(f"⚠️ No market data returned for slug: {slug}")
                                else:
                                    print(f"⚠️ GraphQL errors for slug query: {data.get('errors')}")
                            except json.JSONDecodeError as e:
                                print(f"⚠️ JSON decode error for slug query: {e}")
                                print(f"Response: {response_text[:500]}")
                        else:
                            print(f"⚠️ API returned {response.status} for slug query")
                            if "didn't forecast" in response_text.lower() or "oops" in response_text.lower():
                                print("   ⚠️ Polymarket API returned: 'Oops...we didn't forecast this'")
                                print("   This usually means the query format or slug is incorrect")
                except asyncio.TimeoutError:
                    print(f"⏱️ Method 2 (GraphQL) timeout, continuing to text search...")
                except Exception as e:
                    print(f"Error fetching by slug: {e}")
                    # Continue instead of failing completely
        
        # If we have a query but no slug match, try searching /events endpoint with text
        # This handles cases where user provides event name directly
        if not slug or 'polymarket.com' not in event_query:
            async with aiohttp.ClientSession() as session:
                try:
                    # Use original query text (remove special chars but keep words)
                    search_query = re.sub(r'[^\w\s]', ' ', event_query).strip()
                    if not search_query:
                        search_query = slug.replace('-', ' ') if slug else event_query
                    
                    # Try /events endpoint with query parameter (limit timeout)
                    events_search_url = f"https://gamma-api.polymarket.com/events?query={quote_plus(search_query)}&limit=50"
                    async with session.get(
                        events_search_url,
                        headers={"Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=8)  # Reduced timeout
                    ) as response:
                        if response.status == 200:
                            events = await response.json()
                            if isinstance(events, list) and len(events) > 0:
                                # Calculate best match
                                best_match = None
                                best_score = 0
                                
                                query_words = set(re.findall(r'\b\w+\b', search_query.lower()))
                                
                                for event in events:
                                    title = (event.get('title') or event.get('question') or '').lower()
                                    slug_text = event.get('slug', '').replace('-', ' ').lower()
                                    
                                    title_words = set(re.findall(r'\b\w+\b', title))
                                    slug_words_set = set(re.findall(r'\b\w+\b', slug_text))
                                    
                                    title_overlap = len(query_words & title_words)
                                    slug_overlap = len(query_words & slug_words_set)
                                    exact_bonus = 5 if search_query.lower() in title or search_query.lower() in slug_text else 0
                                    
                                    score = title_overlap * 3 + slug_overlap + exact_bonus
                                    
                                    if len(query_words) <= 5:
                                        if query_words.issubset(title_words) or query_words.issubset(slug_words_set):
                                            score += 10
                                    
                                    if score > best_score:
                                        best_score = score
                                        best_match = event
                                
                                # Require minimum score and key words match
                                # Must match at least 1 important word (like 'tiktok', 'sale', 'announced')
                                important_words = {w for w in query_words if len(w) > 4}  # Longer words are usually more specific
                                if not important_words:
                                    important_words = query_words  # Fallback to all words if all are short
                                
                                if best_match:
                                    match_title = (best_match.get('title') or best_match.get('question') or '').lower()
                                    match_slug = best_match.get('slug', '').replace('-', ' ').lower()
                                    match_text = match_title + ' ' + match_slug
                                    matched_important = any(w in match_text for w in important_words)
                                    
                                    # Require both good score AND important words match
                                    min_score = max(5, len(query_words) * 2)  # At least 2 points per word
                                    if best_score >= min_score and matched_important:
                                        event_title = best_match.get('title') or best_match.get('question', 'Unknown')
                                        print(f"✅ Found event via /events text search (score: {best_score}): {event_title}")
                                    else:
                                        print(f"⚠️ Best match score {best_score} or key words don't match, skipping")
                                        best_match = None
                                
                                if best_match:
                                    event_title = best_match.get('title') or best_match.get('question', 'Unknown')
                                    print(f"✅ Found event via /events text search (score: {best_score}): {event_title}")
                                    
                                    # Get event details and process (same logic as slug match above)
                                    event_id = best_match.get('id')
                                    if event_id:
                                        detail_url = f"https://gamma-api.polymarket.com/events/{event_id}"
                                        try:
                                            async with session.get(
                                                detail_url,
                                                timeout=aiohttp.ClientTimeout(total=6)  # Limit detail fetch time
                                            ) as detail_response:
                                                if detail_response.status == 200:
                                                    event_detail = await detail_response.json()
                                                    if 'markets' in event_detail:
                                                        markets = event_detail['markets']
                                                        if isinstance(markets, list) and len(markets) > 2:
                                                            # Process multi-option event (same as before)
                                                            outcome_list = []
                                                            event_title_final = event_detail.get('title') or event_detail.get('question') or best_match.get('question', '')
                                                            
                                                            for market in markets:
                                                                question = market.get('question', '')
                                                                # Extract option name using dedicated method
                                                                option_name = self._extract_option_name(question)
                                                                
                                                                if option_name and len(option_name) > 1:
                                                                    outcome_prices = market.get('outcomePrices', [])
                                                                    if isinstance(outcome_prices, str):
                                                                        try:
                                                                            outcome_prices = json.loads(outcome_prices)
                                                                        except:
                                                                            outcome_prices = []
                                                                    
                                                                    if isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
                                                                        yes_price = float(outcome_prices[0]) if isinstance(outcome_prices[0], str) else outcome_prices[0]
                                                                        prob = yes_price * 100 if yes_price <= 1 else yes_price
                                                                        if prob > 0.01:
                                                                            outcome_list.append({
                                                                                "name": option_name,
                                                                                "probability": round(prob, 2),
                                                                                "market_prob": round(prob, 2)
                                                                            })
                                                            
                                                            if len(outcome_list) > 2:
                                                                print(f"✅ Extracted {len(outcome_list)} options from event markets")
                                                                total_volume = 0
                                                                for m in markets:
                                                                    if isinstance(m, dict):
                                                                        vol = m.get('volume', 0)
                                                                        try:
                                                                            total_volume += float(vol)
                                                                        except:
                                                                            pass
                                                                
                                                                return self._validate_event_payload({
                                                                    "question": event_title_final or "从 Event 提取的多选项市场",
                                                                    "market_prob": outcome_list[0]["market_prob"] if outcome_list else None,
                                                                    "rules": event_detail.get('description', ''),
                                                                    "volume": int(total_volume),
                                                                    "days_left": 30,
                                                                    "trend": "→",
                                                                    "is_mock": False,
                                                                    "source": "gamma_api_events",
                                                                    "is_multi_option": True,
                                                                    "outcomes": outcome_list
                                                                }, "fetch_polymarket_data.event_title_final")
                                                            elif len(markets) > 0:
                                                                market = markets[0]
                                                                return self._parse_rest_market_data(market)
                                        except asyncio.TimeoutError:
                                            print(f"⏱️ Event detail fetch timeout (text search), using basic event data")
                                            return self._parse_rest_market_data(best_match)
                                    return self._parse_rest_market_data(best_match)
                except asyncio.TimeoutError:
                    print(f"⏱️ /events text search timeout, trying other methods...")
                except Exception as e:
                    print(f"Error with /events text search: {e}")
        
        # If we have a URL but all API methods failed, try scraping as last resort
        if 'polymarket.com/event/' in event_query:
            print("🌐 所有 API 方法失败，尝试网页抓取（最后备用方案）...")
            scraped_data = await self.scrape_market_from_url(event_query)
            if scraped_data:
                print(f"✅ 成功从网页获取市场数据: {scraped_data.get('market_prob')}%")
                return scraped_data
        
        # Clean and escape the query string (for text-based search fallback)
        clean_query = event_query.replace('"', '\\"').replace('\n', ' ').strip()
        
        # Remove URL parts if present, but preserve the query text for searching
        # If we have a slug from URL, use it to reconstruct a searchable query
        if slug and 'polymarket.com' in event_query:
            # Extract question from URL or use slug as basis for search
            # Convert slug back to readable format
            clean_query = slug.replace('-', ' ')
            print(f"🔍 从 slug 生成搜索查询: {clean_query}")
        else:
            # Remove URL parts if present
            clean_query = re.sub(r'https?://[^\s]+', '', clean_query).strip()
        
        # Extract key terms for matching
        query_lower = clean_query.lower()
        # Remove special characters but keep important ones like #
        query_lower_clean = re.sub(r'[^\w\s#]', ' ', query_lower)
        query_words = set(re.findall(r'\b\w+\b', query_lower_clean))
        # Add number patterns (like #1, 1st)
        if '#' in clean_query or '1' in clean_query:
            query_words.add('1')
            query_words.add('first')
            query_words.add('top')
        
        # Try multiple query variations
        query_variations = [
            clean_query,  # Original query
            clean_query.lower(),  # Lowercase
            # Remove # symbol but keep the concept
            clean_query.replace('#', '').replace('#1', '1').replace('# 1', '1'),
            # Extract key terms if query is long
            " ".join(clean_query.split()[:5]) if len(clean_query.split()) > 5 else clean_query,
            # Alternative: "most searched" instead of "#1 searched"
            re.sub(r'#?\s*1\s*(st|nd|rd|th)?', 'most', clean_query, flags=re.IGNORECASE),
            # Remove "this year" variations
            re.sub(r'\s+this\s+year\s*', ' ', clean_query, flags=re.IGNORECASE),
        ]
        
        async with aiohttp.ClientSession() as session:
            # Try REST API first (no auth needed)
            for query_text in query_variations:
                try:
                    # URL encode the query
                    encoded_query = quote_plus(query_text)
                    # Request more results for better matching
                    rest_url = f"{self.POLYMARKET_REST_URL}?query={encoded_query}&limit=50"
                    async with session.get(
                        rest_url,
                        headers={"Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=8)  # Reduced timeout
                    ) as response:
                        if response.status == 200:
                            markets = await response.json()
                            if markets and len(markets) > 0:
                                # Find best match by relevance (keyword matching)
                                best_market = None
                                best_score = -1
                                
                                # Extract important keywords (skip common words)
                                common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'will', 'be', 'is', 'are', 'was', 'were', 'this', 'year'}
                                important_query_words = query_words - common_words
                                
                                # Filter out very short words, but keep numbers and important single chars
                                important_query_words = {w for w in important_query_words if len(w) > 1 or w.isdigit()}
                                
                                print(f"🔍 Searching {len(markets)} markets for query: {query_text}")
                                print(f"   Important keywords: {important_query_words}")
                                
                                # Also check for special patterns
                                has_google = 'google' in query_lower
                                has_searched = 'searched' in query_lower or 'search' in query_lower
                                has_person = 'person' in query_lower or 'people' in query_lower
                                has_top = 'top' in query_lower or 'most' in query_lower or '1' in query_lower or '#' in clean_query
                                
                                for market in markets:
                                    question = market.get("question", "").lower()
                                    slug = market.get("slug", "").lower()
                                    market_words = set(re.findall(r'\b\w+\b', question))
                                    slug_words = set(re.findall(r'\b\w+\b', slug.replace('-', ' ')))
                                    
                                    # Calculate relevance score
                                    # Matches in question title get higher weight
                                    question_matches = len(important_query_words & market_words)
                                    slug_matches = len(important_query_words & slug_words)
                                    
                                    # Bonus for exact substring match (e.g., "gemini 3.0")
                                    exact_match_bonus = 0
                                    query_lower_check = query_text.lower()
                                    if query_lower_check in question or query_lower_check in slug:
                                        exact_match_bonus = 10
                                    
                                    # Special bonus for domain-specific keywords
                                    domain_bonus = 0
                                    if has_google and 'google' in question:
                                        domain_bonus += 5
                                    if has_searched and ('searched' in question or 'search' in question):
                                        domain_bonus += 5
                                    if has_person and ('person' in question or 'people' in question):
                                        domain_bonus += 5
                                    if has_top and ('top' in question or 'most' in question or '1' in question or '#1' in market.get("question", "")):
                                        domain_bonus += 5
                                    
                                    # Weighted score: question matches count more
                                    relevance_score = question_matches * 3 + slug_matches + exact_match_bonus + domain_bonus
                                    
                                    # If perfect match or very high relevance, use it
                                    if relevance_score > best_score:
                                        best_score = relevance_score
                                        best_market = market
                                
                                # Only use match if relevance is high enough
                                # For domain-specific queries (google, searched, person), lower threshold
                                if has_google and has_searched and has_person:
                                    # Special handling for "Google most searched person" type queries
                                    min_score = max(8, len(important_query_words) * 2)  # Lower threshold but still require domain match
                                    print(f"   🎯 检测到领域特定查询（Google搜索人物），调整匹配阈值: {min_score}")
                                else:
                                    min_score = max(3, len(important_query_words))  # At least 3 points or match all important words
                                
                                if best_score >= min_score and best_market:
                                    market = best_market
                                    print(f"✅ Found relevant market (score: {best_score}/{min_score}): {market.get('question', 'Unknown')}")
                                    return self._parse_rest_market_data(market)
                                else:
                                    # No good match found - log for debugging
                                    print(f"⚠️ No relevant market found (best score: {best_score}/{min_score})")
                                    if best_market:
                                        print(f"   最佳候选: {best_market.get('question', 'None')}")
                                        # If it's a domain-specific query and we got close, show what we found
                                        if has_google and has_searched and best_score >= 5:
                                            print(f"   💡 提示: 找到部分匹配的市场，但相关性不足")
                                            print(f"   如果这是你要找的市场，建议使用完整的 Polymarket URL")
                                    print(f"   Continuing to try other query variations...")
                                    # Continue to next query variation instead of returning bad match
                except Exception as e:
                    print(f"Error with REST API query: {e}")
                    continue
            
            # Fallback to GraphQL
            for query_text in query_variations:
                # GraphQL query for this variation
                query = f"""query {{
                  markets(query: "{query_text}", limit: 5) {{
                    slug
                    question
                    currentPrice
                    volume
                    outcomes {{
                      name
                      price
                    }}
                    rules
                    endDate
                    createdAt
                  }}
                }}"""
                
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                    # Add API key if available
                    if self.api_key:
                        headers["Authorization"] = f"Bearer {self.api_key}"
                    
                    async with session.post(
                        self.POLYMARKET_GRAPHQL_URL,
                        json={"query": query},
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=6)  # Reduced timeout
                    ) as response:
                        response_text = await response.text()
                        
                        if response.status == 200:
                            try:
                                data = await response.json()
                                
                                # Check for GraphQL errors
                                if "errors" in data:
                                    print(f"GraphQL errors: {data['errors']}")
                                    continue  # Try next variation
                                
                                markets = data.get("data", {}).get("markets", [])
                                
                                if markets and len(markets) > 0:
                                    # Find best match (highest volume or most relevant)
                                    market = max(markets, key=lambda m: m.get("volume", 0))
                                    print(f"✅ Found Polymarket market: {market.get('question', 'Unknown')}")
                                    return self._parse_market_data(market)
                                
                            except json.JSONDecodeError as e:
                                print(f"JSON decode error: {e}")
                                continue  # Try next variation
                        else:
                            print(f"Polymarket API error: {response.status}")
                            continue  # Try next variation
                
                except asyncio.TimeoutError:
                    print(f"Timeout for query: {query_text}")
                    continue  # Try next variation
                except Exception as e:
                    print(f"Error with query '{query_text}': {e}")
                    continue  # Try next variation
            
            # All variations tried, no market found
            print(f"⚠️ No markets found via API for query: {event_query}")
            print(f"   尝试了多个查询变体: {query_variations}")
            
            # Last resort: if we have a URL, try scraping
            if 'polymarket.com/event/' in event_query:
                print("🌐 Trying web scraping as fallback...")
                scraped_data = await self.scrape_market_from_url(event_query)
                if scraped_data:
                    return scraped_data
            
            # Still return mock data but add a note
            mock_data = self._create_mock_market_data(event_query)
            mock_data["is_mock"] = True
            return mock_data
    
    def _extract_option_name(self, question: str) -> Optional[str]:
        """
        Extract option name from market question using multiple patterns.
        
        Returns:
            Option name string or None if extraction fails
        """
        if not question or not isinstance(question, str):
            return None
        
        # Pattern 1: "Will X be Y?" - extract Y (the option)
        # Example: "Will the next Dutch government be PVV + JA21?"
        be_pattern = r'Will\s+(?:the\s+)?.+?\s+be\s+(.+?)(?:\?|$)'
        match = re.search(be_pattern, question, re.IGNORECASE)
        if match:
            option_name = match.group(1).strip()
        else:
            # Pattern 2: "by [DATE]" - date format: Month + Day
            # Example: "by October 31"
            by_date_pattern = r'\s+by\s+([A-Z][a-z]+\s+\d{1,2})(?:\?|$)'
            match = re.search(by_date_pattern, question, re.IGNORECASE)
            if match:
                option_name = match.group(1).strip()
            else:
                # Pattern 3: general "by/in/on/before/after [OPTION]"
                by_in_pattern = r'(?:announced|engagement|sold|released|completed|finished|done|happens?|occurs?)\s+(?:by|in|on|before|after)\s+(.+?)(?:\?|$)'
                match = re.search(by_in_pattern, question, re.IGNORECASE)
                if match:
                    extracted = match.group(1).strip()
                    # Filter out common invalid words
                    if 'venezuela' not in extracted.lower() and len(extracted) > 3:
                        option_name = extracted
                    else:
                        option_name = None
                else:
                    # Pattern 4: "Will [OPTION] [ACTION]..."
                    generic_pattern = r'Will\s+(?:the\s+)?(.+?)\s+(?:win|get|secure|have|do|become|announce|sell|buy|acquire|announces|announced|sells|sold)\s+'
                    match = re.search(generic_pattern, question, re.IGNORECASE)
                    if match:
                        option_name = match.group(1).strip()
                    else:
                        # Pattern 5: "form the government/coalition"
                        form_pattern = r'Will\s+(?:the\s+)?(.+?)\s+form\s+(?:the\s+)?(?:next\s+)?(?:Dutch\s+)?(?:government|coalition)'
                        match = re.search(form_pattern, question, re.IGNORECASE)
                        if match:
                            option_name = match.group(1).strip()
                        else:
                            option_name = None
        
        # Clean up and validate option name
        if option_name:
            # Remove common suffixes/prefixes
            option_name = re.sub(r'\s+(?:party|Party|group|Group|person|Person|coalition|Coalition)\s*$', '', option_name, flags=re.IGNORECASE)
            option_name = re.sub(r'^(?:the\s+)', '', option_name, flags=re.IGNORECASE).strip()
            
            # Filter out generic/invalid options
            invalid_options = ['next dutch government', 'next government', 'dutch government', 'government', 'coalition']
            if option_name.lower() in invalid_options:
                return None
            
            # Handle year-only options
            if option_name.isdigit() and len(option_name) == 4:
                return f"End of {option_name}"
            
            # Validate minimum length
            if len(option_name) < 2:
                option_name = None
        
        # Fallback: extract capitalized phrases (likely names/entities)
        if not option_name or len(option_name) < 2:
            capitalized_phrases = re.findall(r'\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\b', question)
            common_words = {'Will', 'The', 'Most', 'Seats', 'Votes', 'Win', 'Get', 'Be', 'Election', 'Parliamentary', 'Presidential', 'Announced', 'Sale'}
            filtered = [p for p in capitalized_phrases if p not in common_words and len(p) > 2]
            if filtered:
                option_name = filtered[0]
        
        return option_name if option_name and len(option_name) > 1 else None
    
    def _is_parent_event_title(self, title: str) -> bool:
        """
        Check if title indicates this is a parent event with multiple sub-markets.
        Parent events use placeholders like '___' or 'by ___' for dates/options.
        """
        if not title:
            return False
        
        # Check for various placeholder patterns
        # Pattern 1: Three or more underscores (with or without spaces)
        if re.search(r'_{3,}', title):
            return True
        
        # Pattern 2: "by ___" pattern (may have spaces before/after underscores)
        if re.search(r'by\s+_{3,}', title, re.IGNORECASE):
            return True
        
        # Pattern 3: Question ending with just "?" after "by" (no specific value)
        if re.search(r'by\s+\?\s*$', title, re.IGNORECASE):
            return True
        
        # Pattern 4: "in ___" or "on ___" patterns
        if re.search(r'(?:in|on)\s+_{3,}', title, re.IGNORECASE):
            return True
        
        # Pattern 5: Title ending with placeholder before question mark
        if re.search(r'_{3,}\s*\??\s*$', title):
            return True
        
        return False
    
    async def _fetch_child_markets_by_title(self, parent_title: str, parent_id: str = None) -> List[Dict]:
        """
        Fetch all child markets related to a parent event by searching for similar titles.
        Uses /markets endpoint to find all related sub-markets.
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Extract base title (remove placeholder)
                base_title = parent_title.replace('___', '').replace('by ?', 'by').strip()
                
                # Try multiple search strategies
                search_terms = []
                
                # Strategy 1: Use parent event ID to find related markets
                if parent_id:
                    # First try to get markets directly by event ID
                    url = f"https://gamma-api.polymarket.com/events/{parent_id}"
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as response:
                            if response.status == 200:
                                event_data = await response.json()
                                if 'markets' in event_data and isinstance(event_data['markets'], list):
                                    print(f"✅ Found {len(event_data['markets'])} child markets via event ID")
                                    return event_data['markets']
                    except Exception as e:
                        print(f"⚠️ Failed to fetch markets by event ID: {e}")
                
                # Strategy 2: Search by title pattern
                # Extract key terms from title
                words = re.findall(r'\b[A-Z][a-z]+\b', base_title)
                if len(words) >= 2:
                    search_terms.append(' '.join(words[:3]))  # First 3 capitalized words
                
                for search_term in search_terms:
                    if not search_term:
                        continue
                    
                    encoded_term = quote_plus(search_term)
                    url = f"https://gamma-api.polymarket.com/markets?query={encoded_term}&limit=20"
                    
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as response:
                            if response.status == 200:
                                all_markets = await response.json()
                                if isinstance(all_markets, list):
                                    # Filter markets that match the base title pattern
                                    base_lower = base_title.lower()
                                    related_markets = []
                                    for mkt in all_markets:
                                        mkt_title = (mkt.get('question', '') or mkt.get('title', '')).lower()
                                        # Check if market title starts with base title or contains key terms
                                        if base_lower in mkt_title or any(word.lower() in mkt_title for word in words[:3]):
                                            related_markets.append(mkt)
                                    
                                    if len(related_markets) > 2:
                                        print(f"✅ Found {len(related_markets)} child markets via title search")
                                        return related_markets
                    except Exception as e:
                        print(f"⚠️ Failed to search markets by title: {e}")
                
        except Exception as e:
            print(f"❌ Error fetching child markets: {e}")
        
        return []
    
    def _parse_rest_market_data(self, market: Dict, fetch_children: bool = True) -> Dict:
        """
        Parse market data from REST API response.
        
        Args:
            market: Market data dict
            fetch_children: If True and this is a parent event, try to fetch child markets
        """
        # REST API returns different structure
        question = market.get("question", "") or market.get("title", "")
        # If still empty, try to get from event or reconstruct from slug
        if not question:
            slug = market.get("slug", "")
            if slug:
                question = slug.replace('-', ' ').title()
            else:
                question = "未知市场"
        
        question = self._clean_html_fragment(question)
        # Check if this is a parent event with placeholder
        if fetch_children and self._is_parent_event_title(question):
            print(f"🔍 检测到父事件标题（包含占位符）: {question}")
            # This is a parent event, should not be treated as a single market
            # Return a special marker to indicate we need to fetch children
            parent_payload = {
                "_is_parent_event": True,
                "_parent_id": market.get("id"),
                "_parent_title": question,
                "question": question,
                "market_prob": None,  # No single price for parent event
                "rules": market.get("description", ""),
                "volume": 0,
                "days_left": 30,
                "trend": "→",
                "is_mock": False,
                "source": "parent_event_detected"
            }
            return self._validate_event_payload(parent_payload, "rest_api_parent_event")
        
        end_date_str = market.get("endDate") or market.get("endDateIso")
        days_left = self._calculate_days_left(end_date_str) if end_date_str else 30
        liquidity = float(market.get("liquidity", 0) or market.get("liquidityNum", 0))
        volume = float(market.get("volume", 0) or market.get("volumeNum", 0))
        
        # Get outcomes - check if this is a multi-option market
        outcomes = market.get("outcomes", [])
        outcome_prices = market.get("outcomePrices", [])
        
        # Parse outcomes if it's a string (JSON format)
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
                print(f"✅ 解析 outcomes 字符串: {outcomes}")
            except json.JSONDecodeError as e:
                print(f"⚠️ 无法解析 outcomes 字符串: {e}")
                outcomes = []
        
        # Parse outcome prices if it's a string
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
                print(f"✅ 解析 outcomePrices 字符串: {outcome_prices}")
            except json.JSONDecodeError as e:
                print(f"⚠️ 无法解析 outcomePrices 字符串: {e}")
                outcome_prices = []
        
        # Ensure outcomes is a list
        if not isinstance(outcomes, list):
            print(f"⚠️ outcomes 不是列表类型: {type(outcomes)}, 值: {outcomes}")
            outcomes = []
        
        # Ensure outcome_prices is a list
        if not isinstance(outcome_prices, list):
            print(f"⚠️ outcome_prices 不是列表类型: {type(outcome_prices)}, 值: {outcome_prices}")
            outcome_prices = []
        
        # Check if multi-option (more than 2 outcomes)
        is_multi_option = len(outcomes) > 2
        print(f"🔍 市场类型判断: {len(outcomes)} 个选项, 是否多选项: {is_multi_option}")
        
        # Build outcome list with probabilities
        outcome_list = []
        if is_multi_option and outcomes:
            # Ensure outcome_prices is a list and has valid length
            if not isinstance(outcome_prices, list):
                outcome_prices = []
            
            prices_count = len(outcome_prices)
            outcomes_count = len(outcomes)
            print(f"🔍 解析多选项: {outcomes_count} 个 outcomes, {prices_count} 个价格")
            
            if prices_count != outcomes_count:
                print(f"⚠️ 警告: outcomes 和 outcome_prices 数量不一致 ({outcomes_count} vs {prices_count})")
            
            print(f"   outcomes 内容: {outcomes[:5]}...")  # 打印前5个用于调试
            
            for i, outcome_name in enumerate(outcomes):
                # Validate outcome_name is a string and not empty
                if not isinstance(outcome_name, str) or not outcome_name.strip():
                    print(f"⚠️ 跳过无效选项 {i}: {outcome_name} (类型: {type(outcome_name)})")
                    continue
                
                # Try to get price for this outcome
                prob = None
                if i < len(outcome_prices) and outcome_prices[i] is not None:
                    try:
                        price_str = str(outcome_prices[i])
                        prob = float(price_str)
                        if prob <= 1:
                            prob = prob * 100
                    except (ValueError, TypeError, IndexError) as e:
                        print(f"   ⚠️ 无法解析选项 {i} 的价格 ({outcome_name}): {e}")
                        prob = None
                
                # If no valid price, use default 0% (will be filtered later if needed)
                if prob is None:
                    print(f"   ⚠️ 选项 {i} ({outcome_name}) 没有有效的价格数据，使用默认值 0%")
                    prob = 0.0
                
                # Only add if probability is positive (or if we want to include all options)
                # For now, include all options even if prob is 0, as market might have updated
                clean_name = self._clean_html_fragment(outcome_name)
                outcome_list.append({
                    "name": clean_name,  # Clean whitespace and invalid chars
                    "probability": round(prob, 2),
                    "market_prob": round(prob, 2)
                })
                print(f"   ✅ 选项 {i+1}: {clean_name} = {round(prob, 2)}%")
        
        print(f"📋 最终解析到 {len(outcome_list)} 个有效选项")
        
        # For binary markets, keep existing logic
        market_prob = None  # Don't use default, try to extract real value
        if not is_multi_option:
            # Method 1: outcomePrices (can be array or JSON string)
            if outcome_prices and len(outcome_prices) > 0:
                try:
                    prob_str = str(outcome_prices[0])
                    prob = float(prob_str)
                    if prob <= 1:
                        market_prob = prob * 100
                    else:
                        market_prob = prob
                    print(f"✅ Extracted from outcomePrices: {market_prob}%")
                except (ValueError, TypeError, IndexError, json.JSONDecodeError) as e:
                    print(f"⚠️ Could not parse outcomePrices: {e}")
        
        # Method 2: bestBid and bestAsk (mid price)
        if market_prob is None and market.get("bestBid") and market.get("bestAsk"):
            try:
                bid = float(market["bestBid"])
                ask = float(market["bestAsk"])
                mid_price = (bid + ask) / 2
                market_prob = mid_price * 100
                print(f"✅ Extracted from bestBid/bestAsk: {market_prob}%")
            except (ValueError, TypeError):
                pass
        
        # Method 3: lastTradePrice
        if market_prob is None and market.get("lastTradePrice"):
            try:
                prob = float(market["lastTradePrice"])
                if prob <= 1:
                    market_prob = prob * 100
                else:
                    market_prob = prob
                print(f"✅ Extracted from lastTradePrice: {market_prob}%")
            except (ValueError, TypeError):
                pass
        
        # Method 4: currentPrice (if available)
        if market_prob is None and market.get("currentPrice"):
            try:
                prob = float(market["currentPrice"])
                if prob <= 1:
                    market_prob = prob * 100
                else:
                    market_prob = prob
                print(f"✅ Extracted from currentPrice: {market_prob}%")
            except (ValueError, TypeError):
                pass
        
        # Don't use default values - if we can't extract price, return None
        if market_prob is None:
            print(f"⚠️ Could not extract market probability from any source")
            # Return None instead of default value - let caller handle this
        
        # Extract description/rules
        rules = market.get("description", "") or "查看原链接获取完整规则"
        if len(rules) > 200:
            rules = rules[:197] + "..."
        
        rules = self._clean_html_fragment(rules or "")
        result = {
            "question": question,
            "market_prob": market_prob,
            "rules": rules,
            "volume": volume if volume > 0 else liquidity,
            "days_left": days_left,
            "trend": "→",
            "is_mock": False,
            "source": "rest_api"
        }
        
        # Add multi-option data if available
        if is_multi_option:
            result["is_multi_option"] = True
            result["outcomes"] = outcome_list
            print(f"✅ 检测到多选项市场: {len(outcome_list)} 个选项")
        else:
            result["is_multi_option"] = False
        
        return self._validate_event_payload(result, "rest_api_market")
    
    def _parse_market_data(self, market: Dict) -> Dict:
        """Parse market data from Polymarket API response (GraphQL/legacy)."""
        outcomes = market.get("outcomes", [])
        yes_outcome = next((o for o in outcomes if o.get("name", "").lower() == "yes"), None)
        
        market_prob = None
        if yes_outcome:
            price = yes_outcome.get("price")
            if price is not None:
                try:
                    prob = float(price)
                    market_prob = prob * 100 if prob <= 1 else prob
                except (ValueError, TypeError):
                    pass
        
        end_date_str = market.get("endDate")
        days_left = self._calculate_days_left(end_date_str) if end_date_str else 30
        
        question = self._clean_html_fragment(market.get("question", "") or "Unknown Market")
        result = {
            "question": question,
            "market_prob": market_prob,
            "rules": market.get("rules", "No rules specified."),
            "volume": market.get("volume", 0),
            "days_left": days_left,
            "trend": "→",
            "is_mock": False
        }
        
        return self._validate_event_payload(result, "graphql_market")
    
    def _create_mock_market_data(self, event_query: str) -> Dict:
        """Create mock market data when API fails or no market found."""
        mock_payload = {
            "question": event_query,
            "market_prob": None,  # No default value
            "rules": "⚠️ 未在 Polymarket 找到对应市场。\n\n这可能是因为：\n1. Polymarket 上暂时没有这个市场\n2. 市场名称不匹配\n\n系统将仅使用 AI 模型进行预测（不使用市场数据）。",
            "volume": 0,
            "days_left": 30,
            "trend": "→",
            "is_mock": True
        }
        return self._validate_event_payload(mock_payload, "mock_market")
    
    def _clean_html_fragment(self, text: Optional[str]) -> str:
        """Remove HTML tags, invisible chars, and normalize whitespace."""
        if not text:
            return ""
        cleaned = html.unescape(text)
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        cleaned = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', cleaned)
        cleaned = cleaned.replace('&nbsp;', ' ')
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

    def _sanitize_probability(self, value: Optional[Any], context: str) -> Optional[float]:
        """Clamp probability values within 0-100 range."""
        if value is None:
            return None
        try:
            prob = float(value)
        except (TypeError, ValueError):
            print(f"⚠️ [DATA] {context}: 无效的概率值 -> {value}")
            return None
        if prob < 0 or prob > 100:
            print(f"⚠️ [DATA] {context}: market_prob 超出范围 ({prob})，将裁剪到 0-100")
            prob = min(100.0, max(0.0, prob))
        return round(prob, 2)

    def _sanitize_days_left(self, value: Optional[Any], context: str) -> int:
        """Ensure days_to_resolution is non-negative."""
        if value is None:
            print(f"⚠️ [DATA] {context}: days_to_resolution 缺失，使用 0")
            return 0
        try:
            days = int(value)
        except (TypeError, ValueError):
            print(f"⚠️ [DATA] {context}: 无效的 days_to_resolution -> {value}，使用 0")
            return 0
        if days < 0:
            print(f"⚠️ [DATA] {context}: days_to_resolution 为负数 ({days})，已重置为 0")
            return 0
        return days

    def _validate_event_payload(self, payload: Optional[Dict[str, Any]], context: str) -> Optional[Dict[str, Any]]:
        """Apply probability/day validations and clean text fields."""
        if not isinstance(payload, dict):
            return payload
        payload = dict(payload)
        if "market_prob" in payload:
            payload["market_prob"] = self._sanitize_probability(payload.get("market_prob"), f"{context}.market_prob")
        if "days_left" in payload:
            payload["days_left"] = self._sanitize_days_left(payload.get("days_left"), f"{context}.days_left")
        if "question" in payload and isinstance(payload["question"], str):
            payload["question"] = self._clean_html_fragment(payload["question"])
        if "rules" in payload and isinstance(payload["rules"], str):
            payload["rules"] = self._clean_html_fragment(payload["rules"])
        outcomes = payload.get("outcomes")
        if isinstance(outcomes, list):
            for outcome in outcomes:
                if not isinstance(outcome, dict):
                    continue
                if "name" in outcome and isinstance(outcome["name"], str):
                    outcome["name"] = self._clean_html_fragment(outcome["name"])
                if "market_prob" in outcome:
                    outcome["market_prob"] = self._sanitize_probability(
                        outcome.get("market_prob"),
                        f"{context}.outcome.{outcome.get('name', 'unknown')}.market_prob"
                    )
                if "probability" in outcome:
                    outcome["probability"] = self._sanitize_probability(
                        outcome.get("probability"),
                        f"{context}.outcome.{outcome.get('name', 'unknown')}.probability"
                    ) or 0.0
        payload.setdefault("question", payload.get("title", "Unknown event"))
        payload.setdefault("market_prob", 0.0)
        try:
            event_model = Event(**payload)
            return event_model.model_dump()
        except ValidationError as exc:
            print(f"[EventManager] payload validation failed in {context}: {exc}")
            return payload

    async def _request_with_backoff(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        *,
        json_payload: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        retries: int = 3,
        base_delay: float = 1.0,
        timeout: float = 5.0
    ) -> Optional[Any]:
        """Generic request helper with exponential backoff."""
        delay = base_delay
        for attempt in range(1, retries + 1):
            try:
                async with session.request(
                    method,
                    url,
                    json=json_payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        content_type = response.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            return await response.json()
                        return await response.text()
                    print(f"[EventManager] {method} {url} status={response.status}")
            except Exception as exc:
                print(f"[EventManager] request failed (attempt {attempt}/{retries}): {exc}")
            if attempt < retries:
                await asyncio.sleep(min(delay, 5.0))
                delay *= 2
        return None

    async def _fetch_primary_sources_concurrently(
        self,
        event_query: str,
        slug: Optional[str],
        session: Optional[aiohttp.ClientSession] = None
    ) -> Optional[Dict]:
        """
        Fetch multiple Polymarket sources concurrently to reduce latency.
        """
        if session is None:
            async with aiohttp.ClientSession() as managed_session:
                return await self._fetch_primary_sources_concurrently(event_query, slug, session=managed_session)
        
        fetchers = []
        if slug:
            fetchers.append(self._fetch_via_slug(session, slug))
        fetchers.append(self._fetch_via_markets(session, event_query, slug))
        fetchers.append(self._fetch_via_graphql(session, event_query, slug))
        
        results = await asyncio.gather(*fetchers, return_exceptions=True)
        for result in results:
            if isinstance(result, dict) and result:
                return result
            if isinstance(result, Exception):
                print(f"[EventManager] concurrent fetch error: {result}")
        return None

    async def _fetch_via_slug(
        self,
        session: aiohttp.ClientSession,
        slug: Optional[str]
    ) -> Optional[Dict]:
        if not slug:
            return None
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        data = await self._request_with_backoff(session, "GET", url)
        if not data or not isinstance(data, list):
            return None
        event = data[0]
        payload = {
            "question": event.get("question") or event.get("title"),
            "rules": event.get("rules"),
            "market_prob": self._extract_market_probability(event.get("markets", [{}])[0]) if event.get("markets") else 0.0,
            "outcomes": event.get("markets") or [],
            "slug": slug,
            "source": "concurrent_slug"
        }
        return self._validate_event_payload(payload, "concurrent_slug")

    async def _fetch_via_markets(
        self,
        session: aiohttp.ClientSession,
        event_query: str,
        slug: Optional[str]
    ) -> Optional[Dict]:
        if slug:
            url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
        else:
            encoded_query = quote_plus(event_query[:120])
            url = f"https://gamma-api.polymarket.com/markets?query={encoded_query}&limit=5"
        markets = await self._request_with_backoff(session, "GET", url)
        if not markets or not isinstance(markets, list):
            return None
        market = markets[0]
        payload = {
            "question": market.get("question") or market.get("title"),
            "rules": market.get("rules"),
            "market_prob": self._extract_market_probability(market),
            "outcomes": [market],
            "source": "concurrent_markets"
        }
        return self._validate_event_payload(payload, "concurrent_markets")

    async def _fetch_via_graphql(
        self,
        session: aiohttp.ClientSession,
        event_query: str,
        slug: Optional[str]
    ) -> Optional[Dict]:
        search_term = slug or event_query[:120]
        graphql_query = """
        query MarketSearch($term: String!) {
            markets(searchTerm: $term, limit: 5) {
                question
                slug
                rules
                outcomes { name price }
            }
        }
        """
        payload = {
            "query": graphql_query,
            "variables": {"term": search_term}
        }
        data = await self._request_with_backoff(
            session,
            "POST",
            self.POLYMARKET_GRAPHQL_URL,
            json_payload=payload,
            headers={"Content-Type": "application/json"}
        )
        markets = (((data or {}).get("data") or {}).get("markets") or [])
        if not markets:
            return None
        market = markets[0]
        payload = {
            "question": market.get("question"),
            "rules": market.get("rules"),
            "market_prob": self._extract_market_probability(market),
            "outcomes": market.get("outcomes", []),
            "source": "concurrent_graphql"
        }
        return self._validate_event_payload(payload, "concurrent_graphql")

    def _extract_market_probability(self, market: Optional[Dict[str, Any]]) -> float:
        """Extract Yes probability from generic Polymarket payload."""
        if not isinstance(market, dict):
            return 0.0
        prob = None
        if "yesPrice" in market:
            prob = market.get("yesPrice")
        elif "price" in market:
            prob = market.get("price")
        elif market.get("outcomes"):
            for outcome in market["outcomes"]:
                name = (outcome.get("name") or "").lower()
                if name in {"yes", "y"}:
                    prob = outcome.get("price")
                    break
            if prob is None:
                first = market["outcomes"][0]
                prob = first.get("price")
        try:
            value = float(prob)
            if value <= 1:
                value *= 100
            return value
        except (TypeError, ValueError):
            return 0.0

    def _calculate_days_left(self, end_date_str: str) -> int:
        """Calculate days until market resolution."""
        try:
            # Parse ISO format date
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            now = datetime.now(end_date.tzinfo) if end_date.tzinfo else datetime.now()
            delta = end_date - now
            return self._sanitize_days_left(delta.days, "calculate_days_left")
        except Exception as exc:
            print(f"⚠️ Failed to parse end date '{end_date_str}': {exc}")
            return self._sanitize_days_left(30, "calculate_days_left_fallback")
