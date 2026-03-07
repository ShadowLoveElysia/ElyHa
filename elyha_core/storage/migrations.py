"""SQLite schema migrations for ElyHa."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from elyha_core.i18n import tr

SCHEMA_VERSION = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        active_revision INTEGER NOT NULL DEFAULT 0,
        settings_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS nodes (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL,
        storyline_id TEXT,
        pos_x REAL NOT NULL,
        pos_y REAL NOT NULL,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_nodes_project_id ON nodes(project_id);

    CREATE TABLE IF NOT EXISTS edges (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY(source_id) REFERENCES nodes(id) ON DELETE CASCADE,
        FOREIGN KEY(target_id) REFERENCES nodes(id) ON DELETE CASCADE,
        UNIQUE(project_id, source_id, target_id)
    );
    CREATE INDEX IF NOT EXISTS idx_edges_project_id ON edges(project_id);
    CREATE INDEX IF NOT EXISTS idx_edges_source_id ON edges(source_id);
    CREATE INDEX IF NOT EXISTS idx_edges_target_id ON edges(target_id);

    CREATE TABLE IF NOT EXISTS node_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        content TEXT NOT NULL,
        token_estimate INTEGER NOT NULL DEFAULT 0,
        summary TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(node_id) REFERENCES nodes(id) ON DELETE CASCADE,
        UNIQUE(node_id, chunk_index)
    );
    CREATE INDEX IF NOT EXISTS idx_node_chunks_node_id ON node_chunks(node_id);

    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        node_id TEXT,
        task_type TEXT NOT NULL,
        status TEXT NOT NULL,
        error_code TEXT,
        error_message TEXT,
        started_at TEXT,
        finished_at TEXT,
        revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY(node_id) REFERENCES nodes(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);

    CREATE TABLE IF NOT EXISTS operation_logs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        op_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_operation_project_revision
        ON operation_logs(project_id, revision);

    CREATE TABLE IF NOT EXISTS snapshots (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_snapshots_project_revision
        ON snapshots(project_id, revision);
    """,
    2: """
    ALTER TABLE edges ADD COLUMN narrative_order INTEGER;
    CREATE INDEX IF NOT EXISTS idx_edges_source_order
        ON edges(project_id, source_id, narrative_order, created_at, id);
    """,
}


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Create/upgrade database schema in-place."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
    for version in range(current + 1, SCHEMA_VERSION + 1):
        sql = MIGRATIONS.get(version)
        if sql is None:
            raise RuntimeError(tr("err.migration_payload_missing", version=version))
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
            (version, _now_iso()),
        )
