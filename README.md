# ARTOO (PoC)

Demo técnico: **catálogo semántico (OpenMetadata) + LLM** para pasar de preguntas en lenguaje natural a SQL **fundamentado en el esquema**, con una base PostgreSQL de ejemplo (hotel). Detalle funcional y de arquitectura: [`ARTOO_PoC_Specification.md`](ARTOO_PoC_Specification.md).

## Requisitos

- **Docker** + Docker Compose  
- **Python 3.12+** y [**uv**](https://docs.astral.sh/uv/) (el `Dockerfile` instala `uv`)  
- Credenciales para el **LLM** configuradas en `.env.local` (p. ej. **AWS Bedrock** con perfil/región, u OpenAI/Anthropic según `LLM_PROVIDER`)

## Puesta en marcha rápida

1. Copia variables de entorno:

   ```bash
   cp .env.example .env.local
   ```

   Ajusta secretos: LLM (p. ej. `LLM_AWS_PROFILE` / `LLM_AWS_REGION` para Bedrock), contraseñas de Airflow/Superset si las usas, y **`OPENMETADATA_API_TOKEN`** si tu OpenMetadata exige JWT (en muchos despliegues locales el bootstrap usa el bot de ingestión; ver `openmetadata/bootstrap.py`).

2. Levanta el stack con un solo fichero **`docker-compose.yml`**: OpenMetadata (Postgres + Elasticsearch + Airflow/ingestión), Postgres con `hotel_demo` vía `postgres/init.sql`, Superset, `artoo-api` y `artoo-enricher`.

   ```bash
   make up
   ```

   El servidor OpenMetadata puede tardar **varios minutos** en quedar listo.

3. **Sembrar datos demo** en `hotel_demo`:

   ```bash
   make seed
   ```

4. **Registrar el origen Postgres en OpenMetadata** y disparar la ingestión de metadatos:

   ```bash
   make bootstrap
   ```

   (Equivale a ejecutar `openmetadata/bootstrap.py` vía el contenedor `artoo-enricher` con `--bootstrap-only`.) Espera a que el crawl termine (UI de OpenMetadata o **2–5 minutos** de margen).

5. **Enriquecer el catálogo** — en la demo en vivo suele hacerse **en directo** con `make enrich` (ver [guion](#guion-de-demo-en-vivo-recomendado)). Para ensayar antes:

   ```bash
   make enrich
   ```

6. **API + chat web**:

   ```bash
   make api
   ```

   Chat y API: **http://localhost:8000** (la UI estática sirve en `/`; la API bajo `/api/…`).

## URLs útiles

| Servicio        | URL por defecto        |
|----------------|------------------------|
| Chat + API     | http://localhost:8000  |
| OpenMetadata   | http://localhost:8585  |
| Superset (“antes”) | http://localhost:8088  |
| Airflow (ingestión OM) | http://localhost:8080  |

Postgres del demo queda en el servicio **`postgresql`** del compose (puerto **5432** en host si está publicado).

## Guion de demo en vivo (recomendado)

Tiene sentido **no** ejecutar el enrich antes de la presentación: el momento en que el LLM **rellena significado** en el catálogo es la prueba de valor más clara. Deja hechos **antes** (fuera de pantalla o la noche anterior): `make up`, `make seed`, `bootstrap.py`, esperar al **crawl** de metadatos, y tener **`make api`** levantado. Así en OpenMetadata solo verás **estructura cruda** (nombres crípticos, tipos, FKs) hasta que lances el enrich.

### Preparación (sin audiencia)

- Stack arriba, datos sembrados, servicio Postgres registrado en OM y **ingestión de metadatos completada**.
- **No ejecutes** `make enrich` si quieres el efecto “antes/después” en catálogo en la misma sesión.

### En vivo — narrativa sugerida (~5–7 min)

1. **“El antes” (manual)** — Abre **Superset** u otra SQL UI: el esquema es críptico (`bkng`, `bk_status`…); la pregunta de negocio obliga a **saber tablas y códigos** (p. ej. cancelaciones → `CNCL`).

2. **Catálogo solo crawl** — Abre **OpenMetadata**: el crawler ya descubrió tablas y columnas, pero **sin** descripciones de negocio útiles (o muy genéricas). Refuerza el gap: estructura sí, **semántica no**.

3. **Enriquecimiento en vivo** — En una terminal **visible** (o compartida), ejecuta:

   ```bash
   make enrich
   ```

   Comenta en voz alta: lectura de muestras + LLM + escritura al catálogo. Si el job tarda un minuto, es aceptable: es el “procesamiento” visible. Opcional: `docker compose … logs` del contenedor si quieres más detalle.

4. **Catálogo después** — **Refresca** OpenMetadata: misma tabla (p. ej. `bkng`), ahora con **descripciones**, tags de negocio / PII donde aplique. Opcional: búsqueda “cancellation” y muestra que el catálogo “habla el idioma del negocio”.

5. **“El después” (chat)** — Abre **http://localhost:8000**, 2–4 preguntas en lenguaje natural; muestra SQL + resultados + explicación.

Preguntas sugeridas (también como chips en la UI):

- *Which properties have the highest cancellation rate?*
- *Show top 10 customers by total spend who haven't returned in 6 months*
- *Average NPS by property and room category*
- *Compare weekend vs weekday occupancy across all properties*

**Cierre:** el patrón es **conectar → crawlear → enriquecer (aquí vive ARTOO) → preguntar en natural**; el origen puede ser este Postgres o el del cliente.

### Si ya enriqueciste antes de la demo

Puedes igualmente contar la historia con capturas o una segunda base, o **vaciar descripciones** en OM solo para el PoC (más frágil). Lo más limpio para “en vivo” es **no** haber corrido `make enrich` en esa base hasta el momento 3.

## API relevante

- `POST /api/query` — cuerpo `{"question": "..."}`  
- `GET /api/tables`, `GET /api/table/{fqn}`  
- `GET /health`  
- **`/mcp`** — endpoint ASGI MCP (herramientas `query_data`, `list_tables`, `describe_table`) para clientes compatibles con MCP

## Desarrollo local (sin Docker para el código Python)

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run mypy src/
```

## Makefile

| Objetivo   | Descripción |
|-----------|-------------|
| `make up` | Levanta el stack Compose |
| `make seed` | Carga datos demo en `hotel_demo` (vía contenedor `artoo-api`) |
| `make bootstrap` | Registra Postgres en OpenMetadata y dispara el crawl (espera a que OM responda en `:8585`) |
| `make enrich` | Enriquecimiento semántico (LLM → catálogo); **en demo en vivo** suele lanzarse aquí a propósito |
| `make api` | Levanta `artoo-api` |
| `make demo` | `up` + `seed` + `bootstrap` + `api` — **sin** enrich (para hacer `make enrich` en pantalla) |
| `make demo-full` | Igual que arriba **más** `enrich` (todo en un solo comando) |
| `make test` / `make lint` | Pytest con cobertura y ruff + mypy |
| `make down` | Para servicios y borra volúmenes (`-v`) |

## Mejoras recomendadas (siguiente iteración)

- **Flujo demo**: ya existe `make demo` (sin enrich) y `make demo-full` (con enrich); ajustar tiempos de espera al crawl si hace falta.
- **Tests**: completar `test_list_tables_paginates` (hoy es esqueleto) y/o pruebas de integración con OM + Postgres en CI opcional.
- **Observabilidad**: `/health` podría comprobar conectividad a OM y Postgres (modo “deep”).
- **Seguridad PoC**: CORS abierto y validador SQL solo orientado a demos; endurecer si pasa a entornos compartidos.
- **Tokens OpenMetadata**: documentar cómo obtener JWT en tu versión de OM si el bootstrap falla por 401.

---

© PoC ARTOO — Logicalis España
