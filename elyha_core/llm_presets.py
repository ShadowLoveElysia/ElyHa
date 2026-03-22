"""Load and normalize legacy LLM preset definitions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any

PRESET_TAG_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


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
    source: str = "builtin"


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


def normalize_preset_tag(value: str) -> str:
    tag = _as_text(value).lower()
    if not tag:
        raise ValueError("preset tag cannot be empty")
    if not PRESET_TAG_PATTERN.match(tag):
        raise ValueError("invalid preset tag, allowed: A-Z a-z 0-9 . _ - (1-64 chars)")
    return tag


def _normalize_transport(value: str, api_format: str) -> str:
    llm_transport = _as_text(value).lower()
    if llm_transport in {"openai_sdk", "openai-client", "openai_client"}:
        return "openai"
    if llm_transport in {"anthropic_sdk", "anthropic-client", "anthropic_client"}:
        return "anthropic"
    if llm_transport in {"httpx", "openai", "anthropic"}:
        return llm_transport
    return "anthropic" if _as_text(api_format).lower() == "anthropic" else "httpx"


def _normalize_models(default_model: str, value: Any) -> list[str]:
    models = _as_text_list(value)
    if default_model and default_model not in models:
        models.insert(0, default_model)
    return models


def _preset_from_payload(default_tag: str, payload: Any, *, default_source: str) -> LLMPreset | None:
    if not isinstance(payload, dict):
        return None
    try:
        tag = normalize_preset_tag(_as_text(payload.get("tag")) or _as_text(default_tag))
    except ValueError:
        return None
    source = _as_text(payload.get("source")).lower() or default_source
    if source not in {"builtin", "user"}:
        source = default_source
    name = _as_text(payload.get("name")) or tag
    group = _as_text(payload.get("group")) or ("custom" if source == "user" else "")
    api_format = _as_text(payload.get("api_format"))
    llm_transport = _normalize_transport(_as_text(payload.get("llm_transport")), api_format)
    if not api_format:
        api_format = "Anthropic" if llm_transport == "anthropic" else "OpenAI"
    api_url = _as_text(payload.get("api_url"))
    api_key = _as_text(payload.get("api_key"))
    model = _as_text(payload.get("model")) or _as_text(payload.get("default_model"))
    auto_complete = _as_bool(payload.get("auto_complete"), default=True)
    raw_models = payload.get("model_datas")
    if raw_models is None:
        raw_models = payload.get("models")
    models = _normalize_models(model, raw_models)
    if source == "user":
        api_key = ""
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
        source=source,
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
        preset = _preset_from_payload(_as_text(key), raw, default_source="builtin")
        if preset is None:
            continue
        result[preset.tag] = preset
    return result


class UserLLMPresetManager:
    """Store user presets under a dedicated directory."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _preset_path(self, tag: str) -> Path:
        return self.root_dir / f"{normalize_preset_tag(tag)}.json"

    def _write_text_atomic(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self._write_text_atomic(path, text)

    def load_presets(self) -> dict[str, LLMPreset]:
        presets: dict[str, LLMPreset] = {}
        self.root_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.root_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            preset = _preset_from_payload(path.stem, raw, default_source="user")
            if preset is None:
                continue
            presets[preset.tag] = preset
        return presets

    def save_preset(self, preset: LLMPreset, *, overwrite: bool = False) -> LLMPreset:
        tag = normalize_preset_tag(preset.tag)
        path = self._preset_path(tag)
        if path.exists() and not overwrite:
            raise ValueError(f"preset already exists: {tag}")
        api_format = _as_text(preset.api_format) or ("Anthropic" if preset.llm_transport == "anthropic" else "OpenAI")
        llm_transport = _normalize_transport(preset.llm_transport, api_format)
        model = _as_text(preset.model)
        models = _normalize_models(model, list(preset.models))
        saved = LLMPreset(
            tag=tag,
            name=_as_text(preset.name) or tag,
            group=_as_text(preset.group) or "custom",
            api_format=api_format,
            llm_transport=llm_transport,
            api_url=_as_text(preset.api_url),
            api_key="",
            model=model,
            models=models,
            auto_complete=bool(preset.auto_complete),
            source="user",
        )
        payload = {
            "tag": saved.tag,
            "name": saved.name,
            "group": saved.group,
            "api_format": saved.api_format,
            "llm_transport": saved.llm_transport,
            "api_url": saved.api_url,
            "default_model": saved.model,
            "models": list(saved.models),
            "auto_complete": saved.auto_complete,
            "source": "user",
        }
        self._write_json_atomic(path, payload)
        return saved

    def delete_preset(self, tag: str) -> str:
        normalized = normalize_preset_tag(tag)
        path = self._preset_path(normalized)
        if not path.exists():
            raise KeyError(f"preset not found: {normalized}")
        path.unlink()
        return normalized


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
