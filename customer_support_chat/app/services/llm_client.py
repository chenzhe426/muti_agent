"""
LLM 客户端工厂
支持多种模型服务：OpenAI / vLLM / Ollama / TGI
"""
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from customer_support_chat.app.core.settings import get_settings

settings = get_settings()


def create_llm(
    model: Optional[str] = None,
    temperature: float = 1.0,
    **kwargs
) -> ChatOpenAI:
    """
    工厂函数：根据配置创建 LLM 客户端

    支持的 provider:
    - "openai": OpenAI API (默认)
    - "vllm": vLLM 服务 (OpenAI 兼容)
    - "ollama": Ollama 本地模型
    - "tgi": Hugging Face TGI 服务
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "ollama":
        # Ollama 客户端
        return ChatOllama(
            model=model or settings.LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature,
            **kwargs
        )
    else:
        # OpenAI 兼容接口 (OpenAI / vLLM / TGI / LocalAI)
        # 都使用 ChatOpenAI，通过 base_url 区分
        return ChatOpenAI(
            model=model or settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
            api_key=settings.OPENAI_API_KEY or "dummy",  # 本地服务可能不需要 key
            temperature=temperature,
            **kwargs
        )


# 默认 LLM 实例（共享）
llm = create_llm(temperature=1.0)
