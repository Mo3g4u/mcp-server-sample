"""
Sakila MCP Server - 意図ベース型映画レンタル業務API

MCPプロトコルを通じてSakilaデータベースにアクセスするサーバー。
スキーマ情報を非公開にし、業務操作に特化したツールを提供する。
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any

import aiomysql
import mcp.server.stdio
import mcp.types as types
from dotenv import load_dotenv
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

load_dotenv()

# =============================================================================
# 入力検証用定数
# =============================================================================

VALID_RATINGS = {"G", "PG", "PG-13", "R", "NC-17"}
VALID_STORES = {1, 2}
VALID_RENTAL_STATUS = {"all", "active", "returned"}
VALID_GROUP_BY = {"store", "category", "month", "staff"}
VALID_PERIOD = {"all_time", "last_month", "last_week"}
VALID_METRICS = {"rentals", "spending"}

MAX_LIMIT = 50
DEFAULT_LIMIT = 10


# =============================================================================
# バリデーション関数
# =============================================================================


def validate_rating(rating: str | None) -> str | None:
    """レーティングを検証する。"""
    if rating is None:
        return None
    rating_upper = rating.upper()
    if rating_upper not in VALID_RATINGS:
        raise ValueError(f"無効なレーティング: {rating}。有効な値: {', '.join(sorted(VALID_RATINGS))}")
    return rating_upper


def validate_store_id(store_id: int | None) -> int | None:
    """店舗IDを検証する。"""
    if store_id is None:
        return None
    if store_id not in VALID_STORES:
        raise ValueError(f"無効な店舗ID: {store_id}。有効な値: 1, 2")
    return store_id


def validate_limit(limit: int | None, max_limit: int = MAX_LIMIT) -> int:
    """件数制限を検証する。"""
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(max_limit, int(limit)))


def validate_rental_status(status: str | None) -> str:
    """レンタルステータスを検証する。"""
    if status is None:
        return "all"
    status_lower = status.lower()
    if status_lower not in VALID_RENTAL_STATUS:
        raise ValueError(f"無効なステータス: {status}。有効な値: all, active, returned")
    return status_lower


def validate_group_by(group_by: str | None) -> str:
    """集計単位を検証する。"""
    if group_by is None:
        return "store"
    group_by_lower = group_by.lower()
    if group_by_lower not in VALID_GROUP_BY:
        raise ValueError(f"無効な集計単位: {group_by}。有効な値: store, category, month, staff")
    return group_by_lower


def validate_period(period: str | None) -> str:
    """期間を検証する。"""
    if period is None:
        return "all_time"
    period_lower = period.lower()
    if period_lower not in VALID_PERIOD:
        raise ValueError(f"無効な期間: {period}。有効な値: all_time, last_month, last_week")
    return period_lower


def validate_metric(metric: str | None) -> str:
    """メトリクスを検証する。"""
    if metric is None:
        return "spending"
    metric_lower = metric.lower()
    if metric_lower not in VALID_METRICS:
        raise ValueError(f"無効なメトリクス: {metric}。有効な値: rentals, spending")
    return metric_lower


# =============================================================================
# DB接続
# =============================================================================


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


async def execute_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """
    パラメータ化クエリを実行する。

    Args:
        sql: 実行するSQL文（パラメータは%sで指定）
        params: SQLパラメータのタプル

    Returns:
        クエリ結果のリスト
    """
    async with get_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            results = await cursor.fetchall()
            return list(results)


# =============================================================================
# 映画検索・情報系ツール
# =============================================================================


async def search_films(
    title: str | None = None,
    category: str | None = None,
    rating: str | None = None,
    actor_name: str | None = None,
    release_year: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """映画を検索する。"""
    rating = validate_rating(rating)
    limit = validate_limit(limit)

    sql = """
        SELECT DISTINCT
            f.title,
            f.description,
            f.release_year,
            f.rating,
            c.name as category,
            f.rental_rate,
            f.length as length_minutes
        FROM film f
        LEFT JOIN film_category fc ON f.film_id = fc.film_id
        LEFT JOIN category c ON fc.category_id = c.category_id
        LEFT JOIN film_actor fa ON f.film_id = fa.film_id
        LEFT JOIN actor a ON fa.actor_id = a.actor_id
        WHERE 1=1
    """
    params: list[Any] = []

    if title:
        sql += " AND f.title LIKE %s"
        params.append(f"%{title}%")
    if category:
        sql += " AND c.name = %s"
        params.append(category)
    if rating:
        sql += " AND f.rating = %s"
        params.append(rating)
    if actor_name:
        sql += " AND CONCAT(a.first_name, ' ', a.last_name) LIKE %s"
        params.append(f"%{actor_name}%")
    if release_year:
        sql += " AND f.release_year = %s"
        params.append(release_year)

    sql += " ORDER BY f.title LIMIT %s"
    params.append(limit)

    return await execute_query(sql, tuple(params))


async def get_film_details(title: str) -> dict | None:
    """映画の詳細情報を取得する。"""
    if not title:
        raise ValueError("タイトルを指定してください")

    # 基本情報取得
    sql = """
        SELECT
            f.title,
            f.description,
            f.release_year,
            f.rating,
            f.rental_rate,
            f.rental_duration as rental_duration_days,
            f.length as length_minutes,
            f.replacement_cost,
            f.special_features
        FROM film f
        WHERE f.title LIKE %s
        LIMIT 1
    """
    results = await execute_query(sql, (f"%{title}%",))
    if not results:
        return None

    film = results[0]

    # カテゴリ取得
    cat_sql = """
        SELECT c.name
        FROM category c
        JOIN film_category fc ON c.category_id = fc.category_id
        JOIN film f ON fc.film_id = f.film_id
        WHERE f.title = %s
    """
    categories = await execute_query(cat_sql, (film["title"],))
    film["categories"] = [c["name"] for c in categories]

    # 俳優取得
    actor_sql = """
        SELECT CONCAT(a.first_name, ' ', a.last_name) as name
        FROM actor a
        JOIN film_actor fa ON a.actor_id = fa.actor_id
        JOIN film f ON fa.film_id = f.film_id
        WHERE f.title = %s
        ORDER BY a.last_name, a.first_name
    """
    actors = await execute_query(actor_sql, (film["title"],))
    film["actors"] = [a["name"] for a in actors]

    # 在庫状況取得
    inv_sql = """
        SELECT
            COUNT(i.inventory_id) as total_copies,
            COUNT(i.inventory_id) - COUNT(r.rental_id) as available_copies
        FROM inventory i
        JOIN film f ON i.film_id = f.film_id
        LEFT JOIN rental r ON i.inventory_id = r.inventory_id AND r.return_date IS NULL
        WHERE f.title = %s
    """
    inventory = await execute_query(inv_sql, (film["title"],))
    if inventory:
        film["total_copies"] = inventory[0]["total_copies"]
        film["available_copies"] = inventory[0]["available_copies"]

    return film


async def list_categories() -> list[str]:
    """映画カテゴリ一覧を取得する。"""
    sql = "SELECT name FROM category ORDER BY name"
    results = await execute_query(sql)
    return [r["name"] for r in results]


async def check_film_availability(title: str, store_id: int | None = None) -> dict | None:
    """映画の在庫状況を確認する。"""
    if not title:
        raise ValueError("タイトルを指定してください")

    store_id = validate_store_id(store_id)

    # まず映画タイトルを特定
    film_sql = "SELECT title FROM film WHERE title LIKE %s LIMIT 1"
    films = await execute_query(film_sql, (f"%{title}%",))
    if not films:
        return None

    exact_title = films[0]["title"]

    sql = """
        SELECT
            s.store_id,
            CONCAT('Store ', s.store_id) as store,
            COUNT(i.inventory_id) as total,
            COUNT(i.inventory_id) - COUNT(r.rental_id) as available
        FROM store s
        JOIN inventory i ON s.store_id = i.store_id
        JOIN film f ON i.film_id = f.film_id
        LEFT JOIN rental r ON i.inventory_id = r.inventory_id AND r.return_date IS NULL
        WHERE f.title = %s
    """
    params: list[Any] = [exact_title]

    if store_id:
        sql += " AND s.store_id = %s"
        params.append(store_id)

    sql += " GROUP BY s.store_id ORDER BY s.store_id"

    availability = await execute_query(sql, tuple(params))

    overall_available = sum(a["available"] for a in availability)
    overall_total = sum(a["total"] for a in availability)

    return {
        "title": exact_title,
        "availability": [{"store": a["store"], "available": a["available"], "total": a["total"]} for a in availability],
        "overall_available": overall_available,
        "overall_total": overall_total,
    }


async def get_actor_filmography(actor_name: str) -> dict | None:
    """俳優の出演作品一覧を取得する。"""
    if not actor_name:
        raise ValueError("俳優名を指定してください")

    # 俳優検索
    actor_sql = """
        SELECT actor_id, CONCAT(first_name, ' ', last_name) as name
        FROM actor
        WHERE CONCAT(first_name, ' ', last_name) LIKE %s
        LIMIT 1
    """
    actors = await execute_query(actor_sql, (f"%{actor_name}%",))
    if not actors:
        return None

    actor = actors[0]

    # 出演作品取得
    films_sql = """
        SELECT f.title, f.release_year, c.name as category
        FROM film f
        JOIN film_actor fa ON f.film_id = fa.film_id
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        WHERE fa.actor_id = %s
        ORDER BY f.release_year DESC, f.title
    """
    films = await execute_query(films_sql, (actor["actor_id"],))

    return {
        "actor_name": actor["name"],
        "films": [{"title": f["title"], "release_year": f["release_year"], "category": f["category"]} for f in films],
        "total_films": len(films),
    }


# =============================================================================
# 顧客管理系ツール
# =============================================================================


async def search_customers(
    name: str | None = None,
    email: str | None = None,
    store_id: int | None = None,
    active_only: bool = True,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """顧客を検索する。"""
    store_id = validate_store_id(store_id)
    limit = validate_limit(limit)

    sql = """
        SELECT
            c.customer_id,
            CONCAT(c.first_name, ' ', c.last_name) as name,
            c.email,
            CONCAT('Store ', c.store_id) as store,
            c.active,
            DATE(c.create_date) as registration_date
        FROM customer c
        WHERE 1=1
    """
    params: list[Any] = []

    if name:
        sql += " AND CONCAT(c.first_name, ' ', c.last_name) LIKE %s"
        params.append(f"%{name}%")
    if email:
        sql += " AND c.email LIKE %s"
        params.append(f"%{email}%")
    if store_id:
        sql += " AND c.store_id = %s"
        params.append(store_id)
    if active_only:
        sql += " AND c.active = 1"

    sql += " ORDER BY c.last_name, c.first_name LIMIT %s"
    params.append(limit)

    return await execute_query(sql, tuple(params))


async def get_customer_details(customer_id: int | None = None, email: str | None = None) -> dict | None:
    """顧客の詳細情報を取得する。"""
    if not customer_id and not email:
        raise ValueError("customer_id または email を指定してください")

    sql = """
        SELECT
            c.customer_id,
            CONCAT(c.first_name, ' ', c.last_name) as name,
            c.email,
            CONCAT(a.address, ', ', ci.city, ', ', co.country) as address,
            a.phone,
            CONCAT('Store ', c.store_id) as store,
            c.active,
            DATE(c.create_date) as registration_date
        FROM customer c
        JOIN address a ON c.address_id = a.address_id
        JOIN city ci ON a.city_id = ci.city_id
        JOIN country co ON ci.country_id = co.country_id
        WHERE 1=1
    """
    params: list[Any] = []

    if customer_id:
        sql += " AND c.customer_id = %s"
        params.append(customer_id)
    elif email:
        sql += " AND c.email LIKE %s"
        params.append(f"%{email}%")

    sql += " LIMIT 1"

    results = await execute_query(sql, tuple(params))
    if not results:
        return None

    customer = results[0]

    # レンタル統計取得
    stats_sql = """
        SELECT
            COUNT(r.rental_id) as total_rentals,
            COALESCE(SUM(p.amount), 0) as total_spent,
            COUNT(CASE WHEN r.return_date IS NULL THEN 1 END) as outstanding_rentals
        FROM customer c
        LEFT JOIN rental r ON c.customer_id = r.customer_id
        LEFT JOIN payment p ON r.rental_id = p.rental_id
        WHERE c.customer_id = %s
    """
    stats = await execute_query(stats_sql, (customer["customer_id"],))
    if stats:
        customer["total_rentals"] = stats[0]["total_rentals"]
        customer["total_spent"] = float(stats[0]["total_spent"]) if stats[0]["total_spent"] else 0.0
        customer["outstanding_rentals"] = stats[0]["outstanding_rentals"]

    return customer


# =============================================================================
# レンタル業務系ツール
# =============================================================================


async def get_customer_rentals(
    customer_id: int,
    status: str = "all",
    limit: int = DEFAULT_LIMIT,
) -> dict | None:
    """顧客のレンタル履歴を取得する。"""
    status = validate_rental_status(status)
    limit = validate_limit(limit)

    # 顧客情報取得
    cust_sql = """
        SELECT customer_id, CONCAT(first_name, ' ', last_name) as name
        FROM customer WHERE customer_id = %s
    """
    customers = await execute_query(cust_sql, (customer_id,))
    if not customers:
        return None

    customer = customers[0]

    sql = """
        SELECT
            r.rental_id,
            f.title as film_title,
            r.rental_date,
            r.return_date,
            CASE WHEN r.return_date IS NULL THEN 'active' ELSE 'returned' END as status,
            CONCAT('Store ', i.store_id) as store
        FROM rental r
        JOIN inventory i ON r.inventory_id = i.inventory_id
        JOIN film f ON i.film_id = f.film_id
        WHERE r.customer_id = %s
    """
    params: list[Any] = [customer_id]

    if status == "active":
        sql += " AND r.return_date IS NULL"
    elif status == "returned":
        sql += " AND r.return_date IS NOT NULL"

    sql += " ORDER BY r.rental_date DESC LIMIT %s"
    params.append(limit)

    rentals = await execute_query(sql, tuple(params))

    # 総件数取得
    count_sql = "SELECT COUNT(*) as count FROM rental WHERE customer_id = %s"
    count_result = await execute_query(count_sql, (customer_id,))

    return {
        "customer_id": customer["customer_id"],
        "customer_name": customer["name"],
        "rentals": rentals,
        "total_count": count_result[0]["count"] if count_result else 0,
    }


async def get_overdue_rentals(
    store_id: int | None = None,
    days_overdue: int = 0,
    limit: int = 20,
) -> list[dict]:
    """延滞中のレンタル一覧を取得する。"""
    store_id = validate_store_id(store_id)
    limit = validate_limit(limit, max_limit=100)

    sql = """
        SELECT
            r.rental_id,
            CONCAT(c.first_name, ' ', c.last_name) as customer_name,
            c.email as customer_email,
            f.title as film_title,
            r.rental_date,
            DATEDIFF(CURDATE(), r.rental_date) - f.rental_duration as days_overdue,
            CONCAT('Store ', i.store_id) as store
        FROM rental r
        JOIN customer c ON r.customer_id = c.customer_id
        JOIN inventory i ON r.inventory_id = i.inventory_id
        JOIN film f ON i.film_id = f.film_id
        WHERE r.return_date IS NULL
        AND DATEDIFF(CURDATE(), r.rental_date) > f.rental_duration
    """
    params: list[Any] = []

    if store_id:
        sql += " AND i.store_id = %s"
        params.append(store_id)

    if days_overdue > 0:
        sql += " AND DATEDIFF(CURDATE(), r.rental_date) - f.rental_duration >= %s"
        params.append(days_overdue)

    sql += " ORDER BY days_overdue DESC LIMIT %s"
    params.append(limit)

    return await execute_query(sql, tuple(params))


# =============================================================================
# 基本分析系ツール
# =============================================================================


async def get_popular_films(
    period: str = "all_time",
    category: str | None = None,
    store_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """人気映画ランキングを取得する。"""
    period = validate_period(period)
    store_id = validate_store_id(store_id)
    limit = validate_limit(limit)

    sql = """
        SELECT
            f.title,
            c.name as category,
            COUNT(r.rental_id) as rental_count,
            COALESCE(SUM(p.amount), 0) as total_revenue
        FROM film f
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        JOIN inventory i ON f.film_id = i.film_id
        JOIN rental r ON i.inventory_id = r.inventory_id
        LEFT JOIN payment p ON r.rental_id = p.rental_id
        WHERE 1=1
    """
    params: list[Any] = []

    if period == "last_month":
        sql += " AND r.rental_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)"
    elif period == "last_week":
        sql += " AND r.rental_date >= DATE_SUB(CURDATE(), INTERVAL 1 WEEK)"

    if category:
        sql += " AND c.name = %s"
        params.append(category)

    if store_id:
        sql += " AND i.store_id = %s"
        params.append(store_id)

    sql += " GROUP BY f.film_id, f.title, c.name ORDER BY rental_count DESC LIMIT %s"
    params.append(limit)

    results = await execute_query(sql, tuple(params))

    return [
        {
            "rank": i + 1,
            "title": r["title"],
            "category": r["category"],
            "rental_count": r["rental_count"],
            "total_revenue": float(r["total_revenue"]) if r["total_revenue"] else 0.0,
        }
        for i, r in enumerate(results)
    ]


async def get_revenue_summary(group_by: str = "store", store_id: int | None = None) -> dict:
    """売上サマリーを取得する。"""
    group_by = validate_group_by(group_by)
    store_id = validate_store_id(store_id)

    if group_by == "store":
        sql = """
            SELECT
                CONCAT('Store ', s.store_id) as store,
                SUM(p.amount) as total_revenue,
                COUNT(DISTINCT r.rental_id) as rental_count
            FROM payment p
            JOIN rental r ON p.rental_id = r.rental_id
            JOIN inventory i ON r.inventory_id = i.inventory_id
            JOIN store s ON i.store_id = s.store_id
        """
        params: list[Any] = []
        if store_id:
            sql += " WHERE s.store_id = %s"
            params.append(store_id)
        sql += " GROUP BY s.store_id ORDER BY s.store_id"

    elif group_by == "category":
        sql = """
            SELECT
                c.name as category,
                SUM(p.amount) as total_revenue,
                COUNT(DISTINCT r.rental_id) as rental_count
            FROM payment p
            JOIN rental r ON p.rental_id = r.rental_id
            JOIN inventory i ON r.inventory_id = i.inventory_id
            JOIN film f ON i.film_id = f.film_id
            JOIN film_category fc ON f.film_id = fc.film_id
            JOIN category c ON fc.category_id = c.category_id
        """
        params = []
        if store_id:
            sql += " WHERE i.store_id = %s"
            params.append(store_id)
        sql += " GROUP BY c.category_id, c.name ORDER BY total_revenue DESC"

    elif group_by == "month":
        sql = """
            SELECT
                DATE_FORMAT(p.payment_date, '%Y-%m') as month,
                SUM(p.amount) as total_revenue,
                COUNT(DISTINCT r.rental_id) as rental_count
            FROM payment p
            JOIN rental r ON p.rental_id = r.rental_id
            JOIN inventory i ON r.inventory_id = i.inventory_id
        """
        params = []
        if store_id:
            sql += " WHERE i.store_id = %s"
            params.append(store_id)
        sql += " GROUP BY DATE_FORMAT(p.payment_date, '%Y-%m') ORDER BY month"

    else:  # staff
        sql = """
            SELECT
                CONCAT(st.first_name, ' ', st.last_name) as staff,
                SUM(p.amount) as total_revenue,
                COUNT(DISTINCT r.rental_id) as rental_count
            FROM payment p
            JOIN staff st ON p.staff_id = st.staff_id
            JOIN rental r ON p.rental_id = r.rental_id
            JOIN inventory i ON r.inventory_id = i.inventory_id
        """
        params = []
        if store_id:
            sql += " WHERE i.store_id = %s"
            params.append(store_id)
        sql += " GROUP BY st.staff_id ORDER BY total_revenue DESC"

    results = await execute_query(sql, tuple(params))

    summary = [
        {
            **{k: (float(v) if k == "total_revenue" else v) for k, v in r.items()},
        }
        for r in results
    ]

    grand_total = sum(r["total_revenue"] for r in summary)

    return {"summary": summary, "grand_total": grand_total}


async def get_store_stats(store_id: int | None = None) -> list[dict]:
    """店舗統計を取得する。"""
    store_id = validate_store_id(store_id)

    sql = """
        SELECT
            s.store_id,
            CONCAT(st.first_name, ' ', st.last_name) as manager,
            CONCAT(a.address, ', ', ci.city, ', ', co.country) as address,
            (SELECT COUNT(*) FROM customer c WHERE c.store_id = s.store_id) as total_customers,
            (SELECT COUNT(*) FROM customer c WHERE c.store_id = s.store_id AND c.active = 1) as active_customers,
            (SELECT COUNT(*) FROM inventory i WHERE i.store_id = s.store_id) as total_inventory,
            (SELECT COUNT(*) FROM rental r
             JOIN inventory i ON r.inventory_id = i.inventory_id
             WHERE i.store_id = s.store_id) as total_rentals,
            (SELECT COALESCE(SUM(p.amount), 0) FROM payment p
             JOIN staff st2 ON p.staff_id = st2.staff_id
             WHERE st2.store_id = s.store_id) as total_revenue
        FROM store s
        JOIN staff st ON s.manager_staff_id = st.staff_id
        JOIN address a ON s.address_id = a.address_id
        JOIN city ci ON a.city_id = ci.city_id
        JOIN country co ON ci.country_id = co.country_id
    """
    params: list[Any] = []

    if store_id:
        sql += " WHERE s.store_id = %s"
        params.append(store_id)

    sql += " ORDER BY s.store_id"

    results = await execute_query(sql, tuple(params))

    return [
        {
            "store_id": r["store_id"],
            "manager": r["manager"],
            "address": r["address"],
            "total_customers": r["total_customers"],
            "active_customers": r["active_customers"],
            "total_inventory": r["total_inventory"],
            "total_rentals": r["total_rentals"],
            "total_revenue": float(r["total_revenue"]) if r["total_revenue"] else 0.0,
        }
        for r in results
    ]


# =============================================================================
# 顧客分析系ツール
# =============================================================================


async def get_top_customers(
    metric: str = "spending",
    period: str = "all_time",
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """優良顧客ランキングを取得する。"""
    metric = validate_metric(metric)
    period = validate_period(period)
    limit = validate_limit(limit)

    if metric == "spending":
        order_by = "total_spent"
    else:
        order_by = "rental_count"

    sql = """
        SELECT
            c.customer_id,
            CONCAT(c.first_name, ' ', c.last_name) as name,
            c.email,
            CONCAT('Store ', c.store_id) as store,
            COUNT(DISTINCT r.rental_id) as rental_count,
            COALESCE(SUM(p.amount), 0) as total_spent
        FROM customer c
        LEFT JOIN rental r ON c.customer_id = r.customer_id
        LEFT JOIN payment p ON r.rental_id = p.rental_id
        WHERE 1=1
    """
    params: list[Any] = []

    if period == "last_month":
        sql += " AND r.rental_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)"
    elif period == "last_week":
        sql += " AND r.rental_date >= DATE_SUB(CURDATE(), INTERVAL 1 WEEK)"

    sql += f" GROUP BY c.customer_id ORDER BY {order_by} DESC LIMIT %s"
    params.append(limit)

    results = await execute_query(sql, tuple(params))

    return [
        {
            "rank": i + 1,
            "customer_id": r["customer_id"],
            "name": r["name"],
            "email": r["email"],
            "store": r["store"],
            "rental_count": r["rental_count"],
            "total_spent": float(r["total_spent"]) if r["total_spent"] else 0.0,
        }
        for i, r in enumerate(results)
    ]


async def get_customer_segments() -> dict:
    """顧客セグメント分析を行う。"""
    sql = """
        SELECT
            c.customer_id,
            COUNT(r.rental_id) as rental_count,
            COALESCE(SUM(p.amount), 0) as total_spent
        FROM customer c
        LEFT JOIN rental r ON c.customer_id = r.customer_id
        LEFT JOIN payment p ON r.rental_id = p.rental_id
        WHERE c.active = 1
        GROUP BY c.customer_id
    """
    results = await execute_query(sql)

    # セグメント分類
    segments = {
        "vip": {"count": 0, "criteria": "レンタル20回以上かつ支払い$100以上", "customers": []},
        "regular": {"count": 0, "criteria": "レンタル10-19回または支払い$50-99", "customers": []},
        "occasional": {"count": 0, "criteria": "レンタル1-9回", "customers": []},
        "inactive": {"count": 0, "criteria": "レンタル0回", "customers": []},
    }

    for r in results:
        rental_count = r["rental_count"] or 0
        total_spent = float(r["total_spent"]) if r["total_spent"] else 0.0

        if rental_count >= 20 and total_spent >= 100:
            segments["vip"]["count"] += 1
        elif rental_count >= 10 or total_spent >= 50:
            segments["regular"]["count"] += 1
        elif rental_count >= 1:
            segments["occasional"]["count"] += 1
        else:
            segments["inactive"]["count"] += 1

    total_customers = sum(s["count"] for s in segments.values())

    return {
        "segments": [
            {
                "segment": name,
                "count": data["count"],
                "percentage": round(data["count"] / total_customers * 100, 1) if total_customers > 0 else 0,
                "criteria": data["criteria"],
            }
            for name, data in segments.items()
        ],
        "total_customers": total_customers,
    }


async def get_customer_activity(period: str = "last_month") -> dict:
    """顧客アクティビティ分析を行う。"""
    period = validate_period(period)

    if period == "last_week":
        interval = "1 WEEK"
    elif period == "last_month":
        interval = "1 MONTH"
    else:
        interval = "1 YEAR"

    # アクティブ顧客（期間内にレンタルあり）
    active_sql = f"""
        SELECT COUNT(DISTINCT r.customer_id) as count
        FROM rental r
        WHERE r.rental_date >= DATE_SUB(CURDATE(), INTERVAL {interval})
    """
    active_result = await execute_query(active_sql)
    active_count = active_result[0]["count"] if active_result else 0

    # 新規顧客（期間内に登録）
    new_sql = f"""
        SELECT COUNT(*) as count
        FROM customer
        WHERE create_date >= DATE_SUB(CURDATE(), INTERVAL {interval})
    """
    new_result = await execute_query(new_sql)
    new_count = new_result[0]["count"] if new_result else 0

    # 休眠顧客（アクティブだが期間内にレンタルなし）
    dormant_sql = f"""
        SELECT COUNT(*) as count
        FROM customer c
        WHERE c.active = 1
        AND c.customer_id NOT IN (
            SELECT DISTINCT r.customer_id
            FROM rental r
            WHERE r.rental_date >= DATE_SUB(CURDATE(), INTERVAL {interval})
        )
    """
    dormant_result = await execute_query(dormant_sql)
    dormant_count = dormant_result[0]["count"] if dormant_result else 0

    # 総顧客数
    total_sql = "SELECT COUNT(*) as count FROM customer WHERE active = 1"
    total_result = await execute_query(total_sql)
    total_count = total_result[0]["count"] if total_result else 0

    def calc_pct(count: int) -> float:
        return round(count / total_count * 100, 1) if total_count > 0 else 0

    return {
        "period": period,
        "activity": {
            "active": {"count": active_count, "percentage": calc_pct(active_count)},
            "new": {"count": new_count, "percentage": calc_pct(new_count)},
            "dormant": {"count": dormant_count, "percentage": calc_pct(dormant_count)},
        },
        "total_active_customers": total_count,
    }


# =============================================================================
# 在庫・商品分析系ツール
# =============================================================================


async def get_inventory_turnover(store_id: int | None = None, category: str | None = None) -> list[dict]:
    """在庫回転率分析を行う。"""
    store_id = validate_store_id(store_id)

    sql = """
        SELECT
            f.title,
            c.name as category,
            COUNT(DISTINCT i.inventory_id) as inventory_count,
            COUNT(r.rental_id) as rental_count,
            ROUND(COUNT(r.rental_id) / COUNT(DISTINCT i.inventory_id), 2) as turnover_rate
        FROM film f
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        JOIN inventory i ON f.film_id = i.film_id
        LEFT JOIN rental r ON i.inventory_id = r.inventory_id
        WHERE 1=1
    """
    params: list[Any] = []

    if store_id:
        sql += " AND i.store_id = %s"
        params.append(store_id)

    if category:
        sql += " AND c.name = %s"
        params.append(category)

    sql += " GROUP BY f.film_id, f.title, c.name ORDER BY turnover_rate DESC LIMIT 50"

    results = await execute_query(sql, tuple(params))

    return [
        {
            "title": r["title"],
            "category": r["category"],
            "inventory_count": r["inventory_count"],
            "rental_count": r["rental_count"],
            "turnover_rate": float(r["turnover_rate"]) if r["turnover_rate"] else 0.0,
        }
        for r in results
    ]


async def get_category_performance(period: str = "all_time", store_id: int | None = None) -> list[dict]:
    """カテゴリ別パフォーマンス分析を行う。"""
    period = validate_period(period)
    store_id = validate_store_id(store_id)

    sql = """
        SELECT
            c.name as category,
            COUNT(DISTINCT f.film_id) as film_count,
            COUNT(r.rental_id) as rental_count,
            COALESCE(SUM(p.amount), 0) as total_revenue,
            ROUND(COUNT(r.rental_id) / COUNT(DISTINCT f.film_id), 2) as avg_rentals_per_film
        FROM category c
        JOIN film_category fc ON c.category_id = fc.category_id
        JOIN film f ON fc.film_id = f.film_id
        JOIN inventory i ON f.film_id = i.film_id
        LEFT JOIN rental r ON i.inventory_id = r.inventory_id
        LEFT JOIN payment p ON r.rental_id = p.rental_id
        WHERE 1=1
    """
    params: list[Any] = []

    if period == "last_month":
        sql += " AND (r.rental_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH) OR r.rental_date IS NULL)"
    elif period == "last_week":
        sql += " AND (r.rental_date >= DATE_SUB(CURDATE(), INTERVAL 1 WEEK) OR r.rental_date IS NULL)"

    if store_id:
        sql += " AND i.store_id = %s"
        params.append(store_id)

    sql += " GROUP BY c.category_id, c.name ORDER BY total_revenue DESC"

    results = await execute_query(sql, tuple(params))

    return [
        {
            "category": r["category"],
            "film_count": r["film_count"],
            "rental_count": r["rental_count"],
            "total_revenue": float(r["total_revenue"]) if r["total_revenue"] else 0.0,
            "avg_rentals_per_film": float(r["avg_rentals_per_film"]) if r["avg_rentals_per_film"] else 0.0,
        }
        for r in results
    ]


async def get_underperforming_films(days_not_rented: int = 30, store_id: int | None = None) -> list[dict]:
    """低稼働作品一覧を取得する。"""
    store_id = validate_store_id(store_id)
    days_not_rented = max(1, min(365, days_not_rented))

    sql = """
        SELECT
            f.title,
            c.name as category,
            f.rental_rate,
            MAX(r.rental_date) as last_rental_date,
            DATEDIFF(CURDATE(), MAX(r.rental_date)) as days_since_last_rental,
            COUNT(DISTINCT i.inventory_id) as inventory_count
        FROM film f
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        JOIN inventory i ON f.film_id = i.film_id
        LEFT JOIN rental r ON i.inventory_id = r.inventory_id
        WHERE 1=1
    """
    params: list[Any] = []

    if store_id:
        sql += " AND i.store_id = %s"
        params.append(store_id)

    sql += """
        GROUP BY f.film_id, f.title, c.name, f.rental_rate
        HAVING MAX(r.rental_date) IS NULL
           OR DATEDIFF(CURDATE(), MAX(r.rental_date)) >= %s
        ORDER BY days_since_last_rental DESC
        LIMIT 50
    """
    params.append(days_not_rented)

    results = await execute_query(sql, tuple(params))

    return [
        {
            "title": r["title"],
            "category": r["category"],
            "rental_rate": float(r["rental_rate"]) if r["rental_rate"] else 0.0,
            "last_rental_date": str(r["last_rental_date"]) if r["last_rental_date"] else "なし",
            "days_since_last_rental": r["days_since_last_rental"] if r["days_since_last_rental"] else "N/A",
            "inventory_count": r["inventory_count"],
        }
        for r in results
    ]


# =============================================================================
# MCPサーバー定義
# =============================================================================

server = Server("sakila-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """利用可能なツールの一覧を返す。"""
    return [
        # 映画検索・情報系
        types.Tool(
            name="search_films",
            description="映画を検索します。タイトル、カテゴリ、レーティング、俳優名などで絞り込みできます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "映画タイトル（部分一致）"},
                    "category": {"type": "string", "description": "カテゴリ名"},
                    "rating": {
                        "type": "string",
                        "enum": ["G", "PG", "PG-13", "R", "NC-17"],
                        "description": "レーティング",
                    },
                    "actor_name": {"type": "string", "description": "出演俳優名（部分一致）"},
                    "release_year": {"type": "integer", "description": "公開年"},
                    "limit": {"type": "integer", "description": "取得件数", "default": 10},
                },
            },
        ),
        types.Tool(
            name="get_film_details",
            description="映画の詳細情報（出演者、カテゴリ、在庫状況含む）を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "映画タイトル"},
                },
                "required": ["title"],
            },
        ),
        types.Tool(
            name="list_categories",
            description="利用可能な映画カテゴリの一覧を取得します。",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="check_film_availability",
            description="映画の在庫・貸出状況を確認します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "映画タイトル"},
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗ID（省略時は全店舗）"},
                },
                "required": ["title"],
            },
        ),
        types.Tool(
            name="get_actor_filmography",
            description="俳優の出演作品一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "actor_name": {"type": "string", "description": "俳優名（部分一致可）"},
                },
                "required": ["actor_name"],
            },
        ),
        # 顧客管理系
        types.Tool(
            name="search_customers",
            description="顧客を検索します。名前、メール、店舗で絞り込みできます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "顧客名（部分一致）"},
                    "email": {"type": "string", "description": "メールアドレス（部分一致）"},
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗ID"},
                    "active_only": {"type": "boolean", "description": "アクティブ顧客のみ", "default": True},
                    "limit": {"type": "integer", "description": "取得件数", "default": 10},
                },
            },
        ),
        types.Tool(
            name="get_customer_details",
            description="顧客の詳細情報（住所、レンタル統計含む）を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer", "description": "顧客ID"},
                    "email": {"type": "string", "description": "メールアドレス（customer_idがない場合）"},
                },
            },
        ),
        # レンタル業務系
        types.Tool(
            name="get_customer_rentals",
            description="顧客のレンタル履歴を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer", "description": "顧客ID"},
                    "status": {
                        "type": "string",
                        "enum": ["all", "active", "returned"],
                        "description": "レンタル状態",
                        "default": "all",
                    },
                    "limit": {"type": "integer", "description": "取得件数", "default": 10},
                },
                "required": ["customer_id"],
            },
        ),
        types.Tool(
            name="get_overdue_rentals",
            description="延滞中のレンタル一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗ID（省略時は全店舗）"},
                    "days_overdue": {"type": "integer", "description": "N日以上延滞（デフォルト: 0）", "default": 0},
                    "limit": {"type": "integer", "description": "取得件数（デフォルト20）", "default": 20},
                },
            },
        ),
        # 基本分析系
        types.Tool(
            name="get_popular_films",
            description="人気映画ランキングを取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["all_time", "last_month", "last_week"],
                        "description": "集計期間",
                        "default": "all_time",
                    },
                    "category": {"type": "string", "description": "カテゴリで絞り込み"},
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗ID"},
                    "limit": {"type": "integer", "description": "取得件数", "default": 10},
                },
            },
        ),
        types.Tool(
            name="get_revenue_summary",
            description="売上サマリーを取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_by": {
                        "type": "string",
                        "enum": ["store", "category", "month", "staff"],
                        "description": "集計単位",
                        "default": "store",
                    },
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗で絞り込み"},
                },
            },
        ),
        types.Tool(
            name="get_store_stats",
            description="店舗の統計情報を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗ID（省略時は全店舗）"},
                },
            },
        ),
        # 顧客分析系
        types.Tool(
            name="get_top_customers",
            description="優良顧客ランキングを取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "enum": ["rentals", "spending"],
                        "description": "ランキング基準",
                        "default": "spending",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["all_time", "last_month", "last_week"],
                        "description": "集計期間",
                        "default": "all_time",
                    },
                    "limit": {"type": "integer", "description": "取得件数", "default": 10},
                },
            },
        ),
        types.Tool(
            name="get_customer_segments",
            description="顧客セグメント分析を行います。利用頻度・金額で顧客を自動分類します。",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_customer_activity",
            description="顧客アクティビティ分析を行います。新規・アクティブ・休眠顧客の割合を確認できます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["all_time", "last_month", "last_week"],
                        "description": "分析期間",
                        "default": "last_month",
                    },
                },
            },
        ),
        # 在庫・商品分析系
        types.Tool(
            name="get_inventory_turnover",
            description="在庫回転率分析を行います。作品ごとの在庫効率を確認できます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗ID（省略時は全店舗）"},
                    "category": {"type": "string", "description": "カテゴリで絞り込み"},
                },
            },
        ),
        types.Tool(
            name="get_category_performance",
            description="カテゴリ別パフォーマンス分析を行います。",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["all_time", "last_month", "last_week"],
                        "description": "集計期間（デフォルト: all_time）",
                        "default": "all_time",
                    },
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗ID"},
                },
            },
        ),
        types.Tool(
            name="get_underperforming_films",
            description="低稼働作品一覧を取得します。長期間レンタルされていない作品を特定できます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "days_not_rented": {
                        "type": "integer",
                        "description": "N日以上レンタルなし（デフォルト: 30）",
                        "default": 30,
                    },
                    "store_id": {"type": "integer", "enum": [1, 2], "description": "店舗ID"},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """ツールを実行する。"""
    try:
        result: Any = None

        # 映画検索・情報系
        if name == "search_films":
            result = await search_films(
                title=arguments.get("title"),
                category=arguments.get("category"),
                rating=arguments.get("rating"),
                actor_name=arguments.get("actor_name"),
                release_year=arguments.get("release_year"),
                limit=arguments.get("limit", DEFAULT_LIMIT),
            )
        elif name == "get_film_details":
            result = await get_film_details(title=arguments.get("title", ""))
        elif name == "list_categories":
            result = await list_categories()
        elif name == "check_film_availability":
            result = await check_film_availability(
                title=arguments.get("title", ""),
                store_id=arguments.get("store_id"),
            )
        elif name == "get_actor_filmography":
            result = await get_actor_filmography(actor_name=arguments.get("actor_name", ""))

        # 顧客管理系
        elif name == "search_customers":
            result = await search_customers(
                name=arguments.get("name"),
                email=arguments.get("email"),
                store_id=arguments.get("store_id"),
                active_only=arguments.get("active_only", True),
                limit=arguments.get("limit", DEFAULT_LIMIT),
            )
        elif name == "get_customer_details":
            result = await get_customer_details(
                customer_id=arguments.get("customer_id"),
                email=arguments.get("email"),
            )

        # レンタル業務系
        elif name == "get_customer_rentals":
            result = await get_customer_rentals(
                customer_id=arguments.get("customer_id"),
                status=arguments.get("status", "all"),
                limit=arguments.get("limit", DEFAULT_LIMIT),
            )
        elif name == "get_overdue_rentals":
            result = await get_overdue_rentals(
                store_id=arguments.get("store_id"),
                days_overdue=arguments.get("days_overdue", 0),
                limit=arguments.get("limit", 20),
            )

        # 基本分析系
        elif name == "get_popular_films":
            result = await get_popular_films(
                period=arguments.get("period", "all_time"),
                category=arguments.get("category"),
                store_id=arguments.get("store_id"),
                limit=arguments.get("limit", DEFAULT_LIMIT),
            )
        elif name == "get_revenue_summary":
            result = await get_revenue_summary(
                group_by=arguments.get("group_by", "store"),
                store_id=arguments.get("store_id"),
            )
        elif name == "get_store_stats":
            result = await get_store_stats(store_id=arguments.get("store_id"))

        # 顧客分析系
        elif name == "get_top_customers":
            result = await get_top_customers(
                metric=arguments.get("metric", "spending"),
                period=arguments.get("period", "all_time"),
                limit=arguments.get("limit", DEFAULT_LIMIT),
            )
        elif name == "get_customer_segments":
            result = await get_customer_segments()
        elif name == "get_customer_activity":
            result = await get_customer_activity(period=arguments.get("period", "last_month"))

        # 在庫・商品分析系
        elif name == "get_inventory_turnover":
            result = await get_inventory_turnover(
                store_id=arguments.get("store_id"),
                category=arguments.get("category"),
            )
        elif name == "get_category_performance":
            result = await get_category_performance(
                period=arguments.get("period", "all_time"),
                store_id=arguments.get("store_id"),
            )
        elif name == "get_underperforming_films":
            result = await get_underperforming_films(
                days_not_rented=arguments.get("days_not_rented", 30),
                store_id=arguments.get("store_id"),
            )

        else:
            return [types.TextContent(type="text", text=f"エラー: 未知のツールです: {name}")]

        if result is None:
            return [types.TextContent(type="text", text="該当するデータが見つかりませんでした。")]

        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]

    except ValueError as e:
        return [types.TextContent(type="text", text=f"入力エラー: {e!s}")]
    except Exception:
        # 詳細なエラーメッセージは非公開
        return [types.TextContent(type="text", text="処理中にエラーが発生しました。入力内容を確認してください。")]


async def run():
    """MCPサーバーを起動する。"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="sakila-mcp",
                server_version="0.2.0",
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
