# API Contract

当前已开放端点（Local API）：

- `GET /healthz`

- `GET /api/settings/runtime`
- `PUT /api/settings/runtime`
- `POST /api/settings/runtime/switch`
- `POST /api/settings/runtime/profiles`
- `POST /api/settings/runtime/profiles/rename`
- `DELETE /api/settings/runtime/profiles/{profile}`
- `GET /api/llm/presets`

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`
- `PUT /api/projects/{project_id}/settings`

- `GET /api/projects/{project_id}/nodes`
- `POST /api/projects/{project_id}/nodes`
- `PUT /api/projects/{project_id}/nodes/{node_id}`
- `DELETE /api/projects/{project_id}/nodes/{node_id}`

- `GET /api/projects/{project_id}/edges`
- `POST /api/projects/{project_id}/edges`
- `POST /api/projects/{project_id}/edges/reorder`
- `DELETE /api/projects/{project_id}/edges/{edge_id}`

- `POST /api/projects/{project_id}/validate`
- `POST /api/projects/{project_id}/export`

- `POST /api/projects/{project_id}/snapshots`
- `GET /api/projects/{project_id}/snapshots`
- `POST /api/projects/{project_id}/rollback`

- `POST /api/generate/chapter`
- `POST /api/generate/branches`
- `POST /api/ai/chat`
- `POST /api/ai/workflow/sync`
- `POST /api/ai/workflow/clarify`
- `POST /api/ai/outline/guide`
- `POST /api/review/lore`
- `POST /api/review/logic`
- `GET /api/projects/{project_id}/insights`

- `POST /api/projects/{project_id}/suggestions/cleanup`

`POST /api/generate/chapter` 支持 `workflow_mode` 参数：`multi_agent`（默认）或 `single`。

- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/cancel`
- `GET /api/projects/{project_id}/tasks`
