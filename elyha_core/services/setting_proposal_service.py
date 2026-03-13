"""Setting proposal review/apply service for HITL clarification flows."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from typing import Any

from elyha_core.models.project import project_settings_from_payload
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id


class SettingProposalService:
    """Persist and apply setting proposals produced by clarification answers."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def create_from_clarification(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        clarification_id: str,
        selected_option: str = "",
        answer_text: str = "",
        question_type: str = "other",
        question: str = "",
        target_scope: str = "project",
        proposal_type: str = "",
    ) -> dict[str, Any]:
        clean_option = str(selected_option or "").strip()
        clean_answer = str(answer_text or "").strip()
        if not clean_option and not clean_answer:
            raise ValueError("selected_option and answer_text cannot both be empty")
        if clean_option == "other" and not clean_answer:
            raise ValueError("answer_text is required when selected_option=other")

        clean_scope = str(target_scope or "project").strip().lower()
        if clean_scope not in {"project", "global", "node", "character", "item"}:
            clean_scope = "project"
        clean_type = str(proposal_type or "").strip() or str(question_type or "").strip() or "other"
        effective_revision = self._project_revision(project_id)
        supersedes_id = self._latest_applied_proposal_id(
            project_id=project_id,
            thread_id=thread_id,
            target_scope=clean_scope,
            proposal_type=clean_type,
        )
        proposal_id = generate_id("sp")
        payload = {
            "source": "clarification_answer",
            "clarification_id": clarification_id,
            "question_type": str(question_type or "").strip() or "other",
            "question": str(question or "").strip(),
            "selected_option": clean_option,
            "answer_text": clean_answer,
            "directive_text": self._derive_directive_text(
                question=str(question or "").strip(),
                selected_option=clean_option,
                answer_text=clean_answer,
            ),
        }
        now_iso = utc_now().isoformat()
        with self.repository.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO setting_proposals(
                    id, thread_id, project_id, node_id, clarification_id,
                    proposal_type, target_scope, effective_from_revision,
                    supersedes_proposal_id, proposal_json, status,
                    reviewer, review_note, created_at, reviewed_at, applied_at, applied_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', '', '', ?, '', '', 0)
                """,
                (
                    proposal_id,
                    str(thread_id or "").strip(),
                    project_id,
                    node_id,
                    str(clarification_id or "").strip(),
                    clean_type,
                    clean_scope,
                    int(effective_revision),
                    supersedes_id,
                    self._dump_json(payload),
                    now_iso,
                ),
            )
        return self.get_proposal(proposal_id)

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        clean_id = str(proposal_id or "").strip()
        if not clean_id:
            raise ValueError("proposal_id cannot be empty")
        with self.repository.store.read_only() as conn:
            row = conn.execute(
                "SELECT * FROM setting_proposals WHERE id = ? LIMIT 1",
                (clean_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"setting proposal not found: {clean_id}")
        return self._decode_row(row)

    def list_proposals(
        self,
        *,
        project_id: str,
        thread_id: str | None = None,
        status: str | None = None,
        proposal_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        where = ["project_id = ?"]
        params: list[Any] = [project_id]
        if thread_id is not None:
            where.append("thread_id = ?")
            params.append(str(thread_id).strip())
        if status is not None:
            where.append("status = ?")
            params.append(str(status).strip())
        if proposal_ids:
            cleaned_ids = [str(item).strip() for item in proposal_ids if str(item).strip()]
            if cleaned_ids:
                placeholders = ",".join("?" for _ in cleaned_ids)
                where.append(f"id IN ({placeholders})")
                params.extend(cleaned_ids)
        sql = (
            "SELECT * FROM setting_proposals "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY created_at DESC, id DESC"
        )
        with self.repository.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._decode_row(row) for row in rows]

    def review_proposal(
        self,
        proposal_id: str,
        *,
        action: str,
        reviewer: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        normalized_action = str(action or "").strip().lower()
        if normalized_action in {"approve", "approved"}:
            next_status = "approved"
        elif normalized_action in {"reject", "rejected"}:
            next_status = "rejected"
        else:
            raise ValueError("action must be approve/approved/reject/rejected")

        now_iso = utc_now().isoformat()
        with self.repository.store.transaction() as conn:
            conn.execute(
                """
                UPDATE setting_proposals
                SET status = ?, reviewer = ?, review_note = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    str(reviewer or "").strip(),
                    str(note or "").strip(),
                    now_iso,
                    proposal["id"],
                ),
            )
        return self.get_proposal(proposal["id"])

    def apply_proposal(
        self,
        proposal_id: str,
        *,
        reviewer: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        status = str(proposal.get("status", "")).strip()
        if status == "applied":
            return proposal
        if status != "approved":
            raise ValueError("setting proposal must be approved before apply")

        payload = proposal.get("proposal", {})
        directive_text = ""
        if isinstance(payload, dict):
            directive_text = str(payload.get("directive_text") or "").strip()
        now_iso = utc_now().isoformat()
        with self.repository.store.transaction() as conn:
            if directive_text and str(proposal.get("target_scope", "")) in {"project", "global"}:
                self._append_global_directive(conn, str(proposal.get("project_id", "")), directive_text)
            applied_revision = int(
                conn.execute(
                    "SELECT active_revision FROM projects WHERE id = ? LIMIT 1",
                    (str(proposal.get("project_id", "")),),
                ).fetchone()["active_revision"]
            )
            conn.execute(
                """
                UPDATE setting_proposals
                SET status = 'applied',
                    reviewer = ?,
                    review_note = ?,
                    reviewed_at = CASE WHEN reviewed_at = '' THEN ? ELSE reviewed_at END,
                    applied_at = ?,
                    applied_revision = ?
                WHERE id = ? AND status = 'approved'
                """,
                (
                    str(reviewer or proposal.get("reviewer", "")).strip(),
                    str(note or proposal.get("review_note", "")).strip(),
                    now_iso,
                    now_iso,
                    applied_revision,
                    proposal["id"],
                ),
            )
            supersedes = str(proposal.get("supersedes_proposal_id", "")).strip()
            if supersedes:
                conn.execute(
                    """
                    UPDATE setting_proposals
                    SET status = 'superseded'
                    WHERE id = ? AND status = 'applied'
                    """,
                    (supersedes,),
                )
        return self.get_proposal(proposal["id"])

    def _project_revision(self, project_id: str) -> int:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")
        return int(project.active_revision)

    def _latest_applied_proposal_id(
        self,
        *,
        project_id: str,
        thread_id: str,
        target_scope: str,
        proposal_type: str,
    ) -> str:
        with self.repository.store.read_only() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM setting_proposals
                WHERE project_id = ?
                  AND thread_id = ?
                  AND target_scope = ?
                  AND proposal_type = ?
                  AND status = 'applied'
                ORDER BY applied_at DESC, id DESC
                LIMIT 1
                """,
                (project_id, str(thread_id or "").strip(), target_scope, proposal_type),
            ).fetchone()
        if row is None:
            return ""
        return str(row["id"])

    def _append_global_directive(
        self,
        conn: Any,
        project_id: str,
        directive_text: str,
    ) -> None:
        clean_project_id = str(project_id or "").strip()
        if not clean_project_id:
            return
        row = conn.execute(
            "SELECT settings_json FROM projects WHERE id = ? LIMIT 1",
            (clean_project_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"project not found: {clean_project_id}")
        try:
            settings_payload = json.loads(str(row["settings_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            settings_payload = {}
        settings = project_settings_from_payload(settings_payload)
        merged = self._merge_global_directives(settings.global_directives, directive_text)
        if merged == settings.global_directives:
            return
        updated_settings = replace(settings, global_directives=merged)
        conn.execute(
            "UPDATE projects SET settings_json = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(asdict(updated_settings), sort_keys=True),
                utc_now().isoformat(),
                clean_project_id,
            ),
        )

    def _merge_global_directives(self, current: str, addition: str) -> str:
        clean_add = str(addition or "").strip()
        if not clean_add:
            return str(current or "").strip()
        current_lines = [
            line.strip()
            for line in str(current or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if line.strip()
        ]
        if clean_add in current_lines:
            return "\n".join(current_lines)
        current_lines.append(clean_add)
        return "\n".join(current_lines)

    def _derive_directive_text(
        self,
        *,
        question: str,
        selected_option: str,
        answer_text: str,
    ) -> str:
        clean_answer = str(answer_text or "").strip()
        if clean_answer:
            return clean_answer
        clean_option = str(selected_option or "").strip()
        if not clean_option or clean_option == "other":
            return ""
        clean_question = str(question or "").strip()
        if clean_question:
            return f"{clean_question}: {clean_option}"
        return clean_option

    def _decode_row(self, row: Any) -> dict[str, Any]:
        proposal_payload = self._load_json(str(row["proposal_json"]), fallback={})
        return {
            "id": row["id"],
            "thread_id": row["thread_id"],
            "project_id": row["project_id"],
            "node_id": row["node_id"],
            "clarification_id": row["clarification_id"],
            "proposal_type": row["proposal_type"],
            "target_scope": row["target_scope"],
            "effective_from_revision": int(row["effective_from_revision"]),
            "supersedes_proposal_id": row["supersedes_proposal_id"],
            "proposal": proposal_payload,
            "status": row["status"],
            "reviewer": row["reviewer"],
            "review_note": row["review_note"],
            "created_at": row["created_at"],
            "reviewed_at": row["reviewed_at"],
            "applied_at": row["applied_at"],
            "applied_revision": int(row["applied_revision"]),
        }

    def _dump_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def _load_json(self, raw: str, fallback: Any) -> Any:
        try:
            return json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback
