"""Tool registry and execution for AI tool loop and graph mutations."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from elyha_core.models.node import NodeStatus, NodeType
from elyha_core.services.graph_service import GraphService, NodeCreate
from elyha_core.services.readable_content_tool_service import ReadableContentToolService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now

_DOC_TYPE_ALIASES = {
    "constitution_markdown": "constitution",
    "clarify_markdown": "clarify",
    "specification_markdown": "specification",
    "plan_markdown": "plan",
}

_GUIDE_DOC_ALIASES = {
    "constitution": "constitution_markdown",
    "constitution_markdown": "constitution_markdown",
    "clarify": "clarify_markdown",
    "clarify_markdown": "clarify_markdown",
    "specification": "specification_markdown",
    "specification_markdown": "specification_markdown",
    "plan": "plan_markdown",
    "plan_markdown": "plan_markdown",
}

_NODE_TYPE_VALUES = {"chapter", "group", "branch", "merge", "parallel", "checkpoint"}
_NODE_STATUS_VALUES = {"draft", "generated", "reviewed", "approved"}


class ToolService:
    """Centralized tool schema and execution service."""

    def __init__(
        self,
        *,
        repository: SQLiteRepository,
        graph_service: GraphService,
        readable_tool_service: ReadableContentToolService,
        setting_proposal_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.readable_tool_service = readable_tool_service
        self.setting_proposal_service = setting_proposal_service

    def set_setting_proposal_service(self, service: Any | None) -> None:
        self.setting_proposal_service = service

    def build_native_tool_specs(
        self,
        *,
        write_proposal_enabled: bool,
        write_document_enabled: bool,
        allow_skip_document: bool,
        node_tools_enabled: bool = False,
    ) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = [
            {
                "name": "search_text",
                "description": "Search relevant text chunks by query.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Keyword query to search."},
                        "top_k": {"type": "integer", "description": "Max chunks to return."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "read_chunk",
                "description": "Read one chunk by chunk_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string", "description": "Target chunk id."},
                    },
                    "required": ["chunk_id"],
                },
            },
            {
                "name": "read_neighbors",
                "description": "Read nearby chunks around a chunk_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string", "description": "Center chunk id."},
                        "before": {"type": "integer", "description": "How many chunks before center."},
                        "after": {"type": "integer", "description": "How many chunks after center."},
                    },
                    "required": ["chunk_id"],
                },
            },
            {
                "name": "get_chapter_outline",
                "description": "Get outline markdown for current chapter node.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string", "description": "Chapter node id."},
                    },
                    "required": [],
                },
            },
            {
                "name": "get_world_state",
                "description": "Get project world-state snapshot for entities and variables.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "object",
                            "properties": {
                                "character_ids": {"type": "array", "items": {"type": "string"}},
                                "item_ids": {"type": "array", "items": {"type": "string"}},
                                "world_variable_keys": {"type": "array", "items": {"type": "string"}},
                            },
                        }
                    },
                    "required": [],
                },
            },
            {
                "name": "get_effective_directives",
                "description": "Read effective writing directives and constraints.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string"},
                    },
                    "required": [],
                },
            },
            {
                "name": "prose_rewrite",
                "description": "Rewrite prose according to specific styles or constraints.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "rewrite_mode": {
                            "type": "string",
                            "description": "One of: sensory, pov, iceberg, show_dont_tell, cinematic, spatial, style",
                        },
                        "target_text": {"type": "string"},
                        "instructions": {"type": "string"},
                    },
                    "required": ["rewrite_mode", "target_text", "instructions"],
                },
            },
            {
                "name": "story_analysis_report",
                "description": "Analyze narrative structures, pacing, or reader reactions.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "analysis_type": {
                            "type": "string",
                            "description": "One of: framework, pacing, reader_reaction, editorial",
                        },
                        "scope_node_ids": {"type": "array", "items": {"type": "string"}},
                        "focus_question": {"type": "string"},
                    },
                    "required": ["analysis_type"],
                },
            },
            {
                "name": "foreshadowing_engine",
                "description": "Register, track, or trigger payoff for foreshadowing elements.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "One of: register, propose_payoff, inject_motif, extract_sensory",
                        },
                        "element_id": {"type": "string"},
                        "description": {"type": "string"},
                        "target_node_id": {"type": "string"},
                    },
                    "required": ["action"],
                },
            },
        ]
        if node_tools_enabled:
            tools.extend(
                [
                    {
                        "name": "list_nodes",
                        "description": "List nodes in current project.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "limit": {"type": "integer"},
                                "include_metadata": {"type": "boolean"},
                            },
                            "required": [],
                        },
                    },
                    {
                        "name": "get_node",
                        "description": "Get one node by id.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "node_id": {"type": "string"},
                            },
                            "required": ["node_id"],
                        },
                    },
                    {
                        "name": "create_node",
                        "description": "Create a new node and optionally link from an existing node.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "type": {"type": "string"},
                                "status": {"type": "string"},
                                "storyline_id": {"type": "string"},
                                "pos_x": {"type": "number"},
                                "pos_y": {"type": "number"},
                                "metadata": {"type": "object"},
                                "link_from_node_id": {"type": "string"},
                                "edge_label": {"type": "string"},
                            },
                            "required": ["title"],
                        },
                    },
                    {
                        "name": "split_node",
                        "description": "Split a node atomically into two pieces by modifying the original and creating a new linked target.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "source_node_id": {"type": "string"},
                                "source_patch": {
                                    "type": "object", 
                                    "description": "Fields to modify on source_node_id"
                                },
                                "new_node_title": {"type": "string"},
                                "new_node_type": {"type": "string", "description": "Default is branch"},
                                "new_node_status": {"type": "string"},
                                "new_node_metadata": {"type": "object"},
                                "edge_label": {"type": "string", "description": "Label for edge between source and new node"},
                            },
                            "required": ["source_node_id", "source_patch", "new_node_title"],
                        },
                    },
                    {
                        "name": "update_node",
                        "description": "Update one node by patch.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "node_id": {"type": "string"},
                                "patch": {"type": "object"},
                            },
                            "required": ["node_id"],
                        },
                    },
                    {
                        "name": "create_edge",
                        "description": "Create one directed edge between source and target node.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "source_id": {"type": "string"},
                                "target_id": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["source_id", "target_id"],
                        },
                    },
                    {
                        "name": "delete_node",
                        "description": "Delete one node. Requires confirm=true for execution.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "node_id": {"type": "string"},
                                "confirm": {"type": "boolean"},
                            },
                            "required": ["node_id"],
                        },
                    },
                ]
            )
        if write_proposal_enabled:
            tools.append(
                {
                    "name": "propose_setting_change",
                    "description": "Create a setting-change proposal for user review.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "target_scope": {"type": "string", "description": "project or global"},
                            "proposal_type": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "reason": {"type": "string"},
                            "node_id": {"type": "string"},
                        },
                        "required": ["proposal_type", "title", "content"],
                    },
                }
            )
        if write_document_enabled:
            tools.append(
                {
                    "name": "write_document",
                    "description": "Write one workflow document.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "document_type": {
                                "type": "string",
                                "enum": ["constitution", "clarify", "specification", "plan"],
                            },
                            "content": {"type": "string"},
                        },
                        "required": ["document_type", "content"],
                    },
                }
            )
        if allow_skip_document:
            tools.append(
                {
                    "name": "skip_document",
                    "description": "Request skipping one workflow document with user confirmation.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "document_type": {
                                "type": "string",
                                "enum": ["constitution", "clarify", "specification", "plan"],
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["document_type"],
                    },
                }
            )
        return tools

    def normalize_tool_call_arguments(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        tool_context_node_id: str,
    ) -> tuple[dict[str, Any], str]:
        normalized = str(tool_name or "").strip().lower()
        raw = arguments if isinstance(arguments, dict) else {}

        def _clean_text(value: Any, *, limit: int = 4000) -> str:
            text = str(value or "").strip()
            if len(text) > limit:
                return text[:limit]
            return text

        def _as_int(value: Any, fallback: int, *, lower: int, upper: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                parsed = fallback
            if parsed < lower:
                return lower
            if parsed > upper:
                return upper
            return parsed

        def _as_float(value: Any, fallback: float) -> float:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                parsed = fallback
            if parsed != parsed:
                return fallback
            return parsed

        def _as_bool(value: Any, fallback: bool = False) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                text = value.strip().lower()
                if text in {"1", "true", "yes", "on", "y"}:
                    return True
                if text in {"0", "false", "no", "off", "n"}:
                    return False
            return fallback

        if normalized == "search_text":
            query = _clean_text(raw.get("query") or raw.get("q"), limit=300)
            if not query:
                return {}, "query is required"
            top_k = _as_int(raw.get("top_k", 5), 5, lower=1, upper=20)
            scope_raw = raw.get("scope")
            scope: dict[str, Any] = {}
            if isinstance(scope_raw, dict):
                node_id = _clean_text(scope_raw.get("node_id"), limit=128)
                if node_id:
                    scope["node_id"] = node_id
                node_ids = scope_raw.get("node_ids")
                if isinstance(node_ids, list):
                    normalized_ids = [
                        _clean_text(item, limit=128)
                        for item in node_ids
                        if _clean_text(item, limit=128)
                    ]
                    if normalized_ids:
                        scope["node_ids"] = normalized_ids[:30]
            return {"query": query, "top_k": top_k, "scope": scope}, ""
        if normalized == "read_chunk":
            chunk_id = _clean_text(raw.get("chunk_id"), limit=160)
            if not chunk_id:
                return {}, "chunk_id is required"
            return {"chunk_id": chunk_id}, ""
        if normalized == "read_neighbors":
            chunk_id = _clean_text(raw.get("chunk_id"), limit=160)
            if not chunk_id:
                return {}, "chunk_id is required"
            before = _as_int(raw.get("before", 1), 1, lower=0, upper=10)
            after = _as_int(raw.get("after", 1), 1, lower=0, upper=10)
            return {"chunk_id": chunk_id, "before": before, "after": after}, ""
        if normalized == "get_chapter_outline":
            node_id = _clean_text(raw.get("node_id") or tool_context_node_id, limit=128)
            if not node_id:
                return {}, "node_id is required"
            return {"node_id": node_id}, ""
        if normalized == "get_world_state":
            keys = raw.get("keys")
            if keys is None:
                keys = raw
            if not isinstance(keys, dict):
                keys = {}
            normalized_keys: dict[str, Any] = {}
            for key in ("character_ids", "item_ids", "world_variable_keys"):
                value = keys.get(key)
                if not isinstance(value, list):
                    continue
                cleaned = [_clean_text(item, limit=128) for item in value]
                cleaned = [item for item in cleaned if item]
                if cleaned:
                    normalized_keys[key] = cleaned[:30]
            rel_pairs = keys.get("relationship_pairs")
            if isinstance(rel_pairs, list):
                normalized_pairs: list[dict[str, str]] = []
                for item in rel_pairs:
                    if isinstance(item, dict):
                        left = _clean_text(item.get("subject") or item.get("a"), limit=128)
                        right = _clean_text(item.get("object") or item.get("b"), limit=128)
                        if left and right:
                            normalized_pairs.append({"subject": left, "object": right})
                    elif isinstance(item, (list, tuple)) and len(item) >= 2:
                        left = _clean_text(item[0], limit=128)
                        right = _clean_text(item[1], limit=128)
                        if left and right:
                            normalized_pairs.append({"subject": left, "object": right})
                if normalized_pairs:
                    normalized_keys["relationship_pairs"] = normalized_pairs[:30]
            return {"keys": normalized_keys}, ""
        if normalized == "get_effective_directives":
            target_project_id = _clean_text(raw.get("project_id"), limit=128)
            return {"project_id": target_project_id}, ""
        if normalized == "list_nodes":
            limit = _as_int(raw.get("limit", 30), 30, lower=1, upper=200)
            include_metadata = _as_bool(raw.get("include_metadata"), False)
            return {"limit": limit, "include_metadata": include_metadata}, ""
        if normalized == "get_node":
            node_id = _clean_text(
                raw.get("node_id")
                or raw.get("id")
                or tool_context_node_id,
                limit=128,
            )
            if not node_id:
                return {}, "node_id is required"
            return {"node_id": node_id}, ""
        if normalized == "create_node":
            title = _clean_text(raw.get("title"), limit=200)
            if not title:
                return {}, "title is required"
            node_type = _clean_text(
                raw.get("type") or raw.get("node_type") or "chapter",
                limit=32,
            ).lower()
            if node_type not in _NODE_TYPE_VALUES:
                return {}, "type is invalid"
            status = _clean_text(raw.get("status") or "draft", limit=32).lower()
            if status not in _NODE_STATUS_VALUES:
                return {}, "status is invalid"
            storyline_id = raw.get("storyline_id")
            normalized_storyline = _clean_text(storyline_id, limit=128) if storyline_id is not None else ""
            metadata = raw.get("metadata")
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict):
                return {}, "metadata must be object"
            link_from_node_id = _clean_text(
                raw.get("link_from_node_id")
                or raw.get("source_id"),
                limit=128,
            )
            edge_label = _clean_text(
                raw.get("edge_label") or raw.get("label"),
                limit=120,
            )
            return {
                "title": title,
                "type": node_type,
                "status": status,
                "storyline_id": normalized_storyline,
                "pos_x": _as_float(raw.get("pos_x"), 0.0),
                "pos_y": _as_float(raw.get("pos_y"), 0.0),
                "metadata": dict(metadata),
                "link_from_node_id": link_from_node_id,
                "edge_label": edge_label,
            }, ""
        if normalized == "update_node":
            node_id = _clean_text(
                raw.get("node_id")
                or raw.get("id")
                or tool_context_node_id,
                limit=128,
            )
            if not node_id:
                return {}, "node_id is required"
            patch_source = raw.get("patch")
            if isinstance(patch_source, dict):
                patch_raw = dict(patch_source)
            else:
                patch_raw = dict(raw)
            if "node_id" in patch_raw:
                patch_raw.pop("node_id")
            if "id" in patch_raw:
                patch_raw.pop("id")
            patch: dict[str, Any] = {}
            if "title" in patch_raw:
                title = _clean_text(patch_raw.get("title"), limit=200)
                if not title:
                    return {}, "title cannot be empty"
                patch["title"] = title
            if "type" in patch_raw:
                node_type = _clean_text(patch_raw.get("type"), limit=32).lower()
                if node_type not in _NODE_TYPE_VALUES:
                    return {}, "type is invalid"
                patch["type"] = node_type
            if "status" in patch_raw:
                status = _clean_text(patch_raw.get("status"), limit=32).lower()
                if status not in _NODE_STATUS_VALUES:
                    return {}, "status is invalid"
                patch["status"] = status
            if "storyline_id" in patch_raw:
                storyline_id = patch_raw.get("storyline_id")
                if storyline_id is None:
                    patch["storyline_id"] = None
                else:
                    patch["storyline_id"] = _clean_text(storyline_id, limit=128) or None
            if "pos_x" in patch_raw:
                patch["pos_x"] = _as_float(patch_raw.get("pos_x"), 0.0)
            if "pos_y" in patch_raw:
                patch["pos_y"] = _as_float(patch_raw.get("pos_y"), 0.0)
            if "metadata" in patch_raw:
                metadata = patch_raw.get("metadata")
                if not isinstance(metadata, dict):
                    return {}, "metadata must be object"
                patch["metadata"] = dict(metadata)
            if not patch:
                return {}, "patch cannot be empty"
            return {"node_id": node_id, "patch": patch}, ""
        if normalized == "create_edge":
            source_id = _clean_text(
                raw.get("source_id")
                or raw.get("source")
                or tool_context_node_id,
                limit=128,
            )
            target_id = _clean_text(raw.get("target_id") or raw.get("target"), limit=128)
            if not source_id or not target_id:
                return {}, "source_id and target_id are required"
            label = _clean_text(raw.get("label"), limit=120)
            return {"source_id": source_id, "target_id": target_id, "label": label}, ""
        if normalized == "split_node":
            source_node_id = _clean_text(raw.get("source_node_id") or tool_context_node_id, limit=128)
            if not source_node_id:
                return {}, "source_node_id is required"
            source_patch_raw = raw.get("source_patch", {})
            if not isinstance(source_patch_raw, dict):
                return {}, "source_patch must be object"
            source_patch: dict[str, Any] = {}
            if "title" in source_patch_raw:
                source_patch["title"] = _clean_text(source_patch_raw.get("title"), limit=200)
            if "status" in source_patch_raw:
                source_patch["status"] = _clean_text(source_patch_raw.get("status"), limit=32).lower()
            if "metadata" in source_patch_raw and isinstance(source_patch_raw["metadata"], dict):
                source_patch["metadata"] = dict(source_patch_raw["metadata"])
            
            new_node_title = _clean_text(raw.get("new_node_title"), limit=200)
            if not new_node_title:
                return {}, "new_node_title is required"
            
            new_node_type = _clean_text(raw.get("new_node_type", "branch"), limit=32).lower()
            if new_node_type not in _NODE_TYPE_VALUES:
                new_node_type = "branch"
            
            new_node_status = _clean_text(raw.get("new_node_status", "draft"), limit=32).lower()
            if new_node_status not in _NODE_STATUS_VALUES:
                new_node_status = "draft"
                
            new_metadata = raw.get("new_node_metadata", {})
            if not isinstance(new_metadata, dict):
                new_metadata = {}
                
            edge_label = _clean_text(raw.get("edge_label", ""), limit=120)
            
            return {
                "source_node_id": source_node_id,
                "source_patch": source_patch,
                "new_node_title": new_node_title,
                "new_node_type": new_node_type,
                "new_node_status": new_node_status,
                "new_node_metadata": new_metadata,
                "edge_label": edge_label,
            }, ""
        if normalized == "delete_node":
            node_id = _clean_text(
                raw.get("node_id")
                or raw.get("id")
                or tool_context_node_id,
                limit=128,
            )
            if not node_id:
                return {}, "node_id is required"
            confirm = _as_bool(raw.get("confirm"), False)
            return {"node_id": node_id, "confirm": confirm}, ""
        if normalized == "propose_setting_change":
            target_scope = _clean_text(raw.get("target_scope") or "project", limit=32).lower()
            if target_scope not in {"project", "global"}:
                target_scope = "project"
            proposal_type = _clean_text(raw.get("proposal_type") or "global_directive", limit=64)
            directive_text = _clean_text(
                raw.get("directive_text") or raw.get("content") or raw.get("value"),
                limit=4000,
            )
            if not directive_text:
                return {}, "directive_text is required"
            note = _clean_text(raw.get("note") or raw.get("reason"), limit=400)
            return {
                "target_scope": target_scope,
                "proposal_type": proposal_type or "global_directive",
                "directive_text": directive_text,
                "note": note,
            }, ""
        if normalized == "write_document":
            document_type_raw = _clean_text(
                raw.get("document_type")
                or raw.get("doc_type")
                or raw.get("type"),
                limit=64,
            ).lower()
            document_type = _DOC_TYPE_ALIASES.get(document_type_raw, document_type_raw)
            if document_type not in {"constitution", "clarify", "specification", "plan"}:
                return {}, "document_type is required"
            content = _clean_text(
                raw.get("content")
                or raw.get("markdown")
                or raw.get("text"),
                limit=12000,
            )
            if not content:
                return {}, "content is required"
            return {
                "document_type": document_type,
                "content": content,
            }, ""
        if normalized == "skip_document":
            document_type_raw = _clean_text(
                raw.get("document_type")
                or raw.get("doc_type")
                or raw.get("type"),
                limit=64,
            ).lower()
            document_type = _DOC_TYPE_ALIASES.get(document_type_raw, document_type_raw)
            if document_type not in {"constitution", "clarify", "specification", "plan"}:
                return {}, "document_type is required"
            reason = _clean_text(raw.get("reason") or raw.get("note"), limit=300)
            return {
                "document_type": document_type,
                "reason": reason,
            }, ""
        if normalized == "prose_rewrite":
            rewrite_mode = _clean_text(raw.get("rewrite_mode"), limit=64).lower()
            valid_modes = {"sensory", "pov", "iceberg", "show_dont_tell", "cinematic", "spatial", "style"}
            if rewrite_mode not in valid_modes:
                return {}, f"rewrite_mode must be one of [{', '.join(valid_modes)}]"
            target_text = _clean_text(raw.get("target_text"), limit=8000)
            if not target_text:
                return {}, "target_text is required"
            instructions = _clean_text(raw.get("instructions"), limit=2000)
            if not instructions:
                return {}, "instructions is required"
            return {
                "rewrite_mode": rewrite_mode,
                "target_text": target_text,
                "instructions": instructions,
            }, ""
        if normalized == "story_analysis_report":
            analysis_type = _clean_text(raw.get("analysis_type"), limit=64).lower()
            valid_types = {"framework", "pacing", "reader_reaction", "editorial"}
            if analysis_type not in valid_types:
                return {}, f"analysis_type must be one of [{', '.join(valid_types)}]"
            scope_raw = raw.get("scope_node_ids")
            scope_node_ids: list[str] = []
            if isinstance(scope_raw, list):
                scope_node_ids = [_clean_text(i, limit=128) for i in scope_raw if _clean_text(i, limit=128)]
            focus_question = _clean_text(raw.get("focus_question"), limit=500)
            return {
                "analysis_type": analysis_type,
                "scope_node_ids": scope_node_ids[:20],
                "focus_question": focus_question,
            }, ""
        if normalized == "foreshadowing_engine":
            action = _clean_text(raw.get("action"), limit=64).lower()
            valid_actions = {"register", "propose_payoff", "inject_motif", "extract_sensory"}
            if action not in valid_actions:
                return {}, f"action must be one of [{', '.join(valid_actions)}]"
            element_id = _clean_text(raw.get("element_id"), limit=128)
            description = _clean_text(raw.get("description"), limit=2000)
            target_node_id = _clean_text(raw.get("target_node_id"), limit=128)
            return {
                "action": action,
                "element_id": element_id,
                "description": description,
                "target_node_id": target_node_id,
            }, ""
        return {}, "unknown_tool"

    def tool_cache_key(
        self,
        *,
        tool_name: str,
        project_id: str,
        arguments: dict[str, Any],
    ) -> str:
        cache_payload = {
            "tool": str(tool_name or "").strip().lower(),
            "project_id": str(project_id or "").strip(),
            "arguments": arguments,
        }
        return hashlib.sha256(
            json.dumps(cache_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def execute_tool_call(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        project_id: str,
        tool_context_node_id: str,
        tool_thread_id: str,
        write_proposal_enabled: bool,
        write_document_enabled: bool,
        allow_skip_document: bool,
        node_tools_enabled: bool,
        tool_response_cache: dict[str, tuple[Any, int, dict[str, Any]]],
        single_read_char_limit: int,
        total_read_char_limit: int,
        total_read_chars: int,
    ) -> tuple[Any, int, dict[str, Any]]:
        normalized = str(tool_name or "").strip().lower()
        normalized_args, args_error = self.normalize_tool_call_arguments(
            tool_name=normalized,
            arguments=arguments,
            tool_context_node_id=tool_context_node_id,
        )

        def _payload_chars(payload: Any) -> int:
            try:
                return len(json.dumps(payload, ensure_ascii=False))
            except Exception:
                return len(str(payload or ""))

        if args_error:
            reason = "unknown_tool" if args_error == "unknown_tool" else "invalid_arguments"
            return (
                {"error": args_error, "tool": normalized},
                0,
                {"ok": False, "reason": reason, "error": args_error},
            )
        cacheable_tools = {
            "search_text",
            "read_chunk",
            "read_neighbors",
            "get_chapter_outline",
            "get_world_state",
            "list_nodes",
            "get_node",
        }
        cache_key = self.tool_cache_key(
            tool_name=normalized,
            project_id=project_id,
            arguments=normalized_args,
        )
        if normalized in cacheable_tools and cache_key in tool_response_cache:
            cached_payload, cached_read_chars, cached_meta = tool_response_cache[cache_key]
            next_meta = dict(cached_meta)
            next_meta["cache_hit"] = True
            next_meta["cached_read_chars"] = int(cached_read_chars)
            return cached_payload, 0, next_meta
        try:
            if normalized == "search_text":
                hits = self.readable_tool_service.search_text(
                    project_id=project_id,
                    query=str(normalized_args.get("query", "")),
                    top_k=int(normalized_args.get("top_k", 5)),
                    scope=cast(dict[str, Any], normalized_args.get("scope", {})),
                )
                returned_chars = sum(len(str(item.get("snippet", ""))) for item in hits)
                evidence_chunk_ids = [str(item.get("chunk_id", "")).strip() for item in hits]
                result_meta = {
                    "ok": True,
                    "cache_hit": False,
                    "evidence_chunk_ids": [item for item in evidence_chunk_ids if item],
                }
                tool_response_cache[cache_key] = (hits, returned_chars, dict(result_meta))
                return hits, returned_chars, result_meta
            if normalized == "read_chunk":
                chunk_id = str(normalized_args.get("chunk_id", ""))
                payload = self.readable_tool_service.read_chunk(chunk_id, project_id=project_id)
                content = str(payload.get("content", ""))
                truncated = False
                if len(content) > single_read_char_limit:
                    payload["content"] = content[:single_read_char_limit]
                    payload["chars"] = len(str(payload["content"]))
                    payload["truncated"] = True
                    payload["original_chars"] = len(content)
                    truncated = True
                returned_chars = len(str(payload.get("content", "")))
                if total_read_chars + returned_chars > total_read_char_limit:
                    return (
                        {
                            "error": "total_read_char_limit_exceeded",
                            "remaining_chars": max(0, total_read_char_limit - total_read_chars),
                        },
                        0,
                        {"ok": False, "reason": "total_read_char_limit_exceeded"},
                    )
                evidence_chunk_id = str(payload.get("chunk_id", "")).strip()
                result_meta = {
                    "ok": True,
                    "truncated": truncated,
                    "cache_hit": False,
                    "evidence_chunk_ids": [evidence_chunk_id] if evidence_chunk_id else [],
                }
                tool_response_cache[cache_key] = (payload, returned_chars, dict(result_meta))
                return payload, returned_chars, result_meta
            if normalized == "read_neighbors":
                payload = self.readable_tool_service.read_neighbors(
                    str(normalized_args.get("chunk_id", "")),
                    project_id=project_id,
                    before=int(normalized_args.get("before", 1)),
                    after=int(normalized_args.get("after", 1)),
                )
                budget = single_read_char_limit
                trimmed: list[dict[str, Any]] = []
                truncated = False
                returned_chars = 0
                evidence_chunk_ids: list[str] = []
                for item in payload:
                    text = str(item.get("content", ""))
                    if budget <= 0:
                        truncated = True
                        break
                    take = min(len(text), budget)
                    if take < len(text):
                        truncated = True
                    row = dict(item)
                    row["content"] = text[:take]
                    row["chars"] = take
                    trimmed.append(row)
                    returned_chars += take
                    budget -= take
                    chunk_id = str(row.get("chunk_id", "")).strip()
                    if chunk_id:
                        evidence_chunk_ids.append(chunk_id)
                if total_read_chars + returned_chars > total_read_char_limit:
                    return (
                        {
                            "error": "total_read_char_limit_exceeded",
                            "remaining_chars": max(0, total_read_char_limit - total_read_chars),
                        },
                        0,
                        {"ok": False, "reason": "total_read_char_limit_exceeded"},
                    )
                result_meta = {
                    "ok": True,
                    "truncated": truncated,
                    "cache_hit": False,
                    "evidence_chunk_ids": evidence_chunk_ids,
                }
                tool_response_cache[cache_key] = (trimmed, returned_chars, dict(result_meta))
                return trimmed, returned_chars, result_meta
            if normalized == "get_chapter_outline":
                payload = self.readable_tool_service.get_chapter_outline(
                    project_id=project_id,
                    node_id=str(normalized_args.get("node_id", "")),
                )
                returned_chars = _payload_chars(payload)
                if total_read_chars + returned_chars > total_read_char_limit:
                    return (
                        {
                            "error": "total_read_char_limit_exceeded",
                            "remaining_chars": max(0, total_read_char_limit - total_read_chars),
                        },
                        0,
                        {"ok": False, "reason": "total_read_char_limit_exceeded"},
                    )
                result_meta = {"ok": True, "cache_hit": False}
                tool_response_cache[cache_key] = (payload, returned_chars, dict(result_meta))
                return payload, returned_chars, result_meta
            if normalized == "get_world_state":
                payload = self.readable_tool_service.get_world_state(
                    project_id=project_id,
                    keys=cast(dict[str, Any], normalized_args.get("keys", {})),
                )
                returned_chars = _payload_chars(payload)
                if total_read_chars + returned_chars > total_read_char_limit:
                    return (
                        {
                            "error": "total_read_char_limit_exceeded",
                            "remaining_chars": max(0, total_read_char_limit - total_read_chars),
                        },
                        0,
                        {"ok": False, "reason": "total_read_char_limit_exceeded"},
                    )
                result_meta = {"ok": True, "cache_hit": False}
                tool_response_cache[cache_key] = (payload, returned_chars, dict(result_meta))
                return payload, returned_chars, result_meta
            if normalized == "get_effective_directives":
                target_project_id = str(normalized_args.get("project_id") or project_id).strip()
                payload = self.readable_tool_service.get_effective_directives(project_id=target_project_id)
                returned_chars = _payload_chars(payload)
                if total_read_chars + returned_chars > total_read_char_limit:
                    return (
                        {
                            "error": "total_read_char_limit_exceeded",
                            "remaining_chars": max(0, total_read_char_limit - total_read_chars),
                        },
                        0,
                        {"ok": False, "reason": "total_read_char_limit_exceeded"},
                    )
                return payload, returned_chars, {"ok": True}
            if normalized == "list_nodes":
                if not node_tools_enabled:
                    return (
                        {"error": "node_tools_disabled"},
                        0,
                        {"ok": False, "reason": "node_tools_disabled"},
                    )
                nodes = self.graph_service.list_nodes(project_id)
                limit = int(normalized_args.get("limit", 30))
                include_metadata = bool(normalized_args.get("include_metadata", False))
                payload = {
                    "count": len(nodes),
                    "truncated": len(nodes) > limit,
                    "nodes": [
                        self._serialize_node(node, include_metadata=include_metadata)
                        for node in nodes[:limit]
                    ],
                }
                returned_chars = _payload_chars(payload)
                if total_read_chars + returned_chars > total_read_char_limit:
                    return (
                        {
                            "error": "total_read_char_limit_exceeded",
                            "remaining_chars": max(0, total_read_char_limit - total_read_chars),
                        },
                        0,
                        {"ok": False, "reason": "total_read_char_limit_exceeded"},
                    )
                result_meta = {"ok": True, "cache_hit": False}
                tool_response_cache[cache_key] = (payload, returned_chars, dict(result_meta))
                return payload, returned_chars, result_meta
            if normalized == "get_node":
                if not node_tools_enabled:
                    return (
                        {"error": "node_tools_disabled"},
                        0,
                        {"ok": False, "reason": "node_tools_disabled"},
                    )
                node = self.graph_service.get_node(project_id, str(normalized_args.get("node_id", "")))
                payload = {"node": self._serialize_node(node, include_metadata=True)}
                returned_chars = _payload_chars(payload)
                if total_read_chars + returned_chars > total_read_char_limit:
                    return (
                        {
                            "error": "total_read_char_limit_exceeded",
                            "remaining_chars": max(0, total_read_char_limit - total_read_chars),
                        },
                        0,
                        {"ok": False, "reason": "total_read_char_limit_exceeded"},
                    )
                result_meta = {"ok": True, "cache_hit": False}
                tool_response_cache[cache_key] = (payload, returned_chars, dict(result_meta))
                return payload, returned_chars, result_meta
            if normalized == "create_node":
                if not node_tools_enabled:
                    return (
                        {"error": "node_tools_disabled"},
                        0,
                        {"ok": False, "reason": "node_tools_disabled"},
                    )
                node_type = NodeType(str(normalized_args.get("type", "chapter")).lower())
                node_status = NodeStatus(str(normalized_args.get("status", "draft")).lower())
                storyline_id_raw = normalized_args.get("storyline_id")
                storyline_id = str(storyline_id_raw).strip() if storyline_id_raw is not None else ""
                node = self.graph_service.add_node(
                    project_id,
                    NodeCreate(
                        title=str(normalized_args.get("title", "")),
                        type=node_type,
                        status=node_status,
                        storyline_id=storyline_id or None,
                        pos_x=float(normalized_args.get("pos_x", 0.0)),
                        pos_y=float(normalized_args.get("pos_y", 0.0)),
                        metadata=cast(dict[str, Any], normalized_args.get("metadata", {})),
                    ),
                )
                payload: dict[str, Any] = {"node": self._serialize_node(node, include_metadata=True)}
                link_from = str(normalized_args.get("link_from_node_id", "")).strip()
                if link_from:
                    edge = self.graph_service.add_edge(
                        project_id,
                        link_from,
                        node.id,
                        label=str(normalized_args.get("edge_label", "")).strip(),
                    )
                    payload["edge"] = self._serialize_edge(edge)
                return payload, 0, {"ok": True, "node_created": True}
            if normalized == "update_node":
                if not node_tools_enabled:
                    return (
                        {"error": "node_tools_disabled"},
                        0,
                        {"ok": False, "reason": "node_tools_disabled"},
                    )
                node_id = str(normalized_args.get("node_id", "")).strip()
                patch = cast(dict[str, Any], normalized_args.get("patch", {}))
                node = self.graph_service.update_node(project_id, node_id, patch)
                payload = {"node": self._serialize_node(node, include_metadata=True)}
                return payload, 0, {"ok": True, "node_updated": True}
            if normalized == "create_edge":
                if not node_tools_enabled:
                    return (
                        {"error": "node_tools_disabled"},
                        0,
                        {"ok": False, "reason": "node_tools_disabled"},
                    )
                edge = self.graph_service.add_edge(
                    project_id,
                    str(normalized_args.get("source_id", "")).strip(),
                    str(normalized_args.get("target_id", "")).strip(),
                    label=str(normalized_args.get("label", "")).strip(),
                )
                payload = {"edge": self._serialize_edge(edge)}
                return payload, 0, {"ok": True, "edge_created": True}
            if normalized == "split_node":
                if not node_tools_enabled:
                    return (
                        {"error": "node_tools_disabled"},
                        0,
                        {"ok": False, "reason": "node_tools_disabled"},
                    )
                    
                source_node_id = str(normalized_args.get("source_node_id", "")).strip()
                source_patch = cast(dict[str, Any], normalized_args.get("source_patch", {}))
                edge_label = str(normalized_args.get("edge_label", "")).strip()
                
                new_node_type = NodeType(str(normalized_args.get("new_node_type", "branch")).lower())
                new_node_status = NodeStatus(str(normalized_args.get("new_node_status", "draft")).lower())
                
                # Fetch original node to inherit storyline and position safely if not provided
                original_node = self.graph_service.get_node(project_id, source_node_id)
                new_pos_x = original_node.pos_x + 280.0
                new_pos_y = original_node.pos_y
                
                new_node_input = NodeCreate(
                    title=str(normalized_args.get("new_node_title", "")),
                    type=new_node_type,
                    status=new_node_status,
                    storyline_id=original_node.storyline_id,
                    pos_x=new_pos_x,
                    pos_y=new_pos_y,
                    metadata=cast(dict[str, Any], normalized_args.get("new_node_metadata", {})),
                )
                
                updated_source, new_node, new_edge = self.graph_service.split_node(
                    project_id=project_id,
                    source_node_id=source_node_id,
                    source_patch=source_patch,
                    new_node_input=new_node_input,
                    edge_label=edge_label,
                )
                
                payload = {
                    "source_node": self._serialize_node(updated_source, include_metadata=True),
                    "new_node": self._serialize_node(new_node, include_metadata=True),
                    "edge": self._serialize_edge(new_edge),
                }
                return payload, 0, {"ok": True, "node_split": True}
            if normalized == "delete_node":
                if not node_tools_enabled:
                    return (
                        {"error": "node_tools_disabled"},
                        0,
                        {"ok": False, "reason": "node_tools_disabled"},
                    )
                node_id = str(normalized_args.get("node_id", "")).strip()
                if not bool(normalized_args.get("confirm", False)):
                    payload = {
                        "node_id": node_id,
                        "status": "pending_user_confirm",
                        "requires_user_confirmation": True,
                    }
                    return payload, 0, {
                        "ok": True,
                        "requires_user_confirmation": True,
                        "pending_action": "delete_node",
                        "node_id": node_id,
                    }
                self.graph_service.delete_node(project_id, node_id)
                payload = {"status": "deleted", "node_id": node_id}
                return payload, 0, {"ok": True, "node_deleted": True}
            if normalized == "propose_setting_change":
                if not write_proposal_enabled:
                    return (
                        {"error": "write_proposal_tool_disabled"},
                        0,
                        {"ok": False, "reason": "write_proposal_tool_disabled"},
                    )
                if self.setting_proposal_service is None:
                    return (
                        {"error": "setting_proposal_service_unavailable"},
                        0,
                        {"ok": False, "reason": "setting_proposal_service_unavailable"},
                    )
                if not str(tool_thread_id).strip():
                    return (
                        {"error": "tool_thread_id_required"},
                        0,
                        {"ok": False, "reason": "tool_thread_id_required"},
                    )
                proposal = self.setting_proposal_service.create_from_agent_tool(
                    project_id=project_id,
                    node_id=str(tool_context_node_id or ""),
                    thread_id=str(tool_thread_id),
                    proposal_type=str(normalized_args.get("proposal_type", "global_directive")),
                    target_scope=str(normalized_args.get("target_scope", "project")),
                    directive_text=str(normalized_args.get("directive_text", "")).strip(),
                    note=str(normalized_args.get("note", "")).strip(),
                )
                payload = {
                    "proposal_id": str(proposal.get("id", "")),
                    "status": str(proposal.get("status", "")),
                    "proposal_type": str(proposal.get("proposal_type", "")),
                    "target_scope": str(proposal.get("target_scope", "")),
                    "requires_human_review": True,
                }
                return payload, 0, {
                    "ok": True,
                    "proposal_created": True,
                    "proposal_id": str(proposal.get("id", "")),
                }
            if normalized == "write_document":
                if not write_document_enabled:
                    return (
                        {"error": "write_document_tool_disabled"},
                        0,
                        {"ok": False, "reason": "write_document_tool_disabled"},
                    )
                doc_type = str(normalized_args.get("document_type", "")).strip()
                content = str(normalized_args.get("content", "")).strip()
                if not doc_type or not content:
                    return (
                        {"error": "document_type and content required"},
                        0,
                        {"ok": False, "reason": "invalid_arguments"},
                    )
                valid_types = {"constitution", "clarify", "specification", "plan"}
                if doc_type not in valid_types:
                    return (
                        {"error": f"invalid document_type, must be one of: {', '.join(valid_types)}"},
                        0,
                        {"ok": False, "reason": "invalid_arguments"},
                    )
                doc_key = f"{doc_type}_markdown"
                state = self.repository.get_workflow_doc_state(project_id)
                if state is None:
                    state = self.repository.upsert_workflow_doc_state(
                        project_id,
                        workflow_mode="original",
                        workflow_stage="draft",
                        workflow_initialized=True,
                        round_number=1,
                        assistant_message="",
                        collected_inputs={},
                        clarify_questions=[],
                        pending_docs={},
                        published_docs={},
                    )
                pending_docs = {
                    str(k): str(v or "")
                    for k, v in dict(state.get("pending_docs", {})).items()
                }
                pending_docs[doc_key] = content
                collected_inputs = {
                    str(k): str(v or "")
                    for k, v in dict(state.get("collected_inputs", {})).items()
                }
                clarify_questions = [
                    str(item).strip()
                    for item in list(state.get("clarify_questions", []))
                    if str(item).strip()
                ]
                published_docs = {
                    str(k): str(v or "")
                    for k, v in dict(state.get("published_docs", {})).items()
                }
                self.repository.upsert_workflow_doc_state(
                    project_id,
                    workflow_mode=str(state.get("workflow_mode", "")).strip() or "original",
                    workflow_stage=str(state.get("workflow_stage", "")).strip() or "idle",
                    workflow_initialized=bool(state.get("workflow_initialized", False)),
                    round_number=max(0, int(state.get("round_number", 0) or 0)),
                    assistant_message=str(state.get("assistant_message", "") or ""),
                    collected_inputs=collected_inputs,
                    clarify_questions=clarify_questions,
                    pending_docs=pending_docs,
                    published_docs=published_docs,
                )
                persisted = self.persist_workflow_doc_to_project_settings(
                    project_id=project_id,
                    doc_key=doc_key,
                    content=content,
                )
                payload = {
                    "document_type": doc_type,
                    "status": "written",
                    "chars": len(content),
                    "project_settings_updated": persisted,
                }
                return payload, 0, {
                    "ok": True,
                    "document_written": True,
                    "project_settings_updated": persisted,
                }
            if normalized == "skip_document":
                if not allow_skip_document:
                    return (
                        {"error": "skip_document_tool_disabled"},
                        0,
                        {"ok": False, "reason": "skip_document_tool_disabled"},
                    )
                doc_type = str(normalized_args.get("document_type", "")).strip().lower()
                if doc_type not in {"constitution", "clarify", "specification", "plan"}:
                    return (
                        {"error": "invalid document_type"},
                        0,
                        {"ok": False, "reason": "invalid_arguments"},
                    )
                payload = {
                    "document_type": doc_type,
                    "status": "pending_user_confirm",
                    "reason": str(normalized_args.get("reason", "")).strip(),
                    "requires_user_confirmation": True,
                }
                return payload, 0, {
                    "ok": True,
                    "skip_document_requested": True,
                    "skip_document_type": doc_type,
                    "requires_user_confirmation": True,
                }
            if normalized == "prose_rewrite":
                payload = {
                    "status": "acknowledged",
                    "rewrite_mode": normalized_args.get("rewrite_mode"),
                    "note": "Parameters parsed successfully. Provide the rewritten text in your final response.",
                }
                return payload, 0, {"ok": True, "action": "prose_rewrite"}
            if normalized == "story_analysis_report":
                payload = {
                    "status": "acknowledged",
                    "analysis_type": normalized_args.get("analysis_type"),
                    "note": "Parameters parsed successfully. Please output your analysis in markdown format in your final response.",
                }
                return payload, 0, {"ok": True, "action": "story_analysis_report"}
            if normalized == "foreshadowing_engine":
                payload = {
                    "status": "acknowledged",
                    "action_type": normalized_args.get("action"),
                    "element_id": normalized_args.get("element_id"),
                    "note": "Foreshadowing action registered. Output the narrative changes in your final response.",
                }
                return payload, 0, {"ok": True, "action": "foreshadowing_engine"}
            return (
                {"error": f"unknown_tool:{normalized}"},
                0,
                {"ok": False, "reason": "unknown_tool"},
            )
        except Exception as exc:
            return (
                {"error": str(exc)},
                0,
                {"ok": False, "reason": "execution_error", "error": str(exc)},
            )

    def persist_workflow_doc_to_project_settings(
        self,
        *,
        project_id: str,
        doc_key: str,
        content: str,
    ) -> bool:
        clean_doc_key = str(doc_key or "").strip()
        if clean_doc_key not in {
            "constitution_markdown",
            "clarify_markdown",
            "specification_markdown",
            "plan_markdown",
        }:
            return False
        text = str(content or "").strip()
        project = self.repository.get_project(project_id)
        if project is None:
            return False
        setattr(project.settings, clean_doc_key, text)
        current_skips = list(getattr(project.settings, "guide_skipped_docs", []) or [])
        filtered_skips: list[str] = []
        for item in current_skips:
            slot = _GUIDE_DOC_ALIASES.get(str(item or "").strip().lower(), "")
            if not slot or slot == clean_doc_key:
                continue
            if slot not in filtered_skips:
                filtered_skips.append(slot)
        project.settings.guide_skipped_docs = filtered_skips
        project.updated_at = utc_now()
        project.active_revision += 1
        self.repository.update_project(project)
        return True

    def create_suggested_nodes(
        self,
        *,
        project_id: str,
        source_node: Any,
        options: list[dict[str, Any]],
        edge_label: str,
    ) -> list[str]:
        source_node_id = str(getattr(source_node, "id", "")).strip()
        if not source_node_id:
            return []
        source_x = float(getattr(source_node, "pos_x", 0.0))
        source_y = float(getattr(source_node, "pos_y", 0.0))
        source_status = str(getattr(source_node, "status", "draft") or "draft").strip().lower()
        if source_status not in _NODE_STATUS_VALUES:
            source_status = "draft"
        storyline = getattr(source_node, "storyline_id", None)
        source_storyline_id = str(storyline).strip() if storyline is not None else ""
        now_iso = utc_now().isoformat()
        created_ids: list[str] = []
        tool_response_cache: dict[str, tuple[Any, int, dict[str, Any]]] = {}

        for index, option in enumerate(options):
            title = str(option.get("title", "")).strip()[:200]
            if not title:
                continue
            description = str(option.get("description", "")).strip()
            raw_steps = option.get("outline_steps")
            steps: list[str] = []
            if isinstance(raw_steps, list):
                steps = [str(item).strip() for item in raw_steps if str(item).strip()]
            elif isinstance(raw_steps, str):
                steps = [
                    line.strip("- ").strip()
                    for line in raw_steps.splitlines()
                    if line.strip()
                ]
            metadata = {
                "ai_suggested": True,
                "ai_suggested_from": source_node_id,
                "ai_suggested_at": now_iso,
                "summary": description,
                "content": description,
                "outline_markdown": "\n".join(f"- {step}" for step in steps) if steps else "",
                "ai_suggested_sentiment": str(option.get("sentiment", "neutral") or "neutral"),
                "ai_suggested_plan_mode": str(option.get("plan_mode", "story_extend") or "story_extend"),
            }
            payload, _read_chars, result_meta = self.execute_tool_call(
                tool_name="create_node",
                arguments={
                    "title": title,
                    "type": "branch",
                    "status": source_status,
                    "storyline_id": source_storyline_id,
                    "pos_x": source_x + 280 + index * 240,
                    "pos_y": source_y + (index - 1) * 150,
                    "metadata": metadata,
                },
                project_id=project_id,
                tool_context_node_id=source_node_id,
                tool_thread_id="",
                write_proposal_enabled=False,
                write_document_enabled=False,
                allow_skip_document=False,
                node_tools_enabled=True,
                tool_response_cache=tool_response_cache,
                single_read_char_limit=4000,
                total_read_char_limit=20000,
                total_read_chars=0,
            )
            if not bool(result_meta.get("ok", False)):
                continue
            created_node = payload.get("node") if isinstance(payload, dict) else None
            created_node_id = str((created_node or {}).get("id", "")).strip() if isinstance(created_node, dict) else ""
            if not created_node_id:
                continue
            self.execute_tool_call(
                tool_name="create_edge",
                arguments={
                    "source_id": source_node_id,
                    "target_id": created_node_id,
                    "label": edge_label,
                },
                project_id=project_id,
                tool_context_node_id=source_node_id,
                tool_thread_id="",
                write_proposal_enabled=False,
                write_document_enabled=False,
                allow_skip_document=False,
                node_tools_enabled=True,
                tool_response_cache=tool_response_cache,
                single_read_char_limit=4000,
                total_read_char_limit=20000,
                total_read_chars=0,
            )
            created_ids.append(created_node_id)
        return created_ids

    def _serialize_node(self, node: Any, *, include_metadata: bool = False) -> dict[str, Any]:
        node_type = getattr(node, "type", "")
        node_status = getattr(node, "status", "")
        payload: dict[str, Any] = {
            "id": str(getattr(node, "id", "")),
            "project_id": str(getattr(node, "project_id", "")),
            "title": str(getattr(node, "title", "")),
            "type": str(getattr(node_type, "value", node_type)),
            "status": str(getattr(node_status, "value", node_status)),
            "storyline_id": getattr(node, "storyline_id", None),
            "pos_x": float(getattr(node, "pos_x", 0.0)),
            "pos_y": float(getattr(node, "pos_y", 0.0)),
        }
        if include_metadata:
            metadata = getattr(node, "metadata", {})
            payload["metadata"] = dict(metadata) if isinstance(metadata, dict) else {}
        return payload

    def _serialize_edge(self, edge: Any) -> dict[str, Any]:
        return {
            "id": str(getattr(edge, "id", "")),
            "project_id": str(getattr(edge, "project_id", "")),
            "source_id": str(getattr(edge, "source_id", "")),
            "target_id": str(getattr(edge, "target_id", "")),
            "label": str(getattr(edge, "label", "")),
            "narrative_order": getattr(edge, "narrative_order", None),
        }
