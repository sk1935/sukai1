"""
LMArena 动态权重更新模块

功能：
- 从 LMArena.ai API 获取模型排行榜
- 提取特定模型的 avg_score 并标准化
- 更新 base_weights_lmarena.json 文件
- 支持错误处理和回退机制
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import httpx

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
WEIGHTS_FILE = CONFIG_DIR / "base_weights_lmarena.json"

# LMArena API 端点
LMARENA_API_URL = "https://lmarena.ai/api/leaderboard"

# 模型名称映射（LMArena API 返回的名称 → 我们的内部名称）
MODEL_NAME_MAPPING = {
    "GPT-4o": ["gpt-4o", "gpt-4o-latest"],
    "Claude-3.7-Sonnet": ["claude-3-7-sonnet-latest", "claude-3.7-sonnet", "claude-opus-4-1"],
    "Gemini-2.5-Pro": ["gemini-2.5-pro", "gemini-2.5-pro-latest"],
    "DeepSeek Chat": ["deepseek-chat", "deepseek-v3.2-exp"]
}

# 标准化区间
MIN_SCORE = 0.95
MAX_SCORE = 1.00


def normalize_score(score: float, min_original: float, max_original: float) -> float:
    """
    将分数标准化到 [MIN_SCORE, MAX_SCORE] 区间
    
    Args:
        score: 原始分数
        min_original: 原始分数的最小值
        max_original: 原始分数的最大值
    
    Returns:
        标准化后的分数
    """
    if max_original == min_original:
        return MAX_SCORE  # 如果所有分数相同，返回最大值
    
    # 线性映射到 [MIN_SCORE, MAX_SCORE]
    normalized = MIN_SCORE + (score - min_original) / (max_original - min_original) * (MAX_SCORE - MIN_SCORE)
    return round(normalized, 4)


def extract_model_scores(leaderboard_data: list) -> Dict[str, float]:
    """
    从 LMArena 排行榜数据中提取目标模型的 avg_score
    
    Args:
        leaderboard_data: LMArena API 返回的排行榜数据（list of dict）
    
    Returns:
        Dict mapping model_name -> avg_score
    """
    model_scores = {}
    
    if not isinstance(leaderboard_data, list):
        print(f"⚠️ [LMArena] 排行榜数据格式错误：期望 list，得到 {type(leaderboard_data)}")
        return {}
    
    # 遍历排行榜，查找目标模型
    for entry in leaderboard_data:
        if not isinstance(entry, dict):
            continue
        
        model_name = entry.get("model") or entry.get("name") or entry.get("model_name", "")
        avg_score = entry.get("avg_score") or entry.get("score") or entry.get("average_score")
        
        if not model_name or avg_score is None:
            continue
        
        # 检查是否匹配我们的目标模型
        for our_name, api_names in MODEL_NAME_MAPPING.items():
            for api_name in api_names:
                if api_name.lower() in model_name.lower() or model_name.lower() in api_name.lower():
                    # 找到匹配的模型
                    try:
                        score = float(avg_score)
                        if our_name not in model_scores:
                            model_scores[our_name] = score
                        else:
                            # 如果已存在，取更高的分数
                            model_scores[our_name] = max(model_scores[our_name], score)
                    except (ValueError, TypeError):
                        continue
                    break
    
    return model_scores


def fetch_lmarena_leaderboard() -> Optional[list]:
    """
    从 LMArena API 获取排行榜数据
    
    Returns:
        排行榜数据（list），或 None 如果失败
    """
    try:
        print(f"[LMArena] 正在从 {LMARENA_API_URL} 获取排行榜...")
        
        with httpx.Client(timeout=10.0) as client:
            response = client.get(LMARENA_API_URL)
            
            if response.status_code == 200:
                data = response.json()
                
                # 处理不同的响应格式
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    # 尝试从 dict 中提取 list
                    if "data" in data:
                        return data["data"]
                    elif "leaderboard" in data:
                        return data["leaderboard"]
                    elif "results" in data:
                        return data["results"]
                    else:
                        # 如果是 dict，尝试直接使用
                        print(f"⚠️ [LMArena] 响应格式为 dict，尝试解析...")
                        return [data]
                else:
                    print(f"⚠️ [LMArena] 未知的响应格式: {type(data)}")
                    return None
            else:
                print(f"❌ [LMArena] API 返回错误状态码: {response.status_code}")
                return None
                
    except httpx.TimeoutException:
        print(f"⏱️ [LMArena] 请求超时（>10s）")
        return None
    except httpx.RequestError as e:
        print(f"🌐 [LMArena] 网络错误: {type(e).__name__}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ [LMArena] JSON 解析失败: {e}")
        return None
    except Exception as e:
        print(f"❌ [LMArena] 未知错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


def load_existing_weights() -> Dict:
    """
    加载现有的权重文件
    
    Returns:
        权重数据字典，或空字典如果文件不存在
    """
    if not WEIGHTS_FILE.exists():
        print(f"⚠️ [LMArena] 权重文件不存在: {WEIGHTS_FILE}")
        return {}
    
    try:
        with open(WEIGHTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except json.JSONDecodeError as e:
        print(f"⚠️ [LMArena] 权重文件解析失败: {e}")
        return {}
    except Exception as e:
        print(f"⚠️ [LMArena] 读取权重文件失败: {e}")
        return {}


def update_weights_file(model_scores: Dict[str, float]) -> bool:
    """
    更新权重文件
    
    注意：保持与现有 FusionEngine 兼容的格式
    现有格式有 weights 嵌套结构，我们需要保持兼容
    
    Args:
        model_scores: Dict mapping model_name -> normalized_score
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # 读取现有文件（如果存在），保持兼容格式
        existing_data = load_existing_weights()
        
        # 创建输出数据（保持与 FusionEngine 兼容的格式）
        output_data = {
            "metadata": {
                "source": "LMArena.ai API (auto-updated)",
                "description": "基础权重基于 LMArena 最新模型综合得分，自动更新。",
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d")
            },
            "weights": {},
            "fusion": existing_data.get("fusion", {
                "normalization": True,
                "auto_update": True,
                "default_confidence_multiplier": {
                    "low": 1.0,
                    "medium": 2.0,
                    "high": 3.0
                },
                "notes": "最终融合时，实际权重 = base_weight × 置信度倍数；再进行归一化。"
            }),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
        # 将标准化后的分数映射到 weights 结构
        # 使用模型名称映射到 FusionEngine 期望的键
        model_key_mapping = {
            "GPT-4o": "gpt-4o-latest",
            "Claude-3.7-Sonnet": "claude-opus-4-1",
            "Gemini-2.5-Pro": "gemini-2.5-pro",
            "DeepSeek Chat": "deepseek-v3.2-exp"
        }
        
        for model_name, score in model_scores.items():
            config_key = model_key_mapping.get(model_name, model_name.lower().replace(" ", "-"))
            output_data["weights"][config_key] = {
                "base_weight": score,
                "score": None,  # LMArena 原始分数不在此存储（可选）
                "notes": f"自动更新自 LMArena.ai ({model_name})"
            }
        
        # 保留现有文件中其他模型的权重（如果新数据中没有）
        if existing_data.get("weights"):
            for key, value in existing_data["weights"].items():
                if key not in output_data["weights"]:
                    output_data["weights"][key] = value
        
        # 写入文件（原子操作：先写临时文件，再重命名）
        temp_file = WEIGHTS_FILE.with_suffix('.json.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        # 原子性替换
        temp_file.replace(WEIGHTS_FILE)
        
        print(f"✅ [LMArena] 权重文件已更新: {WEIGHTS_FILE}")
        return True
        
    except Exception as e:
        print(f"❌ [LMArena] 写入权重文件失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def should_update() -> bool:
    """
    检查是否需要更新权重文件
    
    Returns:
        True if file is older than 24 hours or doesn't exist, False otherwise
    """
    if not WEIGHTS_FILE.exists():
        return True
    
    try:
        # 读取现有文件的时间戳字段（兼容两种格式）
        data = load_existing_weights()
        
        # 优先检查 last_updated 字段（新格式）
        last_updated_str = data.get("last_updated")
        
        # 如果没有，检查 metadata.updated_at（旧格式）
        if not last_updated_str:
            metadata = data.get("metadata", {})
            if isinstance(metadata, dict):
                updated_at_str = metadata.get("updated_at")
                if updated_at_str:
                    # 旧格式可能只有日期，需要转换为 datetime
                    try:
                        # 尝试解析为日期字符串
                        if len(updated_at_str) == 10:  # YYYY-MM-DD 格式
                            last_updated = datetime.strptime(updated_at_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        else:
                            last_updated = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                        now = datetime.now(timezone.utc)
                        time_diff = now - last_updated.replace(tzinfo=timezone.utc) if last_updated.tzinfo else (now - last_updated)
                        hours_diff = time_diff.total_seconds() / 3600
                        
                        if hours_diff >= 24:
                            print(f"[LMArena] 权重文件已过期（{hours_diff:.1f} 小时前更新），需要刷新")
                            return True
                        else:
                            print(f"[LMArena] 权重文件仍然有效（{hours_diff:.1f} 小时前更新）")
                            return False
                    except:
                        pass
        
        if not last_updated_str:
            return True  # 没有时间戳，需要更新
        
        # 解析时间戳
        last_updated = datetime.fromisoformat(last_updated_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        
        # 检查是否超过 24 小时
        time_diff = now - last_updated.replace(tzinfo=timezone.utc) if last_updated.tzinfo else (now - last_updated)
        hours_diff = time_diff.total_seconds() / 3600
        
        if hours_diff >= 24:
            print(f"[LMArena] 权重文件已过期（{hours_diff:.1f} 小时前更新），需要刷新")
            return True
        else:
            print(f"[LMArena] 权重文件仍然有效（{hours_diff:.1f} 小时前更新）")
            return False
            
    except Exception as e:
        print(f"⚠️ [LMArena] 检查更新状态失败: {e}，强制更新")
        return True


def update_lmarena_weights() -> bool:
    """
    更新 LMArena 权重的主函数
    
    Returns:
        True if update successful, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"[LMArena] 开始更新模型权重...")
    print(f"{'='*60}")
    
    # 获取排行榜数据
    leaderboard_data = fetch_lmarena_leaderboard()
    
    if not leaderboard_data:
        print(f"⚠️ [LMArena] 拉取失败，使用旧权重")
        return False
    
    # 提取模型分数
    model_scores = extract_model_scores(leaderboard_data)
    
    if not model_scores:
        print(f"⚠️ [LMArena] 未能提取到模型分数，使用旧权重")
        return False
    
    print(f"[LMArena] 成功提取 {len(model_scores)} 个模型的分数:")
    for model_name, score in model_scores.items():
        print(f"  - {model_name}: {score}")
    
    # 标准化分数
    if len(model_scores) > 1:
        scores_list = list(model_scores.values())
        min_score = min(scores_list)
        max_score = max(scores_list)
        
        normalized_scores = {}
        for model_name, score in model_scores.items():
            normalized_scores[model_name] = normalize_score(score, min_score, max_score)
        
        model_scores = normalized_scores
    elif len(model_scores) == 1:
        # 只有一个模型，设置为最大值
        model_name = list(model_scores.keys())[0]
        model_scores[model_name] = MAX_SCORE
    
    # 更新文件
    success = update_weights_file(model_scores)
    
    if success:
        # 格式化输出日志
        score_strs = []
        for model_name, score in sorted(model_scores.items()):
            short_name = model_name.replace("Claude-3.7-Sonnet", "Claude-3.7").replace("Gemini-2.5-Pro", "Gemini").replace("DeepSeek Chat", "DeepSeek")
            score_strs.append(f"{short_name}={score}")
        
        print(f"[LMArena] 更新完成：{', '.join(score_strs)}")
    
    return success


def main():
    """命令行入口"""
    success = update_lmarena_weights()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

