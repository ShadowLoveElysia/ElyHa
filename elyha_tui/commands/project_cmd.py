"""Project command handlers used by TUI."""

from __future__ import annotations

from elyha_core.models.project import Project
from elyha_core.services.project_service import ProjectService, ProjectSettingsPatch


def project_payload(project: Project) -> dict[str, object]:
    return {
        "id": project.id,
        "title": project.title,
        "active_revision": project.active_revision,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "settings": {
            "allow_cycles": project.settings.allow_cycles,
            "auto_snapshot_minutes": project.settings.auto_snapshot_minutes,
            "auto_snapshot_operations": project.settings.auto_snapshot_operations,
        },
    }


def project_create(service: ProjectService, *, title: str) -> dict[str, object]:
    project = service.create_project(title)
    return project_payload(project)


def project_open(service: ProjectService, *, project_id: str) -> dict[str, object]:
    return project_payload(service.load_project(project_id))


def project_list(service: ProjectService) -> list[dict[str, object]]:
    return [project_payload(item) for item in service.list_projects()]


def project_rename(
    service: ProjectService,
    *,
    project_id: str,
    title: str,
) -> dict[str, object]:
    return project_payload(service.rename_project(project_id, title))


def project_update_settings(
    service: ProjectService,
    *,
    project_id: str,
    allow_cycles: bool | None = None,
    auto_snapshot_minutes: int | None = None,
    auto_snapshot_operations: int | None = None,
) -> dict[str, object]:
    patch = ProjectSettingsPatch(
        allow_cycles=allow_cycles,
        auto_snapshot_minutes=auto_snapshot_minutes,
        auto_snapshot_operations=auto_snapshot_operations,
    )
    return project_payload(service.update_project_settings(project_id, patch))


def project_delete(service: ProjectService, *, project_id: str) -> dict[str, object]:
    service.delete_project(project_id)
    return {"status": "deleted", "project_id": project_id}
