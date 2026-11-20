# 04 — AUTHORITY MATRIX — Seguridad, permisos, riesgos y confirmaciones

**Principio inmutable:** *El modelo propone. HOMI-D orquesta. HomePlus autoriza y ejecuta.*
**Regla de oro:** ocultar una tool al modelo **no reemplaza** la verificación de permisos en el servidor. Toda ejecución vuelve a verificar identidad, hogar, capability, propiedad, versión y estado.

---

## 1. Identidad y frontera de autoridad

| Elemento | Autoridad | Evidencia |
|---|---|---|
| Sesión | `authFinalMiddleware` → `req.user`/`req.accessToken` | `backend/src/middleware/authFinalMiddleware.js:3-15` |
| Persona | `people.auth_user_id = req.user.id` | `backend/src/lib/auth.service.js:58-76` |
| Hogar activo | `people.active_household_id` + membership `status='active'` | `backend/src/services/planner.context.service.js:4-71` |
| Finance | `resolveFinanceContext` rechaza selectores de propiedad del llamador | `backend/src/services/finance.context.service.js:75-198` |
| Inventory V2 | `getHouseholdRequestContext`, HOUSEHOLD estricto | `backend/src/services/core/householdRequestContext.service.js:11-54` |
| Assets | service-role con `household_id` **forzado** en la query | `backend/src/services/assets.service.js:410-422` |
| HomeCloud | `getHomeCloudContext`, DTO sin paths | `backend/src/services/homecloud.context.service.js:20-58`; `homecloudReadService.js:21-24` |
| Mensajería | RPC deriva `sender_membership_id`; RLS `messaging_can_access_conversation` | `M/202610070001:94-133,247-322,377-379` |
| Propuestas/ledger | HOMI-D dueño de `proposal_id`, `tool_call_id`, `execution_run` | `homi_tool_proposal.py:22-24`; `homi_tool_execution_ledger.py:1-6` |

**Prohibido al modelo (rechazo en validación):** `actor_id`, `household_id`, `membership_id`, `role`, `authorization`, `tool_call_id`, `catalog_digest`, `request_id`, `trace_id` (`homi_tool_contract.py:81-89,200-205`). Los claims que el cliente envía a los endpoints internos son **afirmaciones validadas**, nunca autoridad (`backend/src/homi/contextContract.js:171-247`).

---

## 2. Matriz rol × operación × contexto (resumen)

Roles finales: `coordinator, adult, adolescent, child, senior, guest` (`backend/src/constants/householdConstants.js:1`). Capacidades **no se derivan del rol en el front** (`front/mi-front-limpio/services/plannerCapabilities.ts:17-20`): vienen de `GET /api/planner/capabilities` y el backend re-verifica.

| Familia de tools | coordinator | adult | adolescent | child | senior | guest | Contexto | Capability backend |
|---|---|---|---|---|---|---|---|---|
| `home.*` (summary/attention/activity) | S | S | S | S | S | S | HOUSEHOLD | `planner.view` |
| `planner.*` READ | S | S | S | S | S | S* | HOUSEHOLD | `planner.view` (*search además `planner.search`, guest=false) |
| `planner.tasks.create` | S | S | S | — | S | — | HOUSEHOLD | `task.create_household` |
| `planner.tasks.update/complete` | S | S | S | — | S | — | HOUSEHOLD | `*_own`/`*_any` por propiedad/asignación |
| `planner.tasks.trash/restore` | S | S | S | — | S | — | HOUSEHOLD | `task.restore` |
| `identity.*` READ | S | S | S | S | S | S | PERSONAL / HH | — |
| `households.*` READ | S | S | S | S* | S | S* | HOUSEHOLD | membership activa (*no-coordinador ve datos limitados/enmascarados) |
| `finance.*` READ | S | S | S | S | S | S | PERSONAL o HH | **sin caps**; `resolveFinanceContext` |
| `finance.expenses.create` / `incomes.create` | S | S | S | S | S | S | PERSONAL o HH | sin caps; **CONFIRM** |
| `inventory.*` READ | S | S | S | S | S | S | HOUSEHOLD | `inventory.view` |
| `inventory.*` WRITE (productos, lista, sesión) | S | S | S | — | S | — | HOUSEHOLD | `inventory.manage` / `inventory.use` |
| `assets.*` READ | S | S | S | S | S | S | HOUSEHOLD | `assets.view` |
| `homecloud.*` READ (metadatos) | S | S | S | S | S | S | HOUSEHOLD | `homecloud.view` |
| `messages.*` READ / `send` | S | S | S | S | S | S* | HOUSEHOLD | membership + acceso a conversación (*direct requiere participante) |

