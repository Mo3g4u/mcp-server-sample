"""Tests for Sakila MCP Server."""

from unittest.mock import AsyncMock, patch

import pytest

from sakila_mcp.server import (
    SAKILA_SCHEMA,
    SAKILA_TABLES,
    call_tool,
    execute_query,
    list_tools,
    validate_sql,
    validate_table_name,
)


class TestListTools:
    """list_tools関数のテスト。"""

    async def test_returns_four_tools(self):
        """4つのツールが返されることを確認。"""
        tools = await list_tools()
        assert len(tools) == 4

    async def test_tool_names(self):
        """ツール名が正しいことを確認。"""
        tools = await list_tools()
        names = {tool.name for tool in tools}
        assert names == {"query", "list_tables", "describe_table", "get_sample_data"}

    async def test_query_tool_has_schema_info(self):
        """queryツールの説明にスキーマ情報が含まれることを確認。"""
        tools = await list_tools()
        query_tool = next(t for t in tools if t.name == "query")
        assert "actor" in query_tool.description
        assert "film" in query_tool.description
        assert "customer" in query_tool.description

    async def test_query_tool_has_required_sql_param(self):
        """queryツールにsqlパラメータが必須であることを確認。"""
        tools = await list_tools()
        query_tool = next(t for t in tools if t.name == "query")
        assert "sql" in query_tool.inputSchema["required"]

    async def test_describe_table_has_required_table_name(self):
        """describe_tableツールにtable_nameパラメータが必須であることを確認。"""
        tools = await list_tools()
        describe_tool = next(t for t in tools if t.name == "describe_table")
        assert "table_name" in describe_tool.inputSchema["required"]

    async def test_get_sample_data_has_limit_param(self):
        """get_sample_dataツールにlimitパラメータがあることを確認。"""
        tools = await list_tools()
        sample_tool = next(t for t in tools if t.name == "get_sample_data")
        assert "limit" in sample_tool.inputSchema["properties"]
        # limitの最大値が10であることを確認
        assert sample_tool.inputSchema["properties"]["limit"]["maximum"] == 10


class TestValidateSql:
    """validate_sql関数のテスト。"""

    def test_select_is_allowed(self):
        """SELECT文が許可されることを確認。"""
        is_valid, error = validate_sql("SELECT * FROM actor")
        assert is_valid is True
        assert error == ""

    def test_show_is_allowed(self):
        """SHOW文が許可されることを確認。"""
        is_valid, error = validate_sql("SHOW TABLES")
        assert is_valid is True
        assert error == ""

    def test_describe_is_allowed(self):
        """DESCRIBE文が許可されることを確認。"""
        is_valid, error = validate_sql("DESCRIBE actor")
        assert is_valid is True
        assert error == ""

    def test_explain_is_allowed(self):
        """EXPLAIN文が許可されることを確認。"""
        is_valid, error = validate_sql("EXPLAIN SELECT * FROM actor")
        assert is_valid is True
        assert error == ""

    def test_insert_is_rejected(self):
        """INSERT文が拒否されることを確認。"""
        is_valid, error = validate_sql("INSERT INTO actor (first_name) VALUES ('test')")
        assert is_valid is False
        assert "許可されていないSQLコマンド" in error

    def test_update_is_rejected(self):
        """UPDATE文が拒否されることを確認。"""
        is_valid, error = validate_sql("UPDATE actor SET first_name = 'test'")
        assert is_valid is False
        assert "許可されていないSQLコマンド" in error

    def test_delete_is_rejected(self):
        """DELETE文が拒否されることを確認。"""
        is_valid, error = validate_sql("DELETE FROM actor")
        assert is_valid is False
        assert "許可されていないSQLコマンド" in error

    def test_drop_is_rejected(self):
        """DROP文が拒否されることを確認。"""
        is_valid, error = validate_sql("DROP TABLE actor")
        assert is_valid is False
        assert "許可されていないSQLコマンド" in error

    def test_truncate_is_rejected(self):
        """TRUNCATE文が拒否されることを確認。"""
        is_valid, error = validate_sql("TRUNCATE TABLE actor")
        assert is_valid is False
        assert "許可されていないSQLコマンド" in error

    def test_subquery_with_delete_is_rejected(self):
        """サブクエリ内のDELETEが拒否されることを確認。"""
        is_valid, error = validate_sql("SELECT * FROM actor; DELETE FROM actor")
        assert is_valid is False
        assert "DELETE" in error

    def test_empty_sql_is_rejected(self):
        """空のSQL文が拒否されることを確認。"""
        is_valid, error = validate_sql("")
        assert is_valid is False
        assert "空" in error

    def test_whitespace_only_is_rejected(self):
        """空白のみのSQL文が拒否されることを確認。"""
        is_valid, error = validate_sql("   ")
        assert is_valid is False
        assert "空" in error


