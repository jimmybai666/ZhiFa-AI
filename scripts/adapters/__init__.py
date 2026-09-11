"""
适配器基类：定义 LegalEval ↔ 智法AI 的输入输出转换接口
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAdapter(ABC):
    """LegalEval 子任务 → 智法AI 的适配器基类"""

    @abstractmethod
    def to_zhifa_input(self, task_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """把 LegalEval 数据转为智法AI的输入格式"""
        ...

    @abstractmethod
    def from_zhifa_output(self, task_id: str, zhifa_result: Dict[str, Any], item: Dict[str, Any]) -> str:
        """把智法AI的输出转为 LegalEval 的答案字符串"""
        ...

    def get_zhifa_module(self) -> str:
        """返回对应的智法AI模块名"""
        ...
