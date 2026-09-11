from langchain_core.callbacks import Callbacks
from langchain_openai import ChatOpenAI

from ..config.config import Config


def get_model(
        model: str = None,
        streaming: bool = False,
        callbacks: Callbacks = None,
        temperature: float = None,
        max_tokens: int = None,
        base_url: str = None) -> ChatOpenAI:
    if model is None:
        model = Config.get_llm_model()

    if temperature is None:
        temperature = Config.get_temperature()

    if max_tokens is None:
        max_tokens = Config.get_max_tokens()

    if base_url is None:
        base_url = Config.DEFAULT_BASE_URL

    api_key = Config.get_api_key()

    print(f"[模型配置] 使用模型: {model}, 温度: {temperature}, 最大输出Token: {max_tokens}")

    llm = ChatOpenAI(
        model=model,
        streaming=streaming,
        callbacks=callbacks,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=base_url,
    )
    return llm
