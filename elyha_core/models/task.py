"""Task domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from elyha_core.i18n import tr
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import ensure_valid_id


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Task:
    """Track asynchronous generate/review work."""

    id: str
    project_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    node_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    revision: int = 0
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.id = ensure_valid_id(self.id, field_name="task.id")
        self.project_id = ensure_valid_id(self.project_id, field_name="task.project_id")
        if self.node_id is not None:
            self.node_id = ensure_valid_id(self.node_id, field_name="task.node_id")
        self.task_type = self.task_type.strip()
        if not self.task_type:
            raise ValueError(tr("err.task_type_empty"))
        if self.revision < 0:
            raise ValueError(tr("err.task_revision_non_negative"))
        if self.status in {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            if self.finished_at is None:
                self.finished_at = utc_now()
