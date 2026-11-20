# 02 — HOMI RECONCILIATION — HOMI CURRENT → HomePlus 18/11

**Fuentes:** `C:\Homi\orchestrator` (HOMI-D) · `C:\Users\thega\Desktop\HomePlus-worktrees\homi-t07` (gateway T07 + front) · handoffs vigentes `VEREDICTO_FINAL.md`, `t32/T32_VOICE_SIMPLE_HANDOFF.md`.
**Baseline recuperable:** `C:\Users\thega\AppData\Local\Temp\opencode\homi-full-integration-baseline-20261119-015527` (365 archivos, 3.803.695 bytes, `MANIFEST.csv` con SHA256). `homi-t07` **no modificado**.

> Decisiones de producto vigentes (evidencia, no inferencia):
> - `T31 TURN TALKING: CANCELLED BY PRODUCT DECISION` (Actor A, 2026-11-18). No se reabre.
> - Voz V1 = `MANUAL DICTATION → STT → EDITABLE TRANSCRIPT → MANUAL TEXT SEND` (`t32/T32_VOICE_SIMPLE_HANDOFF.md:9-15,46-58`).
> - La aceptación física en iPhone pertenece a Actor A (`VEREDICTO_FINAL.md:75-90`; T32 §12). No se falsifica como PASS.

---

## 1. Inventario de componentes HOMI CURRENT

### 1.1 HOMI-D (orquestador Python)

| Componente | Función | Evidencia |
|---|---|---|
| `app.py` | `GET /health`, `/v1/attachments/*`, `/v1/voice/transcript` (STT-only), `/v1/voice/transcribe` (T31 legacy), **`POST /invoke`** (entrada semántica real), `/v1/voice/*` control (T31, no montado en gateway) | `app.py:401-412,441-533,732-814,817-1123,1160-1911` |
| `homi_tool_catalog.py` | 17 contratos READ (8 Planner + 9 T24), anclas `PLANNER_READ_TOOLS_SHA256` / `HOMI_TOOLS_V2_SHA256`, commit `1260442…` / `913e783…`, proyección al modelo sóLO 3 claves | `:53-60,70-86,563-585,708-766`; `catalog/homi-tools.v2.json:4` |
| `homi_tool_contract.py` | `ToolDecisionV1` (5 campos, `extra=forbid`), campos prohibidos al modelo (`actor_id`, `household_id`, `tool_call_id`, `authorization`…), `precheck_tool_arguments` | `:81-89,164-296,490-575` |
| `homi_tool_normalize.py` | Proyección positiva por tool, caps, `strip_internal_keys`, límite 16 KB, metadatos de truncamiento honestos | `:9-18,77-120,2101-2214` |
| `homi_tool_loop.py` (6.993 líneas) | Autoridad de decisión: `MAX_TOOL_CALLS=1`, 1 tool/turn, sin loop/paralelo/recursive, bearer nunca a Node A; atajo de confirmación **antes** de THINK; persistencia del execution start **antes** del dispatch; un solo write; outcomes inciertos sin segundo write | `:20-21,4884-4891,5048-5069,5056-5519,5242-5276,5429-5482,6949-7251` |
| `homi_tool_proposal.py` | 5 WRITE (`planner.tasks.create|update|complete|trash|restore`), TTL 15 min, `apply_proposal_action` (confirm/cancel **no ejecuta**), máquina `CONFIRMED→EXECUTING→SUCCEEDED|FAILED`, recovery **state-only, nunca reintenta write** | `:88-114,3133-3274,3283-3319,3573-3735` |
| `homi_tool_write_execution.py` | Seam `/api/homi/internal/tools/{tool_id}/execute`, header `X-Homi-Internal-Write`, bearer original, **una llamada sin reintentos**, mapa 400/401/403/404/412/422, `retryable = status>=500` | `:73-113,423-505,508-671,915-981` |
| `homi_tool_execution_ledger.py` + `homi_db.py` | Único dueño del SQL del schema `homi`: `execution_runs`, `execution_steps`; idempotencia `homi-write-{proposal_id}`, `homi-exec-{proposal_id}`; identidad ofuscada one-way; filas **antes** del write | `ledger:1-6,129-150,369-527,529-708,710-759,802-819`; `homi_db.py:1-19,107-193` |
| `homi_context_builder.py` | actor/household/session **sólo desde `request.context`**; del cliente acepta pistas no autoritativas (timezone, surface); `project_for_think` excluye secretos y advierte que IDs no son autoridad | `:142-321,104-139,324-361` |
| `homi_tool_t12_targets.py` | Resolución exacta de título sobre READ de confianza; 0 o >1 matches → `clarify` (nunca elección arbitraria); checklist `{text,checked}`; `dueTime` requiere `dueDate` | `:65-71,109-118,206-254,410-459,514-664` |
| `homi_t14_entity.py` / `homi_t14_temporal.py` | Resolución de entidad (exact → alias → normalizado → fuzzy 85/margen 5) y lenguaje temporal | `homi_t14_entity.py:13-45,47-134`; importado en `homi_tool_loop.py:168` |

