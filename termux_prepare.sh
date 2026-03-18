#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

is_termux=0
if command -v pkg >/dev/null 2>&1 && [[ "${PREFIX:-}" == *"com.termux"* ]]; then
  is_termux=1
fi

if [[ "$is_termux" -ne 1 ]]; then
  echo "[ElyHa] This script is for Termux only."
  echo "[ElyHa] Current PREFIX: ${PREFIX:-<empty>}"
  exit 1
fi

echo "[ElyHa] Termux environment detected."
echo "[ElyHa] Installing system dependencies..."

pkg update -y
pkg upgrade -y
pkg install -y \
  bash \
  coreutils \
  curl \
  git \
  openssl \
  libffi \
  pkg-config \
  python \
  clang \
  rust \
  make

if command -v termux-setup-storage >/dev/null 2>&1; then
  echo "[ElyHa] Tip: run 'termux-setup-storage' once if you need shared storage access."
fi

echo "[ElyHa] Checking uv..."
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "[ElyHa] uv not found. Installing from official script..."
  if curl -LsSf https://astral.sh/uv/install.sh | sh; then
    export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
  else
    echo "[ElyHa] Official uv install failed. Fallback to pip..."
    python -m pip install --upgrade pip
    python -m pip install --user uv
    export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[ElyHa] Error: uv installation failed."
  exit 1
fi

echo "[ElyHa] Syncing Python environment..."
export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-termux}"
uv sync

echo "[ElyHa] Done."
echo "[ElyHa] Start Web UI:"
echo "  ./LaunchWebUI.sh"
echo "[ElyHa] If you want LAN access, use:"
echo "  ELYHA_HOST=0.0.0.0 ./LaunchWebUI.sh"
