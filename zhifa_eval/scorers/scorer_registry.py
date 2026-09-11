"""
评分器注册表：任务 → 评分策略映射
"""
from typing import Any, Callable, Dict, List

from .objective.metrics import METRIC_FUNCTIONS


def get_scorer_for_task(task_id: str, metrics: List[str]):
    """返回该任务对应的评分函数列表"""
    scorers = []
    for metric_name in metrics:
        fn = METRIC_FUNCTIONS.get(metric_name)
        if fn:
            scorers.append((metric_name, fn))
    return scorers


def score_single(
    task_id: str,
    metrics: List[str],
    prediction: str,
    reference: str,
    **kwargs,
) -> Dict[str, float]:
    """对单条样本执行所有客观评分"""
    results = {}
    for metric_name, fn in get_scorer_for_task(task_id, metrics):
        result = fn(prediction, reference, **kwargs)
        results.update(result)
    return results