### 1.2 Gateway T07 (backend anterior)

| Superficie | Evidencia | Estado |
|---|---|---|
| `POST /api/homi/text/turn` | `routes/homiText.js:19-21`, `homiText.controller.js:179` | Activo; `proposal_action` confirm/cancel como campo separado (`:47,70-85,166-172`); identidad derivada del bearer (`:180`). |
| `POST /api/homi/voice/transcript` (STT-only) | `routes/homiVoice.js:19-22,35`, `homiVoice.controller.js:215` | Activo; sin `conversation_id`/`turn_id`; flags read-only. |
| `/api/homi/tools/:toolId/invoke` | `routes/homi.js:19-26`, `homi.controller.js:25,111` | Activo; acepta claims `actor_id`/`household_id` **validados** contra contexto. |
| `/api/homi/internal/tools/:toolId/execute` | `routes/homiInternal.js:44-77`, `homiInternal.controller.js:37,192` | Activo; header de secreto + bearer; 5 WRITE allowlist. |
| `/api/homi/attachments/*` | `routes/homiAttachments.js:19-23` | Activo. |
| Registro: **26 definiciones** = 8 READ Planner + 9 READ T24 + 5 WRITE Planner + 4 WRITE T24 (metadata sin binding) | `homi/defaultRegistry.js:30-46`, `homi/tools/*.js`, `homiRuntime/toolBindings.js:66-73` | 17 bindings ejecutables (sólo READ).WRITE genérico rechazado por gate (`toolExecutor.js:229-236`). |
| Handlers → **servicios directos**, no HTTP | `homiRuntime/tools/plannerReadHandlers.js:18-22,69-89,146-269` | Clave para portabilidad: los mismos servicios existen en el 18/11. |
| Derivación de identidad | `homi/contextResolver.js:4-20,46-61,94-169`, `homi/contextContract.js:19-25,146-247` | Claims del cliente = afirmaciones validadas, nunca autoridad. |

### 1.3 Frontend HOMI anterior

| Capa | Evidencia | Reutilización |
|---|---|---|
| `screens/homi/HomiScreen.tsx:3-10` + `components/homi/HomiSurface.tsx:112-143,398-572` | Chat, composer, propuestas, 4 canales | Adaptar: desacoplar demo `runPlannerRead` (`:601-660`) y UI `JSON.stringify` de propuestas (`:833-841`). |
| `components/homi/HomiComposer.tsx:41-65`, `HomiMessageList.tsx`, `HomiTaskCard.tsx`, `HomiEmptyState.tsx`, `HomiThinkingRow.tsx`, `homiVisual.ts` | Presentación pura, props tipadas | **Reutilizables** (si el DTO de tareas se conserva). |
| Voz V1: `createHomiVoiceTransport.ts:35-37` (factory siempre manual), `expoManualDictationTransport.ts:57-261`, `homiDictation.ts:55-148`, `homiMultipart.ts` | STT-only, `playAnswer()` no-op, sin VAD/TTS | **Reutilizables tal cual**. |
| `services/homi/homiClient.ts:40-93`, `homiAttachments.ts:52-99,334-356` | Exigen `actorId`/`householdId` del cliente (el gateway los ignora) | **Adaptar**: eliminar como requisito. |
| Legado T31: `expoTurnVoiceTransport.ts`, `expoStreamVoiceTransport.ts`, `livekitVoiceTransport.ts`, `turnTaking.ts`, `homiLiveKit.ts`, funciones T31 en `homiAttachments.ts:392-681` | Rutas de control no montadas | **NO copiar**. Cancelado por Actor A. |
| Acceso actual: botón QA temporal `screens/home/HomePlannerSections.tsx:355-362` → `navigation.navigate('Homi')`; modal en `AppNavigator.tsx:22,314`; tipo en `types.ts:20` | No es arquitectura visual autoritativa | **Reemplazar** por acceso en hub "Más" (§5). |