class TestValidateTableName:
    """validate_table_name関数のテスト。"""

    def test_valid_table_name(self):
        """有効なテーブル名が許可されることを確認。"""
        is_valid, error = validate_table_name("actor")
        assert is_valid is True
        assert error == ""

    def test_all_sakila_tables_are_valid(self):
        """Sakilaの全テーブルが有効であることを確認。"""
        for table in SAKILA_TABLES:
            is_valid, error = validate_table_name(table)
            assert is_valid is True, f"Table {table} should be valid"

    def test_invalid_table_name(self):
        """無効なテーブル名が拒否されることを確認。"""
        is_valid, error = validate_table_name("nonexistent_table")
        assert is_valid is False
        assert "存在しません" in error

    def test_empty_table_name(self):
        """空のテーブル名が拒否されることを確認。"""
        is_valid, error = validate_table_name("")
        assert is_valid is False
        assert "空" in error

    def test_sql_injection_attempt(self):
        """SQLインジェクションの試みが拒否されることを確認。"""
        is_valid, error = validate_table_name("actor; DROP TABLE actor")
        assert is_valid is False

    def test_special_characters_rejected(self):
        """特殊文字を含むテーブル名が拒否されることを確認。"""
        is_valid, error = validate_table_name("actor--comment")
        assert is_valid is False


