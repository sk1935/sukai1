"""
评估指标模块（Metrics Module）
实现各种预测评估指标，支持二元和多类别场景
"""
import numpy as np
import pandas as pd
from typing import Union, List, Tuple, Optional

try:
    from scipy import stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    # 提供简化的kurtosis实现（如果scipy不可用）
    def stats():
        class Stats:
            @staticmethod
            def kurtosis(x):
                # 简化的峰度计算
                mean = np.mean(x)
                std = np.std(x)
                if std == 0:
                    return 0.0
                n = len(x)
                return np.mean(((x - mean) / std) ** 4) - 3.0
        return Stats()


def brier_score(y_true: Union[np.ndarray, List], p_pred: Union[np.ndarray, List], 
                is_binary: Optional[bool] = None) -> float:
    """
    计算 Brier Score（均方误差）
    
    Args:
        y_true: 真实标签（0/1 或类别索引）
        p_pred: 预测概率（单值二元概率或概率分布）
        is_binary: 是否为二元分类（None时自动检测）
    
    Returns:
        Brier Score（越小越好，范围[0, 1]）
    
    Examples:
        # 二元分类
        brier_score([1, 0, 1], [0.8, 0.3, 0.9])  # 0.033
        
        # 多类别
        brier_score([0, 1, 2], [[0.9, 0.1, 0.0], [0.2, 0.7, 0.1], [0.1, 0.2, 0.7]])  # 多类Brier
    """
    y_true = np.asarray(y_true)
    p_pred = np.asarray(p_pred)
    
    # 自动检测是否为二元分类
    if is_binary is None:
        if p_pred.ndim == 1:
            # 一维数组，可能是二元概率
            is_binary = True
        else:
            # 二维数组，多类别概率分布
            is_binary = False
    
    if is_binary:
        # 二元分类：Brier = mean((y - p)^2)
        if y_true.dtype != p_pred.dtype:
            # 确保类型一致
            if y_true.max() > 1:
                y_true = (y_true == y_true.max()).astype(float)
            else:
                y_true = y_true.astype(float)
        
        return float(np.mean((y_true - p_pred) ** 2))
    else:
        # 多类别：Brier = mean(sum((y_one_hot - p)^2) / num_classes)
        # y_true 应该是类别索引，转换为 one-hot
        n_classes = p_pred.shape[1]
        y_one_hot = np.eye(n_classes)[y_true.astype(int)]
        
        return float(np.mean(np.sum((y_one_hot - p_pred) ** 2, axis=1)))


def log_loss_score(y_true: Union[np.ndarray, List], p_pred: Union[np.ndarray, List],
                   eps: float = 1e-15) -> float:
    """
    计算对数损失（Log Loss / Cross-Entropy Loss）
    支持二元和多类别
    
    Args:
        y_true: 真实标签（0/1 或类别索引）
        p_pred: 预测概率（单值二元概率或概率分布）
        eps: 防止 log(0) 的小值
    
    Returns:
        Log Loss（越小越好，≥0）
    """
    y_true = np.asarray(y_true)
    p_pred = np.asarray(p_pred)
    
    # 确保概率在有效范围内
    p_pred = np.clip(p_pred, eps, 1 - eps)
    
    if p_pred.ndim == 1:
        # 二元分类
        if y_true.dtype != p_pred.dtype:
            y_true = y_true.astype(float)
        
        return float(-np.mean(y_true * np.log(p_pred) + (1 - y_true) * np.log(1 - p_pred)))
    else:
        # 多类别
        n_samples, n_classes = p_pred.shape
        y_one_hot = np.eye(n_classes)[y_true.astype(int)]
        
        return float(-np.mean(np.sum(y_one_hot * np.log(p_pred), axis=1)))


def ece_score(y_true: Union[np.ndarray, List], p_pred: Union[np.ndarray, List],
              n_bins: int = 10) -> float:
    """
    计算期望校准误差（Expected Calibration Error, ECE）
    
    ECE衡量预测概率与真实频率的一致性
    
    Args:
        y_true: 真实标签（0/1 或类别索引）
        p_pred: 预测概率（单值二元概率或概率分布）
        n_bins: 分箱数量（默认10）
    
    Returns:
        ECE（越小越好，范围[0, 1]）
    
    Note:
        对于多类别，使用最大概率作为置信度
    """
    y_true = np.asarray(y_true)
    p_pred = np.asarray(p_pred)
    
    if p_pred.ndim == 1:
        # 二元分类：使用预测概率作为置信度
        confidences = p_pred
        accuracies = (y_true == (p_pred >= 0.5).astype(int)).astype(float)
    else:
        # 多类别：使用最大概率作为置信度，对应的类别作为预测
        confidences = np.max(p_pred, axis=1)
        predictions = np.argmax(p_pred, axis=1)
        accuracies = (y_true.astype(int) == predictions).astype(float)
    
    # 分箱
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]
    
    ece = 0.0
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        # 找到在范围内的样本
        in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
        prop_in_bin = in_bin.sum()
        
        if prop_in_bin > 0:
            accuracy_in_bin = accuracies[in_bin].mean()
            avg_confidence_in_bin = confidences[in_bin].mean()
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
    
    return float(ece / len(y_true))