---

## 2. Delta HOMI → HomePlus 18/11

| Componente | HOMI CURRENT | HomePlus 18/11 CURRENT | GAP | TARGET ADAPTATION |
|---|---|---|---|---|
| **Identidad** | D exige `X-Household-Id`/`X-Actor-Id` (`app.py:419-438`); gateway los deriva del bearer | `getPlannerContext` deriva persona/hogar/membership del JWT (`S/planner.context.service.js:4-71`) | Ninguno en autoridad; sí en transporte | Conservar derivación server-side. El nuevo gateway envía headers a D desde el token. El cliente **nunca** los envía como autoridad. |
| **Rutas Planner** | Handlers llaman servicios directos (`plannerReadHandlers.js:146-269`); escritura vía `/api/planner/tasks/*` hardcodeado en `homi_tool_proposal.py:472-506` | Los mismos servicios existen (`S/planner.tasks.service.js`, `events`, `goals`, …) pero con más operaciones V1/V2 y headers obligatorios | Nombres de servicio estables; nuevos headers y versiones | Reutilizar handlers con adjustment mínimo. Reemplazar las 4 rutas hardcodeadas por un **registro de bindings por tool_id** que llame a servicios canónicos y construya `X-Mutation-Id`/`Idempotency-Key`/`If-Match`. |
| **DTOs Planner** | `due_date`, `checklist {text,checked}`, `trashed_at`, `requires_verification` (`homi_tool_t12_targets.py:410-459,667-723`) | DTOs CURRENT con `version`, `origin_*`, fulfillment V1, assignmentKind | Posibles renombres de campo | Re-validar el DTO real en runtime con fixtures; no asumir compatibilidad de un handoff PASS histórico. Normalización positiva debe actualizarse si cambian nombres. |
| **Catálogo** | 17 READ + 5 WRITE (Planner), 4 WRITE T24 metadata; T24 gate default-off | ~190 operaciones en 13 dominios | **GAP principal** | Extender catálogo a todos los dominios autorizables (03). Anclas SHA deben recalcularse sobre el catálogo nuevo: las actuales apuntan a commits `1260442…`/`913e783…` y fallarían cerrado. |
| **Autorización** | capabilities Planner en `B/lib/plannerCapabilities.js`; Finance sin caps; T24 con `inventoryCapabilities` | Igual más `assetsCapabilities`, `homecloudCapabilities`, `householdPermissions`, `finance.context` | Capabilities nuevas por dominio | Cada tool declara `required_capabilities` y `household_scope`; verificación **en el servidor** en cada ejecución, aunque la tool esté oculta al modelo. |
| **Autoridad duplicada** | D precheck (`homi_tool_contract.py:490-575`) + gateway `validateToolArguments` (`homiRuntime/argumentValidator.js`) | No existe HOMI en el 18/11 | Dos validadores | Consolidar: D valida forma; **el gateway del 18/11 es autoridad final** de argumentos, contexto y permisos, igual que en el contrato anterior (`:496-499`). |
| **Esquema `homi`** | DDL **no versionado**; `HOMI_DB_SCHEMA=homi`, rol `homi_runtime` sin grants a `public.planner_*` (`homi_db.py:8-19`); `migrations/` vacío | Todo en `public.`; 145 migraciones versionadas | DDL ausente | Crear **una migración nueva no destructiva** (`CREATE SCHEMA IF NOT EXISTS homi; CREATE TABLE IF NOT EXISTS …`) en el 18/11. Indispensable para el ledger autorizado. Reversión segura documentada (07). Sin tocar tablas de producto. |
| **Frontend** | `mi-front-limpio` anterior con HOMI + acceso QA temporal | `mi-front-limpio` 18/11 sin HOMI; convención "Más" = módulos con pantalla real | Toda la superficie | Portar componentes/servicios/voz; integrar acceso como **tile en "Más"** con doble gate flag+capability; sin sexto tab, sin botón flotante, sin nuevo deeplink. |
| **Voz** | T32 STT-only operativo | Sin voz HOMI; `expo-audio` ya es dependencia de HomeCloud | Transporte | Portar factory manual + composer editable. No portar T31/LiveKit/VAD/TTS. Aceptación física sigue pendiente (Actor A). |
| **SEE/HOMI-B** | SEE integrado en D para adjuntos; VEREDICTO_FINAL lo marca READY | Sin SEE HOMI | Proveedor externo | Tools dependientes de procesamiento visual real quedan `BLOCKED` si HOMI-B no responde en runtime; **no inventar resultados**. Las tools de metadatos funcionan igual. |
| **Testing** | Suites HOMI en D (pytest) y gateway/front (node --test) | 49 scripts root, `quality` suite; sin HOMI | Sin tests HOMI | Portar tests focales + crear tests de contrato para los bindings nuevos. No reutilizar PASS histórico como compatibilidad 18/11. |
| **Config/runtime** | `.env.homi`, T07 `:3002`, D `:8000`, A `:18011`, C `:8010/8012`, Supabase `:56221/56222`, Metro `:8081` | Backend 18/11 usa `PORT || 3000`, Supabase local estándar | Puertos y URLs | Configuración local reproducible en 07; sin exponer backend públicamente. |

