"""Node domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import math
from typing import Any

from elyha_core.i18n import tr
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import ensure_valid_id


class NodeType(str, Enum):
    CHAPTER = "chapter"
    GROUP = "group"
    BRANCH = "branch"
    MERGE = "merge"
    PARALLEL = "parallel"
    CHECKPOINT = "checkpoint"


class NodeStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    APPROVED = "approved"


@dataclass(slots=True)
class Node:
    """A plot node in the story graph."""

    id: str
    project_id: str
    type: NodeType
    title: str
    status: NodeStatus = NodeStatus.DRAFT
    storyline_id: str | None = None
    pos_x: float = 0.0
    pos_y: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.id = ensure_valid_id(self.id, field_name="node.id")
        self.project_id = ensure_valid_id(self.project_id, field_name="node.project_id")
        self.title = self.title.strip()
        if not self.title:
            raise ValueError(tr("err.node_title_empty"))
        if self.storyline_id is not None:
            if not isinstance(self.storyline_id, str):
                raise ValueError(tr("err.storyline_id_type"))
            normalized_storyline_id = self.storyline_id.strip()
            self.storyline_id = normalized_storyline_id or None
        self.pos_x = float(self.pos_x)
        self.pos_y = float(self.pos_y)
        if not math.isfinite(self.pos_x) or not math.isfinite(self.pos_y):
            raise ValueError(tr("err.node_positions_finite"))
        if not isinstance(self.metadata, dict):
            raise ValueError(tr("err.node_metadata_dict"))
