#!/usr/bin/env bash
set -euo pipefail

UV_CACHE_DIR=.uv-cache uv sync --extra dev
