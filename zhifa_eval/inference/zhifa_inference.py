"""
ZhiFa AI inference bridge.

Bridges the ZhiFa project's RAG chains into the eval platform.
"""
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseInference
from ..config import ZHIFA_PROJECT_PATH


class ZhiFaInference(BaseInference):
    """Call ZhiFa AI RAG chains for inference."""

    def __init__(self):
        self._qa_chain = None
        self._contract_chain = None
        self._case_chain = None
        self._setup_path()

    @property
    def name(self) -> str:
        return "ZhiFa-AI (RAG)"

    def _setup_path(self):
        p = str(ZHIFA_PROJECT_PATH)
        if p not in sys.path:
            sys.path.insert(0, p)

    def _get_qa_chain(self):
        if self._qa_chain is None:
            from src.config.config import config
            from src.chain.legal_question_answering import get_law_chain
            self._qa_chain = get_law_chain(config)
        return self._qa_chain

    def _get_contract_chain(self):
        if self._contract_chain is None:
            from src.config.config import config
            from src.chain.contract_review import get_contract_review_chain
            self._contract_chain = get_contract_review_chain(config)
        return self._contract_chain

    def _get_case_chain(self):
        if self._case_chain is None:
            from src.config.config import config
            from src.chain.case_prediction import get_case_prediction_chain
            self._case_chain = get_case_prediction_chain(config)
        return self._case_chain

    def infer(self, instruction: str, question: str, **kwargs) -> str:
        module = kwargs.get("module", "legal_qa")
        task_id = kwargs.get("task_id", "")

        if module == "legal_qa" or task_id.startswith("legal_qa"):
            return self._infer_qa(question, kwargs.get("history", []))
        elif module == "contract_review" or task_id.startswith("contract_review"):
            contract_text = kwargs.get("contract_text", question)
            return self._infer_contract(contract_text)
        elif module == "case_prediction" or task_id.startswith("case_prediction"):
            return self._infer_case(question, task_id)
        else:
            return self._infer_qa(question)

    def _infer_qa(self, question: str, history: list = None) -> str:
        chain_bundle = self._get_qa_chain()
        full_chain = chain_bundle["full_chain"]
        result = full_chain.invoke({
            "question": question,
            "history": history or [],
        })
        return result.get("answer", "")

    def _infer_contract(self, contract_text: str) -> str:
        chain = self._get_contract_chain()
        result = chain.invoke({"contract_text": contract_text})
        # Flatten clauses analysis into text
        clauses = result.get("clauses_analysis", [])
        parts = []
        for c in clauses:
            risk = c.get("risk_level", "")
            if "高" in risk or "中" in risk:
                parts.append(
                    f"条款: {c.get('clause_text', '')[:80]}\n"
                    f"风险: {risk}\n"
                    f"分析: {c.get('analysis', '')}\n"
                    f"修改建议: {c.get('revised_text', '')}"
                )
        return "\n\n".join(parts) if parts else str(result)

    def _infer_case(self, question: str, task_id: str) -> str:
        chain = self._get_case_chain()
        if "comprehensive" in task_id or "analysis" in task_id:
            result = chain.analyze_case(question)
            return result.get("ai_response", str(result))
        elif "prison" in task_id or "imprisonment" in task_id:
            result = chain.predict_imprisonment(question)
            return result.get("ai_response", str(result))
        elif "clause" in task_id or "accusation" in task_id:
            result = chain.predict_accusation(question)
            return result.get("ai_response", str(result))
        else:
            result = chain.analyze_case(question)
            return result.get("ai_response", str(result))
