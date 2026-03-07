"""Context packing for LLM generation/review."""

from __future__ import annotations

from dataclasses import dataclass, field

from elyha_core.i18n import tr
from elyha_core.models.node import Node
from elyha_core.storage.repository import SQLiteRepository


@dataclass(slots=True)
class ContextSegment:
    """Single context unit with priority for token trimming."""

    kind: str
    text: str
    priority: int
    token_estimate: int


@dataclass(slots=True)
class ContextPack:
    """Assembled context slices under a token budget."""

    project_id: str
    node_id: str
    token_budget: int
    used_tokens: int
    segments: list[ContextSegment] = field(default_factory=list)

    def to_prompt(self) -> str:
        lines: list[str] = []
        for segment in self.segments:
            lines.append(f"[{segment.kind}]")
            lines.append(segment.text)
            lines.append("")
        return "\n".join(lines).strip()


class ContextService:
    """Build bounded context from graph state and metadata summaries."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def build_context(
        self,
        project_id: str,
        node_id: str,
        *,
        token_budget: int = 2500,
        recent_count: int = 4,
        ancestor_limit: int = 8,
        pinned_limit: int = 12,
    ) -> ContextPack:
        if token_budget <= 0:
            raise ValueError(tr("err.token_budget_positive"))
        current = self.repository.get_node(project_id, node_id)
        if current is None:
            raise KeyError(tr("err.node_not_found", node_id=node_id))
        nodes = self.repository.list_nodes(project_id)
        edges = self.repository.list_edges(project_id)
        node_by_id = {node.id: node for node in nodes}
        incoming: dict[str, list[str]] = {}
        for edge in edges:
            incoming.setdefault(edge.target_id, []).append(edge.source_id)

        segments: list[ContextSegment] = []
        segments.extend(self._setting_segments(current))
        segments.append(self._segment_from_node(current, kind="current", priority=0, max_len=1500))
        pinned_nodes = self._pinned_context_nodes(nodes, current=current, limit=pinned_limit)
        pinned_ids = {node.id for node in pinned_nodes}
        for node in pinned_nodes:
            segments.append(
                self._segment_from_node(
                    node,
                    kind="pinned",
                    priority=0,
                    max_len=500,
                )
            )

        ancestor_ids = self._collect_ancestors(
            node_id,
            incoming=incoming,
            limit=ancestor_limit,
        )
        for ancestor_id in ancestor_ids:
            if ancestor_id in pinned_ids:
                continue
            ancestor = node_by_id.get(ancestor_id)
            if ancestor is None:
                continue
            segments.append(
                self._segment_from_node(
                    ancestor,
                    kind="ancestor",
                    priority=1,
                    max_len=300,
                )
            )

        recent = self._recent_storyline_nodes(
            nodes,
            current=current,
            count=recent_count,
        )
        for node in recent:
            if node.id in pinned_ids:
                continue
            segments.append(
                self._segment_from_node(
                    node,
                    kind="recent",
                    priority=2,
                    max_len=250,
                )
            )

        selected: list[ContextSegment] = []
        used_tokens = 0
        required_kinds = {"constraint", "current", "pinned"}
        required = sorted(
            (segment for segment in segments if segment.kind in required_kinds),
            key=lambda item: (item.priority, item.kind),
        )
        optional = sorted(
            (segment for segment in segments if segment.kind not in required_kinds),
            key=lambda item: (item.priority, item.kind),
        )
        for segment in required:
            if not segment.text:
                continue
            fitted = self._fit_segment_to_budget(segment, remaining_tokens=token_budget - used_tokens)
            if fitted is None:
                continue
            selected.append(fitted)
            used_tokens += fitted.token_estimate
        for segment in optional:
            if not segment.text:
                continue
            if used_tokens + segment.token_estimate > token_budget:
                continue
            selected.append(segment)
            used_tokens += segment.token_estimate
        return ContextPack(
            project_id=project_id,
            node_id=node_id,
            token_budget=token_budget,
            used_tokens=used_tokens,
            segments=selected,
        )

    def _fit_segment_to_budget(
        self,
        segment: ContextSegment,
        *,
        remaining_tokens: int,
    ) -> ContextSegment | None:
        if remaining_tokens <= 0:
            return None
        if segment.token_estimate <= remaining_tokens:
            return segment
        char_budget = max(16, remaining_tokens * 4)
        trimmed = segment.text[:char_budget].rstrip()
        if not trimmed:
            return None
        if len(trimmed) < len(segment.text):
            trimmed = f"{trimmed}..."
        return ContextSegment(
            kind=segment.kind,
            text=trimmed,
            priority=segment.priority,
            token_estimate=max(1, len(trimmed) // 4),
        )

    def _setting_segments(self, node: Node) -> list[ContextSegment]:
        result: list[ContextSegment] = []
        metadata = node.metadata
        if not isinstance(metadata, dict):
            return result
        constraints = metadata.get("constraints")
        if isinstance(constraints, str) and constraints.strip():
            text = constraints.strip()[:1200]
            result.append(
                ContextSegment(
                    kind="constraint",
                    text=text,
                    priority=0,
                    token_estimate=max(1, len(text) // 4),
                )
            )
        return result

    def _segment_from_node(
        self,
        node: Node,
        *,
        kind: str,
        priority: int,
        max_len: int,
    ) -> ContextSegment:
        content = self._node_text(node)
        trimmed = content[:max_len].strip()
        text = f"{node.title} ({node.type.value}): {trimmed}" if trimmed else f"{node.title} ({node.type.value})"
        return ContextSegment(
            kind=kind,
            text=text,
            priority=priority,
            token_estimate=max(1, len(text) // 4),
        )

    def _node_text(self, node: Node) -> str:
        chunks = self.repository.list_node_chunks(node.id)
        if chunks:
            return "\n".join(chunks)
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        for key in ("content", "summary", "notes"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _collect_ancestors(
        self,
        node_id: str,
        *,
        incoming: dict[str, list[str]],
        limit: int,
    ) -> list[str]:
        order: list[str] = []
        seen: set[str] = set()
        queue: list[str] = list(incoming.get(node_id, []))
        while queue and len(order) < limit:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            order.append(current)
            queue.extend(incoming.get(current, []))
        return order

    def _pinned_context_nodes(
        self,
        nodes: list[Node],
        *,
        current: Node,
        limit: int,
    ) -> list[Node]:
        if limit <= 0:
            return []
        result: list[Node] = []
        for node in nodes:
            if node.id == current.id:
                continue
            metadata = node.metadata if isinstance(node.metadata, dict) else {}
            marker = metadata.get("context_pinned")
            if self._bool_like(marker):
                result.append(node)
        result.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        return result[:limit]

    def _bool_like(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def _recent_storyline_nodes(
        self,
        nodes: list[Node],
        *,
        current: Node,
        count: int,
    ) -> list[Node]:
        if count <= 0:
            return []
        filtered: list[Node] = []
        for node in nodes:
            if node.id == current.id:
                continue
            if current.storyline_id and node.storyline_id != current.storyline_id:
                continue
            filtered.append(node)
        filtered.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        return filtered[:count]
