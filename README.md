# ElyHa

**图结构化叙事 + AI 辅助创作工具**

> ⚠️ 本项目正在稳步开发中，可能存在不完善之处。如果您有任何建议、发现 bug 或有新的思路，欢迎提 Issue 或 PR，非常感谢！

ElyHa 是一个基于图结构的小说创作系统，通过节点图可视化管理剧情分支，结合 AI 多 Agent 编排（LangGraph）辅助章节生成、设定审查与逻辑校验。

## 核心特性

- **图编辑器** - 拖拽节点、箭头连边、剧情线着色过滤
- **关系洞察图** - 自动分析人物关系、世界观、剧情线统计
- **幽灵节点流程** - AI 建议 → 人工采纳，避免直接覆盖
- **多 Agent 编排** - Planner → Writer → Reviewer → Synthesizer 四阶段生成
- **版本控制** - 快照回滚 + Operation Log 完整历史
- **多端支持** - Web GUI（React）+ TUI（命令行）
- **国际化** - 中文 / English / 日本語

## 快速开始

### 启动 Web GUI（推荐）

```bash
# Windows
LaunchGUI.bat

# Linux/macOS
./LaunchGUI.sh
```

浏览器打开 `http://127.0.0.1:8765/`（默认端口，您可以在Web中修改）

### 启动 TUI（命令行）

```bash
# Windows
LaunchTUI.bat

# Linux/macOS
./LaunchTUI.sh
```

## 项目结构

```text
ElyHa/
├── elyha_core/          # 核心领域层（模型、服务、存储）
├── elyha_api/           # FastAPI 服务端
├── elyha_web/           # React Web GUI
├── elyha_tui/           # Rich TUI 命令行界面
├── tests/               # 单元测试
├── scripts/             # 工具脚本
├── i18n/                # 国际化词条（zh/en/ja）
├── data/                # 用户数据（项目/配置）
└── LLMRequester/        # Legacy LLM 适配层
```

## 技术架构

- **核心层** - Python 3.12, SQLite, Pydantic
- **AI 编排** - LangGraph (StateGraph)
- **API 层** - FastAPI + Uvicorn
- **Web 前端** - React 18 (Vendored)
- **TUI** - Rich + Textual
- **包管理** - uv (快速依赖解析)

## 开发环境

### 安装依赖

```bash
# 安装 uv（如未安装）
pip install uv

# 自动创建虚拟环境并安装依赖
UV_CACHE_DIR=.uv-cache uv sync
```


## 国际化

支持中文 / English / 日本語

- **Web GUI** - 界面内直接切换语言（右上角设置）
- **TUI** - 通过环境变量 `ELYHA_LOCALE` 切换

```bash
# TUI 日语模式
ELYHA_LOCALE=ja ./LaunchTUI.sh

# TUI 英语模式
ELYHA_LOCALE=en ./LaunchTUI.sh
```

## 常用命令

```bash
# 运行迁移
UV_CACHE_DIR=.uv-cache uv run python scripts/migrate.py --db ./data/dev.db

# 启动 Web GUI（React）
UV_CACHE_DIR=.uv-cache uv run uvicorn elyha_api.app:app --reload
# 浏览器打开 http://127.0.0.1:8000/

# TUI 冒烟
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --smoke

# 启动本地 API
UV_CACHE_DIR=.uv-cache uv run uvicorn elyha_api.app:app --reload

# TUI 交互模式
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main

# TUI 图编辑子模式（在交互界面输入 graph-edit）
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --automation graph-view --project-id <proj_id>

# TUI 自动化命令示例
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --automation project-create --title "My Novel"
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --automation node-add --project-id <proj_id> --title "Ch1"
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --automation node-move --project-id <proj_id> --node-id <node_id> --pos-x 180 --pos-y 120
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --automation generate-chapter --project-id <proj_id> --node-id <node_id> --workflow-mode multi_agent
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main --automation task-list --project-id <proj_id> --limit 10
```

## 启动脚本

- `LaunchTUI.bat` / `LaunchTUI.sh`: 启动 Rich TUI
- `LaunchGUI.bat` / `LaunchGUI.sh`: 启动本地 Web GUI（React，Tauri 可复用）
  - 默认从 `data/core_configs/active_profile.txt` 对应配置读取 `web_host/web_port`（可被 `ELYHA_HOST/ELYHA_PORT` 覆盖）

## 运行配置档（Core Config Profiles）

- 目录：`data/core_configs/`
- 核心配置：`core.json`（只读，禁止改名/删除/覆盖）
- 支持多配置档创建、切换、改名、删除（仅自定义配置）
- 当前激活档记录于：`data/core_configs/active_profile.txt`
- `auto_complete=true` 时会自动把 API URL 补全到 `/chat/completions`；关闭后严格按你填写的 URL 请求。

## 致谢

本项目基于以下优秀的开源项目构建：

- [FastAPI](https://github.com/tiangolo/fastapi) - 现代化的 Python Web 框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - AI Agent 编排框架
- [React](https://github.com/facebook/react) - 用户界面库
- [Rich](https://github.com/Textualize/rich) - 终端美化库
- [Pydantic](https://github.com/pydantic/pydantic) - 数据验证库
- [uv](https://github.com/astral-sh/uv) - 快速 Python 包管理器

## 贡献者

<a href="https://github.com/ShadowLoveElysia/ElyHa/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ShadowLoveElysia/ElyHa" />
</a>
