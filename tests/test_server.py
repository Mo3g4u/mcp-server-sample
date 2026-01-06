"""Tests for Sakila MCP Server (Intent-Based API)."""

from unittest.mock import AsyncMock, patch

import pytest

from sakila_mcp.server import (
    VALID_GROUP_BY,
    VALID_METRICS,
    VALID_PERIOD,
    VALID_RATINGS,
    VALID_RENTAL_STATUS,
    VALID_STORES,
    call_tool,
    execute_query,
    list_tools,
    validate_limit,
    validate_period,
    validate_rating,
    validate_rental_status,
    validate_store_id,
)


class TestListTools:
    """list_tools関数のテスト。"""

    async def test_returns_eighteen_tools(self):
        """18個のツールが返されることを確認。"""
        tools = await list_tools()
        assert len(tools) == 18

    async def test_tool_names(self):
        """ツール名が正しいことを確認。"""
        tools = await list_tools()
        names = {tool.name for tool in tools}
        expected_names = {
            # 映画検索・情報系
            "search_films",
            "get_film_details",
            "list_categories",
            "check_film_availability",
            # 顧客管理系
            "search_customers",
            "get_customer_details",
            # レンタル業務系
            "get_customer_rentals",
            "get_overdue_rentals",
            # 基本分析系
            "get_popular_films",
            "get_revenue_summary",
            "get_store_stats",
            "get_actor_filmography",
            # 顧客分析系
            "get_top_customers",
            "get_customer_segments",
            "get_customer_activity",
            # 在庫・商品分析系
            "get_inventory_turnover",
            "get_category_performance",
            "get_underperforming_films",
        }
        assert names == expected_names

    async def test_no_schema_exposure(self):
        """ツール説明にスキーマ情報が露出していないことを確認。"""
        tools = await list_tools()
        forbidden_terms = ["PRIMARY KEY", "FOREIGN KEY", "FK", "PK", "CREATE TABLE", "テーブル構造"]
        for tool in tools:
            for term in forbidden_terms:
                assert term not in tool.description, f"Tool {tool.name} exposes schema info: {term}"

    async def test_search_films_has_expected_params(self):
        """search_filmsツールに期待されるパラメータがあることを確認。"""
        tools = await list_tools()
        search_tool = next(t for t in tools if t.name == "search_films")
        props = search_tool.inputSchema["properties"]
        assert "title" in props
        assert "category" in props
        assert "rating" in props
        assert "actor_name" in props
        assert "limit" in props

    async def test_get_customer_details_requires_identifier(self):
        """get_customer_detailsツールに顧客特定パラメータがあることを確認。"""
        tools = await list_tools()
        tool = next(t for t in tools if t.name == "get_customer_details")
        props = tool.inputSchema["properties"]
        assert "customer_id" in props or "email" in props


