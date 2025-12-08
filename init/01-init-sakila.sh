#!/bin/bash
# Sakila データベースの初期化スクリプト
# MySQL 公式の Sakila サンプルデータベースをダウンロードしてインポート

set -e

echo "Downloading Sakila database..."

# Sakila スキーマとデータをダウンロード
curl -fsSL https://downloads.mysql.com/docs/sakila-db.tar.gz -o /tmp/sakila-db.tar.gz
tar -xzf /tmp/sakila-db.tar.gz -C /tmp

echo "Importing Sakila schema..."
mysql -u root -p"$MYSQL_ROOT_PASSWORD" sakila < /tmp/sakila-db/sakila-schema.sql

echo "Importing Sakila data..."
mysql -u root -p"$MYSQL_ROOT_PASSWORD" sakila < /tmp/sakila-db/sakila-data.sql

echo "Granting privileges to sakila_user..."
mysql -u root -p"$MYSQL_ROOT_PASSWORD" -e "GRANT ALL PRIVILEGES ON sakila.* TO 'sakila_user'@'%'; FLUSH PRIVILEGES;"

echo "Sakila database initialized successfully!"

# クリーンアップ
rm -rf /tmp/sakila-db /tmp/sakila-db.tar.gz
