"""Project-level structural validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from elyha_core.i18n import tr
from elyha_core.models.node import NodeType
from elyha_core.storage.repository import SQLiteRepository


@dataclass(slots=True)
class ValidationIssue:
    """Single validation message."""

    level: str
    code: str
    message: str
    project_id: str
    node_id: str | None = None
    edge_id: str | None = None


@dataclass(slots=True)
class ValidationReport:
    """Structured validation output for adapters and exporters."""

    project_id: str
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.level == "warn"]

    @property
    def infos(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.level == "info"]


class ValidationService:
    """Validate graph integrity constraints outside the UI layer."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def validate_project(self, project_id: str) -> ValidationReport:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(tr("err.project_not_found", project_id=project_id))

        report = ValidationReport(project_id=project_id)
        nodes = self.repository.list_nodes(project_id)
        edges = self.repository.list_edges(project_id)
        node_ids = {node.id for node in nodes}
        indegree: dict[str, int] = {node.id: 0 for node in nodes}
        outdegree: dict[str, int] = {node.id: 0 for node in nodes}
        edge_pairs: set[tuple[str, str]] = set()
        adjacency: dict[str, set[str]] = {node.id: set() for node in nodes}

        for edge in edges:
            pair = (edge.source_id, edge.target_id)
            if pair in edge_pairs:
                report.issues.append(
                    ValidationIssue(
                        level="error",
                        code="duplicate_edge",
                        message=tr("validation.duplicate_edge"),
                        project_id=project_id,
                        edge_id=edge.id,
                    )
                )
            edge_pairs.add(pair)

            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                report.issues.append(
                    ValidationIssue(
                        level="error",
                        code="dangling_edge",
                        message=tr("validation.dangling_edge"),
                        project_id=project_id,
                        edge_id=edge.id,
                    )
                )
                continue
            outdegree[edge.source_id] += 1
            indegree[edge.target_id] += 1
            adjacency[edge.source_id].add(edge.target_id)

        for node in nodes:
            if indegree[node.id] == 0 and outdegree[node.id] == 0:
                report.issues.append(
                    ValidationIssue(
                        level="warn",
                        code="orphan_node",
                        message=tr("validation.orphan_node"),
                        project_id=project_id,
                        node_id=node.id,
                    )
                )
            if node.type == NodeType.MERGE and indegree[node.id] < 2:
                report.issues.append(
                    ValidationIssue(
                        level="error",
                        code="merge_inbound_insufficient",
                        message=tr("validation.merge_inbound_insufficient"),
                        project_id=project_id,
                        node_id=node.id,
                    )
                )
            if node.type != NodeType.GROUP and outdegree[node.id] > 1:
                branch_targets = list(adjacency[node.id])
                common_reachable: set[str] | None = None
                for target_id in branch_targets:
                    reachable = self._reachable_nodes(target_id, adjacency)
                    reachable.discard(node.id)
                    if common_reachable is None:
                        common_reachable = reachable
                    else:
                        common_reachable.intersection_update(reachable)
                    if not common_reachable:
                        break
                if not common_reachable:
                    report.issues.append(
                        ValidationIssue(
                            level="error",
                            code="small_branch_requires_return",
                            message=tr("validation.small_branch_requires_return"),
                            project_id=project_id,
                            node_id=node.id,
                        )
                    )

        report.issues.append(
            ValidationIssue(
                level="info",
                code="summary",
                message=tr(
                    "validation.summary",
                    nodes=len(nodes),
                    edges=len(edges),
                    errors=len(report.errors),
                    warns=len(report.warnings),
                ),
                project_id=project_id,
            )
        )
        return report

    def _reachable_nodes(
        self, start_id: str, adjacency: dict[str, set[str]]
    ) -> set[str]:
        visited: set[str] = set()
        stack: list[str] = [start_id]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adjacency.get(current, ()))
        return visited
