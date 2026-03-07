"""Markdown export service."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import re

from elyha_core.i18n import tr
from elyha_core.models.edge import Edge
from elyha_core.models.node import Node
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.services.validation_service import ValidationService


class ExportService:
    """Export project graph into markdown drafts."""

    def __init__(
        self,
        repository: SQLiteRepository,
        validation_service: ValidationService,
    ) -> None:
        self.repository = repository
        self.validation_service = validation_service

    def export_markdown(
        self,
        project_id: str,
        *,
        output_root: str | Path = "exports",
        traversal: str = "mainline",
    ) -> Path:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(tr("err.project_not_found", project_id=project_id))

        report = self.validation_service.validate_project(project_id)
        if report.errors:
            codes = ", ".join(sorted({issue.code for issue in report.errors}))
            raise ValueError(tr("err.project_validation_failed", codes=codes))

        nodes = self.repository.list_nodes(project_id)
        edges = self.repository.list_edges(project_id)
        ordered_nodes = self._order_nodes(nodes, edges, traversal=traversal)

        stamp = utc_now().strftime("%Y%m%d_%H%M%S")
        safe_title = self._slugify(project.title)
        out_dir = Path(output_root) / safe_title / stamp
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "story.md"
        lines: list[str] = [
            f"# {project.title}",
            "",
            f"- project_id: {project.id}",
            f"- exported_at: {utc_now().isoformat()}",
            f"- traversal: {traversal}",
            "",
        ]
        for index, node in enumerate(ordered_nodes, start=1):
            lines.append(f"## {index}. {node.title} [{node.type.value}]")
            lines.append("")
            lines.append(self._node_content(node))
            lines.append("")
        out_file.write_text("\n".join(lines), encoding="utf-8")
        return out_file

    def _order_nodes(
        self,
        nodes: list[Node],
        edges: list[Edge],
        *,
        traversal: str,
    ) -> list[Node]:
        if traversal == "topological":
            return self._topological_order(nodes, edges)
        if traversal == "mainline":
            return self._mainline_order(nodes, edges)
        raise ValueError(tr("err.traversal_invalid"))

    def _mainline_order(self, nodes: list[Node], edges: list[Edge]) -> list[Node]:
        if not nodes:
            return []
        node_by_id = {node.id: node for node in nodes}
        outgoing: dict[str, list[tuple[str, int, object, str]]] = defaultdict(list)
        indegree: dict[str, int] = {node.id: 0 for node in nodes}
        for edge in edges:
            if edge.source_id in node_by_id and edge.target_id in node_by_id:
                order_rank = (
                    edge.narrative_order
                    if isinstance(edge.narrative_order, int) and edge.narrative_order > 0
                    else 10**9
                )
                outgoing[edge.source_id].append(
                    (edge.target_id, order_rank, edge.created_at, edge.id)
                )
                indegree[edge.target_id] += 1

        def node_key(node_id: str) -> tuple[object, str]:
            node = node_by_id[node_id]
            return (node.created_at, node.id)

        def branch_key(item: tuple[str, int, object, str]) -> tuple[object, ...]:
            target_id, order_rank, _, edge_id = item
            target = node_by_id[target_id]
            return (order_rank, target.created_at, target.id, edge_id)

        for source_id in outgoing:
            outgoing[source_id].sort(key=branch_key)

        roots = sorted(
            [node.id for node in nodes if indegree[node.id] == 0],
            key=node_key,
        )
        start_id = roots[0] if roots else min(node_by_id.keys(), key=node_key)
        visited: set[str] = set()
        ordered: list[Node] = []
        current: str | None = start_id

        while current is not None and current not in visited:
            ordered.append(node_by_id[current])
            visited.add(current)
            next_candidates = [
                target
                for target, _, _, _ in outgoing.get(current, [])
                if target not in visited
            ]
            current = next_candidates[0] if next_candidates else None

        for node in self._topological_order(nodes, edges, allow_cycle_fallback=True):
            if node.id not in visited:
                ordered.append(node)
                visited.add(node.id)
        return ordered

    def _topological_order(
        self,
        nodes: list[Node],
        edges: list[Edge],
        *,
        allow_cycle_fallback: bool = False,
    ) -> list[Node]:
        node_by_id = {node.id: node for node in nodes}
        indegree: dict[str, int] = {node.id: 0 for node in nodes}
        outgoing: dict[str, list[tuple[str, int, object, str]]] = defaultdict(list)
        for edge in edges:
            if edge.source_id in node_by_id and edge.target_id in node_by_id:
                order_rank = (
                    edge.narrative_order
                    if isinstance(edge.narrative_order, int) and edge.narrative_order > 0
                    else 10**9
                )
                outgoing[edge.source_id].append(
                    (edge.target_id, order_rank, edge.created_at, edge.id)
                )
                indegree[edge.target_id] += 1

        queue = deque(sorted(
            [node.id for node in nodes if indegree[node.id] == 0],
            key=lambda node_id: (node_by_id[node_id].created_at, node_id),
        ))
        result: list[Node] = []
        while queue:
            node_id = queue.popleft()
            result.append(node_by_id[node_id])
            branches = sorted(
                outgoing.get(node_id, []),
                key=lambda item: (item[1], node_by_id[item[0]].created_at, item[0], item[3]),
            )
            for target_id, _, _, _ in branches:
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    queue.append(target_id)

        if len(result) != len(nodes):
            if allow_cycle_fallback:
                remaining = [node for node in nodes if node.id not in {item.id for item in result}]
                remaining.sort(key=lambda node: (node.created_at, node.id))
                return result + remaining
            raise ValueError(tr("err.topological_cycle"))
        return result

    def _node_content(self, node: Node) -> str:
        chunks = self.repository.list_node_chunks(node.id)
        if chunks:
            return "\n\n".join(chunks)
        content = node.metadata.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        summary = node.metadata.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        return tr("export.empty_node_content")

    def _slugify(self, title: str) -> str:
        value = re.sub(r"[^\w\-]+", "_", title.strip(), flags=re.UNICODE).strip("_")
        return value or tr("export.untitled_project")
