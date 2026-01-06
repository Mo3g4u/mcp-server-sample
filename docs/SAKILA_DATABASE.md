# Sakila データベース概要

MySQLが公式に提供するサンプルデータベースで、架空のDVDレンタルショップのビジネスデータをモデル化しています。

## 基本情報

| 項目 | 内容 |
|------|------|
| 提供元 | MySQL / Oracle |
| 用途 | 学習・デモ・テスト |
| テーブル数 | 16 |
| ビュー数 | 7 |
| データ量 | 約1,000本の映画、600人の顧客、16,000件のレンタル記録 |

## ビジネスモデル

```
┌─────────────┐    レンタル    ┌─────────────┐
│  顧客       │ ───────────► │  映画       │
│  (customer) │              │  (film)     │
└─────────────┘              └─────────────┘
       │                           │
       │ 支払い                    │ 出演
       ▼                           ▼
┌─────────────┐              ┌─────────────┐
│  支払い     │              │  俳優       │
│  (payment)  │              │  (actor)    │
└─────────────┘              └─────────────┘
```

## 主要テーブル

### コアテーブル

| テーブル | 説明 | 件数目安 |
|---------|------|---------|
| `film` | 映画情報（タイトル、説明、レーティング等） | 1,000件 |
| `actor` | 俳優情報（名前） | 200件 |
| `customer` | 顧客情報（名前、メール、住所） | 600件 |
| `rental` | レンタル記録（いつ誰が何を借りたか） | 16,000件 |
| `payment` | 支払い記録（金額、日時） | 16,000件 |

### 在庫・店舗管理

| テーブル | 説明 | 件数目安 |
|---------|------|---------|
| `inventory` | 在庫（どの店舗にどの映画があるか） | 4,500件 |
| `store` | 店舗情報 | 2件 |
| `staff` | スタッフ情報 | 2件 |

### マスタ・分類

| テーブル | 説明 | 件数目安 |
|---------|------|---------|
| `category` | 映画カテゴリ（Action, Comedy等） | 16件 |
| `language` | 言語 | 6件 |

### 住所関連

| テーブル | 説明 | 件数目安 |
|---------|------|---------|
| `address` | 住所 | 600件 |
| `city` | 都市 | 600件 |
| `country` | 国 | 109件 |

### 関連テーブル（多対多）

| テーブル | 説明 |
|---------|------|
| `film_actor` | 映画と俳優の関連 |
| `film_category` | 映画とカテゴリの関連 |

## ER図（簡略版）

```
                                    ┌──────────┐
                                    │ language │
                                    └────┬─────┘
                                         │
┌───────┐     ┌────────────┐      ┌──────▼─────┐      ┌──────────┐
│ actor │────►│ film_actor │◄────►│    film    │◄────►│ category │
└───────┘     └────────────┘      └──────┬─────┘      └──────────┘
                                         │
                                         │
                                  ┌──────▼─────┐
                                  │ inventory  │
                                  └──────┬─────┘
                                         │
┌──────────┐     ┌─────────┐      ┌──────▼─────┐      ┌─────────┐
│ customer │────►│ rental  │◄─────┤            │◄─────│  staff  │
└────┬─────┘     └────┬────┘      │   store    │      └────┬────┘
     │                │           └────────────┘           │
     │                │                                    │
     │           ┌────▼────┐                               │
     └──────────►│ payment │◄──────────────────────────────┘
                 └─────────┘

┌─────────┐      ┌────────┐      ┌─────────┐
│ address │◄─────│  city  │◄─────│ country │
└─────────┘      └────────┘      └─────────┘
```

## カテゴリ一覧

| カテゴリ | 説明 |
|---------|------|
| Action | アクション |
| Animation | アニメーション |
| Children | 子供向け |
| Classics | クラシック |
| Comedy | コメディ |
| Documentary | ドキュメンタリー |
| Drama | ドラマ |
| Family | ファミリー |
| Foreign | 外国映画 |
| Games | ゲーム |
| Horror | ホラー |
| Music | 音楽 |
| New | 新作 |
| Sci-Fi | SF |
| Sports | スポーツ |
| Travel | 旅行 |

## レーティング

| レーティング | 説明 |
|-------------|------|
| G | 全年齢対象 |
| PG | 保護者の指導推奨 |
| PG-13 | 13歳未満は保護者の指導推奨 |
| R | 17歳未満は保護者同伴 |
| NC-17 | 17歳以下禁止 |

## 組み込みビュー

| ビュー名 | 説明 |
|---------|------|
| `actor_info` | 俳優の出演映画カテゴリ一覧 |
| `customer_list` | 顧客情報と住所の結合 |
| `film_list` | 映画情報とカテゴリ、俳優の結合 |
| `nicer_but_slower_film_list` | 整形済み映画リスト |
| `sales_by_film_category` | カテゴリ別売上 |
| `sales_by_store` | 店舗別売上 |
| `staff_list` | スタッフ情報と住所の結合 |

## 学習に適している理由

1. **現実的なリレーション**
   - 多対多（映画と俳優、映画とカテゴリ）
   - 1対多（顧客とレンタル、店舗と在庫）
   - 自己参照なし（シンプル）

2. **適度なデータ量**
   - 実用的なクエリ練習に十分
   - 軽量で環境構築が容易

3. **多様なデータ型**
   - 日付型（DATE, DATETIME, TIMESTAMP）
   - ENUM（rating）
   - SET（special_features）
   - BLOB（staff.picture）
   - DECIMAL（金額）

4. **高度な機能の学習**
   - ビュー
   - ストアドプロシージャ
   - トリガー

## よく使うクエリ例

### 人気映画ランキング

```sql
SELECT f.title, COUNT(r.rental_id) as rental_count
FROM film f
JOIN inventory i ON f.film_id = i.film_id
JOIN rental r ON i.inventory_id = r.inventory_id
GROUP BY f.film_id
ORDER BY rental_count DESC
LIMIT 10;
```

### カテゴリ別映画数

```sql
SELECT c.name, COUNT(fc.film_id) as film_count
FROM category c
JOIN film_category fc ON c.category_id = fc.category_id
GROUP BY c.category_id
ORDER BY film_count DESC;
```

### 俳優の出演映画数

```sql
SELECT a.first_name, a.last_name, COUNT(fa.film_id) as film_count
FROM actor a
JOIN film_actor fa ON a.actor_id = fa.actor_id
GROUP BY a.actor_id
ORDER BY film_count DESC
LIMIT 10;
```

### 月別売上

```sql
SELECT
    DATE_FORMAT(payment_date, '%Y-%m') as month,
    SUM(amount) as total_sales
FROM payment
GROUP BY month
ORDER BY month;
```

### 特定映画の出演俳優

```sql
SELECT a.first_name, a.last_name
FROM actor a
JOIN film_actor fa ON a.actor_id = fa.actor_id
JOIN film f ON fa.film_id = f.film_id
WHERE f.title = 'ACADEMY DINOSAUR';
```

## 参考資料

- [Sakila Sample Database - MySQL公式](https://dev.mysql.com/doc/sakila/en/)
- [Sakila Structure（ER図）](https://dev.mysql.com/doc/sakila/en/sakila-structure.html)
- [Sakila Installation](https://dev.mysql.com/doc/sakila/en/sakila-installation.html)
