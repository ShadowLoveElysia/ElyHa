# Architecture

## Core-first layout

- `elyha_core`: 唯一业务规则来源
- `elyha_tui`: Rich TUI 入口，仅调用 core 服务
- `elyha_api`: FastAPI 适配层，仅参数转换，不承载业务规则
- `LLMRequester`: 历史调用能力，后续通过 adapter 接入

## Current implemented services

- `ProjectService`: 项目生命周期、设置、revision 与 operation log
- `GraphService`: 节点/边增删改查、重复边检测、禁环约束
- `ValidationService`: merge 入边约束、孤立节点和结构报告
- `ExportService`: 导出前校验 + mainline/topological Markdown 导出
- `SnapshotService`: 快照写入、快照列表、基于快照+operation 重放回滚
- `ContextService`: token 预算下的上下文组装（当前节点/祖先/近期节点）
- `AIService`: 统一章节生成、分支生成、设定与逻辑审查、task 状态管理
- `LLM Adapter`: 内置 `mock` + 可选 `legacy LLMRequester` 适配
- `LangGraph`: AIService 提供单链路与多 Agent 章节编排
  - 单链路：`context -> prompt -> llm`
  - 多 Agent：`planner -> writer -> reviewer -> synthesizer`
- `I18N`: 运行时从 `i18n/{locale}.json` 加载文案，当前支持 `zh/en/ja`

## Storage

- SQLite + migration versioning
- append-only `operation_logs`
- project-level `active_revision` 自增
