"""LLM factory — Claude, OpenAI, DeepSeek, OpenRouter, Ollama."""

from __future__ import annotations

from typing import Any

from autocorp.core.config import (
    MODEL_CATALOG,
    AgentRoleName,
    UserConfig,
    get_settings,
    load_user_config,
    resolve_model_for_role,
)


def get_chat_model(
    role: AgentRoleName,
    user_config: UserConfig | None = None,
    temperature: float = 0.4,
    **kwargs: Any,
):
    """Return a LangChain chat model for the given agent role."""
    model_id = resolve_model_for_role(role, user_config)
    return build_model(model_id, temperature=temperature, **kwargs)


def build_model(model_id: str, temperature: float = 0.4, **kwargs: Any):
    settings = get_settings()
    meta = MODEL_CATALOG.get(model_id, {})
    provider = meta.get("provider") or _infer_provider(model_id)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kw: dict[str, Any] = {
            "model": model_id,
            "temperature": temperature,
            "max_tokens": kwargs.get("max_tokens", 8192),
        }
        if settings.anthropic_api_key:
            kw["api_key"] = settings.anthropic_api_key
        return ChatAnthropic(**kw)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kw = {
            "model": model_id,
            "temperature": temperature if not model_id.startswith("o1") else 1,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        if settings.openai_api_key:
            kw["api_key"] = settings.openai_api_key
        return ChatOpenAI(**kw)

    if provider == "deepseek":
        from langchain_openai import ChatOpenAI

        mid = model_id.replace("deepseek/", "") if model_id.startswith("deepseek/") else model_id
        kw = {
            "model": mid,
            "base_url": meta.get("base_url", "https://api.deepseek.com"),
            "temperature": temperature,
        }
        if settings.deepseek_api_key:
            kw["api_key"] = settings.deepseek_api_key
        return ChatOpenAI(**kw)

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        # openrouter/anthropic/claude-sonnet-4 → anthropic/claude-sonnet-4
        remote = model_id
        if remote.startswith("openrouter/"):
            remote = remote[len("openrouter/") :]
        if remote == "auto":
            remote = "openrouter/auto"
        kw = {
            "model": remote,
            "base_url": meta.get("base_url", "https://openrouter.ai/api/v1"),
            "temperature": temperature,
            "default_headers": {
                "HTTP-Referer": "https://github.com/autocorp-ai/AutoCorp",
                "X-Title": "AutoCorp",
            },
        }
        if settings.openrouter_api_key:
            kw["api_key"] = settings.openrouter_api_key
        return ChatOpenAI(**kw)

    if provider == "ollama":
        # Prefer langchain-ollama if installed; else OpenAI-compatible endpoint
        ollama_model = model_id.split("/", 1)[-1] if model_id.startswith("ollama/") else model_id
        try:
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=ollama_model,
                base_url=settings.ollama_base_url,
                temperature=temperature,
            )
        except ImportError:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=ollama_model,
                api_key="ollama",
                base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
                temperature=temperature,
            )

    # Fallback OpenAI-compatible
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model_id, temperature=temperature)


def _infer_provider(model_id: str) -> str:
    if model_id.startswith("claude"):
        return "anthropic"
    if model_id.startswith("gpt") or model_id.startswith("o1"):
        return "openai"
    if model_id.startswith("deepseek"):
        return "deepseek"
    if model_id.startswith("openrouter"):
        return "openrouter"
    if model_id.startswith("ollama"):
        return "ollama"
    return "openai"


def model_ready(model_id: str) -> tuple[bool, str]:
    """Check whether credentials exist for a model."""
    settings = get_settings()
    meta = MODEL_CATALOG.get(model_id, {})
    provider = meta.get("provider") or _infer_provider(model_id)
    if provider == "anthropic":
        return (bool(settings.anthropic_api_key), "ANTHROPIC_API_KEY")
    if provider == "openai":
        return (bool(settings.openai_api_key), "OPENAI_API_KEY")
    if provider == "deepseek":
        return (bool(settings.deepseek_api_key), "DEEPSEEK_API_KEY")
    if provider == "openrouter":
        return (bool(settings.openrouter_api_key), "OPENROUTER_API_KEY")
    if provider == "ollama":
        return (True, "OLLAMA (local)")
    return (False, "unknown")
