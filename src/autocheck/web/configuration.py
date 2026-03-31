from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from autocheck.config.settings import AppSettings

ConfigValue = str | int | float | bool


@dataclass(frozen=True)
class ConfigFieldSpec:
    key: str
    attr_name: str
    group: str
    label: str
    control: Literal["text", "password", "number", "boolean"]
    value_type: Literal["string", "int", "float", "bool"]
    description: str
    default: ConfigValue
    placeholder: str = ""
    min_value: float | None = None
    step: str | None = None


class ConfigField(BaseModel):
    key: str
    group: str
    label: str
    control: str
    value_type: str
    description: str
    default_value: ConfigValue
    placeholder: str = ""
    min_value: float | None = None
    step: str | None = None


class ConfigResponse(BaseModel):
    env_path: str
    has_env_file: bool
    fields: list[ConfigField]
    values: dict[str, ConfigValue]
    message: str | None = None


class ConfigSaveRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


_FIELD_SPECS: tuple[ConfigFieldSpec, ...] = (
    ConfigFieldSpec(
        key="OPENAI_API_KEY",
        attr_name="openai_api_key",
        group="OpenAI 接入",
        label="API Key",
        control="password",
        value_type="string",
        description="OpenAI 或兼容网关使用的 API Key。",
        default="",
        placeholder="sk-...",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_OPENAI_BASE_URL",
        attr_name="openai_base_url",
        group="OpenAI 接入",
        label="Base URL",
        control="text",
        value_type="string",
        description="兼容接口地址，留空时使用 SDK 默认值。",
        default="",
        placeholder="https://your-openai-compatible-endpoint/v1",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_OPENAI_TIMEOUT",
        attr_name="openai_timeout",
        group="OpenAI 接入",
        label="请求超时（秒）",
        control="number",
        value_type="float",
        description="单次模型请求的超时时间。",
        default=120.0,
        min_value=1,
        step="1",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_OPENAI_MAX_RETRIES",
        attr_name="openai_max_retries",
        group="OpenAI 接入",
        label="最大重试次数",
        control="number",
        value_type="int",
        description="请求失败后的最大自动重试次数。",
        default=2,
        min_value=0,
        step="1",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_OPENAI_WIRE_API",
        attr_name="openai_wire_api",
        group="OpenAI 接入",
        label="接口模式",
        control="text",
        value_type="string",
        description="与 OpenAI 兼容接口通信时使用的协议类型。",
        default="responses",
        placeholder="responses",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_OPENAI_DISABLE_RESPONSE_STORAGE",
        attr_name="openai_disable_response_storage",
        group="OpenAI 接入",
        label="禁用响应存储",
        control="boolean",
        value_type="bool",
        description="更适合隐私敏感场景。",
        default=True,
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_MODEL_REASONING_EFFORT",
        attr_name="model_reasoning_effort",
        group="模型策略",
        label="推理强度",
        control="text",
        value_type="string",
        description="例如 `low`、`medium`、`high`、`xhigh`。",
        default="",
        placeholder="xhigh",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_ENABLE_LLM_EXTRACTION",
        attr_name="enable_llm_extraction",
        group="模型策略",
        label="启用 LLM 抽取",
        control="boolean",
        value_type="bool",
        description="是否使用模型辅助抽取 claim 和 reference。",
        default=False,
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_ENABLE_LLM_VERIFICATION",
        attr_name="enable_llm_verification",
        group="模型策略",
        label="启用 LLM 核验",
        control="boolean",
        value_type="bool",
        description="是否使用模型辅助完成引用核验。",
        default=True,
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_CHAT_MODEL",
        attr_name="chat_model",
        group="模型策略",
        label="默认聊天模型",
        control="text",
        value_type="string",
        description="提取和核验模型未单独指定时回退到这里。",
        default="gpt-5.4",
        placeholder="gpt-5.4",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_EXTRACT_MODEL",
        attr_name="extract_model",
        group="模型策略",
        label="抽取模型",
        control="text",
        value_type="string",
        description="留空时回退到默认聊天模型。",
        default="",
        placeholder="留空则使用默认聊天模型",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_VERIFY_MODEL",
        attr_name="verify_model",
        group="模型策略",
        label="核验模型",
        control="text",
        value_type="string",
        description="默认用于 claim x citation 核验。",
        default="gpt-5.4",
        placeholder="gpt-5.4",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_TEMPERATURE",
        attr_name="temperature",
        group="模型策略",
        label="温度",
        control="number",
        value_type="float",
        description="通常使用 `0` 以提高稳定性。",
        default=0.0,
        min_value=0,
        step="0.1",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_CHUNK_SIZE",
        attr_name="chunk_size",
        group="检索参数",
        label="切块大小",
        control="number",
        value_type="int",
        description="证据检索时每个文本块的字符数。",
        default=2200,
        min_value=1,
        step="1",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_CHUNK_OVERLAP",
        attr_name="chunk_overlap",
        group="检索参数",
        label="切块重叠",
        control="number",
        value_type="int",
        description="相邻文本块之间共享的字符数。",
        default=300,
        min_value=0,
        step="1",
    ),
    ConfigFieldSpec(
        key="AUTOCHECK_STRUCTURED_OUTPUT_METHOD",
        attr_name="structured_output_method",
        group="API 兼容",
        label="结构化输出方法",
        control="text",
        value_type="string",
        description="function_calling（OpenAI/GPT）或 json_mode（第三方 API 兼容）。",
        default="function_calling",
        placeholder="function_calling",
    ),
)

