"""
测试法律问答（Legal QA）完整路径
- chain 能否正常创建
- 端到端调用能否返回答案
"""
import os
import sys
import warnings

warnings.filterwarnings('ignore')
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def test_law_chain_creation():
    """验证法律问答 chain 能正常创建"""
    from src.config.config import config
    from src.chain.legal_question_answering import get_law_chain

    chain = get_law_chain(config)
    assert chain is not None, "get_law_chain 返回 None"
    print("✓ 法律问答 chain 创建成功")
    return chain


def test_law_chain_invoke(chain=None):
    """端到端测试：输入问题，验证能返回完整答案"""
    if chain is None:
        from src.config.config import config
        from src.chain.legal_question_answering import get_law_chain
        chain = get_law_chain(config)

    question = "故意伤害罪的构成要件是什么？"
    print(f"  问题: {question}")
    print("  正在调用（涉及向量检索 + 网页搜索 + LLM 生成，请耐心等待）...")

    result = chain.invoke({"question": question, "history": []})

    assert "answer" in result, f"返回结果中没有 answer 字段，keys={list(result.keys())}"
    assert result["answer"], "answer 为空字符串"

    print(f"\n  [答案] (前200字):")
    print(f"  {result['answer'][:200]}...")

    print(f"\n  [法律上下文] 长度: {len(result.get('law_context', ''))} 字符")
    print(f"  [网页上下文] 长度: {len(result.get('web_context', ''))} 字符")

    if result.get("law_docs_formatted"):
        print(f"  [法律来源] 前100字: {result['law_docs_formatted'][:100]}...")

    print("\n✓ 法律问答端到端测试通过")


def test_law_chain_with_history(chain=None):
    """测试多轮对话：带历史记录的问答"""
    if chain is None:
        from src.config.config import config
        from src.chain.legal_question_answering import get_law_chain
        chain = get_law_chain(config)

    history = [
        {"role": "user", "content": "什么是故意伤害罪？"},
        {"role": "assistant", "content": "故意伤害罪是指故意非法损害他人身体健康的行为。"}
    ]
    question = "那它的量刑标准呢？"

    print(f"  历史: {history[0]['content']} -> ...")
    print(f"  追问: {question}")
    print("  正在调用...")

    result = chain.invoke({"question": question, "history": history})

    assert result["answer"], "多轮对话 answer 为空"
    print(f"\n  [答案] (前200字):")
    print(f"  {result['answer'][:200]}...")
    print("\n✓ 多轮对话测试通过")


if __name__ == "__main__":
    print("=" * 50)
    print("法律问答 (Legal QA) 端到端测试")
    print("=" * 50)

    print("\n[1] Chain 创建测试")
    chain = test_law_chain_creation()

    print("\n[2] 单轮问答测试")
    test_law_chain_invoke(chain)

    print("\n[3] 多轮对话测试")
    test_law_chain_with_history(chain)

    print("\n" + "=" * 50)
    print("全部测试通过")
    print("=" * 50)
