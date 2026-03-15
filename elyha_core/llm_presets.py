"""Load and normalize legacy LLM preset definitions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LLMPreset:
    tag: str
    name: str
    group: str
    api_format: str
    llm_transport: str
    api_url: str
    api_key: str
    model: str
    models: list[str]
    auto_complete: bool = True


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _as_text(item)
        if text:
            items.append(text)
    return items


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _as_text(value).lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _preset_from_payload(default_tag: str, payload: Any) -> LLMPreset | None:
    if not isinstance(payload, dict):
        return None
    tag = _as_text(payload.get("tag")) or _as_text(default_tag)
    if not tag:
        return None
    name = _as_text(payload.get("name")) or tag
    group = _as_text(payload.get("group"))
    api_format = _as_text(payload.get("api_format"))
    llm_transport = _as_text(payload.get("llm_transport")).lower()
    if llm_transport in {"openai_sdk", "openai-client", "openai_client"}:
        llm_transport = "openai"
    elif llm_transport in {"anthropic_sdk", "anthropic-client", "anthropic_client"}:
        llm_transport = "anthropic"
    elif llm_transport not in {"httpx", "openai", "anthropic"}:
        llm_transport = "anthropic" if api_format.lower() == "anthropic" else "httpx"
    api_url = _as_text(payload.get("api_url"))
    api_key = _as_text(payload.get("api_key"))
    model = _as_text(payload.get("model"))
    auto_complete = _as_bool(payload.get("auto_complete"), default=True)
    models = _as_text_list(payload.get("model_datas"))
    if model and model not in models:
        models.insert(0, model)
    return LLMPreset(
        tag=tag,
        name=name,
        group=group,
        api_format=api_format,
        llm_transport=llm_transport,
        api_url=api_url,
        api_key=api_key,
        model=model,
        auto_complete=auto_complete,
        models=models,
    )


def load_llm_presets(path: str | Path) -> dict[str, LLMPreset]:
    preset_path = Path(path)
    if not preset_path.exists():
        return {}
    try:
        payload = json.loads(preset_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    platforms = payload.get("platforms")
    if not isinstance(platforms, dict):
        return {}
    result: dict[str, LLMPreset] = {}
    for key, raw in platforms.items():
        preset = _preset_from_payload(_as_text(key), raw)
        if preset is None:
            continue
        result[preset.tag] = preset
    return result


def preset_to_platform_config(preset: LLMPreset) -> dict[str, Any]:
    config: dict[str, Any] = {
        "target_platform": preset.tag,
        "auto_complete": bool(preset.auto_complete),
        "llm_transport": preset.llm_transport,
    }
    if preset.api_url:
        config["api_url"] = preset.api_url
    if preset.api_key:
        config["api_key"] = preset.api_key
    if preset.model:
        config["model_name"] = preset.model
    return config
