# Sakila MCP Server

MySQL（Sakilaデータベース）にアクセスするMCPサーバーのPython実装。

## 技術スタック

- Python 3.10+
- uv（パッケージ管理・実行）
- mcp SDK（MCPプロトコル実装）
- aiomysql（非同期MySQLクライアント）
- Docker Compose（MySQL環境）
- ruff（リンター・フォーマッター）
- pytest + pytest-asyncio（テスト）

## ディレクトリ構成

```
sakila-mcp-server/
├── CLAUDE.md             # 開発ガイド（Claude Code用）
├── README.md             # セットアップ手順
├── docker-compose.yml    # MySQL 8.0 + Sakila自動セットアップ
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
    └── test_server.py    # サーバーテスト
```

## アーキテクチャ

### Intent-Based API設計

このMCPサーバーはデータベーススキーマを非公開とし、ビジネス意図ベースのツールを提供する方式を採用。

```
ユーザー（自然言語）
    ↓
Claude（LLM）: 自然言語理解 → ツール選択
    ↓
MCPサーバー: 内部でSQL生成・実行 → 結果返却
    ↓
Claude（LLM）: 結果を自然言語で整形
    ↓
ユーザーへ回答
```

**設計方針:**
- **スキーマ非公開**: テーブル構造、カラム名、FK関係は一切公開しない
- **ビジネス意図ベース**: 「映画を検索する」「顧客詳細を取得する」などの意図に対応
- **パラメータ化クエリ**: SQLインジェクション対策としてすべてのユーザー入力は`%s`プレースホルダ経由
- **入力検証**: rating, store_id等は許可値リストでチェック

### 提供ツール一覧（18ツール）

#### 映画検索・情報系
| ツール | 説明 | 主要パラメータ |
|--------|------|---------------|
| `search_films` | 映画検索 | title, category, rating, actor_name, limit |
| `get_film_details` | 映画詳細（出演者・在庫含む） | title |
| `list_categories` | カテゴリ一覧 | なし |
| `check_film_availability` | 在庫・貸出状況 | title, store_id |

#### 顧客管理系
| ツール | 説明 | 主要パラメータ |
|--------|------|---------------|
| `search_customers` | 顧客検索 | name, email, store_id, active_only |
| `get_customer_details` | 顧客詳細（住所・履歴サマリー） | customer_id or email |

#### レンタル業務系
| ツール | 説明 | 主要パラメータ |
|--------|------|---------------|
| `get_customer_rentals` | レンタル履歴 | customer_id, status |
| `get_overdue_rentals` | 延滞一覧 | store_id, days_overdue |

#### 分析・レポート系（基本）
| ツール | 説明 | 主要パラメータ |
|--------|------|---------------|
| `get_popular_films` | 人気ランキング | period, category, store_id |
| `get_revenue_summary` | 売上サマリー | group_by, store_id |
| `get_store_stats` | 店舗統計 | store_id |
| `get_actor_filmography` | 俳優の出演作品 | actor_name |

#### 顧客分析系
| ツール | 説明 | 主要パラメータ |
|--------|------|---------------|
| `get_top_customers` | 優良顧客ランキング | metric(rentals/spending), period, limit |
| `get_customer_segments` | 顧客セグメント分析 | なし（自動分類） |
| `get_customer_activity` | 顧客アクティビティ分析 | period |

#### 在庫・商品分析系
| ツール | 説明 | 主要パラメータ |
|--------|------|---------------|
| `get_inventory_turnover` | 在庫回転率分析 | store_id, category |
| `get_category_performance` | カテゴリ別パフォーマンス | period, store_id |
| `get_underperforming_films` | 低稼働作品一覧 | days_not_rented, store_id |

## セキュリティ

### 実装済み対策

- **パラメータ化クエリ**: 全ユーザー入力は`%s`プレースホルダー経由
- **入力検証**: 許可値リストによるバリデーション
- **数値制限**: limitは最大50件
- **フィールド制限**: 返却JSONは必要フィールドのみ
- **エラーメッセージ**: SQLエラー詳細は非公開

### 入力検証定数

```python
VALID_RATINGS = {"G", "PG", "PG-13", "R", "NC-17"}
VALID_STORES = {1, 2}
VALID_RENTAL_STATUS = {"all", "active", "returned"}
VALID_GROUP_BY = {"store", "category", "month", "staff"}
VALID_PERIOD = {"all_time", "last_month", "last_week"}
VALID_METRICS = {"rentals", "spending"}
```

## 開発コマンド

```bash
# DB起動
docker compose up -d

# 依存関係インストール
uv sync

# サーバー実行
uv run sakila-mcp

# 依存関係追加
uv add <package-name>
uv add --dev <dev-package-name>
```

