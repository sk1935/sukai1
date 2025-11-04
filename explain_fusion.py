"""
解释模型共识的计算方式
"""
import numpy as np

# 模型权重配置
MODEL_WEIGHTS = {
    "gpt-4o": 3.0,
    "claude-3-7-sonnet-latest": 2.5,
    "gemini-2.5-flash": 2.0,
    "grok-3": 2.0,
    "gpt-4o-mini": 2.0
}

# 置信度权重
CONFIDENCE_WEIGHTS = {
    "low": 1.0,
    "medium": 2.0,
    "high": 3.0
}

# 融合权重
MARKET_WEIGHT = 0.3  # 市场价格占30%
MODEL_WEIGHT = 0.7   # 模型共识占70%

def explain_calculation():
    print("=" * 60)
    print("📊 模型共识计算说明")
    print("=" * 60)
    print()
    
    print("假设有3个模型返回了预测：")
    print()
    
    # 示例数据
    example_results = {
        "gpt-4o": {"probability": 15.0, "confidence": "high"},
        "claude-3-7-sonnet-latest": {"probability": 12.0, "confidence": "medium"},
        "gemini-2.5-flash": {"probability": 8.0, "confidence": "medium"}
    }
    
    market_prob = 50.0  # 市场价格
    
    print("模型预测：")
    for model, result in example_results.items():
        print(f"  • {model}: {result['probability']}% (置信度: {result['confidence']})")
    print(f"  • 市场价格: {market_prob}%")
    print()
    
    # 步骤1: 计算每个模型的总权重
    print("步骤1: 计算每个模型的总权重")
    print("  总权重 = 模型基础权重 × 置信度权重")
    print()
    
    probabilities = []
    weights = []
    
    for model_name, result in example_results.items():
        base_weight = MODEL_WEIGHTS.get(model_name, 2.0)
        confidence_weight = CONFIDENCE_WEIGHTS.get(result['confidence'], 2.0)
        total_weight = base_weight * confidence_weight
        
        probabilities.append(result['probability'])
        weights.append(total_weight)
        
        print(f"  {model_name}:")
        print(f"    基础权重: {base_weight}")
        print(f"    置信度权重: {confidence_weight} ({result['confidence']})")
        print(f"    总权重: {total_weight}")
        print(f"    预测值: {result['probability']}%")
        print()
    
    # 步骤2: 计算加权平均
    print("步骤2: 计算加权平均（模型共识）")
    probabilities = np.array(probabilities)
    weights = np.array(weights)
    weighted_mean = np.average(probabilities, weights=weights)
    
    print(f"  加权平均 = Σ(预测值 × 权重) / Σ(权重)")
    print(f"  = ({' + '.join([f'{p}×{w}' for p, w in zip(probabilities, weights)])}) / {weights.sum()}")
    print(f"  = {weighted_mean:.2f}%")
    print()
    
    # 步骤3: 计算不确定性（标准差）
    variance = np.average((probabilities - weighted_mean) ** 2, weights=weights)
    uncertainty = np.sqrt(variance)
    
    print("步骤3: 计算不确定性（加权标准差）")
    print(f"  不确定性 = √[Σ(权重 × (预测值 - 平均值)²) / Σ(权重)]")
    print(f"  = {uncertainty:.2f}%")
    print()
    
    # 步骤4: 融合市场价格
    print("步骤4: 融合市场价格")
    final_prob = MODEL_WEIGHT * weighted_mean + MARKET_WEIGHT * market_prob
    
    print(f"  最终概率 = {MODEL_WEIGHT} × {weighted_mean:.2f}% + {MARKET_WEIGHT} × {market_prob}%")
    print(f"  = {MODEL_WEIGHT * weighted_mean:.2f}% + {MARKET_WEIGHT * market_prob:.2f}%")
    print(f"  = {final_prob:.2f}%")
    print()
    
    print("=" * 60)
    print(f"📊 最终结果: {final_prob:.1f}% ± {uncertainty:.1f}%")
    print("=" * 60)
    print()
    print("说明：")
    print(f"  • 模型共识: {weighted_mean:.1f}% (加权平均)")
    print(f"  • 市场价格: {market_prob:.1f}%")
    print(f"  • 融合后: {final_prob:.1f}% (70%模型 + 30%市场)")
    print(f"  • 不确定性: ±{uncertainty:.1f}% (模型预测之间的差异)")

if __name__ == "__main__":
    explain_calculation()
