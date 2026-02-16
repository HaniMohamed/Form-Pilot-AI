"""
LLM provider factory.

Creates a LangChain BaseChatModel instance configured from environment
variables, pointing to any OpenAI-compatible chat completions endpoint.

Works with any endpoint that follows the OpenAI Chat Completions API
format, such as GOSI Brain, Ollama, or any self-hosted LLM platform.
"""

import os

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel

load_dotenv()


def get_llm(**kwargs) -> BaseChatModel:
    """Create and return an LLM instance for an OpenAI-compatible endpoint.

    Reads configuration from environment variables. Keyword arguments
    override environment defaults.

    Required environment variables:
        CUSTOM_LLM_API_ENDPOINT: Full URL of the chat completions endpoint.
        CUSTOM_LLM_API_KEY: API key / bearer token.
        CUSTOM_LLM_MODEL_NAME: Model identifier (defaults to "default").

    Args:
        **kwargs: Additional keyword arguments passed to the LLM constructor.

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: If required config is missing.
    """
    from langchain_openai import ChatOpenAI

    # Sensible defaults — can be overridden via kwargs
    # request_timeout covers slow local models (e.g. Ollama with large context)
    defaults = {"temperature": 0, "max_tokens": 1024, "request_timeout": 300}
    merged = {**defaults, **kwargs}

    endpoint = merged.pop("api_endpoint", os.getenv("CUSTOM_LLM_API_ENDPOINT"))
    if not endpoint:
        raise ValueError(
            "CUSTOM_LLM_API_ENDPOINT env var (or api_endpoint kwarg) is required. "
            "Set it to your OpenAI-compatible chat completions URL."
        )

    # Strip /chat/completions suffix if present — ChatOpenAI appends it
    base_url = endpoint.rstrip("/")
    for suffix in ["/chat/completions", "/completions"]:
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
            break

    return ChatOpenAI(
        api_key=merged.pop("api_key", os.getenv("CUSTOM_LLM_API_KEY")),
        model=merged.pop("model", os.getenv("CUSTOM_LLM_MODEL_NAME", "default")),
        base_url=base_url,
        **merged,
    )
