"""
合同审查模块 - 批量推理接口

标准化输入格式:
{
    "contract_text": "合同全文文本",
    "contract_id": "合同标识（可选，用于追踪）"
}

标准化输出格式:
{
    "clauses_analysis": [
        {
            "clause_number": "条款编号",
            "clause_text": "条款原文",
            "theme": "主题",
            "risk_level": "风险等级（高风险/中风险/低风险/无风险）",
            "analysis": "分析结果",
            "revised_text": "修改建议文本",
            "evidence": [{"content": "...", "source": "..."}]
        }
    ],
    "summary_report": "整体审查报告",
    "total_clauses": 10,
    "risk_statistics": {"high": 2, "medium": 3, "low": 1, "none": 4}
}
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from .base import BaseBatchInference


class BatchContractReview(BaseBatchInference):
    """合同审查批量推理"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chain = None

    @property
    def module_name(self) -> str:
        return "contract_review"

    def _get_chain(self):
        """懒加载合同审查链"""
        if self._chain is None:
            from src.config.config import config
            from src.chain.contract_review import get_contract_review_chain
            print(f"  [contract_review] 正在初始化合同审查链...")
            self._chain = get_contract_review_chain(config)
            print(f"  [contract_review] 合同审查链初始化完成")
        return self._chain

    def validate_input(self, item: Dict[str, Any]) -> bool:
        """校验输入格式"""
        if not isinstance(item, dict):
            return False
        contract_text = item.get("contract_text", "")
        if not contract_text or not isinstance(contract_text, str):
            return False
        if len(contract_text.strip()) < 10:
            return False
        return True

    def _infer_single(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """单条合同审查推理"""
        chain = self._get_chain()
        contract_text = item["contract_text"].strip()

        # 调用合同审查链
        result = chain.invoke({"contract_text": contract_text})

        clauses_analysis = result.get("clauses_analysis", [])
        summary_report = result.get("summary_report", "")
        total_clauses = result.get("total_clauses", 0)

        # 统计风险分布
        risk_stats = {"high": 0, "medium": 0, "low": 0, "none": 0, "unknown": 0}
        for clause in clauses_analysis:
            risk = clause.get("risk_level", "")
            if "高" in risk:
                risk_stats["high"] += 1
            elif "中" in risk:
                risk_stats["medium"] += 1
            elif "低" in risk:
                risk_stats["low"] += 1
            elif "无" in risk or "安全" in risk:
                risk_stats["none"] += 1
            else:
                risk_stats["unknown"] += 1

        # 标准化输出（只保留评测需要的字段）
        standardized_clauses = []
        for clause in clauses_analysis:
            standardized_clauses.append({
                "clause_number": clause.get("clause_number", ""),
                "clause_text": clause.get("clause_text", ""),
                "theme": clause.get("theme", ""),
                "section": clause.get("section", ""),
                "risk_level": clause.get("risk_level", ""),
                "analysis": clause.get("analysis", ""),
                "revised_text": clause.get("revised_text", ""),
                "evidence": clause.get("evidence", []),
            })

        return {
            "clauses_analysis": standardized_clauses,
            "summary_report": summary_report,
            "total_clauses": total_clauses,
            "risk_statistics": risk_stats,
        }
