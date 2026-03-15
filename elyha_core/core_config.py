"""Shared runtime config profiles stored as JSON files."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile


SUPPORTED_WORKFLOW_MODES = {"single", "multi_agent"}
PROFILE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
CORE_PROFILE = "core"


@dataclass(slots=True)
class CoreRuntimeConfig:
    """Cross-client runtime config for Web/TUI/API."""

    locale: str = "zh"
    llm_provider: str = "mock"
    llm_transport: str = "httpx"
    api_url: str = ""
    api_key: str = ""
    model_name: str = ""
    auto_complete: bool = True
    think_switch: bool = False
    think_depth: str = "medium"
    thinking_budget: int = 2048
    web_search_enabled: bool = False
    web_search_context_size: str = "medium"
    web_search_max_results: int = 5
    llm_request_timeout: int = 90
    web_request_timeout_ms: int = 240000
    default_token_budget: int = 2200
    default_workflow_mode: str = "multi_agent"
    web_host: str = "127.0.0.1"
    web_port: int = 8765

    def normalized(self) -> "CoreRuntimeConfig":
        locale = str(self.locale).strip().lower() or "zh"
        llm_provider = str(self.llm_provider).strip().lower() or "mock"
        llm_transport = str(self.llm_transport).strip().lower() or "httpx"
        if llm_transport in {"openai_sdk", "openai-client", "openai_client"}:
            llm_transport = "openai"
        elif llm_transport in {"anthropic_sdk", "anthropic-client", "anthropic_client"}:
            llm_transport = "anthropic"
        elif llm_transport not in {"httpx", "openai", "anthropic"}:
            llm_transport = "httpx"
        api_url = str(self.api_url).strip()
        api_key = str(self.api_key).strip()
        model_name = str(self.model_name).strip()
        raw_auto_complete = self.auto_complete
        if isinstance(raw_auto_complete, str):
            auto_complete = raw_auto_complete.strip().lower() in {"1", "true", "yes", "on"}
        else:
            auto_complete = bool(raw_auto_complete)
        raw_think_switch = self.think_switch
        if isinstance(raw_think_switch, str):
            think_switch = raw_think_switch.strip().lower() in {"1", "true", "yes", "on"}
        else:
            think_switch = bool(raw_think_switch)
        think_depth = str(self.think_depth).strip().lower() or "medium"
        if think_depth not in {"low", "medium", "high"}:
            think_depth = "medium"
        try:
            thinking_budget = int(self.thinking_budget)
        except (TypeError, ValueError):
            thinking_budget = 2048
        if thinking_budget < 128:
            thinking_budget = 128
        if thinking_budget > 32768:
            thinking_budget = 32768
        raw_web_search = self.web_search_enabled
        if isinstance(raw_web_search, str):
            web_search_enabled = raw_web_search.strip().lower() in {"1", "true", "yes", "on"}
        else:
            web_search_enabled = bool(raw_web_search)
        web_search_context_size = str(self.web_search_context_size).strip().lower() or "medium"
        if web_search_context_size not in {"low", "medium", "high"}:
            web_search_context_size = "medium"
        try:
            web_search_max_results = int(self.web_search_max_results)
        except (TypeError, ValueError):
            web_search_max_results = 5
        if web_search_max_results < 1:
            web_search_max_results = 1
        if web_search_max_results > 20:
            web_search_max_results = 20
        try:
            llm_request_timeout = int(self.llm_request_timeout)
        except (TypeError, ValueError):
            llm_request_timeout = 90
        if llm_request_timeout < 5:
            llm_request_timeout = 5
        if llm_request_timeout > 600:
            llm_request_timeout = 600
        try:
            web_request_timeout_ms = int(self.web_request_timeout_ms)
        except (TypeError, ValueError):
            web_request_timeout_ms = 240000
        if web_request_timeout_ms < 30000:
            web_request_timeout_ms = 30000
        if web_request_timeout_ms > 1200000:
            web_request_timeout_ms = 1200000
        workflow = str(self.default_workflow_mode).strip().lower().replace("-", "_") or "multi_agent"
        if workflow not in SUPPORTED_WORKFLOW_MODES:
            workflow = "multi_agent"
        budget = int(self.default_token_budget)
        if budget <= 0:
            budget = 2200
        web_host = str(self.web_host).strip() or "127.0.0.1"
        try:
            web_port = int(self.web_port)
        except (TypeError, ValueError):
            web_port = 8765
        if web_port <= 0 or web_port > 65535:
            web_port = 8765
        return CoreRuntimeConfig(
            locale=locale,
            llm_provider=llm_provider,
            llm_transport=llm_transport,
            api_url=api_url,
            api_key=api_key,
            model_name=model_name,
            auto_complete=auto_complete,
            think_switch=think_switch,
            think_depth=think_depth,
            thinking_budget=thinking_budget,
            web_search_enabled=web_search_enabled,
            web_search_context_size=web_search_context_size,
            web_search_max_results=web_search_max_results,
            llm_request_timeout=llm_request_timeout,
            web_request_timeout_ms=web_request_timeout_ms,
            default_token_budget=budget,
            default_workflow_mode=workflow,
            web_host=web_host,
            web_port=web_port,
        )


def normalize_profile_name(value: str) -> str:
    profile = str(value).strip()
    if not PROFILE_PATTERN.match(profile):
        raise ValueError("invalid profile name, allowed: A-Z a-z 0-9 . _ - (1-64 chars)")
    return profile


class CoreConfigManager:
    """Manage multi-profile runtime configs in one shared directory."""

    def __init__(
        self,
        root_dir: str | Path,
        *,
        active_profile_file: str = "active_profile.txt",
    ) -> None:
        self.root_dir = Path(root_dir)
        self.active_profile_path = self.root_dir / active_profile_file
        self._ensure_core_profile()

    def _profile_path(self, profile: str) -> Path:
        safe = normalize_profile_name(profile)
        return self.root_dir / f"{safe}.json"

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

    def _write_json_atomic(self, path: Path, payload: dict[str, object]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self._write_text_atomic(path, text)

    def _ensure_core_profile(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        core_path = self._profile_path(CORE_PROFILE)
        if not core_path.exists():
            self._write_json_atomic(core_path, asdict(CoreRuntimeConfig().normalized()))

    def _load_profile_unchecked(self, profile: str) -> CoreRuntimeConfig:
        path = self._profile_path(profile)
        if not path.exists():
            config = CoreRuntimeConfig().normalized()
            self._write_json_atomic(path, asdict(config))
            return config
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = CoreRuntimeConfig().normalized()
            self._write_json_atomic(path, asdict(config))
            return config
        if not isinstance(raw, dict):
            config = CoreRuntimeConfig().normalized()
            self._write_json_atomic(path, asdict(config))
            return config
        data = asdict(CoreRuntimeConfig())
        merged = {key: raw.get(key, default) for key, default in data.items()}
        config = CoreRuntimeConfig(**merged).normalized()
        self._write_json_atomic(path, asdict(config))
        return config

    def list_profiles(self) -> list[str]:
        self._ensure_core_profile()
        profiles: list[str] = []
        for path in sorted(self.root_dir.glob("*.json")):
            profiles.append(path.stem)
        profiles = sorted(set(profiles))
        if CORE_PROFILE in profiles:
            profiles.remove(CORE_PROFILE)
        return [CORE_PROFILE] + profiles

    def profile_exists(self, profile: str) -> bool:
        normalized = normalize_profile_name(profile)
        return self._profile_path(normalized).exists()

    def get_active_profile(self) -> str:
        self._ensure_core_profile()
        if not self.active_profile_path.exists():
            self._write_text_atomic(self.active_profile_path, CORE_PROFILE)
            return CORE_PROFILE
        raw = self.active_profile_path.read_text(encoding="utf-8").strip()
        if not raw:
            self._write_text_atomic(self.active_profile_path, CORE_PROFILE)
            return CORE_PROFILE
        try:
            profile = normalize_profile_name(raw)
        except ValueError:
            self._write_text_atomic(self.active_profile_path, CORE_PROFILE)
            return CORE_PROFILE
        if not self.profile_exists(profile):
            self._write_text_atomic(self.active_profile_path, CORE_PROFILE)
            return CORE_PROFILE
        return profile

    def set_active_profile(self, profile: str, *, create_if_missing: bool = True) -> CoreRuntimeConfig:
        normalized = normalize_profile_name(profile)
        if not self.profile_exists(normalized):
            if create_if_missing and normalized != CORE_PROFILE:
                self.create_profile(normalized)
            elif create_if_missing and normalized == CORE_PROFILE:
                self._ensure_core_profile()
            else:
                raise KeyError(f"profile not found: {normalized}")
        self._write_text_atomic(self.active_profile_path, normalized)
        return self.load_profile(normalized)

    def load_profile(self, profile: str) -> CoreRuntimeConfig:
        normalized = normalize_profile_name(profile)
        if not self.profile_exists(normalized):
            if normalized == CORE_PROFILE:
                self._ensure_core_profile()
            else:
                raise KeyError(f"profile not found: {normalized}")
        return self._load_profile_unchecked(normalized)

    def save_profile(self, profile: str, config: CoreRuntimeConfig) -> CoreRuntimeConfig:
        normalized = normalize_profile_name(profile)
        if normalized == CORE_PROFILE:
            raise PermissionError("core profile is read-only")
        if not self.profile_exists(normalized):
            raise KeyError(f"profile not found: {normalized}")
        normalized_config = config.normalized()
        self._write_json_atomic(self._profile_path(normalized), asdict(normalized_config))
        return normalized_config

    def create_profile(self, profile: str, *, from_profile: str = CORE_PROFILE) -> CoreRuntimeConfig:
        normalized = normalize_profile_name(profile)
        source = normalize_profile_name(from_profile)
        if normalized == CORE_PROFILE:
            raise ValueError("cannot create reserved profile name: core")
        if self.profile_exists(normalized):
            raise ValueError(f"profile already exists: {normalized}")
        if not self.profile_exists(source):
            raise KeyError(f"profile not found: {source}")
        base_config = self.load_profile(source)
        self._write_json_atomic(self._profile_path(normalized), asdict(base_config))
        return self.load_profile(normalized)

    def rename_profile(self, profile: str, new_profile: str) -> str:
        source = normalize_profile_name(profile)
        target = normalize_profile_name(new_profile)
        if source == CORE_PROFILE or target == CORE_PROFILE:
            raise PermissionError("core profile cannot be renamed")
        if not self.profile_exists(source):
            raise KeyError(f"profile not found: {source}")
        if self.profile_exists(target):
            raise ValueError(f"target profile already exists: {target}")
        self._profile_path(source).replace(self._profile_path(target))
        if self.get_active_profile() == source:
            self._write_text_atomic(self.active_profile_path, target)
        return target

    def delete_profile(self, profile: str) -> str:
        normalized = normalize_profile_name(profile)
        if normalized == CORE_PROFILE:
            raise PermissionError("core profile cannot be deleted")
        path = self._profile_path(normalized)
        if not path.exists():
            raise KeyError(f"profile not found: {normalized}")
        path.unlink()
        if self.get_active_profile() == normalized:
            self._write_text_atomic(self.active_profile_path, CORE_PROFILE)
        return normalized

    def load_active(self) -> tuple[str, CoreRuntimeConfig]:
        profile = self.get_active_profile()
        return profile, self.load_profile(profile)

    def update_active(self, patch: dict[str, object]) -> tuple[str, CoreRuntimeConfig]:
        profile, current = self.load_active()
        if profile == CORE_PROFILE:
            raise PermissionError("core profile is read-only")
        data = asdict(current)
        for key, value in patch.items():
            if key in data and value is not None:
                data[key] = value
        saved = self.save_profile(profile, CoreRuntimeConfig(**data))
        return profile, saved
