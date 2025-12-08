"""
Sakila MCP Server - MySQL database access via MCP protocol.

MCPプロトコルを通じてSakilaデータベースにアクセスするサーバー。
LLMが自然言語でクエリを実行できるよう、スキーマ情報をツール説明に埋め込む。
"""

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from typing import Any

import aiomysql
import mcp.server.stdio
import mcp.types as types
from dotenv import load_dotenv
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

load_dotenv()

# Sakilaデータベースのスキーマ情報
# LLMが効率的にSQLを生成できるよう、ツール説明に埋め込む
SAKILA_SCHEMA = """
## Sakila Database Schema

### 主要テーブル

#### actor - 俳優情報
- actor_id (PK, SMALLINT UNSIGNED AUTO_INCREMENT)
- first_name (VARCHAR(45))
- last_name (VARCHAR(45))
- last_update (TIMESTAMP)

#### film - 映画情報
- film_id (PK, SMALLINT UNSIGNED AUTO_INCREMENT)
- title (VARCHAR(128))
- description (TEXT)
- release_year (YEAR)
- language_id (FK → language.language_id)
- original_language_id (FK → language.language_id, NULL)
- rental_duration (TINYINT UNSIGNED, DEFAULT 3)
- rental_rate (DECIMAL(4,2), DEFAULT 4.99)
- length (SMALLINT UNSIGNED) - 上映時間（分）
- replacement_cost (DECIMAL(5,2), DEFAULT 19.99)
- rating (ENUM: 'G','PG','PG-13','R','NC-17')
- special_features (SET: 'Trailers','Commentaries','Deleted Scenes','Behind the Scenes')
- last_update (TIMESTAMP)

#### customer - 顧客情報
- customer_id (PK, SMALLINT UNSIGNED AUTO_INCREMENT)
- store_id (FK → store.store_id)
- first_name (VARCHAR(45))
- last_name (VARCHAR(45))
- email (VARCHAR(50))
- address_id (FK → address.address_id)
- active (BOOLEAN, DEFAULT TRUE)
- create_date (DATETIME)
- last_update (TIMESTAMP)

#### rental - レンタル記録
- rental_id (PK, INT AUTO_INCREMENT)
- rental_date (DATETIME)
- inventory_id (FK → inventory.inventory_id)
- customer_id (FK → customer.customer_id)
- return_date (DATETIME, NULL)
- staff_id (FK → staff.staff_id)
- last_update (TIMESTAMP)

#### payment - 支払い記録
- payment_id (PK, SMALLINT UNSIGNED AUTO_INCREMENT)
- customer_id (FK → customer.customer_id)
- staff_id (FK → staff.staff_id)
- rental_id (FK → rental.rental_id, NULL)
- amount (DECIMAL(5,2))
- payment_date (DATETIME)
- last_update (TIMESTAMP)

#### inventory - 在庫管理
- inventory_id (PK, MEDIUMINT UNSIGNED AUTO_INCREMENT)
- film_id (FK → film.film_id)
- store_id (FK → store.store_id)
- last_update (TIMESTAMP)

#### category - 映画カテゴリ
- category_id (PK, TINYINT UNSIGNED AUTO_INCREMENT)
- name (VARCHAR(25))
- last_update (TIMESTAMP)

#### language - 言語
- language_id (PK, TINYINT UNSIGNED AUTO_INCREMENT)
- name (CHAR(20))
- last_update (TIMESTAMP)

#### store - 店舗情報
- store_id (PK, TINYINT UNSIGNED AUTO_INCREMENT)
- manager_staff_id (FK → staff.staff_id)
- address_id (FK → address.address_id)
- last_update (TIMESTAMP)

#### staff - スタッフ情報
- staff_id (PK, TINYINT UNSIGNED AUTO_INCREMENT)
- first_name (VARCHAR(45))
- last_name (VARCHAR(45))
- address_id (FK → address.address_id)
- picture (BLOB, NULL)
- email (VARCHAR(50))
- store_id (FK → store.store_id)
- active (BOOLEAN, DEFAULT TRUE)
- username (VARCHAR(16))
- password (VARCHAR(40))
- last_update (TIMESTAMP)

#### address - 住所情報
- address_id (PK, SMALLINT UNSIGNED AUTO_INCREMENT)
- address (VARCHAR(50))
- address2 (VARCHAR(50), NULL)
- district (VARCHAR(20))
- city_id (FK → city.city_id)
- postal_code (VARCHAR(10))
- phone (VARCHAR(20))
- last_update (TIMESTAMP)

#### city - 都市情報
- city_id (PK, SMALLINT UNSIGNED AUTO_INCREMENT)
- city (VARCHAR(50))
- country_id (FK → country.country_id)
- last_update (TIMESTAMP)

#### country - 国情報
- country_id (PK, SMALLINT UNSIGNED AUTO_INCREMENT)
- country (VARCHAR(50))
- last_update (TIMESTAMP)

### 関連テーブル（多対多）

#### film_actor - 映画と俳優の関連
- actor_id (PK, FK → actor.actor_id)
- film_id (PK, FK → film.film_id)
- last_update (TIMESTAMP)

#### film_category - 映画とカテゴリの関連
- film_id (PK, FK → film.film_id)
- category_id (PK, FK → category.category_id)
- last_update (TIMESTAMP)

### よく使うJOINパターン

1. 映画と出演俳優:
   film JOIN film_actor ON film.film_id = film_actor.film_id
   JOIN actor ON film_actor.actor_id = actor.actor_id

2. 映画とカテゴリ:
   film JOIN film_category ON film.film_id = film_category.film_id
   JOIN category ON film_category.category_id = category.category_id

3. レンタルと映画:
   rental JOIN inventory ON rental.inventory_id = inventory.inventory_id
   JOIN film ON inventory.film_id = film.film_id

4. 顧客と支払い履歴:
   customer JOIN payment ON customer.customer_id = payment.customer_id

5. 完全な顧客住所:
   customer JOIN address ON customer.address_id = address.address_id
   JOIN city ON address.city_id = city.city_id
   JOIN country ON city.country_id = country.country_id

### ビュー

- actor_info: 俳優の出演映画カテゴリ一覧
- customer_list: 顧客情報と住所の結合ビュー
- film_list: 映画情報とカテゴリ、俳優の結合ビュー
- nicer_but_slower_film_list: 整形済み映画リスト
- sales_by_film_category: カテゴリ別売上
- sales_by_store: 店舗別売上
- staff_list: スタッフ情報と住所の結合ビュー
"""

