# 01 — CURRENT AUDIT — HomePlus 18/11

**Base auditada:** `homeplus-integrado` @ `d8edd49236457ffe1ac66bb9e836ef4117ac980d`
**Rama:** `homi/full-integration-18-11` · **Worktree:** `C:\Users\thega\Desktop\HomePlus-worktrees\homi-full-integration-18-11`
**Modalidad:** auditoría estática read-only (sin ejecución runtime). Toda afirmación cita `archivo:línea`.
**Convención:** rutas relativas a `homeplus-integrado/`. `B/` = `backend/src/`, `S/` = `backend/src/services/`, `C/` = `backend/src/controllers/`, `M/` = `supabase/migrations/`, `F/` = `front/mi-front-limpio/`.

> Las secciones 1–8 son **evidencia confirmada** por lectura de código/SQL. Donde se marca **INFERENCIA** es deducción de contrato, no hecho observado. Ningún resultado de test se elevó a PASS en esta auditoría.

---

## 1. Arquitectura global

| Capa | Autoridad / evidencia |
|---|---|
| Monorepo | `package.json:1-76` (root privado, Node ≥24, 49 scripts, deps `@supabase/supabase-js`, `dotenv`, `node-fetch`, `uuid`). |
| Backend | Express 5 + Supabase + Prisma. Entrypoint `backend/index.js:38-130`. CORS: en producción sólo `CORS_ORIGIN` con `credentials:true` (`:42-59`); sin Origin = mobile/Expo (`:51-59`). Middlewares globales `requestContextMiddleware` → `errorEnvelopeMiddleware` → `express.json()` (`:66-70`). Puerto `PORT || 3000`, bind `0.0.0.0` (`:128-130`). Health `/health` (`:73-80`). |
| Routers montados | 21 prefijos en `backend/index.js:83-103`: `/api/auth`, `/api/invite-links`, join-requests, invite-links, `/api/households` (+ alias `/households`), `/api/invitations` (+ alias), `/api/users` (+ alias), `/api/people`, `/api/feature-flags`, `/api/planner`, `/api/inventory`, `/api/finance`, `/api/presence`, `/api/homecloud`, `/api/messages`, `/api/hplus`, `/api/assets`, `/api/push`. |
| Frontend | Dos proyectos. **Principal/QA = `front/mi-front-limpio`** (CI `.github/workflows/homeplus-quality.yml:29,38,61,67`; runner `tests/run.js:7` apunta a él; `docs/RUN_INTEGRATED_SNAPSHOT.md:9,13`; 599 archivos vs 480; Android + Maestro). `front/mi-front-expo-go` es copia histórica divergente (mismo `name` en package.json, App.tsx más antiguo, sin CI). |
| Database | 145 migraciones (`202606210001` → `20261118000000`). Todo en `public.`. **No existen esquemas `homi` ni `find`** (0 coincidencias de `create schema` / `homi.` / `find.`). |
| RLS / Storage / Realtime | RLS `for update to authenticated` (`M/202606210002_rls_auth.sql:95,131,171,214`). Storage: buckets privados `homecloud-originals`/`homecloud-previews` (`M/20260910000004_homecloud_storage_foundation_v1_1.sql:1,11`) y `avatars`. Realtime activo en inventory, presence, household_members, messaging, planner_tasks, hplus (`M/202610010001:3,7-9`, `M/202610080001:8-12`, etc.). |
| Feature flags | Un único flag: `planner.search_entry` (`B/constants/plannerFeatureFlags.js:3-12`), `defaultValue:false`, `client_visible`. SQL `check (flag_key in ('planner.search_entry'))` (`M/20260714010000_homeplus_g0_4_operation_rollout:58`). **No hay flags HOMI ni de módulos.** |
| Telemetría / auditoría / outbox | Catálogo CORE (7 eventos) + PLANNER (9). Sink `console` o noop (`B/config/telemetry.js:16-19`). `audit_events` inmutable (`prevent_audit_event_mutation`, G0.4:117) + RPC `record_audit_and_enqueue_outbox` (G0.4:189). `outbox_events` con lease 60 s, batch 20, `dedupe_key` y dead-letter (`B/services/outboxProcessor.service.js:9-10,91-93,46-50,66-82`). |
| Testing | Dispatcher `tests/run.js` (tabla `commands:12-740`, `suites:742-890`). Suite `quality` = typecheck, lint, syntax, migration uniqueness, core backend/frontend, g0.3, g0.4-contracts, runtime-smoke, db, coverage, secrets, CI syntax, whitespace (`:880-884`). CI corre `npm run quality` con `HOMEPLUS_TEST_REQUIRE_LOCAL_DB=1` tras `supabase start`. **Estado runtime no verificado en auditoría.** |
| Servicios externos | Expo Push real (`B/services/pushNotifications.service.js:5`). No hay evidencia de Anthropic/FCM/R2/AWS en código. |

