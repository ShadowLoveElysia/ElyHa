"""SQLite schema migrations for ElyHa."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from elyha_core.i18n import tr

SCHEMA_VERSION = 3


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
    3: """
    CREATE TABLE IF NOT EXISTS character_state_events (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        character_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        source_excerpt TEXT NOT NULL DEFAULT '',
        confidence REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_character_state_events_project_node
        ON character_state_events(project_id, node_id, created_at, id);
    CREATE INDEX IF NOT EXISTS idx_character_state_events_project_character
        ON character_state_events(project_id, character_id, created_at, id);

    CREATE TABLE IF NOT EXISTS item_state_events (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        source_excerpt TEXT NOT NULL DEFAULT '',
        confidence REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_item_state_events_project_node
        ON item_state_events(project_id, node_id, created_at, id);
    CREATE INDEX IF NOT EXISTS idx_item_state_events_project_item
        ON item_state_events(project_id, item_id, created_at, id);

    CREATE TABLE IF NOT EXISTS relationship_state_events (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        subject_character_id TEXT NOT NULL,
        object_character_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        source_excerpt TEXT NOT NULL DEFAULT '',
        confidence REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_relationship_events_project_node
        ON relationship_state_events(project_id, node_id, created_at, id);
    CREATE INDEX IF NOT EXISTS idx_relationship_events_project_pair
        ON relationship_state_events(
            project_id,
            subject_character_id,
            object_character_id,
            created_at,
            id
        );

    CREATE TABLE IF NOT EXISTS world_variable_events (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        variable_key TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        source_excerpt TEXT NOT NULL DEFAULT '',
        confidence REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_world_variable_events_project_node
        ON world_variable_events(project_id, node_id, created_at, id);
    CREATE INDEX IF NOT EXISTS idx_world_variable_events_project_key
        ON world_variable_events(project_id, variable_key, created_at, id);

    CREATE TABLE IF NOT EXISTS character_status (
        project_id TEXT NOT NULL,
        character_id TEXT NOT NULL,
        alive INTEGER NOT NULL DEFAULT 1,
        location TEXT NOT NULL DEFAULT '',
        faction TEXT NOT NULL DEFAULT '',
        held_items_json TEXT NOT NULL DEFAULT '[]',
        state_attributes_json TEXT NOT NULL DEFAULT '{}',
        last_event_id TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id, character_id),
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_character_status_project_updated
        ON character_status(project_id, updated_at, character_id);

    CREATE TABLE IF NOT EXISTS item_status (
        project_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        owner_character_id TEXT NOT NULL DEFAULT '',
        location TEXT NOT NULL DEFAULT '',
        destroyed INTEGER NOT NULL DEFAULT 0,
        state_attributes_json TEXT NOT NULL DEFAULT '{}',
        last_event_id TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id, item_id),
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_item_status_project_updated
        ON item_status(project_id, updated_at, item_id);

    CREATE TABLE IF NOT EXISTS relationship_status (
        project_id TEXT NOT NULL,
        subject_character_id TEXT NOT NULL,
        object_character_id TEXT NOT NULL,
        relation_type TEXT NOT NULL DEFAULT '',
        state_attributes_json TEXT NOT NULL DEFAULT '{}',
        last_event_id TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id, subject_character_id, object_character_id),
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_relationship_status_project_updated
        ON relationship_status(
            project_id,
            updated_at,
            subject_character_id,
            object_character_id
        );

    CREATE TABLE IF NOT EXISTS world_variable_status (
        project_id TEXT NOT NULL,
        variable_key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        last_event_id TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id, variable_key),
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_world_variable_status_project_updated
        ON world_variable_status(project_id, updated_at, variable_key);

    CREATE TABLE IF NOT EXISTS state_conflicts (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        conflict_type TEXT NOT NULL,
        detail_json TEXT NOT NULL,
        resolved INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_state_conflicts_project_resolved
        ON state_conflicts(project_id, resolved, created_at, id);

    CREATE TABLE IF NOT EXISTS entity_aliases (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        alias TEXT NOT NULL,
        canonical_id TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_aliases_project_type_alias
        ON entity_aliases(project_id, entity_type, alias);
    CREATE INDEX IF NOT EXISTS idx_entity_aliases_project_canonical
        ON entity_aliases(project_id, entity_type, canonical_id);

    CREATE TABLE IF NOT EXISTS state_change_proposals (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        proposal_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        reviewer TEXT NOT NULL DEFAULT '',
        review_note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        reviewed_at TEXT NOT NULL DEFAULT '',
        applied_at TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_state_proposals_project_node_thread
        ON state_change_proposals(project_id, node_id, thread_id, created_at, id);
    CREATE INDEX IF NOT EXISTS idx_state_proposals_project_status_apply
        ON state_change_proposals(project_id, status, applied_at, created_at, id);

    CREATE TABLE IF NOT EXISTS state_attribute_schema (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        attr_key TEXT NOT NULL,
        value_type TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        constraints_json TEXT NOT NULL DEFAULT '{}',
        is_active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_state_attr_schema_project_entity_key
        ON state_attribute_schema(project_id, entity_type, attr_key);
    CREATE INDEX IF NOT EXISTS idx_state_attr_schema_project_entity_active
        ON state_attribute_schema(project_id, entity_type, is_active, attr_key);
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
