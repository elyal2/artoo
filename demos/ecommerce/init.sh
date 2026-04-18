#!/usr/bin/env bash
set -euo pipefail

DB_PASSWORD="${ARTOO_DB_PASSWORD:?ARTOO_DB_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
    CREATE ROLE artoo_demo LOGIN PASSWORD '${DB_PASSWORD}';
    CREATE DATABASE artoo_demo OWNER artoo_demo;
    CREATE DATABASE superset   OWNER artoo_demo;
SQL

psql -v ON_ERROR_STOP=1 --username artoo_demo --dbname artoo_demo <<-SQL
    CREATE TABLE IF NOT EXISTS customers (
        customer_id   SERIAL PRIMARY KEY,
        first_name    VARCHAR(50)  NOT NULL,
        last_name     VARCHAR(50)  NOT NULL,
        email         VARCHAR(100),
        phone         VARCHAR(20),
        date_of_birth DATE,
        country       VARCHAR(3),
        segment       VARCHAR(10),
        created_at    TIMESTAMP DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS products (
        product_id    SERIAL PRIMARY KEY,
        sku           VARCHAR(20)  NOT NULL UNIQUE,
        name          VARCHAR(150) NOT NULL,
        category      VARCHAR(50),
        subcategory   VARCHAR(50),
        brand         VARCHAR(50),
        unit_price    DECIMAL(10,2),
        cost_price    DECIMAL(10,2),
        stock_qty     INT,
        is_active     BOOLEAN DEFAULT true
    );

    CREATE TABLE IF NOT EXISTS orders (
        order_id      SERIAL PRIMARY KEY,
        customer_id   INT REFERENCES customers(customer_id),
        order_date    TIMESTAMP NOT NULL DEFAULT now(),
        status        VARCHAR(15),
        channel       VARCHAR(15),
        payment_method VARCHAR(15),
        shipping_cost DECIMAL(8,2),
        total_amount  DECIMAL(10,2),
        discount_pct  DECIMAL(5,2) DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS order_items (
        item_id       SERIAL PRIMARY KEY,
        order_id      INT REFERENCES orders(order_id),
        product_id    INT REFERENCES products(product_id),
        quantity      INT NOT NULL,
        unit_price    DECIMAL(10,2) NOT NULL,
        line_total    DECIMAL(10,2) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS reviews (
        review_id     SERIAL PRIMARY KEY,
        order_id      INT REFERENCES orders(order_id),
        product_id    INT REFERENCES products(product_id),
        rating        INT,
        title         VARCHAR(200),
        body          TEXT,
        review_date   DATE
    );

    CREATE TABLE IF NOT EXISTS daily_sales (
        sales_id      SERIAL PRIMARY KEY,
        sale_date     DATE NOT NULL,
        product_id    INT REFERENCES products(product_id),
        units_sold    INT,
        revenue       DECIMAL(10,2),
        returns       INT DEFAULT 0,
        net_revenue   DECIMAL(10,2)
    );
SQL
