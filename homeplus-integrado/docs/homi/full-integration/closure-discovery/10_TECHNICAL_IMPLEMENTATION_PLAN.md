# 10 — TECHNICAL IMPLEMENTATION PLAN — Pasada 1/2

**Destinatario:** Actor C en la pasada 2. **Regla:** este documento permite implementar sin tomar decisiones de producto. Las 6 decisiones pendientes tienen default seguro (§14).

## 1. Arquitectura que se reutiliza

```
Cliente (mi-front-limpio)
   POST /api/homi/v1/text/turn · /voice/transcript · /tools/:id/invoke
   ▼
Gateway HOMI (backend 18/11, :3100)
   authFinalMiddleware → getPlannerContext → isToolVisible → executeTool
   binding estático por tool_id → endpoint FIJO del catálogo + bearer original
   ▼
Servicios canónicos (ÚNICA autoridad de negocio) → PostgreSQL/Supabase + audit_events/outbox
   ▲ rpc HTTP firmado
HOMI-D (:8001)  /invoke → THINK → decisión → propuesta → ledger → un solo dispatch
   ▼
THINK (HOMI-A) · STT (HOMI-C) · SEE (HOMI-B, opcional/BLOCKED)
```

**Decisiones técnicas cerradas:**
1. Un solo frontend (`mi-front-limpio`); un solo gateway (módulo HOMI en el backend del 18/11).
2. Un solo catálogo (`04_TOOL_CATALOG_FINAL.json`) y un ancla SHA; se regeneran runtime y D desde él.
3. Adaptador de endpoint fijo: `http.method` + `http.path` congelados; **sin `execute_any_api_request`**.
4. Autoridad de argumentos: el gateway es la autoridad final; D valida forma.
5. Registry estático con `require()` estáticos; sin `require` dinámico en runtime.
6. Ledger en esquema `homi`, migración nueva no destructiva; sin tablas de producto ni RLS nuevos.
7. Sin T31, LiveKit, VAD, TTS, transports streaming ni control-plane legacy.

## 2. Orden de slices (L1)

| # | Slice | Tarea(s) | Por qué aquí |
|---:|---|---|---|
| 1 | Foundation y compatibilidad | `T-FOUND-01..05` | Todo lo demás depende del catálogo, bindings, propuestas y seam seguro |
| 2 | Catálogo definitivo | `T-FOUND-01` | 307 tools, 0 huérfanos, ancla única |
| 3 | HOMI-D y exposición a THINK | `T-FOUND-03` + `08` | 193 WRITE con propuesta tipada; índice+bajo demanda |
| 4 | Contratos completos de WRITE | `T-FOUND-03`, `T-FOUND-05` | Ciclo G antes de habilitar dominios |
| 5 | Identity / Family / Households | `T-IDENTITY-01`, `T-HOUSEHOLDS-01` | Sin dependencias de dominio |
| 6 | Planner | `T-PLANNER-01` | Base de Home y de integraciones |
| 7 | Finance | `T-FINANCE-01` | Riesgo alto; tras Planner |
| 8 | Inventory | `T-INVENTORY-01` | Integra Planner y Finance |
| 9 | Assets | `T-ASSETS-01` | Integra Planner (doble capability) |
| 10 | HomeCloud | `T-HOMECLOUD-01` | Metadatos sin SEE |
| 11 | Messaging / HPlus | `T-MESSAGES-01`, `T-HPLUS-01` | Contenido no confiable; HPlus lectura |
| 12 | Presence / Notifications / Settings | `T-NOTIFICATIONS-01`, `T-SETTINGS-01` | Presencia queda BLOCKED por PD-02 |
| 13 | Integraciones cruzadas | `T-CROSS-01` | Requiere todos los dominios previos |
| 14 | Frontend y acceso definitivo | `T-FRONT-01` | Consume el catálogo final |
| 15 | E2E reales | `T-E2E-01` | Requiere runtime y proveedores |
| 16 | Autocorrección | `T-ACCEPT-01` | Re-ejecuta consistencia y regresiones |
| 17 | Aceptación técnica | `T-ACCEPT-01` | Veredicto de Actor A |

**Nota:** `home` se implementa con Planner (slice 6); no se omite ningún dominio autorizado. Las tareas exactas y sus dependencias están en `11_TASKS_AND_DEPENDENCIES.json` (21 tareas).

## 3. Archivos a modificar / crear

