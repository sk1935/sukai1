"""
输出层（Output Formatter）：
根据 OPTIMIZATION_NOTES.md 的五层架构设计

职责：
- 将最终结果输出为中文报告
- 包含：市场概率、AI 共识概率、AI 观点总结（中文）
- 支持单选项和多选项两种格式
- 自动区分候选人型事件和条件型事件，使用不同模板

输入：事件数据 + 融合结果
输出：格式化的中文 Markdown 字符串（Telegram 消息）
"""
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


class OutputFormatter:
    """
    Formats prediction results for Telegram Markdown output.
    
    格式化预测结果为中文报告：
    - 单选项：显示融合预测、市场价格、AI摘要等
    - 多选项：显示每个选项的预测排名和详细信息
    - 所有输出均为中文
    - 自动区分候选人型和条件型事件
    """
    
    def __init__(self):
        pass

    def format_low_probability_notice(
        self,
        event_data: Dict,
        threshold: float,
        max_probability: float
    ) -> str:
        """Provide a markdown formatted notice when event is filtered out."""
        question = self.safe_markdown_text(event_data.get("question", "该事件"))
        threshold_val = max(0.0, threshold)
        max_val = max(0.0, max_probability)
        return (
            f"⚠️ *低概率提醒*\n\n"
            f"事件「{question}」的最高市场概率仅为 {max_val:.2f}%，"
            f"低于设定阈值 {threshold_val:.2f}% 。\n"
            f"为保证报告质量，已暂时跳过该事件的深度预测。"
        )

    @staticmethod
    def _extract_trade_signal_data(trade_data: Optional[Dict]) -> Dict:
        """Return the trade signal dict when already supplied as a flat structure."""
        if isinstance(trade_data, dict):
            return trade_data
        return {}

    @staticmethod
    def _trade_signal_icon(signal: Optional[str]) -> str:
        signal_upper = (signal or "HOLD").upper()
        icon_map = {
            "BUY": "💰",
            "SELL": "❌",
            "HOLD": "⚠️",
        }
        return icon_map.get(signal_upper, "⚠️")

    @staticmethod
    def _sanitize_reasoning_text(text: Optional[str], context: str = "output") -> str:
        if text is None:
            return ""
        if isinstance(text, (dict, list)):
            try:
                cleaned = json.dumps(text, ensure_ascii=False)
            except (TypeError, ValueError):
                cleaned = str(text)
        else:
            cleaned = str(text)
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
        cleaned = re.sub(r'[_*\[\]\(\)]', '', cleaned)
        return cleaned

    @staticmethod
    def _reasoning_similarity(text_a: str, text_b: str) -> float:
        if not text_a or not text_b:
            return 0.0
        return SequenceMatcher(None, text_a, text_b).ratio()

    @staticmethod
    def _build_trade_signal_banner(trade_data: Optional[Dict]) -> str:
        """Render concise trade signal banner for Telegram output."""
        option_label = None
        if isinstance(trade_data, dict):
            option_label = trade_data.get("option") or trade_data.get("option_name")
        data = OutputFormatter._extract_trade_signal_data(trade_data)
        required_keys = ("signal", "ev", "annualized_ev", "risk_factor", "signal_reason")
        # [FIX] Skip banner entirely when critical fields are missing to avoid noisy fallbacks.
        if not data or any(data.get(key) in (None, "") for key in required_keys):
            print("[TRADE_SIGNAL] banner unavailable (missing inputs)")
            return ""

        signal = (data.get("signal") or "HOLD").upper()
        icon = OutputFormatter._trade_signal_icon(signal)

        ev_display = OutputFormatter._fmt_percent(data.get("ev"), signed=True)
        annualized_display = OutputFormatter._fmt_percent(data.get("annualized_ev"), signed=True)
        risk_display = OutputFormatter._fmt_number(data.get("risk_factor"))
        reason_text = OutputFormatter.safe_markdown_text(str(data.get("signal_reason", "")).strip()[:200])

        # [FIX] Include option context when available so users know which outcome the signal targets.
        option_suffix = f" — {OutputFormatter.safe_markdown_text(option_label)}" if option_label else ""
        banner = (
            f"{icon} {signal}{option_suffix}\n"
            f"EV: {ev_display} | Annualized EV: {annualized_display} | Risk: {risk_display}\n"
            f"Reason: {reason_text}\n"
        )
        print(
            f"[TRADE_SIGNAL] banner signal={signal} ev={ev_display} "
            f"annualized={annualized_display} risk={risk_display}"
        )
        return banner
    
    def _build_trade_signal_explanation(
        self,
        trade_data: Dict,
        fusion_result: Optional[Dict],
        event_data: Optional[Dict]
    ) -> str:
        basis_parts: List[str] = []
        fusion_result = fusion_result or {}
        event_data = event_data or {}
        model_prob = fusion_result.get("model_only_prob")
        final_prob = fusion_result.get("final_prob")
        market_prob = event_data.get("market_prob")
        if model_prob is not None:
            basis_parts.append(f"AI共识 {self._fmt_percent(model_prob)}")
        if final_prob is not None:
            basis_parts.append(f"融合后 {self._fmt_percent(final_prob)}")
        if market_prob is not None:
            basis_parts.append(f"市场隐含 {self._fmt_percent(market_prob)}")
        if model_prob is not None and market_prob is not None:
            diff = model_prob - market_prob
            basis_parts.append(f"差值 {self._fmt_percent(diff, signed=True)}")
        weights = fusion_result.get("fusion_weights") or {}
        if weights:
            model_weight = weights.get("model_weight")
            market_weight = weights.get("market_weight")
            if model_weight is not None and market_weight is not None:
                basis_parts.append(
                    f"权重 AI {self._fmt_percent(model_weight * 100)} / 市场 {self._fmt_percent(market_weight * 100)}"
                )
        conf_factor = fusion_result.get("model_confidence_factor")
        if conf_factor is not None:
            basis_parts.append(f"模型信心因子 {self._fmt_number(conf_factor)}")
        full_analysis = event_data.get("full_analysis") or {}
        sentiment_trend = full_analysis.get("sentiment_trend")
        sentiment_score = full_analysis.get("sentiment_score")
        if sentiment_trend:
            score_str = self._fmt_number(sentiment_score, signed=True)
            basis_parts.append(f"舆情 {sentiment_trend} (score {score_str})")
        threshold = trade_data.get("edge_threshold")
        if threshold is not None:
            basis_parts.append(f"触发阈值 {self._fmt_percent(threshold * 100)}")
        slippage_fee = trade_data.get("slippage_fee")
        if slippage_fee is not None:
            basis_parts.append(f"成本假设 {self._fmt_percent(slippage_fee * 100)}")
        explanation_lines = []
        if basis_parts:
            explanation_lines.append("🧾 *信号依据:* " + "; ".join(basis_parts))
        return "\n".join(explanation_lines)

    def _render_trade_signal_section(
        self,
        trade_data: Optional[Dict],
        fusion_result: Optional[Dict],
        event_data: Optional[Dict]
    ) -> str:
        banner = self._build_trade_signal_banner(trade_data)
        if not banner:
            return "⚠️ *交易信号:* 暂无信号（数据不足或模型未触发）"
        explanation = self._build_trade_signal_explanation(
            self._extract_trade_signal_data(trade_data),
            fusion_result,
            event_data
        )
        if explanation:
            return f"{banner}\n{explanation}"
        return banner


    @staticmethod
    def _finalize_reasoning_text(text: str, limit: int = 300) -> str:
        if not text:
            return ""
        cleaned = OutputFormatter._sanitize_reasoning_text(text, context="output_formatting")
        cleaned = cleaned.replace("Parsed from unstructured response.", "").replace("Parsed from unstructured response", "").strip()
        
        truncated = False
        if len(cleaned) > limit:
            truncated = True
            sentences = re.split(r'(?<=[。！？.!?])\s+', cleaned)
            rebuilt = []
            total = 0
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if total + len(sentence) > limit:
                    break
                rebuilt.append(sentence)
                total += len(sentence)
            cleaned = " ".join(rebuilt).strip() or cleaned[:limit]
        if truncated and not cleaned.endswith(('。', '！', '？', '.', '!', '?', '…')):
            cleaned = cleaned.rstrip('…') + "..."
        elif not truncated and cleaned and cleaned[-1] not in ('。', '！', '？', '.', '!', '?'):
            cleaned += "。"
        print(f"[SUMMARY] TruncatedReasoning(len={len(cleaned)})")
        return cleaned

    @staticmethod
    def _build_normalization_banner(normalization_info: Optional[Dict]) -> str:
        if not normalization_info:
            return ""
        event_type = normalization_info.get("event_type", "unknown")
        normalized_flag = normalization_info.get("normalized", False)
        reason = normalization_info.get("reason")
        raw_total_before = normalization_info.get("total_before")
        total_before = raw_total_before if isinstance(raw_total_before, (int, float)) else None
        if total_before is None:
            total_before = 0.0
        
        banner = ""
        # 检查是否显示安全归一化横幅（仅当原始总和 < 0.95 或 > 1.05 时）
        guard_fraction = (total_before / 100.0) if total_before else 0.0
        should_show_guard_banner = guard_fraction < 0.95 or guard_fraction > 1.05
        
        if event_type == "mutually_exclusive" and normalized_flag:
            banner = "ℹ️ 互斥事件（所有选项已归一化为 100%）"
            if reason == "sum_guard" and should_show_guard_banner:
                banner += "\nℹ️ 安全归一化已启用（AI 预测总和异常，已缩放至 100%）"
                print(f"[FORMAT] NormalizationBanner shown (guard_fraction={guard_fraction:.3f})")
            else:
                print(f"[FORMAT] NormalizationBanner hidden (guard_fraction={guard_fraction:.3f} in range)")
        elif reason == "sum_guard" and normalized_flag and should_show_guard_banner:
            banner = "ℹ️ 安全归一化已启用（AI 预测总和异常，已缩放至 100%）"
            print(f"[FORMAT] NormalizationBanner shown (guard_fraction={guard_fraction:.3f})")
        elif event_type == "conditional" and not normalized_flag:
            banner = "ℹ️ *条件事件为独立市场（概率未归一化）*"
        else:
            print(f"[FORMAT] NormalizationBanner hidden (reason={reason}, normalized={normalized_flag})")
        if banner:
            log_banner = banner.replace('\n', ' ')
            print(f"[FORMAT] type={event_type} normalized={normalized_flag} banner=\"{log_banner}\"")
            return banner + "\n\n"
        return ""
    
    @staticmethod
    def escape_markdown(text: str, preserve_asterisk: bool = False) -> str:
        """
        Escape special characters for Telegram Markdown.
        
        Telegram Markdown special characters: * _ [ ] ( ) ` ~
        
        Args:
            text: Text to escape
            preserve_asterisk: If True, don't escape * (useful when text will be inside *bold* tags)
        """
        if not text:
            return ""
        # Characters that need to be escaped in Telegram Markdown
        escape_chars = ['_', '[', ']', '(', ')', '`', '~']
        if not preserve_asterisk:
            escape_chars.append('*')
        
        escaped = str(text)
        for char in escape_chars:
            escaped = escaped.replace(char, f'\\{char}')
        return escaped
    
    @staticmethod
    def _fmt_number(value: Optional[float], decimals: int = 2, signed: bool = False, default: str = "—") -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        fmt = f"{{:+.{decimals}f}}" if signed else f"{{:.{decimals}f}}"
        return fmt.format(numeric)
    
    @staticmethod
    def _fmt_percent(value: Optional[float], signed: bool = False, default: str = "—") -> str:
        formatted = OutputFormatter._fmt_number(value, decimals=2, signed=signed, default=default)
        if formatted == default:
            return default
        return f"{formatted}%"
    
    @staticmethod
    def safe_markdown_text(text: str, max_length: int = None) -> str:
        """
        Safely prepare text for Markdown, escaping special characters.
        Also truncate if needed.
        """
        if not text:
            return ""
        
        # First escape special characters
        safe_text = OutputFormatter.escape_markdown(str(text))
        
        # Truncate if needed
        if max_length and len(safe_text) > max_length:
            safe_text = safe_text[:max_length - 3] + "..."
        
        return safe_text
    
    def classify_event_type(self, outcomes: List[Dict]) -> str:
        """
        分类事件类型：候选人型 vs 条件型
        
        Args:
            outcomes: 选项列表，每个包含 name 字段
        
        Returns:
            "candidate" - 候选人型事件（人名、团队名等）
            "conditional" - 条件型事件（数值区间、日期等）
        """
        if not outcomes or len(outcomes) == 0:
            return "candidate"  # 默认
        
        candidate_count = 0
        conditional_count = 0
        
        # 条件型特征关键词
        conditional_keywords = [
            '%', '<', '>', 'below', 'above', 'between', 'range',
            'before', 'after', 'by', 'in', 'on',
            '$', '€', '¥', 'million', 'billion', 'trillion',
            'january', 'february', 'march', 'april', 'may', 'june',
            'july', 'august', 'september', 'october', 'november', 'december',
            '2024', '2025', '2026', '2027', '2028', '2029', '2030',
            'Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2',
            '-', '–', '—',  # 区间符号
            'less than', 'more than', 'at least', 'at most',
            'never', 'no', 'yes'  # 简单选项也视为条件型
        ]
        
        for outcome in outcomes:
            name = outcome.get('name', '').strip()
            if not name:
                continue
            
            name_lower = name.lower()
            
            # 检查条件型特征
            has_conditional = any(keyword in name_lower for keyword in conditional_keywords)
            
            # 检查是否包含数字
            has_number = bool(re.search(r'\d', name))
            
            # 检查人名特征
            # 1. 包含空格（如 "John Smith"）
            # 2. 首字母大写（如 "Trump"）
            # 3. 不包含特殊符号
            has_space = ' ' in name and len(name.split()) <= 4  # 人名通常不超过4个词
            is_capitalized = name[0].isupper() if name else False
            has_no_special = not bool(re.search(r'[%<>$€¥\-–—\d]', name))
            
            # 判断逻辑
            if has_conditional or has_number:
                conditional_count += 1
            elif has_space and is_capitalized and has_no_special:
                candidate_count += 1
            elif is_capitalized and has_no_special and len(name.split()) <= 2:
                # 单个大写词（如 "Trump", "Biden"）
                candidate_count += 1
            else:
                # 默认归为条件型
                conditional_count += 1
        
        print(f"📊 事件类型判断: 候选人={candidate_count}, 条件型={conditional_count}")
        
        # 判断整体类型（多数原则）
        if candidate_count > conditional_count:
            return "candidate"
        else:
            return "conditional"
    
    def format_conditional_prediction(
        self,
        event_data: Dict,
        outcomes: List[Dict],
        normalization_info: Dict = None,
        fusion_result: Optional[Dict] = None,
        trade_signal: Optional[Dict] = None
    ) -> str:
        """
        格式化条件型事件预测输出（数值区间、日期等）
        采用趋势型模板，不使用"名次"或"候选人"措辞
        """
        question = event_data.get("question", "未知事件")
        question_escaped = self.safe_markdown_text(question)
        
        # 标题：根据事件类型选择
        event_type = normalization_info.get("event_type", "conditional") if normalization_info else "conditional"
        if event_type == "mutually_exclusive":
            title_type = "📊 多选项（互斥）预测："
            print(f"[FORMAT] TitleType=mutually_exclusive")
        else:
            title_type = "📊 *条件事件预测：*"
            print(f"[FORMAT] TitleType={event_type}")
        output = f"{title_type} {question_escaped}\n\n"
        
        # 【集成】添加世界情绪和新闻摘要显示（条件型事件）
        full_analysis = event_data.get("full_analysis")
        if full_analysis:
            # 世界情绪（轻量描述模式）
            world_temp_data = event_data.get("world_temp_data")
            if world_temp_data:
                description = world_temp_data.get("description", "未知")
                positive = world_temp_data.get("positive", 0)
                negative = world_temp_data.get("negative", 0)
                neutral = world_temp_data.get("neutral", 0)
                output += f"🧠 *世界情绪:* {description}（正面: {positive}, 负面: {negative}, 中性: {neutral}）\n\n"
            elif event_data.get("world_sentiment_summary"):
                output += f"🧠 *世界情绪:* {self.safe_markdown_text(event_data.get('world_sentiment_summary', ''))}\n\n"
            
            # 新闻摘要
            news_summary = event_data.get("news_summary")
            if news_summary:
                news_preview = news_summary[:100] + "..." if len(news_summary) > 100 else news_summary
                output += f"📰 *新闻摘要:* {self.safe_markdown_text(news_preview)}\n\n"
        
        banner = self._build_normalization_banner(normalization_info)
        if banner:
            output += banner

        if normalization_info and normalization_info.get("event_type") != "conditional":
            total_after = normalization_info.get("total_after")
            error = normalization_info.get("error", 0)
            if total_after is None or total_after == 0:
                ai_sum = sum(
                    outcome.get('model_only_prob') or 0
                    for outcome in outcomes
                    if outcome.get('model_only_prob') is not None
                )
                if ai_sum > 0:
                    total_after = ai_sum
                    print(f"[DEBUG] normalization_info total_after 为 0，从 outcomes 计算得到: {(total_after or 0.0):.2f}%")
            if total_after is not None:
                total_after = total_after or 0.0
                error = error or 0.0
                output += f"📊 *归一化检查：* ΣAI预测 = {(total_after or 0.0):.2f}%\n"
                if error and error > 0.01:
                    output += f"⚠️ 归一化误差: {(error or 0.0):.2f}%\n"
                output += "\n"
        
        # 排序（按AI预测从高到低）
        sorted_outcomes = sorted(outcomes, key=lambda x: x.get("model_only_prob") or x.get("prediction", 0), reverse=True)
        
        # 各条件选项的AI预测和市场价格
        output += "📈 *各条件预测对比*\n\n"
        
        # 计算实际AI预测总和（用于验证）
        # 【Bug修复】只计算有效的 model_only_prob，不使用 prediction 作为 fallback
        ai_sum = 0.0
        for outcome in sorted_outcomes:
            ai_prob = outcome.get('model_only_prob')  # 只使用 model_only_prob，不使用 prediction
            if ai_prob is not None:
                ai_sum += ai_prob
        
        for outcome in sorted_outcomes:
            name = outcome.get('name', '未知选项')
            # 【Bug修复】优先使用归一化后的 model_only_prob（纯AI预测）
            # 如果 model_only_prob 为 None，说明该选项被跳过了归一化，不应该显示 AI 预测
            ai_prob = outcome.get('model_only_prob')
            market_prob = outcome.get('market_prob', 0)
            
            # 转义Markdown
            name_escaped = self.safe_markdown_text(name)
            
            # 检查是否有有效的AI预测
            summary = outcome.get('summary', '')
            has_fallback = any(word in summary for word in [
                "暂无", "暂不可用", "没有可用的模型", "使用市场概率", "使用市场价格"
            ])
            
            # 【修复】确保 ai_prob 和 market_prob 不为 None 且为数值类型
            if ai_prob is None:
                has_ai = False  # 明确标记为没有 AI 预测
            else:
                try:
                    ai_prob_val = float(ai_prob)
                    market_prob_val = float(market_prob) if market_prob is not None else 0.0
                    has_ai = (ai_prob_val > 0 and ai_prob_val <= 100) and not has_fallback
                    
                    # 【Bug修复】验证 ai_prob 是否异常（如 100.0% 对于单个选项来说通常不合理）
                    if ai_prob_val == 100.0 and len(sorted_outcomes) > 1:
                        print(f"[WARNING] 检测到异常 AI 预测值：{name} = {ai_prob_val}%，可能存在归一化错误")
                    
                    if has_ai:
                        ai_prob_str = self._fmt_percent(ai_prob_val)
                        market_prob_str = self._fmt_percent(market_prob_val)
                        output += f"• *{name_escaped}*\n"
                        output += f"  AI预测: {ai_prob_str} | 市场: {market_prob_str}"
                        
                        # 计算偏差（使用归一化后的AI概率）
                        diff = ai_prob_val - market_prob_val
                        diff = diff or 0.0
                        if diff is None:
                            print("⚙️ [SAFE] 修复空值保护: diff")
                            diff = 0.0
                        if abs(diff) > 5:
                            diff_display = self._fmt_percent(abs(diff))
                            if diff > 0:
                                output += f" \\(AI看好 \\+{diff_display}\\)"
                            else:
                                output += f" \\(市场看好 \\+{diff_display}\\)"
                        output += "\n\n"
                    else:
                        # 只有市场价格
                        output += f"• *{name_escaped}*\n"
                        output += f"  市场: {self._fmt_percent(market_prob_val)}\n\n"
                except (TypeError, ValueError) as e:
                    print(f"⚠️ 选项 {name} 的数据格式错误（ai_prob: {ai_prob}, market_prob: {market_prob}），跳过格式化: {e}")
                    try:
                        market_prob_val = float(market_prob) if market_prob is not None else 0.0
                        output += f"• *{name_escaped}*\n"
                        output += f"  市场: {self._fmt_percent(market_prob_val)}\n\n"
                    except (TypeError, ValueError):
                        output += f"• *{name_escaped}*\n"
                        output += f"  市场: N/A\n\n"
            
            # 如果 ai_prob 为 None，直接使用市场价格
            if ai_prob is None:
                try:
                    market_prob_val = float(market_prob) if market_prob is not None else 0.0
                    output += f"• *{name_escaped}*\n"
                    output += f"  市场: {self._fmt_percent(market_prob_val)}\n\n"
                except (TypeError, ValueError):
                    output += f"• *{name_escaped}*\n"
                    output += f"  市场: N/A\n\n"
        
        # AI逻辑摘要（使用第一个有效摘要）
        first_summary = None
        finalized_summary_text = ""  # Ensure variable always initialized to avoid NameError
        for outcome in sorted_outcomes:
            summary = outcome.get('summary', '')
            if summary and len(summary) > 30 and '暂无' not in summary:
                first_summary = summary
                break

        if first_summary:
            finalized_summary = self._finalize_reasoning_text(first_summary, limit=400)
            if finalized_summary:
                finalized_summary_text = finalized_summary
                summary_escaped = self.safe_markdown_text(finalized_summary)
                output += f"🧠 *AI逻辑摘要*\n\n{summary_escaped}\n\n"
        else:
            finalized_summary_text = ""  # 强制默认值，避免后续 DeepSeek 比较时报错
        
        # 市场偏离信号
        output += "🚨 *市场偏离信号*\n\n"
        
        significant_deviations = []
        for outcome in sorted_outcomes:
            name = outcome.get('name', '未知选项')
            # 使用归一化后的AI概率
            ai_prob = outcome.get('model_only_prob')
            if ai_prob is None:
                ai_prob = outcome.get('prediction', 0)
            market_prob = outcome.get('market_prob', 0)
            # 【防御】确保所有值不为 None
            ai_prob = ai_prob or 0.0
            market_prob = market_prob or 0.0
            if ai_prob is None:
                print("⚙️ [SAFE] 修复空值保护: ai_prob (significant_deviations)")
                ai_prob = 0.0
            if market_prob is None:
                print("⚙️ [SAFE] 修复空值保护: market_prob (significant_deviations)")
                market_prob = 0.0
            diff = (ai_prob or 0.0) - (market_prob or 0.0)
            if diff is None:
                print("⚙️ [SAFE] 修复空值保护: diff (significant_deviations)")
                diff = 0.0
            if abs(diff) > 8:
                name_escaped = self.safe_markdown_text(name)
                if diff > 0:
                    significant_deviations.append(
                        f"• \"{name_escaped}\" AI高估 \\(\\+{self._fmt_percent(abs(diff))}\\)"
                    )
                else:
                    significant_deviations.append(
                        f"• \"{name_escaped}\" 市场高估 \\(\\+{self._fmt_percent(abs(diff))}\\)"
                    )
        
        if significant_deviations:
            output += "\n".join(significant_deviations) + "\n\n"
        else:
            output += "• 各条件预测与市场基本一致\n\n"
        
        # DeepSeek 独立区块（条件型事件也显示）
        deepseek_section = ""
        deepseek_reasoning = None
        if fusion_result and fusion_result.get('deepseek_reasoning'):
            deepseek_reasoning = fusion_result.get('deepseek_reasoning')
        elif outcomes and len(outcomes) > 0:
            for outcome in outcomes:
                if 'deepseek_reasoning' in outcome and outcome['deepseek_reasoning']:
                    deepseek_reasoning = outcome['deepseek_reasoning']
                    break
        
        finalized_summary_text = finalized_summary_text or ""  # 防御性赋值，确保存在

        if deepseek_reasoning:
            finalized_deepseek = self._finalize_reasoning_text(deepseek_reasoning, limit=500)
            if finalized_deepseek and finalized_summary_text:
                try:
                    similarity = self._reasoning_similarity(finalized_summary_text, finalized_deepseek)
                    if similarity >= 0.9:
                        print("[FORMAT] Skipped redundant model insight")
                        finalized_deepseek = ""
                except Exception as exc:
                    logger.exception("DeepSeek 摘要去重时发生异常: %s", exc)
            if finalized_deepseek:
                deepseek_text = self.safe_markdown_text(finalized_deepseek)
                deepseek_section = f"\n🧠 *模型洞察 \\(DeepSeek\\)*\n━━━━━━━━━━━━━━━━━━━━\n{deepseek_text}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # 风险提示
        output += "⚠️ *风险提示*\n"
        output += "本预测基于AI语言模型推理，不代表真实概率。\n"
        output += "请谨慎参考，自行判断。\n\n"
        
        # DeepSeek 区块
        if deepseek_section:
            output += deepseek_section
        
        # 规则
        rules = event_data.get("rules", "")
        if rules and rules != "查看原链接获取完整规则":
            rules_short = rules[:150]
            rules_escaped = self.safe_markdown_text(rules_short)
            output += f"📜 *规则*\n{rules_escaped}...\n\n"
        
        # 【归一化验证信息】
        banner_candidate = self._build_normalization_banner(normalization_info)
        if banner_candidate:
            output += banner_candidate

        if normalization_info and normalization_info.get("normalized"):
            total_after = normalization_info.get("total_after", 0)
            error = normalization_info.get("error", 0)
            if not total_after:
                ai_sum = sum(
                    outcome.get('model_only_prob') or 0
                    for outcome in sorted_outcomes
                    if outcome.get('model_only_prob') is not None
                )
                if ai_sum > 0:
                    total_after = ai_sum
            if total_after:
                try:
                    total_after_val = float(total_after)
                    error_val = float(error) if error is not None else 0.0
                    if error_val <= 0.01:
                        output += f"✅ *概率归一化完成* \\(总和={total_after_val:.2f}%，误差≤{error_val:.4f}%\\)\n"
                    else:
                        output += f"⚠️ *归一化警告* \\(总和={total_after_val:.2f}%，误差={error_val:.4f}%\\)\n"
                except (TypeError, ValueError):
                    print("⚠️ total_after 或 error 数据格式错误，跳过格式化")
        elif not normalization_info:
            # 如果没有归一化信息，手动计算总和
            ai_total = sum(
                outcome.get('model_only_prob') or outcome.get('prediction', 0) or 0
                for outcome in sorted_outcomes
                if outcome.get('model_only_prob') is not None or outcome.get('prediction') is not None
            )
            # 【防御】确保 ai_total 不为 None
            ai_total = ai_total or 0.0
            if ai_total is None:
                print("⚙️ [SAFE] 修复空值保护: ai_total")
                ai_total = 0.0
            output += f"📊 *AI预测总和：* {(ai_total or 0.0):.2f}%\n"

        trade_section = self._render_trade_signal_section(trade_signal, fusion_result, event_data)
        if trade_section:
            output += "\n" + trade_section
        
        return output
    
    def format_prediction(
        self,
        event_data: Dict,
        fusion_result: Dict,
        trade_signal: Optional[Dict] = None
    ) -> str:
        """
        Format prediction result as Telegram message.
        
        Args:
            event_data: Dict with 'question', 'market_prob', 'rules', 'trend'
            fusion_result: Dict with 'final_prob', 'uncertainty', 'summary', 'disagreement'
        
        Returns:
            Formatted Markdown string
        """
        # Format trend arrow
        trend = event_data.get("trend", "→")
        if isinstance(trend, str):
            trend_symbol = trend
        else:
            trend_symbol = "↑" if trend > 0 else "↓" if trend < 0 else "→"
        
        # Truncate rules if too long
        rules = event_data.get("rules", "")
        # If it's mock data, keep the warning visible
        if event_data.get("is_mock", False):
            short_rules = rules
        else:
            short_rules = rules[:150] + "..." if len(rules) > 150 else rules
        
        # Translate disagreement level
        disagreement_map = {
            "Low": "低",
            "Medium": "中",
            "High": "高",
            "低": "低",
            "中": "中",
            "高": "高",
            "Unknown": "未知"
        }
        disagreement_raw = fusion_result.get('disagreement', 'Unknown')
        disagreement_cn = disagreement_map.get(disagreement_raw, disagreement_raw if disagreement_raw in ["低", "中", "高"] else "未知")
        
        # Get pure model prediction (if available) or calculate from fusion result
        model_only_prob = fusion_result.get('model_only_prob')
        market_prob = event_data.get('market_prob', 0)
        model_count = fusion_result.get('model_count', 0)
        final_prob = fusion_result.get('final_prob', 0)
        
        # 【防御】确保关键概率值不为 None
        market_prob = market_prob or 0.0
        final_prob = final_prob or 0.0
        if market_prob is None:
            print("⚙️ [SAFE] 修复空值保护: market_prob (format_prediction)")
            market_prob = 0.0
        if final_prob is None:
            print("⚙️ [SAFE] 修复空值保护: final_prob (format_prediction)")
            final_prob = 0.0
        
        from src.fusion_engine import FusionEngine

        # Determine if we have valid AI prediction
        has_ai_prediction = False
        if model_only_prob is not None:
            # Direct value from fusion engine
            has_ai_prediction = True
        elif model_count > 0 and final_prob > 0:
            # Try to reverse calculate only if we have model responses
            try:
                model_only_prob = (final_prob - FusionEngine.MARKET_WEIGHT * market_prob) / FusionEngine.MODEL_WEIGHT
                # Validate the result makes sense
                if 0 <= model_only_prob <= 100:
                    has_ai_prediction = True
                else:
                    model_only_prob = None
            except (ZeroDivisionError, ValueError, TypeError):
                model_only_prob = None
        else:
            # No models responded, use final_prob as fallback (which is just market_prob)
            model_only_prob = None
        
        # Build output in Chinese
        # Escape special characters in user-provided content
        question_escaped = self.safe_markdown_text(event_data.get('question', '未知事件'))
        finalized_logic_summary = self._finalize_reasoning_text(fusion_result.get('summary', '暂无摘要'), limit=400)
        if not finalized_logic_summary:
            finalized_logic_summary = "暂无摘要"
        summary_escaped = self.safe_markdown_text(finalized_logic_summary)
        rules_escaped = self.safe_markdown_text(short_rules)
        
        # 【修复】确保 model_only_prob 不为 None 且为数值类型
        if has_ai_prediction and model_only_prob is not None:
            try:
                model_only_prob_val = float(model_only_prob)
                uncertainty_val = float(fusion_result.get('uncertainty', 0)) if fusion_result.get('uncertainty') is not None else 0.0
                ai_prediction_line = (
                    f"🤖 *纯AI预测:* {self._fmt_percent(model_only_prob_val)} ± "
                    f"{self._fmt_percent(uncertainty_val)}"
                )
            except (TypeError, ValueError):
                print("⚠️ model_only_prob 数据格式错误，跳过格式化")
                ai_prediction_line = f"🤖 *纯AI预测:* 暂不可用 (数据格式错误)"
        else:
            ai_prediction_line = f"🤖 *纯AI预测:* 暂不可用 (模型未响应)"
        
        # Check for DeepSeek reasoning - 独立区块显示
        deepseek_reasoning = fusion_result.get('deepseek_reasoning')
        deepseek_section = ""
        if deepseek_reasoning:
            finalized_deepseek = self._finalize_reasoning_text(deepseek_reasoning, limit=500)
            if finalized_deepseek and finalized_logic_summary:
                similarity = self._reasoning_similarity(finalized_logic_summary, finalized_deepseek)
                if similarity >= 0.9:
                    print("[FORMAT] Skipped redundant model insight")
                    finalized_deepseek = ""
            if finalized_deepseek:
                deepseek_text = self.safe_markdown_text(finalized_deepseek)
                deepseek_section = f"\n🧠 *模型洞察 \\(DeepSeek\\)*\n━━━━━━━━━━━━━━━━━━━━\n{deepseek_text}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Model versions section
        model_versions = fusion_result.get('model_versions', {})
        versions_section = ""
        if model_versions:
            versions_lines = []
            for model_id, version_info in model_versions.items():
                display_name = version_info.get("display_name", model_id)
                last_updated = version_info.get("last_updated", "未知")
                versions_lines.append(f"• {display_name} \\(更新: {last_updated}\\)")
            
            if versions_lines:
                versions_text = "\n".join(versions_lines)
                versions_section = f"\n🧩 *模型版本摘要*\n{versions_text}\n\n"
        
        # Weight source section
        weight_source = fusion_result.get('weight_source', {})
        weight_source_section = ""
        if weight_source:
            source = weight_source.get("source", "未知")
            updated_at = weight_source.get("updated_at", "未知")
            file_name = weight_source.get("file", "未知")
            weight_source_section = f"\n📊 *模型权重来源:* {file_name} \\| 更新时间: {updated_at}\n\n"
        
        # 事件分析信息（市场趋势、类别、舆情、规则摘要）
        analysis_section = ""
        full_analysis = event_data.get("full_analysis")
        if full_analysis:
            category_display = {
                "geopolitics": "地缘政治",
                "economy": "经济指标",
                "tech": "科技产品",
                "social": "社会事件",
                "sports": "体育赛事",
                "general": "通用事件"
            }
            category_cn = category_display.get(full_analysis.get("event_category", "general"), "通用事件")
            sentiment_map = {"positive": "正面", "negative": "负面", "neutral": "中性", "unknown": "未知"}
            sentiment_cn = sentiment_map.get(full_analysis.get("sentiment_trend", "unknown"), "未知")
            
            # 舆情样本量提示
            sentiment_sample = full_analysis.get('sentiment_sample', 0)
            if sentiment_sample < 30:
                sample_hint = "（弱信号）"
            elif sentiment_sample < 100:
                sample_hint = "（中信号）"
            else:
                sample_hint = "（强信号）"
            
            # 【防御】确保 sentiment_score 不为 None
            sentiment_score = full_analysis.get('sentiment_score') or 0.0
            if sentiment_score is None:
                print("⚠️ sentiment_score is None, using default 0.0")
                sentiment_score = 0.0
            
            sentiment_score_str = self._fmt_number(sentiment_score, signed=True)
            analysis_lines = [
                f"🧭 *事件类别:* {category_cn}",
                f"📈 *市场趋势:* {full_analysis.get('market_trend', '数据不足，无法计算')}",
                f"📰 *舆情趋势:* {sentiment_cn} ({sentiment_score_str})，"
                f"样本：{sentiment_sample} 篇{sample_hint}（来源：{full_analysis.get('sentiment_source', '未知')}）",
                f"📜 *规则摘要:* {self.safe_markdown_text(full_analysis.get('rules_summary', '无规则信息'))}"
            ]
            
            # 【集成】添加世界情绪显示（轻量描述模式）
            world_temp_data = event_data.get("world_temp_data")
            if world_temp_data:
                description = world_temp_data.get("description", "未知")
                positive = world_temp_data.get("positive", 0)
                negative = world_temp_data.get("negative", 0)
                neutral = world_temp_data.get("neutral", 0)
                analysis_lines.append(
                    f"🧠 *世界情绪:* {description}（正面: {positive}, 负面: {negative}, 中性: {neutral}）"
                )
            elif event_data.get("world_sentiment_summary"):
                analysis_lines.append(
                    f"🧠 *世界情绪:* {self.safe_markdown_text(event_data.get('world_sentiment_summary', ''))}"
                )
            
            # 【集成】添加新闻摘要显示
            news_summary = event_data.get("news_summary")
            if news_summary:
                news_preview = news_summary[:100] + "..." if len(news_summary) > 100 else news_summary
                analysis_lines.append(
                    f"📰 *新闻摘要:* {self.safe_markdown_text(news_preview)}"
                )
            
            analysis_section = "\n".join(analysis_lines) + "\n\n"
        
        # 评估摘要（如果有真实标签或回测模式）
        evaluation_section = ""
        if event_data.get("evaluation_mode", False) and event_data.get("true_label") is not None:
            try:
                from metrics import compute_all_metrics
                
                true_label = event_data["true_label"]
                pred_prob = final_prob / 100.0  # 转换为0-1范围
                
                # 计算指标
                eval_metrics = compute_all_metrics(
                    [true_label],
                    [pred_prob] if isinstance(true_label, (int, float)) else pred_prob
                )
                
                # 与基线比较（如果有）
                baseline_diff = None
                p_value = None
                if "baseline_metrics" in event_data:
                    baseline = event_data["baseline_metrics"]
                    # 【防御】确保所有评估指标不为 None
                    brier_base = eval_metrics.get("brier") or 0.0
                    log_loss_base = eval_metrics.get("log_loss") or 0.0
                    ece_base = eval_metrics.get("ece") or 0.0
                    if brier_base is None:
                        print("⚙️ [SAFE] 修复空值保护: brier_base")
                        brier_base = 0.0
                    if log_loss_base is None:
                        print("⚙️ [SAFE] 修复空值保护: log_loss_base")
                        log_loss_base = 0.0
                    if ece_base is None:
                        print("⚙️ [SAFE] 修复空值保护: ece_base")
                        ece_base = 0.0
                    baseline_brier = baseline.get("brier") or 0.0
                    baseline_log_loss = baseline.get("log_loss") or 0.0
                    baseline_ece = baseline.get("ece") or 0.0
                    baseline_diff = {
                        "brier": (brier_base or 0.0) - (baseline_brier or 0.0),
                        "log_loss": (log_loss_base or 0.0) - (baseline_log_loss or 0.0),
                        "ece": (ece_base or 0.0) - (baseline_ece or 0.0)
                    }
                    if "p_value" in event_data:
                        p_value = event_data["p_value"]
                
                # 【防御】确保所有评估指标不为 None
                brier = eval_metrics.get('brier') or 0.0
                log_loss = eval_metrics.get('log_loss') or 0.0
                ece = eval_metrics.get('ece') or 0.0
                sharpness = eval_metrics.get('sharpness') or 0.0
                if brier is None:
                    print("⚙️ [SAFE] 修复空值保护: brier")
                    brier = 0.0
                if log_loss is None:
                    print("⚙️ [SAFE] 修复空值保护: log_loss")
                    log_loss = 0.0
                if ece is None:
                    print("⚙️ [SAFE] 修复空值保护: ece")
                    ece = 0.0
                if sharpness is None:
                    print("⚙️ [SAFE] 修复空值保护: sharpness")
                    sharpness = 0.0
                
                eval_lines = [
                    f"📊 *评估摘要*",
                    f"Brier: {(brier or 0.0):.4f}",
                    f"LogLoss: {(log_loss or 0.0):.4f}",
                    f"ECE: {(ece or 0.0):.4f}",
                    f"Sharpness: {(sharpness or 0.0):.4f}"
                ]
                
                if baseline_diff:
                    eval_lines.append("\n*与基线对比:*")
                    for metric, diff in baseline_diff.items():
                        # 【防御】确保 diff 不为 None
                        diff = diff or 0.0
                        if diff is None:
                            print(f"⚙️ [SAFE] 修复空值保护: baseline_diff[{metric}]")
                            diff = 0.0
                        sign = "+" if diff >= 0 else ""
                        eval_lines.append(f"{metric}: {sign}{(diff or 0.0):.4f}")
                
                if p_value is not None:
                    # 【防御】确保 p_value 不为 None
                    p_value = p_value or 0.0
                    if p_value is None:
                        print("⚙️ [SAFE] 修复空值保护: p_value")
                        p_value = 0.0
                    significance = "***" if p_value < 0.001 else "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
                    eval_lines.append(f"\np-value: {(p_value or 0.0):.4f}{significance}")
                
                evaluation_section = "\n".join(eval_lines) + "\n\n"
            except ImportError:
                pass  # metrics模块未安装时跳过
            except Exception as e:
                print(f"⚠️ 计算评估指标失败: {e}")
        
        # 反从众系数标注
        demarket_note = ""
        if fusion_result.get("demarket_applied"):
            demarket_note = f"\n💡 {fusion_result.get('demarket_note', 'Applied de-marketization penalty.')}\n"

        fusion_weights_info = fusion_result.get("fusion_weights") or {}
        model_weight_pct = self._fmt_percent((fusion_weights_info.get("model_weight", FusionEngine.MODEL_WEIGHT) or 0) * 100)
        market_weight_pct = self._fmt_percent((fusion_weights_info.get("market_weight", FusionEngine.MARKET_WEIGHT) or 0) * 100)
        weight_note = ""
        if model_weight_pct != "—" and market_weight_pct != "—":
            weight_note = f"（AI权重 {model_weight_pct}, 市场权重 {market_weight_pct}）"
        market_price_str = self._fmt_percent(market_prob)
        final_prob_str = self._fmt_percent(final_prob)
        output = f"""📊 *事件:* {question_escaped}

{analysis_section}{ai_prediction_line}
📈 *市场价格:* {market_price_str}
🧠 *融合预测:* {final_prob_str} {weight_note}
{demarket_note}{deepseek_section}{versions_section}{weight_source_section}{evaluation_section}💬 *摘要:* {summary_escaped}
⚖️ *分歧程度:* {disagreement_cn}
📜 *规则:* {rules_escaped}"""
        trade_section = self._render_trade_signal_section(trade_signal, fusion_result, event_data)
        if trade_section:
            output += "\n" + trade_section
        
        return output
    
    def format_multi_option_prediction(
        self,
        event_data: Dict,
        outcomes: List[Dict],
        normalization_info: Dict = None,
        fusion_result: Optional[Dict] = None,
        trade_signal: Optional[Dict] = None
    ) -> str:
        """
        Format multi-option prediction result.
        自动区分候选人型和条件型事件，使用不同模板。
        
        Args:
            event_data: Dict with 'question', 'rules', etc.
            outcomes: List of dicts with 'name', 'prediction', 'market_prob', 'uncertainty', 'summary'
        
        Returns:
            Formatted Markdown string
        """
        # Handle empty outcomes
        if not outcomes:
            question_escaped = self.safe_markdown_text(event_data.get('question', '未知事件'))
            output = f"""📊 *事件:* {question_escaped}

⚠️ *多选项预测结果:*

未能获取选项数据。请稍后重试。
"""
            rules = event_data.get("rules", "")
            if rules and not event_data.get("is_mock", False):
                short_rules = rules[:150] + "..." if len(rules) > 150 else rules
                rules_escaped = self.safe_markdown_text(short_rules)
                output += f"\n📜 *规则:* {rules_escaped}"
            return output
        
        # 【关键改进】分类事件类型
        event_type = self.classify_event_type(outcomes)
        print(f"✅ 事件类型识别为: {event_type}")
        
        # 如果是条件型事件，使用条件型模板
        if event_type == "conditional":
            return self.format_conditional_prediction(
                event_data, 
                outcomes, 
                normalization_info,
                fusion_result=fusion_result,
                trade_signal=trade_signal
            )
        
        # ===== 候选人型事件：保持原有格式 =====
        
        # 初始化 finalized_summary_text，避免 UnboundLocalError
        finalized_summary_text = ""
        
        # Sort outcomes by normalized AI prediction (descending)
        # 使用归一化后的 model_only_prob 进行排序
        sorted_outcomes = sorted(
            outcomes,
            key=lambda x: x.get("model_only_prob") or x.get("prediction", 0),
            reverse=True
        )
        
        print(f"📝 格式化 {len(sorted_outcomes)} 个选项 (候选人型)")
        print(f"   原始 outcomes 长度: {len(outcomes)}")
        print(f"   前3个outcomes: {[o.get('name', 'N/A') for o in outcomes[:3]]}")
        
        if len(sorted_outcomes) == 0:
            print(f"⚠️ 警告: sorted_outcomes 为空！原始 outcomes 长度: {len(outcomes)}")
            print(f"   outcomes内容: {outcomes}")
            question_escaped = self.safe_markdown_text(event_data.get('question', '未知事件'))
            return f"""📊 *事件:* {question_escaped}

⚠️ *多选项预测结果:*

未能获取选项数据。请稍后重试。"""
        
        # Build output - escape question
        question_escaped = self.safe_markdown_text(event_data.get('question', '未知事件'))
        output = f"""📊 *事件:* {question_escaped}

"""
        
        # 【集成】添加世界情绪和新闻摘要显示（多选项事件）
        full_analysis = event_data.get("full_analysis")
        if full_analysis:
            # 世界情绪（轻量描述模式）
            world_temp_data = event_data.get("world_temp_data")
            if world_temp_data:
                description = world_temp_data.get("description", "未知")
                positive = world_temp_data.get("positive", 0)
                negative = world_temp_data.get("negative", 0)
                neutral = world_temp_data.get("neutral", 0)
                output += f"🧠 *世界情绪:* {description}（正面: {positive}, 负面: {negative}, 中性: {neutral}）\n\n"
            elif event_data.get("world_sentiment_summary"):
                output += f"🧠 *世界情绪:* {self.safe_markdown_text(event_data.get('world_sentiment_summary', ''))}\n\n"
            
            # 新闻摘要
            news_summary = event_data.get("news_summary")
            if news_summary:
                news_preview = news_summary[:100] + "..." if len(news_summary) > 100 else news_summary
                output += f"📰 *新闻摘要:* {self.safe_markdown_text(news_preview)}\n\n"
        
        banner_multi = self._build_normalization_banner(normalization_info)
        if banner_multi:
            output += banner_multi
        if normalization_info and normalization_info.get("event_type") != "conditional":
            total_after = normalization_info.get("total_after")
            if total_after is None:
                total_after = sum(
                    outcome.get('model_only_prob') or 0
                    for outcome in outcomes
                    if outcome.get('model_only_prob') is not None
                )
            if total_after:
                output += f"📊 *归一化检查：* ΣAI预测 = {(total_after or 0.0):.2f}%\n\n"
        
        output += """🎯 *多选项预测结果:*

"""
        
        # Add top 3-5 outcomes with details
        for i, outcome in enumerate(sorted_outcomes[:5], 1):
            # Escape option name to prevent Markdown parsing errors
            name = self.safe_markdown_text(outcome.get("name", "未知选项"))
            # 优先使用归一化后的 model_only_prob（纯AI预测）进行排序和显示
            ai_pred = outcome.get("model_only_prob")
            if ai_pred is None:
                ai_pred = outcome.get("prediction", 0)
            pred = outcome.get("prediction", 0)  # 融合后的概率（用于其他用途）
            market = outcome.get("market_prob", 0)
            uncertainty = outcome.get("uncertainty", 10.0)
            
            # Calculate difference using normalized AI prediction (not fused prediction)
            # 使用归一化后的AI预测计算差值
            ai_pred_for_diff = ai_pred if ai_pred is not None else pred
            # 【防御】确保所有值不为 None
            ai_pred_for_diff = ai_pred_for_diff or 0.0
            market = market or 0.0
            if ai_pred_for_diff is None:
                print("⚠️ ai_pred_for_diff is None, using default 0.0")
                ai_pred_for_diff = 0.0
            if market is None:
                print("⚠️ market is None, using default 0.0")
                market = 0.0
            diff = ai_pred_for_diff - market
            diff = diff or 0.0
            if diff is None:
                print("⚠️ diff is None, using default 0.0")
                diff = 0.0
            diff_str = self._fmt_percent(diff, signed=True)
            
            # Emoji indicator
            if i == 1:
                emoji = "🥇"
            elif i == 2:
                emoji = "🥈"
            elif i == 3:
                emoji = "🥉"
            else:
                emoji = "📌"
            
            # Check if this is actually AI prediction or just market price
            summary = outcome.get("summary", "")
            
            # Debug: print summary for first outcome
            if i == 1:
                print(f"🔍 第一个选项的 summary: {summary[:200]}")
                # 【防御】确保 pred 和 market 不为 None
                pred = pred or 0.0
                market = market or 0.0
                if pred is None:
                    print("⚙️ [SAFE] 修复空值保护: pred")
                    pred = 0.0
                if market is None:
                    print("⚙️ [SAFE] 修复空值保护: market")
                    market = 0.0
                diff_debug = (pred or 0.0) - (market or 0.0)
                print(f"🔍 prediction: {(pred or 0.0):.2f}%, market: {(market or 0.0):.2f}%, diff: {abs(diff_debug):.2f}%")
            
            # Determine if this is a real AI prediction
            # Threshold: if prediction and market differ by at least 0.5%, consider it AI prediction
            # (More lenient than before to catch edge cases where AI prediction is close to market)
            pred_diff = abs(pred - market)
            pred_exactly_matches = pred_diff < 0.1  # Exactly same (within 0.1%)
            
            # Check for fallback messages in summary
            has_fallback_message = any(word in summary for word in [
                "暂无", "暂不可用", "没有可用的模型", "使用市场概率", 
                "显示市场价格", "没有可用的模型响应", "使用市场", "⚠️"
            ])
            
            # Has meaningful summary (not just fallback message)
            has_meaningful_summary = len(summary) > 30 and not has_fallback_message
            
            # It's a real AI prediction if:
            # 1. Has valid AI prediction (model_only_prob exists or can be derived)
            # 2. AND no fallback messages in summary
            # 3. AND summary has meaningful content
            # OR: if uncertainty is reasonable (> 0) and summary exists (even if diff is small)
            has_valid_ai = ai_pred is not None and ai_pred > 0
            is_ai_prediction = (
                has_valid_ai and              # Has valid AI prediction
                not pred_exactly_matches and  # Must differ from market (if using pred)
                has_meaningful_summary        # Has real content, not fallback
            ) or (
                has_valid_ai and
                uncertainty > 0.1 and         # Has uncertainty value
                has_meaningful_summary         # Has real content
            )
            
            diff_str_escaped = diff_str.replace('(', '\\(').replace(')', '\\)')
            
            # Format the option line carefully
            # The format "*{i}. {name}*" can break if name contains * or other special chars
            # Solution: Don't put name inside bold tags, just the number
            # Or: Use a safer format that avoids Markdown parsing issues
            if is_ai_prediction:
                # 显示归一化后的AI预测（model_only_prob）
                ai_display = ai_pred if ai_pred is not None else pred
                # 【防御】确保所有值不为 None
                ai_display = ai_display or 0.0
                uncertainty = uncertainty or 0.0
                market = market or 0.0
                if ai_display is None:
                    print(f"⚠️ ai_display is None for {name}, using default 0.0")
                    ai_display = 0.0
                if uncertainty is None:
                    print(f"⚠️ uncertainty is None for {name}, using default 0.0")
                    uncertainty = 0.0
                if market is None:
                    print(f"⚠️ market is None for {name}, using default 0.0")
                    market = 0.0
                ai_display_str = self._fmt_percent(ai_display)
                uncertainty_str = self._fmt_percent(uncertainty)
                market_str = self._fmt_percent(market)
                
                output += f"""{emoji} *{i}.* {name}
   🤖 AI预测: {ai_display_str} ± {uncertainty_str}
   📈 市场价格: {market_str} ({diff_str_escaped})
   
"""
            else:
                # Just market price, no AI prediction available
                # 【防御】确保 market 不为 None
                market = market or 0.0
                if market is None:
                    print(f"⚠️ market is None for {name}, using default 0.0")
                    market = 0.0
                output += f"""{emoji} *{i}.* {name}
   📈 市场价格: {self._fmt_percent(market)}
   ⚠️ AI预测暂不可用
   
"""
        
        # Show remaining outcomes if any
        if len(sorted_outcomes) > 5:
            remaining = sorted_outcomes[5:]
            output += f"\n_其他选项 \\({len(remaining)} 个\\):_\n"
            for outcome in remaining:
                name_escaped = self.safe_markdown_text(outcome['name'])
                # 【防御】确保 prediction 和 market_prob 不为 None
                prediction = outcome.get('prediction') or 0.0
                market_prob = outcome.get('market_prob') or 0.0
                if prediction is None:
                    print(f"⚠️ prediction is None for {name_escaped}, using default 0.0")
                    prediction = 0.0
                if market_prob is None:
                    print(f"⚠️ market_prob is None for {name_escaped}, using default 0.0")
                    market_prob = 0.0
                output += f"  • {name_escaped}: {self._fmt_percent(prediction)} \\(市场: {self._fmt_percent(market_prob)}\\)\n"
        
        # Add rules if available
        rules = event_data.get("rules", "")
        if rules and not event_data.get("is_mock", False):
            short_rules = rules[:150] + "..." if len(rules) > 150 else rules
            rules_escaped = self.safe_markdown_text(short_rules)
            output += f"\n📜 *规则:* {rules_escaped}\n"

        # DeepSeek insight block (multi-option)
        finalized_summary_text = finalized_summary_text or ""  # 保证始终有可用于比较的基准摘要
        deepseek_section = ""
        deepseek_reasoning = None
        if fusion_result and fusion_result.get('deepseek_reasoning'):
            deepseek_reasoning = fusion_result.get('deepseek_reasoning')
        elif outcomes:
            for outcome in outcomes:
                if outcome.get('deepseek_reasoning'):
                    deepseek_reasoning = outcome['deepseek_reasoning']
                    break
        if deepseek_reasoning:
            finalized_deepseek = self._finalize_reasoning_text(deepseek_reasoning, limit=500)
            if finalized_deepseek and finalized_summary_text:
                try:
                    similarity = self._reasoning_similarity(finalized_summary_text, finalized_deepseek)
                    if similarity >= 0.9:
                        print("[FORMAT] Skipped redundant model insight (multi-option)")
                        finalized_deepseek = ""
                except Exception as exc:
                    logger.exception("Multi-option DeepSeek 摘要去重时发生异常: %s", exc)
            if finalized_deepseek:
                deepseek_text = self.safe_markdown_text(finalized_deepseek)
                deepseek_section = (
                    "\n🧠 *模型洞察 \\(DeepSeek\\)*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"{deepseek_text}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                )

        # Model versions section (for multi-option events)
        # Collect model versions and weight source from all outcomes (they should all have the same versions)
        model_versions = None
        weight_source = None
        if outcomes and len(outcomes) > 0:
            # Try to get from first outcome (if stored during fusion)
            for outcome in outcomes:
                if 'model_versions' in outcome and outcome['model_versions']:
                    model_versions = outcome['model_versions']
                if 'weight_source' in outcome and outcome['weight_source']:
                    weight_source = outcome['weight_source']
                if model_versions and weight_source:
                    break
        
        versions_section = ""
        if model_versions:
            versions_lines = []
            for model_id, version_info in model_versions.items():
                display_name = version_info.get("display_name", model_id)
                last_updated = version_info.get("last_updated", "未知")
                versions_lines.append(f"• {display_name} \\(更新: {last_updated}\\)")
            
            if versions_lines:
                versions_text = "\n".join(versions_lines)
                versions_section = f"\n🧩 *模型版本摘要*\n{versions_text}\n"
        
        # Weight source section (for multi-option events)
        weight_source_section = ""
        if weight_source:
            source = weight_source.get("source", "未知")
            updated_at = weight_source.get("updated_at", "未知")
            file_name = weight_source.get("file", "未知")
            weight_source_section = f"\n📊 *模型权重来源:* {file_name} \\| 更新时间: {updated_at}\n"
        
        if normalization_info and normalization_info.get("normalized"):
            total_after = normalization_info.get("total_after", 0)
            error = normalization_info.get("error", 0)
            if not total_after:
                ai_sum = sum(
                    outcome.get('model_only_prob') or 0
                    for outcome in sorted_outcomes
                    if outcome.get('model_only_prob') is not None
                )
                if ai_sum > 0:
                    total_after = ai_sum
            if total_after:
                try:
                    total_after_val = float(total_after)
                    error_val = float(error) if error is not None else 0.0
                    if error_val <= 0.01:
                        output += f"\n✅ *概率归一化完成* \\(总和={total_after_val:.2f}%，误差≤{error_val:.4f}%\\)"
                    else:
                        output += f"\n⚠️ *归一化警告* \\(总和={total_after_val:.2f}%，误差={error_val:.4f}%\\)"
                except (TypeError, ValueError):
                    print("⚠️ total_after 或 error 数据格式错误，跳过格式化")
        elif not normalization_info:
            # 如果没有归一化信息，手动计算总和
            ai_total = sum(
                outcome.get('model_only_prob') or outcome.get('prediction', 0) or 0
                for outcome in sorted_outcomes
                if outcome.get('model_only_prob') is not None or outcome.get('prediction') is not None
            )
            output += f"\n📊 *AI预测总和：* {ai_total:.2f}%"
        
        # Add DeepSeek section, versions and weight source sections before normalization info
        combined_sections = ""
        if deepseek_section:
            combined_sections += deepseek_section
        if versions_section:
            combined_sections += versions_section
        if weight_source_section:
            combined_sections += weight_source_section
        
        if combined_sections:
            output = output.rstrip('\n') + combined_sections
        trade_section = self._render_trade_signal_section(trade_signal, fusion_result, event_data)
        if trade_section:
            output += "\n" + trade_section
        
        return output
    
    def format_error(self, error_message: str) -> str:
        """Format error message in Chinese."""
        error_escaped = self.safe_markdown_text(error_message)
        return f"❌ *错误:* {error_escaped}"