# 許可されたSQLコマンド（読み取り専用）
ALLOWED_SQL_COMMANDS = {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}

# Sakilaデータベースのテーブル一覧
SAKILA_TABLES = {
    "actor",
    "address",
    "category",
    "city",
    "country",
    "customer",
    "film",
    "film_actor",
    "film_category",
    "film_text",
    "inventory",
    "language",
    "payment",
    "rental",
    "staff",
    "store",
}


def get_db_config() -> dict[str, Any]:
    """環境変数からDB接続設定を取得する。"""
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "db": os.getenv("MYSQL_DATABASE", "sakila"),
        "user": os.getenv("MYSQL_USER", "sakila_user"),
        "password": os.getenv("MYSQL_PASSWORD", "sakila_pass"),
    }


@asynccontextmanager
async def get_connection():
    """DB接続を取得するコンテキストマネージャー。"""
    config = get_db_config()
    conn = await aiomysql.connect(**config, cursorclass=aiomysql.DictCursor)
    try:
        yield conn
    finally:
        conn.close()


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    SQLの安全性を検証する。

    Args:
        sql: 検証するSQL文

    Returns:
        (is_valid, error_message) のタプル
    """
    # 空文字チェック
    sql = sql.strip()
    if not sql:
        return False, "SQL文が空です"

    # コマンドの抽出
    first_word = sql.split()[0].upper()

    # 許可されたコマンドかチェック
    if first_word not in ALLOWED_SQL_COMMANDS:
        return (
            False,
            f"許可されていないSQLコマンドです: {first_word}。SELECT, SHOW, DESCRIBE, EXPLAIN のみ実行可能です。",
        )

    # 危険なキーワードのチェック（サブクエリ内での書き込み操作を防ぐ）
    dangerous_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE"]
    sql_upper = sql.upper()
    for keyword in dangerous_keywords:
        # 単語境界でマッチ（カラム名などとの誤検出を防ぐ）
        if re.search(rf"\b{keyword}\b", sql_upper):
            return False, f"危険なキーワードが含まれています: {keyword}"

    return True, ""


def validate_table_name(table_name: str) -> tuple[bool, str]:
    """
    テーブル名の安全性を検証する。

    Args:
        table_name: 検証するテーブル名

    Returns:
        (is_valid, error_message) のタプル
    """
    # 空文字チェック
    if not table_name:
        return False, "テーブル名が空です"

    # 識別子として有効かチェック
    if not table_name.isidentifier():
        return False, f"無効なテーブル名です: {table_name}"

    # Sakilaテーブルに存在するかチェック
    if table_name.lower() not in SAKILA_TABLES:
        return False, f"テーブルが存在しません: {table_name}。利用可能なテーブル: {', '.join(sorted(SAKILA_TABLES))}"

    return True, ""


async def execute_query(sql: str) -> list[dict[str, Any]]:
    """
    SQLクエリを実行する。

    Args:
        sql: 実行するSQL文

    Returns:
        クエリ結果のリスト

    Raises:
        ValueError: SQLが無効な場合
    """
    is_valid, error = validate_sql(sql)
    if not is_valid:
        raise ValueError(error)

    async with get_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql)
            results = await cursor.fetchall()
            return list(results)


# MCPサーバーの初期化
server = Server("sakila-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """利用可能なツールの一覧を返す。"""
    return [
        types.Tool(
            name="query",
            description=f"""SQLクエリを実行します（SELECT文のみ）。

