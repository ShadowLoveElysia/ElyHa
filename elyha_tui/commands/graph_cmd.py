"""Graph command handlers used by TUI."""

from __future__ import annotations

from typing import Any

from elyha_core.models.node import NodeStatus, NodeType
from elyha_core.services.graph_service import GraphService, NodeCreate
from elyha_core.services.validation_service import ValidationService


def _node_payload(node) -> dict[str, object]:
    return {
        "id": node.id,
        "project_id": node.project_id,
        "title": node.title,
        "type": node.type.value,
        "status": node.status.value,
        "storyline_id": node.storyline_id,
        "pos_x": node.pos_x,
        "pos_y": node.pos_y,
        "metadata": node.metadata,
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat(),
    }


def _edge_payload(edge) -> dict[str, object]:
    return {
        "id": edge.id,
        "project_id": edge.project_id,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "label": edge.label,
        "narrative_order": edge.narrative_order,
        "created_at": edge.created_at.isoformat(),
    }


def node_add(
    service: GraphService,
    *,
    project_id: str,
    title: str,
    node_type: str = "chapter",
    status: str = "draft",
    storyline_id: str | None = None,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    node = service.add_node(
        project_id,
        NodeCreate(
            title=title,
            type=NodeType(node_type),
            status=NodeStatus(status),
            storyline_id=storyline_id,
            pos_x=pos_x,
            pos_y=pos_y,
            metadata=(metadata or {}).copy(),
        ),
    )
    return _node_payload(node)


def node_update(
    service: GraphService,
    *,
    project_id: str,
    node_id: str,
    patch: dict[str, Any],
) -> dict[str, object]:
    normalized = patch.copy()
    if "type" in normalized and isinstance(normalized["type"], str):
        normalized["type"] = NodeType(normalized["type"]).value
    if "status" in normalized and isinstance(normalized["status"], str):
        normalized["status"] = NodeStatus(normalized["status"]).value
    node = service.update_node(project_id, node_id, normalized)
    return _node_payload(node)


def node_move(
    service: GraphService,
    *,
    project_id: str,
    node_id: str,
    pos_x: float,
    pos_y: float,
) -> dict[str, object]:
    node = service.update_node(
        project_id,
        node_id,
        {"pos_x": float(pos_x), "pos_y": float(pos_y)},
    )
    return _node_payload(node)


def node_delete(service: GraphService, *, project_id: str, node_id: str) -> dict[str, object]:
    service.delete_node(project_id, node_id)
    return {"status": "deleted", "project_id": project_id, "node_id": node_id}


def node_list(service: GraphService, *, project_id: str) -> list[dict[str, object]]:
    return [_node_payload(node) for node in service.list_nodes(project_id)]


def edge_add(
    service: GraphService,
    *,
    project_id: str,
    source_id: str,
    target_id: str,
    label: str = "",
) -> dict[str, object]:
    edge = service.add_edge(project_id, source_id, target_id, label=label)
    return _edge_payload(edge)


def edge_delete(service: GraphService, *, project_id: str, edge_id: str) -> dict[str, object]:
    service.delete_edge(project_id, edge_id)
    return {"status": "deleted", "project_id": project_id, "edge_id": edge_id}


def edge_list(service: GraphService, *, project_id: str) -> list[dict[str, object]]:
    return [_edge_payload(edge) for edge in service.list_edges(project_id)]


def graph_view(service: GraphService, *, project_id: str) -> dict[str, object]:
    nodes = service.list_nodes(project_id)
    edges = service.list_edges(project_id)
    inbound: dict[str, int] = {node.id: 0 for node in nodes}
    outbound: dict[str, int] = {node.id: 0 for node in nodes}
    for edge in edges:
        if edge.source_id in outbound:
            outbound[edge.source_id] += 1
        if edge.target_id in inbound:
            inbound[edge.target_id] += 1
    return {
        "project_id": project_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": [
            {
                **_node_payload(node),
                "inbound": inbound.get(node.id, 0),
                "outbound": outbound.get(node.id, 0),
            }
            for node in nodes
        ],
        "edges": [_edge_payload(edge) for edge in edges],
    }


def validate_project(
    service: ValidationService,
    *,
    project_id: str,
) -> dict[str, object]:
    report = service.validate_project(project_id)
    return {
        "project_id": report.project_id,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "infos": len(report.infos),
        "issues": [
            {
                "level": issue.level,
                "code": issue.code,
                "message": issue.message,
                "project_id": issue.project_id,
                "node_id": issue.node_id,
                "edge_id": issue.edge_id,
            }
            for issue in report.issues
        ],
    }
