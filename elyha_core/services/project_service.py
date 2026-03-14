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
    system_prompt_style: str | None = None
    system_prompt_forbidden: str | None = None
    system_prompt_notes: str | None = None
    constitution_markdown: str | None = None
    clarify_markdown: str | None = None
    specification_markdown: str | None = None
    plan_markdown: str | None = None
    global_directives: str | None = None
    context_soft_min_chars: int | None = None
    context_soft_max_chars: int | None = None
    context_sentence_safe_expand_chars: int | None = None
    context_soft_max_tokens: int | None = None
    strict_json_fence_output: bool | None = None
    context_compaction_enabled: bool | None = None
    context_compaction_trigger_ratio: int | None = None
    context_compaction_keep_recent_chunks: int | None = None
    context_compaction_group_chunks: int | None = None
    context_compaction_chunk_chars: int | None = None
    agent_tool_loop_enabled: bool | None = None
    agent_tool_loop_max_rounds: int | None = None
    agent_tool_loop_max_calls_per_round: int | None = None
    agent_tool_loop_single_read_char_limit: int | None = None
    agent_tool_loop_total_read_char_limit: int | None = None
    agent_tool_loop_no_progress_limit: int | None = None
    agent_tool_write_proposal_enabled: bool | None = None


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
            system_prompt_style=(
                current.system_prompt_style
                if patch.system_prompt_style is None
                else patch.system_prompt_style
            ),
            system_prompt_forbidden=(
                current.system_prompt_forbidden
                if patch.system_prompt_forbidden is None
                else patch.system_prompt_forbidden
            ),
            system_prompt_notes=(
                current.system_prompt_notes
                if patch.system_prompt_notes is None
                else patch.system_prompt_notes
            ),
            constitution_markdown=(
                current.constitution_markdown
                if patch.constitution_markdown is None
                else patch.constitution_markdown
            ),
            clarify_markdown=(
                current.clarify_markdown
                if patch.clarify_markdown is None
                else patch.clarify_markdown
            ),
            specification_markdown=(
                current.specification_markdown
                if patch.specification_markdown is None
                else patch.specification_markdown
            ),
            plan_markdown=(
                current.plan_markdown
                if patch.plan_markdown is None
                else patch.plan_markdown
            ),
            global_directives=(
                current.global_directives
                if patch.global_directives is None
                else patch.global_directives
            ),
            context_soft_min_chars=(
                current.context_soft_min_chars
                if patch.context_soft_min_chars is None
                else patch.context_soft_min_chars
            ),
            context_soft_max_chars=(
                current.context_soft_max_chars
                if patch.context_soft_max_chars is None
                else patch.context_soft_max_chars
            ),
            context_sentence_safe_expand_chars=(
                current.context_sentence_safe_expand_chars
                if patch.context_sentence_safe_expand_chars is None
                else patch.context_sentence_safe_expand_chars
            ),
            context_soft_max_tokens=(
                current.context_soft_max_tokens
                if patch.context_soft_max_tokens is None
                else patch.context_soft_max_tokens
            ),
            strict_json_fence_output=(
                current.strict_json_fence_output
                if patch.strict_json_fence_output is None
                else patch.strict_json_fence_output
            ),
            context_compaction_enabled=(
                current.context_compaction_enabled
                if patch.context_compaction_enabled is None
                else patch.context_compaction_enabled
            ),
            context_compaction_trigger_ratio=(
                current.context_compaction_trigger_ratio
                if patch.context_compaction_trigger_ratio is None
                else patch.context_compaction_trigger_ratio
            ),
            context_compaction_keep_recent_chunks=(
                current.context_compaction_keep_recent_chunks
                if patch.context_compaction_keep_recent_chunks is None
                else patch.context_compaction_keep_recent_chunks
            ),
            context_compaction_group_chunks=(
                current.context_compaction_group_chunks
                if patch.context_compaction_group_chunks is None
                else patch.context_compaction_group_chunks
            ),
            context_compaction_chunk_chars=(
                current.context_compaction_chunk_chars
                if patch.context_compaction_chunk_chars is None
                else patch.context_compaction_chunk_chars
            ),
            agent_tool_loop_enabled=(
                current.agent_tool_loop_enabled
                if patch.agent_tool_loop_enabled is None
                else patch.agent_tool_loop_enabled
            ),
            agent_tool_loop_max_rounds=(
                current.agent_tool_loop_max_rounds
                if patch.agent_tool_loop_max_rounds is None
                else patch.agent_tool_loop_max_rounds
            ),
            agent_tool_loop_max_calls_per_round=(
                current.agent_tool_loop_max_calls_per_round
                if patch.agent_tool_loop_max_calls_per_round is None
                else patch.agent_tool_loop_max_calls_per_round
            ),
            agent_tool_loop_single_read_char_limit=(
                current.agent_tool_loop_single_read_char_limit
                if patch.agent_tool_loop_single_read_char_limit is None
                else patch.agent_tool_loop_single_read_char_limit
            ),
            agent_tool_loop_total_read_char_limit=(
                current.agent_tool_loop_total_read_char_limit
                if patch.agent_tool_loop_total_read_char_limit is None
                else patch.agent_tool_loop_total_read_char_limit
            ),
            agent_tool_loop_no_progress_limit=(
                current.agent_tool_loop_no_progress_limit
                if patch.agent_tool_loop_no_progress_limit is None
                else patch.agent_tool_loop_no_progress_limit
            ),
            agent_tool_write_proposal_enabled=(
                current.agent_tool_write_proposal_enabled
                if patch.agent_tool_write_proposal_enabled is None
                else patch.agent_tool_write_proposal_enabled
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
                "system_prompt_style": updated.system_prompt_style,
                "system_prompt_forbidden": updated.system_prompt_forbidden,
                "system_prompt_notes": updated.system_prompt_notes,
                "constitution_markdown": updated.constitution_markdown,
                "clarify_markdown": updated.clarify_markdown,
                "specification_markdown": updated.specification_markdown,
                "plan_markdown": updated.plan_markdown,
                "global_directives": updated.global_directives,
                "context_soft_min_chars": updated.context_soft_min_chars,
                "context_soft_max_chars": updated.context_soft_max_chars,
                "context_sentence_safe_expand_chars": updated.context_sentence_safe_expand_chars,
                "context_soft_max_tokens": updated.context_soft_max_tokens,
                "strict_json_fence_output": updated.strict_json_fence_output,
                "context_compaction_enabled": updated.context_compaction_enabled,
                "context_compaction_trigger_ratio": updated.context_compaction_trigger_ratio,
                "context_compaction_keep_recent_chunks": updated.context_compaction_keep_recent_chunks,
                "context_compaction_group_chunks": updated.context_compaction_group_chunks,
                "context_compaction_chunk_chars": updated.context_compaction_chunk_chars,
                "agent_tool_loop_enabled": updated.agent_tool_loop_enabled,
                "agent_tool_loop_max_rounds": updated.agent_tool_loop_max_rounds,
                "agent_tool_loop_max_calls_per_round": updated.agent_tool_loop_max_calls_per_round,
                "agent_tool_loop_single_read_char_limit": updated.agent_tool_loop_single_read_char_limit,
                "agent_tool_loop_total_read_char_limit": updated.agent_tool_loop_total_read_char_limit,
                "agent_tool_loop_no_progress_limit": updated.agent_tool_loop_no_progress_limit,
                "agent_tool_write_proposal_enabled": updated.agent_tool_write_proposal_enabled,
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
