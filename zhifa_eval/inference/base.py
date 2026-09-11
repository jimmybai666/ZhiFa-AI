"""
推理接口抽象基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseInference(ABC):
    """推理接口"""

    @abstractmethod
    def infer(self, instruction: str, question: str, **kwargs) -> str:
        """
        执行单条推理，返回模型的纯文本回答。

        Args:
            instruction: 系统指令 / system prompt
            question: 用户问题
            **kwargs: 额外参数（如 contract_text, history 等）

        Returns:
            模型回答文本
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """推理源名称，用于结果标注"""
        ...
