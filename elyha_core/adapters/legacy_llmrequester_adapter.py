"""Adapter bridge to legacy `LLMRequester/` implementation."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import sys
import types
from typing import Any

from elyha_core.adapters.llm_adapter import LLMRequest, LLMResponse


def _ensure_modulefolders_shims() -> None:
    """Install minimal ModuleFolders aliases required by legacy modules."""
    if "ModuleFolders" not in sys.modules:
        root_pkg = types.ModuleType("ModuleFolders")
        root_pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["ModuleFolders"] = root_pkg
    else:
        root_pkg = sys.modules["ModuleFolders"]
        if not hasattr(root_pkg, "__path__"):
            root_pkg.__path__ = []  # type: ignore[attr-defined]

    if "ModuleFolders.Base" not in sys.modules:
        base_pkg = types.ModuleType("ModuleFolders.Base")
        base_pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["ModuleFolders.Base"] = base_pkg
    else:
        base_pkg = sys.modules["ModuleFolders.Base"]
        if not hasattr(base_pkg, "__path__"):
            base_pkg.__path__ = []  # type: ignore[attr-defined]
    setattr(root_pkg, "Base", base_pkg)

    if "ModuleFolders.Base.Base" not in sys.modules:
        class _Status:
            STOPING = "STOPING"
            RUNNING = "RUNNING"

        class Base:
            STATUS = _Status
            work_status = _Status.RUNNING

            def load_config(self) -> dict[str, Any]:
                retry_count_text = str(os.getenv("ELYHA_LEGACY_RETRY_COUNT", "1")).strip()
                backoff_text = str(os.getenv("ELYHA_LEGACY_RETRY_BACKOFF", "0")).strip().lower()
                try:
                    retry_count = max(1, int(retry_count_text))
                except ValueError:
                    retry_count = 1
                enable_backoff = backoff_text in {"1", "true", "yes", "on"}
                return {
                    "retry_count": retry_count,
                    "enable_retry_backoff": enable_backoff,
                }

            def save_config(self, config: dict[str, Any]) -> None:
                _ = config

            def debug(self, *args: Any, **kwargs: Any) -> None:
                _ = args, kwargs

            def error(self, *args: Any, **kwargs: Any) -> None:
                _ = args, kwargs

            def print(self, *args: Any, **kwargs: Any) -> None:
                _ = args, kwargs

            def is_debug(self) -> bool:
                return False

        base_mod = types.ModuleType("ModuleFolders.Base.Base")
        setattr(base_mod, "Base", Base)
        sys.modules["ModuleFolders.Base.Base"] = base_mod
        setattr(base_pkg, "Base", Base)

    if "ModuleFolders.Infrastructure" not in sys.modules:
        infra_pkg = types.ModuleType("ModuleFolders.Infrastructure")
        infra_pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["ModuleFolders.Infrastructure"] = infra_pkg
    else:
        infra_pkg = sys.modules["ModuleFolders.Infrastructure"]
        if not hasattr(infra_pkg, "__path__"):
            infra_pkg.__path__ = []  # type: ignore[attr-defined]
    setattr(root_pkg, "Infrastructure", infra_pkg)

    llm_path = Path(__file__).resolve().parents[2] / "LLMRequester"
    llm_pkg_paths = [str(llm_path)] if llm_path.is_dir() else []
    if "ModuleFolders.Infrastructure.LLMRequester" not in sys.modules:
        llm_pkg = types.ModuleType("ModuleFolders.Infrastructure.LLMRequester")
        llm_pkg.__path__ = llm_pkg_paths  # type: ignore[attr-defined]
        sys.modules["ModuleFolders.Infrastructure.LLMRequester"] = llm_pkg
    else:
        llm_pkg = sys.modules["ModuleFolders.Infrastructure.LLMRequester"]
        llm_pkg.__path__ = llm_pkg_paths  # type: ignore[attr-defined]
    setattr(infra_pkg, "LLMRequester", llm_pkg)

    legacy_modules = [
        "ErrorClassifier",
        "ProviderFingerprint",
        "ModelConfigHelper",
        "LLMClientFactory",
        "OpenaiRequester",
        "GoogleRequester",
        "AnthropicRequester",
        "AmazonbedrockRequester",
        "CohereRequester",
        "DashscopeRequester",
        "LocalLLMRequester",
        "MurasakiRequester",
        "SakuraRequester",
        "LLMRequester",
    ]
    for module_name in legacy_modules:
        alias_name = f"ModuleFolders.Infrastructure.LLMRequester.{module_name}"
        if alias_name in sys.modules:
            continue
        try:
            local_mod = importlib.import_module(f"LLMRequester.{module_name}")
        except Exception:
            continue
        sys.modules[alias_name] = local_mod
        setattr(llm_pkg, module_name, local_mod)


def _map_error_code(text: str) -> str:
    message = text.lower()
    if any(k in message for k in ("api key", "unauthorized", "forbidden", "permission")):
        return "auth"
    if any(k in message for k in ("rate limit", "429", "too many requests", "quota")):
        return "rate_limit"
    if any(k in message for k in ("timeout", "timed out", "read timeout")):
        return "timeout"
    if any(k in message for k in ("network", "connection", "dns", "reset by peer")):
        return "network"
    if any(k in message for k in ("500", "502", "503", "504", "server")):
        return "server"
    if any(k in message for k in ("parse", "invalid json", "schema", "format")):
        return "content"
    return "generic"


@dataclass(slots=True)
class LegacyLLMRequesterAdapter:
    """Bridge adapter around historical LLMRequester request pipeline."""

    default_platform_config: dict[str, Any]

    provider_name: str = "legacy_llmrequester"

    def generate(self, request: LLMRequest) -> LLMResponse:
        _ensure_modulefolders_shims()
        try:
            module = importlib.import_module("LLMRequester.LLMRequester")
            requester_cls = getattr(module, "LLMRequester")
            requester = requester_cls()
        except Exception as exc:
            return LLMResponse(
                ok=False,
                content="",
                error_code="dependency_missing",
                error_message=f"legacy requester unavailable: {exc}",
                provider=self.provider_name,
            )

        platform_config = self.default_platform_config.copy()
        platform_config.update(request.platform_config)
        platform_config.setdefault(
            "target_platform",
            os.getenv("ELYHA_LEGACY_PLATFORM", "openai"),
        )
        platform_config.setdefault("api_url", os.getenv("ELYHA_API_URL", ""))
        platform_config.setdefault("api_key", os.getenv("ELYHA_API_KEY", ""))
        platform_config.setdefault("model_name", os.getenv("ELYHA_MODEL_NAME", ""))
        platform_config.setdefault("auto_complete", True)
        timeout_text = str(os.getenv("ELYHA_LLM_TIMEOUT", "30")).strip()
        try:
            request_timeout = max(5, int(timeout_text))
        except ValueError:
            request_timeout = 30
        platform_config.setdefault("request_timeout", request_timeout)
        message_payload = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        try:
            skip, think, content, prompt_tokens, completion_tokens = requester.sent_request(
                message_payload,
                request.system_prompt,
                platform_config,
            )
        except Exception as exc:
            text = str(exc)
            return LLMResponse(
                ok=False,
                content="",
                error_code=_map_error_code(text),
                error_message=text,
                provider=self.provider_name,
            )

        if skip:
            detail = f"{think} {content}".strip()
            return LLMResponse(
                ok=False,
                content="",
                reasoning=think or "",
                prompt_tokens=int(prompt_tokens),
                completion_tokens=int(completion_tokens),
                error_code=_map_error_code(detail),
                error_message=detail or "legacy requester failed",
                provider=self.provider_name,
            )

        return LLMResponse(
            ok=True,
            content=content or "",
            reasoning=think or "",
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            provider=self.provider_name,
        )
