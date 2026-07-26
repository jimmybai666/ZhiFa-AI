"""
初始化法律向量数据库

功能说明：
1. 创建记录管理器的数据库表结构
2. 清空现有的向量数据库
3. 从Law-Book目录加载所有法律文档（.md文件）
4. 使用LawSplitter按条款和标题分割文档
5. 将分割后的文档转换为向量并存储到Chroma数据库
6. 打印索引统计信息（新增、更新、删除的文档数量）

运行方式：
    python scripts/init_law_vectorstore.py
"""
import os
import sys
import pprint
import math
import time
from dotenv import load_dotenv

# ==========================================
# 强制定位到项目根目录
# ==========================================
current_file_path = os.path.abspath(__file__)
# 获取项目根目录 (从 law_rag/scripts/init_law_vectorstore.py 回退一级到 law_rag/)
project_root = os.path.dirname(os.path.dirname(current_file_path))
os.chdir(project_root)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"工作目录已锁定: {os.getcwd()}")

# 导入必须在路径设置之后
from src.vectorstore.loader import LawLoader
from src.vectorstore.splitter import LawSplitter
from src.vectorstore.utils import law_index, clear_vectorstore, get_record_manager, get_vectorstore
from src.config.config import config

load_dotenv()

def init_vectorstore() -> None:

    # 获取记录管理器，用于跟踪哪些文档已被索引
    record_manager = get_record_manager("law")
    # 创建数据库表结构
    record_manager.create_schema()

    # 清空现有的向量数据库，准备重新索引
    clear_vectorstore("law")

    # 创建文本分割器，使用tiktoken编码器计算token数
    # chunk_size: 每个文档块的最大token数
    # chunk_overlap: 相邻文档块之间的重叠token数，确保上下文连贯性
    text_splitter = LawSplitter.from_tiktoken_encoder(
        chunk_size=config.LAW_BOOK_CHUNK_SIZE, chunk_overlap=config.LAW_BOOK_CHUNK_OVERLAP
    )
    # 加载法律文档并使用分割器分割成小块
    docs = LawLoader(config.LAW_BOOK_PATH).load_and_split(text_splitter=text_splitter)

    # # ==========================================
    # # 【测试模式】只取前 400 条数据进行快速测试
    # # 验证通过后，请注释掉或删除下面这行代码以运行全量数据
    # print("⚠️⚠️⚠️ 当前处于测试模式，仅处理前 400 条文档！ ⚠️⚠️⚠️")
    # docs = docs[:400]
    # # ==========================================

    total_docs = len(docs)
    print(f" 加载到的文档块数量: {total_docs}")

    if total_docs == 0:
        print("警告: 没有加载到任何文档！数据库现在是空的。")
        print("请检查目录下是否有 .md 文件，或者 LawLoader 的过滤规则。")
        return

    # 3. 分批写入配置
    BATCH_SIZE = 50

    total_info = {
        "num_added": 0, "num_updated": 0, "num_skipped": 0, "num_deleted": 0
    }

    num_batches = math.ceil(total_docs / BATCH_SIZE)
    print(f"开始写入向量数据库，共 {num_batches} 个批次，每批 {BATCH_SIZE} 条...")

    for i in range(0, total_docs, BATCH_SIZE):
        batch_docs = docs[i: i + BATCH_SIZE]
        current_batch_num = (i // BATCH_SIZE) + 1

        # ==========================================
        # 【修改 2】增加重试机制
        # ==========================================
        max_retries = 3  # 最大重试次数
        retry_delay = 5  # 重试等待秒数

        for attempt in range(max_retries):
            try:
                print(f"   Processing batch [{current_batch_num}/{num_batches}] (Attempt {attempt + 1})...")

                # 尝试写入
                batch_info = law_index(batch_docs)

                vs = get_vectorstore("law")
                if hasattr(vs, 'persist'):
                    vs.persist()

                # 如果成功，累加数据并跳出重试循环
                for key in total_info:
                    total_info[key] += batch_info.get(key, 0)
                break  # 成功了，跳出 attempt 循环，继续下一个 batch

            except Exception as e:
                print(f"   批次 [{current_batch_num}] 第 {attempt + 1} 次尝试失败: {e}")

                if attempt < max_retries - 1:
                    print(f"   等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    print(f"   批次 [{current_batch_num}] 最终失败，数据已丢失！")
                    # 这里可以选择是否抛出异常终止整个程序
                    # raise e

    print("\n 所有批次处理完成")
    pprint.pprint(total_info)


if __name__ == "__main__":
    init_vectorstore()
