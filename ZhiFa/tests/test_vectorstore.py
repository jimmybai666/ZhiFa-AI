"""
测试向量数据库是否正常工作
- 法律向量库（law）是否有数据
- 案例向量库（criminal_cases）是否有数据
- RAG 检索是否能返回相关结果
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def test_law_vectorstore_exists():
    """验证法律向量库已初始化且有数据"""
    from src.vectorstore.utils import get_vectorstore

    vs = get_vectorstore("law")
    count = vs._collection.count()

    assert count > 0, f"法律向量库为空（count=0），请先运行 python scripts/init_law_vectorstore.py"
    print(f"✓ 法律向量库正常: {count} 条文档")


def test_case_vectorstore_exists():
    """验证案例向量库已初始化且有数据"""
    from src.vectorstore.utils import get_vectorstore

    vs = get_vectorstore("criminal_cases")
    count = vs._collection.count()

    assert count > 0, f"案例向量库为空（count=0），请先运行 python scripts/init_case_vectorstore.py"
    print(f"✓ 案例向量库正常: {count} 条文档")


def test_law_rag_retrieval():
    """测试法律向量库 RAG 检索 — 输入问题，验证能返回相关法条"""
    from src.vectorstore.utils import get_vectorstore

    vs = get_vectorstore("law")
    query = "故意伤害罪的量刑标准"
    results = vs.similarity_search(query, k=3)

    assert len(results) > 0, f"法律检索返回为空，query='{query}'"
    for i, doc in enumerate(results, 1):
        source = doc.metadata.get("source", "未知")
        preview = doc.page_content[:60].replace("\n", " ")
        print(f"  [{i}] 来源: {source}")
        print(f"      内容: {preview}...")
    print(f"✓ 法律 RAG 检索正常: 返回 {len(results)} 条结果")


def test_case_rag_retrieval():
    """测试案例向量库 RAG 检索 — 输入案情，验证能返回相似案例"""
    from src.vectorstore.utils import get_vectorstore

    vs = get_vectorstore("criminal_cases")
    query = "被告人持刀入室抢劫，造成被害人轻伤"
    results = vs.similarity_search(query, k=3)

    assert len(results) > 0, f"案例检索返回为空，query='{query}'"
    for i, doc in enumerate(results, 1):
        preview = doc.page_content[:80].replace("\n", " ")
        print(f"  [{i}] {preview}...")
    print(f"✓ 案例 RAG 检索正常: 返回 {len(results)} 条结果")


if __name__ == "__main__":
    print("=" * 50)
    print("向量数据库 & RAG 检索测试")
    print("=" * 50)

    print("\n[1] 法律向量库存在性检查")
    test_law_vectorstore_exists()

    print("\n[2] 案例向量库存在性检查")
    test_case_vectorstore_exists()

    print("\n[3] 法律 RAG 检索测试")
    test_law_rag_retrieval()

    print("\n[4] 案例 RAG 检索测试")
    test_case_rag_retrieval()

    print("\n" + "=" * 50)
    print("全部测试通过")
    print("=" * 50)
