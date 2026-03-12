"""Project domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from elyha_core.i18n import tr
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import ensure_valid_id

SYSTEM_PROMPT_TEXT_MAX_CHARS = 4000


def _normalize_prompt_text(value: object, *, limit: int = SYSTEM_PROMPT_TEXT_MAX_CHARS) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > limit:
        return text[:limit]
    return text


def _coerce_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return fallback


def _coerce_positive_int(value: object, fallback: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _coerce_text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value)


@dataclass(slots=True)
class ProjectSettings:
    """Project-level behavior toggles."""

    allow_cycles: bool = False
    auto_snapshot_minutes: int = 5
    auto_snapshot_operations: int = 50
    system_prompt_style: str = ""
    system_prompt_forbidden: str = ""
    system_prompt_notes: str = ""

    def __post_init__(self) -> None:
        if self.auto_snapshot_minutes <= 0:
            raise ValueError(tr("err.auto_snapshot_minutes_positive"))
        if self.auto_snapshot_operations <= 0:
            raise ValueError(tr("err.auto_snapshot_operations_positive"))
        self.system_prompt_style = _normalize_prompt_text(self.system_prompt_style)
        self.system_prompt_forbidden = _normalize_prompt_text(self.system_prompt_forbidden)
        self.system_prompt_notes = _normalize_prompt_text(self.system_prompt_notes)


def project_settings_from_payload(raw: Any) -> ProjectSettings:
    """Decode project settings from storage payload with legacy key compatibility."""
    payload = raw if isinstance(raw, dict) else {}

    system_prompt_style = _coerce_text(payload.get("system_prompt_style"), "")
    system_prompt_forbidden = _coerce_text(payload.get("system_prompt_forbidden"), "")
    system_prompt_notes = _coerce_text(payload.get("system_prompt_notes"), "")

    # Legacy keys from older workflow-doc based schemas.
    legacy_constitution = _coerce_text(payload.get("constitution_markdown"), "")
    legacy_clarify = _coerce_text(payload.get("clarify_markdown"), "")
    legacy_specification = _coerce_text(payload.get("specification_markdown"), "")
    legacy_plan = _coerce_text(payload.get("plan_markdown"), "")

    if not system_prompt_style and legacy_constitution:
        system_prompt_style = legacy_constitution
    if not system_prompt_forbidden and legacy_clarify:
        system_prompt_forbidden = legacy_clarify
    if not system_prompt_notes:
        legacy_notes_parts: list[str] = []
        if legacy_specification.strip():
            legacy_notes_parts.append("[Specification]\n" + legacy_specification.strip())
        if legacy_plan.strip():
            legacy_notes_parts.append("[Plan]\n" + legacy_plan.strip())
        if legacy_notes_parts:
            system_prompt_notes = "\n\n".join(legacy_notes_parts)

    return ProjectSettings(
        allow_cycles=_coerce_bool(payload.get("allow_cycles"), False),
        auto_snapshot_minutes=_coerce_positive_int(payload.get("auto_snapshot_minutes"), 5),
        auto_snapshot_operations=_coerce_positive_int(payload.get("auto_snapshot_operations"), 50),
        system_prompt_style=system_prompt_style,
        system_prompt_forbidden=system_prompt_forbidden,
        system_prompt_notes=system_prompt_notes,
    )


@dataclass(slots=True)
class Project:
    """Top-level project metadata."""

    id: str
    title: str
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    active_revision: int = 0
    settings: ProjectSettings = field(default_factory=ProjectSettings)

    def __post_init__(self) -> None:
        self.id = ensure_valid_id(self.id, field_name="project.id")
        self.title = self.title.strip()
        if not self.title:
            raise ValueError(tr("err.project_title_empty"))
        if self.active_revision < 0:
            raise ValueError(tr("err.project_active_revision_non_negative"))