### Autoridad de identidad (transversal)

`authFinalMiddleware` (`B/middleware/authFinalMiddleware.js:3-15`) → `getAuthenticatedUser` (`B/lib/auth.service.js:58-74`) → `req.user`, `req.accessToken`. **`getPlannerContext(req)`** (`S/planner.context.service.js:4-71`) es la autoridad canónica: persona por `auth_user_id`, `active_household_id`, membership `active`, devuelve `{client, person, household, membership, householdId, personId, membershipId, role, membershipStatus}`. Variantes `getPersonalScopeContext` (`:75-108`) y `getHouseholdScopeContext` (`:110-177`). 80+ consumidores. **El cliente nunca define actor ni household.**

### Error envelope

`createHttpError(status, message, code, details)` (`B/lib/httpErrors.js:1-7`); envelope `{error:{code,message,request_id,details?}}` (`:15-54`), 5xx sin filtrar mensaje real (`:34-39`), `X-Request-Id` del `requestContextMiddleware` (regex segura `^[A-Za-z0-9._:-]{1,128}$`, `:21-23`).

---

## 2. Estado de HOMI en el 18/11 — AUSENCIA FUNCIONAL CONFIRMADA

Búsqueda case-insensitive exhaustiva en ambos fronts, backend, tests, scripts, docs y package.json:

| Hallazgo | Evidencia | Naturaleza |
|---|---|---|
| Etiqueta canónica | `F/constants/productLanguage.ts:20` → `homi: 'Homie'`; congelada por `tests/visual_theme_contract.test.js:56-60` | Naming, **no funcionalidad** |
| Extension point sin consumidores | `F/services/messageActionSuggestions.ts:1-17` → `source:'homi'`, `noMessageActionSuggestions = () => []`, nadie lo importa | Stub |
| Utilería visual | `scripts/visual-module-names.cjs:5-6` (sólo lee `mi-front-limpio`) | Herramienta de renombrado |
| Decisión de diferir | `docs/ANTICIPATORY_UX_AUDIT.md:41,98-99,155,212,247` — AX-047/048 `DEFER`, "Homi no debe inventar intención… requiere Product Truth, explicabilidad y backend real" | Product Truth previa |
| Backend | **0 coincidencias** de homi en `backend/` | Confirmado |

**No existe**: ruta en ningún navigator, tile en "Más", pantalla, componente, servicio productivo, deeplink, dependencia npm ni import HOMI. Por tanto la integración es `BUILD` desde cero en el 18/11, apoyada en el código reutilizable del worktree `homi-t07` (ver 02).

---

## 3. Navegación y shell (autoridad CURRENT)

```
App.tsx:103-123  SafeAreaProvider → AppThemeProvider → AuthProvider → ExperienceProvider
                → HouseholdProvider → FeatureFlagsProvider → AppRefreshProvider
                → PlannerTaskRealtimeBridge → ThemedNavigation → AppNavigator
AppNavigator.tsx:158-184  getInitialPrivateRoute() desde authMe.navigation.next
AppNavigator.tsx:316-337  PrivateStack (sin ruta Homi)
ExperienceResolver.tsx:23-26  simple → SimpleShell | standard → StandardShell → HomeTabNavigator
HomeTabNavigator.tsx:197-203  5 tabs: Home | Family | QuickAction (abre sheet) | Planner | More
HomeTabNavigator.tsx:260-285  MoreStack: MoreScreen, Assets, HomeCloud, Inventory, Finance, Presence…
MoreScreen.tsx:15-53         tiles: Objetos, Archivos, Actividad(demo), Finanzas, Inventario
SimpleNavigator.tsx:16-42   SimpleHome/Family/Medication/Agenda/Calls/More/Settings/Sos/ModuleEntry
```

