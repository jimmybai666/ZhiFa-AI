"""
案情预测适配器 — 4 个 case_prediction 子任务

智法AI接口：BatchCasePrediction._infer_single({"query_fact": str, "task_type": str})
  → 不同 task_type 返回不同结构

子任务映射：
  - article_prediction → task_type="accusation" → 从输出提取法条编号
  - clause_prediction → task_type="accusation" → 从输出提取罪名
  - prison_term_prediction → task_type="imprisonment" → 从输出提取刑期月数
  - comprehensive_judgment_prediction → task_type="analysis" → ai_response 直接用

智法AI输出格式（已在 case_prediction_prompt.py 中定义）：
  - imprisonment: "预测刑期：36个月" / "罪名：[罪名]"
  - accusation: "主要罪名：[罪名]" / "法律依据：[法条]"
  - analysis: 自由文本（罪名分析+量刑+刑期+辩护建议）

LegalEval 评分器期望格式：
  - article_prediction: "[法条]刑法第128条、刑法第341条<eoa>"
  - clause_prediction: "[罪名]盗窃;诈骗<eoa>"
  - prison_term_prediction: "[刑期]36月<eoa>"
  - comprehensive_judgment_prediction: 自由文本（Rubric 评分）
"""
import re
from typing import Any, Dict, List


CASE_PREDICTION_TASKS = {
    "case_prediction.article_prediction",
    "case_prediction.clause_prediction",
    "case_prediction.prison_term_prediction",
    "case_prediction.comprehensive_judgment_prediction",
}

# task_id → 智法AI的 task_type
TASK_TYPE_MAP = {
    "case_prediction.article_prediction": "accusation",
    "case_prediction.clause_prediction": "accusation",
    "case_prediction.prison_term_prediction": "imprisonment",
    "case_prediction.comprehensive_judgment_prediction": "analysis",
}


class CasePredictionAdapter:
    """案情预测适配器"""

    def get_zhifa_module(self) -> str:
        return "case_prediction"

    def to_zhifa_input(self, task_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
        question = item.get("question", "")
        task_type = TASK_TYPE_MAP.get(task_id, "analysis")

        result = {"query_fact": question, "task_type": task_type}

        # prison_term_prediction 的 question 里可能包含罪名信息，提取出来
        if task_type == "imprisonment":
            accusations = self._extract_accusations_from_question(question)
            if accusations:
                result["accusations"] = accusations

        return result

    def from_zhifa_output(self, task_id: str, zhifa_result: Dict[str, Any],
                          item: Dict[str, Any]) -> str:
        if task_id == "case_prediction.article_prediction":
            return self._format_article_prediction(zhifa_result)

        elif task_id == "case_prediction.clause_prediction":
            return self._format_clause_prediction(zhifa_result)

        elif task_id == "case_prediction.prison_term_prediction":
            return self._format_prison_term(zhifa_result)

        elif task_id == "case_prediction.comprehensive_judgment_prediction":
            # Rubric 评分，直接用 ai_response
            return zhifa_result.get("ai_response", "")

        return zhifa_result.get("ai_response", "")

    # ─── 输出格式转换 ─────────────────────────────────

    def _format_article_prediction(self, result: Dict) -> str:
        """从智法AI输出中提取法条编号，转为 [法条]刑法第X条<eoa> 格式"""
        ai_response = result.get("ai_response", "")

        # 从 "法律依据：刑法第264条" 或 "法条：第264条" 等提取
        articles = re.findall(r'(?:刑法)?第(\d+)条', ai_response)
        if not articles:
            # fallback: 从 law_context 提取
            law_ctx = result.get("law_context", "")
            articles = re.findall(r'第(\d+)条', law_ctx)

        if articles:
            # 去重保序
            seen = set()
            unique = []
            for a in articles:
                if a not in seen:
                    seen.add(a)
                    unique.append(a)
            formatted = "、".join(f"刑法第{a}条" for a in unique)
            return f"[法条]{formatted}<eoa>"

        return ai_response

    def _format_clause_prediction(self, result: Dict) -> str:
        """从智法AI输出中提取罪名，转为 [罪名]盗窃;诈骗<eoa> 格式"""
        # 优先从 accusation_distribution 提取
        dist = result.get("accusation_distribution", {})
        if dist:
            crimes = list(dist.keys())
            return f"[罪名]{';'.join(crimes)}<eoa>"

        # fallback: 从 ai_response 提取
        ai_response = result.get("ai_response", "")
        # "主要罪名：盗窃" 或 "罪名：非法持有毒品罪"
        m = re.search(r'(?:主要)?罪名[：:]\s*(.+?)(?:\n|$)', ai_response)
        if m:
            crime_text = m.group(1).strip()
            # 去掉"罪"后缀的处理由评分器做，这里保留原文
            crimes = re.split(r'[;；、,，和与及]', crime_text)
            crimes = [c.strip() for c in crimes if c.strip()]
            if crimes:
                return f"[罪名]{';'.join(crimes)}<eoa>"

        return result.get("ai_response", "")

    def _format_prison_term(self, result: Dict) -> str:
        """从智法AI输出中提取刑期，转为 [刑期]36月<eoa> 格式"""
        # 优先从 structured_prediction 提取
        pred = result.get("structured_prediction", {})
        if pred:
            months = pred.get("predicted_imprisonment")
            if months is not None:
                return f"[刑期]{int(months)}月<eoa>"

        # 优先从 predicted_imprisonment 提取
        pi = result.get("predicted_imprisonment")
        if pi is not None:
            return f"[刑期]{int(pi)}月<eoa>"

        # fallback: 从 ai_response 文本提取
        ai_response = result.get("ai_response", "")
        # "预测刑期：36个月" 或 "预测刑期：3年"
        m = re.search(r'预测刑期[：:]\s*(\d+)\s*个?月', ai_response)
        if m:
            return f"[刑期]{m.group(1)}月<eoa>"

        m = re.search(r'预测刑期[：:]\s*(\d+)\s*年', ai_response)
        if m:
            months = int(m.group(1)) * 12
            return f"[刑期]{months}月<eoa>"

        # "有期徒刑X年X个月"
        m = re.search(r'(\d+)\s*年\s*(\d+)\s*个?月', ai_response)
        if m:
            months = int(m.group(1)) * 12 + int(m.group(2))
            return f"[刑期]{months}月<eoa>"

        m = re.search(r'(\d+)\s*个?月', ai_response)
        if m:
            return f"[刑期]{m.group(1)}月<eoa>"

        return f"[刑期]未能提取<eoa>"

    # ─── 辅助 ─────────────────────────────────────────

    @staticmethod
    def _extract_accusations_from_question(question: str) -> List[str]:
        """从 prison_term_prediction 的 question 中提取已知罪名
        格式通常为：...罪名：危险驾驶。法条:...
        """
        m = re.search(r'罪名[：:]\s*(.+?)(?:[。\n]|法条|$)', question)
        if m:
            crime_text = m.group(1).strip()
            crimes = re.split(r'[;；、,，]', crime_text)
            return [c.strip() for c in crimes if c.strip()]
        return []
