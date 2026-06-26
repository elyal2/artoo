#!/usr/bin/env bash
set -euo pipefail

DB_PASSWORD="${ARTOO_DB_PASSWORD:?ARTOO_DB_PASSWORD is required}"

# Create OpenMetadata database and user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
    CREATE USER openmetadata_user WITH ENCRYPTED PASSWORD 'openmetadata_password';
    CREATE DATABASE openmetadata_db OWNER openmetadata_user;
    GRANT ALL PRIVILEGES ON DATABASE openmetadata_db TO openmetadata_user;
SQL

# Create ARTOO demo database and user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
    CREATE ROLE artoo_demo LOGIN PASSWORD '${DB_PASSWORD}';
    CREATE DATABASE artoo_demo OWNER artoo_demo;
    CREATE DATABASE superset   OWNER artoo_demo;
SQL

psql -v ON_ERROR_STOP=1 --username artoo_demo --dbname artoo_demo <<-SQL
    -- Tabla de turismo: visitantes, gasto turístico, país de origen
    CREATE TABLE IF NOT EXISTS turismo (
        anio_referencia      INT NOT NULL,
        trimestre            INT NOT NULL,
        pais_origen          VARCHAR(100),
        numero_visitantes    INT,
        gasto_medio_eur      DECIMAL(10,2),
        PRIMARY KEY (anio_referencia, trimestre, pais_origen)
    );

    -- Tabla de indicadores económicos: PIB, desempleo, visitantes totales, balanza comercial
    CREATE TABLE IF NOT EXISTS indicadores_economicos (
        anio                       INT PRIMARY KEY,
        pib_millones_eur           DECIMAL(15,2),
        paro_tasa_pct              DECIMAL(5,2),
        visitantes_totales_mill    DECIMAL(10,2),
        balanza_comercial_meur     DECIMAL(15,2)
    );

    -- Tabla de tributos: impuestos recaudados por tipo
    CREATE TABLE IF NOT EXISTS tributos (
        anio            INT NOT NULL,
        tipo_impuesto   VARCHAR(100) NOT NULL,
        recaudacion_eur DECIMAL(15,2),
        PRIMARY KEY (anio, tipo_impuesto)
    );

    -- Tabla de presupuesto: ingresos y gastos del gobierno por categoría
    CREATE TABLE IF NOT EXISTS presupuesto (
        anio           INT NOT NULL,
        tipo           VARCHAR(20) NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
        categoria      VARCHAR(200) NOT NULL,
        subcategoria   VARCHAR(200),
        importe_eur    DECIMAL(15,2),
        PRIMARY KEY (anio, tipo, categoria, subcategoria)
    );
SQL
