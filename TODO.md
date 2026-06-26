# TODO

## 🔴 Crítico

- [ ] **Resolver error SQL en query compleja**: "¿Qué porcentaje del PIB depende del turismo?" falla con `column "i.pib_millones_eur" must appear in the GROUP BY clause`. El LLM genera SQL inválido con GROUP BY incorrecto.
- [ ] **Validar conversion rules en prompts**: Verificar que las conversion rules generadas por `generate_conversion_rules()` están siendo usadas efectivamente por el LLM en queries que comparan diferentes unidades.

## 🟡 Importante

- [ ] **Mejorar detección de intent**: Nova Lite falla en preguntas hipotéticas ("¿qué pasaría si...?"). Considerar usar modelo más capaz por defecto para `LLM_INTENT_MODEL` o mejorar el prompt.
- [ ] **Tests para unit enrichment**: Agregar tests de integración que validen end-to-end: enricher → OM API → QueryPipeline → SQL con conversiones correctas.
- [ ] **Documentar strategy de troubleshooting**: Crear guía para diagnosticar errores comunes (LLM timeouts, SQL inválido, crawl failures, enrichment errors).
- [ ] **Optimizar prompts de SQL**: Revisar si las conversion rules están generando demasiado ruido en el prompt. Considerar simplificar o mover a sección separada.

## 🟢 Mejoras

- [ ] **Separar demos mixtos**: Decidir si mantener hotel + andorra en misma DB o hacer `demos/andorra/seed.py` truncar también tablas hotel.
- [ ] **Agregar tests de regresión para queries críticas**: Suite de queries conocidas con respuestas esperadas para detectar regresiones en SQL generation.
- [ ] **Mejorar logging de enricher**: Añadir métricas de éxito/fallo por tabla (cuántas columnas enriquecidas, cuántos unit terms asignados, etc.).
- [ ] **Validar glossary terms en tests**: Test unitario que verifique que `_infer_unit_glossary_term()` detecta correctamente los 7 términos en nombres de columnas variadas.
- [ ] **Documentar patrones de unit detection**: Crear tabla en README con todos los 83 patrones regex y ejemplos de nombres de columnas que matchean.
- [ ] **Chart fallbacks**: Implementar fallback a tabla si chart generation falla (actualmente falla silenciosamente).
- [ ] **Mejorar UX del chat**: Agregar indicador de "pensando..." mientras el LLM genera SQL/explicación.

## 🔵 Exploración Futura

- [ ] **Soporte para múltiples bases de datos**: Permitir que ARTOO consulte varias bases de datos en una misma query (cross-DB joins).
- [ ] **Cache de SQL queries**: Cachear queries frecuentes para reducir latencia y coste LLM.
- [ ] **Feedback loop**: Permitir al usuario marcar respuestas como incorrectas para mejorar el sistema.
- [ ] **Sugerencias de queries**: Basándose en `commonQueries` del catálogo, sugerir preguntas populares al usuario.
- [ ] **Semantic layer abstraction**: Crear capa semántica que abstraiga tablas/columnas técnicas en conceptos de negocio (ej. "ventas" abstrae `orders + order_lines`).
- [ ] **Multi-tenancy**: Soporte para múltiples tenants con aislamiento de datos.

## 📚 Documentación Pendiente

- [ ] **ADRs**: Crear ADRs para decisiones arquitectónicas importantes:
  - ADR-001: Por qué OpenMetadata vs Datahub/Atlas
  - ADR-002: Por qué glossary terms vs custom properties para unidades
  - ADR-003: Strategy de no forzar conversiones en SQL
  - ADR-004: Por qué bypass de Airflow en crawl
- [ ] **Diagramas C4**: Completar Context + Container diagrams en `_docs/`
- [ ] **Runbook de operaciones**: Guía para desplegar en producción, monitoreo, troubleshooting
- [ ] **Guía de contribución**: CONTRIBUTING.md con setup de desarrollo, estilo de código, proceso de PR

## 🐛 Bugs Conocidos

- [ ] **Makefile `make test` no ejecuta tests**: Pasa `-m unit` pero ningún test tiene ese marker. Debería ejecutar todos los tests por defecto.
- [ ] **OpenMetadata login bloqueado**: Después de 3 intentos fallidos, cuenta bloqueada por ~5 min. Documentar workaround.
- [ ] **Airflow 3.x incompatible**: Plugin de OpenMetadata no funciona con Airflow 3.x. Actualmente bypassed con CLI.

## ✅ Completado Recientemente

- [x] Upgrade OpenMetadata 1.2.4 → 1.5.8
- [x] Implementar Strategy 2: Glossary Terms para unidades
- [x] Fix Bedrock EU inference profiles (prefijo `eu.`)
- [x] Documentar error de Docker config cache
- [x] Actualizar README con nuevas variables de entorno
- [x] Actualizar AGENTS.md con cambios de configuración
- [x] Fix metadata crawl (crear `airflow_user`)
- [x] Validar que OM 1.5.8 devuelve glossary terms vía API
