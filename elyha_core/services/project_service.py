"""Project lifecycle management service."""

from __future__ import annotations

from dataclasses import dataclass

from elyha_core.i18n import tr
from elyha_core.models.operation import Operation
from elyha_core.models.project import Project, ProjectSettings
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id


@dataclass(slots=True)
class ProjectSettingsPatch:
    """Partial project settings update."""

    allow_cycles: bool | None = None
    auto_snapshot_minutes: int | None = None
    auto_snapshot_operations: int | None = None


class ProjectService:
    """Manage project CRUD and revisioned audit logs."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def create_project(
        self,
        title: str,
        *,
        project_id: str | None = None,
        settings: ProjectSettings | None = None,
    ) -> Project:
        now = utc_now()
        project = Project(
            id=project_id or generate_id("proj"),
            title=title,
            created_at=now,
            updated_at=now,
            settings=settings or ProjectSettings(),
        )
        self.repository.create_project(project)
        self._record_project_operation(
            project,
            op_type="project_create",
            payload={"title": project.title},
        )
        return self.load_project(project.id)

    def load_project(self, project_id: str) -> Project:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(tr("err.project_not_found", project_id=project_id))
        return project

    def list_projects(self) -> list[Project]:
        return self.repository.list_projects()

    def delete_project(self, project_id: str) -> None:
        project = self.load_project(project_id)
        self._record_project_operation(
            project,
            op_type="project_delete",
            payload={"title": project.title},
        )
        deleted = self.repository.delete_project(project_id)
        if not deleted:
            raise KeyError(tr("err.project_not_found", project_id=project_id))

    def rename_project(self, project_id: str, new_title: str) -> Project:
        project = self.load_project(project_id)
        project.title = new_title.strip()
        if not project.title:
            raise ValueError(tr("err.project_title_empty"))
        self._record_project_operation(
            project,
            op_type="project_rename",
            payload={"new_title": project.title},
        )
        return self.load_project(project_id)

    def update_project_settings(
        self,
        project_id: str,
        patch: ProjectSettingsPatch,
    ) -> Project:
        project = self.load_project(project_id)
        current = project.settings
        updated = ProjectSettings(
            allow_cycles=(
                current.allow_cycles
                if patch.allow_cycles is None
                else patch.allow_cycles
            ),
            auto_snapshot_minutes=(
                current.auto_snapshot_minutes
                if patch.auto_snapshot_minutes is None
                else patch.auto_snapshot_minutes
            ),
            auto_snapshot_operations=(
                current.auto_snapshot_operations
                if patch.auto_snapshot_operations is None
                else patch.auto_snapshot_operations
            ),
        )
        project.settings = updated
        self._record_project_operation(
            project,
            op_type="project_update_settings",
            payload={
                "allow_cycles": updated.allow_cycles,
                "auto_snapshot_minutes": updated.auto_snapshot_minutes,
                "auto_snapshot_operations": updated.auto_snapshot_operations,
            },
        )
        return self.load_project(project_id)

    def _record_project_operation(
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
