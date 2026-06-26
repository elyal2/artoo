from __future__ import annotations

import asyncio
import random
from datetime import date

import asyncpg

from artoo.config import settings


def _dsn() -> str:
    raw = settings.postgres_dsn
    return raw.replace("+psycopg2", "")


async def seed() -> None:
    conn = await asyncpg.connect(_dsn())

    # Truncate en orden inverso (sin FKs, pero por claridad)
    tables = ["presupuesto", "tributos", "indicadores_economicos", "turismo"]
    for tbl in tables:
        await conn.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")

    # ── TURISMO ──────────────────────────────────────────────────────────
    # Datos trimestrales 2019-2024, principales países de origen
    paises = [
        ("España", 0.35, 120),
        ("Francia", 0.28, 135),
        ("Reino Unido", 0.12, 150),
        ("Portugal", 0.08, 110),
        ("Alemania", 0.07, 140),
        ("Italia", 0.05, 125),
        ("Países Bajos", 0.03, 145),
        ("Bélgica", 0.02, 130),
    ]

    turismo_rows = []
    base_visitantes = {
        2019: 15_300_000,
        2020: 6_400_000,  # COVID: -58%
        2021: 12_200_000,
        2022: 14_200_000,
        2023: 14_900_000,
        2024: 15_600_000,
    }

    for anio in range(2019, 2025):
        total_anio = base_visitantes[anio]
        for trimestre in range(1, 5):
            # Distribución trimestral: Q1=18%, Q2=24%, Q3=33%, Q4=25%
            peso_trim = {1: 0.18, 2: 0.24, 3: 0.33, 4: 0.25}[trimestre]
            total_trim = int(total_anio * peso_trim)

            for pais, peso_pais, gasto_base in paises:
                visitantes = int(total_trim * peso_pais * random.uniform(0.92, 1.08))
                gasto_medio = round(gasto_base * random.uniform(0.95, 1.12), 2)
                turismo_rows.append((anio, trimestre, pais, visitantes, gasto_medio))

    await conn.executemany(
        "INSERT INTO turismo (anio_referencia, trimestre, pais_origen, numero_visitantes, gasto_medio_eur) VALUES ($1,$2,$3,$4,$5)",
        turismo_rows,
    )

    # ── INDICADORES ECONÓMICOS ───────────────────────────────────────────
    # PIB, paro, visitantes, balanza comercial
    indicadores = [
        (2019, 3078, 2.1, 15.3, -1420),
        (2020, 2491, 3.8, 6.4, -1150),  # COVID: PIB -19%, visitantes -58%
        (2021, 2836, 3.2, 12.2, -1280),
        (2022, 3202, 2.4, 14.2, -1390),
        (2023, 3352, 2.2, 14.9, -1445),
        (2024, 3499, 2.0, 15.6, -1490),
    ]

    await conn.executemany(
        "INSERT INTO indicadores_economicos (anio, pib_millones_eur, paro_tasa_pct, visitantes_totales_mill, balanza_comercial_meur) VALUES ($1,$2,$3,$4,$5)",
        indicadores,
    )

    # ── TRIBUTOS ─────────────────────────────────────────────────────────
    # Tipos: IGI (IVA andorrano), IS (sociedades), IRPF, ITP (transmisiones)
    tipos_tributo = ["IGI", "IS", "IRPF", "ITP"]
    tributos_rows = []

    # Recaudación base 2024: IGI 351M€, IS 175M€, IRPF 102M€, ITP 33M€
    # Total fiscal ~661M€
    recaudacion_base = {
        "IGI": 351_000_000,
        "IS": 175_000_000,
        "IRPF": 102_000_000,
        "ITP": 33_000_000,
    }

    for anio in range(2019, 2025):
        # Ajuste temporal: 2020 cae un 25%, luego recuperación gradual
        if anio == 2020:
            factor = 0.75
        elif anio == 2021:
            factor = 0.88
        elif anio == 2022:
            factor = 0.96
        elif anio == 2023:
            factor = 0.99
        else:
            factor = 1.0

        for tipo in tipos_tributo:
            base = recaudacion_base[tipo] * factor
            aprobado = base * random.uniform(0.98, 1.02)
            ejecutado = aprobado * random.uniform(0.92, 1.01)
            recaudado = ejecutado  # Para simplificar, recaudado = ejecutado

            tributos_rows.append(
                (
                    anio,
                    tipo,
                    round(recaudado, 2),
                )
            )

    await conn.executemany(
        "INSERT INTO tributos (anio, tipo_impuesto, recaudacion_eur) VALUES ($1,$2,$3)",
        tributos_rows,
    )

    # ── PRESUPUESTO ──────────────────────────────────────────────────────
    # Ingresos y gastos del gobierno por categoría
    presupuesto_rows = []
    
    categorias_ingreso = [
        "Impuestos directos",
        "Impuestos indirectos",
        "Tasas y cánones",
        "Transferencias corrientes",
        "Ingresos patrimoniales",
    ]
    
    categorias_gasto = [
        "Personal",
        "Inversión",
        "Servicios",
        "Transferencias",
        "Sanidad",
        "Educación",
        "Seguridad",
    ]
    
    for anio in range(2019, 2025):
        # Ingresos
        base_ingreso = 600_000_000 * (1 + (anio - 2019) * 0.02)
        if anio == 2020:
            base_ingreso *= 0.85  # COVID impact
        
        for categoria in categorias_ingreso:
            importe = base_ingreso * random.uniform(0.15, 0.25)
            presupuesto_rows.append((anio, "ingreso", categoria, "General", round(importe, 2)))
        
        # Gastos
        base_gasto = 550_000_000 * (1 + (anio - 2019) * 0.02)
        if anio == 2020:
            base_gasto *= 0.88
        
        for categoria in categorias_gasto:
            importe = base_gasto * random.uniform(0.10, 0.18)
            presupuesto_rows.append((anio, "gasto", categoria, "General", round(importe, 2)))

    await conn.executemany(
        "INSERT INTO presupuesto (anio, tipo, categoria, subcategoria, importe_eur) VALUES ($1,$2,$3,$4,$5)",
        presupuesto_rows,
    )

    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
