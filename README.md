# ElyHa

[English](README.md) | [中文](docs/README.zh.md) | [日本語](docs/README.ja.md)

**Graph-based narrative authoring with AI assistance (Web GUI + TUI)**

ElyHa is a graph-first novel writing system. You can manage branching storylines with nodes/edges and use multi-agent workflows (LangGraph) for chapter generation, setting review, and consistency checks.

> The project is under active development. Issues and PRs are welcome.

## Features

- Graph editor: drag nodes, connect edges, filter storylines
- Insight view: character relations, storyline stats, state satellite view
- AI workflow: Planner -> Writer -> Reviewer -> Synthesizer
- Ghost-node workflow: AI proposals + human adoption, no forced overwrite
- Versioning and audit: snapshots + operation log
- Multi-entry: Web GUI (React) + TUI (Rich)
- Localization: Chinese / English / Japanese

## Quick Start

### 1) Windows (Recommended)

```bat
prepare.bat
LaunchWebUI.bat
```

### 2) Linux / macOS

```bash
bash prepare.sh
./LaunchWebUI.sh
```

### 3) Termux (Android)

```bash
bash termux_prepare.sh
./LaunchWebUI.sh
```

Default URL: `http://127.0.0.1:8765/`

For LAN access on mobile:

```bash
ELYHA_HOST=0.0.0.0 ./LaunchWebUI.sh
```

## Startup Scripts

- `prepare.bat` / `prepare.sh`: prepare Python runtime and dependencies
- `termux_prepare.sh`: one-click Termux setup (`pkg` dependencies + `uv sync`)
- `LaunchWebUI.bat` / `LaunchWebUI.sh`: start Web GUI
- `LaunchTUI.bat` / `LaunchTUI.sh`: start TUI

`LaunchWebUI` reads `web_host/web_port` from the active profile in `data/core_configs/active_profile.txt` by default. You can override with `ELYHA_HOST` / `ELYHA_PORT`.

## Release and Auto Build

The repository uses [`Web_Build.yml`](.github/workflows/Web_Build.yml) for automated web bundling:

- On `push` to `main/master` with `elyha_web/**` updates: build dev package and upload to `dev-build`
- On `release published`: build stable package and upload to that release
- Before packaging, `elyha_web/dist` is synced to `elyha_web/static`

So users can run downloaded bundles directly with `prepare.bat + LaunchWebUI.bat`.

## Developer Notes

### Requirements

- Python `>= 3.10`
- `uv` is recommended for dependency management
- Node.js is only needed for frontend development (not required for prebuilt runtime)

### Common Commands

```bash
# Sync Python dependencies
UV_CACHE_DIR=.uv-cache uv sync

# Start API / Web (backend serves elyha_web/static)
UV_CACHE_DIR=.uv-cache uv run uvicorn elyha_api.app:app --host 127.0.0.1 --port 8765

# TUI
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main

# Frontend development
cd elyha_web
npm ci
npm run dev
npm run build
```

If you build frontend manually and want backend to serve the new static files:

```bash
rm -rf elyha_web/static
mkdir -p elyha_web/static
cp -a elyha_web/dist/. elyha_web/static/
```

## Runtime Profiles (Core Config Profiles)

- Directory: `data/core_configs/`
- Core profile: `core.json` (read-only, must not be renamed/deleted/overwritten)
- The `core` preset is not editable. To change settings, switch to another preset or create a custom preset first.
- Active profile marker: `data/core_configs/active_profile.txt`
- Custom profiles can be created/switched/renamed/deleted
- When `auto_complete=true`, API URLs are auto-completed to `/chat/completions`

## Internationalization

- Web GUI: switch language in UI
- TUI: use `ELYHA_LOCALE`

```bash
ELYHA_LOCALE=ja ./LaunchTUI.sh
ELYHA_LOCALE=en ./LaunchTUI.sh
```

## Project Structure

```text
ElyHa/
├── elyha_core/          # core domain layer (models, services, storage)
├── elyha_api/           # FastAPI backend
├── elyha_web/           # React Web GUI (source + static artifacts)
├── elyha_tui/           # Rich TUI
├── i18n/                # locale catalogs (zh/en/ja)
├── scripts/             # utility scripts
├── data/                # user data (projects/configs)
└── LLMRequester/        # legacy LLM adapter layer
```

## License

GPLv3. See [LICENSE](LICENSE).

## Acknowledgements

- [FastAPI](https://github.com/tiangolo/fastapi)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [React](https://github.com/facebook/react)
- [Rich](https://github.com/Textualize/rich)
- [Pydantic](https://github.com/pydantic/pydantic)
- [uv](https://github.com/astral-sh/uv)

## Contributors

<a href="https://github.com/ShadowLoveElysia/ElyHa/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ShadowLoveElysia/ElyHa" />
</a>
