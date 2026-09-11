"""
合同审查适配器 — 3 个 contract_review 子任务

智法AI接口：BatchContractReview._infer_single({"contract_text": str})
  → {"clauses_analysis": [...], "summary_report": str, "risk_statistics": {...}}

子任务映射：
  - clause_correction：输入单条条款 → 输出修正后条款
  - risk_detection：输入合同全文 → 输出风险分析文本
  - risk_revision：输入合同全文 → 输出修订建议文本
"""
from typing import Any, Dict


CONTRACT_TASKS = {
    "contract_review.clause_correction",
    "contract_review.risk_detection",
    "contract_review.risk_revision",
}


class ContractReviewAdapter:
    """合同审查适配器"""

    def get_zhifa_module(self) -> str:
        return "contract_review"

    def to_zhifa_input(self, task_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
        if task_id == "contract_review.clause_correction":
            # clause_correction：item["question"] 是一条需要纠错的条款
            clause_text = item.get("question", "")
            return {"contract_text": clause_text}

        elif task_id in ("contract_review.risk_detection", "contract_review.risk_revision"):
            # risk_detection / risk_revision：item["_contract_text"] 是合同全文
            contract_text = item.get("_contract_text", "")
            return {"contract_text": contract_text}

        raise ValueError(f"未知的合同审查任务: {task_id}")


    def from_zhifa_output(self, task_id: str, zhifa_result: Dict[str, Any],
                          item: Dict[str, Any]) -> str:
        if task_id == "contract_review.clause_correction":
            return self._extract_clause_correction(zhifa_result)

        elif task_id == "contract_review.risk_detection":
            return self._extract_risk_detection(zhifa_result)

        elif task_id == "contract_review.risk_revision":
            return self._extract_risk_revision(zhifa_result)

        return zhifa_result.get("summary_report", "")

    def _extract_clause_correction(self, result: Dict) -> str:
        """从审查结果中提取修正后的条款文本"""
        answer = result.get("answer", "")
        if answer and "clauses_analysis" not in result:
            return answer.strip()

        clauses = result.get("clauses_analysis", [])
        parts = []
        for c in clauses:
            revised = c.get("revised_text", "")
            if revised:
                parts.append(revised)
        if parts:
            return "\n".join(parts)
        return result.get("summary_report", "") or answer


    def _extract_risk_detection(self, result: Dict) -> str:
        """从审查结果中提取风险识别文本
        拼接所有有风险的条款分析，格式化为 LLM-as-Judge 可评判的文本
        """
        clauses = result.get("clauses_analysis", [])
        parts = []
        for c in clauses:
            risk_level = c.get("risk_level", "")
            # 只提取有风险的条款
            if "无" in risk_level or "安全" in risk_level:
                continue
            clause_num = c.get("clause_number", "")
            theme = c.get("theme", "")
            section = c.get("section", "")
            analysis = c.get("analysis", "")
            clause_text = c.get("clause_text", "")
            evidence = c.get("evidence", [])

            part = f"### 风险条款：{section} {clause_num} {theme}\n"
            part += f"风险等级：{risk_level}\n"
            part += f"条款原文：{clause_text[:200]}\n"
            part += f"风险分析：{analysis}\n"
            if evidence:
                laws = "; ".join(e.get("content", "")[:100] for e in evidence[:3])
                part += f"法律依据：{laws}\n"
            parts.append(part)

        if parts:
            return "\n".join(parts)
        return result.get("summary_report", "未发现明显风险")

    def _extract_risk_revision(self, result: Dict) -> str:
        """拼接所有条款的 revised_text，输出一份完整的修订后合同"""
        clauses = result.get("clauses_analysis", [])
        parts = []
        for c in clauses:
            revised = c.get("revised_text", "")
            if revised:
                parts.append(revised)
            else:
                original = c.get("clause_text", "")
                if original:
                    parts.append(original)
        if parts:
            return "\n\n".join(parts)
        return result.get("summary_report", "未发现需修订条款")
