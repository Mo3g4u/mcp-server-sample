"""Pytest fixtures for Sakila MCP Server tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def set_test_env(monkeypatch):
    """テスト用の環境変数を設定する。"""
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_DATABASE", "sakila")
    monkeypatch.setenv("MYSQL_USER", "test_user")
    monkeypatch.setenv("MYSQL_PASSWORD", "test_pass")


@pytest.fixture
def mock_cursor():
    """モックカーソルを作成する。"""
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=[])
    return cursor


@pytest.fixture
def mock_connection(mock_cursor):
    """モック接続を作成する。"""
    conn = AsyncMock()
    conn.cursor = MagicMock(
        return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_cursor), __aexit__=AsyncMock())
    )
    conn.close = MagicMock()
    return conn


class AsyncContextManagerMock:
    """非同期コンテキストマネージャーのモック。"""

    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None
