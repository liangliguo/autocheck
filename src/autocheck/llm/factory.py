from __future__ import annotations

from typing import Optional

from autocheck.config.settings import AppSettings


def build_chat_model(settings: AppSettings, purpose: str = "chat") -> Optional[object]:
    if not settings.openai_api_key:
        return None

    from langchain_openai import ChatOpenAI

    model_name = settings.chat_model
    if purpose == "extract" and settings.extract_model:
        model_name = settings.extract_model
    elif purpose == "verify" and settings.verify_model:
        model_name = settings.verify_model

    client_kwargs = {
        "model": model_name,
        "temperature": settings.temperature,
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout,
        "max_retries": settings.openai_max_retries,
    }
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    if settings.openai_wire_api.strip().lower() == "responses":
        client_kwargs["use_responses_api"] = True
    if settings.model_reasoning_effort:
        client_kwargs["reasoning_effort"] = settings.model_reasoning_effort
    client_kwargs["store"] = not settings.openai_disable_response_storage

    return ChatOpenAI(
        **client_kwargs,
    )
