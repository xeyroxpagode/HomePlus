# 06 — AUTHORITY AND CONFIRMATION MATRIX — Pasada 1/2

**Principio inmutable:** *El modelo propone. HOMI-D orquesta. HomePlus autoriza y ejecuta.*
**Regla de oro:** ocultar una tool al modelo **no reemplaza** la verificación server-side. Cada ejecución vuelve a verificar identidad, hogar, capability, propiedad, versión y estado.

---

## 1. Frontera de autoridad

| Elemento | Autoridad | Evidencia |
|---|---|---|
| Sesión | `authFinalMiddleware` → `req.user`/`req.accessToken` | `backend/src/middleware/authFinalMiddleware.js:3-15` |
| Persona / hogar / membership | `getPlannerContext(req)` | `backend/src/services/planner.context.service.js:4-71` |
| Finance | `resolveFinanceContext` rechaza selectores de propiedad del llamador | `backend/src/services/finance.context.service.js:75-198` |
| Inventory V2 | `getHouseholdRequestContext`, HOUSEHOLD estricto | `backend/src/services/core/householdRequestContext.service.js:11-54` |
| Assets | service-role con `household_id` **forzado** en la query | `backend/src/services/assets.service.js:410-422` |
| HomeCloud | `getHomeCloudContext`, DTO sin paths | `backend/src/services/homecloud.context.service.js:20-58` |
| Mensajería | RPC deriva `sender_membership_id`; RLS `messaging_can_access_conversation` | `MIG/202610070001:94-133` |
| Propuestas/ledger | HOMI-D es dueño de `proposal_id`, `tool_call_id`, `execution_run` | `homi_tool_proposal.py:22-24` |

**Campos prohibidos al modelo** (rechazo en validación D y gateway): `actor_id`, `household_id`, `membership_id`, `role`, `authorization`, `tool_call_id`, `catalog_digest`, `request_id`, `trace_id`. Los claims `actor_id`/`household_id` que el cliente envía al `invoke` son **afirmaciones validadas** (403 si difieren), nunca autoridad (`homiV1.controller.js:100-109`).

## 2. Roles y estados reales de la rama

- Roles finales: `coordinator, adult, adolescent, child, senior, guest` (`backend/src/constants/householdConstants.js:1`).
- Estados de membership: `pending, active, suspended, finalized` (ídem, línea 2) — **nota:** el handoff anterior solo listaba tres; `suspended` existe en la rama.
- Solicitudes de rol: `pending, approved, rejected, canceled` (ídem, línea 3).
- Máximo 5 hogares por persona (ídem, línea 4); timezone por defecto `America/Argentina/Buenos_Aires`.
- Las capacidades **no se derivan del rol en el front** (`plannerCapabilities.ts:17-20`); vienen del backend y se re-verifican.

## 3. Capabilities definidas en SQL (autoridad canónica)

| Dominio | Keys | Evidencia |
|---|---|---|
| Hogar (base) | `invite_members`, `approve_members`, `remove_members`, `manage_roles`, `assign_coordinator`, `edit_config` | `MIG/202606240001:49-104` |
| HomeCloud | `homecloud.view`, `homecloud.contribute`, `homecloud.organize`, `homecloud.delete` | `MIG/20260917000000:24-110` |
| Assets | `assets.view`, `assets.contribute`, `assets.manage` | `MIG/20261020000000:29-140` |
| Planner tareas | `planner.view`, `task.create_household`, `task.complete_assigned/unassigned/any`, `task.verify`, `task.edit_own/any`, `task.cancel_own/any`, `task.restore`, `goal.restore`, `planner.templates.use/manage` | `MIG/20260722010000:14,58-59`; `MIG/20260918000001:54-71` |
| Planner planes | `goal.archive` (**false para los 6 roles**), `goal.restore` | `MIG/20260722040000:355,411-412` |
| Planner eventos | `event.create_household/personal`, `event.edit_own/any`, `event.cancel_own/any`, `event.manage_participants` | `MIG/20260722030000:323,356-362` |
| Inventory | `inventory.view`, `inventory.use`, `inventory.manage`, `inventory.destroy` | `MIG/20261019000001:271,280-283` |
| Finance | **sin capabilities propias**; `resolveFinanceContext` | `finance.context.service.js:75-198` |