---

## 3. Componentes: reutilizar / adaptar / no copiar

| Clasificación | Componentes |
|---|---|
| **REUTILIZAR (núcleo de autoridad)** | `homi_tool_loop.py`, `homi_tool_contract.py`, `homi_tool_normalize.py`, `homi_tool_proposal.py`, `homi_tool_execution_ledger.py`, `homi_tool_write_execution.py`, `homi_tool_client.py`, `homi_context_builder.py`, `homi_tool_compound_result_contract.py`, `homi_t14_entity.py`, `homi_t14_temporal.py`, `homi_db.py` |
| **ADAPTAR** | `app.py` (sólo `/invoke`, health y STT; retirar voice/attachments/LiveKit/T31), `homi_tool_catalog.py` + `catalog/*.json` (re-anclaje), `homi_tool_t12_targets.py` (DTOs), `homi_tool_proposal.py:472-506` (bindings), front `HomiSurface.tsx`, `homiClient.ts`, `homiAttachments.ts`, navegación |
| **NO COPIAR** | `homi_t31_turns.py`, `bridge_c.py`, `homi_voice_turn.py`/`homi_audio.py`/`homi_hear.py`/`homi_voice_store.py`, `homi_speak.py`, transports T31 y LiveKit, control-plane `/resolve/*` legacy, rutas `/api/homi/voice/turn*`, `/api/homi/voice/turn/begin|interrupt|delivery|livekit/token` |
| **NO DUPLICAR** | Clientes API, autoridades de identidad, servicios de dominio: el 18/11 ya tiene los canónicos. No crear un segundo `getPlannerContext`, ni otro registro de capabilities, ni otro executor de tools. |

---

## 4. Validación pendiente antes de implementar (Gate H)

1. Recalcular anclas SHA del catálogo nuevo (las actuales fallarían cerrado por diseño).
2. Confirmar que los métodos de servicio esperados por los handlers existen en el 18/11 con la misma firma (auditado estáticamente: sí para Planner READ; verificar en runtime con fixtures).
3. Aprovisionar esquema `homi` y rol con grants mínimos en la BD de pruebas aislada.
4. Verificar disponibilidad real de HOMI-A (THINK) y HOMI-C (STT) en esta sesión; HOMI-B (SEE) es incierto.
5. Conciliar los dos validadores de argumentos (D vs gateway) con una autoridad única declarada.

**Gate C — HOMI REUSE AND COMPATIBILITY VERIFIED: PASS (estático).** Las compatibilidades no probadas se trasladan a la matriz de autoridad y al plan de pruebas; no se asume que un handoff PASS histórico garantiza compatibilidad con el 18/11.