Las celdas son la proyección por defecto; los overrides viven en `households.config.permissions` (`backend/src/lib/householdPermissions.js:7-119`) y en la matriz de capabilities del dominio. **Ante duda, denegar.**

### Escenarios obligatorios de prueba (J3)

| Escenario | Resultado esperado |
|---|---|
| Usuario autorizado | Ejecución y persistencia verificadas contra servicio autoritativo |
| Rol restringido (child/guest en WRITE) | 403 `planner_forbidden` / `inventory_forbidden` sin efectos |
| Miembro de otro hogar | 404 `not_found_or_not_authorized` (no filtrar existence leak) |
| Sin hogar activo | 403 `no_active_household` |
| Sesión expirada | 401 `not_authenticated` desde `authFinalMiddleware` |
| Usuario revocado / membership `pending` | 403 `not_active_household_member` |
| Capabilities limitadas | Tool **no se ofrece** al modelo **y** se rechaza en servidor |
| Cambio de hogar durante operación | El `household_id` se re-deriva del token en cada paso; confirmación vinculada al hogar original queda inválida |

---

## 3. Clasificación de riesgo y confirmación por herramienta

| Clase | Definición | Política | Ejemplos |
|---|---|---|---|
| `R0_READ` | Sólo lectura, sin efectos, DTO acotado | Sin confirmación; paginación y límites | `home.summary.get`, `planner.tasks.list`, `finance.movements.list`, `homecloud.memories.list` |
| `R1_SAFE_WRITE` | Mutación acotada, revertible, con idempotencia fuerte | Preview + ejecución tras propuesta aceptada | `planner.*` WRITE, `inventory.shopping-list.add` |
| `R2_CONFIRMED_WRITE` | Efecto real en finanzas/mensajes/estado de negocio | Confirmación obligatoria, botón explícito, TTL 15 min | `finance.expenses.create`, `messages.messages.send`, `planner.tasks.complete` |
| `BLOCKED` | Sin autoridad/infraestructura/proveedor | No se ofrece; no se ejecuta; se reporta | `finance.transfers.create` (R1-b), `finance.balance.correction`, `presence.*`, SEE sin HOMI-B, `inventory.purchases.finalize` sin intención explícita |
| `EXCLUDED` | No existe en el producto o está prohibido | Nunca se ofrece | `feed.*` (mock), `identity.login/logout`, `notifications.devices.register`, `identity.user-metadata.update` |
| `DEFERRED` | Operación real fuera de HOMI V1 | Documentada en 03, no implementada | Administración de hogares, presets/publish, correcciones financieras complejas |
| `PRODUCT_DECISION_REQUIRED` | Requiere Actor A | Aislada; se continúa el resto | `inventory.purchases.finalize` con `register_in_finance=true` sin pedido explícito |

**Detalle ejecutable por tool:** `03_TOOL_CATALOG.json` → `tools[].risk_class`, `confirmation_policy`, `idempotency_policy` (92/92 con `canonical_service` validado contra exports reales).

---

## 4. Confirmaciones — contrato vinculante

Una confirmación es válida **sólo** si coincide exactamente:

```
{ actor_hash, household_hash, tool_id, normalized_args_hash, entity_ref, expected_version, expires_at }
```

- `actor_hash`/`household_hash`: hashes one-way en el ledger (`homi_tool_execution_ledger.py:115-126`).
- `normalized_args_hash`: sobre argumentos **normalizados**; cambiar un argumento invalida la confirmación anterior.
- `expected_version`: obligatoria en entidades existentes; 412 `version_conflict` si cambió.
- `expires_at`: TTL 15 min (`homi_tool_proposal.py:88-92`); vencida → `EXPIRED`, hay que proponer de nuevo.
- `confirm` y `cancel` **no ejecutan nada** por sí solos en D (`homi_tool_proposal.py:3162-3165`); la ejecución es un paso posterior con `begin_proposal_execution` → persistencia del inicio → **un solo** dispatch.

---

## 5. Idempotencia, ledger y concurrencia