class TestValidationFunctions:
    """バリデーション関数のテスト。"""

    def test_validate_rating_valid(self):
        """有効なratingが許可されることを確認。"""
        for rating in VALID_RATINGS:
            result = validate_rating(rating)
            assert result == rating

    def test_validate_rating_invalid(self):
        """無効なratingがValueErrorを発生させることを確認。"""
        with pytest.raises(ValueError, match="無効なレーティング"):
            validate_rating("X")
        with pytest.raises(ValueError, match="無効なレーティング"):
            validate_rating("invalid")

    def test_validate_rating_none(self):
        """Noneの入力がNoneを返すことを確認。"""
        assert validate_rating(None) is None

    def test_validate_store_id_valid(self):
        """有効なstore_idが許可されることを確認。"""
        for store_id in VALID_STORES:
            result = validate_store_id(store_id)
            assert result == store_id

    def test_validate_store_id_invalid(self):
        """無効なstore_idがValueErrorを発生させることを確認。"""
        with pytest.raises(ValueError, match="無効な店舗ID"):
            validate_store_id(3)
        with pytest.raises(ValueError, match="無効な店舗ID"):
            validate_store_id(0)
        with pytest.raises(ValueError, match="無効な店舗ID"):
            validate_store_id(-1)

    def test_validate_store_id_none(self):
        """Noneの入力がNoneを返すことを確認。"""
        assert validate_store_id(None) is None

    def test_validate_limit_within_range(self):
        """範囲内のlimitがそのまま返されることを確認。"""
        assert validate_limit(10) == 10
        assert validate_limit(25) == 25
        assert validate_limit(50) == 50

    def test_validate_limit_exceeds_max(self):
        """最大値を超えるlimitが50に制限されることを確認。"""
        assert validate_limit(100) == 50
        assert validate_limit(1000) == 50

    def test_validate_limit_below_min(self):
        """最小値未満のlimitが1に制限されることを確認。"""
        assert validate_limit(0) == 1
        assert validate_limit(-5) == 1

    def test_validate_period_valid(self):
        """有効なperiodが許可されることを確認。"""
        for period in VALID_PERIOD:
            result = validate_period(period)
            assert result == period

    def test_validate_period_invalid(self):
        """無効なperiodがValueErrorを発生させることを確認。"""
        with pytest.raises(ValueError, match="無効な期間"):
            validate_period("invalid")

    def test_validate_rental_status_valid(self):
        """有効なrental_statusが許可されることを確認。"""
        for status in VALID_RENTAL_STATUS:
            result = validate_rental_status(status)
            assert result == status

    def test_validate_rental_status_invalid(self):
        """無効なrental_statusがValueErrorを発生させることを確認。"""
        with pytest.raises(ValueError, match="無効なステータス"):
            validate_rental_status("invalid")


class TestExecuteQuery:
    """execute_query関数のテスト。"""

    async def test_select_with_params(self, mock_connection, mock_cursor):
        """パラメータ付きSELECT文が正しく実行されることを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[{"id": 1}])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await execute_query("SELECT * FROM film WHERE rating = %s", ("PG",))
            assert result == [{"id": 1}]
            mock_cursor.execute.assert_called_once_with("SELECT * FROM film WHERE rating = %s", ("PG",))

    async def test_select_without_params(self, mock_connection, mock_cursor):
        """パラメータなしSELECT文が正しく実行されることを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[{"count": 10}])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await execute_query("SELECT COUNT(*) as count FROM film")
            assert result == [{"count": 10}]


class TestCallTool:
    """call_tool関数のテスト。"""

    async def test_unknown_tool_returns_error(self):
        """未知のツールがエラーを返すことを確認。"""
        result = await call_tool("unknown_tool", {})
        assert len(result) == 1
        assert "未知のツール" in result[0].text

    async def test_search_films_basic(self, mock_connection, mock_cursor):
        """search_filmsが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[{"title": "Test Film", "category": "Action", "rating": "PG"}])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("search_films", {"title": "Test"})
            assert "Test Film" in result[0].text

    async def test_search_films_with_invalid_rating(self, mock_connection, mock_cursor):
        """search_filmsが無効なratingを無視することを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("search_films", {"title": "Test", "rating": "INVALID"})
            # エラーなく空結果が返る（無効なratingは無視される）
            assert len(result) == 1

    async def test_list_categories(self, mock_connection, mock_cursor):
        """list_categoriesが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {"name": "Action", "film_count": 64},
                {"name": "Comedy", "film_count": 58},
            ]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("list_categories", {})
            assert "Action" in result[0].text
            assert "Comedy" in result[0].text

    async def test_get_customer_details_by_id(self):
        """get_customer_detailsがcustomer_idで検索できることを確認。"""
        # get_customer_details関数を直接モックする
        from sakila_mcp import server

        with patch.object(
            server,
            "get_customer_details",
            new=AsyncMock(
                return_value={
                    "customer_id": 1,
                    "name": "John Doe",
                    "email": "john@example.com",
                    "address": "123 Main St, Tokyo, Japan",
                    "phone": "123-456-7890",
                    "store": "Store 1",
                    "active": True,
                    "registration_date": "2024-01-01",
                    "total_rentals": 10,
                    "total_spent": 50.00,
                }
            ),
        ):
            result = await call_tool("get_customer_details", {"customer_id": 1})
            assert "John" in result[0].text

    async def test_get_customer_details_not_found(self, mock_connection, mock_cursor):
        """get_customer_detailsが顧客が見つからない場合のエラーを返すことを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_customer_details", {"customer_id": 99999})
            assert "見つかりませんでした" in result[0].text

    async def test_get_overdue_rentals(self, mock_connection, mock_cursor):
        """get_overdue_rentalsが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "rental_id": 1,
                    "customer_name": "John Doe",
                    "film_title": "Test Film",
                    "rental_date": "2024-01-01",
                    "days_overdue": 10,
                }
            ]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_overdue_rentals", {"days_overdue": 7})
            assert "John Doe" in result[0].text
            assert "Test Film" in result[0].text

    async def test_get_store_stats(self, mock_connection, mock_cursor):
        """get_store_statsが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "store_id": 1,
                    "manager": "John Manager",
                    "address": "123 Store St, City, Country",
                    "total_customers": 326,
                    "active_customers": 318,
                    "total_inventory": 2270,
                    "total_rentals": 5000,
                    "total_revenue": 10000.50,
                }
            ]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_store_stats", {"store_id": 1})
            assert "326" in result[0].text


