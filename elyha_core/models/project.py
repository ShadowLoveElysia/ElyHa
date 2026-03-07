"""Project domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from elyha_core.i18n import tr
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import ensure_valid_id


@dataclass(slots=True)
class ProjectSettings:
    """Project-level behavior toggles."""

    allow_cycles: bool = False
    auto_snapshot_minutes: int = 5
    auto_snapshot_operations: int = 50

    def __post_init__(self) -> None:
        if self.auto_snapshot_minutes <= 0:
            raise ValueError(tr("err.auto_snapshot_minutes_positive"))
        if self.auto_snapshot_operations <= 0:
            raise ValueError(tr("err.auto_snapshot_operations_positive"))


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
