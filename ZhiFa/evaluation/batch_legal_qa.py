"""
法律问答模块 - 批量推理接口

标准化输入格式:
{
    "question": "法律问题文本",
    "history": [{"role": "user/assistant", "content": "..."}]  // 可选
}

标准化输出格式:
{
    "answer": "AI回答文本",
    "sources": [{"title": "...", "content": "...", "chapter": "...", "url": "..."}],
    "law_context": "检索到的法律条文",
    "web_context": "检索到的网页信息"
}
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

# 确保可以导入项目模块
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from .base import BaseBatchInference


class BatchLegalQA(BaseBatchInference):
    """法律问答批量推理"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chain_bundle = None

    @property
    def module_name(self) -> str:
        return "legal_qa"

    def _get_chain(self):
        """懒加载法律问答链"""
        if self._chain_bundle is None:
            from src.config.config import config
            from src.chain.legal_question_answering import get_law_chain
            print(f"  [legal_qa] 正在初始化法律问答链...")
            self._chain_bundle = get_law_chain(config)
            print(f"  [legal_qa] 法律问答链初始化完成")
        return self._chain_bundle

    def validate_input(self, item: Dict[str, Any]) -> bool:
        """校验输入格式"""
        if not isinstance(item, dict):
            return False
        question = item.get("question", "")
        if not question or not isinstance(question, str):
            return False
        if len(question.strip()) == 0:
            return False
        # history 可选，但如果存在必须是列表
        history = item.get("history")
        if history is not None and not isinstance(history, list):
            return False
        return True

    def _infer_single(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """单条法律问答推理"""
        chain_bundle = self._get_chain()
        full_chain = chain_bundle["full_chain"]

        question = item["question"].strip()
        history = item.get("history", [])

        # 调用法律问答链
        result = full_chain.invoke({
            "question": question,
            "history": history,
        })

        # 提取答案
        answer = result.get("answer", "")

        # 格式化来源
        sources = []
        if result.get("law_docs_formatted"):
            for doc in result["law_docs_formatted"][:5]:
                sources.append({
                    "type": "law",
                    "title": doc.get("source", "法律条文"),
                    "chapter": doc.get("chapter", ""),
                    "content": doc.get("content", "")[:300],
                })
        if result.get("web_docs_formatted"):
            for doc in result["web_docs_formatted"][:3]:
                sources.append({
                    "type": "web",
                    "title": doc.get("title", "网页来源"),
                    "url": doc.get("url", ""),
                    "content": doc.get("content", "")[:300],
                })

        return {
            "answer": answer,
            "sources": sources,
            "law_context": result.get("law_context", ""),
            "web_context": result.get("web_context", ""),
        }
