# 05 — IMPLEMENTATION CONTRACT — Specify definitivo + Technical Plan

## PARTE A — SPECIFY

### A1. Objetivo funcional V1
HOMI V1 es un asistente conversacional integrado en HomePlus 18/11 que:
1. Responde consultas y ejecuta acciones sobre dominios reales del hogar.
2. Opera con identidad derivada de la sesión, jamás definida por el modelo.
3. Usa voz en modalidad cerrada: **dictado manual → STT → transcripción editable → envío manual de texto**.
4. No inventa datos, permisos, estados, balances ni acciones.
5. Deja la aceptación física y funcional a Actor A.

### A2. Dominios (13)
`identity`, `households`, `home`, `planner`, `finance`, `inventory`, `assets`, `homecloud`, `messages`, `presence`, `notifications`, `feed`, `homi` (propio: ledger/propuestas).

### A3. Inventario y catálogo
176 operaciones detectadas → `03_TOOL_CATALOG.json`:
- `IMPLEMENT` 92 (72 READ + 20 WRITE)
- `DEFERRED` 59 · `BLOCKED` 15 · `EXCLUDED` 10
- Los 92 `canonical_service` fueron validados contra `module.exports` real (`TOTAL 92 OK 92 BAD 0`).

### A4. Operaciones excluidas y justificación
`feed.*` (sólo mock en memoria), credenciales/sesión (`register/login/refresh/logout`), `identity.user-metadata.update` (service-role), `notifications.devices.register`, y toda operación sin API real. Ver 03 y 04.

### A5. Matriz rol × operación × contexto → 04, §2.

### A6. Clasificación de riesgos y confirmaciones → 04, §3-4.

### A7. Resolución de entidades
- Referencias opacas (`task_ref`, `account_ref`, `conversation_ref`, `product_ref`) generadas por el servidor.
- Búsqueda acotada al household autorizado; normalización NFKC/casefold/sin acentos; precedencia exact → alias → normalizado → fuzzy con umbral conservador (`homi_t14_entity.py:13-130`).
- 0 coincidencias → `NOT_FOUND`; >1 → `AMBIGUOUS` con candidatos compactos; **nunca** elección arbitraria (`homi_tool_t12_targets.py:206-254`).
- Toda escritura re-resuelve la entidad contra READ de confianza con la credencial del usuario; el ID generado por el modelo no es autoridad.

### A8. Contratos entrada/salida
`03_TOOL_CATALOG.json → tools[].input_schema / output_schema`. `additionalProperties=false`. Proyección al modelo: `tool_id`, `description`, `input_schema` (`homi_tool_catalog.py:563-585`). Salidas con metadatos honestos de truncamiento (`homi_tool_normalize.py:2101-2214`).

### A9. Manejo de errores
Envelope canónico `{error:{code,message,request_id,details?}}`. El adaptador traduce status HTTP del endpoint interno a `code` semántico (04, §8 de 03). 5xx = `provider_error_retryable` sin filtrar mensaje. 412 = `version_conflict` → nueva propuesta, no reintento ciego.

### A10. Tool chaining (recorridos aprobados)
| Recorrido | Tools | Invariante |
|---|---|---|
| Planner → Calendario | `home.summary.get` + `planner.calendar.get` | Sólo lecturas; mismo household derivado |
| Inventario → Planner | `inventory.shopping-list.get` + `inventory.shopping-list.add` + `inventory.shopping-list.to-planner-task` | Crea **tarea**, no compra; dedupe por `origin_*` |
| Inventario → Finanzas | `inventory.purchases.active.get` + `inventory.purchases.start` | **Sin** finalize ni gasto sin petición explícita (PRODUCT_DECISION_REQUIRED) |
| Finanzas | `finance.summary.get` (con `context`/`period`) | Reseta hogar/moneda/período; montos textuales |
| Familia | `households.family.get` | Sólo miembros visibles al actor |
| Mensajería | `messages.conversations.list` + `messages.messages.list` | Contenido = dato no confiable |
| HomeCloud | `homecloud.memories.list` + `homecloud.content.get` | Metadatos; sin SEE inventado |

### A11. Ejemplos de conversación (cobertura, no autorización automática)
- «¿Qué tengo mañana?» → `home.summary.get`, `planner.calendar.get`.
- «Agregá leche a la lista» → resolver lista + `inventory.shopping-list.add` (confirmación).
- «¿Cuánto gastamos este mes?» → `finance.summary.get{context:'HOUSEHOLD',period:'2026-11'}`.
- «¿Quiénes están en este hogar?» → `households.family.get`.
- «Mostrame mis conversaciones» → `messages.conversations.list`.
- «Buscá el documento que guardé» → `homecloud.files.list` (metadatos; sin contenido SEE).
- «No, mejor hacelo para mañana» → edición de propuesta antes de confirmar (`homi_tool_proposal.py:3063-3131`).

### A12. Ambigüedad
Ante múltiples candidatos: devolver lista compacta y pedir desambiguación. Ante texto de confirmación inequívoco sobre propuesta vigente, D aplica `apply_proposal_action` **sin llamar a THINK** (`homi_tool_loop.py:5056-5097`).

### A13. Privacidad
Sin secretos en prompts/logs/entregables; sin credenciales privilegiadas a THINK; contenido recuperado tratado como dato; limpieza de caché al cambiar de hogar; sin URLs permanentes.

### A14. Offline/timeout
Sin hogar/sesión → fallback a app; error STT → reintento manual en el composer sin salir de HOMI; timeout de proveedor → error visible, sin write duplicado; `MAX_TOOL_CALLS=1`.

