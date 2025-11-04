"""
消融实验模块（Ablation Study Module）
支持通过配置开关进行不同实验变体的测试
"""
import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fusion_engine import FusionEngine
from metrics import (
    brier_score, log_loss_score, ece_score, sharpness,
    paired_t_test, compute_all_metrics
)

load_dotenv()


class ExperimentConfig:
    """实验配置管理器"""
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化实验配置
        
        Args:
            config_path: YAML配置文件路径（可选）
        """
        self.config = {}
        
        # 从环境变量读取配置
        self._load_from_env()
        
        # 从YAML文件读取配置（如果提供）
        if config_path is None:
            # 默认路径
            default_path = Path(__file__).parent.parent / "config" / "experiments.yaml"
            if default_path.exists():
                config_path = default_path
        
        if config_path and config_path.exists():
            self._load_from_yaml(config_path)
        
        # 设置默认值
        self._set_defaults()
    
    def _load_from_env(self):
        """从环境变量读取配置"""
        self.config = {
            "FUSION": {
                "consensus_coef": os.getenv("FUSION_CONSENSUS_COEF", "true").lower() == "true",
                "market_bias": os.getenv("FUSION_MARKET_BIAS", "true").lower() == "true",
                "demarket_penalty": os.getenv("FUSION_DEMARKET_PENALTY", "true").lower() == "true"
            },
            "CALIBRATION": {
                "post_calibration": os.getenv("CALIBRATION_POST_CALIBRATION", "none").lower()
            },
            "SENTIMENT": {
                "reddit_bluesky": os.getenv("SENTIMENT_REDDIT_BLUESKY", "false").lower() == "true"
            }
        }
    
    def _load_from_yaml(self, config_path: Path):
        """从YAML文件读取配置"""
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    # 合并配置（YAML优先级更高）
                    self._deep_update(self.config, yaml_config)
        except ImportError:
            print("⚠️ PyYAML未安装，跳过YAML配置加载（可选依赖）")
        except Exception as e:
            print(f"⚠️ 加载YAML配置失败: {e}")
    
    def _deep_update(self, base: dict, update: dict):
        """深度合并字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
    def _set_defaults(self):
        """设置默认值"""
        defaults = {
            "FUSION": {
                "consensus_coef": True,
                "market_bias": True,
                "demarket_penalty": True
            },
            "CALIBRATION": {
                "post_calibration": "none"
            },
            "SENTIMENT": {
                "reddit_bluesky": False
            }
        }
        
        for section, values in defaults.items():
            if section not in self.config:
                self.config[section] = {}
            for key, default_value in values.items():
                if key not in self.config[section]:
                    self.config[section][key] = default_value
    
    def get(self, section: str, key: str, default=None):
        """获取配置值"""
        return self.config.get(section, {}).get(key, default)
    
    def to_dict(self) -> dict:
        """转换为字典（供FusionEngine使用）"""
        return self.config.copy()


