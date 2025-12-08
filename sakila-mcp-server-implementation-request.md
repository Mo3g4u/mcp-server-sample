# Sakila MCP Server 実装依頼書

## 1. 概要

### 1.1 プロジェクト名
Sakila MCP Server

### 1.2 目的
MySQL データベース（Sakila サンプルDB）に対して、MCP（Model Context Protocol）を介してLLM（Claude等）から自然言語でクエリを実行できるサーバーを構築する。
https://dev.mysql.com/doc/sakila/en/

### 1.3 背景
- MCPサーバーの実装パターンを習得するためのサンプルプロジェクト
- 将来的に社内データベースへのAI連携基盤として応用を想定

### 1.4 スコープ
- MCPサーバーの実装（Python）
- ローカル開発環境の構築（Docker Compose）
- ユニットテスト・統合テストの整備

---

## 2. 機能要件

### 2.1 提供ツール

| ツール名 | 機能 | 入力パラメータ |
|---------|------|---------------|
| `query` | SQLクエリ実行（SELECT のみ） | `sql`: 実行するSQL文 |
| `list_tables` | テーブル一覧取得 | なし |
| `describe_table` | テーブル構造取得 | `table_name`: テーブル名 |
| `get_sample_data` | サンプルデータ取得（最大10行） | `table_name`, `limit`（任意） |

### 2.2 セキュリティ要件

- SELECT / SHOW / DESCRIBE 文のみ実行可能（INSERT/UPDATE/DELETE/DROP 禁止）
- テーブル名のバリデーション（SQLインジェクション対策）
- 環境変数による認証情報管理

### 2.3 スキーマ情報の提供

LLMが効率的にSQLを生成できるよう、`query` ツールの説明にSakilaデータベースのスキーマ情報を埋め込む。

含める情報：
- 主要テーブル（actor, film, customer, rental, payment 等）
- カラム名と主キー/外部キー
- テーブル間のリレーション
- よく使うJOINパターン

---

## 3. 技術要件

### 3.1 技術スタック

| 項目 | 技術 |
|------|------|
| 言語 | Python 3.10+ |
| パッケージ管理 | uv |
| MCPライブラリ | mcp SDK |
| DBクライアント | aiomysql（非同期） |
| データベース | MySQL 8.0（Docker） |
| リンター/フォーマッター | ruff |
| テスト | pytest, pytest-asyncio, pytest-cov |

### 3.2 開発環境

- Docker Compose によるMySQL環境
- Sakilaサンプルデータの自動インポート
- 環境変数による設定（.env ファイル）

---

## 4. アーキテクチャ

### 4.1 システム構成

```
┌─────────────────┐     MCP Protocol      ┌─────────────────┐
│  Claude Desktop │ ◄──────────────────► │  MCP Server     │
│  (LLM)          │    stdio transport    │  (Python)       │
└─────────────────┘                       └────────┬────────┘
                                                   │
                                                   │ aiomysql
                                                   ▼
                                          ┌─────────────────┐
                                          │  MySQL 8.0      │
                                          │  (Sakila DB)    │
                                          └─────────────────┘
```

### 4.2 処理フロー

```
1. ユーザーが自然言語で質問（例：「レンタル数TOP5の映画は？」）
2. LLM がスキーマ情報を参照してSQLを生成
3. LLM が query ツールを呼び出し
4. MCP サーバーがSQLを実行
5. 結果をJSON形式で返却
6. LLM が結果を自然言語で整形して回答
```

### 4.3 役割分担

| コンポーネント | 役割 |
|---------------|------|
| LLM（Claude） | 自然言語理解、SQL生成、結果の要約 |
| MCPサーバー | ツール定義の公開、SQLの実行、結果返却 |

---

## 5. ファイル構成