class TestSecurityMeasures:
    """セキュリティ対策のテスト。"""

    async def test_sql_injection_in_title_search(self, mock_connection, mock_cursor):
        """タイトル検索でのSQLインジェクションが防がれることを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            # SQLインジェクションの試み
            await call_tool("search_films", {"title": "'; DROP TABLE film; --"})

            # パラメータ化されたクエリが使用されていることを確認
            call_args = mock_cursor.execute.call_args
            query = call_args[0][0]
            params = call_args[0][1] if len(call_args[0]) > 1 else None

            # クエリにプレースホルダが使われている
            assert "%s" in query
            assert params is not None
            # 悪意のある入力がパラメータとして渡される（LIKEパターンのため%が付加される）
            assert any("DROP TABLE" in str(p) for p in params)

    async def test_invalid_store_id_rejected(self, mock_connection, mock_cursor):
        """無効なstore_idがエラーを返すことを確認。"""
        # 無効なstore_id（3は存在しない）はエラーになる
        result = await call_tool("get_store_stats", {"store_id": 3})
        # エラーメッセージが返される
        assert len(result) == 1
        assert "エラー" in result[0].text

    async def test_limit_enforced(self, mock_connection, mock_cursor):
        """limitが最大値に制限されることを確認。"""
        mock_cursor.fetchall = AsyncMock(return_value=[])

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            await call_tool("search_films", {"title": "Test", "limit": 1000})

            # パラメータ化されたクエリでLIMITが50に制限されていることを確認
            call_args = mock_cursor.execute.call_args
            params = call_args[0][1] if len(call_args[0]) > 1 else None
            # パラメータの最後がlimit値（50）であることを確認
            assert params is not None
            assert 50 in params


class TestAnalysisTools:
    """分析系ツールのテスト。"""

    async def test_get_popular_films(self, mock_connection, mock_cursor):
        """get_popular_filmsが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "title": "Popular Film",
                    "category": "Action",
                    "rental_count": 100,
                    "total_revenue": 500.00,
                }
            ]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_popular_films", {"limit": 10})
            assert "Popular Film" in result[0].text

    async def test_get_revenue_summary_by_store(self, mock_connection, mock_cursor):
        """get_revenue_summaryがstore別で正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[{"group_key": "Store 1", "total_revenue": "5000.00", "payment_count": 100}]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_revenue_summary", {"group_by": "store"})
            assert "5000" in result[0].text

    async def test_get_top_customers(self, mock_connection, mock_cursor):
        """get_top_customersが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "customer_id": 1,
                    "name": "Top Customer",
                    "email": "top@example.com",
                    "store": "Store 1",
                    "rental_count": 50,
                    "total_spent": 200.00,
                }
            ]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_top_customers", {"metric": "rentals", "limit": 10})
            assert "Top Customer" in result[0].text

    async def test_get_customer_segments(self, mock_connection, mock_cursor):
        """get_customer_segmentsが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[{"customer_id": 1, "total_rentals": 50, "total_spending": "200.00"}]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_customer_segments", {})
            # セグメント分析結果が返される
            assert len(result) == 1

    async def test_get_inventory_turnover(self, mock_connection, mock_cursor):
        """get_inventory_turnoverが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "title": "High Turnover Film",
                    "category": "Action",
                    "inventory_count": 5,
                    "rental_count": 50,
                    "turnover_rate": 10.00,
                }
            ]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_inventory_turnover", {})
            assert "High Turnover Film" in result[0].text

    async def test_get_underperforming_films(self, mock_connection, mock_cursor):
        """get_underperforming_filmsが正しく動作することを確認。"""
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "title": "Underperforming Film",
                    "category": "Drama",
                    "rental_rate": 2.99,
                    "last_rental_date": "2024-01-01",
                    "days_since_last_rental": 45,
                    "inventory_count": 3,
                }
            ]
        )

        with patch("sakila_mcp.server.get_connection") as mock_get_conn:
            mock_get_conn.return_value = AsyncMock(
                __aenter__=AsyncMock(return_value=mock_connection),
                __aexit__=AsyncMock(return_value=None),
            )

            result = await call_tool("get_underperforming_films", {"days_not_rented": 30})
            assert "Underperforming Film" in result[0].text