**P1 detectado:** `archive_planner_task_v1`/`unarchive_planner_task_v1` exigen `task.archive`, pero la función SQL no contiene ese key y cae en `else false` (`MIG/20260914000002:196,300` vs `MIG/20260918000001:54-70`). No hay backfill. Verificar en `plannerCapabilities.js` antes de habilitar las tools `planner.tasks.archive/unarchive` (tarea `T-FOUND-02`). **No se inventa el permiso.**

## 4. Matriz rol × contexto × acción (proyección por defecto)

| Familia | coord | adult | adol | child | senior | guest | Contexto | Capability |
|---|---|---|---|---|---|---|---|---|
| `home.*`, `planner.*` READ | S | S | S | S | S | S* | HH | `planner.view` (*search: `planner.search`, guest=false) |
| `planner.tasks.create` | S | S | S | — | S | — | HH | `task.create_household` |
| `planner.tasks.update/complete` | S | S | S | — | S | — | HH | `*_own`/`*_any` por propiedad/asignación |
| `planner.tasks.fulfillment.verify` | S | S | S | — | S | — | HH | **nunca el propio cumplimentador** |
| `finance.*` READ | S | S | S | S | S | S | PERSONAL o HH | sin caps; `resolveFinanceContext` |
| `finance.expenses.create` / `incomes.create` | S | S | S | S | S | S | PERSONAL o HH | **CONFIRM×2** |
| `finance.payments.*` WRITE | S | S | — | — | S | — | PERSONAL o HH | CONFIRM×2; algunas PRODUCT_DECISION |
| `inventory.*` READ | S | S | S | S | S | S | HH | `inventory.view` |
| `inventory.*` WRITE | S | S | S | — | S | — | HH | `inventory.manage`/`inventory.use` |
| `inventory.products.permanent-delete` | S | — | — | — | — | — | HH | `inventory.destroy` (BLOCKED_AUTHORITY) |
| `assets.*` READ | S | S | S | S | S | S | HH | `assets.view` |
| `assets.*` WRITE | S | S | S | — | S | — | HH | `assets.contribute`/`assets.manage` |
| `homecloud.*` metadatos | S | S | S | S | S | S | HH | `homecloud.view` |
| `homecloud.albums.*` WRITE | S | S | S | S | S | — | HH | `homecloud.organize` |
| `messages.*` READ / `send` | S | S | S | S | S | S* | HH | membership + acceso (*direct requiere participante) |

Ante duda: **denegar**. Los overrides viven en `households.config.permissions` (`backend/src/lib/householdPermissions.js:7-119`).

## 5. Clasificación de riesgo y confirmación (307 tools)

| Clase | Tools | Política | Ejemplos |
|---|---:|---|---|
| `R0_READ` | 114 | `NONE`: sin confirmación; paginación y límites | `home.summary.get`, `assets.records.list`, `finance.summary.get` |
| `R1_SAFE_WRITE` | 98 | `PREVIEW_THEN_CONFIRM`: propuesta con args normalizados + hash + TTL 15 min | `planner.tasks.create`, `assets.name.update`, `homecloud.albums.add-item` |
| `R2_CONFIRMED_WRITE` | 95 | `CONFIRM_REINFORCED`: botón explícito, advertise del efecto, TTL, re-validación | `finance.expenses.create`, `messages.messages.send`, `*.trash`, `*.cancel` |

**No se usa una política única.** La clase se decide por efecto (financiero, destructivo, privilegios, cambio de estado de negocio), no por módulo. El detalle ejecutable está en `04_TOOL_CATALOG_FINAL.json → tools[].risk_class / confirmation_policy`.

## 6. Contrato vinculante de confirmación

Una confirmación es válida **solo** si coincide exactamente con:

```
{ actor_hash, household_hash, tool_id, normalized_args_hash, entity_ref, expected_version, expires_at }
```

