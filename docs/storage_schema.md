# Storage Schema

当前 SQLite schema 版本：`v1`

## Tables

- `projects`
  - `id` (PK)
  - `title`
  - `created_at`
  - `updated_at`
  - `active_revision`
  - `settings_json`
- `nodes`
  - `id` (PK)
  - `project_id` (FK -> projects.id, cascade delete)
  - `type`, `title`, `status`, `storyline_id`
  - `pos_x`, `pos_y`
  - `metadata_json`
  - `created_at`, `updated_at`
- `edges`
  - `id` (PK)
  - `project_id` (FK -> projects.id)
  - `source_id`, `target_id` (FK -> nodes.id)
  - `label`, `created_at`
  - `UNIQUE(project_id, source_id, target_id)`
- `node_chunks`
  - `id` (PK autoincrement)
  - `node_id` (FK -> nodes.id)
  - `chunk_index`, `content`, `token_estimate`, `summary`
- `tasks`
  - `id` (PK)
  - `project_id` (FK -> projects.id)
  - `node_id` (FK -> nodes.id, set null on delete)
  - `task_type`, `status`
  - `error_code`, `error_message`
  - `started_at`, `finished_at`, `revision`, `created_at`
- `operation_logs`
  - `id` (PK)
  - `project_id` (FK -> projects.id)
  - `revision`, `op_type`, `payload_json`, `created_at`
- `snapshots`
  - `id` (PK)
  - `project_id` (FK -> projects.id)
  - `revision`, `path`, `created_at`

## Indexes

- `idx_nodes_project_id`
- `idx_edges_project_id`, `idx_edges_source_id`, `idx_edges_target_id`
- `idx_node_chunks_node_id`
- `idx_tasks_project_id`, `idx_tasks_project_status`
- `idx_operation_project_revision`
- `idx_snapshots_project_revision`