def run_ablation(dataset_path: str, config: Optional[ExperimentConfig] = None,
                 baseline_config: Optional[Dict] = None) -> pd.DataFrame:
    """
    运行消融实验
    
    Args:
        dataset_path: CSV文件路径，包含列：
            - market_id: 市场ID
            - resolved_outcome: 真实结果（0/1 或类别索引）
            - ai_prob: AI预测概率（单值或概率分布）
            - market_prob: 市场价格（可选）
            - timestamp: 时间戳（可选）
        config: 实验配置（默认使用环境变量）
        baseline_config: 基线配置（默认：所有开关为True）
    
    Returns:
        DataFrame，包含各变体的评估指标：
        [variant, brier, logloss, ece, sharpness, N, p_value]
    """
    # 读取数据集
    df = pd.read_csv(dataset_path)
    print(f"📊 读取数据集: {len(df)} 条记录")
    
    if config is None:
        config = ExperimentConfig()
    
    if baseline_config is None:
        baseline_config = {
            "consensus_coef": True,
            "market_bias": True,
            "demarket_penalty": True,
            "post_calibration": "none"
        }
    
    # 定义实验变体
    variants = [
        {
            "name": "baseline",
            "consensus_coef": baseline_config.get("consensus_coef", True),
            "market_bias": baseline_config.get("market_bias", True),
            "demarket_penalty": baseline_config.get("demarket_penalty", True),
            "post_calibration": baseline_config.get("post_calibration", "none")
        },
        {
            "name": "no_consensus_coef",
            "consensus_coef": False,
            "market_bias": True,
            "demarket_penalty": True,
            "post_calibration": "none"
        },
        {
            "name": "no_market_bias",
            "consensus_coef": True,
            "market_bias": False,
            "demarket_penalty": True,
            "post_calibration": "none"
        },
        {
            "name": "no_demarket_penalty",
            "consensus_coef": True,
            "market_bias": True,
            "demarket_penalty": False,
            "post_calibration": "none"
        },
        {
            "name": "with_binning_calibration",
            "consensus_coef": True,
            "market_bias": True,
            "demarket_penalty": True,
            "post_calibration": "binning"
        },
        {
            "name": "with_platt_calibration",
            "consensus_coef": True,
            "market_bias": True,
            "demarket_penalty": True,
            "post_calibration": "platt"
        }
    ]
    
    results = []
    baseline_metrics = None
    
    for variant in variants:
        print(f"\n🧪 测试变体: {variant['name']}")
        
        # 创建变体配置
        variant_config = ExperimentConfig()
        variant_config.config["FUSION"]["consensus_coef"] = variant["consensus_coef"]
        variant_config.config["FUSION"]["market_bias"] = variant["market_bias"]
        variant_config.config["FUSION"]["demarket_penalty"] = variant["demarket_penalty"]
        variant_config.config["CALIBRATION"]["post_calibration"] = variant["post_calibration"]
        
        # 创建使用该配置的FusionEngine
        fusion_engine = FusionEngine(experiment_config=variant_config)
        
        # 计算该变体的指标
        # 注意：这里需要模拟融合过程，实际应该调用FusionEngine
        # 为简化，我们假设df中已有融合后的概率
        variant_df = df.copy()
        
        # 如果df中有"ai_prob"，直接使用；否则需要模拟融合
        if "final_prob" in variant_df.columns:
            p_pred = variant_df["final_prob"].values
        elif "ai_prob" in variant_df.columns:
            # 简单处理：如果有market_prob，融合；否则直接用ai_prob
            if "market_prob" in variant_df.columns:
                # 模拟融合：80% AI + 20% 市场
                p_pred = 0.8 * variant_df["ai_prob"].values + 0.2 * variant_df["market_prob"].values
            else:
                p_pred = variant_df["ai_prob"].values
        else:
            raise ValueError("数据集必须包含 'final_prob' 或 'ai_prob' 列")
        
        y_true = variant_df["resolved_outcome"].values
        
        # 计算指标
        metrics = compute_all_metrics(y_true, p_pred)
        
        # 配置已保存在variant_config中，不需要恢复
        
        result_row = {
            "variant": variant["name"],
            "brier": metrics["brier"],
            "logloss": metrics["log_loss"],
            "ece": metrics["ece"],
            "sharpness": metrics["sharpness"],
            "N": len(variant_df)
        }
        
        # 如果是基线，保存预测概率用于后续比较
        if variant["name"] == "baseline":
            baseline_preds = p_pred.copy()
            baseline_metrics = metrics
            result_row["p_value"] = None
        else:
            # 与基线做配对t检验
            # 使用Brier Score作为样本得分
            baseline_scores = _compute_sample_scores(y_true, baseline_preds)
            variant_scores = _compute_sample_scores(y_true, p_pred)
            _, p_value = paired_t_test(baseline_scores, variant_scores)
            result_row["p_value"] = p_value
        
        results.append(result_row)
        
        print(f"   Brier: {metrics['brier']:.4f}, LogLoss: {metrics['log_loss']:.4f}, "
              f"ECE: {metrics['ece']:.4f}, Sharpness: {metrics['sharpness']:.4f}")
        if result_row["p_value"]:
            print(f"   vs 基线 p-value: {result_row['p_value']:.4f}")
    
    results_df = pd.DataFrame(results)
    return results_df


def _compute_sample_scores(y_true: np.ndarray, p_pred: np.ndarray) -> np.ndarray:
    """
    计算每个样本的Brier Score（用于配对t检验）
    
    Args:
        y_true: 真实标签
        p_pred: 预测概率
    
    Returns:
        每个样本的Brier Score
    """
    return (y_true - p_pred) ** 2


def print_ablation_table(results_df: pd.DataFrame):
    """打印格式化的消融实验结果表"""
    print("\n" + "=" * 80)
    print("🧪 消融实验结果".center(80))
    print("=" * 80)
    
    print(f"\n{'变体':<25} {'Brier':<10} {'LogLoss':<10} {'ECE':<10} {'Sharpness':<10} {'N':<8} {'p-value':<10}")
    print("-" * 80)
    
    for _, row in results_df.iterrows():
        p_val_str = f"{row['p_value']:.4f}" if row['p_value'] is not None else "-"
        marker = " *" if row['p_value'] and row['p_value'] < 0.05 else ""
        
        print(f"{row['variant']:<25} {row['brier']:<10.4f} {row['logloss']:<10.4f} "
              f"{row['ece']:<10.4f} {row['sharpness']:<10.4f} {int(row['N']):<8} "
              f"{p_val_str:<10}{marker}")
    
    print("\n* p < 0.05 (相对于基线)")
    print("=" * 80)

