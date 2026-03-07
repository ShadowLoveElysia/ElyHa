#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p data
DB_PATH="${ELYHA_DB_PATH:-./data/dev.db}"
CONFIG_DIR="${ELYHA_CORE_CONFIG_DIR:-./data/core_configs}"
ACTIVE_PROFILE="core"
if [[ -f "${CONFIG_DIR}/active_profile.txt" ]]; then
  ACTIVE_PROFILE="$(tr -d '\r\n' < "${CONFIG_DIR}/active_profile.txt")"
fi
CONFIG_FILE="${CONFIG_DIR}/${ACTIVE_PROFILE}.json"

HOST="${ELYHA_HOST:-}"
PORT="${ELYHA_PORT:-}"
PY_BIN="$(command -v python3 || command -v python || true)"

if [[ -z "${HOST}" && -n "${PY_BIN}" && -f "${CONFIG_FILE}" ]]; then
  HOST="$("${PY_BIN}" -c 'import json,sys; cfg=json.load(open(sys.argv[1],encoding="utf-8")); v=str(cfg.get("web_host","")).strip(); print(v)' "${CONFIG_FILE}" 2>/dev/null || true)"
fi
if [[ -z "${PORT}" && -n "${PY_BIN}" && -f "${CONFIG_FILE}" ]]; then
  PORT="$("${PY_BIN}" -c 'import json,sys; cfg=json.load(open(sys.argv[1],encoding="utf-8")); v=cfg.get("web_port",""); print(v if isinstance(v,int) else str(v).strip())' "${CONFIG_FILE}" 2>/dev/null || true)"
fi

HOST="${HOST:-127.0.0.1}"
if [[ -z "${PORT}" ]]; then
  PORT="8765"
fi

echo "[ElyHa] Launching Web GUI with db: ${DB_PATH}"
echo "[ElyHa] Open: http://${HOST}:${PORT}/web"
echo "[ElyHa] Active config profile: ${ACTIVE_PROFILE}"

if command -v uv >/dev/null 2>&1; then
  export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"
  export ELYHA_DB_PATH="${DB_PATH}"
  exec uv run uvicorn elyha_api.app:app --host "${HOST}" --port "${PORT}"
fi

echo "[ElyHa] uv not found, fallback to python -m uvicorn."
export ELYHA_DB_PATH="${DB_PATH}"
exec python -m uvicorn elyha_api.app:app --host "${HOST}" --port "${PORT}"
