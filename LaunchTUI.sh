#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p data
DB_PATH="${ELYHA_DB_PATH:-./data/dev.db}"

echo "[ElyHa] Web GUI available via LaunchGUI.sh (or http://127.0.0.1:8765/web after start)."
echo "[ElyHa] Launching TUI with db: ${DB_PATH}"

if command -v uv >/dev/null 2>&1; then
  export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"
  exec uv run python -m elyha_tui.main --db "${DB_PATH}"
fi

echo "[ElyHa] uv not found, fallback to python."
exec python -m elyha_tui.main --db "${DB_PATH}"
