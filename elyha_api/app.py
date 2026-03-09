"""FastAPI app for local ElyHa adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from elyha_core.i18n import tr
from elyha_core.core_config import CORE_PROFILE, CoreConfigManager, CoreRuntimeConfig
from elyha_core.llm_presets import LLMPreset, load_llm_presets
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
from elyha_core.services.snapshot_service import SnapshotService
from elyha_core.services.validation_service import ValidationService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.storage.sqlite_store import SQLiteStore


@dataclass(slots=True)
class ServiceContainer:
    project_service: ProjectService
    graph_service: GraphService
    validation_service: ValidationService
    export_service: ExportService
    snapshot_service: SnapshotService
    context_service: ContextService
    ai_service: AIService
    insight_service: InsightService
    core_config_manager: CoreConfigManager
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


class GenerateChapterRequest(BaseModel):
    project_id: str
    node_id: str
    token_budget: int = Field(default=2200, ge=1)
    style_hint: str = ""
    workflow_mode: str = "multi_agent"


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


class UpdateRuntimeSettingsRequest(BaseModel):
    locale: str | None = None
    llm_provider: str | None = None
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


def _to_runtime_config_payload(config: CoreRuntimeConfig) -> dict[str, Any]:
    return {
        "locale": config.locale,
        "llm_provider": config.llm_provider,
        "api_url": config.api_url,
        "api_key": config.api_key,
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
        "api_format": preset.api_format,
        "api_url": preset.api_url,
        "auto_complete": preset.auto_complete,
        "default_model": preset.model,
        "models": list(preset.models),
    }


def _to_llm_platform_config(config: CoreRuntimeConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "auto_complete": bool(config.auto_complete),
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
    )


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Create FastAPI app with isolated service container."""
    db_file = Path(db_path or "./data/elyha.db")
    repository = SQLiteRepository(SQLiteStore(db_file))
    project_service = ProjectService(repository)
    graph_service = GraphService(repository)
    validation_service = ValidationService(repository)
    context_service = ContextService(repository)
    config_root = Path(os.getenv("ELYHA_CORE_CONFIG_DIR", db_file.parent / "core_configs"))
    core_config_manager = CoreConfigManager(config_root)
    preset_path = Path(os.getenv("ELYHA_PRESET_PATH", Path(__file__).resolve().parent.parent / "preset.json"))
    llm_presets = load_llm_presets(preset_path)
    _, runtime_config = core_config_manager.load_active()
    os.environ["ELYHA_LOCALE"] = runtime_config.locale
    ai_service = _build_ai_service(
        repository,
        graph_service,
        context_service,
        validation_service,
        runtime_config,
        llm_presets,
    )
    services = ServiceContainer(
        project_service=project_service,
        graph_service=graph_service,
        validation_service=validation_service,
        export_service=ExportService(repository, validation_service),
        snapshot_service=SnapshotService(repository),
        context_service=context_service,
        ai_service=ai_service,
        insight_service=InsightService(repository),
        core_config_manager=core_config_manager,
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

    def _apply_runtime_config(config: CoreRuntimeConfig) -> None:
        os.environ["ELYHA_LOCALE"] = config.locale
        services.ai_service = _build_ai_service(
            repository,
            graph_service,
            context_service,
            validation_service,
            config,
            services.llm_presets,
        )

    @api.get("/api/llm/presets")
    def list_llm_presets() -> list[dict[str, Any]]:
        return [
            _to_llm_preset_payload(preset)
            for preset in services.llm_presets.values()
        ]

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

    @api.post("/api/generate/chapter")
    def generate_chapter(payload: GenerateChapterRequest) -> dict[str, Any]:
        try:
            result = services.ai_service.generate_chapter(
                payload.project_id,
                payload.node_id,
                token_budget=payload.token_budget,
                style_hint=payload.style_hint,
                workflow_mode=payload.workflow_mode,
            )
        except (KeyError, ValueError) as exc:
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
        except (KeyError, ValueError) as exc:
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
                token_budget=payload.token_budget,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "project_id": result.project_id,
            "node_id": result.node_id,
            "route": result.route,
            "reply": result.reply,
            "review_bypassed": result.review_bypassed,
            "updated_node_id": result.updated_node_id,
            "suggested_node_ids": result.suggested_node_ids,
            "suggested_options": result.suggested_options,
            "revision": result.revision,
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
        except (KeyError, ValueError) as exc:
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
        except (KeyError, ValueError) as exc:
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
        except (KeyError, ValueError) as exc:
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
        except (KeyError, ValueError) as exc:
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
        except (KeyError, ValueError) as exc:
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
        except (KeyError, ValueError) as exc:
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
