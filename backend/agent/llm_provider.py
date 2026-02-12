"""
LLM provider factory.

Supports multiple LLM backends via a simple factory function.
All providers return a LangChain BaseChatModel instance configured
from environment variables.

Supported providers:
- openai       → ChatOpenAI
- azure_openai → AzureChatOpenAI
- watsonx      → ChatWatsonx from langchain_ibm
- custom       → ChatOpenAI with a custom base_url (OpenAI-compatible)
"""

import os

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel

load_dotenv()


def get_llm(provider: str | None = None, **kwargs) -> BaseChatModel:
    """Create and return an LLM instance based on the provider.

    Reads configuration from environment variables. Keyword arguments
    override environment defaults.

    Args:
        provider: One of "openai", "azure_openai", "watsonx", "custom".
                  Falls back to the LLM_PROVIDER env var if not given.
        **kwargs: Additional keyword arguments passed to the LLM constructor.

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: If the provider is unknown or required config is missing.
    """
    provider = provider or os.getenv("LLM_PROVIDER", "openai")

    # Sensible defaults — can be overridden via kwargs
    defaults = {"temperature": 0, "max_tokens": 1024}
    merged = {**defaults, **kwargs}

    match provider:
        case "openai":
            return _create_openai(**merged)
        case "azure_openai":
            return _create_azure_openai(**merged)
        case "watsonx":
            return _create_watsonx(**merged)
        case "custom":
            return _create_custom(**merged)
        case _:
            raise ValueError(
                f"Unknown LLM provider: '{provider}'. "
                "Supported: openai, azure_openai, watsonx, custom"
            )


def _create_openai(**kwargs) -> BaseChatModel:
    """Create a ChatOpenAI instance."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=kwargs.pop("api_key", os.getenv("OPENAI_API_KEY")),
        model=kwargs.pop("model", os.getenv("OPENAI_MODEL_NAME", "gpt-4o")),
        **kwargs,
    )


def _create_azure_openai(**kwargs) -> BaseChatModel:
    """Create an AzureChatOpenAI instance."""
    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        api_key=kwargs.pop("api_key", os.getenv("AZURE_OPENAI_API_KEY")),
        azure_endpoint=kwargs.pop(
            "azure_endpoint", os.getenv("AZURE_OPENAI_ENDPOINT")
        ),
        azure_deployment=kwargs.pop(
            "azure_deployment", os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        ),
        api_version=kwargs.pop(
            "api_version", os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        ),
        **kwargs,
    )


def _create_watsonx(**kwargs) -> BaseChatModel:
    """Create a ChatWatsonx instance from langchain_ibm."""
    from langchain_ibm import ChatWatsonx

    return ChatWatsonx(
        apikey=kwargs.pop("api_key", os.getenv("WATSONX_API_KEY")),
        url=kwargs.pop("url", os.getenv("WATSONX_URL")),
        project_id=kwargs.pop("project_id", os.getenv("WATSONX_PROJECT_ID")),
        model_id=kwargs.pop("model", os.getenv("WATSONX_MODEL_ID")),
        **kwargs,
    )


def _create_custom(**kwargs) -> BaseChatModel:
    """Create a ChatOpenAI instance pointing to a custom OpenAI-compatible endpoint.

    This works with any endpoint that follows the OpenAI Chat Completions
    API format, such as GOSI Brain or other self-hosted LLM platforms.
    """
    from langchain_openai import ChatOpenAI

    endpoint = kwargs.pop("api_endpoint", os.getenv("CUSTOM_LLM_API_ENDPOINT"))
    if not endpoint:
        raise ValueError(
            "Custom provider requires CUSTOM_LLM_API_ENDPOINT env var or api_endpoint kwarg"
        )

    # Strip /chat/completions suffix if present — ChatOpenAI appends it
    base_url = endpoint.rstrip("/")
    for suffix in ["/chat/completions", "/completions"]:
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
            break

    return ChatOpenAI(
        api_key=kwargs.pop("api_key", os.getenv("CUSTOM_LLM_API_KEY")),
        model=kwargs.pop("model", os.getenv("CUSTOM_LLM_MODEL_NAME", "default")),
        base_url=base_url,
        **kwargs,
    )
