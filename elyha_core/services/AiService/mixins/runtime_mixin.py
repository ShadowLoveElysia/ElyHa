"""Workflow/runtime/task methods for AIService."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import TYPE_CHECKING, Any, NoReturn, cast

from elyha_core.adapters.llm_adapter import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    create_llm_adapter,
)
from elyha_core.i18n import tr
from elyha_core.llm_presets import LLMPreset, preset_to_platform_config
from elyha_core.models.task import Task, TaskStatus
from elyha_core.services.context_assembler import (
    BuildInput,
    ContextAssembler,
    PromptBundle,
)
from elyha_core.services.context_service import ContextPack, ContextService
from elyha_core.services.graph_service import GraphService
from elyha_core.services.prompt_template_service import PromptTemplateService
from elyha_core.services.readable_content_tool_service import ReadableContentToolService
from elyha_core.services.Tools import ToolService
from elyha_core.services.validation_service import ValidationService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id
from elyha_core.utils.text_splitter import split_text_by_chars
from langgraph.graph import END, StateGraph

from ..types import (
    BranchOption,
    ChapterDraftResult,
    ChatAssistResult,
    ClarificationQuestionResult,
    GenerateResult,
    OutlineDetailNode,
    OutlineDetailNodesResult,
    OutlineGuideResult,
    ReviewReport,
    WorkflowClarifyResult,
    WorkflowDocsDraftResult,
    WorkflowState,
    WorkflowSyncResult,
)

if TYPE_CHECKING:
    from elyha_core.services.setting_proposal_service import SettingProposalService
    from elyha_core.services.state_service import StateService


class AIServiceRuntimeMixin:
    def _build_system_prompt(self, project_id: str | None = None) -> str:
        base_prompt = (
            self.prompt_templates.load("system_prompt")
            or tr("ai.system_prompt")
        ).strip()
        if not project_id:
            return base_prompt
        project = self.repository.get_project(project_id)
        if project is None:
            return base_prompt
        settings = project.settings
        style = str(getattr(settings, "system_prompt_style", "")).strip()
        forbidden = str(getattr(settings, "system_prompt_forbidden", "")).strip()
        notes = str(getattr(settings, "system_prompt_notes", "")).strip()
        global_directives = str(getattr(settings, "global_directives", "")).strip()
        constraint_sections: list[str] = []
        if style:
            constraint_sections.append(f"[User Writing Style]\n{style}")
        if forbidden:
            constraint_sections.append(f"[Forbidden Content]\n{forbidden}")
        if notes:
            constraint_sections.append(f"[Additional Notes To Explain]\n{notes}")
        if global_directives:
            constraint_sections.append(f"[Global Directives]\n{global_directives}")

        docs_sections: list[str] = []
        constitution = str(getattr(settings, "constitution_markdown", "")).strip()
        clarify = str(getattr(settings, "clarify_markdown", "")).strip()
        specification = str(getattr(settings, "specification_markdown", "")).strip()
        plan = str(getattr(settings, "plan_markdown", "")).strip()
        if constitution:
            docs_sections.append(f"[Constitution]\n{constitution}")
        if clarify:
            docs_sections.append(f"[Clarify]\n{clarify}")
        if specification:
            docs_sections.append(f"[Specification]\n{specification}")
        if plan:
            docs_sections.append(f"[Plan]\n{plan}")

        blocks: list[str] = [base_prompt]
        if constraint_sections:
            blocks.append(
                "[User Constraints]\n"
                "The following constraints are from current project settings and should be followed.\n\n"
                + "\n\n".join(constraint_sections)
            )
        if docs_sections:
            blocks.append(
                "[Published Project Workflow Docs]\n"
                "Treat these as approved baselines unless the user explicitly asks for revision.\n\n"
                + "\n\n".join(docs_sections)
            )
        return "\n\n".join(blocks)

    def _build_single_workflow(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("context", self._wf_context_node)
        graph.add_node("prompt", self._wf_prompt_node)
        graph.add_node("llm", self._wf_llm_node)
        graph.set_entry_point("context")
        graph.add_edge("context", "prompt")
        graph.add_edge("prompt", "llm")
        graph.add_edge("llm", END)
        return graph.compile()

    def _build_chapter_multi_workflow(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("context", self._wf_context_node)
        graph.add_node("planner_prompt", self._wf_planner_prompt_node)
        graph.add_node("planner_llm", self._wf_planner_llm_node)
        graph.add_node("writer_prompt", self._wf_writer_prompt_node)
        graph.add_node("writer_llm", self._wf_writer_llm_node)
        graph.add_node("reviewer_prompt", self._wf_reviewer_prompt_node)
        graph.add_node("reviewer_llm", self._wf_reviewer_llm_node)
        graph.add_node("synthesizer_prompt", self._wf_synthesizer_prompt_node)
        graph.add_node("synthesizer_llm", self._wf_synthesizer_llm_node)
        graph.set_entry_point("context")
        graph.add_edge("context", "planner_prompt")
        graph.add_edge("planner_prompt", "planner_llm")
        graph.add_edge("planner_llm", "writer_prompt")
        graph.add_edge("writer_prompt", "writer_llm")
        graph.add_edge("writer_llm", "reviewer_prompt")
        graph.add_edge("reviewer_prompt", "reviewer_llm")
        graph.add_edge("reviewer_llm", "synthesizer_prompt")
        graph.add_edge("synthesizer_prompt", "synthesizer_llm")
        graph.add_edge("synthesizer_llm", END)
        return graph.compile()

    def _run_workflow(
        self,
        *,
        task_type: str,
        project_id: str,
        node_id: str,
        token_budget: int,
        style_hint: str = "",
        branch_count: int = 3,
        workflow_mode: str = "single",
        task_id: str | None = None,
        tool_thread_id: str = "",
    ) -> WorkflowState:
        payload: WorkflowState = {
            "task_id": task_id or "",
            "task_type": task_type,
            "project_id": project_id,
            "node_id": node_id,
            "token_budget": token_budget,
            "style_hint": style_hint,
            "branch_count": branch_count,
            "workflow_mode": workflow_mode,
            "tool_thread_id": str(tool_thread_id or "").strip(),
        }
        workflow = self._single_workflow
        if task_type == "generate_chapter" and workflow_mode == "multi_agent":
            workflow = self._chapter_multi_workflow
        result = workflow.invoke(payload)
        return cast(WorkflowState, result)

    def _wf_context_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        project_id = state["project_id"]
        node_id = state["node_id"]
        token_budget = int(state.get("token_budget", 2200))
        self._ensure_project_valid(project_id)
        node = self.graph_service.get_node(project_id, node_id)
        context = self.context_service.build_context(
            project_id,
            node_id,
            token_budget=token_budget,
        )
        return {
            "node": node,
            "context_pack": context,
            "llm_route": self._resolve_node_llm_route(node),
        }

    def _wf_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        task_type = state["task_type"]
        node = state["node"]
        context = state["context_pack"]
        project_id = str(state.get("project_id", ""))
        token_budget = int(state.get("token_budget", 2200))
        if task_type == "generate_chapter":
            prompt, bundle = self._chapter_prompt(
                project_id,
                node,
                context,
                style_hint=str(state.get("style_hint", "")),
                token_budget=token_budget,
            )
        elif task_type == "generate_branches":
            prompt, bundle = self._branch_prompt(
                project_id,
                node,
                context,
                n=int(state.get("branch_count", 3)),
                token_budget=token_budget,
            )
        elif task_type in {"review_lore", "review_logic"}:
            prompt, bundle = self._review_prompt(
                project_id,
                task_type,
                node,
                context,
                token_budget=token_budget,
            )
        else:
            raise ValueError(tr("ai.workflow.unsupported_task_type", task_type=task_type))
        return {"prompt": prompt, "prompt_bundle": bundle}

    def _wf_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        task_type = state["task_type"]
        prompt = state["prompt"]
        token_budget = int(state.get("token_budget", 2200))
        platform_config = {"token_budget": token_budget}
        platform_config["tool_context_node_id"] = str(state.get("node_id", ""))
        platform_config["tool_thread_id"] = str(state.get("tool_thread_id", ""))
        if task_type == "generate_branches":
            platform_config["branch_count"] = int(state.get("branch_count", 3))
        response = self._generate(
            task_type=task_type,
            prompt=prompt,
            platform_config=platform_config,
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
        )
        return {"llm_response": response}

    def _wf_planner_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        node = state["node"]
        context = state["context_pack"]
        prompt, bundle = self._planner_prompt(
            str(state.get("project_id", "")),
            node,
            context,
            style_hint=str(state.get("style_hint", "")),
            token_budget=max(400, int(state.get("token_budget", 2200)) // 2),
        )
        return {"planner_prompt": prompt, "planner_prompt_bundle": bundle}

    def _wf_planner_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_plan",
            prompt=state["planner_prompt"],
            platform_config={"token_budget": max(400, token_budget // 2)},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
        )
        return {
            "planner_response": response,
            "agent_trace": self._append_agent_trace(state, "planner", response.content),
        }

    def _wf_writer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        node = state["node"]
        context = state["context_pack"]
        planner_response = cast(LLMResponse, state["planner_response"])
        prompt, bundle = self._writer_prompt(
            str(state.get("project_id", "")),
            node,
            context,
            plan=planner_response.content,
            token_budget=int(state.get("token_budget", 2200)),
        )
        return {"writer_prompt": prompt, "writer_prompt_bundle": bundle}

    def _wf_writer_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_write",
            prompt=state["writer_prompt"],
            platform_config={
                "token_budget": token_budget,
                "tool_context_node_id": str(state.get("node_id", "")),
                "tool_thread_id": str(state.get("tool_thread_id", "")),
            },
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
        )
        return {
            "writer_response": response,
            "agent_trace": self._append_agent_trace(state, "writer", response.content),
        }

    def _wf_reviewer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        node = state["node"]
        context = state["context_pack"]
        writer_response = cast(LLMResponse, state["writer_response"])
        prompt, bundle = self._chapter_reviewer_prompt(
            str(state.get("project_id", "")),
            node,
            context,
            draft=writer_response.content,
            token_budget=max(400, int(state.get("token_budget", 2200)) // 2),
        )
        return {"reviewer_prompt": prompt, "reviewer_prompt_bundle": bundle}

    def _wf_reviewer_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_review",
            prompt=state["reviewer_prompt"],
            platform_config={"token_budget": max(400, token_budget // 2)},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
        )
        return {
            "reviewer_response": response,
            "agent_trace": self._append_agent_trace(state, "reviewer", response.content),
        }

    def _wf_synthesizer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        node = state["node"]
        context = state["context_pack"]
        writer_response = cast(LLMResponse, state["writer_response"])
        reviewer_response = cast(LLMResponse, state["reviewer_response"])
        prompt, bundle = self._synthesizer_prompt(
            str(state.get("project_id", "")),
            node,
            context,
            draft=writer_response.content,
            review_feedback=reviewer_response.content,
            token_budget=int(state.get("token_budget", 2200)),
        )
        return {"synthesizer_prompt": prompt, "synthesizer_prompt_bundle": bundle}

    def _wf_synthesizer_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_synthesize",
            prompt=state["synthesizer_prompt"],
            platform_config={"token_budget": token_budget},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
        )
        return {
            "llm_response": response,
            "agent_trace": self._append_agent_trace(state, "synthesizer", response.content),
        }

    def _adapter_for_provider(self, provider: str):
        normalized = str(provider).strip().lower()
        cached = self._adapter_cache.get(normalized)
        if cached is not None:
            return cached
        adapter = create_llm_adapter(normalized, platform_config={})
        self._adapter_cache[normalized] = adapter
        return adapter

    def _resolve_tokenizer_model_hint(self) -> str:
        direct = str(self._default_platform_config.get("model_name", "") or "").strip()
        if direct:
            return direct
        return str(os.getenv("ELYHA_MODEL_NAME", "") or "").strip()

    def _record_prompt_cache_monitor(
        self,
        *,
        project_id: str,
        node_id: str,
        task_type: str,
        task_mode: str,
        prompt: str,
    ) -> dict[str, Any]:
        key = f"{project_id}:{node_id}:{task_type}:{task_mode}"
        current_prompt = str(prompt or "")
        current_hash = hashlib.sha256(current_prompt.encode("utf-8")).hexdigest()
        entry = self._prompt_cache_monitor.get(key)
        if entry is None:
            entry = {
                "total": 0,
                "hits": 0,
                "misses": 0,
                "last_prompt": "",
                "last_prompt_hash": "",
            }
        total = int(entry.get("total", 0))
        hits = int(entry.get("hits", 0))
        misses = int(entry.get("misses", 0))
        last_prompt = str(entry.get("last_prompt", "") or "")

        status = "warmup"
        prefix_hit: bool | None = None
        if total > 0 and last_prompt:
            prefix_hit = current_prompt.startswith(last_prompt)
            if prefix_hit:
                hits += 1
                status = "hit"
            else:
                misses += 1
                status = "miss"
        elif total > 0:
            status = "miss"
            misses += 1

        total += 1
        hit_rate_base = hits + misses
        hit_rate = float(hits / hit_rate_base) if hit_rate_base > 0 else 0.0

        entry.update(
            {
                "total": total,
                "hits": hits,
                "misses": misses,
                "last_prompt": current_prompt,
                "last_prompt_hash": current_hash,
            }
        )
        self._prompt_cache_monitor[key] = entry
        return {
            "cache_key": key,
            "status": status,
            "prefix_hit": prefix_hit,
            "total": total,
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hit_rate, 4),
            "prompt_hash": current_hash,
        }

    def _resolve_node_llm_route(self, node: Any) -> dict[str, Any]:
        metadata = getattr(node, "metadata", {})
        if not isinstance(metadata, dict):
            return {}
        raw_preset = metadata.get("agent_preset")
        preset_tag = str(raw_preset).strip() if raw_preset is not None else ""
        if not preset_tag:
            return {}
        preset = self._llm_presets.get(preset_tag)
        if preset is None:
            return {}
        platform_config = preset_to_platform_config(preset)
        return {
            "provider": "llmrequester",
            "preset_tag": preset.tag,
            "preset_name": preset.name,
            "platform_config": platform_config,
        }

    def _normalize_workflow_mode(self, workflow_mode: str) -> str:
        normalized = str(workflow_mode).strip().lower().replace("-", "_")
        if not normalized:
            return "multi_agent"
        if normalized in {"single", "single_agent"}:
            return "single"
        if normalized in {"multi", "multi_agent", "multiagent"}:
            return "multi_agent"
        raise ValueError(tr("ai.workflow.mode_invalid"))

    def _append_agent_trace(
        self,
        state: WorkflowState,
        agent_name: str,
        content: str,
    ) -> dict[str, str]:
        trace = {
            str(key): str(value)
            for key, value in cast(dict[str, str], state.get("agent_trace", {})).items()
        }
        trace[agent_name] = self._truncate_trace(content)
        return trace

    def _truncate_trace(self, content: str, *, max_len: int = 800) -> str:
        compact = " ".join(content.strip().split())
        if len(compact) <= max_len:
            return compact
        return f"{compact[: max_len - 3]}..."

    def _parse_branch_options(
        self,
        content: str,
        *,
        count: int,
        strict_json_fence: bool = False,
    ) -> list[BranchOption]:
        parsed_payload, parsed_mode = self._parse_branch_options_payload(
            content,
            strict_json_fence=strict_json_fence,
        )
        if parsed_payload:
            parsed_options: list[BranchOption] = []
            top_level_mode = self._normalize_plan_mode(parsed_mode or parsed_payload[0].get("plan_mode"))
            option_limit = 1 if top_level_mode == "outline_decompose" else max(1, count)
            for item in parsed_payload[:option_limit]:
                title = str(item.get("title", "")).strip() or f"Branch {len(parsed_options) + 1}"
                description = str(
                    item.get("description", "")
                    or item.get("summary", "")
                    or item.get("outline", "")
                ).strip()
                outline_steps = self._normalize_outline_list(
                    item.get("outline_steps")
                    or item.get("beats")
                    or item.get("next_steps")
                    or item.get("future_steps"),
                    limit=8,
                )
                if not description and outline_steps:
                    description = " / ".join(outline_steps[:2])
                if not description:
                    description = tr("ai.branch.option_fallback", index=len(parsed_options) + 1)
                option_mode = self._normalize_plan_mode(item.get("plan_mode") or top_level_mode)
                parsed_options.append(
                    BranchOption(
                        title=title,
                        description=description,
                        outline_steps=outline_steps,
                        sentiment=self._normalize_sentiment(item.get("sentiment")),
                        plan_mode=option_mode,
                    )
                )
            min_options = 1 if top_level_mode == "outline_decompose" else max(1, count)
            while len(parsed_options) < min_options:
                index = len(parsed_options) + 1
                parsed_options.append(
                    BranchOption(
                        title=f"Branch {index}",
                        description=tr("ai.branch.option_fallback", index=index),
                        outline_steps=[],
                        sentiment="neutral",
                        plan_mode=top_level_mode,
                    )
                )
            return parsed_options

        if strict_json_fence:
            raise RuntimeError("strict_json_fence_output=true requires valid JSON fence payload")

        options: list[BranchOption] = []
        for line in content.splitlines():
            text = line.strip()
            if not text:
                continue
            if text.startswith("-"):
                text = text[1:].strip()
            parts = text.split(":", 1)
            if len(parts) == 2:
                title = parts[0].strip() or f"Branch {len(options) + 1}"
                desc = parts[1].strip() or "No description"
            else:
                title = f"Branch {len(options) + 1}"
                desc = text
            options.append(
                BranchOption(
                    title=title,
                    description=desc,
                    outline_steps=[],
                    sentiment="neutral",
                    plan_mode="story_extend",
                )
            )
            if len(options) >= count:
                break
        while len(options) < count:
            index = len(options) + 1
            options.append(
                BranchOption(
                    title=f"Branch {index}",
                    description=tr("ai.branch.option_fallback", index=index),
                    outline_steps=[],
                    sentiment="neutral",
                    plan_mode="story_extend",
                )
            )
        return options

    def _parse_branch_options_payload(
        self,
        content: str,
        *,
        strict_json_fence: bool = False,
    ) -> tuple[list[dict[str, Any]], str]:
        raw = str(content or "").strip()
        if not raw:
            return [], "story_extend"
        if strict_json_fence:
            payload = self._parse_strict_json_fence_payload(raw)
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)], "story_extend"
            if isinstance(payload, dict):
                top_level_mode = self._normalize_plan_mode(payload.get("plan_mode"))
                options = payload.get("options")
                if isinstance(options, list):
                    return [item for item in options if isinstance(item, dict)], top_level_mode
                option = payload.get("option")
                if isinstance(option, dict):
                    return [option], top_level_mode
            raise RuntimeError("strict_json_fence_output=true requires JSON object/array payload")
        candidates = [raw]
        bracket_match = re.search(r"\[[\s\S]*\]", raw)
        if bracket_match:
            candidates.append(bracket_match.group(0).strip())
        brace_match = re.search(r"\{[\s\S]*\}", raw)
        if brace_match:
            candidates.append(brace_match.group(0).strip())
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except Exception:
                continue
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)], "story_extend"
            if isinstance(payload, dict):
                top_level_mode = self._normalize_plan_mode(payload.get("plan_mode"))
                options = payload.get("options")
                if isinstance(options, list):
                    return [item for item in options if isinstance(item, dict)], top_level_mode
                option = payload.get("option")
                if isinstance(option, dict):
                    return [option], top_level_mode
        return [], "story_extend"

    def _normalize_plan_mode(self, value: Any) -> str:
        raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if raw == "outline_decompose":
            return "outline_decompose"
        if raw == "story_extend":
            return "story_extend"
        return "story_extend"

    def _normalize_sentiment(self, value: Any) -> str:
        raw = str(value or "").strip().lower()
        alias_map = {
            "conflict": "conflict",
            "high_pressure": "conflict",
            "pressure": "conflict",
            "combat": "conflict",
            "冲突": "conflict",
            "高压": "conflict",
            "対峙": "conflict",
            "衝突": "conflict",
            "calm": "calm",
            "memory": "calm",
            "flashback": "calm",
            "平缓": "calm",
            "回忆": "calm",
            "穏やか": "calm",
            "suspense": "suspense",
            "mystery": "suspense",
            "悬疑": "suspense",
            "疑云": "suspense",
            "サスペンス": "suspense",
            "twist": "twist",
            "turning": "twist",
            "转折": "twist",
            "反转": "twist",
            "転換": "twist",
            "neutral": "neutral",
            "中性": "neutral",
            "中立": "neutral",
        }
        return alias_map.get(raw, "neutral")

    def _parse_review_output(self, content: str) -> tuple[str, float, list[str]]:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        score = 0.7
        issues: list[str] = []
        summary_lines: list[str] = []
        for line in lines:
            lower = line.lower()
            if lower.startswith("score:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    score = float(raw)
                except ValueError:
                    pass
            elif line.startswith("-"):
                issues.append(line[1:].strip())
            else:
                summary_lines.append(line)
        summary = "\n".join(summary_lines) if summary_lines else tr("ai.review.summary_default")
        return summary, max(0.0, min(1.0, score)), issues

    def _create_task(self, project_id: str, node_id: str, *, task_type: str) -> Task:
        task = Task(
            id=generate_id("task"),
            project_id=project_id,
            node_id=node_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            revision=self._project_revision(project_id),
        )
        self.repository.create_task(task)
        return task

    def _set_task_running(self, task: Task) -> None:
        task.status = TaskStatus.RUNNING
        task.started_at = utc_now()
        task.error_code = None
        task.error_message = None
        self.repository.update_task(task)

    def _set_task_success(self, task: Task, *, revision: int) -> None:
        task.status = TaskStatus.SUCCESS
        task.finished_at = utc_now()
        task.revision = revision
        self.repository.update_task(task)

    def _set_task_cancelled(self, task: Task, *, message: str = "task cancelled") -> None:
        task.status = TaskStatus.CANCELLED
        task.error_code = "cancelled"
        task.error_message = message
        if task.started_at is None:
            task.started_at = utc_now()
        task.finished_at = utc_now()
        task.revision = self._project_revision(task.project_id)
        self.repository.update_task(task)

    def _set_task_failed(self, task: Task, exc: Exception) -> None:
        message = str(exc).strip() or exc.__class__.__name__
        code = self._extract_error_code(message)
        task.status = TaskStatus.FAILED
        task.error_code = code
        task.error_message = message
        task.finished_at = utc_now()
        task.revision = self._project_revision(task.project_id)
        self.repository.update_task(task)

    def _extract_error_code(self, message: str) -> str:
        text = message.lower()
        if "cancelled" in text or "canceled" in text:
            return "cancelled"
        if "[auth]" in text or "unauthorized" in text:
            return "auth"
        if "rate_limit" in text or "429" in text:
            return "rate_limit"
        if "timeout" in text:
            return "timeout"
        if "network" in text or "connection" in text:
            return "network"
        if "server" in text:
            return "server"
        if "content" in text or "parse" in text:
            return "content"
        return "generic"

    def _project_revision(self, project_id: str) -> int:
        project = self.repository.get_project(project_id)
        if project is None:
            self._raise_project_missing(project_id)
        assert project is not None
        return project.active_revision

    def _ensure_task_not_cancelled(self, state: WorkflowState) -> None:
        task_id = str(state.get("task_id", "")).strip()
        if not task_id:
            return
        if self._is_task_cancelled(task_id):
            raise RuntimeError("task cancelled")

    def _is_task_cancelled(self, task_id: str) -> bool:
        task = self.repository.get_task(task_id)
        return task is not None and task.status == TaskStatus.CANCELLED

    def _ensure_project_valid(self, project_id: str) -> None:
        report = self.validation_service.validate_project(project_id)
        if report.errors:
            codes = ", ".join(sorted({issue.code for issue in report.errors}))
            raise ValueError(tr("err.project_validation_failed", codes=codes))

    def _raise_project_missing(self, project_id: str) -> NoReturn:
        raise KeyError(tr("err.project_not_found", project_id=project_id))
