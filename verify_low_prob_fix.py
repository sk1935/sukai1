"""
验证低概率过滤Bug修复

测试场景：
1. 单选项事件，market_prob=7.0，outcomes=[] → 不应过滤
2. 单选项事件，market_prob=0.5，outcomes=[] → 应该过滤
3. 多选项事件，正常概率 → 不应过滤
4. outcomes包含错误数据但event_data有正确market_prob → 不应过滤
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.event_manager import EventManager


def run_filter(manager: EventManager, event_data, threshold: float):
    """Helper to run async filter in sync test harness."""
    return asyncio.run(manager.filter_low_probability_event(event_data, threshold=threshold))


def test_case_1():
    """测试场景1：单选项事件，market_prob=7.0，outcomes=[]"""
    print("\n" + "="*60)
    print("测试场景1：单选项事件，market_prob=7.0")
    print("="*60)
    
    manager = EventManager()
    event_data = {
        "question": "Russia x Ukraine ceasefire in 2025?",
        "market_prob": 7.0,
        "outcomes": [],
        "is_multi_option": False,
        "is_mock": False
    }
    
    result = run_filter(manager, event_data, threshold=1.0)
    
    if result is None:
        print("✅ 测试通过：事件未被过滤（预期结果）")
        return True
    else:
        print(f"❌ 测试失败：事件被错误过滤")
        print(f"   max_probability: {result.get('max_probability')}")
        print(f"   threshold: {result.get('threshold')}")
        return False


def test_case_2():
    """测试场景2：单选项事件，market_prob=0.5"""
    print("\n" + "="*60)
    print("测试场景2：真正的低概率事件，market_prob=0.5")
    print("="*60)
    
    manager = EventManager()
    event_data = {
        "question": "Very unlikely event",
        "market_prob": 0.5,
        "outcomes": [],
        "is_multi_option": False,
        "is_mock": False
    }
    
    result = run_filter(manager, event_data, threshold=1.0)
    
    if result is not None:
        print("✅ 测试通过：低概率事件被正确过滤")
        print(f"   max_probability: {result.get('max_probability')}")
        print(f"   threshold: {result.get('threshold')}")
        return True
    else:
        print(f"❌ 测试失败：低概率事件未被过滤")
        return False


def test_case_3():
    """测试场景3：多选项事件，正常概率"""
    print("\n" + "="*60)
    print("测试场景3：多选项事件，正常概率")
    print("="*60)
    
    manager = EventManager()
    event_data = {
        "question": "Who will win?",
        "market_prob": 30.0,  # 首个选项的概率
        "outcomes": [
            {"name": "A", "market_prob": 30.0},
            {"name": "B", "market_prob": 40.0},
            {"name": "C", "market_prob": 30.0}
        ],
        "is_multi_option": True,
        "is_mock": False
    }
    
    result = run_filter(manager, event_data, threshold=1.0)
    
    if result is None:
        print("✅ 测试通过：多选项事件未被过滤（预期结果）")
        return True
    else:
        print(f"❌ 测试失败：多选项事件被错误过滤")
        print(f"   max_probability: {result.get('max_probability')}")
        return False


def test_case_4():
    """测试场景4：outcomes包含错误数据，但event_data有正确market_prob"""
    print("\n" + "="*60)
    print("测试场景4：outcomes有错误数据，event_data有正确market_prob")
    print("="*60)
    
    manager = EventManager()
    event_data = {
        "question": "Test event",
        "market_prob": 5.5,  # 正确的概率
        "outcomes": [
            {"name": "Yes", "market_prob": 0.0},  # 错误的数据
            {"name": "No", "market_prob": 0.0}    # 错误的数据
        ],
        "is_multi_option": False,
        "is_mock": False
    }
    
    result = run_filter(manager, event_data, threshold=1.0)
    
    if result is None:
        print("✅ 测试通过：正确使用event_data的market_prob，未被过滤")
        print("   （这是本次修复的关键场景）")
        return True
    else:
        print(f"❌ 测试失败：被错误过滤")
        print(f"   max_probability: {result.get('max_probability')}")
        print(f"   应该使用 event_data['market_prob']=5.5 而不是 outcomes 中的 0.0")
        return False


def test_case_5():
    """测试场景5：market_prob不存在，从outcomes提取"""
    print("\n" + "="*60)
    print("测试场景5：market_prob不存在，从outcomes提取")
    print("="*60)
    
    manager = EventManager()
    event_data = {
        "question": "Test event",
        # 没有 market_prob
        "outcomes": [
            {"name": "A", "market_prob": 15.0},
            {"name": "B", "market_prob": 35.0}
        ],
        "is_multi_option": True,
        "is_mock": False
    }
    
    result = run_filter(manager, event_data, threshold=1.0)
    
    if result is None:
        print("✅ 测试通过：从outcomes正确提取概率，未被过滤")
        return True
    else:
        print(f"❌ 测试失败：被错误过滤")
        print(f"   max_probability: {result.get('max_probability')}")
        return False


def main():
    """运行所有测试"""
    print("\n🧪 开始验证低概率过滤Bug修复")
    print("="*60)
    
    results = []
    
    results.append(("场景1：单选项，market_prob=7.0", test_case_1()))
    results.append(("场景2：真正低概率，market_prob=0.5", test_case_2()))
    results.append(("场景3：多选项事件", test_case_3()))
    results.append(("场景4：关键Bug场景", test_case_4()))
    results.append(("场景5：从outcomes提取", test_case_5()))
    
    print("\n" + "="*60)
    print("测试总结：")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status}  {name}")
    
    print("="*60)
    print(f"总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！Bug已修复。")
        return True
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，需要进一步检查。")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)



