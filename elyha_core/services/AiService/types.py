"""Shared types for AIService package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

from elyha_core.adapters.llm_adapter import LLMResponse
from elyha_core.services.context_service import ContextPack
from elyha_core.services.context_assembler import PromptBundle


@dataclass(slots=True)
class BranchOption:
    title: str
    description: str
    outline_steps: list[str] = field(default_factory=list)
    sentiment: str = "neutral"
    plan_mode: str = "story_extend"


@dataclass(slots=True)
class GenerateResult:
    task_id: str
    project_id: str
    node_id: str
    content: str
    revision: int
    prompt_tokens: int
    completion_tokens: int
    provider: str
    workflow_mode: str = "single"
    agent_trace: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ChapterDraftResult:
    task_id: str
    project_id: str
    node_id: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    provider: str
    workflow_mode: str = "single"
    agent_trace: dict[str, str] = field(default_factory=dict)
    node_metadata_patch: dict[str, Any] = field(default_factory=dict)
    prompt_version: str = ""
    diff_patch: dict[str, Any] = field(default_factory=dict)
    agent_loop_rounds: list[dict[str, Any]] = field(default_factory=list)
    agent_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    agent_loop_metrics: dict[str, Any] = field(default_factory=dict)
    tool_evidence_chunk_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReviewReport:
    task_id: str
    project_id: str
    node_id: str
    review_type: str
    summary: str
    score: float
    issues: list[str] = field(default_factory=list)
    revision: int = 0


@dataclass(slots=True)
class ChatAssistResult:
    project_id: str
    node_id: str | None
    thread_id: str
    route: str
    reply: str
    review_bypassed: bool = False
    updated_node_id: str | None = None
    suggested_node_ids: list[str] = field(default_factory=list)
    suggested_options: list[dict[str, str]] = field(default_factory=list)
    guide_skip_document: str = ""
    revision: int = 0


@dataclass(slots=True)
class OutlineGuideResult:
    project_id: str
    questions: list[str] = field(default_factory=list)
    outline_markdown: str = ""
    chapter_beats: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class WorkflowClarifyResult:
    project_id: str
    questions: list[str] = field(default_factory=list)
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class WorkflowSyncResult:
    project_id: str
    background_markdown: str = ""
    must_confirm: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    search_requested: bool = False
    search_used: bool = False
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class OutlineDetailNode:
    title: str
    outline_markdown: str
    summary: str = ""


@dataclass(slots=True)
class OutlineDetailNodesResult:
    project_id: str
    nodes: list[OutlineDetailNode] = field(default_factory=list)
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class WorkflowDocsDraftResult:
    project_id: str
    assistant_message: str = ""
    constitution_markdown: str = ""
    clarify_markdown: str = ""
    specification_markdown: str = ""
    plan_markdown: str = ""
    diff_summary: str = ""
    written_keys: list[str] = field(default_factory=list)
    ignored_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClarificationQuestionResult:
    project_id: str
    clarification_id: str
    question_type: str
    question: str
    options: list[dict[str, str]] = field(default_factory=list)
    must_answer: bool = True
    timeout_sec: int = 120
    setting_proposal_status: str = "pending_confirmation"
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


class WorkflowState(TypedDict, total=False):
    task_id: str
    task_type: str
    project_id: str
    node_id: str
    token_budget: int
    style_hint: str
    branch_count: int
    workflow_mode: str
    tool_thread_id: str
    node: Any
    context_pack: ContextPack
    llm_route: dict[str, Any]
    prompt: str
    prompt_bundle: PromptBundle
    planner_prompt: str
    planner_prompt_bundle: PromptBundle
    planner_response: LLMResponse
    writer_prompt: str
    writer_prompt_bundle: PromptBundle
    writer_response: LLMResponse
    reviewer_prompt: str
    reviewer_prompt_bundle: PromptBundle
    reviewer_response: LLMResponse
    synthesizer_prompt: str
    synthesizer_prompt_bundle: PromptBundle
    agent_trace: dict[str, str]
    llm_response: LLMResponse


__all__ = [
    "BranchOption",
    "GenerateResult",
    "ChapterDraftResult",
    "ReviewReport",
    "ChatAssistResult",
    "OutlineGuideResult",
    "WorkflowClarifyResult",
    "WorkflowSyncResult",
    "OutlineDetailNode",
    "OutlineDetailNodesResult",
    "WorkflowDocsDraftResult",
    "ClarificationQuestionResult",
    "WorkflowState",
]
