"""HTTP adapter for calling ElyHa Local API from Web/Tauri bridges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from elyha_core.i18n import tr


@dataclass(slots=True)
class LocalAPIAdapter:
    """Thin HTTP client with normalized error surface."""

    base_url: str = "http://127.0.0.1:8000"
    timeout_seconds: float = 15.0

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.request(
                method=method,
                url=url,
                json=json_body,
                params=params,
            )
        if response.status_code >= 400:
            detail = response.text
            raise RuntimeError(
                tr(
                    "err.local_api_error",
                    status_code=response.status_code,
                    detail=detail,
                )
            )
        if not response.content:
            return None
        return response.json()

    def healthz(self) -> dict[str, Any]:
        return self._request("GET", "/healthz")

    def list_projects(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/projects")

    def create_project(self, title: str) -> dict[str, Any]:
        return self._request("POST", "/api/projects", json_body={"title": title})

    def create_node(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/nodes", json_body=payload)

    def create_edge(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/edges", json_body=payload)

    def validate_project(self, project_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/validate")

    def generate_chapter(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/generate/chapter", json_body=payload)

    def generate_branches(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/generate/branches", json_body=payload)

    def review_lore(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/review/lore", json_body=payload)

    def review_logic(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/review/logic", json_body=payload)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/tasks/{task_id}")

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/tasks/{task_id}/cancel")