| Mecanismo | Contrato | Evidencia |
|---|---|---|
| Headers de mutación | `X-Mutation-Id` + `Idempotency-Key` | `backend/src/lib/mutationContracts.js:63,81` |
| Versión optimista | `If-Match`/`expected_version` → 412 `version_conflict_v2` | `mutationContracts.js:114,139` |
| Claves HOMI | `homi-write-{proposal_id}`, `homi-write-{proposal_id}-op-{i}`, `homi-exec-{proposal_id}` | `homi_tool_execution_ledger.py:129-150` |
| Persistencia antes del dispatch | `persist_compound_execution_start` ANTES del write | `homi_tool_loop.py:5242-5267` |
| Un solo write | Sin reintentos automáticos; outcomes inciertos se registran | `homi_tool_write_execution.py:423-437`; `homi_tool_loop.py:5429-5482` |
| Fallo pre/post commit | No asumir rollback; verificar contra servicio autoritativo | `homi_tool_execution_ledger.py:17-21,529-708` |
| Replay | Mismo payload → outcome previo; payload distinto → conflicto | `homi_tool_execution_ledger.py:413-430` |
| Recovery | State-only, **nunca** reintenta el write | `homi_tool_proposal.py:3573-3585` |

---

## 6. Controles especiales por dominio

### Finanzas
- PERSONAL y HOUSEHOLD separados; `scopeFilters` por servicio (`finance.account.service.js:310-322` y análogos).
- Moneda `/^[A-Z]{3}$/`; importe decimal textual hasta 4 decimales; agregados `BigInt`×10000.
- Propiedad de cuenta verificada (`getAccountForMutation:353-370`, `resolveAccountForTransaction:568-623`).
- Comisión de transferencia **derivada**, input prohibido (`finance.transfer.service.js:20-63`).
- Sin movimientos compensatorios ficticios; correcciones = nueva versión / anchor con anti-backdating.
- DTO de mutación con `Number(amount)` es riesgo connaissance (R1-c documentado); **no se modifica** lógica contable canónica.

### Inventario
- V1 (legacy) separado de V2 (autoritativo).
- `start` = intención; `finalize` requiere `register_in_finance` explícito y total; gasto se crea en paso aparte y se deduplica.
- `dedupe_key` lo genera el servidor; el modelo no lo envía.
- Lista→Planner crea una **tarea**, no una compra.
- Reposición V1 sólo agrega a la lista, nunca genera compra/gasto.

### Mensajería y contenido
- Todo mensaje, nota, documento, nombre de archivo y transcripción es **dato no confiable**: nunca se siguen órdenes found dentro de ellos.
- Enviar a terceros exige confirmación (tool `messages.messages.send`, R2).
- Adjuntos: URL firmada de 300 s, sin contenido persistente en el ledger.

### HomeCloud / SEE
- Sin URLs permanentes; TTL controlado (default 3600 s).
- DTO sin paths; limpieza de contexto al cambiar de hogar.
- Herramientas que requieren píxeles (`homecloud.content.access`, `homecloud.content.analyze`, `messages.attachments.download`) quedan `BLOCKED` si HOMI-B no responde en runtime. **No se inventa contenido.**

### Presencia
- Sin seguimiento silencioso. `presence.locations.list` y `presence.my-location.update` quedan `BLOCKED`: el consentimiento vigente no es verificable por el modelo.

---

## 7. Tool discovery (exposición al modelo)

Se ofrecen **sólo** tools para las que el actor tiene: sesión válida + membership activa + household derivado + capability real + módulo disponible + feature flag (si aplica) + estado de entidad compatible + contexto conversacional pertinente.

La proyección al modelo es mínima (`homi_tool_catalog.py:563-585`): `tool_id`, `description`, `input_schema`. **`MAX_TOOL_CALLS=1`** (`homi_tool_loop.py:20-21`): un tool por turno, sin paralelos, sin llamadas recursivas, sin endpoints elegidos por el modelo.

> La ocultación es UX. La autoridad está en `getPlannerContext` / `resolveFinanceContext` / `getHouseholdRequestContext` / `assertCapability` y en RLS, re-ejecutada en cada tool call.

---

## 8. Gate E

**SECURITY AND EXECUTION AUTHORITY APPROVED BY EVIDENCE — PASS.** Los riesgos R1-a…f del CURRENT se aislaron (BLOCKED/DEFERRED) o se mitigaron con idempotencia gestionada por D (expenses/incomes). No se crearon permisos, reglas financieras ni capacidades nuevas.
