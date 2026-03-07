"""Story graph mutation and constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from elyha_core.i18n import tr
from elyha_core.models.edge import Edge
from elyha_core.models.node import Node, NodeStatus, NodeType
from elyha_core.models.operation import Operation
from elyha_core.models.project import Project
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id


@dataclass(slots=True)
class NodeCreate:
    """Input payload for creating a node."""

    title: str
    type: NodeType = NodeType.CHAPTER
    status: NodeStatus = NodeStatus.DRAFT
    storyline_id: str | None = None
    pos_x: float = 0.0
    pos_y: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    node_id: str | None = None


class GraphService:
    """Mutate graph state while enforcing global constraints."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def add_node(self, project_id: str, node_input: NodeCreate) -> Node:
        project = self._require_project(project_id)
        now = utc_now()
        node = Node(
            id=node_input.node_id or generate_id("node"),
            project_id=project_id,
            type=node_input.type,
            title=node_input.title,
            status=node_input.status,
            storyline_id=node_input.storyline_id,
            pos_x=node_input.pos_x,
            pos_y=node_input.pos_y,
            metadata=node_input.metadata.copy(),
            created_at=now,
            updated_at=now,
        )
        self.repository.create_node(node)
        self._record_graph_operation(
            project,
            op_type="graph_add_node",
            payload={
                "node_id": node.id,
                "node": self._serialize_node(node),
            },
        )
        return self.get_node(project_id, node.id)

    def update_node(
        self,
        project_id: str,
        node_id: str,
        patch: Mapping[str, Any],
    ) -> Node:
        project = self._require_project(project_id)
        current = self.get_node(project_id, node_id)
        node_type = current.type
        title = current.title
        status = current.status
        storyline_id = current.storyline_id
        pos_x = current.pos_x
        pos_y = current.pos_y
        metadata = current.metadata.copy()
        if "type" in patch:
            raw_type = patch["type"]
            node_type = raw_type if isinstance(raw_type, NodeType) else NodeType(raw_type)
        if "title" in patch:
            title = str(patch["title"])
        if "status" in patch:
            raw_status = patch["status"]
            status = (
                raw_status if isinstance(raw_status, NodeStatus) else NodeStatus(raw_status)
            )
        if "storyline_id" in patch:
            raw_storyline_id = patch["storyline_id"]
            if raw_storyline_id is not None and not isinstance(raw_storyline_id, str):
                raise ValueError(tr("err.storyline_id_type"))
            storyline_id = raw_storyline_id
        if "pos_x" in patch:
            pos_x = float(patch["pos_x"])
        if "pos_y" in patch:
            pos_y = float(patch["pos_y"])
        if "metadata" in patch:
            if not isinstance(patch["metadata"], dict):
                raise ValueError(tr("err.node_metadata_dict"))
            metadata = patch["metadata"].copy()
        updated = Node(
            id=current.id,
            project_id=current.project_id,
            type=node_type,
            title=title,
            status=status,
            storyline_id=storyline_id,
            pos_x=pos_x,
            pos_y=pos_y,
            metadata=metadata,
            created_at=current.created_at,
            updated_at=utc_now(),
        )
        self.repository.update_node(updated)
        self._record_graph_operation(
            project,
            op_type="graph_update_node",
            payload={
                "node_id": updated.id,
                "fields": sorted(patch.keys()),
                "node": self._serialize_node(updated),
            },
        )
        return self.get_node(project_id, node_id)

    def delete_node(self, project_id: str, node_id: str) -> None:
        project = self._require_project(project_id)
        _ = self.get_node(project_id, node_id)
        deleted = self.repository.delete_node(project_id, node_id)
        if not deleted:
            raise KeyError(tr("err.node_not_found", node_id=node_id))
        self._record_graph_operation(
            project,
            op_type="graph_delete_node",
            payload={"node_id": node_id},
        )

    def get_node(self, project_id: str, node_id: str) -> Node:
        node = self.repository.get_node(project_id, node_id)
        if node is None:
            raise KeyError(tr("err.node_not_found", node_id=node_id))
        return node

    def list_nodes(self, project_id: str) -> list[Node]:
        self._require_project(project_id)
        return self.repository.list_nodes(project_id)

    def add_edge(
        self,
        project_id: str,
        source_id: str,
        target_id: str,
        *,
        edge_id: str | None = None,
        label: str = "",
    ) -> Edge:
        project = self._require_project(project_id)
        source_node = self.get_node(project_id, source_id)
        _ = self.get_node(project_id, target_id)
        if self.repository.find_edge(project_id, source_id, target_id) is not None:
            raise ValueError(tr("err.duplicate_edge"))
        if not project.settings.allow_cycles and self._would_create_cycle(
            project_id, source_id, target_id
        ):
            raise ValueError(tr("err.cycle_detected"))
        narrative_order: int | None = None
        if source_node.type != NodeType.GROUP:
            narrative_order = len(self.repository.list_outgoing_edges(project_id, source_id)) + 1
        edge = Edge(
            id=edge_id or generate_id("edge"),
            project_id=project_id,
            source_id=source_id,
            target_id=target_id,
            label=label,
            narrative_order=narrative_order,
        )
        self.repository.create_edge(edge)
        self._record_graph_operation(
            project,
            op_type="graph_add_edge",
            payload={
                "edge_id": edge.id,
                "edge": self._serialize_edge(edge),
            },
        )
        return edge

    def delete_edge(self, project_id: str, edge_id: str) -> None:
        project = self._require_project(project_id)
        edge = self.repository.get_edge(project_id, edge_id)
        if edge is None:
            raise KeyError(tr("err.edge_not_found", edge_id=edge_id))
        deleted = self.repository.delete_edge(project_id, edge_id)
        if not deleted:
            raise KeyError(tr("err.edge_not_found", edge_id=edge_id))
        self._normalize_source_narrative_orders(project_id, edge.source_id)
        self._record_graph_operation(
            project,
            op_type="graph_delete_edge",
            payload={"edge_id": edge_id},
        )

    def list_edges(self, project_id: str) -> list[Edge]:
        self._require_project(project_id)
        self._normalize_project_narrative_orders(project_id)
        return self.repository.list_edges(project_id)

    def reorder_outgoing_edges(
        self,
        project_id: str,
        source_id: str,
        ordered_edge_ids: list[str],
    ) -> list[Edge]:
        project = self._require_project(project_id)
        source_node = self.get_node(project_id, source_id)
        if source_node.type == NodeType.GROUP:
            raise ValueError(tr("err.group_branch_order_not_supported"))
        outgoing = self.repository.list_outgoing_edges(project_id, source_id)
        if not outgoing:
            return []
        current_ids = {edge.id for edge in outgoing}
        seen: set[str] = set()
        normalized_input: list[str] = []
        for edge_id in ordered_edge_ids:
            if edge_id in seen:
                continue
            if edge_id not in current_ids:
                raise ValueError(tr("err.edge_reorder_ids_invalid"))
            normalized_input.append(edge_id)
            seen.add(edge_id)
        tail = [edge.id for edge in outgoing if edge.id not in seen]
        final_order = normalized_input + tail
        for index, edge_id in enumerate(final_order, start=1):
            self.repository.update_edge_narrative_order(project_id, edge_id, index)
        self._record_graph_operation(
            project,
            op_type="graph_reorder_edges",
            payload={"source_id": source_id, "edge_ids": final_order},
        )
        latest = self.repository.list_outgoing_edges(project_id, source_id)
        edge_by_id = {edge.id: edge for edge in latest}
        return [edge_by_id[edge_id] for edge_id in final_order if edge_id in edge_by_id]

    def _normalize_project_narrative_orders(self, project_id: str) -> None:
        nodes = self.repository.list_nodes(project_id)
        for node in nodes:
            self._normalize_source_narrative_orders(project_id, node.id)

    def _normalize_source_narrative_orders(self, project_id: str, source_id: str) -> None:
        source_node = self.repository.get_node(project_id, source_id)
        if source_node is None:
            return
        outgoing = self.repository.list_outgoing_edges(project_id, source_id)
        if source_node.type == NodeType.GROUP:
            for edge in outgoing:
                if edge.narrative_order is not None:
                    self.repository.update_edge_narrative_order(project_id, edge.id, None)
            return
        for index, edge in enumerate(outgoing, start=1):
            if edge.narrative_order != index:
                self.repository.update_edge_narrative_order(project_id, edge.id, index)

    def _would_create_cycle(self, project_id: str, source_id: str, target_id: str) -> bool:
        # A new edge source->target creates a cycle iff source is reachable from target.
        adjacency: dict[str, set[str]] = {}
        for edge in self.repository.list_edges(project_id):
            adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
        stack = [target_id]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == source_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency.get(current, ()))
        return False

    def _require_project(self, project_id: str) -> Project:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(tr("err.project_not_found", project_id=project_id))
        return project

    def _record_graph_operation(
        self,
        project: Project,
        *,
        op_type: str,
        payload: dict[str, object],
    ) -> None:
        project.active_revision += 1
        project.updated_at = utc_now()
        self.repository.update_project(project)
        operation = Operation(
            id=generate_id("op"),
            project_id=project.id,
            revision=project.active_revision,
            op_type=op_type,
            payload=payload,
        )
        self.repository.create_operation(operation)

    def _serialize_node(self, node: Node) -> dict[str, Any]:
        return {
            "id": node.id,
            "project_id": node.project_id,
            "type": node.type.value,
            "title": node.title,
            "status": node.status.value,
            "storyline_id": node.storyline_id,
            "pos_x": node.pos_x,
            "pos_y": node.pos_y,
            "metadata": node.metadata.copy(),
            "created_at": self._dump_time(node.created_at),
            "updated_at": self._dump_time(node.updated_at),
        }

    def _serialize_edge(self, edge: Edge) -> dict[str, Any]:
        return {
            "id": edge.id,
            "project_id": edge.project_id,
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "label": edge.label,
            "narrative_order": edge.narrative_order,
            "created_at": self._dump_time(edge.created_at),
        }

    def _dump_time(self, value: datetime) -> str:
        return value.isoformat()
