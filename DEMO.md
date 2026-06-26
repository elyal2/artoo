# ARTOO - Demo Script

Demo script para mostrar las capacidades del sistema de análisis en lenguaje natural sobre datos del Govern d'Andorra.

---

## Configuración de la Demo

### Requisitos previos
```bash
# 1. Levantar la infraestructura completa
make demo-full

# 2. Verificar que todos los servicios estén corriendo
make ps

# 3. Verificar health del API
curl http://localhost:8000/health
# Esperado: {"status":"ok"}
```

### URLs importantes
- **Chat UI**: http://localhost:8000
- **OpenMetadata**: http://localhost:8585 (admin@openmetadata.org / admin)
- **Superset**: http://localhost:8088 (admin / admin)

---

## Secuencia de Demo (15 minutos)

### 1. Introducción (2 min)

**Contexto:**
> "ARTOO es un sistema de análisis de datos en lenguaje natural que combina:
> - OpenMetadata como catálogo semántico enriquecido
> - LLM (AWS Bedrock Nova Lite) para generación SQL y interpretación
> - Pipeline de validación: semantic search → SQL generation → AST validation → EXPLAIN dry-run → execution
> - Frontend interactivo con visualizaciones D3.js"

**Mostrar arquitectura:**
- Abrir `_docs/c4-context.dsl` o diagrama
- Explicar: Usuario → FastAPI → OpenMetadata (catálogo) + Postgres (datos) + LLM (razonamiento)

---

### 2. Exploración del Catálogo (3 min)

**Paso 1: Mostrar tablas disponibles**

Abrir http://localhost:8000 y mostrar el sidebar izquierdo con las 4 tablas:
- `turismo` (Tourism)
- `indicadores_economicos` (Economics)
- `tributos` (Taxation)
- `presupuesto` (Financial Management)

**Paso 2: Click-to-query**

Hacer clic en la tabla `turismo` en el sidebar.

**Resultado esperado:**
```
Pregunta generada automáticamente: "Show me all data from turismo"
SQL: SELECT * FROM turismo LIMIT 100
Filas: 192 rows (2015-2026, trimestral, por país)
```

**Punto a destacar:** "El sistema entiende la estructura del catálogo y puede explorar cualquier tabla sin escribir SQL."

---

### 3. Queries Simples - Una Tabla (3 min)

#### Query 1: Dato puntual
```
¿Cuántos visitantes recibió Andorra en 2024?
```

**Resultado esperado:**
- SQL: `SELECT SUM(numero_visitantes) FROM turismo WHERE anio_referencia = 2024`
- Resultado: ~15.6M visitantes
- Gráfico: Single metric card
- Explicación: "Andorra received approximately 15.6 million visitors in 2024"

**Punto a destacar:** "El LLM genera SQL correcto agregando por año, aunque la tabla es trimestral."

---

#### Query 2: Evolución temporal
```
Muéstrame la evolución de visitantes por año desde 2019
```

**Resultado esperado:**
- SQL: `SELECT anio_referencia, SUM(numero_visitantes) FROM turismo WHERE anio_referencia >= 2019 GROUP BY anio_referencia ORDER BY anio_referencia`
- Gráfico: Line chart
- Datos clave:
  - 2019: 15.3M
  - 2020: 6.4M (caída COVID -58%)
  - 2021-2023: recuperación progresiva
  - 2024: 15.6M (recuperación completa)

**Punto a destacar:** "El sistema recomienda automáticamente line chart para series temporales. El gráfico muestra claramente el impacto COVID."

---

#### Query 3: Distribución
```
¿De qué países vienen más turistas en 2024?
```

**Resultado esperado:**
- SQL: `SELECT pais_origen, SUM(numero_visitantes) FROM turismo WHERE anio_referencia = 2024 GROUP BY pais_origen ORDER BY SUM(numero_visitantes) DESC`
- Gráfico: Bar chart horizontal
- Top países: España, Francia, Portugal

**Punto a destacar:** "La columna `pais_origen` tiene descripciones enriquecidas por el catálogo. El sistema sabe agrupar correctamente."

---

### 4. Queries con JOINs - Multi-tabla (4 min)

#### Query 4: Análisis económico básico
```
Muéstrame PIB y número de visitantes por año
```

