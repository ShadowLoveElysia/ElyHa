#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-./data/demo.db}"
EXPORT_ROOT="${2:-./exports_demo}"

mkdir -p "$(dirname "$DB_PATH")"

run_automation() {
  UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --db "$DB_PATH" --automation "$@"
}

UV_CACHE_DIR=.uv-cache uv run python scripts/migrate.py --db "$DB_PATH"

PROJECT_JSON="$(run_automation project-create --title "Demo Story")"
echo "$PROJECT_JSON"
PROJECT_ID="$(UV_CACHE_DIR=.uv-cache uv run python -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$PROJECT_JSON")"

NODE_A_JSON="$(run_automation node-add --project-id "$PROJECT_ID" --title "Chapter A" --metadata-json '{"content":"A-start"}')"
echo "$NODE_A_JSON"
NODE_A_ID="$(UV_CACHE_DIR=.uv-cache uv run python -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$NODE_A_JSON")"

NODE_B_JSON="$(run_automation node-add --project-id "$PROJECT_ID" --title "Chapter B" --metadata-json '{"content":"B-end"}')"
echo "$NODE_B_JSON"
NODE_B_ID="$(UV_CACHE_DIR=.uv-cache uv run python -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$NODE_B_JSON")"

run_automation edge-add --project-id "$PROJECT_ID" --source-id "$NODE_A_ID" --target-id "$NODE_B_ID"
run_automation generate-chapter --project-id "$PROJECT_ID" --node-id "$NODE_A_ID" --token-budget 1200
run_automation task-list --project-id "$PROJECT_ID" --limit 5
run_automation validate --project-id "$PROJECT_ID"
run_automation snapshot-create --project-id "$PROJECT_ID"
run_automation export --project-id "$PROJECT_ID" --traversal topological --output-root "$EXPORT_ROOT"