- Navbar flotante se oculta con teclado (`HomeTabNavigator.tsx:305-315,338`, `tabBarHideOnKeyboard:true` `:457`).
- `AppTopBar` **sólo en Home** en `mi-front-limpio` (`:101-106,428-445`); en expo-go siempre.
- Permisos: el front **no deriva capacidades del rol** (`F/services/plannerCapabilities.ts:17-20`); recibe proyección de `GET /api/planner/capabilities` y el backend re-verifica. Doble gate flag+capability con default deny (`F/services/planner/plannerSearchGate.ts:28-51`). Scope `accountId:householdId` (`F/context/FeatureFlagsContext.tsx:36-37,50`).
- Guía visual: `docs/agents/homeplus-screen-consistency-agent.md:1-34`; `AppScreen bottomInset="tab"` (`F/components/ui/AppScreen.tsx:31-38`); `AppPageHeader` (`MoreScreen.tsx:110-112`); targets 44 px (`F/constants/theme.ts:603-608`).
- Convención "Más": **sólo módulos con pantallas reales** (`docs/implementation/h042_3_appshell_topbar_navigation.md:107-116`). No agregar tab/sexto destino (`AGENTS.md:9`).

---

## 4. Inventario por dominio (resumen; detalle completo en `03_TOOL_CATALOG.json`)

