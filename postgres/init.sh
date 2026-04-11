#!/bin/bash
set -euo pipefail

# ARTOO_DB_PASSWORD viene del entorno del contenedor (docker-compose.yml)
DB_PASSWORD="${ARTOO_DB_PASSWORD:?ARTOO_DB_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
    CREATE ROLE artoo_demo LOGIN PASSWORD '${DB_PASSWORD}';
    CREATE DATABASE hotel_demo OWNER artoo_demo;
    CREATE DATABASE superset   OWNER artoo_demo;
SQL

psql -v ON_ERROR_STOP=1 --username artoo_demo --dbname hotel_demo <<-SQL
    CREATE TABLE IF NOT EXISTS cust (
        cust_id      SERIAL PRIMARY KEY,
        cust_fname   VARCHAR(50)  NOT NULL,
        cust_lname   VARCHAR(50)  NOT NULL,
        cust_email   VARCHAR(100),
        cust_phone   VARCHAR(20),
        cust_dob     DATE,
        cust_nat     VARCHAR(3),
        cust_tier    VARCHAR(10),
        cust_created TIMESTAMP DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS prop (
        prop_id      SERIAL PRIMARY KEY,
        prop_name    VARCHAR(100) NOT NULL,
        prop_city    VARCHAR(50),
        prop_country VARCHAR(3),
        prop_stars   INT,
        prop_rooms   INT,
        prop_type    VARCHAR(20)
    );

    CREATE TABLE IF NOT EXISTS rm_cat (
        cat_id        SERIAL PRIMARY KEY,
        cat_code      VARCHAR(5),
        cat_name      VARCHAR(50),
        cat_base_rate DECIMAL(10,2),
        cat_max_occ   INT
    );

    CREATE TABLE IF NOT EXISTS bkng (
        bk_id      SERIAL PRIMARY KEY,
        cust_id    INT REFERENCES cust(cust_id),
        prop_id    INT REFERENCES prop(prop_id),
        cat_id     INT REFERENCES rm_cat(cat_id),
        dt_chkin   DATE NOT NULL,
        dt_chkout  DATE NOT NULL,
        n_guests   INT,
        tot_amt    DECIMAL(10,2),
        pay_meth   VARCHAR(10),
        bk_status  VARCHAR(10),
        bk_channel VARCHAR(10),
        bk_created TIMESTAMP DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS gx (
        gx_id        SERIAL PRIMARY KEY,
        bk_id        INT REFERENCES bkng(bk_id),
        nps_score    INT,
        ov_rating    INT,
        clean_rating INT,
        svc_rating   INT,
        fb_text      TEXT,
        gx_date      DATE
    );

    CREATE TABLE IF NOT EXISTS rev_daily (
        rev_id          SERIAL PRIMARY KEY,
        prop_id         INT REFERENCES prop(prop_id),
        rev_date        DATE,
        occ_pct         DECIMAL(5,2),
        adr             DECIMAL(10,2),
        revpar          DECIMAL(10,2),
        n_checkins      INT,
        n_checkouts     INT,
        n_cancellations INT
    );
SQL
