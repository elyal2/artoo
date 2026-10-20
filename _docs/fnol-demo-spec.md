# Demo FNOL (seguros) + independencia de dominio — Especificación v0.1

Estado: borrador para revisión. Alcance: nuevo perfil `demos/insurance`, desacople del código respecto a dominios concretos, subida de LLMs a Sonnet 5.5, Terraform y redespliegue completo en Docker.

## 1. ¿Tiene sentido?

Sí. FNOL (First Notice of Loss) encaja con ARTOO:

- Esquema relacional rico (cliente → póliza → cobertura → siniestro → partner) con FKs claras: lo que más luce el catálogo semántico.
- Muchos campos codificados (`clm_stat`, `loss_typ`, `chnl`) que solo un catálogo enriquecido explica. Mismo valor de demo que el perfil hotel.
- Preguntas de negocio naturales: tiempos de asignación, coste por partner, siniestros sin cobertura, SLA.
- Dominio con PII real (DNI, teléfono, IBAN) para enseñar los tags PII/sensibilidad.

Límite a declarar: ARTOO es de **consulta** (solo SELECT). La demo es analítica sobre datos FNOL ya registrados, no un agente de intake que cree siniestros. Un tool MCP `create_claim` queda como fase posterior y requiere decisión de seguridad (escritura).

## 2. Modelo de datos (perfil `insurance`)

Estilo columnas: abreviado/codificado como en `hotel`, para demostrar el enriquecimiento.

| Tabla | Contenido | Claves |
|---|---|---|
| `cust` | clientes (nombre, email, teléfono, DNI, fecha nac., ciudad, segmento) | PK `cust_id` |
| `cvg` | catálogo de coberturas (código, nombre, ramo, límite base) | PK `cvg_id` |
| `pol` | pólizas (ramo HOME/AUTO/HEALTH, estado, fechas, prima, franquicia) | PK `pol_id`, FK `cust_id` |
| `pol_cvg` | coberturas contratadas por póliza (límite, franquicia) | FK `pol_id`, `cvg_id` |
| `ptnr` | partners (grúas, fontaneros, electricistas, cerrajeros, cristaleros; zona, rating, tarifa, tiempo medio de respuesta, activo) | PK `ptnr_id` |
| `clm` | siniestros/FNOL (póliza, cobertura aplicada, canal, tipo, estado, fecha de ocurrencia/declaración, importe estimado/aprobado, score de fraude, descripción libre) | PK `clm_id`, FK `pol_id`, `cvg_id` |
| `clm_dsp` | despachos a partner (siniestro, partner, hora despacho/llegada/fin, coste, valoración) | FK `clm_id`, `ptnr_id` |
| `clm_evt` | histórico de estados del siniestro (para SLA) | FK `clm_id` |

Volumen sugerido: 500 clientes, ~700 pólizas, 40 partners, ~3.000 siniestros, ~3.500 despachos. Semilla determinista (`Faker` con seed fija) y datos con intención: picos de siniestros por temporada (agua en invierno, colisión en verano), partners lentos o caros, siniestros fuera de cobertura, un cluster de fraude.

Valores codificados (ejemplos): `clm_stat` NEW/TRI/ASG/INP/CLS/REJ; `loss_typ` WTR/ELC/BRK/COL/BKD/LCK/GLS; `chnl` APP/TEL/WEB/AGT; `ptnr_trade` TOW/PLB/ELC/LCK/GLZ.

Preguntas de aceptación (≥12, se documentan en `DEMO.md`): ejemplos
- ¿Cuántos siniestros se declararon por canal el último mes?
- ¿Qué partner de fontanería tiene mejor tiempo medio de llegada?
- ¿Qué porcentaje de siniestros se rechaza por falta de cobertura, por ramo?
- ¿Coste medio de asistencia en carretera por ciudad?
- ¿Siniestros con score de fraude alto y partner asignado?

## 3. Revisión de independencia del código

Hallazgos del análisis actual (dominio acoplado al motor):