| Dominio | Superficies confirmadas | Observaciones de autoría |
|---|---|---|
| **Identidad** | `POST /auth/register|login|refresh|logout`, `GET /auth/me`, `PATCH /users/me`, `GET/PATCH /people/me`, `PATCH /people/me/avatar`, `GET /people/me/households` | `PATCH /users/me` escribe `auth.users.user_metadata` vía service-role (`C/users.controller.js:91,142`) → **no exponer a LLM**. `me` repara persona legacy (`S/me.service.js:109`). |
| **Hogares** | create, set-active, finalize, invite-links create/revoke, join por token, join-requests list/approve/reject; invitaciones legacy = **410** | Roles finales `coordinator, adult, adolescent, child, senior, guest` (`B/constants/householdConstants.js:1`). Límite ≤5 hogares (`:4`). Coordinator requerido en HP/RLS. `finalize` y `set-active` cambian el workspace raíz →415. |
| **Familia** | `GET /households/:id/family`, `/members`, `/members/:id`, `/role-requests`; `PATCH /members/:id/role`, POST role-requests approve/reject/cancel | No hay grafo de relaciones familiares; FAMILIA = `household_members` + `household_role_change_requests` (`M/202607050001:9`). No existe `DELETE /members`. |
| **Home** | `GET /planner/summary`, `/attention`, `/activity` | Sólo lectura, `planner.view`, telemetría allowlisted. Ideales para HOMI. |
| **Planner** | ~120 operaciones: tareas V0 + V1 fulfillment, eventos V0/V1, metas/hitos, planes V1 + grafo, calendario, búsqueda, papelera, actividad, capacidades, responsabilidades, horarios, presets/revisiones, borradores, evidencia/auditoría | Idempotencia `X-Mutation-Id`+`Idempotency-Key` (`B/lib/mutationContracts.js:63,81`), `If-Match`/`expected_version` (`:114`) → 412 `version_conflict_v2` (`:139`). Replay V0 reserve/complete (`:153`) y V2 atómico (`:349`). Rutas fantasma 410: drafts trash/restore (`C/planner.drafts.controller.js:88-108`), invitaciones legacy. `unarchivePlan` inalcanzable por defecto (`goal.archive=false` para los 6 roles, `B/lib/plannerCapabilities.js:107…327`). `getTaskAuditHistory` no exige `planner.audit.view` (`C/planner.tasks.controller.js:493`) — gap a documentar. |
| **Finanzas** | cuentas (CRUD+archive+anchor+activity), categorías, expenses/incomes, installment purchase, transfers + trash/restore, transaction trash/restore/correct, refunds, balance-correction, movements/summary/trash/detalle, analysis, pools (10+ operaciones), category-pool-default, spending-limits, payments dues/series (create/update/cancel/skip/register/settle) | **Sin capabilities propias**; auth + `resolveFinanceContext` (`S/finance.context.service.js:75-198`). Regla PERSONAL/HOUSEHOLD reforzada: selectores de ownership del caller rechazados. Decimal textual exacto 4 dp + `BigInt`×10000 (`S/finance.account.service.js:13-16`, `S/finance.read.service.js:191-225`). Comisión de transferencia derivada, input prohibido (`S/finance.transfer.service.js:20-63`). Sin movimientos compensatorios ficticios. **Riesgos R1 (ver §6).** |
| **Inventario** | V2: capabilities/summary/integrations, catálogo, ubicaciones, productos + stock + lifecycle, lista de compras, lista→tarea, sesión de compra (start/update/pause/resume/cancel/finalize/finance-retry). V1 legacy: templates/items/stock/restock | V2 = HOUSEHOLD estricto, capabilities `inventory.view/use/manage/destroy` (`B/lib/inventoryCapabilities.js:10-23`). `start` = **intención** (no toca stock ni finanzas); `finalize` requiere `register_in_finance` explícito; gasto deduplicado por `finance_transaction_sources` (`M/20261020000002:2-10`). `dedupe_key` prohibido en lista (autoridad del servidor). |
| **Assets** | bienes + identidad/categoría/responsable/tendor/ubicación, perfil, lifecycle, archive/unarchive, trash/restore + historiales, categorías, Records CRUD + link/unlink/remove/restore, Care CRUD, integración Planner | Capabilities `manage ⇒ contribute ⇒ view` (`B/lib/assetsCapabilities.js:44-77`). Service-role con `household_id` forzado (`S/assets.service.js:410-422`). `Idempotency-Key` obligatorio en archive/trash/remove. Episodios append-only. N:M: quitar vínculo **no elimina** el archivo (AGENTS #46). |
| **HomeCloud** | capabilities, content get/access (URL firmada TTL 3600), folders, albums (N:M), memories + preferencias/favoritos, files, register/authorize/verify/finalize | 4 caps (`homecloud.view/contribute/organize/delete`) matriz en `B/lib/householdPermissions.js:61-92`. DTOs sin paths (`S/homecloudReadService.js:21-24`). URL firmada `createSignedUrl` (`S/homecloudStorageAccess.js:147`), TTL sin techo superior (`S/homecloudAccessTtl.js:5-17`). Preview `sharp` sólo image; **sin preview para video/audio** (`S/homecloudPreviewService.js:152-157`). No hay office viewer (download + expo-sharing). Sin purge/restore (sólo `trashed`). |
| **Mensajería** | conversations list/get, directs/ensure, messages list/send (text/task/attachment), read, reactions, attachments register/upload/verify/cancel/download, task actions | Sin capabilities `messaging.*`: membership activa + `messaging_can_access_conversation` (`M/202610070001:94-133`). Identidad derivada en RPC (`messaging_current_membership_id`, `:94-107`). Idempotencia `client_message_id` + `SELECT … FOR UPDATE` (`:70,271-274`). Download firmado 300 s (`S/messagingAttachments.service.js:116-118`). MH1=núcleo, M2=rich media. |
| **Feed** | **No existe backend.** `F/screens/feed/FeedFamiliarScreen.tsx:46-91,112-149` usa `MOCK_POSTS` + `useState`; `publishPost` y `toggleReaction` son estado local. Sin tabla, sin ruta, sin tests. | `EXCLUDED BY CONTRACT`: exponerlo sería inventar producto. Única integración real = preferencia booleana `feed` en `user_metadata`. |
| **Presencia** | `GET /presence/locations`, `PUT /presence/location` (sólo 2 rutas, `routes/presence.js:9-10`) | Consentimiento/grants/historial/lugares/geofences **existen en SQL sin API** (`M/20260904010000:39-116,324-411`). `off` borra coords. RLS `presence_locations_select_visible_only` (`:332-334`). Datos sensibles. |
| **Notificaciones** | `POST /push/devices`, `DELETE /push/devices/current`; envío saliente a Expo (`S/pushNotifications.service.js:75`) | **No hay bandeja/estados/acciones**. Preferencias = booleanos fijos en `user_metadata` (`C/users.controller.js:8`). |
| **Configuración** | `/auth/me`, `/people/me`, `/users/me`, capabilities, `/feature-flags`, members de hogar | Capabilities centralizadas en `B/lib/householdPermissions.js:7-119`. |

---

## 5. Contratos transversales detectados

| Contrato | Evidencia | Implicación para HOMI |
|---|---|---|
| Identidad derivada del token | `authFinalMiddleware.js:3-15`, `S/planner.context.service.js:4-71`, `S/finance.context.service.js:75-198` | El modelo **nunca** puede elegir actor/household. Los claims del cliente son validados, no autoridad (`B/homi/contextContract.js:171-247` en el worktree anterior). |
| Idempotencia | `B/lib/mutationContracts.js:10-137`; hash V2 `B/lib/plannerIdempotencyAdapter.js` | Todo WRITE HOMI debe generar `X-Mutation-Id`/`Idempotency-Key` estables derivados de `proposal_id`. |
| Concurrencia | `If-Match`/`expected_version` → 412 (`mutationContracts.js:114,139`); columnas `version` + triggers (`M/20260712000000`) | Las propuestas deben capturar `expected_version` y re-validar antes de ejecutar. |
| Errores | Envelope canónico con `request_id`; 5xx sin mensaje | `error_mapping` por tool debe traducir `code` (no texto). |
| Auditoría | `audit_events` inmutable + `outbox_events` | Cada escritura HOMI debe correlacionarse con `requestId/mutationId` del gateway. |

---

## 6. Riesgos R1 detectados (heredados del CURRENT, NO introducidos por HOMI)

| ID | Riesgo | Evidencia | Clasificación |
|---|---|---|---|
| R1-a | `createExpense`/`createIncome` **sin correlation id** de API | `S/finance.transaction.service.js:178-248` | Confirmado por código. Mitigación HOMI: *no exponer* como tool de escritura hasta que el orquestador generate y el backend acepte `X-Mutation-Id`+`Idempotency-Key`. Verificado: el backend **no los exige**, pero el envío de headers es inofensivo y HOMI los usará para su propio idempotency hash; se documenta como **condicionada**. |
| R1-b | Hash de transferencia fija `scopeType:PERSONAL` incluso en HOUSEHOLD | `S/finance.transfer.service.js:363-371` vs `S/finance.pool.service.js:218-230` | INFERENCIA (posible colisión entre contextos). No se ejecutó test de colisión. Tool de transferencia queda `CONFIRMATION_REQUIRED` y `BLOCKED` para ejecución autónoma. |
| R1-c | DTO de mutación Finanzas usa `Number(row.amount)` | `S/finance.transaction.service.js:163`, `...trash.service.js:95`, `...restore.service.js:99`, `...correction.service.js:50` | Riesgo de precisión en la **respuesta**, no en BD. Las tools de lectura usan `String(row.amount)` (`:384`). Se documenta; no se modifica lógica contable canónica. |
| R1-d | `registerPayment` sin `scopeFilters` en lectura intermedia | `S/finance.payment.service.js:1312-1320` | INFERENCIA; autoridad final en RPC. Herramienta condicionada. |
| R1-e | TTL de URL firmada sin techo | `S/homecloudAccessTtl.js:5-17` | No se exponen URLs permanentes; TTL controlado por HOMI con valor por defecto. |
| R1-f | Feed mock, Presence consent-only en DB, sin bandeja de notificaciones | §4 | `EXCLUDED BY CONTRACT` / `BLOCKED`. |

---

## 7. Gate B

**HOMEPLUS PRODUCT TRUTH RECONSTRUCTED — PASS (evidencia estática).**
No se afirmó comportamiento runtime. Las contradicciones detectadas (R1-a…f, rutas 410, capabilities inalcanzables) se registran y se absorben en la matriz de autoridad (04) y en el catálogo (03), sin inventar decisiones de producto.
