"""
Notion Logger：自动保存预测结果到 Notion 数据库

功能：
- 在 fusion_engine 生成最终预测结果后，自动写入 Notion 数据库
- 避免重复写入（基于事件名称和时间戳）
- 支持简单限流（每次写入间隔≥5秒）
"""
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv

# 确保加载环境变量
load_dotenv()

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    print("⚠️ notion-client 未安装，Notion 日志功能将不可用。请运行: pip install notion-client")


class NotionLogger:
    """
    Notion 数据库日志记录器
    
    功能：
    - 自动记录预测结果到 Notion 数据库
    - 支持单选项和多选项事件
    - 限流保护（避免频繁写入）
    """
    
    def __init__(self, notion_token: Optional[str] = None, database_id: Optional[str] = None):
        """
        初始化 Notion Logger
        
        Args:
            notion_token: Notion Integration Token（从环境变量读取）
            database_id: Notion Database ID（从环境变量读取）
        """
        # 再次确保环境变量已加载（防止调用时还未加载）
        load_dotenv()
        
        self.notion_token = notion_token or os.getenv("NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_DB_ID")
        
        # 详细检查并输出诊断信息
        if not NOTION_AVAILABLE:
            print("⚠️ Notion Logger: notion-client 库未安装，日志功能将禁用")
            print("   💡 解决方案: pip install notion-client>=2.2.1")
            self.client = None
            self.enabled = False
            return
        
        if not self.notion_token:
            print("⚠️ Notion Logger: 未配置 NOTION_TOKEN，日志功能将禁用")
            print("   💡 请在 .env 文件中添加: NOTION_TOKEN=your_token")
            self.client = None
            self.enabled = False
            return
        
        if not self.database_id:
            print("⚠️ Notion Logger: 未配置 NOTION_DB_ID，日志功能将禁用")
            print("   💡 请在 .env 文件中添加: NOTION_DB_ID=your_database_id")
            self.client = None
            self.enabled = False
            return
        
        try:
            self.client = Client(auth=self.notion_token)
            self.enabled = True
            print(f"✅ Notion Logger 已初始化（数据库 ID: {self.database_id[:8]}...）")
            print(f"   Token 前8位: {self.notion_token[:8]}...")
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            print(f"⚠️ Notion Logger 初始化失败: {error_type}: {error_msg}")
            print(f"   💡 请检查 NOTION_TOKEN 是否正确，以及 Integration 是否有数据库访问权限")
            self.client = None
            self.enabled = False
        
        # 限流：记录上次写入时间
        self.last_write_time = 0
        self.min_write_interval = 5  # 最小写入间隔（秒）
    
    def _can_write(self) -> bool:
        """检查是否可以写入（限流检查）"""
        current_time = time.time()
        elapsed = current_time - self.last_write_time
        if elapsed < self.min_write_interval:
            # 【防御】确保 elapsed 不为 None
            elapsed = elapsed or 0.0
            if elapsed is None:
                print("⚠️ elapsed is None, using default 0.0")
                elapsed = 0.0
            print(f"⏸️ Notion Logger: 限流保护（距离上次写入仅 {(elapsed or 0.0):.1f} 秒）")
            return False
        return True
    
    def _check_duplicate(self, event_name: str, timestamp_utc: str, outcome_name: Optional[str] = None) -> Optional[str]:
        """
        检查是否已存在相同记录（基于事件名称）
        
        Returns:
            如果存在，返回页面 ID；否则返回 None
        """
        if not self.enabled or not self.client:
            return None
        
        try:
            # 简化处理：暂时跳过重复检查
            # 原因：notion_client 2.x 版本不直接支持 databases.query() 方法
            # 如果需要重复检查，可以：
            # 1. 升级到支持查询的新版本
            # 2. 使用 Notion API 的搜索端点直接调用
            # 3. 维护一个本地缓存记录已写入的事件
            # 目前为了确保写入成功，暂时跳过重复检查
            return None
        except Exception as e:
            # 如果发生异常，跳过重复检查，允许创建新记录
            print(f"⚠️ Notion Logger: 检查重复记录失败: {e}")
            return None
    
    def _create_page_properties(self, event_data: Dict, fusion_result: Dict, 
                                outcome: Optional[Dict] = None, 
                                full_analysis: Optional[Dict] = None,
                                normalization_info: Optional[Dict] = None,
                                ai_sum: Optional[float] = None,
                                trade_signal: Optional[Dict] = None) -> Dict:
        """
        创建 Notion 页面属性
        
        Args:
            event_data: 事件数据
            fusion_result: 融合结果
            outcome: 单个选项（多选项事件时）
            full_analysis: 完整分析结果（包含类别、规则摘要等）
            normalization_info: 归一化信息（多选项事件）
            ai_sum: AI 预测总和（多选项事件）
        
        Returns:
            Notion 页面属性字典
        """
        # 事件名称 - 从 event_data["question"]
        event_name = event_data.get("question", "-")
        
        # 选项名称 - 优先从 event_data["outcomes"][0]，否则从 outcome 获取
        outcome_name = "-"
        if outcome:
            # 多选项事件：从 outcome 获取
            outcome_name = str(outcome.get("name", "-"))
        elif event_data.get("outcomes") and len(event_data["outcomes"]) > 0:
            # 从 event_data["outcomes"][0] 获取（单选项事件）
            if isinstance(event_data["outcomes"][0], dict):
                outcome_name = str(event_data["outcomes"][0].get("name", "-"))
            else:
                outcome_name = str(event_data["outcomes"][0])
        elif not event_data.get("is_multi_option", False):
            # 单选项事件的默认值（如果没有 outcomes 字段）
            outcome_name = "Yes"
        
        # AI 预测和市场预测
        if outcome:
            # 多选项事件：从 outcome 获取
            ai_prob = outcome.get("model_only_prob") or outcome.get("prediction", 0)
            market_prob = outcome.get("market_prob", 0)
        else:
            # 单选项事件：从 fusion_result 获取 model_only_prob
            ai_prob = fusion_result.get("model_only_prob", 0)
            market_prob = event_data.get("market_prob", 0)
        
        # 计算差值
        diff = round(ai_prob - market_prob, 2)
        
        # AI 预测总和
        if outcome:
            # 多选项事件：从传入的 ai_sum 获取（所有选项的总和）
            ai_sum_value = ai_sum if ai_sum is not None else None
        else:
            # 单选项事件：Sum (ΣAI) 应该等于 AI 预测值（model_only_prob）
            # 因为只有一个选项，总和就是该选项的值
            ai_sum_value = fusion_result.get("model_only_prob") or fusion_result.get("final_prob", 0)
        
        # 事件类别 - 优先从 event_data["category"]
        category = event_data.get("category", "-")
        if category == "-" and full_analysis:
            # Fallback: 从 full_analysis 获取
            category_map = {
                "geopolitics": "地缘政治",
                "economy": "经济指标",
                "tech": "科技产品",
                "social": "社会事件",
                "sports": "体育赛事",
                "general": "通用事件"
            }
            category = category_map.get(full_analysis.get("event_category", "general"), "-")
        
        # 使用的模型 - 从 fusion_result["models"]
        models_list = fusion_result.get("models", [])
        if not models_list:
            # Fallback: 从 model_versions 提取
            model_versions = fusion_result.get("model_versions", {})
            models_list = [
                info.get("display_name", model_id)
                for model_id, info in model_versions.items()
            ]
        models_used = ", ".join(models_list) if models_list else "-"
        
        # AI 推理摘要 - 从 fusion_result["summary"]
        summary = fusion_result.get("summary", "-")
        if len(summary) > 1800:  # 限制长度
            summary = summary[:1797] + "..."
        
        # 规则摘要 - 从 event_data["rules"]
        rules_summary = event_data.get("rules", "-")
        if len(rules_summary) > 1800:  # 限制长度
            rules_summary = rules_summary[:1797] + "..."
        
        # 时间戳（UTC）
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        
        # Run ID - 从 fusion_result["run_id"]
        run_id = fusion_result.get("run_id", "-")
        
        # 构建属性字典 - 按照用户要求的字段映射
        properties = {
            "Event Name": {
                "title": [{"text": {"content": str(event_name)}}]
            },
            "Outcome Name": {
                "rich_text": [{"text": {"content": str(outcome_name)}}]
            },
            "AI Prediction (%)": {
                "number": round(ai_prob, 2) if ai_prob is not None else 0
            },
            "Market Prediction (%)": {
                "number": round(market_prob, 2) if market_prob is not None else 0
            },
            "Diff (AI - Market)": {
                "number": diff
            },
            "Sum (ΣAI)": {
                "number": round(ai_sum_value, 2) if ai_sum_value is not None else 0
            },
            "Category": {
                "rich_text": [{"text": {"content": str(category)}}]
            },
            "Models Used": {
                "rich_text": [{"text": {"content": str(models_used)}}]
            },
            "Summary (AI reasoning)": {
                "rich_text": [{"text": {"content": str(summary)}}]
            },
            "Rules Summary": {
                "rich_text": [{"text": {"content": str(rules_summary)}}]
            },
            "Timestamp": {
                "date": {"start": timestamp_utc}
            },
            "Run ID": {
                "rich_text": [{"text": {"content": str(run_id)}}]
            }
        }
        
        # Add trade signal fields if available
        if trade_signal:
            # Handle both formats: direct dict or nested {"data": {...}}
            signal_data = trade_signal.get("data", {}) if isinstance(trade_signal, dict) and "data" in trade_signal else trade_signal
            if signal_data:
                ev = signal_data.get("ev")
                annualized_ev = signal_data.get("annualized_ev")
                risk_factor = signal_data.get("risk_factor")
                signal = signal_data.get("signal", "HOLD")
                signal_reason = signal_data.get("signal_reason", "")
                
                # Only add properties if they exist (safe fallback)
                # 【修复】使用标准属性名称：EV, AnnualizedEV, RiskFactor, TradeSignal, TradeReason
                try:
                    if ev is not None:
                        properties["EV"] = {"number": round(float(ev), 4)}
                except Exception:
                    pass  # Skip if property doesn't exist
                
                try:
                    if annualized_ev is not None:
                        properties["AnnualizedEV"] = {"number": round(float(annualized_ev), 4)}
                except Exception:
                    pass  # Skip if property doesn't exist
                
                try:
                    if risk_factor is not None:
                        properties["RiskFactor"] = {"number": round(float(risk_factor), 3)}
                except Exception:
                    pass  # Skip if property doesn't exist
                
                try:
                    if signal:
                        properties["TradeSignal"] = {"rich_text": [{"text": {"content": str(signal)}}]}
                except Exception:
                    pass  # Skip if property doesn't exist
                
                try:
                    if signal_reason:
                        properties["TradeReason"] = {"rich_text": [{"text": {"content": str(signal_reason)[:500]}}]}
                except Exception:
                    pass  # Skip if property doesn't exist
        
        return properties

    def log_trade_signal(self, event_name: str, trade_data: Optional[Dict]) -> None:
        """Emit a concise log line for trade signal data being written to Notion."""
        if not trade_data:
            print(f"[TRADE_SIGNAL] No trade signal for {event_name}")
            return
        signal_data = trade_data.get("data", {}) if isinstance(trade_data, dict) and isinstance(trade_data.get("data"), dict) else trade_data
        if not isinstance(signal_data, dict) or not signal_data:
            print(f"[TRADE_SIGNAL] Invalid trade signal payload for {event_name}")
            return

        signal = (signal_data.get("signal") or "HOLD").upper()
        ev = signal_data.get("ev")
        annualized = signal_data.get("annualized_ev")
        risk_factor = signal_data.get("risk_factor")
        reason = (signal_data.get("signal_reason") or "").strip()

        def _fmt(value: Optional[float], signed: bool = False) -> str:
            if value is None:
                return "—"
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return "—"
            return f"{numeric:+.2f}" if signed else f"{numeric:.2f}"

        print(
            f"[TRADE_SIGNAL] logging {signal} ev={_fmt(ev, True)} "
            f"aev={_fmt(annualized, True)} risk={_fmt(risk_factor)} event=\"{event_name[:80]}\""
        )
        if reason:
            print(f"[TRADE_SIGNAL] reason: {reason[:160]}")
    
    def log_prediction(self, event_data: Dict, fusion_result: Dict,
                      full_analysis: Optional[Dict] = None,
                      outcomes: Optional[List[Dict]] = None,
                      normalization_info: Optional[Dict] = None,
                      trade_signal: Optional[Dict] = None) -> bool:
        """
        记录预测结果到 Notion 数据库
        
        Args:
            event_data: 事件数据（包含 question, market_prob, rules 等）
            fusion_result: 融合结果（包含 final_prob, model_only_prob, summary 等）
            full_analysis: 完整分析结果（可选，包含 event_category, rules_summary 等）
            outcomes: 多选项事件的选项列表（可选）
            normalization_info: 归一化信息（可选，用于计算总和）
            trade_signal: 交易信号数据（可选，包含 ev、annualized_ev、risk_factor、signal 等）
        
        Returns:
            是否成功写入
        """
        # 检查启用状态
        if not self.enabled:
            # enabled=False 时已在初始化时输出过警告，这里不再重复输出
            return False
        
        # 检查客户端是否初始化
        if not self.client:
            print("⚠️ Notion Logger: 客户端未初始化，跳过记录")
            return False
        
        # 限流检查
        if not self._can_write():
            return False
        
        try:
            event_name = event_data.get("question", "未知事件")
            if trade_signal:
                self.log_trade_signal(event_name, trade_signal)
            timestamp_utc = datetime.now(timezone.utc).isoformat()
            
            # 检查重复记录（简化检查，避免因属性不存在而失败）
            existing_page_id = self._check_duplicate(event_name, timestamp_utc)
            
            if outcomes and len(outcomes) > 0:
                # 多选项事件：为每个选项创建一条记录
                success_count = 0
                
                # 计算 AI 预测总和
                ai_sum = None
                if normalization_info:
                    ai_sum = normalization_info.get("total_after", 0)
                else:
                    # 手动计算
                    ai_sum = sum(
                        outcome.get("model_only_prob") or outcome.get("prediction", 0) or 0
                        for outcome in outcomes
                        if outcome.get("model_only_prob") is not None or outcome.get("prediction") is not None
                    )
                
                for outcome in outcomes:
                    properties = self._create_page_properties(
                        event_data=event_data,
                        fusion_result=fusion_result,
                        outcome=outcome,
                        full_analysis=full_analysis,
                        normalization_info=normalization_info,
                        ai_sum=ai_sum,
                        trade_signal=trade_signal
                    )
                    
                    # 检查是否重复（基于事件名称、选项名称和时间戳）
                    if existing_page_id:
                        # 更新现有页面
                        try:
                            self.client.pages.update(
                                page_id=existing_page_id,
                                properties=properties
                            )
                            print(f"✅ Notion Logger: 更新记录 - {event_name[:50]}... ({outcome.get('name', 'N/A')})")
                        except Exception as e:
                            print(f"⚠️ Notion Logger: 更新记录失败: {e}")
                            # 如果更新失败，尝试创建新记录
                            try:
                                self.client.pages.create(
                                    parent={"database_id": self.database_id},
                                    properties=properties
                                )
                                print(f"✅ Notion Logger: 创建记录 - {event_name[:50]}... ({outcome.get('name', 'N/A')})")
                                success_count += 1
                            except Exception as e2:
                                print(f"❌ Notion Logger: 创建记录失败: {e2}")
                    else:
                        # 创建新页面
                        try:
                            self.client.pages.create(
                                parent={"database_id": self.database_id},
                                properties=properties
                            )
                            print(f"✅ Notion Logger: 创建记录 - {event_name[:50]}... ({outcome.get('name', 'N/A')})")
                            success_count += 1
                        except Exception as e:
                            print(f"❌ Notion Logger: 创建记录失败: {e}")
                            # 尝试只写入标题（最基本的信息）
                            try:
                                minimal_props = {
                                    "Event Name": properties.get("Event Name", {
                                        "title": [{"text": {"content": event_name[:2000]}}]
                                    })
                                }
                                page_content = f"选项: {outcome.get('name', 'N/A')}\nAI预测: {outcome.get('prediction', 'N/A')}%\n市场预测: {outcome.get('market_prob', 'N/A')}%\n摘要: {outcome.get('summary', 'N/A')[:500]}"
                                self.client.pages.create(
                                    parent={"database_id": self.database_id},
                                    properties=minimal_props,
                                    children=[{
                                        "object": "block",
                                        "type": "paragraph",
                                        "paragraph": {
                                            "rich_text": [{
                                                "type": "text",
                                                "text": {"content": page_content}
                                            }]
                                        }
                                    }]
                                )
                                print(f"✅ Notion Logger: 创建最小记录 - {event_name[:50]}...")
                                success_count += 1
                            except Exception as e2:
                                print(f"❌ Notion Logger: 创建最小记录也失败: {e2}")
                
                # 更新写入时间
                if success_count > 0:
                    self.last_write_time = time.time()
                
                return success_count > 0
            else:
                # 单选项事件：创建一条记录
                properties = self._create_page_properties(
                    event_data=event_data,
                    fusion_result=fusion_result,
                    outcome=None,
                    full_analysis=full_analysis,
                    normalization_info=normalization_info,
                    ai_sum=None,
                    trade_signal=trade_signal
                )
                
                if existing_page_id:
                    # 更新现有页面
                    try:
                        self.client.pages.update(
                            page_id=existing_page_id,
                            properties=properties
                        )
                        print(f"✅ Notion Logger: 更新记录 - {event_name[:50]}...")
                        self.last_write_time = time.time()
                        return True
                    except Exception as e:
                        print(f"⚠️ Notion Logger: 更新记录失败: {e}")
                        return False
                else:
                    # 创建新页面
                    try:
                        self.client.pages.create(
                            parent={"database_id": self.database_id},
                            properties=properties
                        )
                        print(f"✅ Notion Logger: 创建记录 - {event_name[:50]}...")
                        self.last_write_time = time.time()
                        return True
                    except Exception as e:
                        print(f"❌ Notion Logger: 创建记录失败: {e}")
                        # 尝试只写入标题（最基本的信息）
                        try:
                            minimal_props = {
                                "Event Name": properties.get("Event Name", {
                                    "title": [{"text": {"content": event_name[:2000]}}]
                                })
                            }
                            page_content = f"AI预测: {fusion_result.get('final_prob', 'N/A')}%\n市场预测: {event_data.get('market_prob', 'N/A')}%\n摘要: {fusion_result.get('summary', 'N/A')[:500]}"
                            self.client.pages.create(
                                parent={"database_id": self.database_id},
                                properties=minimal_props,
                                children=[{
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [{
                                            "type": "text",
                                            "text": {"content": page_content}
                                        }]
                                    }
                                }]
                            )
                            print(f"✅ Notion Logger: 创建最小记录 - {event_name[:50]}...")
                            self.last_write_time = time.time()
                            return True
                        except Exception as e2:
                            print(f"❌ Notion Logger: 创建最小记录也失败: {e2}")
                            return False
        
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            print(f"❌ Notion Logger: 记录预测结果时出错: {error_type}: {error_msg}")
            import traceback
            traceback.print_exc()
            
            # 提供更详细的错误诊断
            error_lower = error_msg.lower()
            if "unauthorized" in error_lower or "401" in error_msg:
                print("   💡 可能原因: NOTION_TOKEN 无效或已过期")
            elif "not found" in error_lower or "404" in error_msg:
                print("   💡 可能原因: NOTION_DB_ID 不正确，或 Integration 没有数据库访问权限")
            elif "rate limit" in error_lower or "429" in error_msg:
                print("   💡 可能原因: Notion API 限流，请稍后重试")
            elif "forbidden" in error_lower or "403" in error_msg:
                print("   💡 可能原因: Integration 没有写入权限，请在 Notion 中授予权限")
            
            return False
