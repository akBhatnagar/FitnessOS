"""
Model-agnostic LLM abstraction layer.

This is the single point of contact between FitnessOS and any LLM provider.
Switching providers requires changing only the configuration — not application code.

Supported providers: OpenAI, Anthropic, Google, OpenRouter, Ollama.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

from app.core.config import LLMProvider, settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singletons — instantiated once, reused across requests.
_llm_instances: dict[str, BaseChatModel] = {}
_embedding_instances: dict[str, Embeddings] = {}


def get_llm(
    provider: LLMProvider | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    streaming: bool = False,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Return a configured LangChain chat model for the given provider.

    Instances are cached at the module level — creating one per agent call
    is unnecessary and wasteful.
    """
    target_provider = provider or settings.default_llm_provider
    cache_key = f"{target_provider}:{model}:{temperature}:{streaming}"

    if cache_key in _llm_instances:
        return _llm_instances[cache_key]

    llm = _create_llm(target_provider, model, temperature, max_tokens, streaming, **kwargs)
    _llm_instances[cache_key] = llm

    logger.info(
        "LLM instance created",
        provider=target_provider.value,
        model=model or settings.get_llm_config(target_provider).get("model"),
    )
    return llm


def get_embedding_model(
    provider: LLMProvider | None = None,
    model: str | None = None,
) -> Embeddings:
    """Return a configured LangChain embeddings model."""
    target_provider = provider or settings.default_embedding_provider
    cache_key = f"{target_provider}:{model}"

    if cache_key in _embedding_instances:
        return _embedding_instances[cache_key]

    embeddings = _create_embeddings(target_provider, model)
    _embedding_instances[cache_key] = embeddings
    return embeddings


def _create_llm(
    provider: LLMProvider,
    model: str | None,
    temperature: float,
    max_tokens: int,
    streaming: bool,
    **kwargs: Any,
) -> BaseChatModel:
    config = settings.get_llm_config(provider)
    resolved_model = model or config.get("model", "")

    match provider:
        case LLMProvider.OPENAI:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=resolved_model,
                api_key=config["api_key"],
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **kwargs,
            )

        case LLMProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=resolved_model,
                api_key=config["api_key"],
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **kwargs,
            )

        case LLMProvider.GOOGLE:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=resolved_model,
                google_api_key=config["api_key"],
                temperature=temperature,
                max_output_tokens=max_tokens,
                streaming=streaming,
                **kwargs,
            )

        case LLMProvider.OPENROUTER:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=resolved_model,
                api_key=config["api_key"],
                base_url=config["base_url"],
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **kwargs,
            )

        case LLMProvider.OLLAMA:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=resolved_model,
                base_url=f"{config['base_url']}/v1",
                api_key="ollama",  # Ollama doesn't require a real key
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **kwargs,
            )

        case _:
            raise ValueError(f"Unsupported LLM provider: {provider}")


def _create_embeddings(provider: LLMProvider, model: str | None) -> Embeddings:
    config = settings.get_llm_config(provider)
    resolved_model = model or config.get("model", "")

    match provider:
        case LLMProvider.OPENAI:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model=settings.openai_embedding_model,
                api_key=config["api_key"],
            )

        case LLMProvider.GOOGLE:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            return GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=config["api_key"],
            )

        case LLMProvider.OLLAMA:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model=resolved_model,
                base_url=f"{config['base_url']}/v1",
                api_key="ollama",
            )

        case _:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model=settings.openai_embedding_model,
                api_key=settings.openai_api_key,
            )