class TestValidConstants:
    """定数の検証テスト。"""

    def test_valid_ratings(self):
        """VALID_RATINGSに期待される値が含まれることを確認。"""
        expected = {"G", "PG", "PG-13", "R", "NC-17"}
        assert VALID_RATINGS == expected

    def test_valid_stores(self):
        """VALID_STORESに期待される値が含まれることを確認。"""
        expected = {1, 2}
        assert VALID_STORES == expected

    def test_valid_rental_status(self):
        """VALID_RENTAL_STATUSに期待される値が含まれることを確認。"""
        expected = {"all", "active", "returned"}
        assert VALID_RENTAL_STATUS == expected

    def test_valid_group_by(self):
        """VALID_GROUP_BYに期待される値が含まれることを確認。"""
        expected = {"store", "category", "month", "staff"}
        assert VALID_GROUP_BY == expected

    def test_valid_period(self):
        """VALID_PERIODに期待される値が含まれることを確認。"""
        expected = {"all_time", "last_month", "last_week"}
        assert VALID_PERIOD == expected

    def test_valid_metrics(self):
        """VALID_METRICSに期待される値が含まれることを確認。"""
        expected = {"rentals", "spending"}
        assert VALID_METRICS == expected


@pytest.mark.integration
class TestIntegration:
    """統合テスト（実際のデータベース接続が必要）。"""

    async def test_search_films_with_real_db(self):
        """実際のDBでsearch_filmsが動作することを確認。"""
        result = await call_tool("search_films", {"limit": 5})
        import json

        data = json.loads(result[0].text)
        assert len(data) <= 5

    async def test_list_categories_with_real_db(self):
        """実際のDBでlist_categoriesが動作することを確認。"""
        result = await call_tool("list_categories", {})
        assert "Action" in result[0].text or "Comedy" in result[0].text

    async def test_get_store_stats_with_real_db(self):
        """実際のDBでget_store_statsが動作することを確認。"""
        result = await call_tool("get_store_stats", {"store_id": 1})
        assert "store_id" in result[0].text or "total" in result[0].text

    async def test_get_popular_films_with_real_db(self):
        """実際のDBでget_popular_filmsが動作することを確認。"""
        result = await call_tool("get_popular_films", {"limit": 5})
        import json

        data = json.loads(result[0].text)
        assert isinstance(data, list)

    async def test_get_customer_segments_with_real_db(self):
        """実際のDBでget_customer_segmentsが動作することを確認。"""
        result = await call_tool("get_customer_segments", {})
        # セグメント分析の結果が返される
        assert "high_value" in result[0].text or "segment" in result[0].text.lower()
