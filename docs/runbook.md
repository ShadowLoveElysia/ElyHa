# Runbook

## Setup

```bash
UV_CACHE_DIR=.uv-cache uv sync --extra dev
UV_CACHE_DIR=.uv-cache uv run python scripts/migrate.py --db ./data/dev.db
```

## I18N locale

```bash
ELYHA_LOCALE=zh UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --smoke
ELYHA_LOCALE=en UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --smoke
ELYHA_LOCALE=ja UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --smoke
```

## Core checks

```bash
UV_CACHE_DIR=.uv-cache uv run --extra dev pytest -q
UV_CACHE_DIR=.uv-cache uv run --extra dev mypy elyha_core elyha_api elyha_tui
UV_CACHE_DIR=.uv-cache uv run --extra dev ruff check elyha_core elyha_api elyha_tui tests scripts
```

## TUI usage

```bash
# 交互式（dashboard 四面板）
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --db ./data/dev.db

# 在交互式里输入 graph-edit 进入图编辑子模式

# 自动化（JSON 输出）
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --db ./data/dev.db --automation project-list
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --db ./data/dev.db --automation generate-chapter --project-id <proj_id> --node-id <node_id>
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --db ./data/dev.db --automation node-move --project-id <proj_id> --node-id <node_id> --pos-x 200 --pos-y 120
```

## Web usage

```bash
# 启动 API + Web GUI
UV_CACHE_DIR=.uv-cache uv run uvicorn elyha_api.app:app --reload

# 打开
# http://127.0.0.1:8000/
```

Web GUI 约束：

- 前端使用 React，供后续 Tauri 直接复用。
- 所有确认/输入弹窗使用页面内 Modal，不使用浏览器原生 alert/prompt/confirm。
- Web 内置教程：侧边栏有 6 步快速指南，顶部 `Tutorial` 可打开完整操作说明。

运行配置档（profiles）：

- 配置目录默认：`data/core_configs/`
- 核心档：`core.json`（只读，不可改名/删除/覆盖）
- 活跃配置记录：`data/core_configs/active_profile.txt`
- 可在 Web 中新建/改名/删除自定义配置并切换。
- `web_host/web_port` 写入配置档后，`LaunchGUI.bat/sh` 下次启动会自动读取并应用端口。
- `auto_complete` 控制是否自动把 API URL 补成 `/chat/completions`；关闭后按配置中的 URL 原样请求。

## Snapshot + rollback flow

1. 创建项目并进行图编辑写入。
2. 调用 `POST /api/projects/{project_id}/snapshots` 创建快照。
3. 继续编辑到更高 revision。
4. 调用 `POST /api/projects/{project_id}/rollback` 并传入目标 revision。
5. 调用 `POST /api/projects/{project_id}/validate` 或导出接口进行回归验证。

## Export flow

1. 调用 `POST /api/projects/{project_id}/validate`，确认无 error。
2. 调用 `POST /api/projects/{project_id}/export`。
3. 在返回路径读取 `story.md`。

## AI flow

1. 创建项目并写入至少一个节点。
2. 调用 `POST /api/generate/chapter` 或 TUI `generate-chapter`（可指定 `workflow_mode=multi_agent|single`）。
3. 通过 `GET /api/tasks/{task_id}` 或 `task-list` 查看任务状态。
4. 使用 `POST /api/review/lore` / `POST /api/review/logic` 输出审查报告。
