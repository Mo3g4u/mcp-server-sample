# Sakila MCP Server

MySQL（Sakilaデータベース）にアクセスするMCPサーバーのPython実装です。

## 概要

このプロジェクトは、[Model Context Protocol (MCP)](https://modelcontextprotocol.io/) を使用して、LLM（Claude等）からSakilaデータベースに自然言語でアクセスできるようにします。

**Intent-Based API設計**を採用し、データベーススキーマを非公開としながら、ビジネス意図ベースの18種類のツールを提供します。

### システム構成

```
┌─────────────────┐                         ┌─────────────────┐
│  ユーザー        │  自然言語               │  Claude (LLM)   │
│  (Human)        │ ─────────────────────► │  意図理解       │
└─────────────────┘                         └────────┬────────┘
                                                     │ ツール選択
                                                     ▼
┌─────────────────┐     MCP Protocol        ┌─────────────────┐
│  Claude Desktop │ ◄────────────────────► │  MCP Server     │
│  (Host)         │    stdio transport      │  (Python)       │
└─────────────────┘                         └────────┬────────┘
                                                     │ SQL生成・実行
                                                     │ aiomysql
                                                     ▼
                                            ┌─────────────────┐
                                            │  MySQL 8.0      │
                                            │  (Sakila DB)    │
                                            └─────────────────┘
```

### 設計思想

- **スキーマ非公開**: テーブル構造、カラム名、FK関係は一切公開しない
- **ビジネス意図ベース**: 「映画を検索する」「顧客詳細を取得する」などの意図に対応
- **セキュリティ重視**: パラメータ化クエリ、入力検証、エラーメッセージ制御

## 提供ツール（18種類）

### 映画検索・情報系

| ツール名 | 機能 | 主要パラメータ |
|---------|------|---------------|
| `search_films` | 映画検索（タイトル、カテゴリ、レーティング、俳優名） | title, category, rating, actor_name, limit |
| `get_film_details` | 映画詳細取得（出演者・在庫情報含む） | title |
| `list_categories` | カテゴリ一覧取得 | なし |
| `check_film_availability` | 在庫・貸出状況確認 | title, store_id |

### 顧客管理系

| ツール名 | 機能 | 主要パラメータ |
|---------|------|---------------|
| `search_customers` | 顧客検索 | name, email, store_id, active_only |
| `get_customer_details` | 顧客詳細取得（住所・履歴サマリー含む） | customer_id or email |

### レンタル業務系

| ツール名 | 機能 | 主要パラメータ |
|---------|------|---------------|
| `get_customer_rentals` | レンタル履歴取得 | customer_id, status |
| `get_overdue_rentals` | 延滞一覧取得 | store_id, days_overdue |

### 分析・レポート系

| ツール名 | 機能 | 主要パラメータ |
|---------|------|---------------|
| `get_popular_films` | 人気映画ランキング | period, category, store_id, limit |
| `get_revenue_summary` | 売上サマリー | group_by, store_id, period |
| `get_store_stats` | 店舗統計 | store_id |
| `get_actor_filmography` | 俳優の出演作品一覧 | actor_name |

### 顧客分析系

| ツール名 | 機能 | 主要パラメータ |
|---------|------|---------------|
| `get_top_customers` | 優良顧客ランキング | metric (rentals/spending), period, limit |
| `get_customer_segments` | 顧客セグメント分析 | なし（自動分類） |
| `get_customer_activity` | 顧客アクティビティ分析 | period |

### 在庫・商品分析系

| ツール名 | 機能 | 主要パラメータ |
|---------|------|---------------|
| `get_inventory_turnover` | 在庫回転率分析 | store_id, category |
| `get_category_performance` | カテゴリ別パフォーマンス | period, store_id |
| `get_underperforming_films` | 低稼働作品一覧 | days_not_rented, store_id |

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

## 使用例

Claude Desktopで以下のような質問ができます。

### 映画検索

- 「アクション映画を検索して」
- 「PG-13の映画を5本教えて」
- 「Tom Hanksが出演している映画は？」
- 「映画'ACADEMY DINOSAUR'の詳細を教えて」

### 顧客情報

- 「Smithという名前の顧客を検索して」
- 「顧客ID 1番の詳細情報を見せて」
- 「アクティブな顧客だけを検索して」

### レンタル業務

- 「顧客ID 1番のレンタル履歴を見せて」
- 「延滞している顧客は誰？」
- 「店舗1の延滞状況を確認して」

### 分析・レポート

- 「今月の人気映画ランキングを教えて」
- 「カテゴリ別の売上サマリーを見せて」
- 「店舗ごとの統計を比較して」
- 「優良顧客TOP10は？」

### 在庫分析

- 「在庫回転率が低い映画は？」
- 「カテゴリ別のパフォーマンスを分析して」
- 「30日以上レンタルされていない映画を教えて」

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

## セキュリティ

### 実装済み対策

- **パラメータ化クエリ**: すべてのユーザー入力は`%s`プレースホルダー経由
- **入力検証**: 許可値リストによるバリデーション
  - rating: G, PG, PG-13, R, NC-17
  - store_id: 1, 2
  - period: all_time, last_month, last_week
  - 等
- **数値制限**: limitは最大50件
- **フィールド制限**: 返却JSONは必要フィールドのみ
- **エラーメッセージ**: SQLエラー詳細は非公開

## ディレクトリ構成

```
sakila-mcp-server/
├── CLAUDE.md             # 開発ガイド（Claude Code用）
├── README.md             # セットアップ手順（本ファイル）
├── docker-compose.yml    # MySQL 8.0 + Sakila自動セットアップ
├── init/
│   └── 01-init-sakila.sh # Sakila DB 初期化スクリプト
├── pyproject.toml        # 依存関係・ツール設定
├── .env.example          # 環境変数テンプレート
├── sakila_mcp/
│   ├── __init__.py
│   └── server.py         # MCPサーバー本体（18ツール実装）
└── tests/
    ├── __init__.py
    ├── conftest.py       # 共通fixtures
    └── test_server.py    # サーバーテスト（43テスト）
```

## ドキュメント

- [CLAUDE.md](CLAUDE.md) - 開発者向け詳細ガイド（アーキテクチャ、コーディング規約、テストパターン）
- [docs/SAKILA_DATABASE.md](docs/SAKILA_DATABASE.md) - Sakilaデータベース概要
- [docs/MCP_IMPLEMENTATION_PATTERNS.md](docs/MCP_IMPLEMENTATION_PATTERNS.md) - MCP実装パターンガイド

## 参考資料

- [MCP 公式ドキュメント](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Sakila スキーマ](https://dev.mysql.com/doc/sakila/en/sakila-structure.html)

## ライセンス

MIT
