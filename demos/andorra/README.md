# Demo Andorra — Govern d'Andorra

Dataset de ejemplo basado en datos públicos del gobierno de Andorra (PIB, turismo, recaudación fiscal, presupuesto del Estado).

## Esquema

### `turismo`
Visitantes y gasto turístico por trimestre y país de origen (2019-2024).

| Columna | Tipo | Descripción |
|---|---|---|
| `anio_referencia` | INT | Año de referencia |
| `trimestre` | INT | Trimestre (1-4) |
| `pais_origen` | VARCHAR(100) | País de origen del visitante |
| `numero_visitantes` | INT | Número de visitantes |
| `gasto_medio_eur` | DECIMAL(10,2) | Gasto medio por visitante en euros |

### `indicadores_economicos`
Indicadores macroeconómicos anuales.

| Columna | Tipo | Descripción |
|---|---|---|
| `anio` | INT | Año |
| `pib_millones_eur` | DECIMAL(12,2) | PIB en millones de euros |
| `paro_tasa_pct` | DECIMAL(5,2) | Tasa de paro (%) |
| `visitantes_totales_mill` | DECIMAL(6,2) | Total de visitantes en millones |
| `balanza_comercial_meur` | DECIMAL(10,2) | Balanza comercial en millones de euros |

### `tributos`
Recaudación tributaria anual por tipo de impuesto.

| Columna | Tipo | Descripción |
|---|---|---|
| `anio_fiscal` | INT | Año fiscal |
| `tipo_tributo` | VARCHAR(50) | Tipo de tributo (IGI, IS, IRPF, ITP) |
| `importe_recaudado` | DECIMAL(12,2) | Importe recaudado |
| `importe_aprobado` | DECIMAL(12,2) | Importe aprobado en presupuesto |
| `importe_ejecutado` | DECIMAL(12,2) | Importe ejecutado |

**Tipos de tributo**:
- `IGI`: Impost General Indirecte (equivalente al IVA español)
- `IS`: Impost de Societats (impuesto de sociedades)
- `IRPF`: Impost sobre la Renda de les Persones Físiques
- `ITP`: Impost sobre Transmissions Patrimonials

### `presupuesto`
Presupuesto del Estado por ministerio y partida.

| Columna | Tipo | Descripción |
|---|---|---|
| `anio_fiscal` | INT | Año fiscal |
| `departamento_codigo` | VARCHAR(10) | Código del ministerio |
| `partida` | VARCHAR(100) | Tipo de partida presupuestaria |
| `tipo` | VARCHAR(20) | Tipo de registro (APROBADO, EJECUTADO) |
| `importe_aprobado` | DECIMAL(12,2) | Importe aprobado |
| `importe_ejecutado` | DECIMAL(12,2) | Importe ejecutado |

**Ministerios** (7 ministerios del gobierno central):
- `MIN001`: Afers Socials i Habitatge
- `MIN002`: Finances i Portaveu
- `MIN003`: Educació i Ensenyament Superior
- `MIN004`: Turisme i Comerç
- `MIN005`: Justícia i Interior
- `MIN006`: Territori i Urbanisme
- `MIN007`: Salut

**Partidas**: Personal, Inversió, Serveis, Transferències

## Queries de ejemplo

### Impacto del turismo en el PIB
```sql
SELECT 
    ie.anio,
    ie.visitantes_totales_mill * 1000000 AS total_visitantes,
    SUM(t.numero_visitantes * t.gasto_medio_eur) / 1000000 AS gasto_turistico_meur,
    ie.pib_millones_eur,
    ROUND((SUM(t.numero_visitantes * t.gasto_medio_eur) / 1000000) / ie.pib_millones_eur * 100, 1) AS peso_pct_pib
FROM turismo t
JOIN indicadores_economicos ie ON t.anio_referencia = ie.anio
WHERE t.anio_referencia BETWEEN 2019 AND 2024
GROUP BY ie.anio, ie.visitantes_totales_mill, ie.pib_millones_eur
ORDER BY ie.anio;
```

### Recaudación fiscal desglosada
```sql
SELECT 
    anio_fiscal,
    tipo_tributo,
    COALESCE(importe_recaudado, 0) AS importe_recaudado
FROM tributos
WHERE anio_fiscal BETWEEN 2019 AND 2021
ORDER BY anio_fiscal, importe_recaudado DESC;
```

### Escenario de cierre de frontera
Pregunta: "Si mañana cierra la frontera, ¿qué parte de la economía y las cuentas del Estado se cae?"

Esta query combina:
1. Peso del turismo en el PIB (2019-2024)
2. Dependencia fiscal del turismo (IGI es ~53% del total fiscal, generado en gran parte por visitantes)

```sql
WITH gasto_turistico AS (
    SELECT 
        t.anio_referencia AS anio,
        SUM(t.numero_visitantes * t.gasto_medio_eur) / 1000000 AS gasto_meur
    FROM turismo t
    GROUP BY t.anio_referencia
),
ingresos_fiscales AS (
    SELECT 
        anio_fiscal AS anio,
        SUM(importe_recaudado) / 1000000 AS total_fiscal_meur
    FROM tributos
    GROUP BY anio_fiscal
)
SELECT 
    ie.anio,
    ie.visitantes_totales_mill,
    gt.gasto_meur AS gasto_turistico_meur,
    ie.pib_millones_eur,
    ROUND(gt.gasto_meur / ie.pib_millones_eur * 100, 1) AS peso_pct_pib,
    ifs.total_fiscal_meur,
    ROUND(gt.gasto_meur * 0.045 / ifs.total_fiscal_meur * 100, 1) AS estimacion_peso_fiscal_pct
FROM indicadores_economicos ie
JOIN gasto_turistico gt ON ie.anio = gt.anio
JOIN ingresos_fiscales ifs ON ie.anio = ifs.anio
WHERE ie.anio BETWEEN 2019 AND 2024
ORDER BY ie.anio;
```

**Interpretación**:
- El gasto turístico representa ~75% del PIB en 2024
- El IGI (IVA andorrano al 4,5%) generado por turismo representa ~54-63% de los ingresos fiscales
- Un cierre completo de frontera eliminaría ~75% del PIB y ~360-410M€ de recaudación fiscal

## Preguntas para probar con artoo

1. "¿Cuál fue el impacto del COVID en el turismo y el PIB?"
2. "¿Qué países son los principales emisores de turistas a Andorra?"
3. "¿Cuál es la estructura de ingresos fiscales del Estado?"
4. "¿Cómo ha evolucionado el gasto ejecutado de los ministerios?"
5. "Si mañana cierra la frontera, ¿qué parte de la economía se cae?"
6. "Compara el gasto turístico con los ingresos del Estado"
7. "¿Cuál es el peso del IGI sobre el total fiscal?"
