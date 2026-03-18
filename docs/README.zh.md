# ElyHa

[English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md)

**图结构叙事 + AI 辅助创作工具（Web GUI + TUI）**

ElyHa 是一个基于图结构的小说创作系统。你可以用节点图管理剧情分支，并结合多 Agent 流程（LangGraph）进行章节生成、设定审查和逻辑校验。

> 项目仍在持续迭代中。欢迎提 Issue / PR。

## 核心特性

- 图编辑器：拖拽节点、箭头连边、剧情线过滤
- 关系洞察：人物关系、剧情线统计、状态卫星图
- AI 协作流程：Planner -> Writer -> Reviewer -> Synthesizer
- 幽灵节点机制：AI 建议与人工采纳分离，避免直接覆盖
- 版本与审计：快照回滚 + Operation Log
- 多端入口：Web GUI（React）+ TUI（Rich）
- 多语言：中文 / English / 日本語

## 快速开始

### 1) Windows（推荐）

```bat
prepare.bat
LaunchWebUI.bat
```

### 2) Linux / macOS

```bash
bash prepare.sh
./LaunchWebUI.sh
```

### 3) Termux（Android）

```bash
bash termux_prepare.sh
./LaunchWebUI.sh
```

默认地址：`http://127.0.0.1:8765/`

若需手机局域网访问：

```bash
ELYHA_HOST=0.0.0.0 ./LaunchWebUI.sh
```

## 启动脚本

- `prepare.bat` / `prepare.sh`：准备 Python 运行环境与依赖
- `termux_prepare.sh`：Termux 一键准备（安装 `pkg` 依赖 + `uv sync`）
- `LaunchWebUI.bat` / `LaunchWebUI.sh`：启动 Web GUI
- `LaunchTUI.bat` / `LaunchTUI.sh`：启动 TUI

`LaunchWebUI` 默认从 `data/core_configs/active_profile.txt` 指向的配置读取 `web_host/web_port`，可被 `ELYHA_HOST` / `ELYHA_PORT` 覆盖。

## 发布与自动构建

仓库使用 [`Web_Build.yml`](../.github/workflows/Web_Build.yml) 自动打包 Web 完整项目：

- `push` 到 `main/master` 且命中 `elyha_web/**` 更新时：生成开发包并上传到 `dev-build`
- `release published`：生成稳定包并上传到该 Release
- 打包前会自动构建 `elyha_web/dist` 并同步到 `elyha_web/static`

因此用户下载构建产物后，可直接使用 `prepare.bat + LaunchWebUI.bat` 启动。

## 开发者说明

### 环境要求

- Python `>= 3.10`
- 推荐使用 `uv` 管理依赖
- 仅在开发前端时需要 Node.js（运行预编译包不需要）

### 常用命令

```bash
# Python 依赖同步
UV_CACHE_DIR=.uv-cache uv sync

# 启动 API / Web（后端会托管 elyha_web/static）
UV_CACHE_DIR=.uv-cache uv run uvicorn elyha_api.app:app --host 127.0.0.1 --port 8765

# TUI
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main

# 前端开发
cd elyha_web
npm ci
npm run dev
npm run build
```

如果你手动构建前端并希望本地运行后端托管的新静态资源：

```bash
rm -rf elyha_web/static
mkdir -p elyha_web/static
cp -a elyha_web/dist/. elyha_web/static/
```

## 运行配置档（Core Config Profiles）

- 目录：`data/core_configs/`
- 核心配置：`core.json`（只读，禁止改名/删除/覆盖）
- `core` 预设禁止修改；如需调整参数，请先切换到其他预设或新建自定义预设
- 当前激活配置：`data/core_configs/active_profile.txt`
- 支持创建/切换/改名/删除自定义配置
- `auto_complete=true` 时会自动补全 API URL 到 `/chat/completions`

## 国际化

- Web GUI：界面内直接切换语言
- TUI：通过 `ELYHA_LOCALE` 切换

```bash
ELYHA_LOCALE=ja ./LaunchTUI.sh
ELYHA_LOCALE=en ./LaunchTUI.sh
```

## 项目结构

```text
ElyHa/
├── elyha_core/          # 核心领域层（模型、服务、存储）
├── elyha_api/           # FastAPI 服务端
├── elyha_web/           # React Web GUI（源码 + static 构建产物）
├── elyha_tui/           # Rich TUI
├── i18n/                # 国际化词条（zh/en/ja）
├── scripts/             # 工具脚本
├── data/                # 用户数据（项目/配置）
└── LLMRequester/        # Legacy LLM 适配层
```

## License

本项目采用 GPLv3，详见 [LICENSE](../LICENSE)。

## 致谢

- [FastAPI](https://github.com/tiangolo/fastapi)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [React](https://github.com/facebook/react)
- [Rich](https://github.com/Textualize/rich)
- [Pydantic](https://github.com/pydantic/pydantic)
- [uv](https://github.com/astral-sh/uv)
