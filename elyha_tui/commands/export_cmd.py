"""Export command handlers used by TUI."""

from __future__ import annotations

from pathlib import Path

from elyha_core.services.export_service import ExportService


def export_markdown(
    service: ExportService,
    *,
    project_id: str,
    traversal: str = "mainline",
    output_root: str = "exports",
) -> dict[str, object]:
    out_file = service.export_markdown(
        project_id,
        traversal=traversal,
        output_root=Path(output_root),
    )
    return {"project_id": project_id, "path": str(out_file), "traversal": traversal}
