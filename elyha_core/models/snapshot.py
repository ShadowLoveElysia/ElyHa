"""Snapshot metadata model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from elyha_core.i18n import tr
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import ensure_valid_id


@dataclass(slots=True)
class Snapshot:
    """Snapshot record for project rollback."""

    id: str
    project_id: str
    revision: int
    path: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.id = ensure_valid_id(self.id, field_name="snapshot.id")
        self.project_id = ensure_valid_id(
            self.project_id, field_name="snapshot.project_id"
        )
        self.path = self.path.strip()
        if not self.path:
            raise ValueError(tr("err.snapshot_path_empty"))
        if self.revision < 0:
            raise ValueError(tr("err.snapshot_revision_non_negative"))
