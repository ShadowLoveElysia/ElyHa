"""SQLite connection lifecycle and transaction helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
from typing import Iterator

from elyha_core.storage.migrations import apply_migrations


class SQLiteStore:
    """Provide short-lived sqlite connections with consistent pragmas."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._local = threading.local()

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def initialize(self) -> None:
        """Ensure schema exists and is migrated to latest version."""
        with self.transaction() as conn:
            apply_migrations(conn)

    @contextmanager
    def read_only(self) -> Iterator[sqlite3.Connection]:
        active_conn = getattr(self._local, "transaction_conn", None)
        if isinstance(active_conn, sqlite3.Connection):
            yield active_conn
            return
        conn = self._new_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            active_conn = getattr(self._local, "transaction_conn", None)
            if isinstance(active_conn, sqlite3.Connection):
                savepoint_index = int(getattr(self._local, "savepoint_index", 0)) + 1
                self._local.savepoint_index = savepoint_index
                savepoint_name = f"sp_{savepoint_index}"
                active_conn.execute(f"SAVEPOINT {savepoint_name}")
                try:
                    yield active_conn
                    active_conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                except Exception:
                    active_conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                    active_conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                    raise
                return

            conn = self._new_connection()
            self._local.transaction_conn = conn
            self._local.savepoint_index = 0
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._local.transaction_conn = None
                self._local.savepoint_index = 0
                conn.close()
