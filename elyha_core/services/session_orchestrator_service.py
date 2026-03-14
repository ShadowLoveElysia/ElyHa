"""Single-agent HITL session orchestration service."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from elyha_core.services.graph_service import GraphService
from elyha_core.services.setting_proposal_service import SettingProposalService
from elyha_core.services.state_service import StateService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id
from elyha_core.utils.text_splitter import split_text_by_chars

if TYPE_CHECKING:
    from elyha_core.services.ai_service import AIService, ChapterDraftResult
else:
    AIService = Any  # type: ignore[misc,assignment]
    ChapterDraftResult = Any  # type: ignore[misc,assignment]


class SessionOrchestratorService:
    """Coordinate generation/correction/clarification loops for a single thread."""

    STATUS_RUNNING_GENERATION = "RUNNING_GENERATION"
    STATUS_AWAITING_CONFIRM = "AWAITING_CONFIRM"
    STATUS_AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    STATUS_AWAITING_SETTING_PROPOSAL_CONFIRM = "AWAITING_SETTING_PROPOSAL_CONFIRM"
    STATUS_AWAITING_CHAPTER_REVIEW = "AWAITING_CHAPTER_REVIEW"
    STATUS_RUNNING_CORRECTION = "RUNNING_CORRECTION"
    STATUS_AWAITING_CORRECTION_CONFIRM = "AWAITING_CORRECTION_CONFIRM"
    STATUS_PAUSED_BY_USER = "PAUSED_BY_USER"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"

    def __init__(
        self,
        repository: SQLiteRepository,
        graph_service: GraphService,
        ai_service: AIService,
        state_service: StateService,
        setting_proposal_service: SettingProposalService,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.ai_service = ai_service
        self.state_service = state_service
        self.setting_proposal_service = setting_proposal_service
        if hasattr(self.ai_service, "set_setting_proposal_service"):
            self.ai_service.set_setting_proposal_service(self.setting_proposal_service)

    def set_ai_service(self, ai_service: AIService) -> None:
        self.ai_service = ai_service
        if hasattr(self.ai_service, "set_setting_proposal_service"):
            self.ai_service.set_setting_proposal_service(self.setting_proposal_service)

    def start_session(
        self,
        *,
        project_id: str,
        node_id: str,
        mode: str = "single_agent",
        token_budget: int = 2200,
        style_hint: str = "",
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_project_and_node(project_id, node_id)
        clean_thread_id = str(thread_id or "").strip() or generate_id("thread")
        clean_mode = str(mode or "").strip() or "single_agent"
        now_iso = utc_now().isoformat()
        try:
            with self.repository.store.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_sessions(
                        thread_id, project_id, node_id, mode, status, state_version,
                        token_budget, style_hint, pending_content, pending_meta_json,
                        pending_clarification_json, latest_clarification_id,
                        latest_setting_proposal_id, last_committed_revision, last_error,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, '', '{}', '{}', '', '', 0, '', ?, ?)
                    """,
                    (
                        clean_thread_id,
                        project_id,
                        node_id,
                        clean_mode,
                        self.STATUS_RUNNING_GENERATION,
                        max(1, int(token_budget)),
                        str(style_hint or "").strip(),
                        now_iso,
                        now_iso,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"session already exists: {clean_thread_id}") from exc
        session = self._run_generation_cycle(
            clean_thread_id,
            run_status=self.STATUS_RUNNING_GENERATION,
            wait_status=self.STATUS_AWAITING_CONFIRM,
            correction_text="",
            base_content="",
        )
        return {
            "thread_id": clean_thread_id,
            "session": session,
        }

    def resume_session(self, thread_id: str) -> dict[str, Any]:
        return self.get_session_state(thread_id)

    def get_session_state(self, thread_id: str) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        retry_summary = self._process_state_update_outbox(
            project_id=str(session["project_id"]),
            thread_id=str(session["thread_id"]),
            limit=2,
        )
        proposal_id = str(session.get("latest_setting_proposal_id", "")).strip()
        if proposal_id:
            try:
                session["latest_setting_proposal"] = self.setting_proposal_service.get_proposal(proposal_id)
            except KeyError:
                session["latest_setting_proposal"] = None
        else:
            session["latest_setting_proposal"] = None
        session["pending_state_update_count"] = int(retry_summary.get("pending_count", 0))
        session["state_update_retry_summary"] = retry_summary
        return session

    def cancel_session(self, thread_id: str) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        updated = self._transition_session(
            session,
            expected_version=int(session["state_version"]),
            status=self.STATUS_PAUSED_BY_USER,
            last_error="cancelled_by_user",
        )
        return {
            "thread_id": str(updated["thread_id"]),
            "session": updated,
        }

    def request_clarification_question(
        self,
        *,
        thread_id: str,
        context: str = "",
        token_budget: int = 900,
    ) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        context_text = str(context or "").strip()
        if not context_text:
            context_text = str(session.get("pending_content", ""))[-1200:]
        question = self.ai_service.generate_clarification_question(
            str(session["project_id"]),
            node_id=str(session["node_id"]),
            context=context_text,
            token_budget=max(200, int(token_budget)),
        )
        payload = {
            "clarification_id": question.clarification_id,
            "question_type": question.question_type,
            "question": question.question,
            "options": question.options,
            "must_answer": question.must_answer,
            "timeout_sec": question.timeout_sec,
            "setting_proposal_status": question.setting_proposal_status,
            "provider": question.provider,
            "prompt_tokens": question.prompt_tokens,
            "completion_tokens": question.completion_tokens,
        }
        updated = self._transition_session(
            session,
            expected_version=int(session["state_version"]),
            status=self.STATUS_AWAITING_CLARIFICATION,
            pending_clarification=payload,
            latest_clarification_id=question.clarification_id,
            last_error="",
        )
        return {
            "thread_id": str(updated["thread_id"]),
            "session": updated,
            "clarification_request": payload,
        }

    def submit_clarification_answer(
        self,
        *,
        thread_id: str,
        clarification_id: str,
        decision_id: str,
        selected_option: str = "",
        answer_text: str = "",
    ) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        clean_option = str(selected_option or "").strip()
        clean_answer = str(answer_text or "").strip()
        if not clean_option and not clean_answer:
            raise ValueError("selected_option and answer_text cannot both be empty")
        if clean_option == "other" and not clean_answer:
            raise ValueError("answer_text is required when selected_option=other")

        cleaned_clarification_id = str(clarification_id or "").strip()
        latest_clarification_id = str(session.get("latest_clarification_id", "")).strip()
        if latest_clarification_id and cleaned_clarification_id and latest_clarification_id != cleaned_clarification_id:
            raise ValueError("clarification_id does not match latest clarification request")

        can_execute, duplicate_payload = self._claim_decision(
            thread_id=str(session["thread_id"]),
            decision_id=decision_id,
            action="submit_clarification_answer",
            payload={
                "clarification_id": cleaned_clarification_id,
                "selected_option": clean_option,
                "answer_text": clean_answer,
            },
            state_before=str(session["status"]),
            version_before=int(session["state_version"]),
        )
        if not can_execute and duplicate_payload is not None:
            return duplicate_payload

        pending_question = session.get("pending_clarification")
        question_type = ""
        question_text = ""
        if isinstance(pending_question, dict):
            question_type = str(pending_question.get("question_type") or "").strip()
            question_text = str(pending_question.get("question") or "").strip()

        proposal = self.setting_proposal_service.create_from_clarification(
            project_id=str(session["project_id"]),
            node_id=str(session["node_id"]),
            thread_id=str(session["thread_id"]),
            clarification_id=cleaned_clarification_id or latest_clarification_id,
            selected_option=clean_option,
            answer_text=clean_answer,
            question_type=question_type or "other",
            question=question_text,
            target_scope="project",
            proposal_type=question_type or "clarification_answer",
        )
        latest = self._load_session_or_raise(str(session["thread_id"]))
        updated = self._transition_session(
            latest,
            expected_version=int(latest["state_version"]),
            status=self.STATUS_AWAITING_SETTING_PROPOSAL_CONFIRM,
            latest_setting_proposal_id=str(proposal["id"]),
            last_error="",
        )
        response = {
            "thread_id": str(updated["thread_id"]),
            "session": updated,
            "setting_proposal": proposal,
        }
        self._finalize_decision(
            thread_id=str(updated["thread_id"]),
            decision_id=decision_id,
            state_after=str(updated["status"]),
            version_after=int(updated["state_version"]),
            response_payload=response,
        )
        return response

    def review_setting_proposal(
        self,
        *,
        thread_id: str,
        proposal_id: str,
        action: str,
        reviewer: str = "",
        note: str = "",
        decision_id: str,
        expected_state_version: int | None = None,
    ) -> dict[str, Any]:
        normalized = str(action or "").strip().lower()
        if normalized in {"approve", "approved"}:
            mapped_action = "approve_setting_update"
        elif normalized in {"reject", "rejected"}:
            mapped_action = "reject_setting_update"
        else:
            raise ValueError("action must be approve/approved/reject/rejected")
        return self.submit_decision(
            thread_id=thread_id,
            action=mapped_action,
            decision_id=decision_id,
            expected_state_version=expected_state_version,
            payload={
                "proposal_id": proposal_id,
                "reviewer": reviewer,
                "note": note,
            },
        )

    def list_setting_proposals(
        self,
        *,
        thread_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        session = self._load_session_or_raise(thread_id)
        status_filter = str(status or "").strip() or None
        if status_filter:
            return self.setting_proposal_service.list_proposals(
                project_id=str(session["project_id"]),
                thread_id=str(session["thread_id"]),
                status=status_filter,
            )
        return self.setting_proposal_service.list_proposals(
            project_id=str(session["project_id"]),
            thread_id=str(session["thread_id"]),
        )

    def review_setting_proposals_batch(
        self,
        *,
        thread_id: str,
        action: str,
        proposal_ids: list[str] | None = None,
        reviewer: str = "",
        note: str = "",
        decision_id: str,
        expected_state_version: int | None = None,
    ) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        if expected_state_version is not None and int(session["state_version"]) != int(expected_state_version):
            raise ValueError("expected_state_version mismatch")
        normalized = str(action or "").strip().lower()
        if normalized not in {"approve", "approved", "reject", "rejected"}:
            raise ValueError("action must be approve/approved/reject/rejected")
        approved = normalized in {"approve", "approved"}
        cleaned_ids = self._normalize_hunk_ids(proposal_ids or [])

        can_execute, duplicate_payload = self._claim_decision(
            thread_id=str(session["thread_id"]),
            decision_id=decision_id,
            action="review_setting_proposals_batch",
            payload={
                "action": "approved" if approved else "rejected",
                "proposal_ids": cleaned_ids,
                "reviewer": str(reviewer or "").strip(),
                "note": str(note or "").strip(),
            },
            state_before=str(session["status"]),
            version_before=int(session["state_version"]),
        )
        if not can_execute and duplicate_payload is not None:
            return duplicate_payload

        targets: list[dict[str, Any]]
        if cleaned_ids:
            targets = []
            for proposal_id in cleaned_ids:
                proposal = self.setting_proposal_service.get_proposal(proposal_id)
                if str(proposal.get("thread_id", "")).strip() != str(session["thread_id"]):
                    raise ValueError(f"proposal does not belong to thread: {proposal_id}")
                targets.append(proposal)
        else:
            targets = self.setting_proposal_service.list_proposals(
                project_id=str(session["project_id"]),
                thread_id=str(session["thread_id"]),
                status="pending_review",
            )

        processed: list[dict[str, Any]] = []
        for proposal in targets:
            proposal_id = str(proposal.get("id", "")).strip()
            if not proposal_id:
                continue
            reviewed = self.setting_proposal_service.review_proposal(
                proposal_id,
                action="approved" if approved else "rejected",
                reviewer=reviewer,
                note=note,
            )
            if approved:
                reviewed = self.setting_proposal_service.apply_proposal(
                    proposal_id,
                    reviewer=reviewer,
                    note=note,
                )
            processed.append(reviewed)

        latest = self._load_session_or_raise(str(session["thread_id"]))
        response = {
            "thread_id": str(latest["thread_id"]),
            "session": latest,
            "setting_proposals": processed,
            "review_action": "approved" if approved else "rejected",
            "review_count": len(processed),
        }
        self._finalize_decision(
            thread_id=str(latest["thread_id"]),
            decision_id=decision_id,
            state_after=str(latest["status"]),
            version_after=int(latest["state_version"]),
            response_payload=response,
        )
        return response

    def submit_diff_review(
        self,
        *,
        thread_id: str,
        diff_id: str,
        decision_id: str,
        accepted_hunk_ids: list[str] | None = None,
        rejected_hunk_ids: list[str] | None = None,
        expected_base_revision: int | None = None,
        expected_base_hash: str | None = None,
        expected_state_version: int | None = None,
    ) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        if expected_state_version is not None and int(session["state_version"]) != int(expected_state_version):
            raise ValueError("expected_state_version mismatch")
        if str(session.get("status", "")) != self.STATUS_AWAITING_CORRECTION_CONFIRM:
            raise ValueError("current status does not support diff review")

        accepted = self._normalize_hunk_ids(accepted_hunk_ids or [])
        rejected = self._normalize_hunk_ids(rejected_hunk_ids or [])
        overlap = set(accepted) & set(rejected)
        if overlap:
            raise ValueError(f"accepted_hunk_ids and rejected_hunk_ids overlap: {sorted(overlap)}")

        can_execute, duplicate_payload = self._claim_decision(
            thread_id=str(session["thread_id"]),
            decision_id=decision_id,
            action="submit_diff_review",
            payload={
                "diff_id": str(diff_id or "").strip(),
                "accepted_hunk_ids": accepted,
                "rejected_hunk_ids": rejected,
                "expected_base_revision": expected_base_revision,
                "expected_base_hash": str(expected_base_hash or "").strip(),
            },
            state_before=str(session["status"]),
            version_before=int(session["state_version"]),
        )
        if not can_execute and duplicate_payload is not None:
            return duplicate_payload

        pending_meta = session.get("pending_meta")
        if not isinstance(pending_meta, dict):
            pending_meta = {}
        diff_patch = pending_meta.get("diff_patch")
        if not isinstance(diff_patch, dict):
            raise ValueError("diff_patch is missing in pending correction draft")
        clean_diff_id = str(diff_id or "").strip()
        patch_diff_id = str(diff_patch.get("diff_id") or "").strip()
        if clean_diff_id and patch_diff_id and clean_diff_id != patch_diff_id:
            raise ValueError("diff_id does not match pending diff")
        base_revision = int(diff_patch.get("base_revision") or 0)
        base_hash = str(diff_patch.get("base_content_hash") or "").strip()
        if expected_base_revision is not None and base_revision != int(expected_base_revision):
            raise ValueError("expected_base_revision mismatch")
        if expected_base_hash is not None and str(expected_base_hash).strip() and base_hash != str(expected_base_hash).strip():
            raise ValueError("expected_base_hash mismatch")

        project_revision = self._project_revision(str(session["project_id"]))
        if base_revision and project_revision != base_revision:
            raise ValueError("diff base_revision mismatch with current project revision; regenerate diff required")

        base_content = str(pending_meta.get("diff_base_content") or "")
        if self._text_hash(base_content) != base_hash:
            raise ValueError("diff base_content_hash mismatch; regenerate diff required")

        apply_result = self._apply_diff_patch(
            base_content=base_content,
            diff_patch=diff_patch,
            accepted_hunk_ids=accepted,
            rejected_hunk_ids=rejected,
        )
        updated_meta = dict(pending_meta)
        updated_meta["diff_apply_status"] = apply_result["status"]
        updated_meta["diff_accepted_hunk_ids"] = apply_result["accepted_hunk_ids"]
        updated_meta["diff_rejected_hunk_ids"] = apply_result["rejected_hunk_ids"]
        updated_meta["diff_applied_hunk_ids"] = apply_result["applied_hunk_ids"]
        updated_meta["diff_applied_at"] = utc_now().isoformat()
        updated_meta["diff_result_content_hash"] = self._text_hash(str(apply_result["content"]))
        updated_meta["diff_apply_message"] = apply_result["message"]

        latest = self._load_session_or_raise(str(session["thread_id"]))
        updated = self._transition_session(
            latest,
            expected_version=int(latest["state_version"]),
            status=self.STATUS_AWAITING_CORRECTION_CONFIRM,
            pending_content=str(apply_result["content"]),
            pending_meta=updated_meta,
            last_error="",
        )
        response = {
            "thread_id": str(updated["thread_id"]),
            "session": updated,
            "diff_review": {
                "diff_id": patch_diff_id or clean_diff_id,
                "status": apply_result["status"],
                "message": apply_result["message"],
                "applied_hunk_ids": apply_result["applied_hunk_ids"],
                "accepted_hunk_ids": apply_result["accepted_hunk_ids"],
                "rejected_hunk_ids": apply_result["rejected_hunk_ids"],
                "base_revision": base_revision,
                "base_content_hash": base_hash,
            },
        }
        self._finalize_decision(
            thread_id=str(updated["thread_id"]),
            decision_id=decision_id,
            state_after=str(updated["status"]),
            version_after=int(updated["state_version"]),
            response_payload=response,
        )
        return response

    def submit_decision(
        self,
        *,
        thread_id: str,
        action: str,
        decision_id: str,
        expected_state_version: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        if expected_state_version is not None and int(session["state_version"]) != int(expected_state_version):
            raise ValueError("expected_state_version mismatch")

        normalized_action = str(action or "").strip().lower()
        payload_obj = payload if isinstance(payload, dict) else {}
        can_execute, duplicate_payload = self._claim_decision(
            thread_id=str(session["thread_id"]),
            decision_id=decision_id,
            action=normalized_action,
            payload=payload_obj,
            state_before=str(session["status"]),
            version_before=int(session["state_version"]),
        )
        if not can_execute and duplicate_payload is not None:
            return duplicate_payload

        response: dict[str, Any]
        if normalized_action in {"confirm_yes", "yes"}:
            response = self._handle_confirm_action(
                session,
                persist_rule=False,
                payload=payload_obj,
            )
        elif normalized_action in {"confirm_yes_persist_rule", "yes_persist_rule"}:
            response = self._handle_confirm_action(
                session,
                persist_rule=True,
                payload=payload_obj,
            )
        elif normalized_action in {"correct", "correction"}:
            response = self._handle_correction_action(session, payload=payload_obj)
        elif normalized_action in {"stop", "pause"}:
            response = self._handle_stop_action(session)
        elif normalized_action == "approve_setting_update":
            response = self._handle_setting_proposal_action(
                session,
                payload=payload_obj,
                approved=True,
            )
        elif normalized_action == "reject_setting_update":
            response = self._handle_setting_proposal_action(
                session,
                payload=payload_obj,
                approved=False,
            )
        elif normalized_action in {"defer_setting_update", "continue_without_setting_apply"}:
            response = self._handle_setting_proposal_defer(session)
        elif normalized_action in {"satisfied", "chapter_satisfied"}:
            response = self._handle_chapter_satisfied(session)
        elif normalized_action in {"unsatisfied", "chapter_unsatisfied"}:
            response = self._handle_chapter_unsatisfied(session, payload=payload_obj)
        else:
            raise ValueError(f"unsupported decision action: {normalized_action}")

        final_session = response.get("session")
        if not isinstance(final_session, dict):
            final_session = self._load_session_or_raise(thread_id)
            response["session"] = final_session
        self._finalize_decision(
            thread_id=str(session["thread_id"]),
            decision_id=decision_id,
            state_after=str(final_session["status"]),
            version_after=int(final_session["state_version"]),
            response_payload=response,
        )
        return response

    def _handle_confirm_action(
        self,
        session: dict[str, Any],
        *,
        persist_rule: bool,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        status = str(session.get("status", ""))
        if status not in {self.STATUS_AWAITING_CONFIRM, self.STATUS_AWAITING_CORRECTION_CONFIRM}:
            raise ValueError(f"current status does not support confirm: {status}")

        directive_text = ""
        if persist_rule:
            directive_text = (
                str(payload.get("directive") or "").strip()
                or str(payload.get("global_directive") or "").strip()
                or str(payload.get("rule_text") or "").strip()
            )
            if not directive_text:
                raise ValueError("directive text is required for confirm_yes_persist_rule")

        commit_result = self._commit_pending_draft(
            thread_id=str(session["thread_id"]),
            directive_text=directive_text,
        )
        next_session = self._run_generation_cycle(
            str(session["thread_id"]),
            run_status=self.STATUS_RUNNING_GENERATION,
            wait_status=self.STATUS_AWAITING_CONFIRM,
            correction_text="",
            base_content="",
        )
        return {
            "thread_id": str(next_session["thread_id"]),
            "session": next_session,
            "commit": commit_result,
        }

    def _handle_correction_action(
        self,
        session: dict[str, Any],
        *,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        status = str(session.get("status", ""))
        if status not in {self.STATUS_AWAITING_CONFIRM, self.STATUS_AWAITING_CHAPTER_REVIEW}:
            raise ValueError(f"current status does not support correction: {status}")
        correction_text = (
            str(payload.get("correction") or "").strip()
            or str(payload.get("user_correction") or "").strip()
            or str(payload.get("message") or "").strip()
        )
        if not correction_text:
            raise ValueError("correction text cannot be empty")
        base_content = str(session.get("pending_content", "")).strip()
        updated = self._run_generation_cycle(
            str(session["thread_id"]),
            run_status=self.STATUS_RUNNING_CORRECTION,
            wait_status=self.STATUS_AWAITING_CORRECTION_CONFIRM,
            correction_text=correction_text,
            base_content=base_content,
        )
        return {
            "thread_id": str(updated["thread_id"]),
            "session": updated,
        }

    def _handle_stop_action(self, session: dict[str, Any]) -> dict[str, Any]:
        updated = self._transition_session(
            session,
            expected_version=int(session["state_version"]),
            status=self.STATUS_PAUSED_BY_USER,
            last_error="paused_by_user",
        )
        return {
            "thread_id": str(updated["thread_id"]),
            "session": updated,
        }

    def _handle_setting_proposal_action(
        self,
        session: dict[str, Any],
        *,
        payload: dict[str, Any],
        approved: bool,
    ) -> dict[str, Any]:
        status = str(session.get("status", ""))
        if status != self.STATUS_AWAITING_SETTING_PROPOSAL_CONFIRM:
            raise ValueError(f"current status does not support setting proposal review: {status}")
        proposal_id = (
            str(payload.get("proposal_id") or "").strip()
            or str(session.get("latest_setting_proposal_id") or "").strip()
        )
        if not proposal_id:
            raise ValueError("proposal_id cannot be empty")
        reviewer = str(payload.get("reviewer") or "").strip()
        note = str(payload.get("note") or "").strip()
        action = "approved" if approved else "rejected"
        reviewed = self.setting_proposal_service.review_proposal(
            proposal_id,
            action=action,
            reviewer=reviewer,
            note=note,
        )
        applied = None
        if approved:
            applied = self.setting_proposal_service.apply_proposal(
                proposal_id,
                reviewer=reviewer,
                note=note,
            )
        next_session = self._run_generation_cycle(
            str(session["thread_id"]),
            run_status=self.STATUS_RUNNING_GENERATION,
            wait_status=self.STATUS_AWAITING_CONFIRM,
            correction_text="",
            base_content="",
        )
        return {
            "thread_id": str(next_session["thread_id"]),
            "session": next_session,
            "setting_proposal": applied if approved else reviewed,
        }

    def _handle_setting_proposal_defer(self, session: dict[str, Any]) -> dict[str, Any]:
        status = str(session.get("status", ""))
        if status != self.STATUS_AWAITING_SETTING_PROPOSAL_CONFIRM:
            raise ValueError(f"current status does not support proposal defer: {status}")
        deferred_proposal_id = str(session.get("latest_setting_proposal_id") or "").strip()
        next_session = self._run_generation_cycle(
            str(session["thread_id"]),
            run_status=self.STATUS_RUNNING_GENERATION,
            wait_status=self.STATUS_AWAITING_CONFIRM,
            correction_text="",
            base_content="",
        )
        return {
            "thread_id": str(next_session["thread_id"]),
            "session": next_session,
            "deferred_setting_proposal_id": deferred_proposal_id,
        }

    def _handle_chapter_satisfied(self, session: dict[str, Any]) -> dict[str, Any]:
        status = str(session.get("status", ""))
        if status != self.STATUS_AWAITING_CHAPTER_REVIEW:
            raise ValueError(f"current status does not support chapter completion: {status}")
        updated = self._transition_session(
            session,
            expected_version=int(session["state_version"]),
            status=self.STATUS_COMPLETED,
            last_error="",
        )
        return {"thread_id": str(updated["thread_id"]), "session": updated}

    def _handle_chapter_unsatisfied(
        self,
        session: dict[str, Any],
        *,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        status = str(session.get("status", ""))
        if status != self.STATUS_AWAITING_CHAPTER_REVIEW:
            raise ValueError(f"current status does not support chapter unsatisfied: {status}")
        correction_text = (
            str(payload.get("correction") or "").strip()
            or str(payload.get("message") or "").strip()
        )
        if not correction_text:
            correction_text = "继续修订并提升章节完成度。"
        updated = self._run_generation_cycle(
            str(session["thread_id"]),
            run_status=self.STATUS_RUNNING_CORRECTION,
            wait_status=self.STATUS_AWAITING_CORRECTION_CONFIRM,
            correction_text=correction_text,
            base_content=str(session.get("pending_content", "")),
        )
        return {"thread_id": str(updated["thread_id"]), "session": updated}

    def _run_generation_cycle(
        self,
        thread_id: str,
        *,
        run_status: str,
        wait_status: str,
        correction_text: str,
        base_content: str,
    ) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        running = self._transition_session(
            session,
            expected_version=int(session["state_version"]),
            status=run_status,
            last_error="",
        )
        try:
            retry_summary = self._process_state_update_outbox(
                project_id=str(running["project_id"]),
                thread_id=str(running["thread_id"]),
                limit=2,
            )
            base_revision = self._project_revision(str(running["project_id"]))
            if correction_text.strip():
                draft = self.ai_service.generate_chapter_correction_draft(
                    str(running["project_id"]),
                    str(running["node_id"]),
                    user_correction=correction_text,
                    base_content=str(base_content or ""),
                    token_budget=max(1, int(running.get("token_budget", 2200))),
                    tool_thread_id=thread_id,
                )
            else:
                draft = self.ai_service.generate_chapter_draft(
                    str(running["project_id"]),
                    str(running["node_id"]),
                    token_budget=max(1, int(running.get("token_budget", 2200))),
                    style_hint=str(running.get("style_hint", "")),
                    workflow_mode=str(running.get("mode", "single_agent")),
                    tool_thread_id=thread_id,
                )
            self._persist_agent_loop_audits(
                thread_id=thread_id,
                draft=draft,
            )
            pending_meta = self._draft_to_meta(draft)
            pending_meta["agent_loop_rounds_count"] = len(getattr(draft, "agent_loop_rounds", []) or [])
            pending_meta["agent_tool_calls_count"] = len(getattr(draft, "agent_tool_calls", []) or [])
            pending_meta["chapter_done_evaluation"] = self._build_chapter_done_evaluation(
                session=running,
                draft=draft,
                correction_mode=bool(correction_text.strip()),
            )
            pending_meta["state_update_retry_summary"] = retry_summary
            tool_setting_proposal_ids = self._extract_tool_setting_proposal_ids(draft)
            if tool_setting_proposal_ids:
                pending_meta["tool_setting_proposal_ids"] = tool_setting_proposal_ids
            target_wait_status = wait_status
            latest_setting_proposal_id: str | None = None
            if tool_setting_proposal_ids:
                latest_setting_proposal_id = tool_setting_proposal_ids[-1]
                if not correction_text.strip():
                    target_wait_status = self.STATUS_AWAITING_SETTING_PROPOSAL_CONFIRM
            if correction_text.strip():
                llm_diff_patch = getattr(draft, "diff_patch", None)
                if isinstance(llm_diff_patch, dict) and llm_diff_patch.get("hunks"):
                    diff_patch = self._normalize_llm_diff_patch(
                        thread_id=thread_id,
                        base_revision=base_revision,
                        base_content=str(base_content or ""),
                        revised_content=str(draft.content),
                        llm_patch=llm_diff_patch,
                    )
                    pending_meta["diff_source"] = "llm"
                else:
                    diff_patch = self._build_diff_patch(
                        thread_id=thread_id,
                        base_revision=base_revision,
                        base_content=str(base_content or ""),
                        revised_content=str(draft.content),
                    )
                    pending_meta["diff_source"] = "server_fallback"
                pending_meta["diff_patch"] = diff_patch
                pending_meta["diff_base_content"] = str(base_content or "")
                pending_meta["diff_apply_status"] = "pending_review"
            else:
                evaluation = pending_meta.get("chapter_done_evaluation")
                if isinstance(evaluation, dict) and bool(evaluation.get("review_ready")):
                    target_wait_status = self.STATUS_AWAITING_CHAPTER_REVIEW
            latest = self._load_session_or_raise(thread_id)
            updated = self._transition_session(
                latest,
                expected_version=int(latest["state_version"]),
                status=target_wait_status,
                pending_content=draft.content,
                pending_meta=pending_meta,
                pending_clarification={},
                latest_clarification_id="",
                latest_setting_proposal_id=latest_setting_proposal_id,
                last_error="",
            )
            return updated
        except Exception as exc:
            failed_session = self._load_session_or_raise(thread_id)
            self._transition_session(
                failed_session,
                expected_version=int(failed_session["state_version"]),
                status=self.STATUS_FAILED,
                last_error=str(exc),
            )
            raise

    def _persist_agent_loop_audits(self, *, thread_id: str, draft: ChapterDraftResult) -> None:
        rounds = getattr(draft, "agent_loop_rounds", [])
        calls = getattr(draft, "agent_tool_calls", [])
        metrics_payload = getattr(draft, "agent_loop_metrics", {})
        if not isinstance(rounds, list):
            rounds = []
        if not isinstance(calls, list):
            calls = []
        if not isinstance(metrics_payload, dict):
            metrics_payload = {}
        if rounds:
            self.repository.create_agent_loop_rounds(thread_id, rounds)
        if calls:
            self.repository.create_agent_tool_calls(thread_id, calls)
        if metrics_payload:
            task_type = "generate_chapter_correction_draft" if bool(getattr(draft, "diff_patch", {})) else "generate_chapter"
            agent = "single"
            if rounds:
                first_round = rounds[0] if isinstance(rounds[0], dict) else {}
                task_type = str(first_round.get("task_type") or task_type)
                agent = str(first_round.get("agent") or agent)
            self.repository.create_agent_loop_metrics(
                thread_id,
                [
                    {
                        "task_type": task_type,
                        "agent": agent,
                        "metrics": metrics_payload,
                        "created_at": utc_now().isoformat(),
                    }
                ],
            )

    def _commit_pending_draft(
        self,
        *,
        thread_id: str,
        directive_text: str = "",
    ) -> dict[str, Any]:
        session = self._load_session_or_raise(thread_id)
        content = str(session.get("pending_content", "")).strip()
        if not content:
            raise ValueError("pending_content is empty, nothing to commit")
        project_id = str(session["project_id"])
        node_id = str(session["node_id"])

        node = self.graph_service.get_node(project_id, node_id)
        metadata = node.metadata.copy() if isinstance(node.metadata, dict) else {}
        pending_meta = session.get("pending_meta")
        metadata_patch = {}
        if isinstance(pending_meta, dict):
            raw_patch = pending_meta.get("node_metadata_patch")
            if isinstance(raw_patch, dict):
                metadata_patch = {str(k): v for k, v in raw_patch.items()}
        metadata.update(metadata_patch)
        metadata["content"] = content
        metadata["summary"] = content[:200]
        self.graph_service.update_node(
            project_id,
            node_id,
            {
                "status": "generated",
                "metadata": metadata,
            },
        )
        self.repository.replace_node_chunks(node_id, split_text_by_chars(content))
        if str(directive_text or "").strip():
            self._append_global_directive(project_id, str(directive_text or "").strip())

        revision = self._project_revision(project_id)
        state_sync = self._sync_state_after_commit(
            project_id=project_id,
            node_id=node_id,
            thread_id=thread_id,
            content=content,
            revision=revision,
        )
        latest = self._load_session_or_raise(thread_id)
        self._transition_session(
            latest,
            expected_version=int(latest["state_version"]),
            status=self.STATUS_RUNNING_GENERATION,
            pending_content="",
            pending_meta={},
            pending_clarification={},
            latest_clarification_id="",
            last_committed_revision=revision,
            last_error="",
        )
        return {
            "project_id": project_id,
            "node_id": node_id,
            "revision": revision,
            "state_events": int(state_sync.get("state_events", 0)),
            "state_change_proposal_count": int(state_sync.get("state_change_proposal_count", 0)),
            "state_change_proposal_ids": list(state_sync.get("state_change_proposal_ids", [])),
            "state_update_pending": bool(state_sync.get("pending_state_update", False)),
            "state_update_outbox_id": str(state_sync.get("state_update_outbox_id", "")),
            "state_update_error": str(state_sync.get("state_update_error", "")),
            "state_update_retry_summary": state_sync.get("state_update_retry_summary", {}),
        }

    def _sync_state_after_commit(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        content: str,
        revision: int,
    ) -> dict[str, Any]:
        retry_summary = self._process_state_update_outbox(
            project_id=project_id,
            thread_id=thread_id,
            limit=3,
        )
        try:
            sync = self._apply_state_sync_payload(
                project_id=project_id,
                node_id=node_id,
                thread_id=thread_id,
                content=content,
            )
            pending_count = self._pending_state_update_count(
                project_id=project_id,
                thread_id=thread_id,
            )
            return {
                **sync,
                "pending_state_update": False,
                "state_update_outbox_id": "",
                "state_update_error": "",
                "state_update_retry_summary": {
                    **retry_summary,
                    "pending_count": pending_count,
                },
            }
        except Exception as exc:
            outbox_id = self._enqueue_state_update_outbox(
                project_id=project_id,
                node_id=node_id,
                thread_id=thread_id,
                revision=revision,
                content=content,
                error_message=str(exc),
            )
            pending_count = self._pending_state_update_count(
                project_id=project_id,
                thread_id=thread_id,
            )
            return {
                "state_events": 0,
                "state_change_proposal_count": 0,
                "state_change_proposal_ids": [],
                "pending_state_update": True,
                "state_update_outbox_id": outbox_id,
                "state_update_error": str(exc),
                "state_update_retry_summary": {
                    **retry_summary,
                    "pending_count": pending_count,
                },
            }

    def _apply_state_sync_payload(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        content: str,
    ) -> dict[str, Any]:
        extract_result = self.state_service.extract_state_events(project_id, node_id, content)
        events = extract_result.get("events", [])
        created_proposals: list[dict[str, Any]] = []
        if isinstance(events, list) and events:
            created_proposals = self.state_service.create_state_change_proposals(
                project_id,
                node_id,
                thread_id,
                [item for item in events if isinstance(item, dict)],
            )
        return {
            "state_events": len(events) if isinstance(events, list) else 0,
            "state_change_proposal_count": len(created_proposals),
            "state_change_proposal_ids": [str(item.get("id", "")) for item in created_proposals],
        }

    def _enqueue_state_update_outbox(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        revision: int,
        content: str,
        error_message: str,
    ) -> str:
        outbox_id = generate_id("sout")
        now = utc_now()
        payload = {
            "project_id": project_id,
            "node_id": node_id,
            "thread_id": thread_id,
            "revision": int(revision),
            "content": str(content or ""),
        }
        with self.repository.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO state_update_outbox(
                    id, thread_id, project_id, node_id, revision,
                    payload_json, status, attempts, next_retry_at, last_error,
                    created_at, updated_at, applied_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?, '')
                """,
                (
                    outbox_id,
                    str(thread_id),
                    str(project_id),
                    str(node_id),
                    int(revision),
                    self._dump_json(payload),
                    now.isoformat(),
                    str(error_message or ""),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return outbox_id

    def _process_state_update_outbox(
        self,
        *,
        project_id: str,
        thread_id: str,
        limit: int = 3,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(10, int(limit)))
        now = utc_now()
        now_iso = now.isoformat()
        with self.repository.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT * FROM state_update_outbox
                WHERE project_id = ?
                  AND thread_id = ?
                  AND status = 'pending'
                  AND (next_retry_at = '' OR next_retry_at <= ?)
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (str(project_id), str(thread_id), now_iso, safe_limit),
            ).fetchall()

        processed = 0
        success = 0
        failed = 0
        for row in rows:
            processed += 1
            payload = self._load_json(row["payload_json"], {})
            if not isinstance(payload, dict):
                payload = {}
            try:
                self._apply_state_sync_payload(
                    project_id=str(payload.get("project_id") or project_id),
                    node_id=str(payload.get("node_id") or row["node_id"]),
                    thread_id=str(payload.get("thread_id") or row["thread_id"]),
                    content=str(payload.get("content") or ""),
                )
                with self.repository.store.transaction() as conn:
                    conn.execute(
                        """
                        UPDATE state_update_outbox
                        SET status = 'applied',
                            attempts = attempts + 1,
                            last_error = '',
                            next_retry_at = '',
                            applied_at = ?,
                            updated_at = ?
                        WHERE id = ? AND status = 'pending'
                        """,
                        (now_iso, now_iso, str(row["id"])),
                    )
                success += 1
            except Exception as exc:
                failed += 1
                attempts = int(row["attempts"]) + 1
                backoff_sec = min(900, max(10, attempts * 30))
                next_retry = (now + timedelta(seconds=backoff_sec)).isoformat()
                with self.repository.store.transaction() as conn:
                    conn.execute(
                        """
                        UPDATE state_update_outbox
                        SET attempts = ?,
                            last_error = ?,
                            next_retry_at = ?,
                            updated_at = ?
                        WHERE id = ? AND status = 'pending'
                        """,
                        (attempts, str(exc), next_retry, now_iso, str(row["id"])),
                    )

        pending_count = self._pending_state_update_count(
            project_id=project_id,
            thread_id=thread_id,
        )
        return {
            "processed": processed,
            "success": success,
            "failed": failed,
            "pending_count": pending_count,
            "timestamp": now_iso,
        }

    def _pending_state_update_count(
        self,
        *,
        project_id: str,
        thread_id: str,
    ) -> int:
        with self.repository.store.read_only() as conn:
            row = conn.execute(
                """
                SELECT COUNT(1) AS n
                FROM state_update_outbox
                WHERE project_id = ? AND thread_id = ? AND status = 'pending'
                """,
                (str(project_id), str(thread_id)),
            ).fetchone()
        return int(row["n"]) if row is not None else 0

    def _append_global_directive(self, project_id: str, directive_text: str) -> None:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")
        clean_add = str(directive_text or "").strip()
        if not clean_add:
            return
        current_lines = [
            line.strip()
            for line in str(project.settings.global_directives or "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .split("\n")
            if line.strip()
        ]
        if clean_add in current_lines:
            return
        current_lines.append(clean_add)
        project.settings.global_directives = "\n".join(current_lines)
        project.updated_at = utc_now()
        self.repository.update_project(project)

    def _project_revision(self, project_id: str) -> int:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")
        return int(project.active_revision)

    def _require_project_and_node(self, project_id: str, node_id: str) -> None:
        if self.repository.get_project(project_id) is None:
            raise KeyError(f"project not found: {project_id}")
        _ = self.graph_service.get_node(project_id, node_id)

    def _load_session_or_raise(self, thread_id: str) -> dict[str, Any]:
        clean_thread = str(thread_id or "").strip()
        if not clean_thread:
            raise ValueError("thread_id cannot be empty")
        with self.repository.store.read_only() as conn:
            row = conn.execute(
                "SELECT * FROM agent_sessions WHERE thread_id = ? LIMIT 1",
                (clean_thread,),
            ).fetchone()
        if row is None:
            raise KeyError(f"session not found: {clean_thread}")
        return self._decode_session_row(row)

    def _decode_session_row(self, row: Any) -> dict[str, Any]:
        return {
            "thread_id": row["thread_id"],
            "project_id": row["project_id"],
            "node_id": row["node_id"],
            "mode": row["mode"],
            "status": row["status"],
            "state_version": int(row["state_version"]),
            "token_budget": int(row["token_budget"]),
            "style_hint": row["style_hint"],
            "pending_content": row["pending_content"],
            "pending_meta": self._load_json(row["pending_meta_json"], {}),
            "pending_clarification": self._load_json(row["pending_clarification_json"], {}),
            "latest_clarification_id": row["latest_clarification_id"],
            "latest_setting_proposal_id": row["latest_setting_proposal_id"],
            "last_committed_revision": int(row["last_committed_revision"]),
            "last_error": row["last_error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _transition_session(
        self,
        session: dict[str, Any],
        *,
        expected_version: int,
        status: str | None = None,
        pending_content: str | None = None,
        pending_meta: dict[str, Any] | None = None,
        pending_clarification: dict[str, Any] | None = None,
        latest_clarification_id: str | None = None,
        latest_setting_proposal_id: str | None = None,
        last_committed_revision: int | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        next_payload = dict(session)
        if status is not None:
            next_payload["status"] = status
        if pending_content is not None:
            next_payload["pending_content"] = str(pending_content)
        if pending_meta is not None:
            next_payload["pending_meta"] = pending_meta
        if pending_clarification is not None:
            next_payload["pending_clarification"] = pending_clarification
        if latest_clarification_id is not None:
            next_payload["latest_clarification_id"] = str(latest_clarification_id)
        if latest_setting_proposal_id is not None:
            next_payload["latest_setting_proposal_id"] = str(latest_setting_proposal_id)
        if last_committed_revision is not None:
            next_payload["last_committed_revision"] = int(last_committed_revision)
        if last_error is not None:
            next_payload["last_error"] = str(last_error)
        next_payload["state_version"] = int(expected_version) + 1
        next_payload["updated_at"] = utc_now().isoformat()
        with self.repository.store.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE agent_sessions
                SET status = ?,
                    state_version = ?,
                    token_budget = ?,
                    style_hint = ?,
                    pending_content = ?,
                    pending_meta_json = ?,
                    pending_clarification_json = ?,
                    latest_clarification_id = ?,
                    latest_setting_proposal_id = ?,
                    last_committed_revision = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE thread_id = ? AND state_version = ?
                """,
                (
                    str(next_payload["status"]),
                    int(next_payload["state_version"]),
                    int(next_payload["token_budget"]),
                    str(next_payload["style_hint"]),
                    str(next_payload["pending_content"]),
                    self._dump_json(next_payload["pending_meta"]),
                    self._dump_json(next_payload["pending_clarification"]),
                    str(next_payload["latest_clarification_id"]),
                    str(next_payload["latest_setting_proposal_id"]),
                    int(next_payload["last_committed_revision"]),
                    str(next_payload["last_error"]),
                    str(next_payload["updated_at"]),
                    str(next_payload["thread_id"]),
                    int(expected_version),
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("session state_version mismatch")
        return self._load_session_or_raise(str(next_payload["thread_id"]))

    def _claim_decision(
        self,
        *,
        thread_id: str,
        decision_id: str,
        action: str,
        payload: dict[str, Any],
        state_before: str,
        version_before: int,
    ) -> tuple[bool, dict[str, Any] | None]:
        clean_decision = str(decision_id or "").strip()
        if not clean_decision:
            raise ValueError("decision_id cannot be empty")
        now_iso = utc_now().isoformat()
        try:
            with self.repository.store.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_session_decisions(
                        thread_id, decision_id, action, payload_json,
                        status_before, status_after,
                        state_version_before, state_version_after,
                        response_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)
                    """,
                    (
                        thread_id,
                        clean_decision,
                        str(action or "").strip(),
                        self._dump_json(payload),
                        str(state_before),
                        str(state_before),
                        int(version_before),
                        int(version_before),
                        now_iso,
                    ),
                )
            return True, None
        except sqlite3.IntegrityError:
            with self.repository.store.read_only() as conn:
                row = conn.execute(
                    """
                    SELECT response_json
                    FROM agent_session_decisions
                    WHERE thread_id = ? AND decision_id = ?
                    LIMIT 1
                    """,
                    (thread_id, clean_decision),
                ).fetchone()
            if row is None:
                return False, {"thread_id": thread_id, "session": self.get_session_state(thread_id)}
            response_payload = self._load_json(str(row["response_json"]), {})
            if isinstance(response_payload, dict) and response_payload:
                return False, response_payload
            return False, {"thread_id": thread_id, "session": self.get_session_state(thread_id)}

    def _finalize_decision(
        self,
        *,
        thread_id: str,
        decision_id: str,
        state_after: str,
        version_after: int,
        response_payload: dict[str, Any],
    ) -> None:
        with self.repository.store.transaction() as conn:
            conn.execute(
                """
                UPDATE agent_session_decisions
                SET status_after = ?,
                    state_version_after = ?,
                    response_json = ?
                WHERE thread_id = ? AND decision_id = ?
                """,
                (
                    str(state_after),
                    int(version_after),
                    self._dump_json(response_payload),
                    str(thread_id),
                    str(decision_id),
                ),
            )

    def _build_chapter_done_evaluation(
        self,
        *,
        session: dict[str, Any],
        draft: ChapterDraftResult,
        correction_mode: bool,
    ) -> dict[str, Any]:
        if correction_mode:
            return {
                "chapter_done_signal": False,
                "chapter_done_signal_source": "disabled_in_correction",
                "review_ready": False,
                "min_chars": 0,
                "content_chars": len(str(draft.content or "").strip()),
                "forced_progression_points_total": 0,
                "forced_progression_points_hit": 0,
                "forced_progression_coverage": 0.0,
                "pending_setting_proposals": 0,
                "unresolved_state_conflicts": 0,
                "unmet_conditions": ["correction_mode"],
            }

        project_id = str(session["project_id"])
        node_id = str(session["node_id"])
        node = self.graph_service.get_node(project_id, node_id)
        metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
        content = str(draft.content or "").strip()
        min_chars = max(200, self._safe_int(metadata.get("chapter_done_min_chars"), fallback=800))
        content_chars = len(content)
        min_chars_ok = content_chars >= min_chars

        forced_points = self._extract_forced_progression_points(metadata.get("forced_progression_points"))
        normalized_content = self._normalize_text_for_match(content)
        forced_hits = 0
        for point in forced_points:
            normalized_point = self._normalize_text_for_match(point)
            if normalized_point and normalized_point in normalized_content:
                forced_hits += 1
        coverage = 1.0 if not forced_points else (forced_hits / len(forced_points))
        forced_points_ok = coverage >= 1.0

        pending_setting_count = 0
        pending_state_change_count = 0
        pending_ok = True
        try:
            pending = self.setting_proposal_service.list_proposals(
                project_id=project_id,
                thread_id=str(session["thread_id"]),
                status="pending_review",
            )
            pending_setting_count = len(pending)
            with self.repository.store.read_only() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(1) AS n
                    FROM state_change_proposals
                    WHERE project_id = ? AND thread_id = ? AND status = 'pending'
                    """,
                    (project_id, str(session["thread_id"])),
                ).fetchone()
            pending_state_change_count = int(row["n"]) if row is not None else 0
            pending_ok = (pending_setting_count + pending_state_change_count) == 0
        except Exception:
            pending_ok = False

        conflict_count = 0
        conflicts_ok = True
        try:
            conflicts = self.state_service.list_state_conflicts(project_id, unresolved_only=True)
            related_conflicts = [
                item
                for item in conflicts
                if str(item.get("node_id", "")).strip() in {"", node_id}
            ]
            conflict_count = len(related_conflicts)
            conflicts_ok = conflict_count == 0
        except Exception:
            conflicts_ok = False

        explicit_signal = self._extract_explicit_chapter_done_signal(
            content=content,
            draft=draft,
        )
        inferred_signal = min_chars_ok and forced_points_ok and pending_ok and conflicts_ok
        signal = explicit_signal or inferred_signal
        review_ready = signal and min_chars_ok and forced_points_ok and pending_ok and conflicts_ok

        unmet: list[str] = []
        if not min_chars_ok:
            unmet.append("min_chars")
        if not forced_points_ok:
            unmet.append("forced_progression_points")
        if not pending_ok:
            unmet.append("pending_setting_proposals")
        if not conflicts_ok:
            unmet.append("unresolved_state_conflicts")
        if not signal:
            unmet.append("chapter_done_signal")

        return {
            "chapter_done_signal": bool(signal),
            "chapter_done_signal_source": "explicit" if explicit_signal else "inferred_by_gate",
            "review_ready": bool(review_ready),
            "min_chars": min_chars,
            "content_chars": content_chars,
            "forced_progression_points_total": len(forced_points),
            "forced_progression_points_hit": forced_hits,
            "forced_progression_coverage": round(coverage, 4),
            "pending_setting_proposals": pending_setting_count,
            "pending_state_change_proposals": pending_state_change_count,
            "pending_proposals_total": pending_setting_count + pending_state_change_count,
            "unresolved_state_conflicts": conflict_count,
            "unmet_conditions": unmet,
        }

    def _extract_explicit_chapter_done_signal(
        self,
        *,
        content: str,
        draft: ChapterDraftResult,
    ) -> bool:
        patch = getattr(draft, "node_metadata_patch", None)
        if isinstance(patch, dict) and "ai_chapter_done_signal" in patch:
            return bool(patch.get("ai_chapter_done_signal"))

        text = str(content or "")
        if not text:
            return False
        if re.search(r"\bchapter_done_signal\b\s*[:=]\s*(true|1|yes)\b", text, flags=re.IGNORECASE):
            return True
        if re.search(r"章节完成信号\s*[:：]\s*(true|1|是)", text, flags=re.IGNORECASE):
            return True
        return False

    def _extract_forced_progression_points(self, raw: Any) -> list[str]:
        points: list[str] = []
        if isinstance(raw, list):
            for item in raw:
                text = str(item or "").strip()
                if text:
                    points.append(text)
        elif isinstance(raw, str):
            for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)、])\s*", "", line).strip()
                if cleaned:
                    points.append(cleaned)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in points:
            key = self._normalize_text_for_match(item)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _normalize_text_for_match(self, value: str) -> str:
        text = str(value or "").lower()
        text = re.sub(r"\s+", "", text)
        return text

    def _build_diff_patch(
        self,
        *,
        thread_id: str,
        base_revision: int,
        base_content: str,
        revised_content: str,
    ) -> dict[str, Any]:
        base_lines = self._split_lines(base_content)
        revised_lines = self._split_lines(revised_content)
        matcher = difflib.SequenceMatcher(a=base_lines, b=revised_lines, autojunk=False)
        hunks: list[dict[str, Any]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag == "replace":
                op = "replace"
            elif tag == "delete":
                op = "delete"
            elif tag == "insert":
                op = "add"
            else:
                continue
            hunks.append(
                {
                    "hunk_id": generate_id("hunk"),
                    "op": op,
                    "start_line": int(i1 + 1),
                    "end_line": int(i2),
                    "old_text": "\n".join(base_lines[i1:i2]),
                    "new_text": "\n".join(revised_lines[j1:j2]),
                    "reason": "LLM correction proposal",
                }
            )
        return {
            "diff_id": generate_id("diff"),
            "thread_id": str(thread_id or "").strip(),
            "base_revision": int(base_revision),
            "base_content_hash": self._text_hash(base_content),
            "hunks": hunks,
        }

    def _normalize_llm_diff_patch(
        self,
        *,
        thread_id: str,
        base_revision: int,
        base_content: str,
        revised_content: str,
        llm_patch: dict[str, Any],
    ) -> dict[str, Any]:
        raw_hunks = llm_patch.get("hunks")
        if not isinstance(raw_hunks, list):
            return self._build_diff_patch(
                thread_id=thread_id,
                base_revision=base_revision,
                base_content=base_content,
                revised_content=revised_content,
            )
        normalized_hunks: list[dict[str, Any]] = []
        for item in raw_hunks:
            if not isinstance(item, dict):
                continue
            op = str(item.get("op") or "").strip().lower()
            if op not in {"add", "delete", "replace"}:
                continue
            start_line = max(1, self._safe_int(item.get("start_line"), fallback=1))
            end_line = max(0, self._safe_int(item.get("end_line"), fallback=max(0, start_line - 1)))
            normalized_hunks.append(
                {
                    "hunk_id": str(item.get("hunk_id") or "").strip() or generate_id("hunk"),
                    "op": op,
                    "start_line": int(start_line),
                    "end_line": int(end_line),
                    "old_text": str(item.get("old_text") or ""),
                    "new_text": str(item.get("new_text") or ""),
                    "reason": str(item.get("reason") or "").strip() or "LLM correction proposal",
                }
            )
        if not normalized_hunks:
            return self._build_diff_patch(
                thread_id=thread_id,
                base_revision=base_revision,
                base_content=base_content,
                revised_content=revised_content,
            )
        return {
            "diff_id": str(llm_patch.get("diff_id") or "").strip() or generate_id("diff"),
            "thread_id": str(thread_id or "").strip(),
            "base_revision": int(base_revision),
            "base_content_hash": self._text_hash(base_content),
            "hunks": normalized_hunks,
        }

    def _split_lines(self, text: str) -> list[str]:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized:
            return []
        return normalized.split("\n")

    def _normalize_hunk_ids(self, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in values:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    def _apply_diff_patch(
        self,
        *,
        base_content: str,
        diff_patch: dict[str, Any],
        accepted_hunk_ids: list[str],
        rejected_hunk_ids: list[str],
    ) -> dict[str, Any]:
        raw_hunks = diff_patch.get("hunks")
        if not isinstance(raw_hunks, list):
            raise ValueError("invalid diff_patch: hunks must be a list")
        hunks = [item for item in raw_hunks if isinstance(item, dict)]
        all_hunk_ids = [
            str(item.get("hunk_id") or "").strip()
            for item in hunks
            if str(item.get("hunk_id") or "").strip()
        ]
        if not all_hunk_ids:
            return {
                "status": "no_changes",
                "message": "diff has no hunks",
                "content": base_content,
                "accepted_hunk_ids": [],
                "rejected_hunk_ids": [],
                "applied_hunk_ids": [],
            }

        unknown_accepted = [item for item in accepted_hunk_ids if item not in set(all_hunk_ids)]
        unknown_rejected = [item for item in rejected_hunk_ids if item not in set(all_hunk_ids)]
        if unknown_accepted:
            raise ValueError(f"unknown accepted_hunk_ids: {unknown_accepted}")
        if unknown_rejected:
            raise ValueError(f"unknown rejected_hunk_ids: {unknown_rejected}")

        rejected_set = set(rejected_hunk_ids)
        if accepted_hunk_ids:
            selected_set = set(accepted_hunk_ids)
            rejected_set = rejected_set | {item for item in all_hunk_ids if item not in selected_set}
        else:
            selected_set = {item for item in all_hunk_ids if item not in rejected_set}
        selected_ids = [item for item in all_hunk_ids if item in selected_set]
        normalized_rejected = [item for item in all_hunk_ids if item in rejected_set]
        if not selected_ids:
            return {
                "status": "no_changes",
                "message": "no hunks selected for apply",
                "content": base_content,
                "accepted_hunk_ids": selected_ids,
                "rejected_hunk_ids": normalized_rejected,
                "applied_hunk_ids": [],
            }

        lines = self._split_lines(base_content)
        offset = 0
        applied: list[str] = []
        for hunk in hunks:
            hunk_id = str(hunk.get("hunk_id") or "").strip()
            if not hunk_id or hunk_id not in selected_set:
                continue
            op = str(hunk.get("op") or "").strip().lower()
            start_line = max(1, self._safe_int(hunk.get("start_line"), fallback=1))
            end_line = max(0, self._safe_int(hunk.get("end_line"), fallback=start_line - 1))
            start_idx = max(0, start_line - 1 + offset)
            end_idx = max(start_idx, end_line + offset)
            old_lines = self._split_lines(str(hunk.get("old_text") or ""))
            new_lines = self._split_lines(str(hunk.get("new_text") or ""))

            if op in {"replace", "delete"}:
                current = lines[start_idx:end_idx]
                if current != old_lines:
                    raise ValueError(
                        f"diff hunk old_text mismatch: {hunk_id}, expected lines {start_line}-{end_line}"
                    )
            if op == "add":
                lines[start_idx:start_idx] = new_lines
                offset += len(new_lines)
            elif op == "delete":
                removed = end_idx - start_idx
                del lines[start_idx:end_idx]
                offset -= removed
            elif op == "replace":
                replaced = end_idx - start_idx
                lines[start_idx:end_idx] = new_lines
                offset += len(new_lines) - replaced
            else:
                raise ValueError(f"unsupported diff op: {op}")
            applied.append(hunk_id)

        content = "\n".join(lines)
        return {
            "status": "applied" if applied else "no_changes",
            "message": "diff applied" if applied else "no hunks applied",
            "content": content,
            "accepted_hunk_ids": selected_ids,
            "rejected_hunk_ids": normalized_rejected,
            "applied_hunk_ids": applied,
        }

    def _text_hash(self, text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _safe_int(self, value: Any, *, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _extract_tool_setting_proposal_ids(self, draft: ChapterDraftResult) -> list[str]:
        calls = getattr(draft, "agent_tool_calls", [])
        if not isinstance(calls, list):
            return []
        proposal_ids: list[str] = []
        seen: set[str] = set()
        for item in calls:
            if not isinstance(item, dict):
                continue
            result_meta = item.get("result_meta")
            if not isinstance(result_meta, dict):
                continue
            proposal_id = str(result_meta.get("proposal_id") or "").strip()
            if not proposal_id or proposal_id in seen:
                continue
            seen.add(proposal_id)
            proposal_ids.append(proposal_id)
        return proposal_ids

    def _draft_to_meta(self, draft: ChapterDraftResult) -> dict[str, Any]:
        return {
            "provider": draft.provider,
            "prompt_tokens": int(draft.prompt_tokens),
            "completion_tokens": int(draft.completion_tokens),
            "workflow_mode": draft.workflow_mode,
            "agent_trace": dict(draft.agent_trace),
            "node_metadata_patch": dict(draft.node_metadata_patch),
            "task_id": draft.task_id,
            "prompt_version": draft.prompt_version,
            "llm_diff_patch": dict(getattr(draft, "diff_patch", {}) or {}),
            "agent_loop_metrics": dict(getattr(draft, "agent_loop_metrics", {}) or {}),
            "tool_evidence_chunk_ids": list(getattr(draft, "tool_evidence_chunk_ids", []) or []),
        }

    def _dump_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def _load_json(self, raw: Any, fallback: Any) -> Any:
        try:
            return json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback
