# ElyHa

[English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md)

**グラフ構造の物語制作 + AI 支援ツール（Web GUI + TUI）**

ElyHa は、グラフ構造を中心にした小説制作システムです。ノード/エッジで分岐を管理し、マルチエージェントワークフロー（LangGraph）で章生成、設定レビュー、一貫性チェックを行えます。

> 本プロジェクトは継続的に開発中です。Issue / PR を歓迎します。

## 主な機能

- グラフエディタ：ノードのドラッグ、エッジ接続、ストーリーラインのフィルタ
- インサイト表示：人物関係、ストーリー統計、状態サテライト図
- AI ワークフロー：Planner -> Writer -> Reviewer -> Synthesizer
- ゴーストノード方式：AI 提案と人間の採用を分離し、直接上書きを防止
- バージョン管理と監査：スナップショット + Operation Log
- 複数入口：Web GUI（React）+ TUI（Rich）
- 多言語：中文 / English / 日本語

## クイックスタート

### 1) Windows（推奨）

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

デフォルト URL：`http://127.0.0.1:8765/`

モバイル端末から LAN でアクセスする場合：

```bash
ELYHA_HOST=0.0.0.0 ./LaunchWebUI.sh
```

## 起動スクリプト

- `prepare.bat` / `prepare.sh`：Python 実行環境と依存関係を準備
- `termux_prepare.sh`：Termux ワンクリック準備（`pkg` 依存 + `uv sync`）
- `LaunchWebUI.bat` / `LaunchWebUI.sh`：Web GUI を起動
- `LaunchTUI.bat` / `LaunchTUI.sh`：TUI を起動

`LaunchWebUI` は既定で `data/core_configs/active_profile.txt` のアクティブ設定から `web_host/web_port` を読み込みます。`ELYHA_HOST` / `ELYHA_PORT` で上書きできます。

## リリースと自動ビルド

リポジトリは [`Web_Build.yml`](../.github/workflows/Web_Build.yml) で Web 完全パッケージを自動生成します。

- `main/master` への `push`（`elyha_web/**` 更新を含む）：開発版を生成して `dev-build` にアップロード
- `release published`：安定版を生成して当該 Release にアップロード
- パッケージ化前に `elyha_web/dist` を `elyha_web/static` へ同期

そのため、配布物は `prepare.bat + LaunchWebUI.bat` でそのまま起動できます。

## 開発者向け

### 要件

- Python `>= 3.10`
- 依存管理には `uv` を推奨
- Node.js はフロント開発時のみ必要（実行済み配布物の利用には不要）

### よく使うコマンド

```bash
# Python 依存を同期
UV_CACHE_DIR=.uv-cache uv sync

# API / Web を起動（backend が elyha_web/static を配信）
UV_CACHE_DIR=.uv-cache uv run uvicorn elyha_api.app:app --host 127.0.0.1 --port 8765

# TUI
UV_CACHE_DIR=.uv-cache uv run python -m elyha_tui.main

# フロント開発
cd elyha_web
npm ci
npm run dev
npm run build
```

フロントを手動ビルドした後に backend 配信を更新する場合：

```bash
rm -rf elyha_web/static
mkdir -p elyha_web/static
cp -a elyha_web/dist/. elyha_web/static/
```

## 実行プロファイル（Core Config Profiles）

- ディレクトリ：`data/core_configs/`
- コア設定：`core.json`（読み取り専用。改名/削除/上書き禁止）
- `core` プリセットは編集不可。設定変更は他プリセットへ切替、またはカスタムプリセットを作成してから行ってください
- アクティブ設定：`data/core_configs/active_profile.txt`
- カスタム設定は作成/切替/改名/削除が可能
- `auto_complete=true` の場合、API URL は `/chat/completions` へ自動補完

## 国際化

- Web GUI：UI 内で言語切替
- TUI：`ELYHA_LOCALE` で切替

```bash
ELYHA_LOCALE=ja ./LaunchTUI.sh
ELYHA_LOCALE=en ./LaunchTUI.sh
```

## プロジェクト構成

```text
ElyHa/
├── elyha_core/          # コアドメイン層（モデル、サービス、ストレージ）
├── elyha_api/           # FastAPI バックエンド
├── elyha_web/           # React Web GUI（ソース + static 成果物）
├── elyha_tui/           # Rich TUI
├── i18n/                # ローカライズ辞書（zh/en/ja）
├── scripts/             # ツールスクリプト
├── data/                # ユーザーデータ（プロジェクト/設定）
└── LLMRequester/        # 旧 LLM アダプタ層
```

## License

GPLv3。詳細は [LICENSE](../LICENSE) を参照してください。

## 謝辞

- [FastAPI](https://github.com/tiangolo/fastapi)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [React](https://github.com/facebook/react)
- [Rich](https://github.com/Textualize/rich)
- [Pydantic](https://github.com/pydantic/pydantic)
- [uv](https://github.com/astral-sh/uv)