def sharpness(p_pred: Union[np.ndarray, List], method: str = "variance") -> float:
    """
    计算概率分布尖锐度（Sharpness）
    
    Sharpness衡量预测分布的确定性程度（不依赖真实标签）
    
    Args:
        p_pred: 预测概率（单值二元概率或概率分布）
        method: 计算方法（"variance" 或 "kurtosis"）
    
    Returns:
        Sharpness值
        - variance: 方差（多类别）或 p(1-p)（二元）
        - kurtosis: 峰度（越高越尖锐）
    """
    p_pred = np.asarray(p_pred)
    
    if p_pred.ndim == 1:
        # 二元概率
        if method == "variance":
            # 对于二元，sharpness = mean(p * (1-p))
            return float(np.mean(p_pred * (1 - p_pred)))
        else:
            # 峰度：转换为分布后再计算
            # 对于二元，可以计算 p 值的峰度
            if HAS_SCIPY:
                return float(stats.kurtosis(p_pred))
            else:
                # 简化的峰度计算
                mean = np.mean(p_pred)
                std = np.std(p_pred)
                if std == 0:
                    return 0.0
                return float(np.mean(((p_pred - mean) / std) ** 4) - 3.0)
    else:
        # 多类别概率分布
        if method == "variance":
            # 计算每个样本的熵，然后取平均的负值（或直接用方差）
            # 或者：mean(max(p)) - 1/n_classes（最大概率与均匀分布的差异）
            n_classes = p_pred.shape[1]
            max_probs = np.max(p_pred, axis=1)
            # Sharpness = mean(max_prob) - 1/n_classes
            return float(np.mean(max_probs) - 1.0 / n_classes)
        else:
            # 峰度：对每个样本的最大概率计算峰度
            max_probs = np.max(p_pred, axis=1)
            if HAS_SCIPY:
                return float(stats.kurtosis(max_probs))
            else:
                # 简化的峰度计算
                mean = np.mean(max_probs)
                std = np.std(max_probs)
                if std == 0:
                    return 0.0
                return float(np.mean(((max_probs - mean) / std) ** 4) - 3.0)


def paired_t_test(scores_before: Union[np.ndarray, List], 
                  scores_after: Union[np.ndarray, List]) -> Tuple[float, float]:
    """
    配对 t 检验（Paired t-test）
    
    用于比较两个相关样本的均值差异（如基线 vs 变体）
    
    Args:
        scores_before: 基线得分列表
        scores_after: 变体得分列表（必须与before长度相同）
    
    Returns:
        (t_statistic, p_value)
        p_value < 0.05 通常表示显著差异
    """
    scores_before = np.asarray(scores_before)
    scores_after = np.asarray(scores_after)
    
    if len(scores_before) != len(scores_after):
        raise ValueError(f"两个样本长度必须相同: {len(scores_before)} vs {len(scores_after)}")
    
    # 计算差值
    differences = scores_after - scores_before
    
    # 配对 t 检验
    if HAS_SCIPY:
        t_stat, p_value = stats.ttest_1samp(differences, 0.0)
        return float(t_stat), float(p_value)
    else:
        # 简化的t检验（手动计算）
        n = len(differences)
        if n < 2:
            return 0.0, 1.0
        
        mean_diff = np.mean(differences)
        std_diff = np.std(differences, ddof=1)
        
        if std_diff == 0:
            return 0.0, 1.0
        
        t_stat = mean_diff / (std_diff / np.sqrt(n))
        # 简化的p值（使用正态近似，实际应查t分布表）
        p_value = 2.0 * (1.0 - 0.5 * (1.0 + np.tanh(abs(t_stat) / np.sqrt(n))))
        return float(t_stat), float(p_value)


def compute_all_metrics(y_true: Union[np.ndarray, List], 
                       p_pred: Union[np.ndarray, List],
                       n_bins: int = 10) -> dict:
    """
    计算所有评估指标
    
    Args:
        y_true: 真实标签
        p_pred: 预测概率
        n_bins: ECE分箱数
    
    Returns:
        包含所有指标的字典
    """
    results = {
        "brier": brier_score(y_true, p_pred),
        "log_loss": log_loss_score(y_true, p_pred),
        "ece": ece_score(y_true, p_pred, n_bins),
        "sharpness": sharpness(p_pred, method="variance")
    }
    
    return results


def batch_compute_metrics(df: pd.DataFrame, 
                          y_col: str = "resolved_outcome",
                          p_col: str = "ai_prob",
                          is_binary: Optional[bool] = None) -> dict:
    """
    批量计算指标（从DataFrame）
    
    Args:
        df: 包含真实标签和预测概率的DataFrame
        y_col: 真实标签列名
        p_col: 预测概率列名
        is_binary: 是否为二元（None时自动检测）
    
    Returns:
        指标字典
    """
    y_true = df[y_col].values
    p_pred = df[p_col].values
    
    return compute_all_metrics(y_true, p_pred)

