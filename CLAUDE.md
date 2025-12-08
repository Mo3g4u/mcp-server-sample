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

### LLMとMCPサーバーの役割分担

```
ユーザー（自然言語）
    ↓
Claude（LLM）: 自然言語理解 → SQL生成
    ↓
MCPサーバー: SQL実行 → 結果返却
    ↓
Claude（LLM）: 結果を自然言語で整形
    ↓
ユーザーへ回答
```

- **LLM**: 自然言語処理、SQL生成、結果の要約
- **MCPサーバー**: ツール定義の公開、クエリ実行

### スキーマ情報の提供方式

LLMが効率的にSQLを生成できるよう、**ツール説明にスキーマを埋め込む方式**を採用。

```python
SAKILA_SCHEMA = """
## 主要テーブル
### actor - 俳優
- actor_id (PK), first_name, last_name
...
"""

Tool(
    name="query",
    description=f"SQLクエリを実行します。\n{SAKILA_SCHEMA}",
    ...
)
```

**この方式のメリット:**
- LLMが即座にスキーマを認識（探索不要）
- ツール呼び出し回数の削減
- トークン消費と応答時間の最適化

**トレードオフ:**
- スキーマ変更時は`SAKILA_SCHEMA`定数の更新が必要
- 動的スキーマには不向き（その場合はResources方式を検討）

### スキーマ更新時のチェックリスト

- [ ] `SAKILA_SCHEMA`定数を更新
- [ ] テーブル名、カラム名、FK関係を確認
- [ ] JOINパターンの例を更新
- [ ] テストで動作確認

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
            name="ツール名",
            description="説明",
            inputSchema={
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        )
    ]
```

### ツール実行

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        # 処理
        return [TextContent(type="text", text=json.dumps(result))]
    except Exception as e:
        return [TextContent(type="text", text=f"エラー: {str(e)}")]
```

## テストパターン

### クラス構成

テストはクラスでグループ化し、`Test`プレフィックスを付ける：

```python
class TestListTools:
    """list_tools関数のテスト"""

    async def test_returns_expected_count(self):
        ...
```

### fixtures（conftest.py）

- `mock_cursor` - DBカーソルのモック
- `mock_connection` - DB接続のモック
- `set_test_env` - テスト用環境変数設定

### DB接続のモック

```python
async def test_example(self, mock_connection, mock_cursor):
    mock_cursor.fetchall = AsyncMock(return_value=[{"id": 1}])

    with patch("sakila_mcp.server.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await execute_query("SELECT * FROM actor")
        assert result == [{"id": 1}]
```

### 統合テスト

実DBが必要なテストは`@pytest.mark.integration`でマーク：

```python
@pytest.mark.integration
class TestIntegration:
    async def test_with_real_db(self):
        ...
```

## コーディング規約

- 型ヒント必須
- 非同期処理は`async/await`
- docstringはモジュール・クラス・公開関数に必須
- SQLインジェクション対策：ユーザー入力は必ず検証
- SELECT/SHOW/DESCRIBE以外のSQL実行禁止
- エラーは`TextContent`で返す
- 1関数80行以内目安

## セキュリティ

### 実装済み対策

- SQL文の種類チェック（SELECT/SHOW/DESCRIBE/EXPLAINのみ許可）
- テーブル名の検証（`isidentifier()`）
- バッククォートによるエスケープ

### 追加時の注意

- 書き込み操作を追加する場合はトランザクション管理必須
- パラメータはプレースホルダ（`%s`）を使用

## DB接続情報

| 項目 | 値 |
|------|-----|
| Host | localhost |
| Port | 3306 |
| Database | sakila |
| User | sakila_user |
| Password | sakila_pass |

## 拡張時のチェックリスト

- [ ] `list_tools()`にツール定義追加
- [ ] `call_tool()`に処理追加
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
