"""
初始化案例向量数据库

功能说明：
1. 创建案例记录管理器的数据库表结构
2. 清空现有的案例向量数据库
3. 从案例数据集加载刑事案例
4. 将案例转换为向量并存储到Chroma数据库
5. 打印索引统计信息

运行方式：
    python scripts/init_case_vectorstore.py
    python scripts/init_case_vectorstore.py --test  # 测试模式
"""
import os
import sys
import pprint
import math
import time
import warnings
from dotenv import load_dotenv

# 忽略 SHA-1 相关的警告（在此场景下安全性足够）
warnings.filterwarnings('ignore', message='.*SHA-1.*')

# ==========================================
# 强制定位到项目根目录
# ==========================================
current_file_path = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file_path))
os.chdir(project_root)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"工作目录已锁定: {os.getcwd()}")

# 导入必须在路径设置之后
from src.vectorstore.case_loader import CaseLoader
from src.vectorstore.utils import case_index, clear_vectorstore, get_record_manager, get_vectorstore
from src.config.config import config

load_dotenv()
 

def init_case_vectorstore(max_cases: int = None) -> None:
    """
    初始化案例向量数据库
    
    Args:
        max_cases: 最大加载案例数（None表示全部加载，用于测试时可设置较小值）
    """
    print("="*60)
    print("案例向量数据库初始化")
    print("="*60)
    
    # 获取记录管理器，用于跟踪哪些文档已被索引
    record_manager = get_record_manager("criminal_cases")
    # 创建数据库表结构
    record_manager.create_schema()

    # 清空现有的向量数据库，准备重新索引
    print("\n正在清空现有案例向量库...")
    clear_vectorstore("criminal_cases")

    # 加载案例数据
    print(f"\n正在加载案例数据集: {config.CASE_DATASET_PATH}")
    loader = CaseLoader(
        file_path=config.CASE_DATASET_PATH,
        max_chars=config.CASE_MAX_CHARS,
        max_cases=max_cases
    )
    docs = loader.load()

    total_docs = len(docs)
    print(f"待索引案例数量: {total_docs}")

    if total_docs == 0:
        print("警告: 没有加载到任何案例！数据库现在是空的。")
        return

    # 分批写入配置
    BATCH_SIZE = 50

    total_info = {
        "num_added": 0, "num_updated": 0, "num_skipped": 0, "num_deleted": 0
    }

    num_batches = math.ceil(total_docs / BATCH_SIZE)
    print(f"\n开始写入向量数据库，共 {num_batches} 个批次，每批 {BATCH_SIZE} 条...")
    
    start_time = time.time()

    for i in range(0, total_docs, BATCH_SIZE):
        batch_docs = docs[i: i + BATCH_SIZE]
        current_batch_num = (i // BATCH_SIZE) + 1

        # 增加重试机制
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                print(f"   Processing batch [{current_batch_num}/{num_batches}] (Attempt {attempt + 1})...")

                # 尝试写入
                batch_info = case_index(batch_docs)

                vs = get_vectorstore("criminal_cases")
                if hasattr(vs, 'persist'):
                    vs.persist()

                # 如果成功，累加数据并跳出重试循环
                for key in total_info:
                    total_info[key] += batch_info.get(key, 0)
                break

            except Exception as e:
                print(f"   批次 [{current_batch_num}] 第 {attempt + 1} 次尝试失败: {e}")

                if attempt < max_retries - 1:
                    print(f"   等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    print(f"   批次 [{current_batch_num}] 最终失败，数据已丢失！")
    
    elapsed_time = time.time() - start_time

    print("\n" + "="*60)
    print("案例向量数据库初始化完成！")
    print("="*60)
    pprint.pprint(total_info)
    print(f"\n⏱ 总耗时: {elapsed_time/60:.1f} 分钟")
    print(f"⚡ 平均速度: {total_docs/elapsed_time:.1f} 条/秒")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="初始化案例向量数据库")
    parser.add_argument(
        "--max-cases", 
        type=int, 
        default=None,
        help="最大加载案例数（用于测试，默认全部加载）"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="测试模式，仅加载1000条案例"
    )
    
    args = parser.parse_args()
    
    max_cases = args.max_cases
    if args.test:
        max_cases = 1000
        print("⚠️ 测试模式：仅加载1000条案例")
    
    init_case_vectorstore(max_cases=max_cases)