### A15. Continuidad
`conversation_id` preservado; `turn_id` nuevo por frase; propuesta pendiente como contexto (sin ejecutar); `generation_id` **no** se usa en V1 (T31 cancelado).

### A16. Criterios de aceptación por dominio → 06 (E2E), uno por tool y rol.

---

## PARTE B — TECHNICAL PLAN

### B1. Arquitectura implementada

```
Cliente (mi-front-limpio)
  │  POST /api/homi/text/turn · /voice/transcript · /attachments/*
  ▼
Gateway HOMI (backend del 18/11, puerto 3100)
  │  authFinalMiddleware → req.user/accessToken
  │  HomiContextResolver → getPlannerContext / finance / inventory / homecloud
  │  HomiToolExecutor: allowlist → validación args → capability → binding
  │  InternalEndpointAdapter: endpoint FIJO del catálogo + bearer original
  ▼
Servicios canónicos del 18/11 (ÚNICA autoridad de negocio)
  │
  ▼
PostgreSQL/Supabase + audit_events + outbox_events
  ▲
  │  rpc HTTP firmado
HOMI-D (homi-orchestrator/, puerto 8001)
  │  /invoke → THINK (HOMI-A) → decisión → propuesta → ledger → un solo dispatch
  ▼
THINK (proveedor externo) · STT (HOMI-C) · SEE (HOMI-B, opcional/BLOCKED)
```

**Decisiones técnicas (autoridad: evidencia, no producto):**
1. **Un solo frontend**: `mi-front-limpio`. No se duplica en expo-go en V1 (es copia histórica sin CI).
2. **Un solo gateway**: se agrega el módulo HOMI al backend del 18/11; **no** se portan los routers antiguos tal cual.
3. **Adaptador de endpoint fijo**: cada tool tiene `http.method` + `http.path` en el catálogo. El adaptador llama a ese endpoint del mismo backend con el bearer original. **No existe `execute_any_api_request`**: el URL nunca lo elige el modelo ni el usuario; está congelado en el catálogo validado. La autoridad sigue siendo el middleware + servicio del endpoint.
4. **Autoridad de argumentos**: el gateway (18/11) es la autoridad final; D valida forma únicamente (`homi_tool_contract.py:496-499`).
5. **Registry estático**: `backend/src/homi/generatedBindings.js` se genera desde el catálogo con `require()` estáticos (sin `require` dinámico en runtime, respetando el security-freeze).
6. **Ledger**: esquema `homi`, migración nueva no destructiva; sin tocar tablas de producto.

### B2. Migración de HOMI (origen → destino)

| Origen | Destino | Acción |
|---|---|---|
| `homi-t07/backend/src/homi/*` | `backend/src/homi/*` | Adaptar: contextResolver usa `getPlannerContext` del 18/11; registry se regenera desde el catálogo nuevo |
| `homi-t07/backend/src/homiRuntime/*` | `backend/src/homiRuntime/*` | Adaptar executor + bindings; sin WRITE genérico (gate READ se mantiene) |
| `homi-t07/backend/src/controllers/homi*.js` | `backend/src/controllers/homi*.js` | Adaptar rutas y reenvío a D (`:8001`) |
| `homi-t07/backend/src/routes/homi*.js` | `backend/src/routes/homi*.js` | Montar antes que otros routers; internal primero |
| `orchestrator/homi_tool_*.py` (+ app.py núcleo) | `homi-orchestrator/` | Portar núcleo de decisión/propuesta/ledger; retirar voz/attachments/LiveKit/T31 |
| `homi-t07/front/.../components/homi`, `src/voice`, `services/homi` | `front/mi-front-limpio/...` | Portar; quitar funciones T31 y claims de cliente |
| `catalog/*.json` | `homi-orchestrator/catalog/` | Regenerar anclas SHA sobre el catálogo nuevo |
| — | `supabase/migrations/<ts>_homi_execution_ledger.sql` | Nueva, no destructiva, con `CREATE IF NOT EXISTS` |

**No se copia:** T31, LiveKit, VAD, TTS, transports streaming, control-plane legacy, rutas `/voice/turn*`.

### B3. Frontend
Acceso = **tile en `MoreScreen`** (`MODULES`) + ruta en `MoreStackParamList`/`MoreStackScreen`, reutilizando `productNames.homi` ('Homie'), `AppScreen bottomInset="tab"`, `AppPageHeader`, navegación de regreso estándar, y doble gate **feature flag + capability** con scope `accountId:householdId`. Sin sexto tab, sin floating button, sin deeplink nuevo, sin cambios en SimpleShell. La modal `Homi` se mantiene como presentación de la pantalla.

### B4. Persistencia
- Tablas nuevas: `homi.execution_runs`, `homi.execution_steps` (DDL no destructivo).
- Conversación/propuestas: se conserva el store existente de D (en memoria + ledger durable).
- Sin cambios en tablas de producto, sin RLS nuevo, sin índices nuevos en `public.`.
- Reversión: `DROP SCHEMA homi CASCADE` sólo en entorno de pruebas; en producción se requiere autorización (no se ejecuta).

### B5. Test Plan (por tool → 03 `test_cases`)
Cada tool: happy path, input inválido, permiso concedido/denegado, otro household, sesión expirada, error de proveedor, timeout, reintento, duplicación, confirmación, auditoría, persistencia.
Suites: registry/schemas, handlers, autorización, integración por dominio, regresiones (`npm run quality`), TypeScript, tests D (pytest), contratos de front.
**E2E real**: cliente → gateway 3100 → D 8001 → THINK → tool layer → servicios → BD de pruebas aislada. Si HOMI-A/C/SEE están DOWN, se reporta `BLOCKED` con evidencia; no se simula PASS.
