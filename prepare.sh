#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[ElyHa] Preparing environment..."

# Check if uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo "[ElyHa] uv not found. Installing uv from official source..."
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        export PATH="$HOME/.local/bin:$PATH"
        echo "[ElyHa] uv installed successfully."
    else
        echo "[ElyHa] Official install failed. Trying pip fallback..."
        if command -v pip >/dev/null 2>&1; then
            pip install uv
        elif command -v pip3 >/dev/null 2>&1; then
            pip3 install uv
        else
            echo "[ElyHa] Error: All install methods failed."
            echo "[ElyHa] Visit: https://docs.astral.sh/uv/getting-started/installation/"
            exit 1
        fi
    fi
fi

echo "[ElyHa] uv found. Installing dependencies..."
export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"
uv sync

echo "[ElyHa] Setup complete!"
echo "[ElyHa] Run './LaunchWebUI.sh' to start Web GUI"
echo "[ElyHa] Run './LaunchTUI.sh' to start TUI"
