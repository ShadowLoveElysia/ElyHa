#!/usr/bin/env python3
"""Migration bootstrap script."""

from __future__ import annotations

import argparse
from pathlib import Path

from elyha_core.storage.sqlite_store import SQLiteStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SQLite migrations for ElyHa")
    parser.add_argument("--db", required=True, help="Path to sqlite database file")
    args = parser.parse_args()
    db_path = Path(args.db)
    store = SQLiteStore(db_path)
    store.initialize()
    print(f"Migrations applied: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