{SAKILA_SCHEMA}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "実行するSQL文（SELECT/SHOW/DESCRIBE/EXPLAINのみ）",
                    }
                },
                "required": ["sql"],
            },
        ),
        types.Tool(
            name="list_tables",
            description="Sakilaデータベースのテーブル一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="describe_table",
            description="指定したテーブルの構造（カラム情報）を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "テーブル名",
                    }
                },
                "required": ["table_name"],
            },
        ),
        types.Tool(
            name="get_sample_data",
            description="指定したテーブルのサンプルデータを取得します（最大10行）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "テーブル名",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "取得する行数（1-10、デフォルト: 5）",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 5,
                    },
                },
                "required": ["table_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """
    ツールを実行する。

    Args:
        name: ツール名
        arguments: ツールの引数

    Returns:
        実行結果のTextContentリスト
    """
    try:
        if name == "query":
            sql = arguments.get("sql", "")
            results = await execute_query(sql)
            return [types.TextContent(type="text", text=json.dumps(results, ensure_ascii=False, default=str))]

        elif name == "list_tables":
            results = await execute_query("SHOW TABLES")
            # MySQLのSHOW TABLESはカラム名が動的なので整形
            tables = [list(row.values())[0] for row in results]
            return [types.TextContent(type="text", text=json.dumps(tables, ensure_ascii=False))]

        elif name == "describe_table":
            table_name = arguments.get("table_name", "")
            is_valid, error = validate_table_name(table_name)
            if not is_valid:
                return [types.TextContent(type="text", text=f"エラー: {error}")]

            # バッククォートでエスケープしてSQLインジェクションを防ぐ
            results = await execute_query(f"DESCRIBE `{table_name}`")
            return [types.TextContent(type="text", text=json.dumps(results, ensure_ascii=False, default=str))]

        elif name == "get_sample_data":
            table_name = arguments.get("table_name", "")
            is_valid, error = validate_table_name(table_name)
            if not is_valid:
                return [types.TextContent(type="text", text=f"エラー: {error}")]

            limit = arguments.get("limit", 5)
            # limitを1-10の範囲に制限
            limit = max(1, min(10, int(limit)))

            results = await execute_query(f"SELECT * FROM `{table_name}` LIMIT {limit}")
            return [types.TextContent(type="text", text=json.dumps(results, ensure_ascii=False, default=str))]

        else:
            return [types.TextContent(type="text", text=f"エラー: 未知のツールです: {name}")]

    except ValueError as e:
        return [types.TextContent(type="text", text=f"エラー: {e!s}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"エラー: {e!s}")]


async def run():
    """MCPサーバーを起動する。"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="sakila-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main():
    """エントリーポイント。"""
    asyncio.run(run())


if __name__ == "__main__":
    main()
