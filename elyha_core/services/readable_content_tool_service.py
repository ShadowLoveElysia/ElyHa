"""Tool-facing long-text read helpers for search and chunk retrieval."""

from __future__ import annotations

import re
from typing import Any

from elyha_core.services.graph_service import GraphService
from elyha_core.storage.repository import SQLiteRepository


class ReadableContentToolService:
    """Backend implementation for read/search tools used by agent loop."""

    def __init__(
        self,
        repository: SQLiteRepository,
        graph_service: GraphService,
        *,
        state_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.state_service = state_service

    def search_text(
        self,
        *,
        project_id: str,
        query: str,
        top_k: int = 5,
        scope: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        clean_query = str(query or "").strip()
        if not clean_query:
            return []
        node_ids = self._extract_scope_node_ids(scope)
        rows = self.repository.list_project_chunk_records(project_id, node_ids=node_ids or None)
        terms = self._query_terms(clean_query)
        hits: list[dict[str, Any]] = []
        for row in rows:
            content = str(row.get("content", ""))
            summary = str(row.get("summary", ""))
            score, match_terms = self._score_chunk(content, summary, terms)
            if score <= 0:
                continue
            node_id = str(row["node_id"])
            chunk_index = int(row["chunk_index"])
            hits.append(
                {
                    "chunk_id": self._to_chunk_id(node_id, chunk_index),
                    "score": score,
                    "snippet": self._snippet(content, terms),
                    "node_id": node_id,
                    "match_terms": match_terms,
                }
            )
        hits.sort(key=lambda item: (-float(item["score"]), str(item["chunk_id"])))
        limit = min(20, max(1, int(top_k)))
        return hits[:limit]

    def read_chunk(self, chunk_id: str, *, project_id: str = "") -> dict[str, Any]:
        node_id, chunk_index = self._parse_chunk_id(chunk_id)
        self._ensure_node_project(node_id=node_id, project_id=project_id)
        records = self.repository.list_node_chunk_records(node_id)
        for row in records:
            if int(row["chunk_index"]) != chunk_index:
                continue
            content = str(row["content"])
            return {
                "chunk_id": self._to_chunk_id(node_id, chunk_index),
                "content": content,
                "node_id": node_id,
                "paragraph_range": [chunk_index + 1, chunk_index + 1],
                "chars": len(content),
            }
        raise KeyError(f"chunk not found: {chunk_id}")

    def read_neighbors(
        self,
        chunk_id: str,
        *,
        project_id: str = "",
        before: int = 1,
        after: int = 1,
    ) -> list[dict[str, Any]]:
        node_id, chunk_index = self._parse_chunk_id(chunk_id)
        self._ensure_node_project(node_id=node_id, project_id=project_id)
        clean_before = max(0, min(10, int(before)))
        clean_after = max(0, min(10, int(after)))
        records = self.repository.list_node_chunk_records(node_id)
        indexed = {int(row["chunk_index"]): row for row in records}
        if chunk_index not in indexed:
            raise KeyError(f"chunk not found: {chunk_id}")
        start = max(0, chunk_index - clean_before)
        end = chunk_index + clean_after
        result: list[dict[str, Any]] = []
        for idx in range(start, end + 1):
            row = indexed.get(idx)
            if row is None:
                continue
            content = str(row["content"])
            result.append(
                {
                    "chunk_id": self._to_chunk_id(node_id, idx),
                    "content": content,
                    "node_id": node_id,
                    "paragraph_range": [idx + 1, idx + 1],
                    "chars": len(content),
                }
            )
        return result

    def get_chapter_outline(self, *, project_id: str, node_id: str) -> dict[str, Any]:
        node = self.graph_service.get_node(project_id, node_id)
        metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
        forced = metadata.get("forced_progression_points", [])
        if not isinstance(forced, list):
            forced = []
        return {
            "node_id": node.id,
            "title": node.title,
            "outline_markdown": str(metadata.get("outline_markdown", "")).strip(),
            "goal": str(metadata.get("goal", "")).strip(),
            "chapter_position": str(metadata.get("chapter_position", "")).strip(),
            "forced_progression_points": [str(item).strip() for item in forced if str(item).strip()],
        }

    def get_world_state(self, *, project_id: str, keys: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.state_service is None:
            return {"project_id": project_id, "state_snapshot": {}}
        payload = keys if isinstance(keys, dict) else {}
        character_ids = self._normalize_str_list(payload.get("character_ids"))
        item_ids = self._normalize_str_list(payload.get("item_ids"))
        world_variable_keys = self._normalize_str_list(payload.get("world_variable_keys"))
        relationship_pairs = self._normalize_relationship_pairs(payload.get("relationship_pairs"))
        snapshot = self.state_service.build_prompt_state_payload(
            project_id,
            character_ids=character_ids or None,
            item_ids=item_ids or None,
            relationship_pairs=relationship_pairs or None,
            world_variable_keys=world_variable_keys or None,
        )
        result: dict[str, Any] = {"project_id": project_id, "state_snapshot": snapshot}
        # Conditionally attach arc summary for long-term memory
        arc_summary = self.state_service.generate_arc_summary(project_id)
        if arc_summary:
            result["arc_summary"] = arc_summary
        return result

    def get_effective_directives(self, *, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")
        directives = str(getattr(project.settings, "global_directives", "") or "").strip()
        return {"project_id": project_id, "global_directives": directives}

    def _extract_scope_node_ids(self, scope: dict[str, Any] | None) -> list[str]:
        if not isinstance(scope, dict):
            return []
        result: list[str] = []
        raw_node_id = scope.get("node_id")
        if raw_node_id is not None:
            text = str(raw_node_id).strip()
            if text:
                result.append(text)
        raw_node_ids = scope.get("node_ids")
        if isinstance(raw_node_ids, list):
            for item in raw_node_ids:
                text = str(item).strip()
                if text:
                    result.append(text)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in result:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _score_chunk(self, content: str, summary: str, terms: list[str]) -> tuple[float, list[str]]:
        if not terms:
            return 0.0, []
        haystack = content.lower()
        summary_haystack = summary.lower()
        score = 0.0
        matched_terms: list[str] = []
        unique_hit_count = 0
        for term in terms:
            if not term:
                continue
            freq = haystack.count(term)
            if freq > 0:
                score += float(freq * max(1, len(term)))
                unique_hit_count += 1
                matched_terms.append(term)
            summary_freq = summary_haystack.count(term)
            if summary_freq > 0:
                # Summary hit is often a denser signal for relevance.
                score += float(summary_freq * max(1, len(term)) * 1.1)
                if term not in matched_terms:
                    unique_hit_count += 1
                    matched_terms.append(term)

        # Coverage bonus: reward chunks matching more unique query terms.
        coverage = unique_hit_count / max(1, len(terms))
        score += coverage * 6.0

        # Phrase bonus: contiguous phrase hit gets extra confidence.
        clean_terms = [item for item in terms if item]
        if len(clean_terms) >= 2:
            for i in range(len(clean_terms) - 1):
                phrase = clean_terms[i] + clean_terms[i + 1]
                if phrase and phrase in haystack:
                    score += max(1.0, len(phrase) * 0.8)

        # Lightweight fuzzy bonus for CJK-heavy query miss cases.
        query_ngrams = self._char_ngrams("".join(clean_terms), n=2)
        if query_ngrams:
            content_ngrams = self._char_ngrams(haystack, n=2, max_chars=1600)
            overlap = len(query_ngrams & content_ngrams)
            if overlap > 0:
                score += min(4.0, float(overlap) * 0.35)

        return round(score, 4), matched_terms[:12]

    def _snippet(self, content: str, terms: list[str], *, limit: int = 220) -> str:
        text = str(content or "").strip()
        if not text:
            return ""
        lower_text = text.lower()
        positions = [lower_text.find(term) for term in terms if term and lower_text.find(term) >= 0]
        hit_at = min(positions) if positions else 0
        start = max(0, hit_at - 80)
        end = min(len(text), start + max(80, int(limit)))
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet

    def _query_terms(self, query: str) -> list[str]:
        raw_terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", str(query or "").lower())
        result: list[str] = []
        seen: set[str] = set()
        for term in raw_terms:
            clean = term.strip()
            if not clean or len(clean) <= 1:
                continue
            if clean in seen:
                continue
            seen.add(clean)
            result.append(clean)
        return result[:12]

    def _char_ngrams(self, text: str, *, n: int = 2, max_chars: int = 0) -> set[str]:
        clean = str(text or "").strip().lower()
        if max_chars > 0:
            clean = clean[:max_chars]
        if len(clean) < n:
            return set()
        result: set[str] = set()
        for idx in range(0, len(clean) - n + 1):
            token = clean[idx : idx + n]
            if token.strip():
                result.add(token)
        return result

    def _normalize_str_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result

    def _normalize_relationship_pairs(self, value: Any) -> list[tuple[str, str]]:
        if not isinstance(value, list):
            return []
        result: list[tuple[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                left = str(item.get("subject") or item.get("a") or "").strip()
                right = str(item.get("object") or item.get("b") or "").strip()
                if left and right:
                    result.append((left, right))
                continue
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                left = str(item[0]).strip()
                right = str(item[1]).strip()
                if left and right:
                    result.append((left, right))
        return result

    def _to_chunk_id(self, node_id: str, chunk_index: int) -> str:
        return f"{node_id}:{chunk_index}"

    def _parse_chunk_id(self, chunk_id: str) -> tuple[str, int]:
        raw = str(chunk_id or "").strip()
        if ":" not in raw:
            raise ValueError(f"invalid chunk_id: {chunk_id!r}")
        node_id, index_text = raw.rsplit(":", 1)
        clean_node = node_id.strip()
        if not clean_node:
            raise ValueError(f"invalid chunk_id: {chunk_id!r}")
        try:
            chunk_index = int(index_text)
        except ValueError as exc:
            raise ValueError(f"invalid chunk index in chunk_id: {chunk_id!r}") from exc
        if chunk_index < 0:
            raise ValueError(f"invalid chunk index in chunk_id: {chunk_id!r}")
        return clean_node, chunk_index

    def _ensure_node_project(self, *, node_id: str, project_id: str) -> None:
        clean_project = str(project_id or "").strip()
        if not clean_project:
            return
        _ = self.graph_service.get_node(clean_project, node_id)
