"""
测试混元 Hy3 模型调用是否正常
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def test_config_uses_hunyuan():
    """验证配置文件读取的是混元模型"""
    from src.config.config import Config

    assert "hy3" in Config.get_llm_model(), f"LLM 模型不是 hy3: {Config.get_llm_model()}"
    assert "hunyuan" in Config.get_embedding_model() or "hy3" in Config.get_embedding_model(), \
        f"Embedding 模型不是混元: {Config.get_embedding_model()}"
    assert Config.get_api_key(), "API Key 未配置"
    print(f"✓ 配置正确: LLM={Config.get_llm_model()}, Embedding={Config.get_embedding_model()}")


def test_llm_call():
    """测试 LLM 对话调用"""
    from src.core.model_factory import get_model

    model = get_model(streaming=False)
    resp = model.invoke("你好，请用一句话介绍你是什么模型")

    assert resp.content, "LLM 返回为空"
    print(f"✓ LLM 调用成功: {resp.content[:80]}")


def test_embedding_call():
    """测试 Embedding 向量生成"""
    from src.vectorstore.utils import get_cached_embedder

    embedder = get_cached_embedder()
    vec = embedder.embed_query("中华人民共和国刑法")

    assert isinstance(vec, list), f"返回类型错误: {type(vec)}"
    assert len(vec) > 0, "向量维度为 0"
    print(f"✓ Embedding 调用成功: 向量维度={len(vec)}")


if __name__ == "__main__":
    print("=" * 50)
    print("混元 Hy3 API 调用测试")
    print("=" * 50)

    test_config_uses_hunyuan()
    print()
    test_llm_call()
    print()
    test_embedding_call()

    print()
    print("=" * 50)
    print("全部测试通过")
    print("=" * 50)