| Capa | Archivos |
|---|---|
| Catálogo | `backend/src/homi/v1/tool_catalog.json` (regenerado), `homi-orchestrator/catalog/*.json` (re-anclado), `backend/src/homi/v1/catalog.js` |
| Gateway | `backend/src/homi/generatedBindings.js` (nuevo/expandido), `v1/executor.js`, `v1/authority.js`, `v1/argumentValidator.js`, `controllers/homiV1.controller.js` |
| HOMI-D | `homi_tool_proposal.py` (familias), `homi_tool_write_execution.py` (allowlist por tool), `homi_tool_catalog.py`, `homi_tool_loop.py` (índice+bajo demanda) |
| BD | Sin migraciones nuevas salvo la del ledger ya creada; **no tocar RLS ni tablas de producto** |
| Frontend | `screens/homi/`, `components/homi/`, `services/homi/`, `src/voice/`, `navigation/HomeTabNavigator.tsx`, `navigation/types.ts`, `screens/MoreScreen.tsx` |
| Tests | `backend/tests/homi/*`, `homi-orchestrator/tests/support.py` (portar), `front/.../tests/homi*.test.js` |

## 4. Por familia de tool

1. **READ:** binding → endpoint canónico con bearer → proyección positiva → metadatos de truncamiento → DTO sin secretos. Sin confirmación; reintento solo en 5xx.
2. **WRITE R1:** preview → propuesta (familia tipada) → confirmación → re-validación → `X-Mutation-Id`/`Idempotency-Key` derivados de `proposal_id` → un dispatch → verificación → ledger.
3. **WRITE R2:** igual, más confirmación reforzada, advertise del efecto financiero/destructivo y `expected_version` obligatoria.
4. **Multi-operación** (`events.v1.mutate`, `participants.mutate`, `responsibilities.lifecycle`): **descomponer en tools tipadas por `action`**, nunca pasar `action` libre desde el modelo.

## 5. Errores y confirmaciones

- `error_mapping` por tool traduce el `code` del envelope canónico; 5xx → `provider_error_retryable` sin filtrar mensaje; 412 → `version_conflict` → nueva propuesta.
- Confirmaciones con TTL 15 min, hash de argumentos normalizados y expected_version (§06).

## 6. Resolución planificada de errores históricos

| Histórico | Resolución |
|---|---|
| 11 tests D fallidos | `T-FOUND-04`: actualizar anclas/enums al catálogo 307 sin relajar aserciones de autoridad |
| Suite D no autocontenida | Portar `support.py`, resolver `PY`, separar T31/STT, fixtures BD aisladas |
| Contratos de propuesta solo 5 | `T-FOUND-03`: 8 familias tipadas para 193 WRITE |
| Cobertura multirol | `T-E2E-01`: fixtures de coordinator/adult/adolescente/child/senior/guest, otro hogar, sesión expirada, flag off |
| Integración THINK real | Preflight `§13` + turno `infer_with_tools`; si DOWN → BLOCKED con evidencia |
| Dictado STT real | Preflight STT-only + guion T32 §12 por Actor A |
| HomeCloud/SEE | Metadatos implementados; píxeles BLOCKED hasta HOMI-B (PD-05) |
| Riesgos Finance | R1-a mitigado con hash propio; R1-b/c/d BLOCKED o condicionados (PD-03) |
| Rutas LAN en iPhone | `§13`: verificar LAN/tailnet real antes de QA |
| Divergencia frontends | Un solo proyecto autoritativo (PD-06) |

## 7. Stop conditions globales

1. Un tool sin servicio canónico real → fuera del catálogo y documentado; no se implementa adaptador inventado.
2. Un endpoint 410/inexistente → BLOCKED y documentado antes de continuar el slice.
3. Un test verde que se rompe → detener el slice siguiente hasta diagnosticar (AGENTS #24).
4. Un proveedor DOWN → reportar BLOCKED con evidencia; **nunca simular PASS**.
5. Una decisión de producto no resuelta → aplicar default seguro; no habilitar la tool.

## 8. Cómo se demuestra completitud

- `CONSISTENCY_REPORT.json` → 20/20 checks PASS.
- `03_CRUD_COVERAGE_MATRIX.md` → 350 filas con destino único; 307 tools con contrato.
- `11_TASKS_AND_DEPENDENCIES.json` → 21 tareas con dependencias válidas y criterio de terminado.
- `12_E2E_ACCEPTANCE_PLAN.md` → matriz por herramienta/dominio/rol/escenario.
- `git diff --check` limpio al cierre de la pasada 2.

**Gate L: IMPLEMENTATION PLAN EXHAUSTIVE — PASS.**
