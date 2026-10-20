#!/usr/bin/env bash
set -euo pipefail

# ARTOO_DB_PASSWORD viene del entorno del contenedor (docker-compose.yml)
DB_PASSWORD="${ARTOO_DB_PASSWORD:?ARTOO_DB_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
    CREATE ROLE artoo_demo LOGIN PASSWORD '${DB_PASSWORD}';
    CREATE DATABASE artoo_demo OWNER artoo_demo;
    CREATE DATABASE superset   OWNER artoo_demo;
SQL

# Demo FNOL (First Notice of Loss) — seguros hogar y auto.
# Columnas abreviadas/codificadas a propósito: el valor del demo es que el catálogo las explique.
psql -v ON_ERROR_STOP=1 --username artoo_demo --dbname artoo_demo <<-SQL
    CREATE TABLE IF NOT EXISTS cust (
        cust_id    SERIAL PRIMARY KEY,
        fname      VARCHAR(50)  NOT NULL,
        lname      VARCHAR(80)  NOT NULL,
        email      VARCHAR(100),
        phone      VARCHAR(20),
        nif        VARCHAR(12),
        dob        DATE,
        city       VARCHAR(50),
        seg        VARCHAR(5),
        cust_since DATE
    );

    CREATE TABLE IF NOT EXISTS cvg (
        cvg_id    SERIAL PRIMARY KEY,
        cvg_code  VARCHAR(5)  NOT NULL UNIQUE,
        cvg_name  VARCHAR(80) NOT NULL,
        line      VARCHAR(5)  NOT NULL,
        lim_eur   DECIMAL(12,2),
        trade     VARCHAR(5)
    );

    CREATE TABLE IF NOT EXISTS pol (
        pol_id     SERIAL PRIMARY KEY,
        cust_id    INT NOT NULL REFERENCES cust(cust_id),
        pol_no     VARCHAR(20) NOT NULL UNIQUE,
        line       VARCHAR(5)  NOT NULL,
        pol_stat   VARCHAR(5)  NOT NULL,
        dt_start   DATE NOT NULL,
        dt_end     DATE,
        prem_eur   DECIMAL(10,2),
        ded_eur    DECIMAL(10,2)
    );

    CREATE TABLE IF NOT EXISTS pol_cvg (
        pol_id  INT NOT NULL REFERENCES pol(pol_id),
        cvg_id  INT NOT NULL REFERENCES cvg(cvg_id),
        lim_eur DECIMAL(12,2),
        ded_eur DECIMAL(10,2),
        PRIMARY KEY (pol_id, cvg_id)
    );

    CREATE TABLE IF NOT EXISTS ptnr (
        ptnr_id      SERIAL PRIMARY KEY,
        ptnr_name    VARCHAR(100) NOT NULL,
        trade        VARCHAR(5)   NOT NULL,
        city         VARCHAR(50),
        rating       DECIMAL(3,2),
        avg_resp_min INT,
        rate_eur_h   DECIMAL(8,2),
        is_active    BOOLEAN DEFAULT TRUE
    );

    CREATE TABLE IF NOT EXISTS clm (
        clm_id     SERIAL PRIMARY KEY,
        pol_id     INT NOT NULL REFERENCES pol(pol_id),
        cvg_id     INT REFERENCES cvg(cvg_id),
        reported_at TIMESTAMP NOT NULL,
        loss_dt    DATE NOT NULL,
        chnl       VARCHAR(5),
        loss_typ   VARCHAR(5),
        clm_stat   VARCHAR(5),
        sev        VARCHAR(5),
        est_amt_eur  DECIMAL(10,2),
        appr_amt_eur DECIMAL(10,2),
        fraud_score  INT,
        loss_desc  TEXT,
        rej_reason VARCHAR(20)
    );

    CREATE TABLE IF NOT EXISTS clm_dsp (
        dsp_id      SERIAL PRIMARY KEY,
        clm_id      INT NOT NULL REFERENCES clm(clm_id),
        ptnr_id     INT NOT NULL REFERENCES ptnr(ptnr_id),
        dt_dispatch TIMESTAMP,
        dt_arrival  TIMESTAMP,
        dt_done     TIMESTAMP,
        dsp_stat    VARCHAR(5),
        cost_eur    DECIMAL(10,2),
        cust_rating INT
    );

    CREATE TABLE IF NOT EXISTS clm_evt (
        evt_id   SERIAL PRIMARY KEY,
        clm_id   INT NOT NULL REFERENCES clm(clm_id),
        evt_stat VARCHAR(5) NOT NULL,
        evt_ts   TIMESTAMP NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_pol_cust_id ON pol(cust_id);
    CREATE INDEX IF NOT EXISTS idx_clm_pol_id ON clm(pol_id);
    CREATE INDEX IF NOT EXISTS idx_clm_cvg_id ON clm(cvg_id);
    CREATE INDEX IF NOT EXISTS idx_clm_stat ON clm(clm_stat);
    CREATE INDEX IF NOT EXISTS idx_clm_reported_at ON clm(reported_at);
    CREATE INDEX IF NOT EXISTS idx_clm_dsp_clm_id ON clm_dsp(clm_id);
    CREATE INDEX IF NOT EXISTS idx_clm_dsp_ptnr_id ON clm_dsp(ptnr_id);
    CREATE INDEX IF NOT EXISTS idx_clm_evt_clm_id ON clm_evt(clm_id);
SQL
