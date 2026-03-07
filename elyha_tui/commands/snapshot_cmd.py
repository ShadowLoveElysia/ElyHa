"""Snapshot command handlers used by TUI."""

from __future__ import annotations

from elyha_core.services.snapshot_service import SnapshotService


def _snapshot_payload(snapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "project_id": snapshot.project_id,
        "revision": snapshot.revision,
        "path": snapshot.path,
        "created_at": snapshot.created_at.isoformat(),
    }


def snapshot_create(service: SnapshotService, *, project_id: str) -> dict[str, object]:
    return _snapshot_payload(service.create_snapshot(project_id))


def snapshot_list(service: SnapshotService, *, project_id: str) -> list[dict[str, object]]:
    return [_snapshot_payload(snapshot) for snapshot in service.list_snapshots(project_id)]


def rollback_to_revision(
    service: SnapshotService,
    *,
    project_id: str,
    revision: int,
) -> dict[str, object]:
    project = service.rollback(project_id, revision)
    return {
        "project_id": project.id,
        "title": project.title,
        "active_revision": project.active_revision,
        "updated_at": project.updated_at.isoformat(),
    }