- `actor_hash`/`household_hash`: hashes one-way en el ledger.
- `normalized_args_hash`: sobre argumentos **normalizados**; cambiar un argumento invalida la confirmación anterior.
- `expected_version`: obligatoria en entidades existentes; 412 `version_conflict`.
- `expires_at`: TTL 15 min (`homi_tool_proposal.py:88-92`).
- `confirm`/`cancel` **no ejecutan** por sí solos en D; la ejecución es un paso posterior con persistencia del inicio y un solo dispatch.

## 7. Controles especiales

### Finanzas
- PERSONAL/HOUSEHOLD separados; `scopeFilters` por servicio.
- Moneda `/^[A-Z]{3}$/`; importe decimal textual hasta 4 dp; agregados `BigInt`×10000.
- Comisión de transferencia **derivada**, input prohibido (`finance.transfer.service.js:20-63`).
- Sin movimientos compensatorios ficticios; correcciones = nueva versión/anchor con anti-backdating.
- R1-a: `createExpense`/`createIncome` no exigen correlation id canónico; HOMI genera `X-Mutation-Id`/`Idempotency-Key` propios (envío inofensivo, documentado como condicionado).
- R1-b/c/d: ver `01_SOURCE_BASELINE_AND_DELTA.md` y `05_...md`.

### Inventario
- V1 legacy separado de V2 (autoritativo).
- `start` = intención; `finalize` requiere `register_in_finance` explícito y gasto deduplicado por `finance_transaction_sources`.
- `dedupe_key` lo genera el servidor; el modelo no lo envía.
- Lista→Planner crea **tarea**, no compra.
- Borrado permanente exige `inventory.destroy` (no expuesto por defecto).

### Mensajería y contenido
- Todo mensaje, nombre de archivo y transcripción es **dato no confiable**: nunca se siguen instrucciones dentro de ellos.
- Enviar a terceros exige confirmación reforzada.
- Adjuntos: URL firmada 300 s, sin contenido en el ledger.
- `messages.actions.link-task` usa admin client para leer `planner_tasks` (RLS bypass): **no exponer** hasta corregir.

### HomeCloud / SEE
- Sin URLs permanentes; TTL controlado (default 3600 s).
- DTO sin paths; limpieza de contexto al cambiar de hogar.
- Las tools de metadatos funcionan sin SEE; las de píxeles quedan `BLOCKED_DEPENDENCY`.

### Presencia
- Sin seguimiento silencioso. Consentimiento no verificable por el modelo → `BLOCKED_AUTHORITY` (PD-02).

## 8. Pruebas obligatorias de autoridad

| Escenario | Resultado esperado |
|---|---|
| Usuario autorizado | Ejecución y persistencia verificadas contra servicio autoritativo |
| Rol restringido (child/guest en WRITE) | 403 `*_forbidden` sin efectos |
| Miembro de otro hogar | 404 `not_found_or_not_authorized` (sin existence leak) |
| Membership `suspended`/`pending`/revocado | 403 `not_active_household_member` |
| Sin hogar activo | 403 `no_active_household` |
| Sesión expirada | 401 `not_authenticated` |
| Capability limitada | Tool **no se ofrece** al modelo **y** se rechaza en servidor |
| Cambio de hogar durante operación | `household_id` se re-deriva del token; confirmación vinculada al hogar original queda inválida |

## 9. Hallazgo abierto del seam (P1)

`POST /api/homi/v1/internal/tools/:toolId/execute` acepta **cualquier** tool con `risk_class !== 'R0_READ'` con solo `proposal_id` (`homiV1.controller.js:186-200`). No verifica que la propuesta esté `CONFIRMED` ni que el hash de argumentos vigente coincida. El executor re-chequea authority (`:174`) pero no el estado de la propuesta. **Corrección planificada en `T-FOUND-05`**. Hasta entonces, el secreto interno es el único gate y no se considera suficiente para la pasada 2.

**Gate I: PASS con PD pendientes (PD-01 … PD-04) y P1 del seam planificado.**
