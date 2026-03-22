"""FastAPI app for local ElyHa adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from elyha_core.i18n import (
    catalog as i18n_catalog,
    clear_i18n_cache,
    normalize_locale,
    tr,
)
from elyha_core.core_config import CORE_PROFILE, CoreConfigManager, CoreRuntimeConfig
from elyha_core.llm_presets import (
    LLMPreset,
    UserLLMPresetManager,
    load_llm_presets,
    normalize_preset_tag,
)
from elyha_core.models.task import TaskStatus
from elyha_core.services.ai_service import AIService
from elyha_core.services.context_service import ContextService
from elyha_core.models.node import NodeStatus, NodeType
from elyha_core.services.export_service import ExportService
from elyha_core.services.graph_service import GraphService, NodeCreate
from elyha_core.services.insight_service import InsightService
from elyha_core.services.project_service import (
    ProjectService,
    ProjectSettingsPatch,
)
from elyha_core.services.session_orchestrator_service import SessionOrchestratorService
from elyha_core.services.setting_proposal_service import SettingProposalService
from elyha_core.services.snapshot_service import SnapshotService
from elyha_core.services.state_service import StateService
from elyha_core.services.validation_service import ValidationService
from elyha_core.services.workflow_doc_service import WorkflowDocumentService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.storage.sqlite_store import SQLiteStore
from elyha_core.utils.ids import generate_id

API_KEY_CONFIGURED_PLACEHOLDER = "__ELYHA_API_KEY_CONFIGURED__"


def _mask_secret(value: str) -> str:
    secret = str(value or "")
    if not secret:
        return ""
    return "*" * len(secret)


@dataclass(slots=True)
class ServiceContainer:
    project_service: ProjectService
    graph_service: GraphService
    validation_service: ValidationService
    export_service: ExportService
    snapshot_service: SnapshotService
    state_service: StateService
    context_service: ContextService
    ai_service: AIService
    workflow_doc_service: WorkflowDocumentService
    setting_proposal_service: SettingProposalService
    session_orchestrator_service: SessionOrchestratorService
    insight_service: InsightService
    core_config_manager: CoreConfigManager
    builtin_llm_presets: dict[str, LLMPreset]
    user_preset_manager: UserLLMPresetManager
    llm_presets: dict[str, LLMPreset]


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class UpdateSettingsRequest(BaseModel):
    allow_cycles: bool | None = None
    auto_snapshot_minutes: int | None = Field(default=None, ge=1)
    auto_snapshot_operations: int | None = Field(default=None, ge=1)
    system_prompt_style: str | None = Field(default=None, max_length=4000)
    system_prompt_forbidden: str | None = Field(default=None, max_length=4000)
    system_prompt_notes: str | None = Field(default=None, max_length=4000)
    constitution_markdown: str | None = Field(default=None, max_length=12000)
    clarify_markdown: str | None = Field(default=None, max_length=12000)
    specification_markdown: str | None = Field(default=None, max_length=12000)
    plan_markdown: str | None = Field(default=None, max_length=12000)
    guide_skipped_docs: list[str] | None = None
    global_directives: str | None = Field(default=None, max_length=12000)
    context_soft_min_chars: int | None = Field(default=None, ge=1)
    context_soft_max_chars: int | None = Field(default=None, ge=1)
    context_sentence_safe_expand_chars: int | None = Field(default=None, ge=0)
    context_soft_max_tokens: int | None = Field(default=None, ge=1)
    strict_json_fence_output: bool | None = None
    context_compaction_enabled: bool | None = None
    context_compaction_trigger_ratio: int | None = Field(default=None, ge=1, le=100)
    context_compaction_keep_recent_chunks: int | None = Field(default=None, ge=1)
    context_compaction_group_chunks: int | None = Field(default=None, ge=1)
    context_compaction_chunk_chars: int | None = Field(default=None, ge=1)
    agent_tool_loop_enabled: bool | None = None
    agent_tool_loop_max_rounds: int | None = Field(default=None, ge=1, le=20)
    agent_tool_loop_max_calls_per_round: int | None = Field(default=None, ge=1, le=20)
    agent_tool_loop_single_read_char_limit: int | None = Field(default=None, ge=200, le=50000)
    agent_tool_loop_total_read_char_limit: int | None = Field(default=None, ge=1000, le=200000)
    agent_tool_loop_no_progress_limit: int | None = Field(default=None, ge=1, le=10)
    agent_tool_write_proposal_enabled: bool | None = None


class CreateNodeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    type: NodeType = NodeType.CHAPTER
    status: NodeStatus = NodeStatus.DRAFT
    storyline_id: str | None = None
    pos_x: float = 0.0
    pos_y: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateNodeRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    type: NodeType | None = None
    status: NodeStatus | None = None
    storyline_id: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    metadata: dict[str, Any] | None = None


class CreateEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    label: str = ""


class ReorderEdgesRequest(BaseModel):
    source_id: str
    edge_ids: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    traversal: str = "mainline"
    output_root: str = "exports"


class RollbackRequest(BaseModel):
    revision: int = Field(ge=0)


class ExtractStateEventsRequest(BaseModel):
    project_id: str
    node_id: str
    content: str = ""
    thread_id: str = "default"
    create_proposals: bool = False


class CreateStateProposalsRequest(BaseModel):
    project_id: str
    node_id: str
    thread_id: str = Field(min_length=1, max_length=128)
    events: list[dict[str, Any]] = Field(default_factory=list)


class ReviewStateProposalRequest(BaseModel):
    action: str
    reviewer: str = ""
    note: str = ""


class ApplyStateChangesRequest(BaseModel):
    project_id: str
    node_id: str
    thread_id: str = Field(min_length=1, max_length=128)
    proposal_ids: list[str] = Field(default_factory=list)


class UpsertEntityAliasRequest(BaseModel):
    project_id: str
    entity_type: str
    alias: str = Field(min_length=1, max_length=128)
    canonical_id: str = Field(min_length=1, max_length=128)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class UpsertStateSchemaRequest(BaseModel):
    project_id: str
    entity_type: str
    attr_key: str = Field(min_length=1, max_length=128)
    value_type: str
    description: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class UpsertRelationshipStatusRequest(BaseModel):
    project_id: str
    subject_character_id: str = Field(min_length=1, max_length=128)
    object_character_id: str = Field(min_length=1, max_length=128)
    relation_type: str = Field(min_length=1, max_length=128)
    node_id: str | None = Field(default=None, max_length=128)
    source_excerpt: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    state_attributes: dict[str, Any] = Field(default_factory=dict)


class RebuildStateSnapshotRequest(BaseModel):
    upto_revision: int | None = Field(default=None, ge=0)


class PromptStatePayloadRequest(BaseModel):
    project_id: str
    character_ids: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    relationship_pairs: list[str] = Field(default_factory=list)
    world_variable_keys: list[str] = Field(default_factory=list)


class GenerateChapterRequest(BaseModel):
    project_id: str
    node_id: str
    token_budget: int = Field(default=2200, ge=1)
    style_hint: str = ""
    workflow_mode: str | None = None


class GenerateBranchesRequest(BaseModel):
    project_id: str
    node_id: str
    n: int = Field(default=3, ge=1)
    token_budget: int = Field(default=1800, ge=1)


class ReviewRequest(BaseModel):
    project_id: str
    node_id: str
    token_budget: int = Field(default=1500, ge=1)


class ChatAssistRequest(BaseModel):
    project_id: str
    message: str = Field(min_length=1, max_length=4000)
    node_id: str | None = None
    thread_id: str | None = Field(default=None, min_length=1, max_length=128)
    allow_node_write: bool = True
    guide_mode: bool = False
    token_budget: int = Field(default=1800, ge=1)


class OutlineGuideRequest(BaseModel):
    project_id: str
    goal: str = Field(min_length=1, max_length=4000)
    sync_context: str = ""
    specify: str = ""
    clarify_answers: str = ""
    plan_notes: str = ""
    constraints: str = ""
    tone: str = ""
    token_budget: int = Field(default=2200, ge=1)


class OutlineDetailNodesRequest(BaseModel):
    project_id: str
    outline_markdown: str = ""
    chapter_beats: list[str] = Field(default_factory=list)
    user_request: str = ""
    mode: str = ""
    token_budget: int = Field(default=1800, ge=1)
    max_nodes: int = Field(default=8, ge=3, le=12)


class WorkflowClarifyRequest(BaseModel):
    project_id: str
    goal: str = Field(min_length=1, max_length=4000)
    sync_context: str = ""
    specify: str = ""
    constraints: str = ""
    tone: str = ""
    token_budget: int = Field(default=1200, ge=1)


class WorkflowSyncRequest(BaseModel):
    project_id: str
    goal: str = Field(min_length=1, max_length=4000)
    sync_context: str = Field(min_length=1, max_length=12000)
    mode: str = ""
    constraints: str = ""
    tone: str = ""
    token_budget: int = Field(default=1400, ge=1)


class StartWorkflowRequest(BaseModel):
    mode: str = "original"
    token_budget: int = Field(default=1000, ge=1)


class AutoStartWorkflowRequest(BaseModel):
    user_input: str = Field(min_length=1, max_length=4000)
    token_budget: int = Field(default=400, ge=1)


class SubmitWorkflowStageInputRequest(BaseModel):
    user_input: str = Field(min_length=1, max_length=12000)
    token_budget: int = Field(default=1000, ge=1)


class ConfirmWorkflowRoundRequest(BaseModel):
    round_number: int = Field(ge=1, le=2)


class ClarificationQuestionRequest(BaseModel):
    project_id: str
    node_id: str | None = None
    context: str = ""
    token_budget: int = Field(default=900, ge=1)


class StartAgentSessionRequest(BaseModel):
    project_id: str
    node_id: str
    mode: str = "single_agent"
    token_budget: int = Field(default=2200, ge=1)
    style_hint: str = ""
    thread_id: str | None = None


class ResumeAgentSessionRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)


class SubmitAgentDecisionRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=64)
    decision_id: str = Field(min_length=1, max_length=128)
    expected_state_version: int | None = Field(default=None, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class RequestAgentClarificationRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    context: str = ""
    token_budget: int = Field(default=900, ge=1)


class SubmitClarificationAnswerRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    clarification_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    selected_option: str = ""
    answer_text: str = ""


class ReviewSettingProposalActionRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    proposal_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=32)
    reviewer: str = ""
    note: str = ""
    decision_id: str = Field(min_length=1, max_length=128)
    expected_state_version: int | None = Field(default=None, ge=1)


class SubmitDiffReviewRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    diff_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    accepted_hunk_ids: list[str] = Field(default_factory=list)
    rejected_hunk_ids: list[str] = Field(default_factory=list)
    edited_hunks: list[dict[str, Any]] = Field(default_factory=list)
    expected_base_revision: int | None = Field(default=None, ge=0)
    expected_base_hash: str | None = Field(default=None, max_length=128)
    expected_state_version: int | None = Field(default=None, ge=1)


class ReviewSettingProposalsBatchRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=32)
    proposal_ids: list[str] = Field(default_factory=list)
    reviewer: str = ""
    note: str = ""
    decision_id: str = Field(min_length=1, max_length=128)
    expected_state_version: int | None = Field(default=None, ge=1)


class CreateChatThreadRequest(BaseModel):
    thread_id: str | None = Field(default=None, max_length=128)
    node_id: str = Field(default="", max_length=128)


class UpdateRuntimeSettingsRequest(BaseModel):
    locale: str | None = None
    llm_provider: str | None = None
    preset_tag: str | None = None
    llm_transport: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    auto_complete: bool | None = None
    think_switch: bool | None = None
    think_depth: str | None = None
    thinking_budget: int | None = Field(default=None, ge=1)
    web_search_enabled: bool | None = None
    web_search_context_size: str | None = None
    web_search_max_results: int | None = Field(default=None, ge=1, le=20)
    llm_request_timeout: int | None = Field(default=None, ge=5, le=600)
    web_request_timeout_ms: int | None = Field(default=None, ge=30000, le=1200000)
    default_token_budget: int | None = Field(default=None, ge=1)
    default_workflow_mode: str | None = None
    web_host: str | None = None
    web_port: int | None = Field(default=None, ge=1, le=65535)


class SwitchRuntimeProfileRequest(BaseModel):
    profile: str
    create_if_missing: bool = True


class CreateRuntimeProfileRequest(BaseModel):
    profile: str
    from_profile: str = CORE_PROFILE


class RenameRuntimeProfileRequest(BaseModel):
    profile: str
    new_profile: str


class CreateLlmPresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tag: str | None = None
    group: str | None = None
    api_format: str | None = None
    llm_transport: str | None = None
    api_url: str | None = None
    default_model: str | None = None
    models: list[str] = Field(default_factory=list)
    auto_complete: bool = True


class RenameLlmPresetRequest(BaseModel):
    tag: str
    new_name: str = Field(min_length=1, max_length=120)


def _to_project_payload(project) -> dict[str, Any]:
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
            "system_prompt_style": project.settings.system_prompt_style,
            "system_prompt_forbidden": project.settings.system_prompt_forbidden,
            "system_prompt_notes": project.settings.system_prompt_notes,
            "constitution_markdown": project.settings.constitution_markdown,
            "clarify_markdown": project.settings.clarify_markdown,
            "specification_markdown": project.settings.specification_markdown,
            "plan_markdown": project.settings.plan_markdown,
            "guide_skipped_docs": list(project.settings.guide_skipped_docs),
            "global_directives": project.settings.global_directives,
            "context_soft_min_chars": project.settings.context_soft_min_chars,
            "context_soft_max_chars": project.settings.context_soft_max_chars,
            "context_sentence_safe_expand_chars": project.settings.context_sentence_safe_expand_chars,
            "context_soft_max_tokens": project.settings.context_soft_max_tokens,
            "strict_json_fence_output": project.settings.strict_json_fence_output,
            "context_compaction_enabled": project.settings.context_compaction_enabled,
            "context_compaction_trigger_ratio": project.settings.context_compaction_trigger_ratio,
            "context_compaction_keep_recent_chunks": project.settings.context_compaction_keep_recent_chunks,
            "context_compaction_group_chunks": project.settings.context_compaction_group_chunks,
            "context_compaction_chunk_chars": project.settings.context_compaction_chunk_chars,
            "agent_tool_loop_enabled": project.settings.agent_tool_loop_enabled,
            "agent_tool_loop_max_rounds": project.settings.agent_tool_loop_max_rounds,
            "agent_tool_loop_max_calls_per_round": project.settings.agent_tool_loop_max_calls_per_round,
            "agent_tool_loop_single_read_char_limit": project.settings.agent_tool_loop_single_read_char_limit,
            "agent_tool_loop_total_read_char_limit": project.settings.agent_tool_loop_total_read_char_limit,
            "agent_tool_loop_no_progress_limit": project.settings.agent_tool_loop_no_progress_limit,
            "agent_tool_write_proposal_enabled": project.settings.agent_tool_write_proposal_enabled,
        },
    }


def _to_node_payload(node) -> dict[str, Any]:
    return {
        "id": node.id,
        "project_id": node.project_id,
        "title": node.title,
        "type": node.type.value,
        "status": node.status.value,
        "storyline_id": node.storyline_id,
        "pos_x": node.pos_x,
        "pos_y": node.pos_y,
        "metadata": node.metadata,
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat(),
    }


def _to_edge_payload(edge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "project_id": edge.project_id,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "label": edge.label,
        "narrative_order": edge.narrative_order,
        "created_at": edge.created_at.isoformat(),
    }


def _to_snapshot_payload(snapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "project_id": snapshot.project_id,
        "revision": snapshot.revision,
        "path": snapshot.path,
        "created_at": snapshot.created_at.isoformat(),
    }


def _to_task_payload(task) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "node_id": task.node_id,
        "task_type": task.task_type,
        "status": task.status.value,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "revision": task.revision,
        "created_at": task.created_at.isoformat(),
    }


def _to_workflow_doc_payload(state: Any) -> dict[str, Any]:
    return {
        "project_id": str(getattr(state, "project_id", "")),
        "workflow_mode": str(getattr(state, "workflow_mode", "")),
        "workflow_stage": str(getattr(state, "workflow_stage", "")),
        "workflow_initialized": bool(getattr(state, "workflow_initialized", False)),
        "round_number": int(getattr(state, "round_number", 0) or 0),
        "assistant_message": str(getattr(state, "assistant_message", "") or ""),
        "collected_inputs": dict(getattr(state, "collected_inputs", {}) or {}),
        "clarify_questions": list(getattr(state, "clarify_questions", []) or []),
        "pending_docs": dict(getattr(state, "pending_docs", {}) or {}),
        "published_docs": dict(getattr(state, "published_docs", {}) or {}),
        "created_at": str(getattr(state, "created_at", "") or ""),
        "updated_at": str(getattr(state, "updated_at", "") or ""),
    }


def _parse_relationship_pairs(values: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        if "|" in text:
            left, right = text.split("|", 1)
        elif ":" in text:
            left, right = text.split(":", 1)
        elif "," in text:
            left, right = text.split(",", 1)
        else:
            continue
        src = left.strip()
        dst = right.strip()
        if src and dst:
            pairs.append((src, dst))
    return pairs


def _to_runtime_config_payload(config: CoreRuntimeConfig) -> dict[str, Any]:
    slot_masks = {
        slot: _mask_secret(secret)
        for slot, secret in config.api_key_store.items()
        if str(secret or "").strip()
    }
    return {
        "locale": config.locale,
        "llm_provider": config.llm_provider,
        "preset_tag": config.preset_tag,
        "llm_transport": config.llm_transport,
        "api_url": config.api_url,
        "api_key": "",
        "api_key_mask": _mask_secret(str(config.api_key or "")),
        "api_key_slot_masks": slot_masks,
        "model_name": config.model_name,
        "auto_complete": config.auto_complete,
        "think_switch": config.think_switch,
        "think_depth": config.think_depth,
        "thinking_budget": config.thinking_budget,
        "web_search_enabled": config.web_search_enabled,
        "web_search_context_size": config.web_search_context_size,
        "web_search_max_results": config.web_search_max_results,
        "llm_request_timeout": config.llm_request_timeout,
        "web_request_timeout_ms": config.web_request_timeout_ms,
        "default_token_budget": config.default_token_budget,
        "default_workflow_mode": config.default_workflow_mode,
        "web_host": config.web_host,
        "web_port": config.web_port,
    }


def _to_runtime_settings_payload(
    profile: str,
    config: CoreRuntimeConfig,
    profiles: list[str],
) -> dict[str, Any]:
    return {
        "active_profile": profile,
        "profiles": profiles,
        "is_core_profile": profile == CORE_PROFILE,
        "config": _to_runtime_config_payload(config),
    }


def _to_llm_preset_payload(preset: LLMPreset) -> dict[str, Any]:
    return {
        "tag": preset.tag,
        "name": preset.name,
        "group": preset.group,
        "source": preset.source,
        "is_user": preset.source == "user",
        "api_format": preset.api_format,
        "llm_transport": preset.llm_transport,
        "api_url": preset.api_url,
        "auto_complete": preset.auto_complete,
        "default_model": preset.model,
        "models": list(preset.models),
    }


def _merge_llm_presets(
    builtin_presets: dict[str, LLMPreset],
    user_presets: dict[str, LLMPreset],
) -> dict[str, LLMPreset]:
    merged = dict(builtin_presets)
    for tag, preset in user_presets.items():
        merged[tag] = preset
    return merged


def _sorted_llm_presets(presets: dict[str, LLMPreset]) -> list[LLMPreset]:
    return sorted(
        presets.values(),
        key=lambda item: (
            0 if item.source == "builtin" else 1,
            str(item.group or "").lower(),
            str(item.name or "").lower(),
            item.tag,
        ),
    )


def _slugify_preset_tag(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or "").strip().lower()).strip("-._")
    if not slug:
        slug = "preset"
    if len(slug) > 64:
        slug = slug[:64].rstrip("-._")
    return slug or "preset"


def _to_llm_platform_config(config: CoreRuntimeConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "auto_complete": bool(config.auto_complete),
        "llm_transport": str(config.llm_transport),
        "think_switch": bool(config.think_switch),
        "think_depth": str(config.think_depth),
        "thinking_budget": int(config.thinking_budget),
        "web_search_enabled": bool(config.web_search_enabled),
        "web_search_context_size": str(config.web_search_context_size),
        "web_search_max_results": int(config.web_search_max_results),
        "request_timeout": int(config.llm_request_timeout),
    }
    if config.api_url:
        payload["api_url"] = config.api_url
    if config.api_key:
        payload["api_key"] = config.api_key
    if config.model_name:
        payload["model_name"] = config.model_name
    return payload


def _build_ai_service(
    repository: SQLiteRepository,
    graph_service: GraphService,
    context_service: ContextService,
    validation_service: ValidationService,
    state_service: StateService,
    setting_proposal_service: SettingProposalService,
    runtime_config: CoreRuntimeConfig,
    llm_presets: dict[str, LLMPreset],
) -> AIService:
    return AIService(
        repository,
        graph_service,
        context_service,
        validation_service,
        llm_provider=runtime_config.llm_provider,
        llm_platform_config=_to_llm_platform_config(runtime_config),
        llm_presets=llm_presets,
        state_service=state_service,
        setting_proposal_service=setting_proposal_service,
    )


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Create FastAPI app with isolated service container."""
    db_file = Path(db_path or "./data/elyha.db")
    repository = SQLiteRepository(SQLiteStore(db_file))
    project_service = ProjectService(repository)
    graph_service = GraphService(repository)
    validation_service = ValidationService(repository)
    state_service = StateService(repository)
    context_service = ContextService(repository)
    setting_proposal_service = SettingProposalService(repository)
    config_root = Path(os.getenv("ELYHA_CORE_CONFIG_DIR", db_file.parent / "core_configs"))
    core_config_manager = CoreConfigManager(config_root)
    preset_path = Path(os.getenv("ELYHA_PRESET_PATH", Path(__file__).resolve().parent.parent / "preset.json"))
    builtin_llm_presets = load_llm_presets(preset_path)
    user_preset_root = Path(os.getenv("ELYHA_USER_PRESET_DIR", db_file.parent / "llm_presets"))
    user_preset_manager = UserLLMPresetManager(user_preset_root)
    llm_presets = _merge_llm_presets(builtin_llm_presets, user_preset_manager.load_presets())
    _, runtime_config = core_config_manager.load_active()
    os.environ["ELYHA_LOCALE"] = runtime_config.locale
    ai_service = _build_ai_service(
        repository,
        graph_service,
        context_service,
        validation_service,
        state_service,
        setting_proposal_service,
        runtime_config,
        llm_presets,
    )
    workflow_doc_service = WorkflowDocumentService(repository, ai_service)
    session_orchestrator_service = SessionOrchestratorService(
        repository,
        graph_service,
        ai_service,
        state_service,
        setting_proposal_service,
    )
    services = ServiceContainer(
        project_service=project_service,
        graph_service=graph_service,
        validation_service=validation_service,
        export_service=ExportService(repository, validation_service),
        snapshot_service=SnapshotService(repository),
        state_service=state_service,
        context_service=context_service,
        ai_service=ai_service,
        workflow_doc_service=workflow_doc_service,
        setting_proposal_service=setting_proposal_service,
        session_orchestrator_service=session_orchestrator_service,
        insight_service=InsightService(repository),
        core_config_manager=core_config_manager,
        builtin_llm_presets=builtin_llm_presets,
        user_preset_manager=user_preset_manager,
        llm_presets=llm_presets,
    )

    api = FastAPI(title="ElyHa Local API")
    web_root = Path(__file__).resolve().parent.parent / "elyha_web" / "static"
    i18n_root = Path(__file__).resolve().parent.parent / "i18n"
    if web_root.exists():
        api.mount(
            "/static",
            StaticFiles(directory=str(web_root)),
            name="elyha-static",
        )
        api.mount(
            "/web/static",
            StaticFiles(directory=str(web_root)),
            name="elyha-web-static",
        )
        if i18n_root.exists():
            api.mount(
                "/i18n",
                StaticFiles(directory=str(i18n_root)),
                name="elyha-i18n",
            )
            api.mount(
                "/web/i18n",
                StaticFiles(directory=str(i18n_root)),
                name="elyha-web-i18n",
            )

        @api.get("/", include_in_schema=False)
        @api.get("/web", include_in_schema=False)
        @api.get("/web/", include_in_schema=False)
        def web_index() -> FileResponse:
            return FileResponse(web_root / "index.html")

    @api.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "elyha_api"}

    def _reload_llm_presets() -> dict[str, LLMPreset]:
        user_presets = services.user_preset_manager.load_presets()
        merged = _merge_llm_presets(services.builtin_llm_presets, user_presets)
        services.llm_presets = merged
        return merged

    def _apply_runtime_config(config: CoreRuntimeConfig) -> None:
        os.environ["ELYHA_LOCALE"] = config.locale
        services.ai_service = _build_ai_service(
            repository,
            graph_service,
            context_service,
            validation_service,
            state_service,
            setting_proposal_service,
            config,
            services.llm_presets,
        )
        services.session_orchestrator_service.set_ai_service(services.ai_service)
        services.workflow_doc_service.set_ai_service(services.ai_service)

    @api.get("/api/llm/presets")
    def list_llm_presets() -> list[dict[str, Any]]:
        presets = _reload_llm_presets()
        return [
            _to_llm_preset_payload(preset)
            for preset in _sorted_llm_presets(presets)
        ]

    @api.post("/api/llm/presets")
    def create_llm_preset(payload: CreateLlmPresetRequest) -> dict[str, Any]:
        name = str(payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="preset name cannot be empty")
        presets = _reload_llm_presets()
        if payload.tag is None or not str(payload.tag).strip():
            base_tag = _slugify_preset_tag(name)
            tag = base_tag
            index = 1
            while tag in presets:
                suffix = f"-{index}"
                stem = base_tag[: max(1, 64 - len(suffix))].rstrip("-._")
                tag = f"{stem}{suffix}" if stem else f"preset{suffix}"
                index += 1
        else:
            try:
                tag = normalize_preset_tag(payload.tag)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if tag in services.builtin_llm_presets:
            raise HTTPException(status_code=400, detail=f"preset tag is reserved by builtin preset: {tag}")
        if tag in presets:
            raise HTTPException(status_code=400, detail=f"preset already exists: {tag}")
        llm_transport = str(payload.llm_transport or "").strip().lower()
        if llm_transport in {"openai_sdk", "openai-client", "openai_client"}:
            llm_transport = "openai"
        elif llm_transport in {"anthropic_sdk", "anthropic-client", "anthropic_client"}:
            llm_transport = "anthropic"
        elif llm_transport not in {"httpx", "openai", "anthropic"}:
            llm_transport = "httpx"
        model = str(payload.default_model or "").strip()
        models: list[str] = []
        for item in payload.models:
            text = str(item or "").strip()
            if text and text not in models:
                models.append(text)
        if model and model not in models:
            models.insert(0, model)
        api_format = str(payload.api_format or "").strip()
        if not api_format:
            api_format = "Anthropic" if llm_transport == "anthropic" else "OpenAI"
        candidate = LLMPreset(
            tag=tag,
            name=name,
            group=str(payload.group or "").strip() or "custom",
            api_format=api_format,
            llm_transport=llm_transport,
            api_url=str(payload.api_url or "").strip(),
            api_key="",
            model=model,
            models=models,
            auto_complete=bool(payload.auto_complete),
            source="user",
        )
        try:
            saved = services.user_preset_manager.save_preset(candidate, overwrite=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _reload_llm_presets()
        _, active_config = services.core_config_manager.load_active()
        _apply_runtime_config(active_config)
        return _to_llm_preset_payload(saved)

    @api.post("/api/llm/presets/rename")
    def rename_llm_preset(payload: RenameLlmPresetRequest) -> dict[str, Any]:
        next_name = str(payload.new_name or "").strip()
        if not next_name:
            raise HTTPException(status_code=400, detail="preset name cannot be empty")
        try:
            tag = normalize_preset_tag(payload.tag)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        presets = _reload_llm_presets()
        target = presets.get(tag)
        if target is None:
            raise HTTPException(status_code=404, detail=f"preset not found: {tag}")
        if target.source != "user":
            raise HTTPException(status_code=403, detail="builtin preset cannot be renamed")
        candidate = LLMPreset(
            tag=target.tag,
            name=next_name,
            group=target.group,
            api_format=target.api_format,
            llm_transport=target.llm_transport,
            api_url=target.api_url,
            api_key="",
            model=target.model,
            models=list(target.models),
            auto_complete=bool(target.auto_complete),
            source="user",
        )
        try:
            saved = services.user_preset_manager.save_preset(candidate, overwrite=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _reload_llm_presets()
        _, active_config = services.core_config_manager.load_active()
        _apply_runtime_config(active_config)
        return _to_llm_preset_payload(saved)

    @api.delete("/api/llm/presets/{tag}")
    def delete_llm_preset(tag: str) -> dict[str, Any]:
        try:
            normalized = normalize_preset_tag(tag)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        presets = _reload_llm_presets()
        target = presets.get(normalized)
        if target is None:
            raise HTTPException(status_code=404, detail=f"preset not found: {normalized}")
        if target.source != "user":
            raise HTTPException(status_code=403, detail="builtin preset cannot be deleted")
        try:
            services.user_preset_manager.delete_preset(normalized)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        _reload_llm_presets()
        active_profile, active_config = services.core_config_manager.load_active()
        if active_profile != CORE_PROFILE and active_config.preset_tag == normalized:
            merged = asdict(active_config)
            merged["preset_tag"] = ""
            saved = services.core_config_manager.save_profile(active_profile, CoreRuntimeConfig(**merged).normalized())
            _apply_runtime_config(saved)
        else:
            _apply_runtime_config(active_config)
        return {"status": "deleted", "tag": normalized}

    @api.get("/api/i18n/{locale}")
    def get_i18n_catalog(locale: str) -> dict[str, str]:
        clear_i18n_cache()
        return i18n_catalog(normalize_locale(locale))

    @api.get("/api/settings/runtime")
    def get_runtime_settings() -> dict[str, Any]:
        profile, config = services.core_config_manager.load_active()
        return _to_runtime_settings_payload(
            profile,
            config,
            services.core_config_manager.list_profiles(),
        )

    @api.put("/api/settings/runtime")
    def update_runtime_settings(payload: UpdateRuntimeSettingsRequest) -> dict[str, Any]:
        patch = payload.model_dump(exclude_none=True)
        try:
            profile, current = services.core_config_manager.load_active()
            if profile == CORE_PROFILE:
                raise PermissionError("core profile is read-only")
            merged = asdict(current)
            for key, value in patch.items():
                if key == "api_key_mask":
                    continue
                if key == "api_key":
                    text = str(value or "").strip()
                    if not text or text == API_KEY_CONFIGURED_PLACEHOLDER:
                        continue
                    merged[key] = text
                    continue
                merged[key] = value
            candidate = CoreRuntimeConfig(**merged).normalized()
            _apply_runtime_config(candidate)
            saved = services.core_config_manager.save_profile(profile, candidate)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_runtime_settings_payload(
            profile,
            saved,
            services.core_config_manager.list_profiles(),
        )

    @api.post("/api/settings/runtime/switch")
    def switch_runtime_profile(payload: SwitchRuntimeProfileRequest) -> dict[str, Any]:
        try:
            config = services.core_config_manager.set_active_profile(
                payload.profile,
                create_if_missing=payload.create_if_missing,
            )
            profile = services.core_config_manager.get_active_profile()
            _apply_runtime_config(config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_runtime_settings_payload(
            profile,
            config,
            services.core_config_manager.list_profiles(),
        )

    @api.post("/api/settings/runtime/profiles")
    def create_runtime_profile(payload: CreateRuntimeProfileRequest) -> dict[str, Any]:
        try:
            services.core_config_manager.create_profile(
                payload.profile,
                from_profile=payload.from_profile,
            )
            profile = services.core_config_manager.get_active_profile()
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_runtime_settings_payload(
            profile,
            services.core_config_manager.load_profile(profile),
            services.core_config_manager.list_profiles(),
        )

    @api.post("/api/settings/runtime/profiles/rename")
    def rename_runtime_profile(payload: RenameRuntimeProfileRequest) -> dict[str, Any]:
        try:
            services.core_config_manager.rename_profile(payload.profile, payload.new_profile)
            profile = services.core_config_manager.get_active_profile()
            config = services.core_config_manager.load_profile(profile)
            _apply_runtime_config(config)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_runtime_settings_payload(
            profile,
            config,
            services.core_config_manager.list_profiles(),
        )

    @api.delete("/api/settings/runtime/profiles/{profile}")
    def delete_runtime_profile(profile: str) -> dict[str, Any]:
        try:
            services.core_config_manager.delete_profile(profile)
            active = services.core_config_manager.get_active_profile()
            config = services.core_config_manager.load_profile(active)
            _apply_runtime_config(config)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_runtime_settings_payload(
            active,
            config,
            services.core_config_manager.list_profiles(),
        )

    @api.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        return [_to_project_payload(project) for project in services.project_service.list_projects()]

    @api.post("/api/projects")
    def create_project(payload: CreateProjectRequest) -> dict[str, Any]:
        try:
            project = services.project_service.create_project(payload.title)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_project_payload(project)

    @api.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        try:
            project = services.project_service.load_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_project_payload(project)

    @api.delete("/api/projects/{project_id}")
    def delete_project(project_id: str) -> dict[str, str]:
        try:
            services.project_service.delete_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "deleted", "project_id": project_id}

    def _update_project_settings(project_id: str, payload: UpdateSettingsRequest) -> dict[str, Any]:
        patch = ProjectSettingsPatch(
            allow_cycles=payload.allow_cycles,
            auto_snapshot_minutes=payload.auto_snapshot_minutes,
            auto_snapshot_operations=payload.auto_snapshot_operations,
            system_prompt_style=payload.system_prompt_style,
            system_prompt_forbidden=payload.system_prompt_forbidden,
            system_prompt_notes=payload.system_prompt_notes,
            constitution_markdown=payload.constitution_markdown,
            clarify_markdown=payload.clarify_markdown,
            specification_markdown=payload.specification_markdown,
            plan_markdown=payload.plan_markdown,
            guide_skipped_docs=payload.guide_skipped_docs,
            global_directives=payload.global_directives,
            context_soft_min_chars=payload.context_soft_min_chars,
            context_soft_max_chars=payload.context_soft_max_chars,
            context_sentence_safe_expand_chars=payload.context_sentence_safe_expand_chars,
            context_soft_max_tokens=payload.context_soft_max_tokens,
            strict_json_fence_output=payload.strict_json_fence_output,
            context_compaction_enabled=payload.context_compaction_enabled,
            context_compaction_trigger_ratio=payload.context_compaction_trigger_ratio,
            context_compaction_keep_recent_chunks=payload.context_compaction_keep_recent_chunks,
            context_compaction_group_chunks=payload.context_compaction_group_chunks,
            context_compaction_chunk_chars=payload.context_compaction_chunk_chars,
            agent_tool_loop_enabled=payload.agent_tool_loop_enabled,
            agent_tool_loop_max_rounds=payload.agent_tool_loop_max_rounds,
            agent_tool_loop_max_calls_per_round=payload.agent_tool_loop_max_calls_per_round,
            agent_tool_loop_single_read_char_limit=payload.agent_tool_loop_single_read_char_limit,
            agent_tool_loop_total_read_char_limit=payload.agent_tool_loop_total_read_char_limit,
            agent_tool_loop_no_progress_limit=payload.agent_tool_loop_no_progress_limit,
            agent_tool_write_proposal_enabled=payload.agent_tool_write_proposal_enabled,
        )
        try:
            project = services.project_service.update_project_settings(project_id, patch)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_project_payload(project)

    @api.put("/api/projects/{project_id}/settings")
    def update_settings(project_id: str, payload: UpdateSettingsRequest) -> dict[str, Any]:
        return _update_project_settings(project_id, payload)

    @api.patch("/api/projects/{project_id}")
    def patch_project_settings_compat(project_id: str, payload: UpdateSettingsRequest) -> dict[str, Any]:
        # Compatibility endpoint for older Web clients that PATCH /api/projects/{id}.
        return _update_project_settings(project_id, payload)

    @api.post("/api/projects/{project_id}/workflow-docs/start")
    def start_workflow_docs(project_id: str, payload: StartWorkflowRequest) -> dict[str, Any]:
        try:
            state = services.workflow_doc_service.start_workflow(
                project_id,
                mode=payload.mode,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_workflow_doc_payload(state)

    @api.post("/api/projects/{project_id}/workflow-docs/auto-start")
    def auto_start_workflow_docs(project_id: str, payload: AutoStartWorkflowRequest) -> dict[str, Any]:
        try:
            state = services.workflow_doc_service.start_workflow_auto(
                project_id,
                user_input=payload.user_input,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_workflow_doc_payload(state)

    @api.post("/api/projects/{project_id}/workflow-docs/input")
    def submit_workflow_docs_stage_input(
        project_id: str,
        payload: SubmitWorkflowStageInputRequest,
    ) -> dict[str, Any]:
        try:
            state = services.workflow_doc_service.submit_stage_input(
                project_id,
                user_input=payload.user_input,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_workflow_doc_payload(state)

    @api.post("/api/projects/{project_id}/workflow-docs/confirm")
    def confirm_workflow_docs_round(
        project_id: str,
        payload: ConfirmWorkflowRoundRequest,
    ) -> dict[str, Any]:
        try:
            state = services.workflow_doc_service.confirm_round(
                project_id,
                round_number=payload.round_number,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_workflow_doc_payload(state)

    @api.post("/api/projects/{project_id}/workflow-docs/publish")
    def publish_workflow_docs(project_id: str) -> dict[str, Any]:
        try:
            state = services.workflow_doc_service.publish_pending_docs(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_workflow_doc_payload(state)

    @api.get("/api/projects/{project_id}/workflow-docs")
    def get_workflow_docs_state(project_id: str) -> dict[str, Any]:
        try:
            state = services.workflow_doc_service.get_state(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_workflow_doc_payload(state)

    @api.get("/api/projects/{project_id}/nodes")
    def list_nodes(project_id: str) -> list[dict[str, Any]]:
        try:
            nodes = services.graph_service.list_nodes(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [_to_node_payload(node) for node in nodes]

    @api.post("/api/projects/{project_id}/nodes")
    def create_node(project_id: str, payload: CreateNodeRequest) -> dict[str, Any]:
        try:
            node = services.graph_service.add_node(
                project_id,
                NodeCreate(
                    title=payload.title,
                    type=payload.type,
                    status=payload.status,
                    storyline_id=payload.storyline_id,
                    pos_x=payload.pos_x,
                    pos_y=payload.pos_y,
                    metadata=payload.metadata,
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_node_payload(node)

    @api.put("/api/projects/{project_id}/nodes/{node_id}")
    def update_node(
        project_id: str,
        node_id: str,
        payload: UpdateNodeRequest,
    ) -> dict[str, Any]:
        patch = payload.model_dump(exclude_none=True)
        try:
            node = services.graph_service.update_node(project_id, node_id, patch)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_node_payload(node)

    @api.delete("/api/projects/{project_id}/nodes/{node_id}")
    def delete_node(project_id: str, node_id: str) -> dict[str, str]:
        try:
            services.graph_service.delete_node(project_id, node_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "deleted", "node_id": node_id}

    @api.get("/api/projects/{project_id}/edges")
    def list_edges(project_id: str) -> list[dict[str, Any]]:
        try:
            edges = services.graph_service.list_edges(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [_to_edge_payload(edge) for edge in edges]

    @api.post("/api/projects/{project_id}/edges")
    def create_edge(project_id: str, payload: CreateEdgeRequest) -> dict[str, Any]:
        try:
            edge = services.graph_service.add_edge(
                project_id,
                source_id=payload.source_id,
                target_id=payload.target_id,
                label=payload.label,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_edge_payload(edge)

    @api.post("/api/projects/{project_id}/edges/reorder")
    def reorder_edges(project_id: str, payload: ReorderEdgesRequest) -> dict[str, Any]:
        try:
            edges = services.graph_service.reorder_outgoing_edges(
                project_id,
                source_id=payload.source_id,
                ordered_edge_ids=payload.edge_ids,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "source_id": payload.source_id,
            "edges": [_to_edge_payload(item) for item in edges],
        }

    @api.delete("/api/projects/{project_id}/edges/{edge_id}")
    def delete_edge(project_id: str, edge_id: str) -> dict[str, str]:
        try:
            services.graph_service.delete_edge(project_id, edge_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "deleted", "edge_id": edge_id}

    @api.post("/api/projects/{project_id}/validate")
    def validate(project_id: str) -> dict[str, Any]:
        try:
            report = services.validation_service.validate_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": report.project_id,
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "infos": len(report.infos),
            "issues": [asdict(issue) for issue in report.issues],
        }

    @api.post("/api/projects/{project_id}/export")
    def export_markdown(project_id: str, payload: ExportRequest) -> dict[str, Any]:
        try:
            output = services.export_service.export_markdown(
                project_id,
                traversal=payload.traversal,
                output_root=payload.output_root,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"project_id": project_id, "path": str(output)}

    @api.post("/api/projects/{project_id}/snapshots")
    def create_snapshot(project_id: str) -> dict[str, Any]:
        try:
            snapshot = services.snapshot_service.create_snapshot(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_snapshot_payload(snapshot)

    @api.get("/api/projects/{project_id}/snapshots")
    def list_snapshots(project_id: str) -> list[dict[str, Any]]:
        try:
            snapshots = services.snapshot_service.list_snapshots(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [_to_snapshot_payload(snapshot) for snapshot in snapshots]

    @api.post("/api/projects/{project_id}/rollback")
    def rollback(project_id: str, payload: RollbackRequest) -> dict[str, Any]:
        try:
            project = services.snapshot_service.rollback(project_id, payload.revision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_project_payload(project)

    @api.post("/api/state/extract")
    def extract_state_events(payload: ExtractStateEventsRequest) -> dict[str, Any]:
        try:
            extracted = services.state_service.extract_state_events(
                payload.project_id,
                payload.node_id,
                payload.content,
            )
            proposals: list[dict[str, Any]] = []
            if payload.create_proposals and extracted["events"]:
                proposals = services.state_service.create_state_change_proposals(
                    payload.project_id,
                    payload.node_id,
                    payload.thread_id,
                    extracted["events"],
                )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            **extracted,
            "thread_id": payload.thread_id,
            "proposals": proposals,
            "proposal_count": len(proposals),
        }

    @api.post("/api/state/proposals")
    def create_state_change_proposals(payload: CreateStateProposalsRequest) -> dict[str, Any]:
        try:
            proposals = services.state_service.create_state_change_proposals(
                payload.project_id,
                payload.node_id,
                payload.thread_id,
                payload.events,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "project_id": payload.project_id,
            "node_id": payload.node_id,
            "thread_id": payload.thread_id,
            "created": len(proposals),
            "proposals": proposals,
        }

    @api.get("/api/projects/{project_id}/state/proposals")
    def list_state_change_proposals(
        project_id: str,
        node_id: str | None = None,
        thread_id: str | None = None,
        status: str | None = None,
        include_applied: bool = True,
    ) -> dict[str, Any]:
        try:
            proposals = services.state_service.list_state_change_proposals(
                project_id,
                node_id=node_id,
                thread_id=thread_id,
                status=status,
                include_applied=include_applied,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "count": len(proposals),
            "proposals": proposals,
        }

    @api.post("/api/state/proposals/{proposal_id}/review")
    def review_state_change_proposal(
        proposal_id: str,
        payload: ReviewStateProposalRequest,
    ) -> dict[str, Any]:
        try:
            proposal = services.state_service.review_state_change_proposal(
                proposal_id,
                payload.action,
                payload.reviewer,
                payload.note,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return proposal

    @api.post("/api/state/apply")
    def apply_state_changes(payload: ApplyStateChangesRequest) -> dict[str, Any]:
        try:
            result = services.state_service.apply_approved_state_changes(
                payload.project_id,
                payload.node_id,
                payload.thread_id,
                proposal_ids=payload.proposal_ids,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result

    @api.get("/api/projects/{project_id}/state/characters")
    def get_character_status(
        project_id: str,
        character_ids: str | None = None,
    ) -> dict[str, Any]:
        ids = [part.strip() for part in str(character_ids or "").split(",") if part.strip()]
        try:
            rows = services.state_service.get_character_status(project_id, ids or None)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "count": len(rows),
            "characters": rows,
        }

    @api.get("/api/projects/{project_id}/state/items")
    def get_item_status(
        project_id: str,
        item_ids: str | None = None,
    ) -> dict[str, Any]:
        ids = [part.strip() for part in str(item_ids or "").split(",") if part.strip()]
        try:
            rows = services.state_service.get_item_status(project_id, ids or None)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "count": len(rows),
            "items": rows,
        }

    @api.get("/api/projects/{project_id}/state/relationships")
    def get_relationship_status(
        project_id: str,
        pairs: str | None = None,
    ) -> dict[str, Any]:
        parsed_pairs = _parse_relationship_pairs(
            [part.strip() for part in str(pairs or "").split(";") if part.strip()]
        )
        try:
            rows = services.state_service.get_relationship_status(project_id, parsed_pairs or None)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "count": len(rows),
            "relationships": rows,
        }

    @api.put("/api/state/relationships")
    def upsert_relationship_status(payload: UpsertRelationshipStatusRequest) -> dict[str, Any]:
        try:
            return services.state_service.upsert_relationship_status(
                payload.project_id,
                subject_character_id=payload.subject_character_id,
                object_character_id=payload.object_character_id,
                relation_type=payload.relation_type,
                node_id=str(payload.node_id or "").strip(),
                source_excerpt=payload.source_excerpt,
                confidence=payload.confidence,
                state_attributes=payload.state_attributes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.get("/api/projects/{project_id}/state/world-variables")
    def get_world_variable_status(
        project_id: str,
        keys: str | None = None,
    ) -> dict[str, Any]:
        key_list = [part.strip() for part in str(keys or "").split(",") if part.strip()]
        try:
            rows = services.state_service.get_world_variable_status(project_id, key_list or None)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "count": len(rows),
            "world_variables": rows,
        }

    @api.post("/api/state/prompt-payload")
    def build_prompt_state_payload(payload: PromptStatePayloadRequest) -> dict[str, Any]:
        pairs = _parse_relationship_pairs(payload.relationship_pairs)
        try:
            return services.state_service.build_prompt_state_payload(
                payload.project_id,
                character_ids=payload.character_ids or None,
                item_ids=payload.item_ids or None,
                relationship_pairs=pairs or None,
                world_variable_keys=payload.world_variable_keys or None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.get("/api/projects/{project_id}/state/conflicts")
    def list_state_conflicts(
        project_id: str,
        unresolved_only: bool = True,
    ) -> dict[str, Any]:
        try:
            conflicts = services.state_service.list_state_conflicts(
                project_id,
                unresolved_only=unresolved_only,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "count": len(conflicts),
            "conflicts": conflicts,
        }

    @api.post("/api/projects/{project_id}/state/audit")
    def audit_state_consistency(
        project_id: str,
        record_conflicts: bool = True,
    ) -> dict[str, Any]:
        try:
            return services.state_service.audit_state_consistency(
                project_id,
                record_conflicts=record_conflicts,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.post("/api/projects/{project_id}/state/rebuild")
    def rebuild_state_snapshot(
        project_id: str,
        payload: RebuildStateSnapshotRequest,
    ) -> dict[str, Any]:
        try:
            result = services.state_service.rebuild_state_snapshot(
                project_id,
                upto_revision=payload.upto_revision,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result

    @api.get("/api/projects/{project_id}/state/aliases/resolve")
    def resolve_entity_alias(
        project_id: str,
        entity_type: str,
        alias: str,
    ) -> dict[str, Any]:
        try:
            canonical_id = services.state_service.resolve_entity_alias(project_id, entity_type, alias)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "entity_type": entity_type,
            "alias": alias,
            "canonical_id": canonical_id,
        }

    @api.put("/api/state/aliases")
    def upsert_entity_alias(payload: UpsertEntityAliasRequest) -> dict[str, Any]:
        try:
            return services.state_service.upsert_entity_alias(
                payload.project_id,
                payload.entity_type,
                payload.alias,
                payload.canonical_id,
                payload.confidence,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.put("/api/state/attribute-schema")
    def upsert_state_attribute_schema(payload: UpsertStateSchemaRequest) -> dict[str, Any]:
        try:
            return services.state_service.upsert_state_attribute_schema(
                payload.project_id,
                payload.entity_type,
                payload.attr_key,
                payload.value_type,
                payload.constraints,
                description=payload.description,
                is_active=payload.is_active,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.get("/api/projects/{project_id}/state/attribute-schema/{entity_type}")
    def list_state_attribute_schema(
        project_id: str,
        entity_type: str,
    ) -> dict[str, Any]:
        try:
            rows = services.state_service.list_state_attribute_schema(project_id, entity_type)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "entity_type": entity_type,
            "count": len(rows),
            "schemas": rows,
        }

    @api.post("/api/generate/chapter")
    def generate_chapter(payload: GenerateChapterRequest) -> dict[str, Any]:
        try:
            workflow_mode = str(payload.workflow_mode or "").strip()
            if not workflow_mode:
                _, active_config = services.core_config_manager.load_active()
                workflow_mode = active_config.default_workflow_mode
            result = services.ai_service.generate_chapter(
                payload.project_id,
                payload.node_id,
                token_budget=payload.token_budget,
                style_hint=payload.style_hint,
                workflow_mode=workflow_mode,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "task_id": result.task_id,
            "project_id": result.project_id,
            "node_id": result.node_id,
            "content": result.content,
            "revision": result.revision,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "provider": result.provider,
            "workflow_mode": result.workflow_mode,
            "agent_trace": result.agent_trace,
        }

    @api.post("/api/generate/branches")
    def generate_branches(payload: GenerateBranchesRequest) -> dict[str, Any]:
        try:
            options = services.ai_service.generate_branches(
                payload.project_id,
                payload.node_id,
                n=payload.n,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "project_id": payload.project_id,
            "node_id": payload.node_id,
            "options": [{"title": item.title, "description": item.description} for item in options],
        }

    @api.post("/api/ai/chat")
    def ai_chat(payload: ChatAssistRequest) -> dict[str, Any]:
        try:
            result = services.ai_service.chat_assist(
                payload.project_id,
                message=payload.message,
                node_id=payload.node_id,
                thread_id=payload.thread_id,
                allow_node_write=payload.allow_node_write,
                guide_mode=payload.guide_mode,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "project_id": result.project_id,
            "node_id": result.node_id,
            "thread_id": result.thread_id,
            "route": result.route,
            "reply": result.reply,
            "review_bypassed": result.review_bypassed,
            "updated_node_id": result.updated_node_id,
            "suggested_node_ids": result.suggested_node_ids,
            "suggested_options": result.suggested_options,
            "guide_skip_document": result.guide_skip_document,
            "revision": result.revision,
        }

    @api.get("/api/projects/{project_id}/chat/threads")
    def list_project_chat_threads(project_id: str, limit: int = 50) -> dict[str, Any]:
        if repository.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail=f"project not found: {project_id}")
        rows = repository.list_chat_threads(project_id, limit=limit)
        return {
            "project_id": project_id,
            "count": len(rows),
            "threads": rows,
        }

    @api.post("/api/projects/{project_id}/chat/threads")
    def create_project_chat_thread(project_id: str, payload: CreateChatThreadRequest) -> dict[str, Any]:
        if repository.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail=f"project not found: {project_id}")
        requested_thread = str(payload.thread_id or "").strip()
        thread_id = requested_thread or generate_id("chat")
        try:
            repository.upsert_chat_thread(
                thread_id,
                project_id=project_id,
                node_id=str(payload.node_id or "").strip(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        thread = repository.get_chat_thread(thread_id) or {
            "thread_id": thread_id,
            "project_id": project_id,
            "node_id": str(payload.node_id or "").strip(),
        }
        return {
            "project_id": project_id,
            "thread_id": thread_id,
            "thread": thread,
        }

    @api.get("/api/projects/{project_id}/chat/threads/{thread_id}/messages")
    def list_project_chat_thread_messages(
        project_id: str,
        thread_id: str,
        limit: int = 80,
    ) -> dict[str, Any]:
        if repository.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail=f"project not found: {project_id}")
        thread = repository.get_chat_thread(thread_id)
        if thread is None or str(thread.get("project_id", "") or "") != project_id:
            raise HTTPException(status_code=404, detail=f"chat thread not found: {thread_id}")
        rows = repository.list_chat_messages(thread_id, limit=limit)
        return {
            "project_id": project_id,
            "thread_id": thread_id,
            "count": len(rows),
            "messages": rows,
        }

    @api.post("/api/ai/outline/guide")
    def ai_outline_guide(payload: OutlineGuideRequest) -> dict[str, Any]:
        try:
            result = services.ai_service.guide_project_outline(
                payload.project_id,
                goal=payload.goal,
                sync_context=payload.sync_context,
                specify=payload.specify,
                clarify_answers=payload.clarify_answers,
                plan_notes=payload.plan_notes,
                constraints=payload.constraints,
                tone=payload.tone,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "project_id": result.project_id,
            "questions": result.questions,
            "outline_markdown": result.outline_markdown,
            "chapter_beats": result.chapter_beats,
            "next_steps": result.next_steps,
            "provider": result.provider,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }

    @api.post("/api/ai/outline/detail_nodes")
    @api.post("/api/ai/outline/detail-nodes")
    @api.post("/api/ai/outline/detailNodes")
    def ai_outline_detail_nodes(payload: OutlineDetailNodesRequest) -> dict[str, Any]:
        try:
            result = services.ai_service.guide_outline_detail_nodes(
                payload.project_id,
                outline_markdown=payload.outline_markdown,
                chapter_beats=payload.chapter_beats,
                user_request=payload.user_request,
                mode=payload.mode,
                token_budget=payload.token_budget,
                max_nodes=payload.max_nodes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "project_id": result.project_id,
            "nodes": [
                {
                    "title": item.title,
                    "outline_markdown": item.outline_markdown,
                    "summary": item.summary,
                }
                for item in result.nodes
            ],
            "provider": result.provider,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }

    @api.post("/api/ai/workflow/clarify")
    def ai_workflow_clarify(payload: WorkflowClarifyRequest) -> dict[str, Any]:
        try:
            result = services.ai_service.guide_workflow_clarify(
                payload.project_id,
                goal=payload.goal,
                sync_context=payload.sync_context,
                specify=payload.specify,
                constraints=payload.constraints,
                tone=payload.tone,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "project_id": result.project_id,
            "questions": result.questions,
            "provider": result.provider,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }

    @api.post("/api/ai/workflow/sync")
    def ai_workflow_sync(payload: WorkflowSyncRequest) -> dict[str, Any]:
        try:
            result = services.ai_service.guide_workflow_sync_background(
                payload.project_id,
                goal=payload.goal,
                sync_context=payload.sync_context,
                mode=payload.mode,
                constraints=payload.constraints,
                tone=payload.tone,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "project_id": result.project_id,
            "background_markdown": result.background_markdown,
            "must_confirm": result.must_confirm,
            "citations": result.citations,
            "risk_notes": result.risk_notes,
            "search_requested": result.search_requested,
            "search_used": result.search_used,
            "provider": result.provider,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }

    @api.post("/api/ai/clarification/question")
    def ai_clarification_question(payload: ClarificationQuestionRequest) -> dict[str, Any]:
        try:
            result = services.ai_service.generate_clarification_question(
                payload.project_id,
                node_id=payload.node_id,
                context=payload.context,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "project_id": result.project_id,
            "clarification_id": result.clarification_id,
            "question_type": result.question_type,
            "question": result.question,
            "options": result.options,
            "must_answer": result.must_answer,
            "timeout_sec": result.timeout_sec,
            "setting_proposal_status": result.setting_proposal_status,
            "provider": result.provider,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }

    @api.post("/api/agent/session/start")
    def start_agent_session(payload: StartAgentSessionRequest) -> dict[str, Any]:
        try:
            return services.session_orchestrator_service.start_session(
                project_id=payload.project_id,
                node_id=payload.node_id,
                mode=payload.mode,
                token_budget=payload.token_budget,
                style_hint=payload.style_hint,
                thread_id=payload.thread_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.post("/api/agent/session/resume")
    def resume_agent_session(payload: ResumeAgentSessionRequest) -> dict[str, Any]:
        try:
            session = services.session_orchestrator_service.resume_session(payload.thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "thread_id": payload.thread_id,
            "session": session,
        }

    @api.get("/api/agent/session/{thread_id}")
    def get_agent_session(thread_id: str) -> dict[str, Any]:
        try:
            session = services.session_orchestrator_service.get_session_state(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "thread_id": thread_id,
            "session": session,
        }

    @api.get("/api/projects/{project_id}/agent/session/latest")
    def get_latest_project_agent_session(project_id: str) -> dict[str, Any]:
        try:
            payload = services.session_orchestrator_service.get_latest_session_for_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not payload:
            return {"project_id": project_id, "thread_id": "", "session": None}
        return {
            "project_id": project_id,
            "thread_id": str(payload.get("thread_id", "") or ""),
            "session": payload.get("session"),
        }

    @api.get("/api/agent/session/{thread_id}/audits")
    def get_agent_session_audits(thread_id: str) -> dict[str, Any]:
        try:
            _ = services.session_orchestrator_service.get_session_state(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        rounds = repository.list_agent_loop_rounds(thread_id)
        tool_calls = repository.list_agent_tool_calls(thread_id)
        metrics = repository.list_agent_loop_metrics(thread_id)
        return {
            "thread_id": thread_id,
            "agent_loop_rounds": rounds,
            "agent_tool_calls": tool_calls,
            "agent_loop_metrics": metrics,
            "round_count": len(rounds),
            "tool_call_count": len(tool_calls),
            "metrics_count": len(metrics),
        }

    @api.post("/api/agent/session/decision")
    def submit_agent_decision(payload: SubmitAgentDecisionRequest) -> dict[str, Any]:
        try:
            return services.session_orchestrator_service.submit_decision(
                thread_id=payload.thread_id,
                action=payload.action,
                decision_id=payload.decision_id,
                expected_state_version=payload.expected_state_version,
                payload=payload.payload,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.post("/api/agent/session/clarification/question")
    def request_agent_clarification(payload: RequestAgentClarificationRequest) -> dict[str, Any]:
        try:
            return services.session_orchestrator_service.request_clarification_question(
                thread_id=payload.thread_id,
                context=payload.context,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.post("/api/agent/session/clarification/answer")
    def submit_agent_clarification_answer(payload: SubmitClarificationAnswerRequest) -> dict[str, Any]:
        try:
            return services.session_orchestrator_service.submit_clarification_answer(
                thread_id=payload.thread_id,
                clarification_id=payload.clarification_id,
                decision_id=payload.decision_id,
                selected_option=payload.selected_option,
                answer_text=payload.answer_text,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.post("/api/agent/session/setting_proposal/review")
    def review_agent_setting_proposal(payload: ReviewSettingProposalActionRequest) -> dict[str, Any]:
        try:
            return services.session_orchestrator_service.review_setting_proposal(
                thread_id=payload.thread_id,
                proposal_id=payload.proposal_id,
                action=payload.action,
                reviewer=payload.reviewer,
                note=payload.note,
                decision_id=payload.decision_id,
                expected_state_version=payload.expected_state_version,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.get("/api/agent/session/{thread_id}/setting_proposals")
    def list_agent_setting_proposals(thread_id: str, status: str | None = None) -> dict[str, Any]:
        try:
            proposals = services.session_orchestrator_service.list_setting_proposals(
                thread_id=thread_id,
                status=status,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "thread_id": thread_id,
            "status_filter": status or "",
            "setting_proposals": proposals,
            "count": len(proposals),
        }

    @api.post("/api/agent/session/setting_proposals/review_batch")
    def review_agent_setting_proposals_batch(payload: ReviewSettingProposalsBatchRequest) -> dict[str, Any]:
        try:
            return services.session_orchestrator_service.review_setting_proposals_batch(
                thread_id=payload.thread_id,
                action=payload.action,
                proposal_ids=payload.proposal_ids,
                reviewer=payload.reviewer,
                note=payload.note,
                decision_id=payload.decision_id,
                expected_state_version=payload.expected_state_version,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.post("/api/agent/session/diff/review")
    def review_agent_diff(payload: SubmitDiffReviewRequest) -> dict[str, Any]:
        try:
            return services.session_orchestrator_service.submit_diff_review(
                thread_id=payload.thread_id,
                diff_id=payload.diff_id,
                decision_id=payload.decision_id,
                accepted_hunk_ids=payload.accepted_hunk_ids,
                rejected_hunk_ids=payload.rejected_hunk_ids,
                edited_hunks=payload.edited_hunks,
                expected_base_revision=payload.expected_base_revision,
                expected_base_hash=payload.expected_base_hash,
                expected_state_version=payload.expected_state_version,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.post("/api/agent/session/{thread_id}/cancel")
    def cancel_agent_session(thread_id: str) -> dict[str, Any]:
        try:
            return services.session_orchestrator_service.cancel_session(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/projects/{project_id}/suggestions/cleanup")
    def clear_suggestions(project_id: str) -> dict[str, Any]:
        try:
            deleted = services.ai_service.clear_suggested_nodes(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "deleted": deleted,
        }

    @api.get("/api/projects/{project_id}/insights")
    def project_insights(project_id: str) -> dict[str, Any]:
        try:
            return services.insight_service.build_project_insights(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/review/lore")
    def review_lore(payload: ReviewRequest) -> dict[str, Any]:
        try:
            report = services.ai_service.review_lore(
                payload.project_id,
                payload.node_id,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "task_id": report.task_id,
            "project_id": report.project_id,
            "node_id": report.node_id,
            "review_type": report.review_type,
            "summary": report.summary,
            "score": report.score,
            "issues": report.issues,
            "revision": report.revision,
        }

    @api.post("/api/review/logic")
    def review_logic(payload: ReviewRequest) -> dict[str, Any]:
        try:
            report = services.ai_service.review_logic(
                payload.project_id,
                payload.node_id,
                token_budget=payload.token_budget,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "task_id": report.task_id,
            "project_id": report.project_id,
            "node_id": report.node_id,
            "review_type": report.review_type,
            "summary": report.summary,
            "score": report.score,
            "issues": report.issues,
            "revision": report.revision,
        }

    @api.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        try:
            task = services.ai_service.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_task_payload(task)

    @api.post("/api/tasks/{task_id}/cancel")
    def cancel_task(task_id: str) -> dict[str, Any]:
        try:
            task = services.ai_service.cancel_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_task_payload(task)

    @api.get("/api/projects/{project_id}/tasks")
    def list_tasks(
        project_id: str,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        parsed_status = None
        if status:
            try:
                parsed_status = TaskStatus(status)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=tr("api.error.invalid_task_status", status=status),
                ) from exc
        try:
            tasks = services.ai_service.list_tasks(
                project_id,
                status=parsed_status,
                limit=limit,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [_to_task_payload(task) for task in tasks]

    return api


app = create_app(os.getenv("ELYHA_DB_PATH", "./data/elyha.db"))
