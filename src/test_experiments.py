#!/usr/bin/env python3
"""
实验框架测试脚本
演示如何使用metrics和ablation模块
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.metrics import (
    brier_score, log_loss_score, ece_score, sharpness,
    paired_t_test, compute_all_metrics
)
from src.ablation import ExperimentConfig, run_ablation, print_ablation_table


def test_metrics():
    """测试评估指标"""
    print("=" * 80)
    print("🧮 Metrics模块测试".center(80))
    print("=" * 80)
    
    # 测试数据
    y_true = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
    p_pred = np.array([0.85, 0.15, 0.90, 0.20, 0.75, 0.25, 0.95, 0.10, 0.80, 0.30])
    
    metrics = compute_all_metrics(y_true, p_pred)
    
    print(f"\n【二元分类指标】")
    print(f"Brier Score: {metrics['brier']:.4f}")
    print(f"Log Loss: {metrics['log_loss']:.4f}")
    print(f"ECE: {metrics['ece']:.4f}")
    print(f"Sharpness: {metrics['sharpness']:.4f}")
    
    # 测试配对t检验
    scores_before = [0.15, 0.20, 0.18, 0.22, 0.19, 0.17, 0.21]
    scores_after = [0.12, 0.16, 0.15, 0.18, 0.16, 0.14, 0.17]
    t_stat, p_val = paired_t_test(scores_before, scores_after)
    
    print(f"\n【配对t检验】")
    print(f"t-statistic: {t_stat:.4f}")
    print(f"p-value: {p_val:.4f}")
    print(f"显著性: {'是' if p_val < 0.05 else '否'} (p < 0.05)")
    
    print("\n✅ Metrics测试通过！\n")


def test_ablation_example():
    """演示消融实验"""
    print("=" * 80)
    print("🧪 Ablation模块示例".center(80))
    print("=" * 80)
    
    # 创建示例数据集
    n_samples = 20
    test_data = {
        "market_id": [f"market_{i}" for i in range(n_samples)],
        "resolved_outcome": np.random.randint(0, 2, n_samples),
        "ai_prob": np.random.uniform(30, 70, n_samples),
        "market_prob": np.random.uniform(35, 65, n_samples),
        "timestamp": ["2025-01-01"] * n_samples
    }
    
    df_test = pd.DataFrame(test_data)
    test_csv_path = "/tmp/test_ablation_data.csv"
    df_test.to_csv(test_csv_path, index=False)
    
    print(f"\n📊 创建测试数据集: {test_csv_path}")
    print(f"   数据量: {len(df_test)} 条")
    print(f"   列: {list(df_test.columns)}")
    
    # 测试配置
    config = ExperimentConfig()
    print(f"\n【实验配置】")
    print(f"consensus_coef: {config.get('FUSION', 'consensus_coef')}")
    print(f"market_bias: {config.get('FUSION', 'market_bias')}")
    print(f"demarket_penalty: {config.get('FUSION', 'demarket_penalty')}")
    print(f"post_calibration: {config.get('CALIBRATION', 'post_calibration')}")
    
    print("\n💡 运行完整消融实验请调用:")
    print("   results_df = run_ablation(test_csv_path)")
    print("   print_ablation_table(results_df)")
    
    print("\n✅ Ablation测试通过！\n")


if __name__ == "__main__":
    test_metrics()
    test_ablation_example()
    
    print("=" * 80)
    print("✅ 所有测试完成！".center(80))
    print("=" * 80)



