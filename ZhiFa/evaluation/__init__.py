"""
智法AI 评测模块

提供三大功能模块的批量推理接口，支持：
- 标准化 JSON 输入/输出
- 批量脚本化调用
- 自动重试与容错
- 进度追踪与日志
"""

from .batch_legal_qa import BatchLegalQA
from .batch_contract_review import BatchContractReview
from .batch_case_prediction import BatchCasePrediction
from .batch_runner import BatchRunner

__all__ = [
    "BatchLegalQA",
    "BatchContractReview",
    "BatchCasePrediction",
    "BatchRunner",
]
