# Sakila MCP Server

MySQL（Sakilaデータベース）にアクセスするMCPサーバーのPython実装です。

## 概要

このプロジェクトは、[Model Context Protocol (MCP)](https://modelcontextprotocol.io/) を使用して、LLM（Claude等）からSakilaデータベースに自然言語でクエリを実行できるようにします。

### システム構成

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

## 提供ツール

| ツール名 | 機能 | 入力パラメータ |
|---------|------|---------------|
| `query` | SQLクエリ実行（SELECT のみ） | `sql`: 実行するSQL文 |
| `list_tables` | テーブル一覧取得 | なし |
| `describe_table` | テーブル構造取得 | `table_name`: テーブル名 |
| `get_sample_data` | サンプルデータ取得（最大10行） | `table_name`, `limit`（任意） |

## セットアップ

### 1. リポジトリのクローン

```bash
git clone <repository-url>
cd sakila-mcp-server
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# 必要に応じて .env を編集
```

### 3. MySQL の起動

```bash
docker compose up -d
```

初回起動時、Sakilaデータベースが自動的にインポートされます（約1-2分）。

### 4. 依存関係のインストール

```bash
uv sync
```

### 5. サーバーの起動（動作確認）

```bash
uv run sakila-mcp
```

## Claude Desktop への接続

`~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）または適切な設定ファイルに以下を追加：

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

## 開発

### リント・フォーマット

```bash
# リント
uv run ruff check .

# リント（自動修正）
uv run ruff check --fix .

# フォーマット
uv run ruff format .

# フォーマットチェック
uv run ruff format --check .
```

### テスト

```bash
# 全テスト実行
uv run pytest

# ユニットテストのみ（DB不要）
uv run pytest -m "not integration"

# 統合テストのみ（DB起動後）
uv run pytest -m integration

# カバレッジ付き
uv run pytest --cov=sakila_mcp --cov-report=term-missing
```

## DB接続情報

| 項目 | 値 |
|------|-----|
| Host | localhost |
| Port | 3306 |
| Database | sakila |
| User | sakila_user |
| Password | sakila_pass |

## 使用例

Claude Desktopで以下のような質問ができます。

### 基本的なデータ取得

- 「actorテーブルの最初の5件を見せて」
- 「映画のカテゴリ一覧を教えて」
- 「テーブル一覧を表示して」

### 集計・分析

- 「レンタル回数が最も多い顧客TOP10は？」
- 「カテゴリ別の映画本数を集計して」
- 「2005年7月の日別売上を教えて」
- 「出演映画数が多い俳優ランキングTOP5」
- 「レンタル期間が最も長い映画は？」

### JOIN が必要なクエリ

- 「映画'ACADEMY DINOSAUR'に出演している俳優は？」
- 「顧客'MARY SMITH'のレンタル履歴を見せて」
- 「店舗ごとの売上合計を比較して」
- 「'Action'カテゴリの映画で最もレンタルされているのは？」

### 複雑な分析

- 「レンタルされたことがない映画はある？」
- 「同じ映画を2回以上借りた顧客はいる？」
- 「最も売上が高かった月は？」

### ツール確認

- 「どんなツールが使える？」
- 「filmテーブルの構造を教えて」
- 「customerテーブルのサンプルデータを見せて」

## セキュリティ

- SELECT / SHOW / DESCRIBE / EXPLAIN 文のみ実行可能
- INSERT / UPDATE / DELETE / DROP などの書き込み操作は禁止
- テーブル名のバリデーション（SQLインジェクション対策）
- 環境変数による認証情報管理

## 参考資料

- [MCP 公式ドキュメント](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Sakila スキーマ](https://dev.mysql.com/doc/sakila/en/sakila-structure.html)

## ライセンス

MIT