## リント・フォーマット

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

## テスト

```bash
# 全テスト実行
uv run pytest

# カバレッジ付き
uv run pytest --cov=sakila_mcp --cov-report=term-missing

# 特定テスト
uv run pytest tests/test_server.py::TestListTools -v

# ユニットテストのみ（DB不要）
uv run pytest -m "not integration"

# 統合テストのみ（DB必要）
uv run pytest -m integration
```

## CI実行例

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest -m "not integration" --cov=sakila_mcp
```

## MCPサーバー実装パターン

### ツール定義

```python
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_films",
            description="映画を検索します。タイトル、カテゴリ、レーティング等で絞り込み可能。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "タイトル（部分一致）"},
                    "category": {"type": "string", "description": "カテゴリ名"},
                    "rating": {"type": "string", "enum": ["G", "PG", "PG-13", "R", "NC-17"]},
                    "limit": {"type": "integer", "maximum": 50, "default": 10}
                }
            }
        )
    ]
```

### ビジネスロジック関数

```python
async def search_films(
    title: str | None = None,
    category: str | None = None,
    rating: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """映画を検索する。"""
    rating = validate_rating(rating)  # 入力検証
    limit = validate_limit(limit)

    sql = "SELECT ... FROM film f WHERE 1=1"
    params: list[Any] = []

    if title:
        sql += " AND f.title LIKE %s"
        params.append(f"%{title}%")

    # ... その他の条件

    sql += " LIMIT %s"
    params.append(limit)

    return await execute_query(sql, tuple(params))
```

### ツール実行

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "search_films":
            result = await search_films(
                title=arguments.get("title"),
                category=arguments.get("category"),
                rating=arguments.get("rating"),
                limit=arguments.get("limit", DEFAULT_LIMIT),
            )
        # ... 他のツール

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text="処理中にエラーが発生しました。")]
```

## テストパターン

### クラス構成

テストはクラスでグループ化し、`Test`プレフィックスを付ける：

```python
class TestListTools:
    """list_tools関数のテスト"""

    async def test_returns_expected_count(self):
        tools = await list_tools()
        assert len(tools) == 18

class TestValidationFunctions:
    """バリデーション関数のテスト"""

    def test_validate_rating_valid(self):
        for rating in VALID_RATINGS:
            result = validate_rating(rating)
            assert result == rating
```

### fixtures（conftest.py）

- `mock_cursor` - DBカーソルのモック
- `mock_connection` - DB接続のモック
- `set_test_env` - テスト用環境変数設定

### DB接続のモック

```python
async def test_search_films(self, mock_connection, mock_cursor):
    mock_cursor.fetchall = AsyncMock(
        return_value=[{"title": "Test Film", "category": "Action"}]
    )

    with patch("sakila_mcp.server.get_connection") as mock_get_conn:
        mock_get_conn.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=mock_connection),
            __aexit__=AsyncMock(return_value=None),
        )

        result = await call_tool("search_films", {"title": "Test"})
        assert "Test Film" in result[0].text
```

### 統合テスト

実DBが必要なテストは`@pytest.mark.integration`でマーク：

```python
@pytest.mark.integration
class TestIntegration:
    async def test_search_films_with_real_db(self):
        result = await call_tool("search_films", {"limit": 5})
        import json
        data = json.loads(result[0].text)
        assert len(data) <= 5
```

## コーディング規約

- 型ヒント必須
- 非同期処理は`async/await`
- docstringはモジュール・クラス・公開関数に必須
- パラメータ化クエリ必須（`%s`プレースホルダ使用）
- 入力は必ず検証関数を通す
- エラーは`TextContent`で返す（詳細なSQLエラーは非公開）
- 1関数80行以内目安

## DB接続情報

| 項目 | 値 |
|------|-----|
| Host | localhost |
| Port | 3306 |
| Database | sakila |
| User | sakila_user |
| Password | sakila_pass |

## 拡張時のチェックリスト

- [ ] ビジネスロジック関数を追加
- [ ] `list_tools()`にツール定義追加
- [ ] `call_tool()`に処理追加
- [ ] 入力検証関数を追加（必要に応じて）
- [ ] テストクラス追加（ユニット・統合）
- [ ] README更新
- [ ] `uv run ruff check .` パス
- [ ] `uv run pytest` パス

## 参考リンク

- [MCP公式ドキュメント](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Sakilaスキーマ](https://dev.mysql.com/doc/sakila/en/sakila-structure.html)
- [ruff](https://docs.astral.sh/ruff/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