| Ubicación | Acoplamiento | Acción |
|---|---|---|
| `catalog/openmetadata.py:128` | `if "pib" in col["name"]` hardcodeado | eliminar; usar reglas de unidades genéricas |
| `enricher/writer.py` (patrones `_rooms`, `_keys`, `_importe_eur`…) | patrones de unidades/dominio hotel y España dentro del código | mover a `demos/<perfil>/profile.yaml` (`unit_patterns`, `count_patterns`) con un conjunto base genérico en el motor |
| `catalog/openmetadata.py:~490` glosario `UnidadesMedida` | términos en español fijos | glosario base configurable por perfil/idioma |
| `llm/prompts.py` | ejemplos `bkng`, `prop`, `pib_millones_eur` en el prompt | sustituir por ejemplos neutros; regla de AGENTS.md: prompts agnósticos |
| `config.py` | `demo_profile` default `hotel`, región `eu-south-2`, modelo Nova | default neutro; modelos por tarea |
| `llm/client.py` | rama específica Nova y Anthropic en Bedrock | mantener por proveedor, probar con Sonnet 5.5 |

Resultado esperado: añadir un dominio = crear `demos/<perfil>/{init.sh,seed.py,profile.yaml}` sin tocar `src/`. Criterio de aceptación: test que carga un perfil ficticio mínimo y verifica que no se usa ningún nombre de dominio del código; `grep` de términos de dominio en `src/` vacío (salvo glosario base).

## 4. LLMs → Sonnet 5.5

- IDs: API directa `claude-sonnet-5-5`; Bedrock EU `eu.anthropic.claude-sonnet-5-5-…` (**verificar el ID exacto de inference profile y la disponibilidad en la región antes de fijarlo**).
- Mantener un modelo configurable por tarea (intent, SQL, explicación, chart, enricher) vía env; el valor por defecto de todos pasa a Sonnet 5.5, con posibilidad de bajar enricher/intent a un modelo más barato.
- Registrar tokens in/out por petición (regla de coste) y comparar latencia/coste frente a Nova Lite en la demo.
- Revisar `max_tokens`/temperatura y el parseo JSON con las respuestas de Sonnet 5.5; actualizar `.env.example`, `AGENTS.md` y tests de `llm/client`.

## 5. Terraform

Reglas globales: infra en `terraform/` (`modules/`, `environments/`), nunca `apply` sin `plan` revisado, LocalStack para AWS local, target `make plan`/`make apply`.

Propuesta:
- `terraform/modules/llm_access`: política IAM mínima `bedrock:InvokeModel` sobre los modelos configurados (+ rol/usuario para el contenedor, sin `AWS_PROFILE` en Docker).
- `terraform/modules/docker_stack`: provider `kreuzwerker/docker` para red, volúmenes y contenedores de `artoo-api` y `artoo-enricher`.
- `terraform/environments/local`: LocalStack + Docker; `environments/aws` solo esqueleto.
- Targets `make tf-init|plan|apply|destroy`; job `terraform plan` en CI.

Decisión abierta (D1): OpenMetadata/Elasticsearch/Postgres/Superset (12 servicios en `docker-compose.yml`) **siguen en Compose** y Terraform gestiona solo ARTOO + acceso a Bedrock. Migrar todo el stack a Terraform duplica trabajo y no aporta a la demo. Recomendado.

## 6. Redespliegue y verificación en Docker

Flujo: `make down` (scoped al proyecto, nunca `prune` global) → `make demo-full DEMO_PROFILE=insurance`. Verificación: tests, `make lint-check`, crawl OM OK, enrichment sin errores, las ≥12 preguntas de aceptación devuelven SQL válido, healthchecks verdes, y capturas/resultados en `DEMO.md`.

## 7. Fases y dependencias

1. Independencia de dominio (bloquea todo lo demás).
2. Sonnet 5.5 (paralelo a 1 salvo prompts).
3. Perfil `insurance` (depende de 1).
4. Terraform (paralelo a 3).
5. Redespliegue y validación (depende de 1–4).

## 8. Riesgos

- ID/disponibilidad de Sonnet 5.5 en Bedrock EU → verificar primero; fallback API directa Anthropic.
- Coste/latencia de Sonnet 5.5 en enrichment masivo → modelo por tarea.
- OpenMetadata 1.5.8 tarda 3–5 min en arrancar → no afecta al diseño, sí a los tiempos de validación.
- Calidad del SQL con esquema más grande (8 tablas, FKs compuestas) → suite de regresión de preguntas.
- Datos sintéticos de PII: usar solo valores ficticios.