**Resultado esperado:**
- SQL: JOIN entre `indicadores_economicos` y `turismo`
- Gráfico: Line chart con dos series
- Correlación visible: cuando visitantes caen (2020), PIB cae

**Punto a destacar:** "El sistema infiere la relación entre tablas usando `anio_referencia` como clave común, gracias al enriquecimiento del catálogo."

---

#### Query 5: Porcentaje del PIB
```
¿Qué porcentaje del PIB representa el gasto turístico?
```

**Resultado esperado:**
- SQL: Calcula `(gasto_turistico / PIB) * 100`
- Resultado: ~75% en 2024
- Explicación: "Tourism spending represents approximately 75% of Andorra's GDP in 2024, showing the country's heavy economic dependence on tourism."

**Advertencia:** Este cálculo usa `gasto_medio_eur * numero_visitantes` dividido por PIB. Las unidades están correctamente documentadas en el catálogo (millones de euros).

---

#### Query 6: Impacto fiscal
```
Compara ingresos tributarios y gasto público en 2024
```

**Resultado esperado:**
- SQL: JOIN entre `tributos` y `presupuesto` 
- Tributos 2024: 661M€ (IGI 351M, IS 175M, IRPF 102M, ITP 33M)
- Gasto ejecutado 2024: 162M€ (solo 7 ministerios centrales, sin CASS ni comunas)
- Gráfico: Stacked bar chart

**Punto a destacar:** "El catálogo incluye glossary terms (`UnidadesMedida.Millones_EUR`) que documentan las unidades. El sistema NO hace conversiones aritméticas forzadas — confía en que el LLM interprete correctamente las unidades en la explicación."

---

### 5. Intent Routing - Conversacional (2 min)

#### Query 7: Pregunta meta (no data query)
```
¿Cómo interpretas estos datos?
```

**Resultado esperado:**
- **NO genera SQL**
- Respuesta conversacional:
  > "Based on the data we've analyzed, Andorra's economy shows a strong dependence on tourism, which represents approximately 75% of GDP. The COVID-19 pandemic had a severe but temporary impact, with visitor numbers dropping 58% in 2020. However, the recovery has been complete by 2024, returning to pre-pandemic levels. Tax revenues are heavily influenced by tourist spending, particularly through IGI (sales tax), which is the largest revenue source at 53% of total tax collection."

**Punto a destacar:** "El sistema clasifica la intención (conversacional vs data_query) ANTES de generar SQL. Esto evita errores en preguntas que no requieren consultas a la base de datos."

---

### 6. Semantic Search (2 min)

#### Query 8: Búsqueda por concepto
```
¿Qué datos tengo sobre economía?
```

**Resultado esperado:**
- OpenMetadata semantic search devuelve:
  - `indicadores_economicos` (Economics domain)
  - `presupuesto` (Financial Management domain)
  - `tributos` (Taxation domain)
- El LLM genera un resumen de las tablas disponibles SIN ejecutar SQL

**Punto a destacar:** "El semantic search usa embeddings en OpenSearch para encontrar tablas por significado, no por nombre exacto. Los dominios de negocio (`Economics`, `Tourism`, etc.) ayudan a la búsqueda."

---

### 7. Catálogo Enriquecido (1 min)

**Mostrar OpenMetadata:**
1. Abrir http://localhost:8585
2. Login: `admin@openmetadata.org` / `admin`
3. Navegar a `Explore > Tables > turismo`
4. Mostrar:
   - **Description**: Enriquecida automáticamente por el enricher
   - **Domain**: Tourism
   - **Glossary Terms**: `UnidadesMedida.Millones_EUR` en columnas numéricas
   - **Tags**: Clasificaciones de sensibilidad (si se configuraron)
   - **Relationships**: Foreign keys inferidas

**Punto a destacar:** "Todo este contexto semántico se genera automáticamente con `make enrich` y se usa en el prompt del LLM para generar SQL correcto."

---

## Preguntas de Backup / Q&A

### ¿Qué pasa si pregunto algo que no está en los datos?
```
¿Cuál es la población de Andorra?
```
**Resultado:** El sistema intenta buscar tablas relacionadas, no encuentra datos, y responde honestamente: "I don't have population data in the available tables."

---

### ¿Puede el sistema detectar errores en el SQL?
Sí, tiene 3 capas de validación:

