"""Operation log domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from elyha_core.i18n import tr
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import ensure_valid_id


@dataclass(slots=True)
class Operation:
    """Append-only operation event for replay and audit."""

    id: str
    project_id: str
    revision: int
    op_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.id = ensure_valid_id(self.id, field_name="operation.id")
        self.project_id = ensure_valid_id(
            self.project_id, field_name="operation.project_id"
        )
        if self.revision < 0:
            raise ValueError(tr("err.operation_revision_non_negative"))
        self.op_type = self.op_type.strip()
        if not self.op_type:
            raise ValueError(tr("err.operation_op_type_empty"))
        if not isinstance(self.payload, dict):
            raise ValueError(tr("err.operation_payload_dict"))
