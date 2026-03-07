"""Edge domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from elyha_core.i18n import tr
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import ensure_valid_id


@dataclass(slots=True)
class Edge:
    """Connection between two nodes."""

    id: str
    project_id: str
    source_id: str
    target_id: str
    label: str = ""
    narrative_order: int | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.id = ensure_valid_id(self.id, field_name="edge.id")
        self.project_id = ensure_valid_id(self.project_id, field_name="edge.project_id")
        self.source_id = ensure_valid_id(self.source_id, field_name="edge.source_id")
        self.target_id = ensure_valid_id(self.target_id, field_name="edge.target_id")
        if self.source_id == self.target_id:
            raise ValueError(tr("err.edge_self_loop"))
        self.label = self.label.strip()
        if self.narrative_order is not None:
            self.narrative_order = int(self.narrative_order)
            if self.narrative_order <= 0:
                self.narrative_order = None
