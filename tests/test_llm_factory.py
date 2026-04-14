from __future__ import annotations

import sys
from types import ModuleType

from autocheck.config.settings import AppSettings
from autocheck.llm.factory import build_chat_model


class _FakeChatOpenAI:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def test_build_chat_model_uses_qwen_thinking_extra_body_for_compatible_api(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv(
        "AUTOCHECK_OPENAI_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setenv("AUTOCHECK_ENABLE_THINKING", "true")
    monkeypatch.setenv("AUTOCHECK_THINKING_BUDGET", "50")
    monkeypatch.setenv("AUTOCHECK_PRESERVE_THINKING", "true")
    monkeypatch.setenv("AUTOCHECK_MODEL_REASONING_EFFORT", "high")

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = _FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    settings = AppSettings.from_env(project_root=tmp_path)

    model = build_chat_model(settings)

    assert model.kwargs["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert model.kwargs["extra_body"] == {
        "enable_thinking": True,
        "thinking_budget": 50,
        "preserve_thinking": True,
    }
    assert "reasoning_effort" not in model.kwargs
    assert "use_responses_api" not in model.kwargs


def test_build_chat_model_keeps_openai_reasoning_effort_for_native_api(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AUTOCHECK_MODEL_REASONING_EFFORT", "high")
    monkeypatch.setenv("AUTOCHECK_OPENAI_WIRE_API", "responses")

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = _FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    settings = AppSettings.from_env(project_root=tmp_path)

    model = build_chat_model(settings)

    assert model.kwargs["reasoning_effort"] == "high"
    assert model.kwargs["use_responses_api"] is True
    assert "extra_body" not in model.kwargs


def test_settings_read_qwen_thinking_configuration(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOCHECK_ENABLE_THINKING", "true")
    monkeypatch.setenv("AUTOCHECK_THINKING_BUDGET", "128")
    monkeypatch.setenv("AUTOCHECK_PRESERVE_THINKING", "true")

    settings = AppSettings.from_env(project_root=tmp_path)

    assert settings.enable_thinking is True
    assert settings.thinking_budget == 128
    assert settings.preserve_thinking is True