1. **AST validation** con `sqlglot`: valida que las columnas existan en las tablas correctas
2. **EXPLAIN dry-run**: Postgres valida el SQL completo sin ejecutarlo
3. **Retry con feedback**: Si falla, el LLM recibe el error y reintenta

**Demo:**
```
Muéstrame la columna "ventas" de turismo
```
**Resultado:** Error: "Column 'ventas' does not exist. Available columns: anio_referencia, trimestre, pais_origen, numero_visitantes, gasto_medio_eur"

---

### ¿Funciona con preguntas hipotéticas?

**Limitación actual:**
```
Si mañana cierra la frontera, ¿qué parte de la economía se cae?
```

Esta pregunta genera SQL básico (datos históricos) pero **NO hace análisis de escenarios**. 

**Razón:** Requiere multi-step reasoning:
1. Identificar tablas relevantes (turismo, tributos, PIB)
2. Calcular dependencia real (con agregaciones complejas)
3. Proyectar impacto (requiere modelo económico)

**Roadmap:** Implementar query planning multi-paso (similar al Skill de Claude del PDF).

---

## Métricas de Éxito de la Demo

Al final, el usuario debería entender:

✅ **Valor del catálogo semántico**: Descripciones, dominios, glossary terms mejoran la calidad del SQL  
✅ **Pipeline robusto**: 3 capas de validación evitan SQL roto  
✅ **Intent routing**: El sistema sabe cuándo NO generar SQL  
✅ **Semantic search**: Busca tablas por significado, no por nombre  
✅ **Visualización automática**: D3 charts recomendados según el tipo de datos  
✅ **Transparencia**: SQL visible, explicaciones en lenguaje natural  

---

## Troubleshooting Durante la Demo

### El API no responde
```bash
docker compose logs artoo-api --tail=50
# Si hay errores de conexión a OpenMetadata:
docker compose restart openmetadata-server
sleep 30
docker compose restart artoo-api
```

### OpenMetadata no tiene tablas
```bash
make crawl  # Re-crawl metadata
make enrich # Re-enrich semantic metadata
```

### Los gráficos no se renderizan
- Refresh del navegador (Ctrl+Shift+R)
- Verificar consola JavaScript (F12)

### El LLM tarda mucho
- Nova Lite es rápido (~2s), pero las primeras queries pueden tardar más (cold start)
- Si tarda >10s, verificar AWS credentials: `aws sts get-caller-identity --profile default`

---

## Datos de Referencia

### Números clave para validar resultados:

| Métrica | 2019 | 2020 (COVID) | 2024 |
|---------|------|--------------|------|
| Visitantes | 15.3M | 6.4M (-58%) | 15.6M |
| PIB | 3,078M€ | 2,491M€ (-19%) | 3,499M€ |
| Gasto turístico | 2,474M€ | 1,007M€ | 2,632M€ |
| % PIB turismo | 80.4% | 40.4% | 75.2% |
| Tributos totales | 538M€ | 426M€ | 661M€ |
| IGI (sales tax) | 286M€ | 203M€ | 351M€ |

### Estructura de tablas:

**turismo**: 192 rows (2015-2026, trimestral, 16 países)  
**indicadores_economicos**: 6 rows (2019-2024, anual)  
**tributos**: 24 rows (2019-2024, 4 tipos: IGI, IS, IRPF, ITP)  
**presupuesto**: 168 rows (2019-2024, 7 ministerios, ingresos+gastos)

---

## Próximos Pasos / Roadmap

### Mejoras planificadas:

1. **Query planning multi-paso**: Para preguntas complejas tipo "¿qué pasa si cierra la frontera?"
2. **Semantic search mejorado**: Usar embeddings para column-level search
3. **Query history persistente**: Actualmente solo en memoria
4. **Retry logic para Bedrock**: Manejar throttling automáticamente
5. **Caching de resultados**: Reducir latencia y costos
6. **Observabilidad**: Logs estructurados, métricas de latencia/costos
7. **Multi-source**: DuckDB para files (CSV, Parquet), no solo Postgres

---

## Contacto

Para más información sobre el proyecto:
- Repo Azure DevOps: https://dev.azure.com/logicalis-data-apps/artoo
- Repo GitHub (backup): https://github.com/elyal2/artoo
- Documentación técnica: `AGENTS.md`, `README.md`
