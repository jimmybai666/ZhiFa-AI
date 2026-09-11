"""
通用 OpenAI 兼容 API 推理

适用于裸模型对比测试、LLM-as-Judge 评分调用。
"""
from openai import OpenAI
from typing import Any, Dict, Optional

from .base import BaseInference


class OpenAIInference(BaseInference):
    """OpenAI 兼容 API 推理"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        display_name: Optional[str] = None,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._name = display_name or model

    @property
    def name(self) -> str:
        return self._name

    def infer(self, instruction: str, question: str, **kwargs) -> str:
        messages = []
        if instruction:
            messages.append({"role": "system", "content": instruction})
        messages.append({"role": "user", "content": question})

        for attempt in range(2):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content or ""
            finish = response.choices[0].finish_reason
            if content or finish == "stop":
                return content
            # finish_reason=length + empty content: 某些代理的截断行为，加大 max_tokens 重试
            if attempt == 0 and finish == "length":
                self.max_tokens = min(self.max_tokens * 2, 32768)
        return content
