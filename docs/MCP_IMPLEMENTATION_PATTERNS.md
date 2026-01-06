# MCP サーバー実装パターンガイド

MCPサーバーの実装パターンと、用途に応じた設計指針をまとめたドキュメント。

## 目次

1. [スキーマ開示レベルによる分類](#1-スキーマ開示レベルによる分類)
2. [パターン詳細](#2-パターン詳細)
3. [用途別推奨パターン](#3-用途別推奨パターン)
4. [有料サービス向け設計](#4-有料サービス向け設計)
5. [実装チェックリスト](#5-実装チェックリスト)

---

## 1. スキーマ開示レベルによる分類

| パターン | スキーマ開示 | LLMの役割 | 柔軟性 | セキュリティ | 実装コスト |
|----------|-------------|-----------|--------|-------------|-----------|
| **全開示型** | 全開示 | SQL生成 | 高 | 低 | 低 |
| **自然言語API型** | 非開示 | ツール選択のみ | 低 | 高 | 高 |
| **意図ベース型** | 非開示 | 意図パラメータ化 | 中 | 高 | 中 |
| **抽象化ビュー型** | 部分開示 | 限定SQL生成 | 中 | 中 | 中 |

---

## 2. パターン詳細

### 2.1 全開示型

**概要**: スキーマ情報をツール説明に埋め込み、LLMがSQLを生成する。

**アーキテクチャ**:
```
ユーザー「人気映画TOP5は？」
    ↓
LLM: スキーマ参照 → SQL生成
    ↓
MCPサーバー: SQL実行（SELECT * FROM film JOIN rental...）
    ↓
LLM: 結果を自然言語で回答
```

**実装例**:
```python
SCHEMA_INFO = """
## テーブル構造
- film: film_id, title, description, rating
- rental: rental_id, film_id, customer_id, rental_date
"""

Tool(
    name="query",
    description=f"SQLクエリを実行します。\n{SCHEMA_INFO}",
    inputSchema={
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"]
    }
)
```

**メリット**:
- 実装がシンプル
- 任意のクエリに対応可能
- 探索的なデータ分析に最適

**デメリット**:
- スキーマが完全に露出
- SQLインジェクションリスク（要対策）
- パフォーマンス予測が困難

**適用場面**: 社内ツール、学習目的、プロトタイプ

---

### 2.2 自然言語API型（本プロジェクトの実装）

**概要**: ビジネス機能をツールとして抽象化し、内部でSQLを生成。

**アーキテクチャ**:
```
ユーザー「人気映画TOP5は？」
    ↓
LLM: 適切なツールを選択（get_movie_ranking）
    ↓
MCPサーバー: 内部でSQL生成・実行
    ↓
LLM: 結果を自然言語で回答
```

**実装例**:
```python
Tool(
    name="get_movie_ranking",
    description="映画の人気ランキングを取得します",
    inputSchema={
        "properties": {
            "period": {
                "type": "string",
                "enum": ["daily", "weekly", "monthly", "all"],
                "description": "集計期間"
            },
            "category": {
                "type": "string",
                "description": "カテゴリで絞り込み（任意）"
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "maximum": 100
            }
        }
    }
)

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_movie_ranking":
        # 内部でSQL生成（ユーザーには見えない）
        sql = build_ranking_query(
            period=arguments.get("period", "all"),
            category=arguments.get("category"),
            limit=arguments.get("limit", 10)
        )
        return await execute_and_format(sql)
```

**メリット**:
- スキーマ完全非開示
- SQLインジェクション不可
- パフォーマンス最適化可能
- 課金設計が容易

**デメリット**:
- 想定外のクエリに対応不可
- 機能追加に開発が必要
- 柔軟性が低い

**適用場面**: 有料サービス、外部提供API、本番環境

---

### 2.3 意図ベース型

**概要**: ユーザーの分析意図をパラメータ化し、サーバー側で解釈。

**アーキテクチャ**:
```
ユーザー「カテゴリ別の売上比較」
    ↓
LLM: 意図をパラメータ化（analysis_type=comparison, target=sales, group_by=category）
    ↓
MCPサーバー: パラメータからSQL生成・実行
    ↓
LLM: 結果を自然言語で回答
```

**実装例**:
```python
Tool(
    name="analyze_data",
    description="データ分析を実行します",
    inputSchema={
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["ranking", "trend", "comparison", "distribution", "search"],
                "description": "分析タイプ"
            },
            "target": {
                "type": "string",
                "enum": ["movies", "customers", "sales", "rentals", "actors"],
                "description": "分析対象"
            },
            "group_by": {
                "type": "string",
                "enum": ["category", "store", "date", "rating"],
                "description": "グループ化の軸"
            },
            "period": {
                "type": "object",
                "properties": {
                    "from": {"type": "string", "format": "date"},
                    "to": {"type": "string", "format": "date"}
                }
            },
            "limit": {"type": "integer", "default": 10}
        },
        "required": ["analysis_type", "target"]
    }
)
```

**メリット**:
- スキーマ非開示
- 柔軟性とセキュリティのバランス
- 新しい分析パターンを追加しやすい

**デメリット**:
- パラメータ設計が複雑
- LLMのパラメータ解釈精度に依存

**適用場面**: BIツール、レポーティングサービス

---

### 2.4 抽象化ビュー型

**概要**: 内部スキーマを隠し、論理的なビュー名のみ公開。

**アーキテクチャ**:
```
ユーザー「売上サマリを見せて」
    ↓
LLM: ビュー選択 + 条件指定
    ↓
MCPサーバー: ビュー定義からSQL生成・実行
    ↓
LLM: 結果を自然言語で回答
```

**実装例**:
```python
# 論理ビュー定義（実テーブル名は隠蔽）
AVAILABLE_VIEWS = {
    "映画一覧": {
        "base_sql": "SELECT title, description, rating, release_year FROM film",
        "filterable": ["rating", "release_year"],
        "sortable": ["title", "release_year"]
    },
    "売上サマリ": {
        "base_sql": """
            SELECT DATE(payment_date) as date, SUM(amount) as total
            FROM payment
            GROUP BY DATE(payment_date)
        """,
        "filterable": ["date"],
        "sortable": ["date", "total"]
    },
    "顧客情報": {
        "base_sql": "SELECT first_name, last_name, email FROM customer",
        "filterable": ["last_name"],
        "sortable": ["last_name", "first_name"]
    }
}

Tool(
    name="query_view",
    description=f"利用可能なビュー: {list(AVAILABLE_VIEWS.keys())}",
    inputSchema={
        "properties": {
            "view_name": {
                "type": "string",
                "enum": list(AVAILABLE_VIEWS.keys())
            },
            "filters": {
                "type": "object",
                "description": "フィルタ条件"
            },
            "sort_by": {"type": "string"},
            "limit": {"type": "integer", "default": 100}
        },
        "required": ["view_name"]
    }
)
```

**メリット**:
- 実テーブル名・構造を隠蔽
- 許可された範囲で柔軟なクエリ
- 段階的な機能公開が可能

**デメリット**:
- ビュー定義の管理が必要
- JOIN等の複雑なクエリは制限

**適用場面**: データカタログ、セルフサービスBI

---

## 3. 用途別推奨パターン

| ユースケース | 推奨パターン | 理由 |
|-------------|-------------|------|
| 社内データ探索 | 全開示型 | 柔軟性重視、信頼できるユーザー |
| 学習・プロトタイプ | 全開示型 | 実装容易、機能理解 |
| 有料SaaS | 自然言語API型 | セキュリティ・課金・SLA |
| 外部パートナー連携 | 自然言語API型 | 知的財産保護 |
| BIダッシュボード | 意図ベース型 | 柔軟性とセキュリティのバランス |
| データカタログ | 抽象化ビュー型 | 段階的な情報公開 |

---

## 4. 有料サービス向け設計

### 4.1 システム構成

```
┌─────────────────┐                      ┌─────────────────┐
│  顧客のLLM      │     MCP Protocol     │  MCP Gateway    │
│  (Claude等)     │ ◄─────────────────► │  ├─ 認証        │
└─────────────────┘                      │  ├─ レート制限  │
                                         │  ├─ 監査ログ    │
                                         │  └─ 課金計測    │
                                         └────────┬────────┘
                                                  │
                                         ┌────────▼────────┐
                                         │  Business Logic │
                                         │  (SQL隠蔽)      │
                                         └────────┬────────┘
                                                  │
                                         ┌────────▼────────┐
                                         │  Database       │
                                         └─────────────────┘
```

### 4.2 必須コンポーネント

#### 認証・認可
```python
from functools import wraps

# プラン定義
PLANS = {
    "free": {
        "requests_per_day": 100,
        "allowed_tools": ["search_movies", "get_categories"],
        "max_results": 10
    },
    "basic": {
        "requests_per_day": 1000,
        "allowed_tools": ["search_movies", "get_categories", "get_ranking"],
        "max_results": 100
    },
    "pro": {
        "requests_per_day": 10000,
        "allowed_tools": "all",
        "max_results": 1000
    },
    "enterprise": {
        "requests_per_day": None,  # 無制限
        "allowed_tools": "all",
        "max_results": None
    }
}

async def authenticate(api_key: str) -> dict | None:
    """APIキーから顧客情報を取得"""
    customer = await db.customers.find_one({"api_key": api_key})
    if not customer or not customer.get("active"):
        return None
    return customer

async def check_rate_limit(customer_id: str, plan: str) -> bool:
    """レート制限をチェック"""
    limit = PLANS[plan]["requests_per_day"]
    if limit is None:
        return True

    today = datetime.utcnow().date()
    count = await db.usage.count_documents({
        "customer_id": customer_id,
        "date": today
    })
    return count < limit

def require_auth(allowed_tools: list[str] | None = None):
    """認証デコレータ"""
    def decorator(func):
        @wraps(func)
        async def wrapper(name: str, arguments: dict):
            # APIキー取得（実装はトランスポートに依存）
            api_key = get_api_key_from_context()

            customer = await authenticate(api_key)
            if not customer:
                return error_response("認証に失敗しました")

            plan = customer["plan"]
            plan_config = PLANS[plan]

            # ツール利用権限チェック
            if plan_config["allowed_tools"] != "all":
                if name not in plan_config["allowed_tools"]:
                    return error_response(f"このプランでは {name} を利用できません")

            # レート制限チェック
            if not await check_rate_limit(customer["_id"], plan):
                return error_response("本日のリクエスト上限に達しました")

            # 使用量記録
            await record_usage(customer["_id"], name)

            return await func(name, arguments)
        return wrapper
    return decorator
```

#### 監査ログ
```python
from datetime import datetime
import hashlib

async def record_audit_log(
    customer_id: str,
    tool_name: str,
    arguments: dict,
    result: str,
    latency_ms: float,
    success: bool
):
    """監査ログを記録"""
    # 機密情報のマスキング
    safe_arguments = mask_sensitive_data(arguments)

    await db.audit_logs.insert_one({
        "timestamp": datetime.utcnow(),
        "customer_id": customer_id,
        "tool": tool_name,
        "arguments": safe_arguments,
        "arguments_hash": hashlib.sha256(str(arguments).encode()).hexdigest(),
        "result_size": len(result),
        "latency_ms": latency_ms,
        "success": success,
        "ip_address": get_client_ip(),
        "user_agent": get_user_agent()
    })

def mask_sensitive_data(data: dict) -> dict:
    """機密データをマスク"""
    sensitive_keys = {"password", "secret", "token", "key", "email"}
    masked = {}
    for key, value in data.items():
        if any(s in key.lower() for s in sensitive_keys):
            masked[key] = "***MASKED***"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_data(value)
        else:
            masked[key] = value
    return masked
```

#### 課金計測
```python
# ツール別の課金単価（クレジット）
TOOL_COSTS = {
    "search_movies": 1,
    "get_categories": 1,
    "get_ranking": 2,
    "get_customer_analysis": 5,
    "generate_report": 10
}

async def record_usage(customer_id: str, tool_name: str):
    """使用量を記録"""
    cost = TOOL_COSTS.get(tool_name, 1)

    await db.usage.insert_one({
        "customer_id": customer_id,
        "tool": tool_name,
        "cost": cost,
        "timestamp": datetime.utcnow(),
        "date": datetime.utcnow().date()
    })

async def get_monthly_usage(customer_id: str, year: int, month: int) -> dict:
    """月間使用量を取得"""
    start = datetime(year, month, 1)
    end = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)

    pipeline = [
        {"$match": {
            "customer_id": customer_id,
            "timestamp": {"$gte": start, "$lt": end}
        }},
        {"$group": {
            "_id": "$tool",
            "count": {"$sum": 1},
            "total_cost": {"$sum": "$cost"}
        }}
    ]

    results = await db.usage.aggregate(pipeline).to_list(None)
    return {
        "period": f"{year}-{month:02d}",
        "breakdown": results,
        "total_cost": sum(r["total_cost"] for r in results)
    }
```

### 4.3 ツール設計例

```python
@server.list_tools()
async def list_tools():
    return [
        # 基本検索（Freeプラン以上）
        Tool(
            name="search_movies",
            description="映画を検索します",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "検索キーワード"
                    },
                    "rating": {
                        "type": "string",
                        "enum": ["G", "PG", "PG-13", "R", "NC-17"],
                        "description": "レーティングで絞り込み"
                    },
                    "category": {
                        "type": "string",
                        "description": "カテゴリで絞り込み"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "maximum": 100
                    }
                }
            }
        ),

        # カテゴリ一覧（Freeプラン以上）
        Tool(
            name="get_categories",
            description="映画カテゴリの一覧を取得します",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        # ランキング（Basicプラン以上）
        Tool(
            name="get_ranking",
            description="映画・俳優・顧客のランキングを取得します",
            inputSchema={
                "type": "object",
                "properties": {
                    "ranking_type": {
                        "type": "string",
                        "enum": ["popular_movies", "top_actors", "active_customers"],
                        "description": "ランキング種別"
                    },
                    "period": {
                        "type": "string",
                        "enum": ["week", "month", "year", "all"],
                        "default": "month"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "maximum": 50
                    }
                },
                "required": ["ranking_type"]
            }
        ),

        # 売上分析（Proプラン以上）
        Tool(
            name="get_sales_analysis",
            description="売上データを分析します",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_by": {
                        "type": "string",
                        "enum": ["day", "week", "month", "store", "category"],
                        "description": "集計軸"
                    },
                    "period": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "string", "format": "date"},
                            "to": {"type": "string", "format": "date"}
                        }
                    },
                    "compare_previous": {
                        "type": "boolean",
                        "default": False,
                        "description": "前期比較を含める"
                    }
                },
                "required": ["group_by"]
            }
        ),

        # レポート生成（Enterpriseプラン）
        Tool(
            name="generate_report",
            description="カスタムレポートを生成します",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "enum": ["executive_summary", "detailed_analysis", "trend_report"]
                    },
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["sales", "inventory", "customers", "trends"]
                        }
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown", "csv"],
                        "default": "json"
                    }
                },
                "required": ["report_type"]
            }
        )
    ]
```

### 4.4 料金プラン例

| プラン | 月額 | リクエスト/日 | 利用可能ツール | 最大結果数 |
|--------|------|--------------|---------------|-----------|
| Free | ¥0 | 100 | search_movies, get_categories | 10 |
| Basic | ¥5,000 | 1,000 | + get_ranking | 100 |
| Pro | ¥20,000 | 10,000 | + get_sales_analysis | 1,000 |
| Enterprise | 要相談 | 無制限 | 全ツール + カスタム | 無制限 |

---

## 5. 実装チェックリスト

### 全パターン共通

- [ ] エラーハンドリング（ユーザーフレンドリーなメッセージ）
- [ ] タイムアウト設定
- [ ] 接続プーリング
- [ ] ヘルスチェックエンドポイント
- [ ] ログ出力（構造化ログ推奨）

### セキュリティ

- [ ] 入力バリデーション
- [ ] SQLインジェクション対策
- [ ] レート制限
- [ ] 認証・認可（有料サービスの場合）
- [ ] 監査ログ（有料サービスの場合）
- [ ] 機密情報のマスキング

### 運用

- [ ] メトリクス収集（Prometheus等）
- [ ] アラート設定
- [ ] バックアップ・リストア手順
- [ ] スケーリング計画
- [ ] インシデント対応手順

### ドキュメント

- [ ] API仕様書
- [ ] 利用ガイド
- [ ] トラブルシューティング
- [ ] 変更履歴

---

## 参考資料

- [MCP 公式ドキュメント](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