class TestExecuteQuery:
    """execute_query関数のテスト。"""

    async def test_rejects_insert(self):
        """INSERT文が拒否されることを確認。"""
        with pytest.raises(ValueError, match="許可されていないSQLコマンド"):
            await execute_query("INSERT INTO actor (first_name) VALUES ('test')")

    async def test_rejects_update(self):
        """UPDATE文が拒否されることを確認。"""
        with pytest.raises(ValueError, match="許可されていないSQLコマンド"):
            await execute_query("UPDATE actor SET first_name = 'test'")

    async def test_rejects_delete(self):
        """DELETE文が拒否されることを確認。"""
        with pytest.raises(ValueError, match="許可されていないSQLコマンド"):
            await execute_query("DELETE FROM actor")

    async def test_rejects_drop(self):
        """DROP文が拒否されることを確認。"""
        with pytest.raises(ValueError, match="許可されていないSQLコマンド"):
            await execute_query("DROP TABLE actor")

    async def test_select_calls_database(self, mock_connection, mock_cursor):
        """SELECT文がデータベースを呼び出すことを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[{"actor_id": 1, "first_name": "Test"}])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection), __aexit__=AsyncMock(return_value=None)
            )

            result = await execute_query("SELECT * FROM actor LIMIT 1")
            assert result == [{"actor_id": 1, "first_name": "Test"}]
            mock_cursor.execute.assert_called_once_with("SELECT * FROM actor LIMIT 1")


class TestCallTool:
    """call_tool関数のテスト。"""

    async def test_unknown_tool_returns_error(self):
        """未知のツールがエラーを返すことを確認。"""
        result = await call_tool("unknown_tool", {})
        assert len(result) == 1
        assert "未知のツール" in result[0].text

    async def test_describe_table_invalid_name_returns_error(self):
        """無効なテーブル名がエラーを返すことを確認。"""
        result = await call_tool("describe_table", {"table_name": "invalid_table"})
        assert len(result) == 1
        assert "エラー" in result[0].text

    async def test_get_sample_data_invalid_name_returns_error(self):
        """無効なテーブル名がエラーを返すことを確認。"""
        result = await call_tool("get_sample_data", {"table_name": "invalid_table"})
        assert len(result) == 1
        assert "エラー" in result[0].text

    async def test_get_sample_data_limit_capped_at_10(self, mock_connection, mock_cursor):
        """get_sample_dataのlimitが10に制限されることを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection), __aexit__=AsyncMock(return_value=None)
            )

            await call_tool("get_sample_data", {"table_name": "actor", "limit": 100})
            # limitが10に制限されていることを確認
            call_args = mock_cursor.execute.call_args[0][0]
            assert "LIMIT 10" in call_args

    async def test_get_sample_data_limit_minimum_1(self, mock_connection, mock_cursor):
        """get_sample_dataのlimitが最小1に制限されることを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection), __aexit__=AsyncMock(return_value=None)
            )

            await call_tool("get_sample_data", {"table_name": "actor", "limit": -5})
            # limitが1に制限されていることを確認
            call_args = mock_cursor.execute.call_args[0][0]
            assert "LIMIT 1" in call_args

    async def test_list_tables_returns_table_names(self, mock_connection, mock_cursor):
        """list_tablesがテーブル名のリストを返すことを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[{"Tables_in_sakila": "actor"}, {"Tables_in_sakila": "film"}])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection), __aexit__=AsyncMock(return_value=None)
            )

            result = await call_tool("list_tables", {})
            assert "actor" in result[0].text
            assert "film" in result[0].text

    async def test_query_returns_results(self, mock_connection, mock_cursor):
        """queryが結果を返すことを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[{"actor_id": 1, "first_name": "PENELOPE"}])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection), __aexit__=AsyncMock(return_value=None)
            )

            result = await call_tool("query", {"sql": "SELECT * FROM actor LIMIT 1"})
            assert "PENELOPE" in result[0].text


class TestSchemaInfo:
    """スキーマ情報のテスト。"""

    def test_schema_contains_main_tables(self):
        """スキーマ情報に主要テーブルが含まれることを確認。"""
        assert "actor" in SAKILA_SCHEMA
        assert "film" in SAKILA_SCHEMA
        assert "customer" in SAKILA_SCHEMA
        assert "rental" in SAKILA_SCHEMA
        assert "payment" in SAKILA_SCHEMA

    def test_schema_contains_join_patterns(self):
        """スキーマ情報にJOINパターンが含まれることを確認。"""
        assert "JOIN" in SAKILA_SCHEMA

    def test_schema_contains_foreign_keys(self):
        """スキーマ情報に外部キー情報が含まれることを確認。"""
        assert "FK" in SAKILA_SCHEMA


@pytest.mark.integration
class TestIntegration:
    """統合テスト（実際のデータベース接続が必要）。"""

    async def test_list_tables_with_real_db(self):
        """実際のDBでlist_tablesが動作することを確認。"""
        result = await call_tool("list_tables", {})
        # 結果にactorテーブルが含まれることを確認
        assert "actor" in result[0].text

    async def test_query_with_real_db(self):
        """実際のDBでqueryが動作することを確認。"""
        result = await call_tool("query", {"sql": "SELECT COUNT(*) as count FROM actor"})
        # 結果にcount情報が含まれることを確認
        assert "count" in result[0].text

    async def test_describe_table_with_real_db(self):
        """実際のDBでdescribe_tableが動作することを確認。"""
        result = await call_tool("describe_table", {"table_name": "actor"})
        # actor_idカラムが含まれることを確認
        assert "actor_id" in result[0].text

    async def test_get_sample_data_with_real_db(self):
        """実際のDBでget_sample_dataが動作することを確認。"""
        result = await call_tool("get_sample_data", {"table_name": "actor", "limit": 3})
        # 結果がJSON形式であることを確認
        import json

        data = json.loads(result[0].text)
        assert len(data) <= 3
