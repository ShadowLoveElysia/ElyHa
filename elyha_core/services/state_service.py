"""State management service for world-state extraction, review and apply."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from typing import Any

from elyha_core.i18n import tr
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id


_JSON_FENCE_PATTERN = re.compile(
    r"```(?:json|state[-_ ]?events?)?\s*([\s\S]*?)```",
    flags=re.IGNORECASE,
)

# Fallback extractor patterns stay centralized for easy future externalization.
_DEATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}).{0,8}(死亡|死去|阵亡|被杀|牺牲)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})\s+(dies?|dead|killed|slain)\b",
        flags=re.IGNORECASE,
    ),
)

_MOVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}).{0,8}(来到|抵达|前往|移动到|位于)(?P<to>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})\s+(arrives?\s+at|goes?\s+to|moves?\s+to)\s+(?P<to>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})",
        flags=re.IGNORECASE,
    ),
)

_HOLD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}).{0,8}(获得|拿到|拾取|持有)(?P<item>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})\s+(obtains?|gets?|picks?\s+up|holds?)\s+(?P<item>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})",
        flags=re.IGNORECASE,
    ),
)

_DESTROY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?P<item>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}).{0,8}(被摧毁|损毁|毁坏)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<item>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})\s+(destroyed|shattered|broken)\b",
        flags=re.IGNORECASE,
    ),
)


class StateService:
    """HITL-first world-state management for chapter-level updates."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def extract_state_events(
        self,
        project_id: str,
        node_id: str,
        content: str,
    ) -> dict[str, Any]:
        """Extract draft state events from chapter content.

        This extractor intentionally remains conservative. It prefers explicit JSON blocks
        and only applies shallow rule-based heuristics when no explicit structure exists.
        """
        self._require_project(project_id)
        self._require_node(project_id, node_id)
        text = str(content or "").strip()
        events = self._extract_events_from_json_blocks(text)
        if not events:
            events = self._extract_events_from_rules(text)
        normalized: list[dict[str, Any]] = []
        for event in events:
            try:
                normalized.append(self._normalize_event(event))
            except ValueError:
                continue
        return {
            "project_id": project_id,
            "node_id": node_id,
            "events": normalized,
            "count": len(normalized),
        }

    def extract_relationship_events(
        self,
        project_id: str,
        node_id: str,
        content: str,
    ) -> dict[str, Any]:
        extracted = self.extract_state_events(project_id, node_id, content)
        rel_events = [
            item for item in extracted["events"] if str(item.get("entity_type", "")) == "relationship"
        ]
        return {
            "project_id": project_id,
            "node_id": node_id,
            "events": rel_events,
            "count": len(rel_events),
        }

    def extract_world_variable_events(
        self,
        project_id: str,
        node_id: str,
        content: str,
    ) -> dict[str, Any]:
        extracted = self.extract_state_events(project_id, node_id, content)
        world_events = [
            item for item in extracted["events"] if str(item.get("entity_type", "")) == "world_variable"
        ]
        return {
            "project_id": project_id,
            "node_id": node_id,
            "events": world_events,
            "count": len(world_events),
        }

    def create_state_change_proposals(
        self,
        project_id: str,
        node_id: str,
        thread_id: str,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self._require_project(project_id)
        self._require_node(project_id, node_id)
        thread = str(thread_id or "").strip()
        if not thread:
            raise ValueError("thread_id cannot be empty")
        now_iso = self._now_iso()
        created_ids: list[str] = []
        with self.repository.store.transaction() as conn:
            for raw in events:
                event = self._normalize_event(raw)
                proposal_id = generate_id("stp")
                conn.execute(
                    """
                    INSERT INTO state_change_proposals(
                        id, project_id, node_id, thread_id, proposal_json,
                        status, reviewer, review_note, created_at, reviewed_at, applied_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', '', '', ?, '', '')
                    """,
                    (
                        proposal_id,
                        project_id,
                        node_id,
                        thread,
                        self._dump_json(event),
                        now_iso,
                    ),
                )
                created_ids.append(proposal_id)
        return self.list_state_change_proposals(project_id, proposal_ids=created_ids)

    def list_state_change_proposals(
        self,
        project_id: str,
        *,
        node_id: str | None = None,
        thread_id: str | None = None,
        status: str | None = None,
        include_applied: bool = True,
        proposal_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_project(project_id)
        where = ["project_id = ?"]
        params: list[Any] = [project_id]

        if node_id is not None:
            where.append("node_id = ?")
            params.append(node_id)
        if thread_id is not None:
            where.append("thread_id = ?")
            params.append(thread_id)
        if status is not None:
            where.append("status = ?")
            params.append(status)
        if not include_applied:
            where.append("applied_at = ''")

        if proposal_ids:
            ids = [str(item).strip() for item in proposal_ids if str(item).strip()]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                where.append(f"id IN ({placeholders})")
                params.extend(ids)

        sql = (
            "SELECT * FROM state_change_proposals "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY created_at DESC, id DESC"
        )
        with self.repository.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._decode_proposal_row(row) for row in rows]

    def review_state_change_proposal(
        self,
        proposal_id: str,
        action: str,
        reviewer: str,
        note: str,
    ) -> dict[str, Any]:
        proposal = self._get_proposal_or_raise(proposal_id)
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"approved", "rejected"}:
            raise ValueError("action must be approved or rejected")
        now_iso = self._now_iso()
        with self.repository.store.transaction() as conn:
            conn.execute(
                """
                UPDATE state_change_proposals
                SET status = ?, reviewer = ?, review_note = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (
                    normalized_action,
                    str(reviewer or "").strip(),
                    str(note or "").strip(),
                    now_iso,
                    proposal_id,
                ),
            )
        refreshed = self._get_proposal_or_raise(proposal_id)
        if refreshed["status"] == "approved" and proposal["status"] != "approved":
            refreshed["transition"] = "pending_to_approved"
        elif refreshed["status"] == "rejected" and proposal["status"] != "rejected":
            refreshed["transition"] = "pending_to_rejected"
        return refreshed

    def apply_approved_state_changes(
        self,
        project_id: str,
        node_id: str,
        thread_id: str,
        *,
        proposal_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        self._require_node(project_id, node_id)
        thread = str(thread_id or "").strip()
        if not thread:
            raise ValueError("thread_id cannot be empty")

        requested = [str(item).strip() for item in (proposal_ids or []) if str(item).strip()]
        applied_ids: list[str] = []
        skipped_ids: list[str] = []
        conflict_count = 0

        with self.repository.store.transaction() as conn:
            start_conflicts = int(
                conn.execute(
                    "SELECT COUNT(1) AS n FROM state_conflicts WHERE project_id = ?",
                    (project_id,),
                ).fetchone()["n"]
            )
            proposals = self._load_proposals_for_apply(
                conn,
                project_id=project_id,
                node_id=node_id,
                thread_id=thread,
                proposal_ids=requested,
            )
            for proposal in proposals:
                proposal_id = str(proposal["id"])
                event = self._load_json(str(proposal["proposal_json"]), {})
                if not isinstance(event, dict):
                    self._record_conflict(
                        conn,
                        project_id=project_id,
                        node_id=node_id,
                        conflict_type="invalid_proposal_payload",
                        detail={
                            "proposal_id": proposal_id,
                            "reason": "proposal_json is not an object",
                        },
                    )
                    conflict_count += 1
                    skipped_ids.append(proposal_id)
                    continue

                # Claim proposal first to make apply idempotent under repeated clicks/races.
                claim_cursor = conn.execute(
                    """
                    UPDATE state_change_proposals
                    SET applied_at = ?
                    WHERE id = ? AND status = 'approved' AND applied_at = ''
                    """,
                    (self._now_iso(), proposal_id),
                )
                if claim_cursor.rowcount == 0:
                    skipped_ids.append(proposal_id)
                    continue

                applied = self._apply_single_event_from_proposal(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    proposal_id=proposal_id,
                    event=event,
                )
                if applied:
                    applied_ids.append(proposal_id)
                else:
                    conn.execute(
                        "UPDATE state_change_proposals SET applied_at = '' WHERE id = ?",
                        (proposal_id,),
                    )
                    skipped_ids.append(proposal_id)
            end_conflicts = int(
                conn.execute(
                    "SELECT COUNT(1) AS n FROM state_conflicts WHERE project_id = ?",
                    (project_id,),
                ).fetchone()["n"]
            )
            conflict_count = max(0, end_conflicts - start_conflicts)

        return {
            "project_id": project_id,
            "node_id": node_id,
            "thread_id": thread,
            "requested_count": len(requested) if requested else None,
            "proposal_count": len(applied_ids) + len(skipped_ids),
            "applied_count": len(applied_ids),
            "skipped_count": len(skipped_ids),
            "conflict_count": conflict_count,
            "applied_proposal_ids": applied_ids,
            "skipped_proposal_ids": skipped_ids,
        }

    def get_character_status(
        self,
        project_id: str,
        character_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_project(project_id)
        where = ["project_id = ?"]
        params: list[Any] = [project_id]
        if character_ids:
            cleaned = [str(item).strip() for item in character_ids if str(item).strip()]
            if cleaned:
                placeholders = ",".join("?" for _ in cleaned)
                where.append(f"character_id IN ({placeholders})")
                params.extend(cleaned)
        sql = (
            "SELECT * FROM character_status "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY updated_at DESC, character_id ASC"
        )
        with self.repository.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "project_id": row["project_id"],
                    "character_id": row["character_id"],
                    "alive": bool(row["alive"]),
                    "location": row["location"],
                    "faction": row["faction"],
                    "held_items": self._load_json(str(row["held_items_json"]), []),
                    "state_attributes": self._load_json(str(row["state_attributes_json"]), {}),
                    "last_event_id": row["last_event_id"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def get_item_status(
        self,
        project_id: str,
        item_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_project(project_id)
        where = ["project_id = ?"]
        params: list[Any] = [project_id]
        if item_ids:
            cleaned = [str(item).strip() for item in item_ids if str(item).strip()]
            if cleaned:
                placeholders = ",".join("?" for _ in cleaned)
                where.append(f"item_id IN ({placeholders})")
                params.extend(cleaned)
        sql = (
            "SELECT * FROM item_status "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY updated_at DESC, item_id ASC"
        )
        with self.repository.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "project_id": row["project_id"],
                    "item_id": row["item_id"],
                    "owner_character_id": row["owner_character_id"],
                    "location": row["location"],
                    "destroyed": bool(row["destroyed"]),
                    "state_attributes": self._load_json(str(row["state_attributes_json"]), {}),
                    "last_event_id": row["last_event_id"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def get_relationship_status(
        self,
        project_id: str,
        pairs: list[tuple[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_project(project_id)
        with self.repository.store.read_only() as conn:
            if not pairs:
                rows = conn.execute(
                    """
                    SELECT * FROM relationship_status
                    WHERE project_id = ?
                    ORDER BY updated_at DESC, subject_character_id ASC, object_character_id ASC
                    """,
                    (project_id,),
                ).fetchall()
            else:
                cleaned_pairs = [
                    (str(src).strip(), str(dst).strip())
                    for src, dst in pairs
                    if str(src).strip() and str(dst).strip()
                ]
                if not cleaned_pairs:
                    return []
                filters = " OR ".join(
                    "(subject_character_id = ? AND object_character_id = ?)" for _ in cleaned_pairs
                )
                params: list[Any] = [project_id]
                for src, dst in cleaned_pairs:
                    params.extend([src, dst])
                rows = conn.execute(
                    f"""
                    SELECT * FROM relationship_status
                    WHERE project_id = ? AND ({filters})
                    ORDER BY updated_at DESC, subject_character_id ASC, object_character_id ASC
                    """,
                    tuple(params),
                ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "project_id": row["project_id"],
                    "subject_character_id": row["subject_character_id"],
                    "object_character_id": row["object_character_id"],
                    "relation_type": row["relation_type"],
                    "state_attributes": self._load_json(str(row["state_attributes_json"]), {}),
                    "last_event_id": row["last_event_id"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def get_world_variable_status(
        self,
        project_id: str,
        keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_project(project_id)
        where = ["project_id = ?"]
        params: list[Any] = [project_id]
        if keys:
            cleaned = [str(item).strip() for item in keys if str(item).strip()]
            if cleaned:
                placeholders = ",".join("?" for _ in cleaned)
                where.append(f"variable_key IN ({placeholders})")
                params.extend(cleaned)
        sql = (
            "SELECT * FROM world_variable_status "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY updated_at DESC, variable_key ASC"
        )
        with self.repository.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "project_id": row["project_id"],
                    "variable_key": row["variable_key"],
                    "value": self._load_json(str(row["value_json"]), None),
                    "last_event_id": row["last_event_id"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def build_prompt_state_payload(
        self,
        project_id: str,
        *,
        character_ids: list[str] | None = None,
        item_ids: list[str] | None = None,
        relationship_pairs: list[tuple[str, str]] | None = None,
        world_variable_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "characters": self.get_character_status(project_id, character_ids),
            "items": self.get_item_status(project_id, item_ids),
            "relationships": self.get_relationship_status(project_id, relationship_pairs),
            "world_variables": self.get_world_variable_status(project_id, world_variable_keys),
        }

    def generate_arc_summary(
        self,
        project_id: str,
        *,
        node_count_threshold: int = 50,
        max_summary_chars: int = 4000,
    ) -> str | None:
        """Generate a condensed arc-level summary from node chunk summaries.

        Returns None if auto-summary is disabled or node count is below threshold.
        """
        project = self.repository.get_project(project_id)
        if project is None:
            return None
        if not getattr(project.settings, "enable_auto_arc_summary", False):
            return None

        with self.repository.store.read_only() as conn:
            node_count_row = conn.execute(
                "SELECT COUNT(1) AS n FROM nodes WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            node_count = int(node_count_row["n"]) if node_count_row else 0
            if node_count < node_count_threshold:
                return None

            # Check if we already have a cached summary that is still fresh
            cached_row = conn.execute(
                "SELECT value_json, updated_at FROM world_variable_status "
                "WHERE project_id = ? AND variable_key = '__arc_summary__' LIMIT 1",
                (project_id,),
            ).fetchone()
            if cached_row:
                cached_summary = self._load_json(str(cached_row["value_json"]), "")
                if isinstance(cached_summary, str) and cached_summary.strip():
                    return cached_summary.strip()

            # Build fresh summary from chunk summaries
            rows = conn.execute(
                "SELECT n.title, c.summary FROM node_chunks c "
                "JOIN nodes n ON n.id = c.node_id AND n.project_id = c.project_id "
                "WHERE c.project_id = ? AND c.summary != '' "
                "ORDER BY n.created_at ASC, c.chunk_index ASC",
                (project_id,),
            ).fetchall()

        if not rows:
            return None

        # Condense: take first line of each chunk summary, group by node title
        segments: list[str] = []
        current_title = ""
        budget = max_summary_chars
        for row in rows:
            title = str(row["title"]).strip()
            summary_line = str(row["summary"]).strip().split("\n")[0][:200]
            if not summary_line:
                continue
            if title != current_title:
                current_title = title
                header = f"[{title}]"
                if len(header) + 2 > budget:
                    break
                segments.append(header)
                budget -= len(header) + 1
            if len(summary_line) > budget:
                break
            segments.append(f"  {summary_line}")
            budget -= len(summary_line) + 3

        arc_text = "\n".join(segments).strip()
        if not arc_text:
            return None

        # Persist for caching
        self._upsert_arc_summary_cache(project_id, arc_text)
        return arc_text

    def _upsert_arc_summary_cache(self, project_id: str, summary_text: str) -> None:
        now_iso = self._now_iso()
        summary_json = self._dump_json(summary_text)
        with self.repository.store.transaction() as conn:
            existing = conn.execute(
                "SELECT 1 FROM world_variable_status "
                "WHERE project_id = ? AND variable_key = '__arc_summary__' LIMIT 1",
                (project_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE world_variable_status SET value_json = ?, updated_at = ? "
                    "WHERE project_id = ? AND variable_key = '__arc_summary__'",
                    (summary_json, now_iso, project_id),
                )
            else:
                conn.execute(
                    "INSERT INTO world_variable_status "
                    "(project_id, variable_key, value_json, last_event_id, updated_at) "
                    "VALUES (?, '__arc_summary__', ?, '', ?)",
                    (project_id, summary_json, now_iso),
                )

    def list_state_conflicts(
        self,
        project_id: str,
        *,
        unresolved_only: bool = True,
    ) -> list[dict[str, Any]]:
        self._require_project(project_id)
        sql = "SELECT * FROM state_conflicts WHERE project_id = ?"
        params: list[Any] = [project_id]
        if unresolved_only:
            sql += " AND resolved = 0"
        sql += " ORDER BY created_at DESC, id DESC"
        with self.repository.store.read_only() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "node_id": row["node_id"],
                "conflict_type": row["conflict_type"],
                "detail": self._load_json(str(row["detail_json"]), {}),
                "resolved": bool(row["resolved"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def audit_state_consistency(
        self,
        project_id: str,
        *,
        record_conflicts: bool = True,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        issues: list[dict[str, Any]] = []

        with self.repository.store.transaction() as conn:
            char_rows = conn.execute(
                "SELECT character_id, held_items_json FROM character_status WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            item_rows = conn.execute(
                "SELECT item_id, owner_character_id, destroyed FROM item_status WHERE project_id = ?",
                (project_id,),
            ).fetchall()

            char_holds: dict[str, list[str]] = {}
            item_holders: dict[str, list[str]] = {}
            for row in char_rows:
                character_id = str(row["character_id"])
                held_items = self._load_json(str(row["held_items_json"]), [])
                normalized = [str(item) for item in held_items] if isinstance(held_items, list) else []
                char_holds[character_id] = normalized
                for item_id in normalized:
                    item_holders.setdefault(item_id, []).append(character_id)

            item_map = {
                str(row["item_id"]): {
                    "owner_character_id": str(row["owner_character_id"] or ""),
                    "destroyed": bool(row["destroyed"]),
                }
                for row in item_rows
            }

            for item_id, holders in item_holders.items():
                if len(holders) > 1:
                    issues.append(
                        {
                            "type": "unique_item_multi_holder",
                            "item_id": item_id,
                            "holders": holders,
                        }
                    )

            for item_id, info in item_map.items():
                owner = str(info["owner_character_id"])
                destroyed = bool(info["destroyed"])
                if destroyed and owner:
                    issues.append(
                        {
                            "type": "destroyed_item_has_owner",
                            "item_id": item_id,
                            "owner_character_id": owner,
                        }
                    )
                if owner:
                    holder_items = char_holds.get(owner, [])
                    if item_id not in holder_items:
                        issues.append(
                            {
                                "type": "item_owner_holder_mismatch",
                                "item_id": item_id,
                                "owner_character_id": owner,
                            }
                        )

            for character_id, items in char_holds.items():
                for item_id in items:
                    item = item_map.get(item_id)
                    if item is None:
                        issues.append(
                            {
                                "type": "held_item_missing_status",
                                "character_id": character_id,
                                "item_id": item_id,
                            }
                        )
                        continue
                    if str(item["owner_character_id"]) != character_id:
                        issues.append(
                            {
                                "type": "item_owner_holder_mismatch",
                                "character_id": character_id,
                                "item_id": item_id,
                                "owner_character_id": item["owner_character_id"],
                            }
                        )

            if record_conflicts:
                for issue in issues:
                    self._record_conflict(
                        conn,
                        project_id=project_id,
                        node_id="audit",
                        conflict_type=str(issue.get("type") or "state_consistency_issue"),
                        detail=issue,
                        blocking=False,
                    )

        return {
            "project_id": project_id,
            "issue_count": len(issues),
            "issues": issues,
            "record_conflicts": record_conflicts,
        }

    def rebuild_state_snapshot(
        self,
        project_id: str,
        upto_revision: int | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        cutoff: str | None = None
        if upto_revision is not None:
            if upto_revision < 0:
                raise ValueError(tr("err.revision_non_negative"))
            with self.repository.store.read_only() as conn:
                row = conn.execute(
                    """
                    SELECT created_at FROM operation_logs
                    WHERE project_id = ? AND revision <= ?
                    ORDER BY revision DESC, created_at DESC
                    LIMIT 1
                    """,
                    (project_id, upto_revision),
                ).fetchone()
            if row:
                cutoff = str(row["created_at"])

        replay_stats = {
            "character_events": 0,
            "item_events": 0,
            "relationship_events": 0,
            "world_variable_events": 0,
            "conflicts": 0,
        }

        with self.repository.store.transaction() as conn:
            conn.execute("DELETE FROM character_status WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM item_status WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM relationship_status WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM world_variable_status WHERE project_id = ?", (project_id,))

            char_sql = (
                "SELECT * FROM character_state_events WHERE project_id = ? "
                + ("AND created_at <= ? " if cutoff else "")
                + "ORDER BY created_at ASC, id ASC"
            )
            item_sql = (
                "SELECT * FROM item_state_events WHERE project_id = ? "
                + ("AND created_at <= ? " if cutoff else "")
                + "ORDER BY created_at ASC, id ASC"
            )
            rel_sql = (
                "SELECT * FROM relationship_state_events WHERE project_id = ? "
                + ("AND created_at <= ? " if cutoff else "")
                + "ORDER BY created_at ASC, id ASC"
            )
            world_sql = (
                "SELECT * FROM world_variable_events WHERE project_id = ? "
                + ("AND created_at <= ? " if cutoff else "")
                + "ORDER BY created_at ASC, id ASC"
            )
            params = (project_id, cutoff) if cutoff else (project_id,)

            for row in conn.execute(char_sql, params).fetchall():
                payload = self._load_json(str(row["payload_json"]), {})
                event = {
                    "entity_type": "character",
                    "canonical_id": row["character_id"],
                    "event_type": row["event_type"],
                    "payload": payload,
                    "source_excerpt": row["source_excerpt"],
                    "confidence": row["confidence"],
                }
                if not self._apply_character_event(
                    conn,
                    project_id=project_id,
                    node_id=str(row["node_id"]),
                    proposal_id="rebuild",
                    event=event,
                    event_id=str(row["id"]),
                    persist_event=False,
                ):
                    replay_stats["conflicts"] += 1
                replay_stats["character_events"] += 1

            for row in conn.execute(item_sql, params).fetchall():
                payload = self._load_json(str(row["payload_json"]), {})
                event = {
                    "entity_type": "item",
                    "canonical_id": row["item_id"],
                    "event_type": row["event_type"],
                    "payload": payload,
                    "source_excerpt": row["source_excerpt"],
                    "confidence": row["confidence"],
                }
                if not self._apply_item_event(
                    conn,
                    project_id=project_id,
                    node_id=str(row["node_id"]),
                    proposal_id="rebuild",
                    event=event,
                    event_id=str(row["id"]),
                    persist_event=False,
                ):
                    replay_stats["conflicts"] += 1
                replay_stats["item_events"] += 1

            for row in conn.execute(rel_sql, params).fetchall():
                payload = self._load_json(str(row["payload_json"]), {})
                event = {
                    "entity_type": "relationship",
                    "subject_character_id": row["subject_character_id"],
                    "object_character_id": row["object_character_id"],
                    "event_type": row["event_type"],
                    "payload": payload,
                    "source_excerpt": row["source_excerpt"],
                    "confidence": row["confidence"],
                }
                if not self._apply_relationship_event(
                    conn,
                    project_id=project_id,
                    node_id=str(row["node_id"]),
                    proposal_id="rebuild",
                    event=event,
                    event_id=str(row["id"]),
                    persist_event=False,
                ):
                    replay_stats["conflicts"] += 1
                replay_stats["relationship_events"] += 1

            for row in conn.execute(world_sql, params).fetchall():
                payload = self._load_json(str(row["payload_json"]), {})
                event = {
                    "entity_type": "world_variable",
                    "variable_key": row["variable_key"],
                    "event_type": row["event_type"],
                    "payload": payload,
                    "source_excerpt": row["source_excerpt"],
                    "confidence": row["confidence"],
                }
                if not self._apply_world_variable_event(
                    conn,
                    project_id=project_id,
                    node_id=str(row["node_id"]),
                    proposal_id="rebuild",
                    event=event,
                    event_id=str(row["id"]),
                    persist_event=False,
                ):
                    replay_stats["conflicts"] += 1
                replay_stats["world_variable_events"] += 1

        return {
            "project_id": project_id,
            "upto_revision": upto_revision,
            "cutoff_created_at": cutoff,
            **replay_stats,
        }

    def resolve_entity_alias(
        self,
        project_id: str,
        entity_type: str,
        alias: str,
    ) -> str | None:
        self._require_project(project_id)
        normalized_entity = self._normalize_entity_type(entity_type)
        normalized_alias = self._normalize_alias(alias)
        if not normalized_alias:
            return None
        with self.repository.store.read_only() as conn:
            row = conn.execute(
                """
                SELECT canonical_id FROM entity_aliases
                WHERE project_id = ? AND entity_type = ? AND alias = ?
                LIMIT 1
                """,
                (project_id, normalized_entity, normalized_alias),
            ).fetchone()
        return str(row["canonical_id"]) if row else None

    def upsert_entity_alias(
        self,
        project_id: str,
        entity_type: str,
        alias: str,
        canonical_id: str,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        normalized_entity = self._normalize_entity_type(entity_type)
        normalized_alias = self._normalize_alias(alias)
        canonical = str(canonical_id or "").strip()
        if normalized_entity not in {"character", "item"}:
            raise ValueError("entity_type must be character or item")
        if not normalized_alias:
            raise ValueError("alias cannot be empty")
        if not canonical:
            raise ValueError("canonical_id cannot be empty")
        score = self._normalize_confidence(confidence)
        now_iso = self._now_iso()
        alias_id = generate_id("stal")

        with self.repository.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO entity_aliases(
                    id, project_id, entity_type, alias, canonical_id, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, entity_type, alias)
                DO UPDATE SET
                    canonical_id = excluded.canonical_id,
                    confidence = excluded.confidence,
                    created_at = excluded.created_at
                """,
                (
                    alias_id,
                    project_id,
                    normalized_entity,
                    normalized_alias,
                    canonical,
                    score,
                    now_iso,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM entity_aliases
                WHERE project_id = ? AND entity_type = ? AND alias = ?
                LIMIT 1
                """,
                (project_id, normalized_entity, normalized_alias),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to upsert entity alias")
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "entity_type": row["entity_type"],
            "alias": row["alias"],
            "canonical_id": row["canonical_id"],
            "confidence": float(row["confidence"]),
            "created_at": row["created_at"],
        }

    def upsert_state_attribute_schema(
        self,
        project_id: str,
        entity_type: str,
        attr_key: str,
        value_type: str,
        constraints: dict[str, Any] | None = None,
        *,
        description: str = "",
        is_active: bool = True,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        normalized_entity = self._normalize_entity_type(entity_type)
        if normalized_entity not in {"character", "item"}:
            raise ValueError("entity_type must be character or item")
        key = str(attr_key or "").strip()
        if not key:
            raise ValueError("attr_key cannot be empty")
        normalized_value_type = str(value_type or "").strip().lower()
        if normalized_value_type not in {"number", "string", "bool", "enum", "json"}:
            raise ValueError("value_type must be one of number|string|bool|enum|json")

        now_iso = self._now_iso()
        schema_id = generate_id("stas")
        with self.repository.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO state_attribute_schema(
                    id, project_id, entity_type, attr_key, value_type,
                    description, constraints_json, is_active, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, entity_type, attr_key)
                DO UPDATE SET
                    value_type = excluded.value_type,
                    description = excluded.description,
                    constraints_json = excluded.constraints_json,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at
                """,
                (
                    schema_id,
                    project_id,
                    normalized_entity,
                    key,
                    normalized_value_type,
                    str(description or "").strip(),
                    self._dump_json(constraints or {}),
                    1 if is_active else 0,
                    now_iso,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM state_attribute_schema
                WHERE project_id = ? AND entity_type = ? AND attr_key = ?
                LIMIT 1
                """,
                (project_id, normalized_entity, key),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to upsert state attribute schema")
        return self._decode_schema_row(row)

    def list_state_attribute_schema(
        self,
        project_id: str,
        entity_type: str,
    ) -> list[dict[str, Any]]:
        self._require_project(project_id)
        normalized_entity = self._normalize_entity_type(entity_type)
        with self.repository.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT * FROM state_attribute_schema
                WHERE project_id = ? AND entity_type = ?
                ORDER BY attr_key ASC
                """,
                (project_id, normalized_entity),
            ).fetchall()
        return [self._decode_schema_row(row) for row in rows]

    def _apply_single_event_from_proposal(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        node_id: str,
        proposal_id: str,
        event: dict[str, Any],
    ) -> bool:
        normalized = self._normalize_event(event)
        entity_type = normalized["entity_type"]
        if entity_type == "character":
            return self._apply_character_event(
                conn,
                project_id=project_id,
                node_id=node_id,
                proposal_id=proposal_id,
                event=normalized,
            )
        if entity_type == "item":
            return self._apply_item_event(
                conn,
                project_id=project_id,
                node_id=node_id,
                proposal_id=proposal_id,
                event=normalized,
            )
        if entity_type == "relationship":
            return self._apply_relationship_event(
                conn,
                project_id=project_id,
                node_id=node_id,
                proposal_id=proposal_id,
                event=normalized,
            )
        if entity_type == "world_variable":
            return self._apply_world_variable_event(
                conn,
                project_id=project_id,
                node_id=node_id,
                proposal_id=proposal_id,
                event=normalized,
            )
        self._record_conflict(
            conn,
            project_id=project_id,
            node_id=node_id,
            conflict_type="unsupported_entity_type",
            detail={"proposal_id": proposal_id, "entity_type": entity_type},
        )
        return False

    def _apply_character_event(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        node_id: str,
        proposal_id: str,
        event: dict[str, Any],
        event_id: str | None = None,
        persist_event: bool = True,
    ) -> bool:
        now_iso = self._now_iso()
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        character_id = self._resolve_entity_id_for_event(
            conn,
            project_id=project_id,
            event=event,
            entity_type="character",
        )
        if not character_id:
            self._record_conflict(
                conn,
                project_id=project_id,
                node_id=node_id,
                conflict_type="entity_ambiguous",
                detail={
                    "proposal_id": proposal_id,
                    "entity_type": "character",
                    "event": event,
                },
            )
            return False

        kind = str(event.get("event_type", "")).strip()
        event_record_id = event_id or generate_id("stce")
        char_state = self._load_character_status(conn, project_id, character_id)
        attr_updates: dict[str, Any] = {}

        if kind == "move":
            destination = str(payload.get("to") or payload.get("location") or "").strip()
            if destination:
                char_state["location"] = destination
        elif kind == "alive_change":
            alive = bool(payload.get("alive", False))
            char_state["alive"] = alive
            if not alive:
                # Dropping held items avoids stale multi-hold artifacts after death.
                death_location = str(char_state.get("location", "") or "").strip()
                for item_id in list(char_state["held_items"]):
                    item_state = self._load_item_status(conn, project_id, item_id)
                    if item_state["owner_character_id"] == character_id:
                        item_state["owner_character_id"] = ""
                        if death_location:
                            item_state["location"] = death_location
                        item_state["last_event_id"] = event_record_id
                        item_state["updated_at"] = now_iso
                        self._save_item_status(conn, item_state)
                char_state["held_items"] = []
        elif kind == "faction_change":
            faction = str(payload.get("faction") or payload.get("to") or "").strip()
            if faction:
                char_state["faction"] = faction
        elif kind == "hold_item":
            item_id = self._resolve_item_id_from_payload(conn, project_id, payload)
            if not item_id:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="entity_ambiguous",
                    detail={
                        "proposal_id": proposal_id,
                        "entity_type": "item",
                        "event": event,
                    },
                )
                return False
            if not char_state["alive"]:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="dead_character_hold_item",
                    detail={
                        "proposal_id": proposal_id,
                        "character_id": character_id,
                        "item_id": item_id,
                    },
                )
                return False
            item_state = self._load_item_status(conn, project_id, item_id)
            if item_state["destroyed"]:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="destroyed_item_transfer",
                    detail={
                        "proposal_id": proposal_id,
                        "character_id": character_id,
                        "item_id": item_id,
                    },
                )
                return False
            holders = self._find_item_holders(conn, project_id, item_id)
            if len(holders) > 1:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="unique_item_multi_holder",
                    detail={
                        "proposal_id": proposal_id,
                        "item_id": item_id,
                        "holders": holders,
                    },
                    blocking=False,
                )
            self._remove_item_from_all_holders(
                conn,
                project_id=project_id,
                item_id=item_id,
                keep_character_id=character_id,
                event_id=event_record_id,
                now_iso=now_iso,
            )
            if item_id not in char_state["held_items"]:
                char_state["held_items"].append(item_id)
            if char_state["location"] and item_state["location"] and char_state["location"] != item_state["location"]:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="location_mismatch_warning",
                    detail={
                        "proposal_id": proposal_id,
                        "character_id": character_id,
                        "item_id": item_id,
                        "character_location": char_state["location"],
                        "item_location": item_state["location"],
                    },
                    blocking=False,
                )
            item_state["owner_character_id"] = character_id
            if char_state["location"]:
                item_state["location"] = char_state["location"]
            item_state["last_event_id"] = event_record_id
            item_state["updated_at"] = now_iso
            self._save_item_status(conn, item_state)
        elif kind == "drop_item":
            item_id = self._resolve_item_id_from_payload(conn, project_id, payload)
            if not item_id:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="entity_ambiguous",
                    detail={"proposal_id": proposal_id, "entity_type": "item", "event": event},
                )
                return False
            char_state["held_items"] = [item for item in char_state["held_items"] if item != item_id]
            item_state = self._load_item_status(conn, project_id, item_id)
            if item_state["owner_character_id"] == character_id:
                item_state["owner_character_id"] = ""
                if char_state["location"] and not item_state["location"]:
                    item_state["location"] = char_state["location"]
                item_state["last_event_id"] = event_record_id
                item_state["updated_at"] = now_iso
                self._save_item_status(conn, item_state)
        elif kind in {"mood_change", "injury_change", "finance_change"}:
            mapped_key = {
                "mood_change": "mood",
                "injury_change": "injury",
                "finance_change": "finance",
            }[kind]
            if mapped_key in payload:
                attr_updates[mapped_key] = payload[mapped_key]
            elif "value" in payload:
                attr_updates[mapped_key] = payload["value"]
            else:
                attr_updates[mapped_key] = payload
        elif kind == "custom":
            if "alive" in payload:
                char_state["alive"] = bool(payload["alive"])
            if "location" in payload:
                char_state["location"] = str(payload["location"] or "").strip()
            if "faction" in payload:
                char_state["faction"] = str(payload["faction"] or "").strip()

        raw_state_attrs = payload.get("state_attributes")
        if isinstance(raw_state_attrs, dict):
            attr_updates.update(raw_state_attrs)

        if attr_updates:
            err = self._validate_state_attributes(
                conn,
                project_id=project_id,
                entity_type="character",
                attrs=attr_updates,
            )
            if err:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="attribute_schema_violation",
                    detail={
                        "proposal_id": proposal_id,
                        "character_id": character_id,
                        "errors": err,
                        "attrs": attr_updates,
                    },
                )
                return False
            char_state["state_attributes"].update(attr_updates)

        if persist_event:
            conn.execute(
                """
                INSERT INTO character_state_events(
                    id, project_id, node_id, character_id, event_type,
                    payload_json, source_excerpt, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_record_id,
                    project_id,
                    node_id,
                    character_id,
                    kind,
                    self._dump_json(payload),
                    str(event.get("source_excerpt", "")),
                    self._normalize_confidence(event.get("confidence", 0.0)),
                    now_iso,
                ),
            )

        char_state["last_event_id"] = event_record_id
        char_state["updated_at"] = now_iso
        self._save_character_status(conn, char_state)
        return True

    def _apply_item_event(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        node_id: str,
        proposal_id: str,
        event: dict[str, Any],
        event_id: str | None = None,
        persist_event: bool = True,
    ) -> bool:
        now_iso = self._now_iso()
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        item_id = self._resolve_entity_id_for_event(
            conn,
            project_id=project_id,
            event=event,
            entity_type="item",
        )
        if not item_id:
            self._record_conflict(
                conn,
                project_id=project_id,
                node_id=node_id,
                conflict_type="entity_ambiguous",
                detail={"proposal_id": proposal_id, "entity_type": "item", "event": event},
            )
            return False

        kind = str(event.get("event_type", "")).strip()
        event_record_id = event_id or generate_id("stie")
        item_state = self._load_item_status(conn, project_id, item_id)
        attr_updates: dict[str, Any] = {}

        if kind == "owner_change":
            if item_state["destroyed"]:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="destroyed_item_transfer",
                    detail={"proposal_id": proposal_id, "item_id": item_id},
                )
                return False
            owner_id = str(
                payload.get("owner_character_id")
                or payload.get("owner")
                or payload.get("to_character_id")
                or ""
            ).strip()
            if not owner_id:
                mention = str(payload.get("owner_mention") or "").strip()
                if mention:
                    owner_id = self.resolve_entity_alias(project_id, "character", mention) or ""
            if owner_id:
                owner_status = self._load_character_status(conn, project_id, owner_id)
                if not owner_status["alive"]:
                    self._record_conflict(
                        conn,
                        project_id=project_id,
                        node_id=node_id,
                        conflict_type="dead_character_hold_item",
                        detail={
                            "proposal_id": proposal_id,
                            "character_id": owner_id,
                            "item_id": item_id,
                        },
                    )
                    return False
                if item_state["owner_character_id"] and item_state["owner_character_id"] != owner_id:
                    prev_owner = self._load_character_status(
                        conn,
                        project_id,
                        item_state["owner_character_id"],
                    )
                    prev_owner["held_items"] = [
                        item for item in prev_owner["held_items"] if item != item_id
                    ]
                    prev_owner["last_event_id"] = event_record_id
                    prev_owner["updated_at"] = now_iso
                    self._save_character_status(conn, prev_owner)
                owner_status["held_items"] = [
                    item for item in owner_status["held_items"] if item != item_id
                ]
                owner_status["held_items"].append(item_id)
                owner_status["last_event_id"] = event_record_id
                owner_status["updated_at"] = now_iso
                self._save_character_status(conn, owner_status)
                item_state["owner_character_id"] = owner_id
                if owner_status["location"]:
                    item_state["location"] = owner_status["location"]
            else:
                if item_state["owner_character_id"]:
                    prev_owner = self._load_character_status(
                        conn,
                        project_id,
                        item_state["owner_character_id"],
                    )
                    prev_owner["held_items"] = [
                        item for item in prev_owner["held_items"] if item != item_id
                    ]
                    prev_owner["last_event_id"] = event_record_id
                    prev_owner["updated_at"] = now_iso
                    self._save_character_status(conn, prev_owner)
                item_state["owner_character_id"] = ""
        elif kind == "location_change":
            location = str(payload.get("location") or payload.get("to") or "").strip()
            if location:
                item_state["location"] = location
        elif kind == "destroyed":
            destroyed = bool(payload.get("destroyed", True))
            item_state["destroyed"] = destroyed
            if destroyed:
                owner_id = item_state["owner_character_id"]
                if owner_id:
                    owner_state = self._load_character_status(conn, project_id, owner_id)
                    owner_state["held_items"] = [
                        item for item in owner_state["held_items"] if item != item_id
                    ]
                    owner_state["last_event_id"] = event_record_id
                    owner_state["updated_at"] = now_iso
                    self._save_character_status(conn, owner_state)
                item_state["owner_character_id"] = ""
        elif kind in {"hidden", "custom"}:
            if "location" in payload:
                item_state["location"] = str(payload["location"] or "").strip()
            if "destroyed" in payload:
                item_state["destroyed"] = bool(payload["destroyed"])

        raw_state_attrs = payload.get("state_attributes")
        if isinstance(raw_state_attrs, dict):
            attr_updates.update(raw_state_attrs)
        if kind == "hidden":
            attr_updates.setdefault("hidden", bool(payload.get("hidden", True)))

        if attr_updates:
            err = self._validate_state_attributes(
                conn,
                project_id=project_id,
                entity_type="item",
                attrs=attr_updates,
            )
            if err:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="attribute_schema_violation",
                    detail={
                        "proposal_id": proposal_id,
                        "item_id": item_id,
                        "errors": err,
                        "attrs": attr_updates,
                    },
                )
                return False
            item_state["state_attributes"].update(attr_updates)

        if persist_event:
            conn.execute(
                """
                INSERT INTO item_state_events(
                    id, project_id, node_id, item_id, event_type,
                    payload_json, source_excerpt, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_record_id,
                    project_id,
                    node_id,
                    item_id,
                    kind,
                    self._dump_json(payload),
                    str(event.get("source_excerpt", "")),
                    self._normalize_confidence(event.get("confidence", 0.0)),
                    now_iso,
                ),
            )

        item_state["last_event_id"] = event_record_id
        item_state["updated_at"] = now_iso
        self._save_item_status(conn, item_state)
        return True

    def _apply_relationship_event(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        node_id: str,
        proposal_id: str,
        event: dict[str, Any],
        event_id: str | None = None,
        persist_event: bool = True,
    ) -> bool:
        now_iso = self._now_iso()
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        subject = str(event.get("subject_character_id") or "").strip()
        object_ = str(event.get("object_character_id") or "").strip()
        if not subject:
            subject = self._resolve_entity_alias_from_payload(
                project_id,
                payload,
                key="subject_mention",
                entity_type="character",
            )
        if not object_:
            object_ = self._resolve_entity_alias_from_payload(
                project_id,
                payload,
                key="object_mention",
                entity_type="character",
            )
        if not subject or not object_:
            self._record_conflict(
                conn,
                project_id=project_id,
                node_id=node_id,
                conflict_type="entity_ambiguous",
                detail={
                    "proposal_id": proposal_id,
                    "entity_type": "relationship",
                    "event": event,
                },
            )
            return False

        kind = str(event.get("event_type", "")).strip()
        event_record_id = event_id or generate_id("stre")
        rel_state = self._load_relationship_status(conn, project_id, subject, object_)
        attr_updates: dict[str, Any] = {}

        if kind == "relation_change":
            next_relation = str(
                payload.get("relation_type")
                or payload.get("to")
                or payload.get("value")
                or ""
            ).strip()
            current_relation = str(rel_state.get("relation_type") or "").strip().lower()
            if (
                current_relation in {"enemy", "hostile", "仇敌", "敌对"}
                and next_relation.lower() in {"ally", "friend", "亲密", "同盟"}
                and not bool(payload.get("transition"))
            ):
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="relationship_inconsistency",
                    detail={
                        "proposal_id": proposal_id,
                        "subject_character_id": subject,
                        "object_character_id": object_,
                        "from": rel_state.get("relation_type", ""),
                        "to": next_relation,
                    },
                    blocking=False,
                )
            rel_state["relation_type"] = next_relation
        elif kind in {"trust_change", "hostility_change", "alliance_change"}:
            mapped_key = {
                "trust_change": "trust",
                "hostility_change": "hostility",
                "alliance_change": "alliance",
            }[kind]
            if "delta" in payload and isinstance(payload["delta"], (int, float)) and not isinstance(
                payload["delta"], bool
            ):
                current = rel_state["state_attributes"].get(mapped_key)
                base = current if isinstance(current, (int, float)) and not isinstance(current, bool) else 0
                attr_updates[mapped_key] = base + payload["delta"]
            elif "value" in payload:
                attr_updates[mapped_key] = payload["value"]
            else:
                attr_updates[mapped_key] = payload
        elif kind == "custom":
            if "relation_type" in payload:
                rel_state["relation_type"] = str(payload["relation_type"] or "").strip()

        raw_state_attrs = payload.get("state_attributes")
        if isinstance(raw_state_attrs, dict):
            attr_updates.update(raw_state_attrs)
        if attr_updates:
            rel_state["state_attributes"].update(attr_updates)

        if persist_event:
            conn.execute(
                """
                INSERT INTO relationship_state_events(
                    id, project_id, node_id, subject_character_id, object_character_id,
                    event_type, payload_json, source_excerpt, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_record_id,
                    project_id,
                    node_id,
                    subject,
                    object_,
                    kind,
                    self._dump_json(payload),
                    str(event.get("source_excerpt", "")),
                    self._normalize_confidence(event.get("confidence", 0.0)),
                    now_iso,
                ),
            )

        rel_state["last_event_id"] = event_record_id
        rel_state["updated_at"] = now_iso
        self._save_relationship_status(conn, rel_state)
        return True

    def _apply_world_variable_event(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        node_id: str,
        proposal_id: str,
        event: dict[str, Any],
        event_id: str | None = None,
        persist_event: bool = True,
    ) -> bool:
        now_iso = self._now_iso()
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        variable_key = str(event.get("variable_key") or payload.get("variable_key") or "").strip()
        if not variable_key:
            variable_key = str(event.get("canonical_id") or "").strip()
        if not variable_key:
            self._record_conflict(
                conn,
                project_id=project_id,
                node_id=node_id,
                conflict_type="entity_ambiguous",
                detail={
                    "proposal_id": proposal_id,
                    "entity_type": "world_variable",
                    "event": event,
                },
            )
            return False

        kind = str(event.get("event_type", "")).strip()
        event_record_id = event_id or generate_id("stwe")
        world_state = self._load_world_variable_status(conn, project_id, variable_key)
        current_value = world_state.get("value")

        if kind == "set":
            next_value = payload["value"] if "value" in payload else payload
            if current_value is not None and current_value != next_value and not bool(payload.get("transition")):
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="world_state_inconsistency",
                    detail={
                        "proposal_id": proposal_id,
                        "variable_key": variable_key,
                        "from": current_value,
                        "to": next_value,
                    },
                    blocking=False,
                )
            world_state["value"] = next_value
        elif kind == "increase":
            delta = payload.get("delta", payload.get("value", 0))
            if isinstance(delta, (int, float)) and not isinstance(delta, bool):
                base = current_value if isinstance(current_value, (int, float)) and not isinstance(current_value, bool) else 0
                world_state["value"] = base + delta
            else:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="invalid_world_variable_delta",
                    detail={
                        "proposal_id": proposal_id,
                        "variable_key": variable_key,
                        "delta": delta,
                    },
                )
                return False
        elif kind == "decrease":
            delta = payload.get("delta", payload.get("value", 0))
            if isinstance(delta, (int, float)) and not isinstance(delta, bool):
                base = current_value if isinstance(current_value, (int, float)) and not isinstance(current_value, bool) else 0
                world_state["value"] = base - delta
            else:
                self._record_conflict(
                    conn,
                    project_id=project_id,
                    node_id=node_id,
                    conflict_type="invalid_world_variable_delta",
                    detail={
                        "proposal_id": proposal_id,
                        "variable_key": variable_key,
                        "delta": delta,
                    },
                )
                return False
        elif kind in {"transfer_control", "weather_change", "custom"}:
            if "value" in payload:
                world_state["value"] = payload["value"]
            elif kind == "transfer_control":
                world_state["value"] = {
                    "owner": payload.get("owner") or payload.get("to") or payload.get("target"),
                    "source": payload.get("source") or payload.get("from"),
                }
            elif kind == "weather_change":
                world_state["value"] = payload.get("weather")
            else:
                world_state["value"] = payload

        if persist_event:
            conn.execute(
                """
                INSERT INTO world_variable_events(
                    id, project_id, node_id, variable_key, event_type,
                    payload_json, source_excerpt, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_record_id,
                    project_id,
                    node_id,
                    variable_key,
                    kind,
                    self._dump_json(payload),
                    str(event.get("source_excerpt", "")),
                    self._normalize_confidence(event.get("confidence", 0.0)),
                    now_iso,
                ),
            )

        world_state["last_event_id"] = event_record_id
        world_state["updated_at"] = now_iso
        self._save_world_variable_status(conn, world_state)
        return True

    def _load_proposals_for_apply(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        proposal_ids: list[str],
    ) -> list[sqlite3.Row]:
        if proposal_ids:
            placeholders = ",".join("?" for _ in proposal_ids)
            rows = conn.execute(
                f"""
                SELECT * FROM state_change_proposals
                WHERE project_id = ? AND id IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                (project_id, *proposal_ids),
            ).fetchall()
            by_id = {str(row["id"]): row for row in rows}
            approved_rows: list[sqlite3.Row] = []
            for proposal_id in proposal_ids:
                row = by_id.get(proposal_id)
                if row is None:
                    self._record_conflict(
                        conn,
                        project_id=project_id,
                        node_id=node_id,
                        conflict_type="unapproved_state_write",
                        detail={
                            "proposal_id": proposal_id,
                            "reason": "proposal not found",
                        },
                    )
                    continue
                if str(row["node_id"]) != node_id or str(row["thread_id"]) != thread_id:
                    self._record_conflict(
                        conn,
                        project_id=project_id,
                        node_id=node_id,
                        conflict_type="unapproved_state_write",
                        detail={
                            "proposal_id": proposal_id,
                            "reason": "proposal scope mismatch",
                            "expected_node_id": node_id,
                            "expected_thread_id": thread_id,
                            "actual_node_id": row["node_id"],
                            "actual_thread_id": row["thread_id"],
                        },
                    )
                    continue
                if str(row["status"]) != "approved":
                    self._record_conflict(
                        conn,
                        project_id=project_id,
                        node_id=node_id,
                        conflict_type="unapproved_state_write",
                        detail={
                            "proposal_id": proposal_id,
                            "status": row["status"],
                        },
                    )
                    continue
                if str(row["applied_at"] or "").strip():
                    # Idempotent repeated apply: already done, skip silently.
                    continue
                approved_rows.append(row)
            return approved_rows

        return conn.execute(
            """
            SELECT * FROM state_change_proposals
            WHERE project_id = ?
              AND node_id = ?
              AND thread_id = ?
              AND status = 'approved'
              AND applied_at = ''
            ORDER BY created_at ASC, rowid ASC
            """,
            (project_id, node_id, thread_id),
        ).fetchall()

    def _find_item_holders(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        item_id: str,
    ) -> list[str]:
        rows = conn.execute(
            "SELECT character_id, held_items_json FROM character_status WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        holders: list[str] = []
        for row in rows:
            held_items = self._load_json(str(row["held_items_json"]), [])
            if isinstance(held_items, list) and item_id in [str(item) for item in held_items]:
                holders.append(str(row["character_id"]))
        return holders

    def _remove_item_from_all_holders(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        item_id: str,
        keep_character_id: str,
        event_id: str,
        now_iso: str,
    ) -> None:
        rows = conn.execute(
            "SELECT * FROM character_status WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        for row in rows:
            character_id = str(row["character_id"])
            if character_id == keep_character_id:
                continue
            held_items = self._load_json(str(row["held_items_json"]), [])
            if not isinstance(held_items, list):
                continue
            normalized = [str(item) for item in held_items]
            if item_id not in normalized:
                continue
            normalized = [item for item in normalized if item != item_id]
            conn.execute(
                """
                UPDATE character_status
                SET held_items_json = ?, last_event_id = ?, updated_at = ?
                WHERE project_id = ? AND character_id = ?
                """,
                (
                    self._dump_json(normalized),
                    event_id,
                    now_iso,
                    project_id,
                    character_id,
                ),
            )

    def _resolve_item_id_from_payload(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        payload: dict[str, Any],
    ) -> str:
        item_id = str(
            payload.get("item_id")
            or payload.get("canonical_item_id")
            or payload.get("target_item_id")
            or ""
        ).strip()
        if item_id:
            return item_id
        mention = str(payload.get("item_mention") or payload.get("item") or "").strip()
        if mention:
            return self.resolve_entity_alias(project_id, "item", mention) or ""
        return ""

    def _resolve_entity_alias_from_payload(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        key: str,
        entity_type: str,
    ) -> str:
        mention = str(payload.get(key) or "").strip()
        if not mention:
            return ""
        return self.resolve_entity_alias(project_id, entity_type, mention) or ""

    def _resolve_entity_id_for_event(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        event: dict[str, Any],
        entity_type: str,
    ) -> str:
        canonical = str(event.get("canonical_id") or "").strip()
        if canonical:
            return canonical
        mention = str(event.get("raw_mention") or "").strip()
        if mention:
            resolved = self.resolve_entity_alias(project_id, entity_type, mention)
            if resolved:
                return resolved

            # Fall back to exact canonical match if mention already equals an existing entity id.
            table = "character_status" if entity_type == "character" else "item_status"
            field = "character_id" if entity_type == "character" else "item_id"
            row = conn.execute(
                f"SELECT {field} FROM {table} WHERE project_id = ? AND {field} = ? LIMIT 1",
                (project_id, mention),
            ).fetchone()
            if row:
                return str(row[field])
        return ""

    def _validate_state_attributes(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        entity_type: str,
        attrs: dict[str, Any],
    ) -> list[str]:
        if not attrs:
            return []
        rows = conn.execute(
            """
            SELECT attr_key, value_type, constraints_json
            FROM state_attribute_schema
            WHERE project_id = ? AND entity_type = ? AND is_active = 1
            """,
            (project_id, entity_type),
        ).fetchall()
        schema: dict[str, dict[str, Any]] = {}
        for row in rows:
            schema[str(row["attr_key"])] = {
                "value_type": str(row["value_type"]),
                "constraints": self._load_json(str(row["constraints_json"]), {}),
            }

        errors: list[str] = []
        for key, value in attrs.items():
            spec = schema.get(key)
            if spec is None:
                errors.append(f"{key}: missing_schema")
                continue
            value_type = str(spec.get("value_type") or "")
            constraints = spec.get("constraints")
            if not isinstance(constraints, dict):
                constraints = {}

            if value_type == "number":
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                    errors.append(f"{key}: expect_number")
                    continue
                min_v = constraints.get("min")
                max_v = constraints.get("max")
                if isinstance(min_v, (int, float)) and float(value) < float(min_v):
                    errors.append(f"{key}: below_min")
                if isinstance(max_v, (int, float)) and float(value) > float(max_v):
                    errors.append(f"{key}: above_max")
            elif value_type == "string":
                if not isinstance(value, str):
                    errors.append(f"{key}: expect_string")
            elif value_type == "bool":
                if not isinstance(value, bool):
                    errors.append(f"{key}: expect_bool")
            elif value_type == "enum":
                options = constraints.get("options")
                if not isinstance(options, list) or value not in options:
                    errors.append(f"{key}: invalid_enum")
            elif value_type == "json":
                # Any JSON-serializable value is allowed.
                try:
                    json.dumps(value, ensure_ascii=False)
                except (TypeError, ValueError):
                    errors.append(f"{key}: not_json_serializable")
            else:
                errors.append(f"{key}: unsupported_value_type:{value_type}")

        return errors

    def _load_character_status(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        character_id: str,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT * FROM character_status
            WHERE project_id = ? AND character_id = ?
            LIMIT 1
            """,
            (project_id, character_id),
        ).fetchone()
        if row is None:
            return {
                "project_id": project_id,
                "character_id": character_id,
                "alive": True,
                "location": "",
                "faction": "",
                "held_items": [],
                "state_attributes": {},
                "last_event_id": "",
                "updated_at": self._now_iso(),
            }
        held = self._load_json(str(row["held_items_json"]), [])
        attrs = self._load_json(str(row["state_attributes_json"]), {})
        return {
            "project_id": row["project_id"],
            "character_id": row["character_id"],
            "alive": bool(row["alive"]),
            "location": str(row["location"] or ""),
            "faction": str(row["faction"] or ""),
            "held_items": [str(item) for item in held] if isinstance(held, list) else [],
            "state_attributes": attrs if isinstance(attrs, dict) else {},
            "last_event_id": str(row["last_event_id"] or ""),
            "updated_at": str(row["updated_at"]),
        }

    def _save_character_status(self, conn: sqlite3.Connection, state: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO character_status(
                project_id, character_id, alive, location, faction,
                held_items_json, state_attributes_json, last_event_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, character_id)
            DO UPDATE SET
                alive = excluded.alive,
                location = excluded.location,
                faction = excluded.faction,
                held_items_json = excluded.held_items_json,
                state_attributes_json = excluded.state_attributes_json,
                last_event_id = excluded.last_event_id,
                updated_at = excluded.updated_at
            """,
            (
                state["project_id"],
                state["character_id"],
                1 if state.get("alive", True) else 0,
                str(state.get("location", "")),
                str(state.get("faction", "")),
                self._dump_json(state.get("held_items", [])),
                self._dump_json(state.get("state_attributes", {})),
                str(state.get("last_event_id", "")),
                str(state.get("updated_at", self._now_iso())),
            ),
        )

    def _load_item_status(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        item_id: str,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT * FROM item_status
            WHERE project_id = ? AND item_id = ?
            LIMIT 1
            """,
            (project_id, item_id),
        ).fetchone()
        if row is None:
            return {
                "project_id": project_id,
                "item_id": item_id,
                "owner_character_id": "",
                "location": "",
                "destroyed": False,
                "state_attributes": {},
                "last_event_id": "",
                "updated_at": self._now_iso(),
            }
        attrs = self._load_json(str(row["state_attributes_json"]), {})
        return {
            "project_id": row["project_id"],
            "item_id": row["item_id"],
            "owner_character_id": str(row["owner_character_id"] or ""),
            "location": str(row["location"] or ""),
            "destroyed": bool(row["destroyed"]),
            "state_attributes": attrs if isinstance(attrs, dict) else {},
            "last_event_id": str(row["last_event_id"] or ""),
            "updated_at": str(row["updated_at"]),
        }

    def _save_item_status(self, conn: sqlite3.Connection, state: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO item_status(
                project_id, item_id, owner_character_id, location, destroyed,
                state_attributes_json, last_event_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, item_id)
            DO UPDATE SET
                owner_character_id = excluded.owner_character_id,
                location = excluded.location,
                destroyed = excluded.destroyed,
                state_attributes_json = excluded.state_attributes_json,
                last_event_id = excluded.last_event_id,
                updated_at = excluded.updated_at
            """,
            (
                state["project_id"],
                state["item_id"],
                str(state.get("owner_character_id", "")),
                str(state.get("location", "")),
                1 if state.get("destroyed", False) else 0,
                self._dump_json(state.get("state_attributes", {})),
                str(state.get("last_event_id", "")),
                str(state.get("updated_at", self._now_iso())),
            ),
        )

    def _load_relationship_status(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        subject_character_id: str,
        object_character_id: str,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT * FROM relationship_status
            WHERE project_id = ? AND subject_character_id = ? AND object_character_id = ?
            LIMIT 1
            """,
            (project_id, subject_character_id, object_character_id),
        ).fetchone()
        if row is None:
            return {
                "project_id": project_id,
                "subject_character_id": subject_character_id,
                "object_character_id": object_character_id,
                "relation_type": "",
                "state_attributes": {},
                "last_event_id": "",
                "updated_at": self._now_iso(),
            }
        attrs = self._load_json(str(row["state_attributes_json"]), {})
        return {
            "project_id": row["project_id"],
            "subject_character_id": row["subject_character_id"],
            "object_character_id": row["object_character_id"],
            "relation_type": str(row["relation_type"] or ""),
            "state_attributes": attrs if isinstance(attrs, dict) else {},
            "last_event_id": str(row["last_event_id"] or ""),
            "updated_at": str(row["updated_at"]),
        }

    def _save_relationship_status(self, conn: sqlite3.Connection, state: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO relationship_status(
                project_id, subject_character_id, object_character_id,
                relation_type, state_attributes_json, last_event_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, subject_character_id, object_character_id)
            DO UPDATE SET
                relation_type = excluded.relation_type,
                state_attributes_json = excluded.state_attributes_json,
                last_event_id = excluded.last_event_id,
                updated_at = excluded.updated_at
            """,
            (
                state["project_id"],
                state["subject_character_id"],
                state["object_character_id"],
                str(state.get("relation_type", "")),
                self._dump_json(state.get("state_attributes", {})),
                str(state.get("last_event_id", "")),
                str(state.get("updated_at", self._now_iso())),
            ),
        )

    def _load_world_variable_status(
        self,
        conn: sqlite3.Connection,
        project_id: str,
        variable_key: str,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT * FROM world_variable_status
            WHERE project_id = ? AND variable_key = ?
            LIMIT 1
            """,
            (project_id, variable_key),
        ).fetchone()
        if row is None:
            return {
                "project_id": project_id,
                "variable_key": variable_key,
                "value": None,
                "last_event_id": "",
                "updated_at": self._now_iso(),
            }
        return {
            "project_id": row["project_id"],
            "variable_key": row["variable_key"],
            "value": self._load_json(str(row["value_json"]), None),
            "last_event_id": str(row["last_event_id"] or ""),
            "updated_at": str(row["updated_at"]),
        }

    def _save_world_variable_status(self, conn: sqlite3.Connection, state: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO world_variable_status(
                project_id, variable_key, value_json, last_event_id, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, variable_key)
            DO UPDATE SET
                value_json = excluded.value_json,
                last_event_id = excluded.last_event_id,
                updated_at = excluded.updated_at
            """,
            (
                state["project_id"],
                state["variable_key"],
                self._dump_json(state.get("value")),
                str(state.get("last_event_id", "")),
                str(state.get("updated_at", self._now_iso())),
            ),
        )

    def _record_conflict(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        node_id: str,
        conflict_type: str,
        detail: dict[str, Any],
        blocking: bool = True,
    ) -> None:
        _ = blocking
        conn.execute(
            """
            INSERT INTO state_conflicts(
                id, project_id, node_id, conflict_type, detail_json, resolved, created_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (
                generate_id("stcf"),
                project_id,
                str(node_id or "unknown"),
                str(conflict_type or "unknown_conflict"),
                self._dump_json(detail),
                self._now_iso(),
            ),
        )

    def _extract_events_from_json_blocks(self, content: str) -> list[dict[str, Any]]:
        if not content:
            return []
        events: list[dict[str, Any]] = []

        direct = self._load_json(content, None)
        events.extend(self._events_from_payload(direct))

        for match in _JSON_FENCE_PATTERN.finditer(content):
            block = str(match.group(1) or "").strip()
            if not block:
                continue
            parsed = self._load_json(block, None)
            events.extend(self._events_from_payload(parsed))
        return events

    def _events_from_payload(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("events"), list):
                return [item for item in payload["events"] if isinstance(item, dict)]
            if payload.get("entity_type") and payload.get("event_type"):
                return [payload]
        return []

    def _extract_events_from_rules(self, content: str) -> list[dict[str, Any]]:
        if not content:
            return []
        events: list[dict[str, Any]] = []
        lines = [line.strip() for line in content.splitlines() if line.strip()]

        for line in lines:
            death = re.search(r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}).{0,8}(死亡|死去|阵亡|被杀)", line)
            if death:
                mention = str(death.group("char"))
                events.append(
                    {
                        "entity_type": "character",
                        "raw_mention": mention,
                        "event_type": "alive_change",
                        "payload": {"alive": False},
                        "source_excerpt": line,
                        "confidence": 0.55,
                    }
                )
                continue

            moved = re.search(
                r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}).{0,8}(来到|抵达|前往|移动到|位于)(?P<to>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})",
                line,
            )
            if moved:
                mention = str(moved.group("char"))
                to_location = str(moved.group("to"))
                events.append(
                    {
                        "entity_type": "character",
                        "raw_mention": mention,
                        "event_type": "move",
                        "payload": {"to": to_location},
                        "source_excerpt": line,
                        "confidence": 0.45,
                    }
                )
                continue

            hold = re.search(
                r"(?P<char>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}).{0,8}(获得|拿到|拾取|持有)(?P<item>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32})",
                line,
            )
            if hold:
                events.append(
                    {
                        "entity_type": "character",
                        "raw_mention": str(hold.group("char")),
                        "event_type": "hold_item",
                        "payload": {"item_mention": str(hold.group("item"))},
                        "source_excerpt": line,
                        "confidence": 0.45,
                    }
                )
                continue

            destroyed = re.search(
                r"(?P<item>[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}).{0,8}(被摧毁|损毁|毁坏|destroyed)",
                line,
                flags=re.IGNORECASE,
            )
            if destroyed:
                events.append(
                    {
                        "entity_type": "item",
                        "raw_mention": str(destroyed.group("item")),
                        "event_type": "destroyed",
                        "payload": {"destroyed": True},
                        "source_excerpt": line,
                        "confidence": 0.5,
                    }
                )
        return events

    def _normalize_event(self, raw: dict[str, Any]) -> dict[str, Any]:
        entity_type = self._normalize_entity_type(raw.get("entity_type"))
        event_type = str(raw.get("event_type") or "").strip()
        if not event_type:
            raise ValueError("event_type cannot be empty")
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        normalized: dict[str, Any] = {
            "entity_type": entity_type,
            "event_type": event_type,
            "payload": payload,
            "canonical_id": str(raw.get("canonical_id") or "").strip(),
            "raw_mention": str(raw.get("raw_mention") or "").strip(),
            "confidence": self._normalize_confidence(raw.get("confidence", 0.0)),
            "source_excerpt": str(raw.get("source_excerpt") or "").strip(),
        }

        if entity_type == "relationship":
            normalized["subject_character_id"] = str(raw.get("subject_character_id") or "").strip()
            normalized["object_character_id"] = str(raw.get("object_character_id") or "").strip()
        elif entity_type == "world_variable":
            normalized["variable_key"] = str(raw.get("variable_key") or "").strip()
        return normalized

    def _normalize_entity_type(self, value: object) -> str:
        text = str(value or "").strip().lower().replace("-", "_")
        if text in {"character", "item", "relationship", "world_variable"}:
            return text
        if text == "world":
            return "world_variable"
        raise ValueError("entity_type must be character|item|relationship|world_variable")

    def _normalize_alias(self, alias: str) -> str:
        text = str(alias or "").strip().lower()
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text[:128]

    def _normalize_confidence(self, value: object) -> float:
        try:
            parsed = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            parsed = 0.0
        if math.isnan(parsed) or math.isinf(parsed):
            return 0.0
        if parsed < 0:
            return 0.0
        if parsed > 1:
            return 1.0
        return parsed

    def _decode_proposal_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "node_id": row["node_id"],
            "thread_id": row["thread_id"],
            "proposal": self._load_json(str(row["proposal_json"]), {}),
            "status": row["status"],
            "reviewer": row["reviewer"],
            "review_note": row["review_note"],
            "created_at": row["created_at"],
            "reviewed_at": row["reviewed_at"],
            "applied_at": row["applied_at"],
        }

    def _decode_schema_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "entity_type": row["entity_type"],
            "attr_key": row["attr_key"],
            "value_type": row["value_type"],
            "description": row["description"],
            "constraints": self._load_json(str(row["constraints_json"]), {}),
            "is_active": bool(row["is_active"]),
            "updated_at": row["updated_at"],
        }

    def _get_proposal_or_raise(self, proposal_id: str) -> dict[str, Any]:
        with self.repository.store.read_only() as conn:
            row = conn.execute(
                "SELECT * FROM state_change_proposals WHERE id = ? LIMIT 1",
                (proposal_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"state_change_proposal not found: {proposal_id}")
        return self._decode_proposal_row(row)

    def _require_project(self, project_id: str) -> None:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(tr("err.project_not_found", project_id=project_id))

    def _require_node(self, project_id: str, node_id: str) -> None:
        node = self.repository.get_node(project_id, node_id)
        if node is None:
            raise KeyError(tr("err.node_not_found", node_id=node_id))

    def _dump_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def _load_json(self, text: str, fallback: Any) -> Any:
        try:
            return json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback

    def _now_iso(self) -> str:
        return utc_now().isoformat()