_FIELD_BY_KEY = {spec.key: spec for spec in _FIELD_SPECS}
_MANAGED_KEYS = tuple(spec.key for spec in _FIELD_SPECS)
_ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


class ConfigService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.env_path = self.project_root / ".env"

    def build_response(
        self,
        settings: AppSettings,
        message: str | None = None,
    ) -> ConfigResponse:
        return ConfigResponse(
            env_path=str(self.env_path),
            has_env_file=self.env_path.exists(),
            fields=[self._field_payload(spec) for spec in _FIELD_SPECS],
            values=self._values_from_settings(settings),
            message=message,
        )

    def save(
        self,
        current_settings: AppSettings,
        raw_values: dict[str, Any],
    ) -> tuple[AppSettings, ConfigResponse]:
        values = self._merge_values(current_settings, raw_values)
        self._write_env_file(values)
        self._apply_environment(values)
        refreshed_settings = AppSettings.from_env(project_root=self.project_root)
        return refreshed_settings, self.build_response(
            settings=refreshed_settings,
            message=f"配置已保存到 {self.env_path}",
        )

    def _merge_values(
        self,
        current_settings: AppSettings,
        raw_values: dict[str, Any],
    ) -> dict[str, ConfigValue]:
        current_values = self._values_from_settings(current_settings)
        unknown_keys = sorted(set(raw_values) - set(_FIELD_BY_KEY))
        if unknown_keys:
            raise ValueError(f"存在未知配置项：{', '.join(unknown_keys)}")

        merged = dict(current_values)
        for key, raw_value in raw_values.items():
            merged[key] = self._coerce_value(_FIELD_BY_KEY[key], raw_value)

        self._validate_values(merged)
        return merged

    def _coerce_value(self, spec: ConfigFieldSpec, raw_value: Any) -> ConfigValue:
        if spec.value_type == "bool":
            return self._coerce_bool(spec, raw_value)
        if spec.value_type == "int":
            return self._coerce_int(spec, raw_value)
        if spec.value_type == "float":
            return self._coerce_float(spec, raw_value)
        return "" if raw_value is None else str(raw_value).strip()

    def _coerce_bool(self, spec: ConfigFieldSpec, raw_value: Any) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            value = raw_value.strip().lower()
            if value in {"1", "true", "yes", "on"}:
                return True
            if value in {"0", "false", "no", "off"}:
                return False
        raise ValueError(f"{spec.label} 必须是布尔值。")

    def _coerce_int(self, spec: ConfigFieldSpec, raw_value: Any) -> int:
        try:
            parsed = int(str(raw_value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{spec.label} 必须是整数。") from exc
        if spec.min_value is not None and parsed < spec.min_value:
            raise ValueError(f"{spec.label} 不能小于 {int(spec.min_value)}。")
        return parsed

    def _coerce_float(self, spec: ConfigFieldSpec, raw_value: Any) -> float:
        try:
            parsed = float(str(raw_value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{spec.label} 必须是数字。") from exc
        if spec.min_value is not None and parsed < spec.min_value:
            raise ValueError(f"{spec.label} 不能小于 {spec.min_value:g}。")
        return parsed

    def _validate_values(self, values: dict[str, ConfigValue]) -> None:
        chunk_size = int(values["AUTOCHECK_CHUNK_SIZE"])
        chunk_overlap = int(values["AUTOCHECK_CHUNK_OVERLAP"])
        if chunk_overlap >= chunk_size:
            raise ValueError("切块重叠必须小于切块大小。")

    def _write_env_file(self, values: dict[str, ConfigValue]) -> None:
        existing_lines = []
        if self.env_path.exists():
            existing_lines = self.env_path.read_text(encoding="utf-8").splitlines()

        rendered: list[str] = []
        seen: set[str] = set()
        for line in existing_lines:
            match = _ENV_LINE_RE.match(line)
            if not match:
                rendered.append(line)
                continue
            key = match.group(1)
            if key not in _MANAGED_KEYS:
                rendered.append(line)
                continue
            rendered.append(f"{key}={self._serialize_for_env(values[key])}")
            seen.add(key)

        missing = [key for key in _MANAGED_KEYS if key not in seen]
        if missing:
            if rendered and rendered[-1].strip():
                rendered.append("")
            if "# AutoCheck Web UI managed settings" not in rendered:
                rendered.append("# AutoCheck Web UI managed settings")
            for key in missing:
                rendered.append(f"{key}={self._serialize_for_env(values[key])}")

        content = "\n".join(rendered).rstrip()
        self.env_path.write_text(f"{content}\n" if content else "", encoding="utf-8")

    def _apply_environment(self, values: dict[str, ConfigValue]) -> None:
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("OPENAI_API_BASE", None)
        for key, value in values.items():
            os.environ[key] = self._serialize_for_process(value)

    def _values_from_settings(self, settings: AppSettings) -> dict[str, ConfigValue]:
        return {
            spec.key: getattr(settings, spec.attr_name)
            for spec in _FIELD_SPECS
        }

    def _field_payload(self, spec: ConfigFieldSpec) -> ConfigField:
        return ConfigField(
            key=spec.key,
            group=spec.group,
            label=spec.label,
            control=spec.control,
            value_type=spec.value_type,
            description=spec.description,
            default_value=spec.default,
            placeholder=spec.placeholder,
            min_value=spec.min_value,
            step=spec.step,
        )

    def _serialize_for_env(self, value: ConfigValue) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)

        text = value
        if text == "" or any(char.isspace() for char in text) or "#" in text or '"' in text:
            return json.dumps(text, ensure_ascii=False)
        return text

    def _serialize_for_process(self, value: ConfigValue) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
