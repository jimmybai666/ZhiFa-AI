"""
案情预测模块 - 批量推理接口

标准化输入格式:
{
    "query_fact": "案情描述文本",
    "task_type": "imprisonment" | "accusation" | "analysis",  // 预测任务类型
    "accusations": ["罪名"]  // 仅 imprisonment 时可选
}

标准化输出格式 (imprisonment):
{
    "task_type": "imprisonment",
    "predicted_imprisonment": 36,
    "structured_prediction": {...},
    "similar_cases_count": 10,
    "case_statistics": {"avg": 30, "min": 12, "max": 60, "count": 10},
    "ai_response": "分析文本",
    "law_context": "相关法条"
}

标准化输出格式 (accusation):
{
    "task_type": "accusation",
    "accusation_distribution": {"盗窃": 5, "抢劫": 3},
    "ai_response": "分析文本",
    "similar_cases_count": 10,
    "law_context": "相关法条"
}

标准化输出格式 (analysis):
{
    "task_type": "analysis",
    "predicted_accusation": "盗窃",
    "case_statistics": {"min": 12, "max": 36},
    "ai_response": "分析文本",
    "similar_cases_count": 10,
    "law_context": "相关法条"
}
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from .base import BaseBatchInference


VALID_TASK_TYPES = {"imprisonment", "accusation", "analysis"}


class BatchCasePrediction(BaseBatchInference):
    """案情预测批量推理"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chain = None

    @property
    def module_name(self) -> str:
        return "case_prediction"

    def _get_chain(self):
        """懒加载案情预测链"""
        if self._chain is None:
            from src.config.config import config
            from src.chain.case_prediction import get_case_prediction_chain
            print(f"  [case_prediction] 正在初始化案情预测链...")
            self._chain = get_case_prediction_chain(config)
            print(f"  [case_prediction] 案情预测链初始化完成")
        return self._chain

    def validate_input(self, item: Dict[str, Any]) -> bool:
        """校验输入格式"""
        if not isinstance(item, dict):
            return False
        query_fact = item.get("query_fact", "")
        if not query_fact or not isinstance(query_fact, str):
            return False
        if len(query_fact.strip()) < 10:
            return False
        task_type = item.get("task_type", "imprisonment")
        if task_type not in VALID_TASK_TYPES:
            return False
        return True

    def _infer_single(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """单条案情预测推理"""
        chain = self._get_chain()
        query_fact = item["query_fact"].strip()
        task_type = item.get("task_type", "imprisonment")
        accusations = item.get("accusations", None)

        if task_type == "imprisonment":
            result = chain.predict_imprisonment(query_fact, accusations)
            return {
                "task_type": "imprisonment",
                "predicted_imprisonment": result.get("predicted_imprisonment"),
                "structured_prediction": result.get("structured_prediction"),
                "similar_cases_count": result.get("similar_cases_count", 0),
                "case_statistics": result.get("case_statistics", {}),
                "ai_response": result.get("ai_response", ""),
                "law_context": result.get("law_context", ""),
            }

        elif task_type == "accusation":
            result = chain.predict_accusation(query_fact)
            return {
                "task_type": "accusation",
                "accusation_distribution": result.get("accusation_distribution", {}),
                "ai_response": result.get("ai_response", ""),
                "similar_cases_count": result.get("similar_cases_count", 0),
                "law_context": result.get("law_context", ""),
            }

        elif task_type == "analysis":
            result = chain.analyze_case(query_fact)
            return {
                "task_type": "analysis",
                "predicted_accusation": result.get("predicted_accusation", ""),
                "case_statistics": result.get("case_statistics", {}),
                "ai_response": result.get("ai_response", ""),
                "similar_cases_count": result.get("similar_cases_count", 0),
                "law_context": result.get("law_context", ""),
            }

        else:
            raise ValueError(f"不支持的任务类型: {task_type}")
