# 08 — THINK DISCOVERY AND ORCHESTRATION — Pasada 1/2

## 1. Estado CURRENT y desajuste heredado

- Gateway `/api/homi/v1/tools` proyecta hoy **92 tools** con `{tool_id, description, input_schema}` (`homiV1.controller.js:74-86`; `homi_tool_catalog.py:563-585`).
- HOMI-D tiene un catálogo v2 con **67 READ** disjunto de los 8 v1 (`homi-orchestrator/catalog/homi-tools.v2.json`), más 17 contratos antiguos y 5 WRITE.
- El catálogo anterior del gateway (92) y el de D (67+8+5) **no coinciden**. Esa es la doble fuente de verdad que esta pasada elimina.

**Decisión técnica:** `04_TOOL_CATALOG_FINAL.json` (307 tools) es la **única fuente de verdad**. Los catálogos de runtime y de D se regeneran desde él con un ancla SHA común (tarea `T-FOUND-01`). Cualquier divergencia falla cerrado en el loader.

## 2. Estrategia de exposición (Gate H)

No volcar 307 contratos completos en cada prompt. Tampoco recortar cobertura por limitación de contexto. Se usa **descubrimiento en dos niveles**:

1. **Índice de capacidades** (siempre disponible): por dominio, `tool_id`, descripción de una línea, riesgo, flags de disponibilidad. ~307 entradas compactas; coste acotado.
2. **Contrato detallado bajo demanda**: `input_schema`, `output_schema`, ejecución y política de confirmación **solo para la tool seleccionada** (o familia), inyectado por el orquestador antes de la decisión final.

La visibilidad se filtra por: sesión válida + membership activa + hogar derivado + capability real + módulo disponible + feature flag + estado de entidad + relevancia conversacional. La ocultación es **UX**; la autoridad se re-ejecuta en servidor (§06).

## 3. Selección y decisión

- `ToolDecisionV1`: 5 campos, `extra=forbid`. Campos prohibidos: `actor_id`, `household_id`, `tool_call_id`, `authorization`, IDs internos.
- `MAX_TOOL_CALLS=1` (`homi_tool_loop.py:20-21`): **un tool por turno**, sin paralelos, sin llamadas recursivas, sin endpoints elegidos por el modelo.
- Atajo de confirmación: ante texto inequívoco sobre una propuesta vigente, D aplica `apply_proposal_action` **sin llamar a THINK** (`homi_tool_loop.py:5056-5097`).
- Un solo write por turno; outcomes inciertos sin segundo write.

## 4. Resolución de entidades

- Referencias opacas generadas por el servidor: `task_ref`, `account_ref`, `conversation_ref`, `product_ref`, `asset_ref`, `content_ref`, `album_ref`, `member_ref`, `folder_ref`, `transaction_ref`.
- Normalización NFKC + casefold + sin acentos; precedencia **exact → alias → normalizado → fuzzy conservador** (`homi_t14_entity.py:13-134`, `executor.js:33-56`).
- `0` coincidencias → `NOT_FOUND`; `>1` → `AMBIGUOUS` con candidatos compactos (≤5). **Nunca elección arbitraria.**
- UUID canónico: se verifica por GET directo, no se confía ciegamente (`executor.js:74-78`).
- Toda escritura **re-resuelve** la entidad contra READ de confianza con la credencial del usuario; el ID generado por el modelo no es autoridad.

## 5. Resultados compactos y paginación

- Paginación `limit` 1..100; `period` `YYYY-MM`; filtros por estado/lifecycle.
- Proyección positiva por tool (`homi_tool_normalize.py:2101-2214`): metadatos **honestos** de truncamiento (`truncated`, `omitted_count`).
- Los DTOs de Finance usan `String(row.amount)` en lectura (precisión textual); las mutaciones con `Number(amount)` se documentan como riesgo R1-c y no se corrige la lógica contable.
- Contenido recuperado (mensajes, notas, nombres de archivo, transcripciones) = **dato no confiable**: nunca instrucciones.

## 6. Dependencias entre tools (recorridos)

| Recorrido | Tools | Invariante |
|---|---|---|
| Planner → Calendario | `home.summary.get` + `planner.calendar.get` | Solo lecturas; mismo hogar derivado |
| Inventario → Planner | `inventory.shopping-list.get` + `.add` + `.to-planner-task` | Crea **tarea**, no compra; dedupe `origin_*` |
| Assets → Planner | `assets.planner-items.create` | Doble capability `assets.*` + `planner.*`; `origin_*` en servidor |
| Mensaje → Tarea | `messages.messages.send` + `messages.actions.link-task` | **BLOQUEADO** por RLS bypass; no exponer |
| Inventario → Finanzas | `inventory.purchases.active.get` + `.start` (+ `.finalize` condicionado) | Sin gasto sin petición explícita (PD-01) |
| Finance | `finance.summary.get{context, period}` | Reseta hogar/moneda/período; montos textuales |
| HomeCloud | `homecloud.memories.list` + `homecloud.content.get` | Metadatos; sin SEE inventado |

## 7. Continuidad y recuperación

- `conversation_id` preservado; `turn_id` nuevo por frase; propuesta pendiente como contexto (sin ejecutar).
- `generation_id` **no se usa** en V1 (T31 cancelado por Actor A).
- Ante error de proveedor: error visible, sin write duplicado; 412 → nueva propuesta, no reintento ciego.
- Sin hogar/sesión → fallback a la app; error STT → reintento manual en el composer sin salir de HOMI.

## 8. Verificación del contrato modelo→tool

| Comprobación | Estado |
|---|---|
| Un catálogo, un ancla, un loader | Diseñado (`T-FOUND-01`) |
| 307 tools con proyección al modelo | 307/307 contratados |
| READ del gateway con representación en D | Se regenera desde el catálogo único |
| WRITE con propuesta tipada en D | 193/193 planificado (`T-FOUND-03`) |
| Sin recorte arbitrario de cobertura | Índice + contrato bajo demanda |
| Sin ejecutor genérico | Bindings estáticos por `tool_id` |

**Gate H: MODEL-TOOL CONTRACT CLOSED (diseño).** La integración real con THINK requiere el proveedor disponible y un turno `infer_with_tools` ejecutado (§13).