```
sakila-mcp-server/
├── CLAUDE.md             # 開発ガイド（Claude Code用）
├── README.md             # セットアップ手順
├── docker-compose.yml    # MySQL コンテナ定義
├── init/
│   └── 01-init-sakila.sh # Sakila DB 初期化スクリプト
├── pyproject.toml        # 依存関係・ツール設定
├── .env.example          # 環境変数テンプレート
├── sakila_mcp/
│   ├── __init__.py
│   └── server.py         # MCPサーバー本体
└── tests/
    ├── __init__.py
    ├── conftest.py       # 共通fixtures
    └── test_server.py    # テストコード
```

---

## 6. 実装詳細

### 6.1 server.py の構成

```python
# 1. スキーマ定義
SAKILA_SCHEMA = """
## 主要テーブル
### actor - 俳優
- actor_id (PK), first_name, last_name
...
"""

# 2. ツール一覧
@server.list_tools()
async def list_tools() -> list[Tool]:
    ...

# 3. ツール実行
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    ...

# 4. クエリ実行（内部関数）
async def execute_query(sql: str) -> list[dict]:
    ...
```

### 6.2 pyproject.toml

```toml
[project]
name = "sakila-mcp-server"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
    "aiomysql>=0.2.0",
    "python-dotenv>=1.0.0",
]

[dependency-groups]
dev = [
    "ruff>=0.8.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0.0",
]

[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["integration: tests requiring database connection"]
```

---

## 7. テスト要件

### 7.1 ユニットテスト（DB不要）

| テスト対象 | 内容 |
|-----------|------|
| list_tools | ツール数、ツール名、必須パラメータ、スキーマ情報の存在 |
| execute_query | INSERT/UPDATE/DELETE/DROP の拒否 |
| call_tool | 未知のツール、無効なテーブル名の拒否、LIMIT制限 |

### 7.2 統合テスト（DB必要）

| テスト対象 | 内容 |
|-----------|------|
| list_tables | Sakilaテーブル一覧の取得 |
| query | 実際のSELECT実行と結果検証 |

### 7.3 テストコマンド

```bash
# ユニットテストのみ
uv run pytest -m "not integration"

# 全テスト（DB起動後）
uv run pytest

# カバレッジ
uv run pytest --cov=sakila_mcp --cov-report=term-missing
```

---

## 8. 開発コマンド

```bash
# 環境構築
docker compose up -d      # MySQL起動
cp .env.example .env      # 環境変数設定
uv sync                   # 依存関係インストール

# 実行
uv run sakila-mcp         # サーバー起動

# 品質管理
uv run ruff check .       # リント
uv run ruff format .      # フォーマット
uv run pytest             # テスト
```

---

## 9. Claude Desktop 連携設定

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sakila": {
      "command": "uv",
      "args": ["--directory", "/path/to/sakila-mcp-server", "run", "sakila-mcp"]
    }
  }
}
```

---

## 10. DB接続情報

| 項目 | 値 |
|------|-----|
| Host | localhost |
| Port | 3306 |
| Database | sakila |
| User | sakila_user |
| Password | sakila_pass |
| Root Password | rootpassword |

---

## 11. 成果物

| 成果物 | 説明 |
|-------|------|
| ソースコード | sakila_mcp/ 配下 |
| テストコード | tests/ 配下 |
| 開発環境 | docker-compose.yml, init/ |
| ドキュメント | README.md, CLAUDE.md |
| 設定ファイル | pyproject.toml, .env.example |

---

## 12. 受入基準

- [ ] `uv run ruff check .` がエラーなしで通ること
- [ ] `uv run ruff format --check .` がエラーなしで通ること
- [ ] `uv run pytest -m "not integration"` が全件パスすること
- [ ] `uv run pytest -m integration` が全件パスすること（DB起動時）
- [ ] Claude Desktop から接続し、自然言語でクエリが実行できること
- [ ] CLAUDE.md が最新の実装を反映していること

---

## 13. 参考資料

- [MCP 公式ドキュメント](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Sakila スキーマ](https://dev.mysql.com/doc/sakila/en/sakila-structure.html)
- [ruff](https://docs.astral.sh/ruff/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
