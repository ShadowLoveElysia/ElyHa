"""Repository backed by SQLite tables."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import sqlite3
from typing import Any

from elyha_core.i18n import tr
from elyha_core.models.edge import Edge
from elyha_core.models.node import Node, NodeStatus, NodeType
from elyha_core.models.operation import Operation
from elyha_core.models.project import Project, project_settings_from_payload
from elyha_core.models.snapshot import Snapshot
from elyha_core.models.task import Task, TaskStatus
from elyha_core.storage.sqlite_store import SQLiteStore
from elyha_core.utils.clock import utc_now


def _dump_time(value: datetime) -> str:
    return value.isoformat()


def _load_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SQLiteRepository:
    """CRUD operations for project graph and operation logs."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        self.store.initialize()

    def _decode_project(self, row: sqlite3.Row) -> Project:
        try:
            settings_raw = json.loads(row["settings_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            settings_raw = {}
        settings = project_settings_from_payload(settings_raw)
        return Project(
            id=row["id"],
            title=row["title"],
            created_at=_load_time(row["created_at"]),
            updated_at=_load_time(row["updated_at"]),
            active_revision=row["active_revision"],
            settings=settings,
        )

    def _decode_node(self, row: sqlite3.Row) -> Node:
        return Node(
            id=row["id"],
            project_id=row["project_id"],
            type=NodeType(row["type"]),
            title=row["title"],
            status=NodeStatus(row["status"]),
            storyline_id=row["storyline_id"],
            pos_x=row["pos_x"],
            pos_y=row["pos_y"],
            metadata=json.loads(row["metadata_json"]),
            created_at=_load_time(row["created_at"]),
            updated_at=_load_time(row["updated_at"]),
        )

    def _decode_edge(self, row: sqlite3.Row) -> Edge:
        raw_order = row["narrative_order"] if "narrative_order" in row.keys() else None
        return Edge(
            id=row["id"],
            project_id=row["project_id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            label=row["label"],
            narrative_order=int(raw_order) if raw_order is not None else None,
            created_at=_load_time(row["created_at"]),
        )

    def _decode_operation(self, row: sqlite3.Row) -> Operation:
        return Operation(
            id=row["id"],
            project_id=row["project_id"],
            revision=row["revision"],
            op_type=row["op_type"],
            payload=json.loads(row["payload_json"]),
            created_at=_load_time(row["created_at"]),
        )

    def _decode_snapshot(self, row: sqlite3.Row) -> Snapshot:
        return Snapshot(
            id=row["id"],
            project_id=row["project_id"],
            revision=row["revision"],
            path=row["path"],
            created_at=_load_time(row["created_at"]),
        )

    def _decode_task(self, row: sqlite3.Row) -> Task:
        started_at = _load_time(row["started_at"]) if row["started_at"] else None
        finished_at = _load_time(row["finished_at"]) if row["finished_at"] else None
        return Task(
            id=row["id"],
            project_id=row["project_id"],
            task_type=row["task_type"],
            status=TaskStatus(row["status"]),
            node_id=row["node_id"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            started_at=started_at,
            finished_at=finished_at,
            revision=row["revision"],
            created_at=_load_time(row["created_at"]),
        )

    def create_project(self, project: Project) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projects(
                    id, title, created_at, updated_at, active_revision, settings_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.title,
                    _dump_time(project.created_at),
                    _dump_time(project.updated_at),
                    project.active_revision,
                    json.dumps(asdict(project.settings), sort_keys=True),
                ),
            )

    def update_project(self, project: Project) -> None:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE projects
                SET title = ?, updated_at = ?, active_revision = ?, settings_json = ?
                WHERE id = ?
                """,
                (
                    project.title,
                    _dump_time(project.updated_at),
                    project.active_revision,
                    json.dumps(asdict(project.settings), sort_keys=True),
                    project.id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(tr("err.project_not_found", project_id=project.id))

    def get_project(self, project_id: str) -> Project | None:
        with self.store.read_only() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return self._decode_project(row) if row else None

    def list_projects(self) -> list[Project]:
        with self.store.read_only() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._decode_project(row) for row in rows]

    def delete_project(self, project_id: str) -> bool:
        with self.store.transaction() as conn:
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cursor.rowcount > 0

    def create_node(self, node: Node) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO nodes(
                    id, project_id, type, title, status, storyline_id, pos_x, pos_y,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.id,
                    node.project_id,
                    node.type.value,
                    node.title,
                    node.status.value,
                    node.storyline_id,
                    node.pos_x,
                    node.pos_y,
                    json.dumps(node.metadata, sort_keys=True),
                    _dump_time(node.created_at),
                    _dump_time(node.updated_at),
                ),
            )

    def update_node(self, node: Node) -> None:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE nodes
                SET type = ?, title = ?, status = ?, storyline_id = ?, pos_x = ?, pos_y = ?,
                    metadata_json = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    node.type.value,
                    node.title,
                    node.status.value,
                    node.storyline_id,
                    node.pos_x,
                    node.pos_y,
                    json.dumps(node.metadata, sort_keys=True),
                    _dump_time(node.updated_at),
                    node.id,
                    node.project_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(tr("err.node_not_found", node_id=node.id))

    def get_node(self, project_id: str, node_id: str) -> Node | None:
        with self.store.read_only() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ? AND project_id = ?",
                (node_id, project_id),
            ).fetchone()
        return self._decode_node(row) if row else None

    def list_nodes(self, project_id: str) -> list[Node]:
        with self.store.read_only() as conn:
            rows = conn.execute(
                "SELECT * FROM nodes WHERE project_id = ? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return [self._decode_node(row) for row in rows]

    def delete_node(self, project_id: str, node_id: str) -> bool:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM nodes WHERE id = ? AND project_id = ?",
                (node_id, project_id),
            )
            return cursor.rowcount > 0

    def create_edge(self, edge: Edge) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO edges(
                    id, project_id, source_id, target_id, label, narrative_order, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge.id,
                    edge.project_id,
                    edge.source_id,
                    edge.target_id,
                    edge.label,
                    edge.narrative_order,
                    _dump_time(edge.created_at),
                ),
            )

    def get_edge(self, project_id: str, edge_id: str) -> Edge | None:
        with self.store.read_only() as conn:
            row = conn.execute(
                "SELECT * FROM edges WHERE id = ? AND project_id = ?",
                (edge_id, project_id),
            ).fetchone()
        return self._decode_edge(row) if row else None

    def find_edge(self, project_id: str, source_id: str, target_id: str) -> Edge | None:
        with self.store.read_only() as conn:
            row = conn.execute(
                """
                SELECT * FROM edges
                WHERE project_id = ? AND source_id = ? AND target_id = ?
                """,
                (project_id, source_id, target_id),
            ).fetchone()
        return self._decode_edge(row) if row else None

    def list_edges(self, project_id: str) -> list[Edge]:
        with self.store.read_only() as conn:
            rows = conn.execute(
                "SELECT * FROM edges WHERE project_id = ? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return [self._decode_edge(row) for row in rows]

    def list_outgoing_edges(self, project_id: str, source_id: str) -> list[Edge]:
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT * FROM edges
                WHERE project_id = ? AND source_id = ?
                ORDER BY
                    CASE WHEN narrative_order IS NULL THEN 1 ELSE 0 END ASC,
                    narrative_order ASC,
                    created_at ASC,
                    id ASC
                """,
                (project_id, source_id),
            ).fetchall()
        return [self._decode_edge(row) for row in rows]

    def update_edge_narrative_order(
        self,
        project_id: str,
        edge_id: str,
        narrative_order: int | None,
    ) -> None:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE edges
                SET narrative_order = ?
                WHERE id = ? AND project_id = ?
                """,
                (narrative_order, edge_id, project_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(tr("err.edge_not_found", edge_id=edge_id))

    def delete_edge(self, project_id: str, edge_id: str) -> bool:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM edges WHERE id = ? AND project_id = ?",
                (edge_id, project_id),
            )
            return cursor.rowcount > 0

    def create_operation(self, operation: Operation) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO operation_logs(id, project_id, revision, op_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    operation.id,
                    operation.project_id,
                    operation.revision,
                    operation.op_type,
                    json.dumps(operation.payload, sort_keys=True),
                    _dump_time(operation.created_at),
                ),
            )

    def list_operations(
        self,
        project_id: str,
        *,
        limit: int | None = None,
    ) -> list[Operation]:
        sql = """
            SELECT * FROM operation_logs
            WHERE project_id = ?
            ORDER BY revision DESC, created_at DESC
        """
        params: list[Any] = [project_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._decode_operation(row) for row in rows]

    def list_operations_range(
        self,
        project_id: str,
        *,
        start_revision_exclusive: int,
        end_revision_inclusive: int,
    ) -> list[Operation]:
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT * FROM operation_logs
                WHERE project_id = ?
                  AND revision > ?
                  AND revision <= ?
                ORDER BY revision ASC, created_at ASC
                """,
                (project_id, start_revision_exclusive, end_revision_inclusive),
            ).fetchall()
        return [self._decode_operation(row) for row in rows]

    def create_snapshot(self, snapshot: Snapshot) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO snapshots(id, project_id, revision, path, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.project_id,
                    snapshot.revision,
                    snapshot.path,
                    _dump_time(snapshot.created_at),
                ),
            )

    def list_snapshots(self, project_id: str) -> list[Snapshot]:
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT * FROM snapshots
                WHERE project_id = ?
                ORDER BY revision DESC, created_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [self._decode_snapshot(row) for row in rows]

    def get_latest_snapshot_before_or_equal(
        self,
        project_id: str,
        revision: int,
    ) -> Snapshot | None:
        with self.store.read_only() as conn:
            row = conn.execute(
                """
                SELECT * FROM snapshots
                WHERE project_id = ? AND revision <= ?
                ORDER BY revision DESC, created_at DESC
                LIMIT 1
                """,
                (project_id, revision),
            ).fetchone()
        return self._decode_snapshot(row) if row else None

    def replace_project_state(
        self,
        project: Project,
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        """Replace project graph state atomically without writing operation logs."""
        with self.store.transaction() as conn:
            conn.execute(
                """
                UPDATE projects
                SET title = ?, created_at = ?, updated_at = ?, active_revision = ?, settings_json = ?
                WHERE id = ?
                """,
                (
                    project.title,
                    _dump_time(project.created_at),
                    _dump_time(project.updated_at),
                    project.active_revision,
                    json.dumps(asdict(project.settings), sort_keys=True),
                    project.id,
                ),
            )
            conn.execute("DELETE FROM edges WHERE project_id = ?", (project.id,))
            conn.execute("DELETE FROM nodes WHERE project_id = ?", (project.id,))

            for node in nodes:
                conn.execute(
                    """
                    INSERT INTO nodes(
                        id, project_id, type, title, status, storyline_id, pos_x, pos_y,
                        metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node.id,
                        node.project_id,
                        node.type.value,
                        node.title,
                        node.status.value,
                        node.storyline_id,
                        node.pos_x,
                        node.pos_y,
                        json.dumps(node.metadata, sort_keys=True),
                        _dump_time(node.created_at),
                        _dump_time(node.updated_at),
                    ),
                )

            for edge in edges:
                conn.execute(
                    """
                    INSERT INTO edges(
                        id, project_id, source_id, target_id, label, narrative_order, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge.id,
                        edge.project_id,
                        edge.source_id,
                        edge.target_id,
                        edge.label,
                        edge.narrative_order,
                        _dump_time(edge.created_at),
                    ),
                )

    def list_node_chunks(self, node_id: str) -> list[str]:
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT content FROM node_chunks
                WHERE node_id = ?
                ORDER BY chunk_index ASC
                """,
                (node_id,),
            ).fetchall()
        return [str(row["content"]) for row in rows]

    def list_node_chunk_records(self, node_id: str) -> list[dict[str, Any]]:
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT chunk_index, content, token_estimate, summary
                FROM node_chunks
                WHERE node_id = ?
                ORDER BY chunk_index ASC
                """,
                (node_id,),
            ).fetchall()
        return [
            {
                "node_id": str(node_id),
                "chunk_index": int(row["chunk_index"]),
                "content": str(row["content"]),
                "token_estimate": int(row["token_estimate"]),
                "summary": str(row["summary"]),
            }
            for row in rows
        ]

    def list_project_chunk_records(
        self,
        project_id: str,
        *,
        node_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        clean_node_ids = [str(item).strip() for item in (node_ids or []) if str(item).strip()]
        params: list[Any] = [project_id]
        sql = """
            SELECT n.id AS node_id, c.chunk_index, c.content, c.token_estimate, c.summary
            FROM node_chunks AS c
            INNER JOIN nodes AS n ON n.id = c.node_id
            WHERE n.project_id = ?
        """
        if clean_node_ids:
            placeholders = ",".join("?" for _ in clean_node_ids)
            sql += f" AND n.id IN ({placeholders})"
            params.extend(clean_node_ids)
        sql += " ORDER BY n.updated_at DESC, n.id ASC, c.chunk_index ASC"
        with self.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            {
                "node_id": str(row["node_id"]),
                "chunk_index": int(row["chunk_index"]),
                "content": str(row["content"]),
                "token_estimate": int(row["token_estimate"]),
                "summary": str(row["summary"]),
            }
            for row in rows
        ]

    def replace_node_chunks(self, node_id: str, chunks: list[str]) -> None:
        with self.store.transaction() as conn:
            conn.execute("DELETE FROM node_chunks WHERE node_id = ?", (node_id,))
            for index, content in enumerate(chunks):
                content_text = content.strip()
                if not content_text:
                    continue
                conn.execute(
                    """
                    INSERT INTO node_chunks(node_id, chunk_index, content, token_estimate, summary)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        index,
                        content_text,
                        max(1, len(content_text) // 4),
                        content_text[:120],
                    ),
                )

    def create_task(self, task: Task) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tasks(
                    id, project_id, node_id, task_type, status,
                    error_code, error_message, started_at, finished_at, revision, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.project_id,
                    task.node_id,
                    task.task_type,
                    task.status.value,
                    task.error_code,
                    task.error_message,
                    _dump_time(task.started_at) if task.started_at else None,
                    _dump_time(task.finished_at) if task.finished_at else None,
                    task.revision,
                    _dump_time(task.created_at),
                ),
            )

    def update_task(self, task: Task) -> None:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = ?, error_code = ?, error_message = ?, started_at = ?, finished_at = ?, revision = ?
                WHERE id = ?
                """,
                (
                    task.status.value,
                    task.error_code,
                    task.error_message,
                    _dump_time(task.started_at) if task.started_at else None,
                    _dump_time(task.finished_at) if task.finished_at else None,
                    task.revision,
                    task.id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(tr("err.task_not_found", task_id=task.id))

    def get_task(self, task_id: str) -> Task | None:
        with self.store.read_only() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._decode_task(row) if row else None

    def list_tasks(
        self,
        project_id: str,
        *,
        status: TaskStatus | None = None,
        limit: int | None = None,
    ) -> list[Task]:
        sql = """
            SELECT * FROM tasks
            WHERE project_id = ?
        """
        params: list[Any] = [project_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        sql += " ORDER BY created_at DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._decode_task(row) for row in rows]

    def create_agent_loop_rounds(self, thread_id: str, rounds: list[dict[str, Any]]) -> None:
        clean_thread = str(thread_id or "").strip()
        if not clean_thread or not rounds:
            return
        with self.store.transaction() as conn:
            for item in rounds:
                round_no = max(1, int(item.get("round_no", 1)))
                conn.execute(
                    """
                    INSERT INTO agent_loop_rounds(
                        thread_id, round_no, task_type, agent,
                        prompt_hash, prompt_tokens, completion_tokens, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_thread,
                        round_no,
                        str(item.get("task_type", "") or ""),
                        str(item.get("agent", "") or ""),
                        str(item.get("prompt_hash", "") or ""),
                        max(0, int(item.get("prompt_tokens", 0))),
                        max(0, int(item.get("completion_tokens", 0))),
                        str(item.get("status", "") or ""),
                        str(item.get("created_at", "") or ""),
                    ),
                )

    def create_agent_tool_calls(self, thread_id: str, calls: list[dict[str, Any]]) -> None:
        clean_thread = str(thread_id or "").strip()
        if not clean_thread or not calls:
            return
        with self.store.transaction() as conn:
            for item in calls:
                round_no = max(1, int(item.get("round_no", 1)))
                args = item.get("args")
                if not isinstance(args, dict):
                    args = {}
                result_meta = item.get("result_meta")
                if not isinstance(result_meta, dict):
                    result_meta = {}
                conn.execute(
                    """
                    INSERT INTO agent_tool_calls(
                        thread_id, round_no, task_type, agent,
                        tool_name, args_json, result_meta_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_thread,
                        round_no,
                        str(item.get("task_type", "") or ""),
                        str(item.get("agent", "") or ""),
                        str(item.get("tool_name", "") or ""),
                        json.dumps(args, ensure_ascii=False, sort_keys=True),
                        json.dumps(result_meta, ensure_ascii=False, sort_keys=True),
                        str(item.get("created_at", "") or ""),
                    ),
                )

    def create_agent_loop_metrics(self, thread_id: str, metrics: list[dict[str, Any]]) -> None:
        clean_thread = str(thread_id or "").strip()
        if not clean_thread or not metrics:
            return
        with self.store.transaction() as conn:
            for item in metrics:
                payload = item.get("metrics")
                if not isinstance(payload, dict):
                    payload = {}
                conn.execute(
                    """
                    INSERT INTO agent_loop_metrics(
                        thread_id, task_type, agent, metrics_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        clean_thread,
                        str(item.get("task_type", "") or ""),
                        str(item.get("agent", "") or ""),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        str(item.get("created_at", "") or ""),
                    ),
                )

    def list_agent_loop_rounds(self, thread_id: str) -> list[dict[str, Any]]:
        clean_thread = str(thread_id or "").strip()
        if not clean_thread:
            return []
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT thread_id, round_no, task_type, agent, prompt_hash,
                       prompt_tokens, completion_tokens, status, created_at
                FROM agent_loop_rounds
                WHERE thread_id = ?
                ORDER BY id ASC
                """,
                (clean_thread,),
            ).fetchall()
        return [
            {
                "thread_id": str(row["thread_id"]),
                "round_no": int(row["round_no"]),
                "task_type": str(row["task_type"]),
                "agent": str(row["agent"]),
                "prompt_hash": str(row["prompt_hash"]),
                "prompt_tokens": int(row["prompt_tokens"]),
                "completion_tokens": int(row["completion_tokens"]),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def list_agent_loop_metrics(self, thread_id: str) -> list[dict[str, Any]]:
        clean_thread = str(thread_id or "").strip()
        if not clean_thread:
            return []
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT thread_id, task_type, agent, metrics_json, created_at
                FROM agent_loop_metrics
                WHERE thread_id = ?
                ORDER BY id ASC
                """,
                (clean_thread,),
            ).fetchall()
        return [
            {
                "thread_id": str(row["thread_id"]),
                "task_type": str(row["task_type"]),
                "agent": str(row["agent"]),
                "metrics": json.loads(str(row["metrics_json"])),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def list_agent_tool_calls(self, thread_id: str) -> list[dict[str, Any]]:
        clean_thread = str(thread_id or "").strip()
        if not clean_thread:
            return []
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT thread_id, round_no, task_type, agent, tool_name, args_json, result_meta_json, created_at
                FROM agent_tool_calls
                WHERE thread_id = ?
                ORDER BY id ASC
                """,
                (clean_thread,),
            ).fetchall()
        return [
            {
                "thread_id": str(row["thread_id"]),
                "round_no": int(row["round_no"]),
                "task_type": str(row["task_type"]),
                "agent": str(row["agent"]),
                "tool_name": str(row["tool_name"]),
                "args": json.loads(str(row["args_json"])),
                "result_meta": json.loads(str(row["result_meta_json"])),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def get_workflow_doc_state(self, project_id: str) -> dict[str, Any] | None:
        clean_project = str(project_id or "").strip()
        if not clean_project:
            return None
        with self.store.read_only() as conn:
            row = conn.execute(
                """
                SELECT project_id, workflow_mode, workflow_stage, workflow_initialized, round_number,
                       assistant_message, collected_inputs_json, clarify_questions_json,
                       pending_docs_json, published_docs_json, created_at, updated_at
                FROM workflow_doc_states
                WHERE project_id = ?
                LIMIT 1
                """,
                (clean_project,),
            ).fetchone()
        if row is None:
            return None
        try:
            collected_inputs = json.loads(str(row["collected_inputs_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            collected_inputs = {}
        if not isinstance(collected_inputs, dict):
            collected_inputs = {}
        try:
            clarify_questions = json.loads(str(row["clarify_questions_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            clarify_questions = []
        if not isinstance(clarify_questions, list):
            clarify_questions = []
        try:
            pending_docs = json.loads(str(row["pending_docs_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            pending_docs = {}
        if not isinstance(pending_docs, dict):
            pending_docs = {}
        try:
            published_docs = json.loads(str(row["published_docs_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            published_docs = {}
        if not isinstance(published_docs, dict):
            published_docs = {}
        return {
            "project_id": str(row["project_id"]),
            "workflow_mode": str(row["workflow_mode"]),
            "workflow_stage": str(row["workflow_stage"]),
            "workflow_initialized": bool(int(row["workflow_initialized"])),
            "round_number": int(row["round_number"]),
            "assistant_message": str(row["assistant_message"]),
            "collected_inputs": {str(k): str(v or "") for k, v in collected_inputs.items()},
            "clarify_questions": [str(item) for item in clarify_questions if str(item or "").strip()],
            "pending_docs": {str(k): str(v or "") for k, v in pending_docs.items()},
            "published_docs": {str(k): str(v or "") for k, v in published_docs.items()},
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def upsert_workflow_doc_state(
        self,
        project_id: str,
        *,
        workflow_mode: str,
        workflow_stage: str,
        workflow_initialized: bool,
        round_number: int,
        assistant_message: str,
        collected_inputs: dict[str, str],
        clarify_questions: list[str],
        pending_docs: dict[str, str],
        published_docs: dict[str, str],
    ) -> dict[str, Any]:
        clean_project = str(project_id or "").strip()
        if not clean_project:
            raise ValueError("project_id cannot be empty")
        now_iso = _dump_time(utc_now())
        created_at = now_iso
        with self.store.transaction() as conn:
            existing = conn.execute(
                "SELECT created_at FROM workflow_doc_states WHERE project_id = ? LIMIT 1",
                (clean_project,),
            ).fetchone()
            if existing is not None:
                created_at = str(existing["created_at"])
                conn.execute(
                    """
                    UPDATE workflow_doc_states
                    SET workflow_mode = ?, workflow_stage = ?, workflow_initialized = ?, round_number = ?,
                        assistant_message = ?, collected_inputs_json = ?, clarify_questions_json = ?,
                        pending_docs_json = ?, published_docs_json = ?, updated_at = ?
                    WHERE project_id = ?
                    """,
                    (
                        str(workflow_mode or "").strip() or "original",
                        str(workflow_stage or "").strip() or "idle",
                        1 if workflow_initialized else 0,
                        max(0, int(round_number)),
                        str(assistant_message or ""),
                        json.dumps(collected_inputs or {}, ensure_ascii=False, sort_keys=True),
                        json.dumps(list(clarify_questions or []), ensure_ascii=False),
                        json.dumps(pending_docs or {}, ensure_ascii=False, sort_keys=True),
                        json.dumps(published_docs or {}, ensure_ascii=False, sort_keys=True),
                        now_iso,
                        clean_project,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO workflow_doc_states(
                        project_id, workflow_mode, workflow_stage, workflow_initialized, round_number,
                        assistant_message, collected_inputs_json, clarify_questions_json,
                        pending_docs_json, published_docs_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_project,
                        str(workflow_mode or "").strip() or "original",
                        str(workflow_stage or "").strip() or "idle",
                        1 if workflow_initialized else 0,
                        max(0, int(round_number)),
                        str(assistant_message or ""),
                        json.dumps(collected_inputs or {}, ensure_ascii=False, sort_keys=True),
                        json.dumps(list(clarify_questions or []), ensure_ascii=False),
                        json.dumps(pending_docs or {}, ensure_ascii=False, sort_keys=True),
                        json.dumps(published_docs or {}, ensure_ascii=False, sort_keys=True),
                        now_iso,
                        now_iso,
                    ),
                )
        state = self.get_workflow_doc_state(clean_project)
        if state is None:
            raise RuntimeError("failed to persist workflow doc state")
        state["created_at"] = created_at
        return state

    def upsert_chat_thread(self, thread_id: str, *, project_id: str, node_id: str = "") -> str:
        clean_thread = str(thread_id or "").strip()
        clean_project = str(project_id or "").strip()
        clean_node = str(node_id or "").strip()
        if not clean_thread:
            raise ValueError("thread_id cannot be empty")
        if not clean_project:
            raise ValueError("project_id cannot be empty")
        now_iso = _dump_time(utc_now())
        with self.store.transaction() as conn:
            existing = conn.execute(
                "SELECT thread_id FROM chat_threads WHERE thread_id = ? LIMIT 1",
                (clean_thread,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO chat_threads(thread_id, project_id, node_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (clean_thread, clean_project, clean_node, now_iso, now_iso),
                )
            else:
                conn.execute(
                    """
                    UPDATE chat_threads
                    SET project_id = ?, node_id = ?, updated_at = ?
                    WHERE thread_id = ?
                    """,
                    (clean_project, clean_node, now_iso, clean_thread),
                )
        return clean_thread

    def append_chat_message(self, thread_id: str, *, role: str, content: str) -> None:
        clean_thread = str(thread_id or "").strip()
        clean_role = str(role or "").strip() or "user"
        text = str(content or "").strip()
        if not clean_thread or not text:
            return
        now_iso = _dump_time(utc_now())
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages(thread_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (clean_thread, clean_role, text, now_iso),
            )
            conn.execute(
                "UPDATE chat_threads SET updated_at = ? WHERE thread_id = ?",
                (now_iso, clean_thread),
            )

    def list_chat_messages(self, thread_id: str, *, limit: int = 20) -> list[dict[str, str]]:
        clean_thread = str(thread_id or "").strip()
        if not clean_thread:
            return []
        safe_limit = max(1, min(int(limit), 200))
        with self.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM chat_messages
                WHERE thread_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (clean_thread, safe_limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [
            {
                "role": str(row["role"] or ""),
                "content": str(row["content"] or ""),
                "created_at": str(row["created_at"] or ""),
            }
            for row in rows
        ]
