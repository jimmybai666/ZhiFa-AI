"""
test_case_prediction.py - 案情预测功能测试脚本

测试刑期预测、罪名预测等功能
"""
import warnings
import os
import json
import random
import csv
from datetime import datetime
from typing import List, Dict, Any

warnings.filterwarnings('ignore')

# 禁用LangChain追踪
os.environ["LANGCHAIN_WARNING"] = "false"
os.environ["LANGSMITH_WARNINGS"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_ENDPOINT"] = ""
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ["LANGSMITH_TRACING"] = "false"

import sys
from dotenv import load_dotenv

# 添加项目根目录到路径（tests/ 目录上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # 切换工作目录到项目根目录

from src.config.config import config
from src.chain.case_prediction import get_case_prediction_chain

load_dotenv('.env')


def test_single_prediction(chain, case_data: Dict[str, Any], case_num: int) -> Dict[str, Any]:
    """
    测试单个案例的刑期预测
    
    Args:
        chain: 案情预测链
        case_data: 案例数据
        case_num: 案例编号
        
    Returns:
        测试结果字典
    """
    fact = case_data.get('fact', '')
    meta = case_data.get('meta', {})
    term_of_imprisonment = meta.get('term_of_imprisonment', {})
    actual_imprisonment = term_of_imprisonment.get('imprisonment', 0)
    accusations = meta.get('accusation', [])
    
    print(f"\n{'='*60}")
    print(f"【测试案例 {case_num}】")
    print(f"{'='*60}")
    print(f"罪名: {', '.join(accusations) if accusations else '未知'}")
    print(f"实际刑期: {actual_imprisonment}个月 ({actual_imprisonment//12}年{actual_imprisonment%12}个月)")
    print(f"案情摘要: {fact[:100]}...")
    
    try:
        # 调用预测
        result = chain.predict_imprisonment(fact, accusations)
        
        # 显示AI回答
        print(f"\n【AI大模型回答】")
        print("-"*40)
        print(result.get('ai_response', '无响应'))
        print("-"*40)
        
        # 提取预测结果
        predicted = result.get('predicted_imprisonment')
        
        if predicted is not None:
            error = abs(predicted - actual_imprisonment)
            print(f"\n【预测结果对比】")
            print(f"✓ 预测刑期: {predicted}个月 ({predicted//12}年{predicted%12}个月)")
            print(f"✓ 实际刑期: {actual_imprisonment}个月")
            print(f"✓ 误差: {error}个月")
            
            return {
                "success": True,
                "case_num": case_num,
                "fact": fact,
                "accusation": accusations,
                "actual": actual_imprisonment,
                "predicted": predicted,
                "error": error
            }
        else:
            print("⚠️ 无法提取预测刑期")
            return {
                "success": False,
                "case_num": case_num,
                "error_msg": "无法提取预测刑期"
            }
            
    except Exception as e:
        print(f"❌ 测试出错: {e}")
        return {
            "success": False,
            "case_num": case_num,
            "error_msg": str(e)
        }


def test_model(num_cases: int = 10) -> List[Dict[str, Any]]:
    """
    从测试集中随机抽取案例进行测试
    
    Args:
        num_cases: 测试案例数量
        
    Returns:
        测试结果列表
    """
    print("="*60)
    print("刑期预测系统 - 模型测试")
    print("="*60)
    
    # 初始化预测链
    print("\n正在初始化案情预测链...")
    try:
        chain = get_case_prediction_chain(config)
        print("✓ 案情预测链初始化成功")
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        return []
    
    # 加载测试集
    print(f"\n正在加载测试集: {config.CASE_TESTSET_PATH}")
    test_cases = []
    with open(config.CASE_TESTSET_PATH, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if line.strip():
                case_data = json.loads(line)
                case_data['_index'] = idx + 1
                test_cases.append(case_data)
    
    print(f"测试集共有 {len(test_cases)} 个案例")
    
    # 随机抽取
    if num_cases > len(test_cases):
        num_cases = len(test_cases)
    
    selected_cases = random.sample(test_cases, num_cases)
    print(f"随机抽取 {len(selected_cases)} 个案例进行测试")
    
    # 测试每个案例
    results = []
    for i, case_data in enumerate(selected_cases, 1):
        result = test_single_prediction(chain, case_data, i)
        results.append(result)
    
    # 统计结果
    print("\n" + "="*60)
    print("【测试统计】")
    print("="*60)
    
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    print(f"成功: {len(successful)}/{len(results)}")
    print(f"失败: {len(failed)}/{len(results)}")
    
    if successful:
        errors = [r['error'] for r in successful]
        avg_error = sum(errors) / len(errors)
        print(f"平均误差: {avg_error:.1f}个月")
        print(f"最小误差: {min(errors)}个月")
        print(f"最大误差: {max(errors)}个月")
        
        # 计算误差分布
        error_within_6 = sum(1 for e in errors if e <= 6)
        error_within_12 = sum(1 for e in errors if e <= 12)
        error_within_24 = sum(1 for e in errors if e <= 24)
        
        print(f"\n误差分布:")
        print(f"  ≤6个月: {error_within_6}/{len(successful)} ({error_within_6*100/len(successful):.1f}%)")
        print(f"  ≤12个月: {error_within_12}/{len(successful)} ({error_within_12*100/len(successful):.1f}%)")
        print(f"  ≤24个月: {error_within_24}/{len(successful)} ({error_within_24*100/len(successful):.1f}%)")
    
    # 保存结果到CSV
    if successful:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = os.path.join(config.OUTPUT_DIR, f"案情预测测试结果_{timestamp}.csv")
        
        # 确保输出目录存在
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        
        print(f"\n正在保存结果到 {csv_filename}...")
        with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as csvfile:
            fieldnames = ['案例编号', '案情描述', '罪名', '实际刑期', '预测刑期', '误差']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for r in successful:
                writer.writerow({
                    '案例编号': r['case_num'],
                    '案情描述': r['fact'][:200] + '...',
                    '罪名': '、'.join(r['accusation']) if r['accusation'] else '未知',
                    '实际刑期': r['actual'],
                    '预测刑期': r['predicted'],
                    '误差': r['error']
                })
        
        print(f"✓ 结果已保存")
    
    return results


def interactive_mode():
    """交互模式 - 手动输入案情进行预测"""
    print("="*60)
    print("刑期预测系统 - 交互模式")
    print("="*60)
    
    # 初始化预测链
    print("\n正在初始化案情预测链...")
    try:
        chain = get_case_prediction_chain(config)
        print("✓ 案情预测链初始化成功")
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        return
    
    print("\n系统已就绪！")
    
    while True:
        print("\n" + "="*60)
        print("请选择功能:")
        print("1. 刑期预测")
        print("2. 罪名预测")
        print("3. 案件综合分析")
        print("4. 退出")
        print("-"*60)
        
        choice = input("请输入选项 (1/2/3/4): ").strip()
        
        if choice == "4":
            print("\n再见！")
            break
        
        if choice not in ["1", "2", "3"]:
            print("无效选项，请重新输入")
            continue
        
        # 获取案情输入
        print("\n请输入案情描述（输入空行结束）：")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        
        query_fact = "\n".join(lines)
        
        if not query_fact.strip():
            print("案情描述不能为空！")
            continue
        
        print("\n" + "="*60)
        
        if choice == "1":
            # 刑期预测
            accusations_input = input("涉及罪名（可选，多个用逗号分隔）：").strip()
            accusations = [a.strip() for a in accusations_input.split(',')] if accusations_input else None
            
            result = chain.predict_imprisonment(query_fact, accusations)
            
            print("\n【AI预测结果】")
            print("-"*40)
            print(result.get('ai_response', '无响应'))
            print("-"*40)
            
            predicted = result.get('predicted_imprisonment')
            if predicted:
                print(f"\n✓ 预测刑期: {predicted}个月 ({predicted//12}年{predicted%12}个月)")
        
        elif choice == "2":
            # 罪名预测
            result = chain.predict_accusation(query_fact)
            
            print("\n【AI预测结果】")
            print("-"*40)
            print(result.get('ai_response', '无响应'))
            print("-"*40)
            
            if result.get('accusation_distribution'):
                print(f"\n相似案例罪名分布: {result['accusation_distribution']}")
        
        elif choice == "3":
            # 综合分析
            result = chain.analyze_case(query_fact)
            
            print("\n【AI分析结果】")
            print("-"*40)
            print(result.get('ai_response', '无响应'))
            print("-"*40)
        
        print("\n" + "="*60)
        print("预测完成！")


def main():
    """主函数"""
    print("="*60)
    print("刑期预测系统")
    print("="*60)
    print("\n请选择运行模式：")
    print("1. 交互模式 - 手动输入案情进行预测")
    print("2. 测试模式 - 从测试集中随机抽取案例进行测试")
    print("3. 退出")
    
    choice = input("\n请输入选项 (1/2/3): ").strip()
    
    if choice == "3":
        print("\n再见！")
    elif choice == "1":
        interactive_mode()
    elif choice == "2":
        while True:
            try:
                num_input = input("\n请输入要测试的案例数量（建议1-20）: ").strip()
                num_cases = int(num_input)
                
                if num_cases <= 0:
                    print("❌ 案例数量必须大于0")
                    continue
                elif num_cases > 50:
                    confirm = input(f"⚠️ 数量较大({num_cases}个)，可能需要较长时间，确认继续？(y/n): ").strip().lower()
                    if confirm != 'y':
                        continue
                
                break
            except ValueError:
                print("❌ 请输入有效的数字")
        
        test_model(num_cases=num_cases)
    else:
        print("\n无效的选项！")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n程序出错: {e}")
        import traceback
        traceback.print_exc()

