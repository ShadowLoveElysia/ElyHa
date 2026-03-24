"""Workflow-doc state machine for clarify/constitution/specification/plan drafts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from elyha_core.services.ai_service import AIService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now

_DOC_KEYS = (
    "constitution_markdown",
    "clarify_markdown",
    "specification_markdown",
    "plan_markdown",
)


@dataclass(slots=True)
class WorkflowDocumentState:
    project_id: str
    workflow_mode: str = "original"
    workflow_stage: str = "idle"
    workflow_initialized: bool = False
    round_number: int = 0
    assistant_message: str = ""
    collected_inputs: dict[str, str] = field(default_factory=dict)
    clarify_questions: list[str] = field(default_factory=list)
    pending_docs: dict[str, str] = field(default_factory=dict)
    published_docs: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class WorkflowDocumentService:
    """Persist and drive the workflow-doc lifecycle."""

    def __init__(self, repository: SQLiteRepository, ai_service: AIService) -> None:
        self.repository = repository
        self.ai_service = ai_service

    def set_ai_service(self, service: AIService) -> None:
        self.ai_service = service

    def start_workflow(self, project_id: str, *, mode: str = "original") -> WorkflowDocumentState:
        self._ensure_project_exists(project_id)
        clean_mode = self._normalize_mode(mode)
        assistant = self.ai_service.generate_workflow_stage_reply(
            project_id,
            mode=clean_mode,
            stage="collect_constitution",
            collected_inputs={},
            clarify_questions=[],
        )
        state = WorkflowDocumentState(
            project_id=project_id,
            workflow_mode=clean_mode,
            workflow_stage="collect_constitution",
            workflow_initialized=False,
            round_number=0,
            assistant_message=assistant,
            collected_inputs={},
            clarify_questions=[],
            pending_docs=self._empty_docs(),
            published_docs=self._load_published_docs_from_project(project_id),
        )
        return self._persist_state(state)

    def start_workflow_auto(
        self,
        project_id: str,
        *,
        user_input: str,
        token_budget: int = 400,
    ) -> WorkflowDocumentState:
        self._ensure_project_exists(project_id)
        mode = self.ai_service.judge_workflow_mode(
            project_id,
            user_input=user_input,
            token_budget=token_budget,
        )
        return self.start_workflow(project_id, mode=mode)

    def get_state(self, project_id: str) -> WorkflowDocumentState:
        self._ensure_project_exists(project_id)
        existing = self.repository.get_workflow_doc_state(project_id)
        if existing is None:
            return WorkflowDocumentState(
                project_id=project_id,
                published_docs=self._load_published_docs_from_project(project_id),
                pending_docs=self._empty_docs(),
            )
        return self._state_from_payload(existing)

    def submit_stage_input(
        self,
        project_id: str,
        *,
        user_input: str,
        token_budget: int = 1000,
    ) -> WorkflowDocumentState:
        state = self.get_state(project_id)
        text = str(user_input or "").strip()
        if not text:
            raise ValueError("user_input cannot be empty")

        stage = state.workflow_stage
        if stage == "collect_constitution":
            state.collected_inputs["constitution_input"] = text
            state.workflow_stage = "collect_specification"
            state.assistant_message = self.ai_service.generate_workflow_stage_reply(
                project_id,
                mode=state.workflow_mode,
                stage=state.workflow_stage,
                collected_inputs=state.collected_inputs,
                clarify_questions=state.clarify_questions,
                token_budget=token_budget,
            )
            return self._persist_state(state)

        if stage == "collect_specification":
            state.collected_inputs["specification_input"] = text
            clarify = self.ai_service.guide_workflow_clarify(
                project_id,
                goal=state.collected_inputs.get("constitution_input", ""),
                sync_context=state.collected_inputs.get("specification_input", ""),
                specify=state.collected_inputs.get("specification_input", ""),
                constraints="",
                tone="",
                token_budget=max(600, token_budget),
            )
            questions = list(getattr(clarify, "questions", []) or [])
            state.clarify_questions = [str(item) for item in questions if str(item or "").strip()]
            state.workflow_stage = "collect_clarify"
            state.assistant_message = self.ai_service.generate_workflow_stage_reply(
                project_id,
                mode=state.workflow_mode,
                stage=state.workflow_stage,
                collected_inputs=state.collected_inputs,
                clarify_questions=state.clarify_questions,
                token_budget=token_budget,
            )
            return self._persist_state(state)

        if stage == "collect_clarify":
            state.collected_inputs["clarify_input"] = text
            state.workflow_stage = "collect_plan"
            state.assistant_message = self.ai_service.generate_workflow_stage_reply(
                project_id,
                mode=state.workflow_mode,
                stage=state.workflow_stage,
                collected_inputs=state.collected_inputs,
                clarify_questions=state.clarify_questions,
                token_budget=token_budget,
            )
            return self._persist_state(state)

        if stage == "collect_plan":
            state.collected_inputs["plan_input"] = text
            draft = self.ai_service.generate_workflow_documents(
                project_id,
                mode=state.workflow_mode,
                collected_inputs=state.collected_inputs,
                clarify_questions=state.clarify_questions,
                token_budget=max(1200, token_budget),
            )
            incoming_docs = self._docs_from_draft_result(draft)
            state.pending_docs = self._merge_docs(
                current=state.pending_docs,
                incoming=incoming_docs,
            )
            written = [
                str(item).strip()
                for item in list(getattr(draft, "written_keys", []) or [])
                if str(item).strip()
            ]
            if not written:
                written = [key for key, value in incoming_docs.items() if str(value or "").strip()]
            if not written:
                state.workflow_stage = "collect_plan"
                state.assistant_message = self._workflow_doc_message_from_result(draft)
                return self._persist_state(state)
            state.workflow_stage = "draft"
            state.round_number = 1
            state.assistant_message = self._workflow_doc_message_from_result(draft)
            return self._persist_state(state)

        if stage == "revise":
            state.collected_inputs["revise_input"] = text
            revised = self.ai_service.revise_workflow_documents(
                project_id,
                mode=state.workflow_mode,
                collected_inputs=state.collected_inputs,
                clarify_questions=state.clarify_questions,
                pending_docs=state.pending_docs,
                user_feedback=text,
                token_budget=max(1200, token_budget),
            )
            incoming_docs = self._docs_from_draft_result(revised)
            state.pending_docs = self._merge_docs(
                current=state.pending_docs,
                incoming=incoming_docs,
            )
            written = [
                str(item).strip()
                for item in list(getattr(revised, "written_keys", []) or [])
                if str(item).strip()
            ]
            if not written:
                written = [key for key, value in incoming_docs.items() if str(value or "").strip()]
            if not written:
                state.workflow_stage = "revise"
                state.assistant_message = self._workflow_doc_message_from_result(revised)
                return self._persist_state(state)
            state.workflow_stage = "confirm_2"
            state.round_number = 2
            state.assistant_message = self._workflow_doc_message_from_result(revised)
            return self._persist_state(state)

        raise ValueError(f"workflow stage does not accept input: {stage}")

    def confirm_round(self, project_id: str, *, round_number: int) -> WorkflowDocumentState:
        state = self.get_state(project_id)
        clean_round = max(1, int(round_number))
        if clean_round == 1 and state.workflow_stage == "draft":
            state.workflow_stage = "revise"
            state.round_number = 1
            state.assistant_message = self.ai_service.generate_workflow_stage_reply(
                project_id,
                mode=state.workflow_mode,
                stage="revise",
                collected_inputs=state.collected_inputs,
                clarify_questions=state.clarify_questions,
            )
            return self._persist_state(state)

        if clean_round == 2 and state.workflow_stage == "confirm_2":
            state.workflow_stage = "modal_confirm"
            state.round_number = 2
            state.assistant_message = self.ai_service.generate_workflow_stage_reply(
                project_id,
                mode=state.workflow_mode,
                stage="modal_confirm",
                collected_inputs=state.collected_inputs,
                clarify_questions=state.clarify_questions,
            )
            return self._persist_state(state)

        raise ValueError(f"cannot confirm round {clean_round} at stage {state.workflow_stage}")

    def publish_pending_docs(self, project_id: str) -> WorkflowDocumentState:
        state = self.get_state(project_id)
        if state.workflow_stage not in {"modal_confirm", "published"}:
            raise ValueError(f"cannot publish at stage {state.workflow_stage}")
        has_pending = any(str(state.pending_docs.get(key, "")).strip() for key in _DOC_KEYS)
        if not has_pending and state.workflow_stage != "published":
            raise ValueError("pending docs are empty")

        if has_pending:
            state.published_docs = dict(state.pending_docs)
            state.pending_docs = self._empty_docs()
            self._persist_published_docs_to_project(project_id, state.published_docs)

        state.workflow_initialized = True
        state.workflow_stage = "published"
        state.assistant_message = self.ai_service.generate_workflow_stage_reply(
            project_id,
            mode=state.workflow_mode,
            stage="published",
            collected_inputs=state.collected_inputs,
            clarify_questions=state.clarify_questions,
        )
        return self._persist_state(state)

    def _normalize_mode(self, mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized in {"sequel", "续写"}:
            return "sequel"
        return "original"

    def _ensure_project_exists(self, project_id: str) -> None:
        if self.repository.get_project(project_id) is None:
            raise KeyError(f"project not found: {project_id}")

    def _persist_state(self, state: WorkflowDocumentState) -> WorkflowDocumentState:
        payload = self.repository.upsert_workflow_doc_state(
            state.project_id,
            workflow_mode=state.workflow_mode,
            workflow_stage=state.workflow_stage,
            workflow_initialized=state.workflow_initialized,
            round_number=state.round_number,
            assistant_message=state.assistant_message,
            collected_inputs=state.collected_inputs,
            clarify_questions=state.clarify_questions,
            pending_docs=state.pending_docs,
            published_docs=state.published_docs,
        )
        return self._state_from_payload(payload)

    def _state_from_payload(self, payload: dict[str, Any]) -> WorkflowDocumentState:
        return WorkflowDocumentState(
            project_id=str(payload.get("project_id", "") or ""),
            workflow_mode=str(payload.get("workflow_mode", "original") or "original"),
            workflow_stage=str(payload.get("workflow_stage", "idle") or "idle"),
            workflow_initialized=bool(payload.get("workflow_initialized", False)),
            round_number=max(0, int(payload.get("round_number", 0) or 0)),
            assistant_message=str(payload.get("assistant_message", "") or ""),
            collected_inputs={
                str(k): str(v or "")
                for k, v in dict(payload.get("collected_inputs", {}) or {}).items()
            },
            clarify_questions=[
                str(item)
                for item in list(payload.get("clarify_questions", []) or [])
                if str(item or "").strip()
            ],
            pending_docs={
                **self._empty_docs(),
                **{str(k): str(v or "") for k, v in dict(payload.get("pending_docs", {}) or {}).items()},
            },
            published_docs={
                **self._empty_docs(),
                **{str(k): str(v or "") for k, v in dict(payload.get("published_docs", {}) or {}).items()},
            },
            created_at=str(payload.get("created_at", "") or ""),
            updated_at=str(payload.get("updated_at", "") or ""),
        )

    def _docs_from_draft_result(self, draft: Any) -> dict[str, str]:
        return {
            "constitution_markdown": str(getattr(draft, "constitution_markdown", "") or "").strip(),
            "clarify_markdown": str(getattr(draft, "clarify_markdown", "") or "").strip(),
            "specification_markdown": str(getattr(draft, "specification_markdown", "") or "").strip(),
            "plan_markdown": str(getattr(draft, "plan_markdown", "") or "").strip(),
        }

    def _merge_docs(self, *, current: dict[str, str], incoming: dict[str, str]) -> dict[str, str]:
        merged = dict(self._empty_docs())
        for key in _DOC_KEYS:
            base_value = str(current.get(key, "") or "").strip()
            incoming_value = str(incoming.get(key, "") or "").strip()
            merged[key] = incoming_value if incoming_value else base_value
        return merged

    def _workflow_doc_message_from_result(self, draft: Any) -> str:
        base = str(getattr(draft, "assistant_message", "") or "").strip()
        written = [
            str(item).strip()
            for item in list(getattr(draft, "written_keys", []) or [])
            if str(item).strip()
        ]
        ignored = [
            str(item).strip()
            for item in list(getattr(draft, "ignored_keys", []) or [])
            if str(item).strip()
        ]
        parts: list[str] = []
        if base:
            parts.append(base)
        if written:
            parts.append("written_keys: " + ", ".join(written))
        if ignored:
            parts.append("ignored_keys: " + ", ".join(ignored))
        return "\n".join(parts).strip()

    def _empty_docs(self) -> dict[str, str]:
        return {key: "" for key in _DOC_KEYS}

    def _load_published_docs_from_project(self, project_id: str) -> dict[str, str]:
        project = self.repository.get_project(project_id)
        if project is None:
            return self._empty_docs()
        settings = project.settings
        return {
            "constitution_markdown": str(getattr(settings, "constitution_markdown", "") or "").strip(),
            "clarify_markdown": str(getattr(settings, "clarify_markdown", "") or "").strip(),
            "specification_markdown": str(getattr(settings, "specification_markdown", "") or "").strip(),
            "plan_markdown": str(getattr(settings, "plan_markdown", "") or "").strip(),
        }

    def _persist_published_docs_to_project(self, project_id: str, docs: dict[str, str]) -> None:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")
        project.settings.constitution_markdown = str(docs.get("constitution_markdown", "") or "").strip()
        project.settings.clarify_markdown = str(docs.get("clarify_markdown", "") or "").strip()
        project.settings.specification_markdown = str(docs.get("specification_markdown", "") or "").strip()
        project.settings.plan_markdown = str(docs.get("plan_markdown", "") or "").strip()
        project.updated_at = utc_now()
        project.active_revision += 1
        self.repository.update_project(project)
