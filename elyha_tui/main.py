"""CLI entrypoint for ElyHa Rich TUI."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
from typing import Any
from typing import Sequence
from typing import cast

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from elyha_core.core_config import CoreConfigManager, CoreRuntimeConfig
from elyha_core.i18n import available_locales, current_locale, tr
from elyha_core.llm_presets import load_llm_presets
from elyha_core.models.task import TaskStatus
from elyha_core.services.ai_service import AIService
from elyha_core.services.context_service import ContextService
from elyha_core.services.export_service import ExportService
from elyha_core.services.graph_service import GraphService
from elyha_core.services.project_service import ProjectService
from elyha_core.services.snapshot_service import SnapshotService
from elyha_core.services.validation_service import ValidationService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.storage.sqlite_store import SQLiteStore
from elyha_tui.commands.ai_cmd import (
    ai_status,
    generate_branches,
    generate_chapter,
    review_logic,
    review_lore,
    task_cancel,
    task_get,
    task_list,
)
from elyha_tui.commands.export_cmd import export_markdown
from elyha_tui.commands.graph_cmd import (
    edge_add,
    edge_delete,
    edge_list,
    graph_view,
    node_add,
    node_delete,
    node_list,
    node_move,
    node_update,
    validate_project,
)
from elyha_tui.commands.project_cmd import (
    project_create,
    project_delete,
    project_list,
    project_open,
    project_rename,
    project_update_settings,
)
from elyha_tui.commands.snapshot_cmd import (
    rollback_to_revision,
    snapshot_create,
    snapshot_list,
)


console = Console()
AUTOMATION_COMMANDS = (
    "project-create",
    "project-list",
    "project-open",
    "project-rename",
    "project-settings",
    "project-delete",
    "node-add",
    "node-update",
    "node-move",
    "node-delete",
    "node-list",
    "graph-view",
    "edge-add",
    "edge-delete",
    "edge-list",
    "validate",
    "export",
    "snapshot-create",
    "snapshot-list",
    "rollback",
    "ai-status",
    "generate-chapter",
    "generate-branches",
    "review-lore",
    "review-logic",
    "task-get",
    "task-cancel",
    "task-list",
    "settings",
)

MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("1", "project-create"),
    ("2", "project-open"),
    ("3", "project-list"),
    ("4", "node-add"),
    ("5", "node-update"),
    ("6", "node-move"),
    ("7", "edge-add"),
    ("8", "graph-view"),
    ("9", "graph-edit"),
    ("10", "generate-chapter"),
    ("11", "generate-branches"),
    ("12", "review-lore"),
    ("13", "review-logic"),
    ("14", "task-list"),
    ("15", "snapshot-create"),
    ("16", "rollback"),
    ("17", "export"),
    ("18", "settings"),
)

MENU_INDEX: dict[str, str] = dict(MENU_ITEMS)

GRAPH_MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("1", "add-node"),
    ("2", "rename-node"),
    ("3", "move-node"),
    ("4", "delete-node"),
    ("5", "add-edge"),
    ("6", "delete-edge"),
    ("7", "validate"),
    ("8", "list"),
    ("9", "help"),
)

GRAPH_MENU_INDEX: dict[str, str] = dict(GRAPH_MENU_ITEMS)


@dataclass(slots=True)
class Runtime:
    repository: SQLiteRepository
    project_service: ProjectService
    graph_service: GraphService
    validation_service: ValidationService
    context_service: ContextService
    ai_service: AIService
    export_service: ExportService
    snapshot_service: SnapshotService
    default_workflow_mode: str = "multi_agent"


@dataclass(slots=True)
class SessionState:
    current_project_id: str | None = None
    last_command: str | None = None


@dataclass(slots=True)
class PromptField:
    key: str
    label: str
    required: bool = False
    default: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elyha", description=tr("tui.parser.description"))
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=tr("tui.arg.smoke"),
    )
    parser.add_argument(
        "--db",
        default="./data/elyha.db",
        help=tr("tui.arg.db"),
    )
    parser.add_argument(
        "--automation",
        choices=AUTOMATION_COMMANDS,
        help=tr("tui.arg.automation"),
    )
    parser.add_argument("--project-id")
    parser.add_argument("--title")
    parser.add_argument("--node-id")
    parser.add_argument("--edge-id")
    parser.add_argument("--source-id")
    parser.add_argument("--target-id")
    parser.add_argument("--type", default="chapter")
    parser.add_argument("--status", default="draft")
    parser.add_argument("--storyline-id")
    parser.add_argument("--pos-x", type=float, default=0.0)
    parser.add_argument("--pos-y", type=float, default=0.0)
    parser.add_argument("--label", default="")
    parser.add_argument("--metadata-json")
    parser.add_argument("--patch-json")
    parser.add_argument("--traversal", default="mainline")
    parser.add_argument("--output-root", default="exports")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--task-id")
    parser.add_argument("--task-status")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--token-budget", type=int, default=2200)
    parser.add_argument("--style-hint", default="")
    parser.add_argument("--workflow-mode")
    parser.add_argument("--locale", help=tr("tui.arg.locale"))
    parser.add_argument("--allow-cycles")
    parser.add_argument("--auto-snapshot-minutes", type=int)
    parser.add_argument("--auto-snapshot-operations", type=int)
    parser.add_argument("--system-prompt-style")
    parser.add_argument("--system-prompt-forbidden")
    parser.add_argument("--system-prompt-notes")
    return parser


def run_smoke() -> int:
    console.print(f"[green]{tr('tui.smoke.ok')}[/green]")
    return 0


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


def _build_runtime(db_path: str | Path) -> Runtime:
    db_file = Path(db_path)
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
    ai_service = AIService(
        repository,
        graph_service,
        context_service,
        validation_service,
        llm_provider=runtime_config.llm_provider,
        llm_platform_config=_to_llm_platform_config(runtime_config),
        llm_presets=llm_presets,
    )
    export_service = ExportService(repository, validation_service)
    snapshot_service = SnapshotService(repository)
    return Runtime(
        repository=repository,
        project_service=project_service,
        graph_service=graph_service,
        validation_service=validation_service,
        context_service=context_service,
        ai_service=ai_service,
        export_service=export_service,
        snapshot_service=snapshot_service,
        default_workflow_mode=runtime_config.default_workflow_mode,
    )


def _bool_from_text(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(tr("tui.error.invalid_bool", value=value))


def _parse_json_dict(raw: str | None, *, field: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(tr("tui.error.json_dict_required", field=field))
    return parsed


def _require_text(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if value is None:
        raise ValueError(tr("tui.error.arg_missing", name=key))
    text = str(value).strip()
    if not text:
        raise ValueError(tr("tui.error.arg_empty", name=key))
    return text


def _parse_locale(value: str) -> str:
    text = value.strip().lower()
    text = text.replace("-", "_")
    if "." in text:
        text = text.split(".", 1)[0]
    if "_" in text:
        text = text.split("_", 1)[0]
    supported = available_locales()
    if text not in supported:
        raise ValueError(
            tr(
                "tui.error.locale_invalid",
                locale=value,
                supported=", ".join(supported),
            )
        )
    return text


def _settings_payload() -> dict[str, Any]:
    return {
        "locale": current_locale(),
        "supported_locales": list(available_locales()),
    }


def _command_desc_key(command: str) -> str:
    return f"tui.help.desc.{command.replace('-', '_')}"


def _alias_tokens(raw: str) -> list[str]:
    return [item.strip().lower().replace("_", "-") for item in raw.split(",") if item.strip()]


def _main_command_aliases() -> dict[str, str]:
    command_list = (
        "help",
        "menu",
        "exit",
        "quit",
        "graph-edit",
        *AUTOMATION_COMMANDS,
    )
    mapping: dict[str, str] = {}
    for command in command_list:
        canonical = command.lower()
        mapping[canonical] = canonical
        mapping[canonical.replace("_", "-")] = canonical
        alias_key = f"tui.alias.command.{canonical.replace('-', '_')}"
        alias_raw = tr(alias_key)
        if alias_raw != alias_key:
            for token in _alias_tokens(alias_raw):
                mapping[token] = canonical
    return mapping


def _graph_command_aliases() -> dict[str, str]:
    command_list = (
        "help",
        "menu",
        "back",
        "exit",
        "quit",
        "list",
        "add-node",
        "rename-node",
        "move-node",
        "delete-node",
        "add-edge",
        "delete-edge",
        "validate",
    )
    mapping: dict[str, str] = {}
    for command in command_list:
        canonical = command.lower()
        mapping[canonical] = canonical
        alias_key = f"graph.alias.command.{canonical.replace('-', '_')}"
        alias_raw = tr(alias_key)
        if alias_raw != alias_key:
            for token in _alias_tokens(alias_raw):
                mapping[token] = canonical
    return mapping


def _normalize_main_command(command: str) -> str:
    normalized = command.strip().lower().replace("_", "-")
    return _main_command_aliases().get(normalized, normalized)


def _normalize_graph_command(command: str) -> str:
    normalized = command.strip().lower().replace("_", "-")
    return _graph_command_aliases().get(normalized, normalized)


def _print_numeric_menu() -> None:
    table = Table(title=tr("tui.menu.title"))
    table.add_column(tr("tui.col.number"))
    table.add_column(tr("tui.col.command"))
    table.add_column(tr("tui.col.description"))
    table.add_row("0", tr("tui.menu.exit_command"), tr("tui.menu.exit_desc"))
    for number, command in MENU_ITEMS:
        table.add_row(number, command, tr(_command_desc_key(command)))
    console.print(table)
    console.print(f"[dim]{tr('tui.menu.tips')}[/dim]")


def _print_graph_numeric_menu() -> None:
    table = Table(title=tr("graph.menu.title"))
    table.add_column(tr("tui.col.number"))
    table.add_column(tr("tui.col.command"))
    table.add_column(tr("tui.col.description"))
    table.add_row("0", tr("graph.menu.back_command"), tr("graph.menu.back_desc"))
    for number, command in GRAPH_MENU_ITEMS:
        table.add_row(number, command, tr(f"graph.help.desc.{command.replace('-', '_')}"))
    console.print(table)
    console.print(f"[dim]{tr('graph.menu.tips')}[/dim]")


def _project_prompt_field(state: SessionState) -> PromptField:
    return PromptField(
        key="project_id",
        label=tr("tui.wizard.field.project_id"),
        required=state.current_project_id is None,
        default=state.current_project_id,
    )


def _build_prompt_fields(
    command: str,
    state: SessionState,
    *,
    default_workflow_mode: str,
) -> list[PromptField]:
    project = _project_prompt_field(state)
    if command == "project-create":
        return [PromptField("title", tr("tui.wizard.field.title"), required=True)]
    if command == "project-open":
        return [PromptField("project_id", tr("tui.wizard.field.project_id"), required=True)]
    if command == "project-rename":
        return [project, PromptField("title", tr("tui.wizard.field.title"), required=True)]
    if command == "project-settings":
        return [
            project,
            PromptField("allow_cycles", tr("tui.wizard.field.allow_cycles")),
            PromptField(
                "auto_snapshot_minutes",
                tr("tui.wizard.field.auto_snapshot_minutes"),
            ),
            PromptField(
                "auto_snapshot_operations",
                tr("tui.wizard.field.auto_snapshot_operations"),
            ),
            PromptField(
                "system_prompt_style",
                tr("tui.wizard.field.system_prompt_style"),
            ),
            PromptField(
                "system_prompt_forbidden",
                tr("tui.wizard.field.system_prompt_forbidden"),
            ),
            PromptField(
                "system_prompt_notes",
                tr("tui.wizard.field.system_prompt_notes"),
            ),
        ]
    if command == "project-delete":
        return [project]
    if command == "node-add":
        return [
            project,
            PromptField("title", tr("tui.wizard.field.title"), required=True),
            PromptField("type", tr("tui.wizard.field.node_type"), default="chapter"),
            PromptField("status", tr("tui.wizard.field.node_status"), default="draft"),
            PromptField("storyline_id", tr("tui.wizard.field.storyline_id")),
            PromptField("pos_x", tr("tui.wizard.field.pos_x"), default="0"),
            PromptField("pos_y", tr("tui.wizard.field.pos_y"), default="0"),
            PromptField("metadata_json", tr("tui.wizard.field.metadata_json")),
        ]
    if command == "node-update":
        return [
            project,
            PromptField("node_id", tr("tui.wizard.field.node_id"), required=True),
            PromptField("patch_json", tr("tui.wizard.field.patch_json"), required=True),
        ]
    if command == "node-move":
        return [
            project,
            PromptField("node_id", tr("tui.wizard.field.node_id"), required=True),
            PromptField("pos_x", tr("tui.wizard.field.pos_x"), required=True),
            PromptField("pos_y", tr("tui.wizard.field.pos_y"), required=True),
        ]
    if command == "node-delete":
        return [
            project,
            PromptField("node_id", tr("tui.wizard.field.node_id"), required=True),
        ]
    if command == "node-list":
        return [project]
    if command == "edge-add":
        return [
            project,
            PromptField("source_id", tr("tui.wizard.field.source_id"), required=True),
            PromptField("target_id", tr("tui.wizard.field.target_id"), required=True),
            PromptField("label", tr("tui.wizard.field.label")),
        ]
    if command == "edge-delete":
        return [project, PromptField("edge_id", tr("tui.wizard.field.edge_id"), required=True)]
    if command == "edge-list":
        return [project]
    if command == "graph-view":
        return [project]
    if command == "graph-edit":
        return [project]
    if command == "validate":
        return [project]
    if command == "export":
        return [
            project,
            PromptField("traversal", tr("tui.wizard.field.traversal"), default="mainline"),
            PromptField("output_root", tr("tui.wizard.field.output_root"), default="exports"),
        ]
    if command == "snapshot-create":
        return [project]
    if command == "snapshot-list":
        return [project]
    if command == "rollback":
        return [
            project,
            PromptField("revision", tr("tui.wizard.field.revision"), required=True),
        ]
    if command == "generate-chapter":
        return [
            project,
            PromptField("node_id", tr("tui.wizard.field.node_id"), required=True),
            PromptField("token_budget", tr("tui.wizard.field.token_budget"), default="2200"),
            PromptField("style_hint", tr("tui.wizard.field.style_hint")),
            PromptField(
                "workflow_mode",
                tr("tui.wizard.field.workflow_mode"),
                default=default_workflow_mode,
            ),
        ]
    if command == "generate-branches":
        return [
            project,
            PromptField("node_id", tr("tui.wizard.field.node_id"), required=True),
            PromptField("n", tr("tui.wizard.field.n"), default="3"),
            PromptField("token_budget", tr("tui.wizard.field.token_budget"), default="1800"),
        ]
    if command in {"review-lore", "review-logic"}:
        return [
            project,
            PromptField("node_id", tr("tui.wizard.field.node_id"), required=True),
            PromptField("token_budget", tr("tui.wizard.field.token_budget"), default="1500"),
        ]
    if command == "task-get":
        return [PromptField("task_id", tr("tui.wizard.field.task_id"), required=True)]
    if command == "task-cancel":
        return [PromptField("task_id", tr("tui.wizard.field.task_id"), required=True)]
    if command == "task-list":
        return [
            project,
            PromptField("task_status", tr("tui.wizard.field.task_status")),
            PromptField("limit", tr("tui.wizard.field.limit")),
        ]
    if command == "settings":
        return [PromptField("locale", tr("tui.wizard.field.locale"), default=current_locale())]
    return []


def _build_graph_prompt_fields(command: str) -> list[PromptField]:
    if command == "add-node":
        return [
            PromptField("title", tr("tui.wizard.field.title"), required=True),
            PromptField("type", tr("tui.wizard.field.node_type"), default="chapter"),
            PromptField("status", tr("tui.wizard.field.node_status"), default="draft"),
            PromptField("x", tr("graph.wizard.field.x"), default="0"),
            PromptField("y", tr("graph.wizard.field.y"), default="0"),
            PromptField("storyline_id", tr("tui.wizard.field.storyline_id")),
            PromptField("metadata_json", tr("tui.wizard.field.metadata_json")),
        ]
    if command == "rename-node":
        return [
            PromptField("node_id", tr("tui.wizard.field.node_id"), required=True),
            PromptField("title", tr("tui.wizard.field.title"), required=True),
        ]
    if command == "move-node":
        return [
            PromptField("node_id", tr("tui.wizard.field.node_id"), required=True),
            PromptField("x", tr("graph.wizard.field.x"), required=True),
            PromptField("y", tr("graph.wizard.field.y"), required=True),
        ]
    if command == "delete-node":
        return [PromptField("node_id", tr("tui.wizard.field.node_id"), required=True)]
    if command == "add-edge":
        return [
            PromptField("source_id", tr("tui.wizard.field.source_id"), required=True),
            PromptField("target_id", tr("tui.wizard.field.target_id"), required=True),
            PromptField("label", tr("tui.wizard.field.label")),
        ]
    if command == "delete-edge":
        return [PromptField("edge_id", tr("tui.wizard.field.edge_id"), required=True)]
    return []


def _prompt_with_fields(command: str, fields: list[PromptField]) -> dict[str, Any] | None:
    if not fields:
        return {}
    console.print(f"[cyan]{tr('tui.wizard.title', command=command)}[/cyan]")
    params: dict[str, Any] = {}
    for field in fields:
        while True:
            label = field.label
            if field.default is not None:
                prompt = tr("tui.wizard.prompt.with_default", label=label, default=field.default)
            elif field.required:
                prompt = tr("tui.wizard.prompt.required", label=label)
            else:
                prompt = tr("tui.wizard.prompt.optional", label=label)
            raw = console.input(prompt).strip()
            if raw in {"!", "back"}:
                console.print(f"[yellow]{tr('tui.wizard.cancelled')}[/yellow]")
                return None
            if not raw:
                if field.default is not None:
                    params[field.key] = field.default
                    break
                if field.required:
                    console.print(
                        f"[red]{tr('tui.error.arg_missing', name=field.key)}[/red]"
                    )
                    continue
                break
            params[field.key] = raw
            break
    return params


def _prompt_for_params(
    command: str,
    state: SessionState,
    runtime: Runtime,
) -> dict[str, Any] | None:
    return _prompt_with_fields(
        command,
        _build_prompt_fields(
            command,
            state,
            default_workflow_mode=runtime.default_workflow_mode,
        ),
    )


def _prompt_for_graph_params(command: str) -> dict[str, Any] | None:
    return _prompt_with_fields(command, _build_graph_prompt_fields(command))


def _resolve_project_id(params: dict[str, Any], state: SessionState) -> str:
    value = params.get("project_id")
    if value is not None:
        return str(value)
    if state.current_project_id is not None:
        return state.current_project_id
    raise ValueError(tr("tui.error.project_required"))


def _revision_of(runtime: Runtime, project_id: str) -> int:
    return runtime.project_service.load_project(project_id).active_revision


def _enrich_revision(payload: Any, runtime: Runtime, project_id: str) -> Any:
    if isinstance(payload, dict):
        enriched = payload.copy()
        enriched.setdefault("project_id", project_id)
        enriched["revision"] = _revision_of(runtime, project_id)
        return enriched
    return payload


def execute_command(
    command: str,
    params: dict[str, Any],
    runtime: Runtime,
    state: SessionState,
) -> Any:
    if command == "project-create":
        payload = project_create(runtime.project_service, title=_require_text(params, "title"))
        state.current_project_id = str(payload["id"])
        return payload
    if command == "project-list":
        return project_list(runtime.project_service)
    if command == "project-open":
        payload = project_open(
            runtime.project_service,
            project_id=_require_text(params, "project_id"),
        )
        state.current_project_id = str(payload["id"])
        return payload
    if command == "project-rename":
        project_id = _resolve_project_id(params, state)
        payload = project_rename(
            runtime.project_service,
            project_id=project_id,
            title=_require_text(params, "title"),
        )
        state.current_project_id = project_id
        return payload
    if command == "project-settings":
        project_id = _resolve_project_id(params, state)
        allow_cycles = _bool_from_text(params.get("allow_cycles"))
        auto_snapshot_minutes = params.get("auto_snapshot_minutes")
        auto_snapshot_operations = params.get("auto_snapshot_operations")
        system_prompt_style = params.get("system_prompt_style")
        system_prompt_forbidden = params.get("system_prompt_forbidden")
        system_prompt_notes = params.get("system_prompt_notes")
        if (
            allow_cycles is None
            and auto_snapshot_minutes is None
            and auto_snapshot_operations is None
            and system_prompt_style is None
            and system_prompt_forbidden is None
            and system_prompt_notes is None
        ):
            raise ValueError(tr("tui.error.project_settings_requires_one"))
        payload = project_update_settings(
            runtime.project_service,
            project_id=project_id,
            allow_cycles=allow_cycles,
            auto_snapshot_minutes=(
                int(auto_snapshot_minutes)
                if auto_snapshot_minutes is not None
                else None
            ),
            auto_snapshot_operations=(
                int(auto_snapshot_operations)
                if auto_snapshot_operations is not None
                else None
            ),
            system_prompt_style=(
                str(system_prompt_style)
                if system_prompt_style is not None
                else None
            ),
            system_prompt_forbidden=(
                str(system_prompt_forbidden)
                if system_prompt_forbidden is not None
                else None
            ),
            system_prompt_notes=(
                str(system_prompt_notes)
                if system_prompt_notes is not None
                else None
            ),
        )
        state.current_project_id = project_id
        return payload
    if command == "project-delete":
        project_id = _resolve_project_id(params, state)
        payload = project_delete(runtime.project_service, project_id=project_id)
        if state.current_project_id == project_id:
            state.current_project_id = None
        return payload
    if command == "node-add":
        project_id = _resolve_project_id(params, state)
        payload = node_add(
            runtime.graph_service,
            project_id=project_id,
            title=_require_text(params, "title"),
            node_type=str(params.get("type", "chapter")),
            status=str(params.get("status", "draft")),
            storyline_id=(
                str(params["storyline_id"])
                if params.get("storyline_id") is not None
                else None
            ),
            pos_x=float(params.get("pos_x", 0.0)),
            pos_y=float(params.get("pos_y", 0.0)),
            metadata=_parse_json_dict(params.get("metadata_json"), field="metadata_json"),
        )
        state.current_project_id = project_id
        return _enrich_revision(payload, runtime, project_id)
    if command == "node-update":
        project_id = _resolve_project_id(params, state)
        node_id = _require_text(params, "node_id")
        patch = _parse_json_dict(_require_text(params, "patch_json"), field="patch_json")
        payload = node_update(
            runtime.graph_service,
            project_id=project_id,
            node_id=node_id,
            patch=patch or {},
        )
        state.current_project_id = project_id
        return _enrich_revision(payload, runtime, project_id)
    if command == "node-move":
        project_id = _resolve_project_id(params, state)
        node_id = _require_text(params, "node_id")
        if params.get("pos_x") is None or params.get("pos_y") is None:
            raise ValueError(tr("tui.error.node_move_requires_pos"))
        payload = node_move(
            runtime.graph_service,
            project_id=project_id,
            node_id=node_id,
            pos_x=float(params["pos_x"]),
            pos_y=float(params["pos_y"]),
        )
        state.current_project_id = project_id
        return _enrich_revision(payload, runtime, project_id)
    if command == "node-delete":
        project_id = _resolve_project_id(params, state)
        payload = node_delete(
            runtime.graph_service,
            project_id=project_id,
            node_id=_require_text(params, "node_id"),
        )
        state.current_project_id = project_id
        return _enrich_revision(payload, runtime, project_id)
    if command == "node-list":
        project_id = _resolve_project_id(params, state)
        state.current_project_id = project_id
        return node_list(runtime.graph_service, project_id=project_id)
    if command == "edge-add":
        project_id = _resolve_project_id(params, state)
        payload = edge_add(
            runtime.graph_service,
            project_id=project_id,
            source_id=_require_text(params, "source_id"),
            target_id=_require_text(params, "target_id"),
            label=str(params.get("label", "")),
        )
        state.current_project_id = project_id
        return _enrich_revision(payload, runtime, project_id)
    if command == "edge-delete":
        project_id = _resolve_project_id(params, state)
        payload = edge_delete(
            runtime.graph_service,
            project_id=project_id,
            edge_id=_require_text(params, "edge_id"),
        )
        state.current_project_id = project_id
        return _enrich_revision(payload, runtime, project_id)
    if command == "edge-list":
        project_id = _resolve_project_id(params, state)
        state.current_project_id = project_id
        return edge_list(runtime.graph_service, project_id=project_id)
    if command == "graph-view":
        project_id = _resolve_project_id(params, state)
        state.current_project_id = project_id
        return graph_view(runtime.graph_service, project_id=project_id)
    if command == "validate":
        project_id = _resolve_project_id(params, state)
        state.current_project_id = project_id
        return validate_project(runtime.validation_service, project_id=project_id)
    if command == "export":
        project_id = _resolve_project_id(params, state)
        state.current_project_id = project_id
        return export_markdown(
            runtime.export_service,
            project_id=project_id,
            traversal=str(params.get("traversal", "mainline")),
            output_root=str(params.get("output_root", "exports")),
        )
    if command == "snapshot-create":
        project_id = _resolve_project_id(params, state)
        state.current_project_id = project_id
        payload = snapshot_create(runtime.snapshot_service, project_id=project_id)
        return _enrich_revision(payload, runtime, project_id)
    if command == "snapshot-list":
        project_id = _resolve_project_id(params, state)
        state.current_project_id = project_id
        return snapshot_list(runtime.snapshot_service, project_id=project_id)
    if command == "rollback":
        project_id = _resolve_project_id(params, state)
        revision_value = params.get("revision")
        if revision_value is None:
            raise ValueError(tr("tui.error.rollback_requires_revision"))
        payload = rollback_to_revision(
            runtime.snapshot_service,
            project_id=project_id,
            revision=int(revision_value),
        )
        state.current_project_id = project_id
        return payload
    if command == "generate-chapter":
        project_id = _resolve_project_id(params, state)
        payload = generate_chapter(
            runtime.ai_service,
            project_id=project_id,
            node_id=_require_text(params, "node_id"),
            token_budget=int(params.get("token_budget", 2200)),
            style_hint=str(params.get("style_hint", "")),
            workflow_mode=str(
                params.get("workflow_mode") or runtime.default_workflow_mode
            ),
        )
        state.current_project_id = project_id
        return payload
    if command == "generate-branches":
        project_id = _resolve_project_id(params, state)
        payload = generate_branches(
            runtime.ai_service,
            project_id=project_id,
            node_id=_require_text(params, "node_id"),
            n=int(params.get("n", 3)),
            token_budget=int(params.get("token_budget", 1800)),
        )
        state.current_project_id = project_id
        return payload
    if command == "review-lore":
        project_id = _resolve_project_id(params, state)
        payload = review_lore(
            runtime.ai_service,
            project_id=project_id,
            node_id=_require_text(params, "node_id"),
            token_budget=int(params.get("token_budget", 1500)),
        )
        state.current_project_id = project_id
        return payload
    if command == "review-logic":
        project_id = _resolve_project_id(params, state)
        payload = review_logic(
            runtime.ai_service,
            project_id=project_id,
            node_id=_require_text(params, "node_id"),
            token_budget=int(params.get("token_budget", 1500)),
        )
        state.current_project_id = project_id
        return payload
    if command == "task-get":
        return task_get(runtime.ai_service, task_id=_require_text(params, "task_id"))
    if command == "task-cancel":
        return task_cancel(runtime.ai_service, task_id=_require_text(params, "task_id"))
    if command == "task-list":
        project_id = _resolve_project_id(params, state)
        status = params.get("task_status")
        limit_value = params.get("limit")
        task_items = task_list(
            runtime.ai_service,
            project_id=project_id,
            status=str(status) if status is not None else None,
            limit=int(limit_value) if limit_value is not None else None,
        )
        state.current_project_id = project_id
        return task_items
    if command == "ai-status":
        return ai_status()
    if command == "settings":
        locale_value = params.get("locale")
        if locale_value is None:
            locale_value = params.get("lang")
        if locale_value is None:
            return _settings_payload()
        locale_text = str(locale_value).strip()
        if not locale_text:
            raise ValueError(tr("tui.error.arg_empty", name="locale"))
        os.environ["ELYHA_LOCALE"] = _parse_locale(locale_text)
        return _settings_payload()
    raise ValueError(tr("tui.error.unknown_command", command=command))


def _print_command_help() -> None:
    console.print(f"[dim]{tr('tui.help.replaced_by_menu')}[/dim]")
    _print_numeric_menu()


def _parse_interactive_params(tokens: list[str]) -> tuple[str, dict[str, Any]]:
    if not tokens:
        raise ValueError(tr("tui.error.empty_input"))
    command = tokens[0]
    params: dict[str, Any] = {}
    for token in tokens[1:]:
        if "=" not in token:
            raise ValueError(tr("tui.error.args_key_value"))
        key, value = token.split("=", 1)
        params[key.replace("-", "_")] = value
    return command, params


def _normalize_output_payload(payload: Any) -> Any:
    if not isinstance(payload, str):
        return payload
    text = payload.strip()
    if len(text) < 2:
        return payload
    if not ((text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))):
        return payload
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return payload


def _print_payload(payload: Any, *, state: SessionState) -> None:
    normalized = _normalize_output_payload(payload)
    if isinstance(normalized, (dict, list)):
        console.print_json(data=normalized, ensure_ascii=False, indent=2)
    else:
        console.print(normalized)
    if state.current_project_id is not None:
        console.print(
            f"[dim]{tr('tui.label.current_project_id')}={state.current_project_id}[/dim]"
        )


def _task_status_cell(status: TaskStatus) -> str:
    if status == TaskStatus.SUCCESS:
        return f"[green]{tr('tui.status.success')}[/green]"
    if status == TaskStatus.FAILED:
        return f"[red]{tr('tui.status.failed')}[/red]"
    if status == TaskStatus.RUNNING:
        return f"[yellow]{tr('tui.status.running')}[/yellow]"
    if status == TaskStatus.CANCELLED:
        return f"[magenta]{tr('tui.status.cancelled')}[/magenta]"
    return status.value


def _arrow_lines_from_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    limit: int = 14,
) -> list[str]:
    if not edges:
        return [tr("graph.arrow.empty")]
    title_by_id = {str(node["id"]): str(node["title"]) for node in nodes}
    lines: list[str] = []
    for edge in edges[:limit]:
        source_id = str(edge["source_id"])
        target_id = str(edge["target_id"])
        source_title = title_by_id.get(source_id, source_id)
        target_title = title_by_id.get(target_id, target_id)
        label = str(edge.get("label", "")).strip()
        order_raw = edge.get("narrative_order")
        order_text = ""
        if isinstance(order_raw, int) and order_raw > 0:
            order_text = str(order_raw)
        if order_text and label:
            label = f"{order_text} | {label}"
        elif order_text:
            label = order_text
        if label:
            lines.append(
                tr(
                    "graph.arrow.line_with_label",
                    source=source_title,
                    target=target_title,
                    label=label,
                )
            )
        else:
            lines.append(
                tr(
                    "graph.arrow.line",
                    source=source_title,
                    target=target_title,
                )
            )
    if len(edges) > limit:
        lines.append(tr("graph.arrow.more", count=len(edges) - limit))
    return lines


def _render_dashboard(
    runtime: Runtime,
    state: SessionState,
    *,
    db_path: str,
) -> None:
    project = (
        runtime.repository.get_project(state.current_project_id)
        if state.current_project_id
        else None
    )

    project_table = Table(title=tr("tui.dashboard.project_title"), expand=True)
    project_table.add_column(tr("tui.col.field"))
    project_table.add_column(tr("tui.col.value"))
    if project is None:
        project_table.add_row(tr("tui.field.current"), "-")
        project_table.add_row(tr("tui.field.db"), db_path)
        project_table.add_row(tr("tui.field.locale"), current_locale())
    else:
        project_table.add_row(tr("tui.field.id"), project.id)
        project_table.add_row(tr("tui.field.title"), project.title)
        project_table.add_row(tr("tui.field.revision"), str(project.active_revision))
        project_table.add_row(
            tr("tui.field.allow_cycles"),
            str(project.settings.allow_cycles).lower(),
        )
        project_table.add_row(tr("tui.field.db"), db_path)
        project_table.add_row(tr("tui.field.locale"), current_locale())
        if state.last_command:
            project_table.add_row(tr("tui.field.last_cmd"), state.last_command)

    nodes_table = Table(title=tr("tui.dashboard.nodes_title"), expand=True)
    nodes_table.add_column(tr("tui.col.id"))
    nodes_table.add_column(tr("tui.col.title"))
    nodes_table.add_column(tr("tui.col.type"))
    nodes_table.add_column(tr("tui.col.status"))
    if project is None:
        nodes_table.add_row("-", "-", "-", "-")
    else:
        nodes = runtime.repository.list_nodes(project.id)[:8]
        if not nodes:
            nodes_table.add_row("-", "-", "-", "-")
        for node in nodes:
            nodes_table.add_row(node.id, node.title, node.type.value, node.status.value)

    tasks_table = Table(title=tr("tui.dashboard.tasks_title"), expand=True)
    tasks_table.add_column(tr("tui.col.id"))
    tasks_table.add_column(tr("tui.col.type"))
    tasks_table.add_column(tr("tui.col.status"))
    tasks_table.add_column(tr("tui.col.rev"))
    if project is None:
        tasks_table.add_row("-", "-", "-", "-")
    else:
        tasks = runtime.repository.list_tasks(project.id, limit=8)
        if not tasks:
            tasks_table.add_row("-", "-", "-", "-")
        for task in tasks:
            tasks_table.add_row(
                task.id,
                task.task_type,
                _task_status_cell(task.status),
                str(task.revision),
            )

    ops_table = Table(title=tr("tui.dashboard.operations_title"), expand=True)
    ops_table.add_column(tr("tui.col.rev"))
    ops_table.add_column(tr("tui.col.op_type"))
    if project is None:
        ops_table.add_row("-", "-")
    else:
        operations = runtime.repository.list_operations(project.id, limit=8)
        if not operations:
            ops_table.add_row("-", "-")
        for operation in operations:
            ops_table.add_row(str(operation.revision), operation.op_type)

    console.print(
        Columns(
            [
                Panel(project_table, border_style="cyan"),
                Panel(nodes_table, border_style="green"),
            ],
            equal=True,
            expand=True,
        )
    )
    console.print(
        Columns(
            [
                Panel(tasks_table, border_style="yellow"),
                Panel(ops_table, border_style="magenta"),
            ],
            equal=True,
            expand=True,
        )
    )

    arrow_lines = [tr("graph.arrow.empty")]
    if project is not None:
        graph_payload = graph_view(runtime.graph_service, project_id=project.id)
        graph_nodes = cast(list[dict[str, Any]], graph_payload["nodes"])
        graph_edges = cast(list[dict[str, Any]], graph_payload["edges"])
        arrow_lines = _arrow_lines_from_graph(graph_nodes, graph_edges, limit=12)
    console.print(
        Panel(
            "\n".join(arrow_lines),
            title=tr("graph.arrow.title"),
            border_style="blue",
            expand=True,
        )
    )


def _print_graph_editor_help() -> None:
    table = Table(title=tr("graph.help.title"))
    table.add_column(tr("tui.col.command"))
    table.add_column(tr("tui.col.example"))
    table.add_column(tr("tui.col.description"))
    table.add_row(
        "add-node",
        tr("graph.help.example.add_node"),
        tr("graph.help.desc.add_node"),
    )
    table.add_row(
        "rename-node",
        tr("graph.help.example.rename_node"),
        tr("graph.help.desc.rename_node"),
    )
    table.add_row(
        "move-node",
        tr("graph.help.example.move_node"),
        tr("graph.help.desc.move_node"),
    )
    table.add_row(
        "delete-node",
        tr("graph.help.example.delete_node"),
        tr("graph.help.desc.delete_node"),
    )
    table.add_row(
        "add-edge",
        tr("graph.help.example.add_edge"),
        tr("graph.help.desc.add_edge"),
    )
    table.add_row(
        "delete-edge",
        tr("graph.help.example.delete_edge"),
        tr("graph.help.desc.delete_edge"),
    )
    table.add_row(
        "validate",
        tr("graph.help.example.validate"),
        tr("graph.help.desc.validate"),
    )
    table.add_row(
        "help",
        tr("graph.help.example.help"),
        tr("graph.help.desc.help"),
    )
    table.add_row(
        "list",
        tr("graph.help.example.list"),
        tr("graph.help.desc.list"),
    )
    table.add_row(
        "back",
        tr("graph.help.example.back"),
        tr("graph.help.desc.back"),
    )
    console.print(table)
    console.print(f"[dim]{tr('graph.help.tips')}[/dim]")


def _render_graph_editor(runtime: Runtime, *, project_id: str, db_path: str) -> None:
    project = runtime.project_service.load_project(project_id)
    payload = graph_view(runtime.graph_service, project_id=project_id)
    nodes = cast(list[dict[str, Any]], payload["nodes"])
    edges = cast(list[dict[str, Any]], payload["edges"])

    summary = Table(title=tr("graph.summary.title"), expand=True)
    summary.add_column(tr("tui.col.field"))
    summary.add_column(tr("tui.col.value"))
    summary.add_row(tr("tui.field.project_id"), project_id)
    summary.add_row(tr("tui.field.title"), project.title)
    summary.add_row(tr("tui.field.revision"), str(project.active_revision))
    summary.add_row(tr("graph.field.node_count"), str(payload["node_count"]))
    summary.add_row(tr("graph.field.edge_count"), str(payload["edge_count"]))
    summary.add_row(tr("tui.field.db"), db_path)

    nodes_table = Table(title=tr("graph.nodes.title"), expand=True)
    nodes_table.add_column(tr("tui.col.id"))
    nodes_table.add_column(tr("tui.col.title"))
    nodes_table.add_column(tr("tui.col.type"))
    nodes_table.add_column(tr("tui.col.status"))
    nodes_table.add_column(tr("graph.col.pos"))
    nodes_table.add_column(tr("graph.col.deg"))
    if not nodes:
        nodes_table.add_row("-", "-", "-", "-", "-", "-")
    for node in nodes[:18]:
        pos = f"({node['pos_x']:.1f},{node['pos_y']:.1f})"
        deg = tr(
            "graph.value.degree",
            inbound=node["inbound"],
            outbound=node["outbound"],
        )
        nodes_table.add_row(
            str(node["id"]),
            str(node["title"]),
            str(node["type"]),
            str(node["status"]),
            pos,
            deg,
        )

    edges_table = Table(title=tr("graph.edges.title"), expand=True)
    edges_table.add_column(tr("tui.col.id"))
    edges_table.add_column(tr("graph.col.source_target"))
    edges_table.add_column(tr("graph.col.narrative_order"))
    edges_table.add_column(tr("graph.col.label"))
    if not edges:
        edges_table.add_row("-", "-", "-", "-")
    for edge in edges[:18]:
        order_raw = edge.get("narrative_order")
        order_text = str(order_raw) if isinstance(order_raw, int) and order_raw > 0 else "-"
        edges_table.add_row(
            str(edge["id"]),
            f"{edge['source_id']} -> {edge['target_id']}",
            order_text,
            str(edge["label"]),
        )

    arrow_panel = Panel(
        "\n".join(_arrow_lines_from_graph(nodes, edges, limit=18)),
        title=tr("graph.arrow.title"),
        border_style="blue",
        expand=True,
    )

    console.print(
        Columns(
            [
                Panel(summary, border_style="cyan"),
                Panel(nodes_table, border_style="green"),
            ],
            equal=True,
            expand=True,
        )
    )
    console.print(
        Columns(
            [
                Panel(edges_table, border_style="magenta"),
                arrow_panel,
            ],
            equal=True,
            expand=True,
        )
    )


def _dispatch_graph_editor_command(
    command: str,
    params: dict[str, Any],
    runtime: Runtime,
    state: SessionState,
    *,
    project_id: str,
) -> Any:
    normalized = _normalize_graph_command(command)
    scoped = params.copy()
    scoped["project_id"] = project_id
    if "x" in scoped and "pos_x" not in scoped:
        scoped["pos_x"] = scoped.pop("x")
    if "y" in scoped and "pos_y" not in scoped:
        scoped["pos_y"] = scoped.pop("y")

    if normalized in {"list", "ls", "refresh"}:
        return execute_command("graph-view", scoped, runtime, state)
    if normalized in {"add-node", "node-add"}:
        return execute_command("node-add", scoped, runtime, state)
    if normalized in {"rename-node"}:
        node_id = _require_text(scoped, "node_id")
        title = _require_text(scoped, "title")
        return execute_command(
            "node-update",
            {
                "project_id": project_id,
                "node_id": node_id,
                "patch_json": json.dumps({"title": title}, ensure_ascii=False),
            },
            runtime,
            state,
        )
    if normalized in {"move-node", "move", "node-move"}:
        return execute_command("node-move", scoped, runtime, state)
    if normalized in {"delete-node", "node-delete"}:
        return execute_command("node-delete", scoped, runtime, state)
    if normalized in {"add-edge", "edge-add"}:
        return execute_command("edge-add", scoped, runtime, state)
    if normalized in {"delete-edge", "edge-delete"}:
        return execute_command("edge-delete", scoped, runtime, state)
    if normalized in {"validate"}:
        return execute_command("validate", scoped, runtime, state)
    raise ValueError(tr("graph.editor.unsupported_cmd"))


def _run_graph_editor(
    runtime: Runtime,
    state: SessionState,
    *,
    project_id: str,
    db_path: str,
) -> None:
    graph_wizard_commands = {
        "add-node",
        "rename-node",
        "move-node",
        "delete-node",
        "add-edge",
        "delete-edge",
    }
    state.current_project_id = project_id
    while True:
        console.clear()
        console.print(
            Panel.fit(
                tr("graph.editor.banner"),
                title=tr("graph.editor.title"),
                border_style="green",
            )
        )
        _render_graph_editor(runtime, project_id=project_id, db_path=db_path)
        _print_graph_numeric_menu()
        try:
            line = console.input(tr("graph.prompt.input")).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not line:
            continue
        if line == "0":
            break
        tokens = shlex.split(line)
        if not tokens:
            continue
        if tokens[0].isdigit() and tokens[0] in GRAPH_MENU_INDEX:
            command = GRAPH_MENU_INDEX[tokens[0]]
            if command in {"help", "menu"}:
                _print_graph_editor_help()
                _ = console.input(f"[dim]{tr('tui.prompt.press_enter')}[/dim] ")
                continue
            if command in {"list", "validate"}:
                params = {}
            else:
                prompted = _prompt_for_graph_params(command)
                if prompted is None:
                    continue
                params = prompted
        else:
            command = _normalize_graph_command(tokens[0])
            if command in {"back", "exit", "quit"}:
                break
            if command in {"help", "menu"}:
                _print_graph_editor_help()
                _ = console.input(f"[dim]{tr('tui.prompt.press_enter')}[/dim] ")
                continue
            if len(tokens) == 1 and command in graph_wizard_commands:
                prompted = _prompt_for_graph_params(command)
                if prompted is None:
                    continue
                params = prompted
            else:
                _, params = _parse_interactive_params([command, *tokens[1:]])
        try:
            payload = _dispatch_graph_editor_command(
                command,
                params,
                runtime,
                state,
                project_id=project_id,
            )
            state.last_command = f"graph-edit:{command}"
            console.print(
                Panel.fit(
                    tr("graph.editor.command_success", command=command),
                    title=tr("graph.editor.success_title"),
                    border_style="green",
                )
            )
            _print_payload(payload, state=state)
            _ = console.input(f"[dim]{tr('tui.prompt.press_enter')}[/dim] ")
        except Exception as exc:
            console.print(
                Panel.fit(
                    tr("graph.editor.command_failed", error=str(exc)),
                    title=tr("graph.editor.error_title"),
                    border_style="red",
                )
            )
            _ = console.input(f"[dim]{tr('tui.prompt.press_enter')}[/dim] ")


def run_tui(runtime: Runtime, *, db_path: str) -> int:
    state = SessionState()
    console.clear()
    console.print(
        Panel.fit(
            tr("tui.banner.mode_dashboard"),
            title=tr("tui.banner.title"),
            border_style="cyan",
        )
    )
    _render_dashboard(runtime, state, db_path=db_path)
    _print_numeric_menu()
    while True:
        try:
            line = console.input(tr("tui.prompt.input")).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not line:
            continue
        if line == "0":
            break
        try:
            command: str
            params: dict[str, Any]
            if line.isdigit() and line in MENU_INDEX:
                command = MENU_INDEX[line]
                prompted = _prompt_for_params(command, state, runtime)
                if prompted is None:
                    continue
                params = prompted
            else:
                tokens = shlex.split(line)
                if not tokens:
                    continue
                command = _normalize_main_command(tokens[0])
                if command in {"exit", "quit"}:
                    break
                if command == "help":
                    _print_command_help()
                    continue
                if command == "menu":
                    _print_numeric_menu()
                    continue
                _, params = _parse_interactive_params([command, *tokens[1:]])
            if command == "graph-edit":
                project_id = _resolve_project_id(params, state)
                _run_graph_editor(
                    runtime,
                    state,
                    project_id=project_id,
                    db_path=db_path,
                )
                console.clear()
                console.print(
                    Panel.fit(
                        tr("tui.banner.return_from_graph_editor"),
                        title=tr("tui.banner.title"),
                        border_style="cyan",
                    )
                )
                _render_dashboard(runtime, state, db_path=db_path)
                _print_numeric_menu()
                continue
            payload = execute_command(command, params, runtime, state)
            state.last_command = command
            console.clear()
            console.print(
                Panel.fit(
                    tr("tui.banner.command_success", command=command),
                    title=tr("tui.banner.title"),
                    border_style="green",
                )
            )
            _render_dashboard(runtime, state, db_path=db_path)
            _print_payload(payload, state=state)
            _print_numeric_menu()
        except Exception as exc:
            console.clear()
            console.print(
                Panel.fit(
                    tr("tui.banner.command_failed", error=str(exc)),
                    title=tr("tui.banner.error_title"),
                    border_style="red",
                )
            )
            _render_dashboard(runtime, state, db_path=db_path)
            console.print(f"[red]{tr('tui.error.prefix')}:[/red] {exc}")
            _print_numeric_menu()
    return 0


def run_automation(args: argparse.Namespace, runtime: Runtime) -> int:
    state = SessionState(current_project_id=args.project_id)
    params = {
        "project_id": args.project_id,
        "title": args.title,
        "node_id": args.node_id,
        "edge_id": args.edge_id,
        "task_id": args.task_id,
        "task_status": args.task_status,
        "limit": args.limit,
        "source_id": args.source_id,
        "target_id": args.target_id,
        "type": args.type,
        "status": args.status,
        "n": args.n,
        "token_budget": args.token_budget,
        "style_hint": args.style_hint,
        "workflow_mode": args.workflow_mode or runtime.default_workflow_mode,
        "locale": args.locale,
        "storyline_id": args.storyline_id,
        "pos_x": args.pos_x,
        "pos_y": args.pos_y,
        "label": args.label,
        "metadata_json": args.metadata_json,
        "patch_json": args.patch_json,
        "traversal": args.traversal,
        "output_root": args.output_root,
        "revision": args.revision,
        "allow_cycles": args.allow_cycles,
        "auto_snapshot_minutes": args.auto_snapshot_minutes,
        "auto_snapshot_operations": args.auto_snapshot_operations,
        "system_prompt_style": args.system_prompt_style,
        "system_prompt_forbidden": args.system_prompt_forbidden,
        "system_prompt_notes": args.system_prompt_notes,
    }
    try:
        payload = _normalize_output_payload(
            execute_command(str(args.automation), params, runtime, state)
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "command": args.automation,
                    "message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke:
        return run_smoke()
    runtime = _build_runtime(args.db)
    if args.automation:
        return run_automation(args, runtime)
    return run_tui(runtime, db_path=args.db)


if __name__ == "__main__":
    raise SystemExit(main())
