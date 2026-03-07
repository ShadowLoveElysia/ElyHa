"""Snapshot create/list/rollback service."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from elyha_core.i18n import tr
from elyha_core.models.edge import Edge
from elyha_core.models.node import Node, NodeStatus, NodeType
from elyha_core.models.project import Project, ProjectSettings
from elyha_core.models.snapshot import Snapshot
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id


class SnapshotService:
    """Manage project snapshots and rollback via replay."""

    def __init__(
        self,
        repository: SQLiteRepository,
        *,
        snapshot_root: str | Path = "snapshots",
    ) -> None:
        self.repository = repository
        self.snapshot_root = Path(snapshot_root)
        self.snapshot_root.mkdir(parents=True, exist_ok=True)

    def create_snapshot(self, project_id: str) -> Snapshot:
        project = self._require_project(project_id)
        nodes = self.repository.list_nodes(project_id)
        edges = self.repository.list_edges(project_id)
        snapshot_id = generate_id("snap")
        revision = project.active_revision
        out_dir = self.snapshot_root / project_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{revision:08d}_{snapshot_id}.json"
        payload = {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "project": self._serialize_project(project),
            "nodes": [self._serialize_node(node) for node in nodes],
            "edges": [self._serialize_edge(edge) for edge in edges],
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        snapshot = Snapshot(
            id=snapshot_id,
            project_id=project_id,
            revision=revision,
            path=str(out_path),
        )
        self.repository.create_snapshot(snapshot)
        return snapshot

    def list_snapshots(self, project_id: str) -> list[Snapshot]:
        _ = self._require_project(project_id)
        return self.repository.list_snapshots(project_id)

    def rollback(self, project_id: str, revision: int) -> Project:
        project = self._require_project(project_id)
        if revision < 0:
            raise ValueError(tr("err.revision_non_negative"))
        if revision > project.active_revision:
            raise ValueError(
                tr(
                    "err.target_revision_exceeds",
                    revision=revision,
                    current=project.active_revision,
                )
            )
        snapshot = self.repository.get_latest_snapshot_before_or_equal(project_id, revision)
        if snapshot is None:
            raise ValueError(
                tr(
                    "err.no_snapshot_before_revision",
                    revision=revision,
                    project_id=project_id,
                )
            )

        base_project, base_nodes, base_edges = self._load_snapshot(snapshot.path)
        replay_ops = self.repository.list_operations_range(
            project_id,
            start_revision_exclusive=snapshot.revision,
            end_revision_inclusive=revision,
        )
        restored_project, restored_nodes, restored_edges = self._replay_operations(
            base_project,
            base_nodes,
            base_edges,
            replay_ops,
            target_revision=revision,
        )
        self.repository.replace_project_state(restored_project, restored_nodes, restored_edges)
        reloaded = self.repository.get_project(project_id)
        if reloaded is None:
            raise RuntimeError(tr("err.rollback_missing_project"))
        return reloaded

    def _require_project(self, project_id: str) -> Project:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(tr("err.project_not_found", project_id=project_id))
        return project

    def _load_snapshot(self, snapshot_path: str) -> tuple[Project, list[Node], list[Edge]]:
        payload = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        project = self._deserialize_project(payload["project"])
        nodes = [self._deserialize_node(item) for item in payload.get("nodes", [])]
        edges = [self._deserialize_edge(item) for item in payload.get("edges", [])]
        return project, nodes, edges

    def _replay_operations(
        self,
        project: Project,
        nodes: list[Node],
        edges: list[Edge],
        operations,
        *,
        target_revision: int,
    ) -> tuple[Project, list[Node], list[Edge]]:
        node_map: dict[str, Node] = {node.id: node for node in nodes}
        edge_map: dict[str, Edge] = {edge.id: edge for edge in edges}
        for operation in operations:
            payload = operation.payload
            if operation.op_type == "project_rename":
                new_title = payload.get("new_title")
                if isinstance(new_title, str) and new_title.strip():
                    project.title = new_title.strip()
            elif operation.op_type == "project_update_settings":
                project.settings = ProjectSettings(
                    allow_cycles=bool(payload.get("allow_cycles", project.settings.allow_cycles)),
                    auto_snapshot_minutes=int(
                        payload.get(
                            "auto_snapshot_minutes",
                            project.settings.auto_snapshot_minutes,
                        )
                    ),
                    auto_snapshot_operations=int(
                        payload.get(
                            "auto_snapshot_operations",
                            project.settings.auto_snapshot_operations,
                        )
                    ),
                )
            elif operation.op_type in {"graph_add_node", "graph_update_node"}:
                node_raw = payload.get("node")
                if isinstance(node_raw, dict):
                    node = self._deserialize_node(node_raw)
                    node_map[node.id] = node
            elif operation.op_type == "graph_delete_node":
                node_id = payload.get("node_id")
                if isinstance(node_id, str):
                    node_map.pop(node_id, None)
                    edge_map = {
                        edge_id: edge
                        for edge_id, edge in edge_map.items()
                        if edge.source_id != node_id and edge.target_id != node_id
                    }
            elif operation.op_type == "graph_add_edge":
                edge_raw = payload.get("edge")
                if isinstance(edge_raw, dict):
                    edge = self._deserialize_edge(edge_raw)
                    if edge.source_id in node_map and edge.target_id in node_map:
                        edge_map[edge.id] = edge
            elif operation.op_type == "graph_delete_edge":
                edge_id = payload.get("edge_id")
                if isinstance(edge_id, str):
                    edge_map.pop(edge_id, None)

        project.active_revision = target_revision
        project.updated_at = utc_now()
        remaining_nodes = sorted(
            node_map.values(),
            key=lambda item: (item.created_at, item.id),
        )
        remaining_node_ids = {node.id for node in remaining_nodes}
        remaining_edges = [
            edge
            for edge in sorted(edge_map.values(), key=lambda item: (item.created_at, item.id))
            if edge.source_id in remaining_node_ids and edge.target_id in remaining_node_ids
        ]
        return project, remaining_nodes, remaining_edges

    def _serialize_project(self, project: Project) -> dict[str, Any]:
        return {
            "id": project.id,
            "title": project.title,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
            "active_revision": project.active_revision,
            "settings": asdict(project.settings),
        }

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
            "metadata": node.metadata,
            "created_at": node.created_at.isoformat(),
            "updated_at": node.updated_at.isoformat(),
        }

    def _serialize_edge(self, edge: Edge) -> dict[str, Any]:
        return {
            "id": edge.id,
            "project_id": edge.project_id,
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "label": edge.label,
            "narrative_order": edge.narrative_order,
            "created_at": edge.created_at.isoformat(),
        }

    def _deserialize_project(self, payload: dict[str, Any]) -> Project:
        return Project(
            id=str(payload["id"]),
            title=str(payload["title"]),
            created_at=self._load_time(payload["created_at"]),
            updated_at=self._load_time(payload["updated_at"]),
            active_revision=int(payload["active_revision"]),
            settings=ProjectSettings(**payload["settings"]),
        )

    def _deserialize_node(self, payload: dict[str, Any]) -> Node:
        return Node(
            id=str(payload["id"]),
            project_id=str(payload["project_id"]),
            type=NodeType(payload["type"]),
            title=str(payload["title"]),
            status=NodeStatus(payload["status"]),
            storyline_id=payload.get("storyline_id"),
            pos_x=float(payload.get("pos_x", 0.0)),
            pos_y=float(payload.get("pos_y", 0.0)),
            metadata=dict(payload.get("metadata", {})),
            created_at=self._load_time(payload["created_at"]),
            updated_at=self._load_time(payload["updated_at"]),
        )

    def _deserialize_edge(self, payload: dict[str, Any]) -> Edge:
        raw_order = payload.get("narrative_order")
        return Edge(
            id=str(payload["id"]),
            project_id=str(payload["project_id"]),
            source_id=str(payload["source_id"]),
            target_id=str(payload["target_id"]),
            label=str(payload.get("label", "")),
            narrative_order=int(raw_order) if raw_order is not None else None,
            created_at=self._load_time(payload["created_at"]),
        )

    def _load_time(self, value: Any) -> datetime:
        if not isinstance(value, str):
            raise ValueError(tr("err.invalid_datetime_payload", value=repr(value)))
        return datetime.fromisoformat(value)
