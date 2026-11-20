# 07 — HOMI-D WRITE LIFECYCLE CONTRACT — Pasada 1/2

**Punto crítico heredado:** el gateway tiene 20 WRITE en catálogo, pero HOMI-D solo tiene contratos de propuesta para **5** (`planner.tasks.create|update|complete|trash|restore`) y **1** ejecutable por el seam (`planner.tasks.create`). Esta pasada cierra el diseño para **las 193 WRITE del catálogo final**.

---

## 1. Ciclo uniforme

```
DISCOVER → INTENT → RESOLVE → VALIDATE → PREVIEW → CONFIRM/EDIT/CANCEL
        → REVALIDATE → EXECUTE → VERIFY → LEDGER → RESPOND
```

| Etapa | Dueño | Acción | Fallo |
|---|---|---|---|
| DISCOVER | gateway | Filtra tools por sesión + membership + capability + flag + estado | Tool no se ofrece; 403 si se invoca |
| INTENT | THINK (HOMI-A) | `ToolDecisionV1` (`extra=forbid`), 1 tool por turno (`MAX_TOOL_CALLS=1`) | `clarify` / rechazo por forma |
| RESOLVE | gateway | Referencias opacas → GET autorizado; 0=`NOT_FOUND`, >1=`AMBIGUOUS` | Candidatos compactos; nunca elección arbitraria |
| VALIDATE | D (forma) + gateway (autoridad) | D valida esquema; gateway re-valida args, contexto y permisos | 400 `invalid_arguments` / 403 |
| PREVIEW | D | Args normalizados + efecto esperado + `expected_version` + TTL | — |
| CONFIRM/EDIT/CANCEL | Usuario vía UI | `apply_proposal_action` **no ejecuta** en D | Edición cambia hash → confirmación vieja inválida |
| REVALIDATE | D + gateway | Re-deriva household del bearer, re-chequea capability y versión | 412 `version_conflict` → nueva propuesta |
| EXECUTE | D seam → gateway | **Un solo** dispatch al endpoint canónico fijo | Sin reintentos automáticos |
| VERIFY | D | Resultado contra servicio autoritativo (lectura de confianza) | `outcome_uncertain` |
| LEDGER | D | `execution_runs` + `execution_steps`, filas **antes** del write | Ver §6 |
| RESPOND | D → gateway → cliente | DTO acotado + metadatos honestos | Sin secretos ni contenido sensible |

## 2. Identidad de propuesta (G1)

```json
{
  "proposal_id": "uuid v4 generado por D",
  "tool_id": "string del catálogo final (307 posibles; 193 WRITE)",
  "tool_family": "planner.task | planner.event | planner.goal | finance.transaction | inventory.product | assets.record | ...",
  "args_normalized": { "...": "solo campos permitidos por el tool" },
  "normalized_args_hash": "sha256(args_normalized + tool_id + schema_version)",
  "actor_hash": "one-way (nunca el ID en claro)",
  "household_hash": "one-way (nunca el ID en claro)",
  "entity_ref": "referencia opaca resuelta en RESOLVE",
  "expected_version": "string (obligatoria en entidades existentes)",
  "risk_class": "R1_SAFE_WRITE | R2_CONFIRMED_WRITE",
  "confirmation_policy": "PREVIEW_THEN_CONFIRM | CONFIRM_REINFORCED",
  "created_at": "UTC ISO-8601",
  "expires_at": "created_at + 900 s",
  "status": "PROPOSED",
  "revision": 1,
  "schema_version": "1.0"
}
```

**Reglas de edición:** solo `EDITABLE_PROPOSAL_FIELDS` por familia; cualquier cambio incrementa `revision` y recalcula `normalized_args_hash`. **Reglas de cancelación:** `CANCELLED` es terminal; no reactiva ni ejecuta. **Estado posterior a ejecución:** `CONFIRMED → EXECUTING → SUCCEEDED | PARTIAL | FAILED`; timeout antes de commit → `FAILED` (sin efecto); timeout después de commit → `VERIFYING → VERIFIED | UNKNOWN` (nunca `SUCCEEDED` sin persistencia comprobada).

## 3. Paso de 5 → 193 contratos (G2)

**No se crea un ejecutor genérico.** Se define una **familia de contratos tipados por operación**, con validadores y builders de idempotencia propios. Cada familia comparte la máquina de propuesta pero no el payload:

| Familia | WRITEs | Contrato tipado | Especificidad |
|---|---:|---|---|
| `planner.task` | 21 | `PlannerTaskProposalV1` | título, checklist `{text,checked}`, `dueDate`+`dueTime`, `expected_version`; hereda 5 históricas |
| `planner.event` / `goal` / `milestone` / `plan` / `preset` / `draft` / `responsibility` / `schedule` | 31 | `Planner*ProposalV1` | fechas, lifecycle action, section-typed payload (sin JSON libre) |
| `finance.transaction` / `account` / `pool` / `payment` / `refund` / `installment` / `category` / `limit` | 40 | `Finance*ProposalV1` | `amount` textual 4 dp, `currency` ISO, `context` derivado, comisión prohibida, `expected_version` |
| `inventory.product` / `location` / `shopping` / `purchase` / `restock` | 34 | `Inventory*ProposalV1` | `delta` entero, `dedupe_key` servidor, `register_in_finance` (PD-01) |
| `assets.asset` / `record` / `care` / `category` | 26 | `Assets*ProposalV1` | perfil, N:M sin borrado de archivo, episodios append-only |
| `homecloud.metadata` / `album` / `memory` / `folder` | 7 | `HomeCloud*ProposalV1` | metadatos/cover/membership; **sin píxeles** |
| `messages.send` / `reaction` / `read` / `attachment` | 4 | `Messaging*ProposalV1` | `client_message_id` derivado de `proposal_id`; contenido = dato no confiable |
| `identity` / `households` / `settings` / `hplus` | 30 | `Simple*ProposalV1` | payload acotado, sin credenciales ni privilegios |

**Migración:** los 5 contratos históricos (`homi_tool_proposal.py:98-104`, `T12_EXECUTION_TOOL_IDS:159-165`) se convierten en la familia `planner.task`. El flag `T12_CONFIRM_EXECUTION_ENABLED=False` (`:141`) se sustituye por habilitación **por tool** en el catálogo anclado: una tool solo es proponible/ejecutable si aparece en el catálogo con contrato y shake validado. Nunca un booleano global.

## 4. Seguridad (G3)

1. **Doble validación:** D valida forma antes de proponer; el gateway valida autoridad **antes de proponer y otra vez antes de ejecutar** (`assertExecutionAuthority` en `executor.js:174`).
2. **Confirmación ligada a argumentos vigentes:** la firma `{actor_hash, household_hash, tool_id, normalized_args_hash, entity_ref, expected_version, expires_at}` se recalcula en REVALIDATE. Si cambió cualquier campo → 409 `stale_confirmation`; hay que proponer de nuevo.
3. **Sin salto de validaciones:** el modelo nunca elige endpoint, actor, hogar, capability ni versión. El binding es estático por `tool_id` (`generatedBindings.js`).
4. **El seam no sustituye a la propuesta:** corrección `T-FOUND-05` — exigir propuesta `CONFIRMED` y hash vigente antes de dispatch, además del secreto interno.
5. **Sin `execute_any_api_request`:** el URL está congelado en el catálogo validado; `executor.js` llama al mismo backend con el bearer original.

## 5. Concurrencia (G4)

| Situación | Comportamiento |
|---|---|
| Doble confirmación | Segunda llamada sobre propuesta no-`PROPOSED` → 409 `invalid_transition`; un solo dispatch |
| Retry del cliente | Mismo `proposal_id` + mismo hash → outcome previo (idempotencia); distinto hash → conflicto |
| Timeout antes de commit | `FAILED`, sin write; se puede proponer de nuevo |
| Timeout después de commit | `VERIFYING`; verificar contra servicio autoritativo; nunca reintentar write |
| Resultado tardío | Se registra pero no cambia un terminal ya emitido |
| Pérdida de conexión | Recovery **state-only** (`homi_tool_proposal.py:3573-3585`), nunca reintenta write |
| Cambio de household | `household_id` se re-deriva del token en cada etapa; propuesta queda inválida |
| Expiración | TTL 15 min → `EXPIRED` terminal; nueva propuesta |
| Conflicto de versión | 412 `version_conflict` → re-leer entidad y regenerar propuesta con `expected_version` vigente |

## 6. Ledger (G5)

Tablas (`supabase/migrations/20261119000000_homi_execution_ledger.sql`): `homi.execution_runs` y `homi.execution_steps`. **Sin tocar tablas de producto ni RLS.**

| Transición | Datos registrados |
|---|---|
| `PROPOSED` | `proposal_id`, `tool_id`, hashes de actor/hogar, `args_hash`, `expected_version`, `risk_class`, TTL |
| `CONFIRMED` | `confirmed_at`, revisión vigente, hash confirmado |
| `EXECUTING` | `execution_run_id`, índice de paso determinista, `mutation_id` generado |
| `SUCCEEDED` | `result_ref`, `persisted=true` **solo tras lectura de verificación** |
| `PARTIAL` | pasos completados/fallidos, compensaciones aplicadas |
| `FAILED` / `UNKNOWN` | código semántico (no texto 5xx), `retryable`, sin write duplicado |
| `EXPIRED` / `CANCELLED` | terminal, sin dispatch |

Claves: `homi-write-{proposal_id}`, `homi-write-{proposal_id}-op-{i}`, `homi-exec-{proposal_id}`. **No duplicar escrituras. No marcar SUCCESS sin resultado persistido comprobado.**

## 7. Contratos de ejecución por tool (F5 aplicado)

Cada una de las 193 WRITE en `04_TOOL_CATALOG_FINAL.json` declara: `execution.handler`, `execution.canonical_service`, `execution.idempotency`, `execution.concurrency`, `execution.ledger`, `execution.retries`, `side_effects`, `error_mapping` (400/401/403/404/409/412/413/415/422/5xx → código semántico), `confirmation_policy` y `test_cases` (14 casos para WRITE). El adaptador usa `http.method` + `http.path` del catálogo, nunca un valor del modelo.

## 8. Verificación de completitud

| Comprobación | Resultado |
|---|---|
| 193 WRITE con propuesta tipada (familia asignada) | Cubierto por `T-FOUND-03` |
| 193 WRITE con `confirmation_policy` | 193/193 (consistencia C09) |
| 193 WRITE con `canonical_service` e idempotencia | 193/193 (consistencia C12) |
| Ningún ejecutor genérico de JSON arbitrario | Diseño: bindings estáticos por `tool_id` |
| Sin reintentos automáticos de write | `retry_policy` en cada tool |
| Ledger con filas antes del write | `persist_compound_execution_start` previo al dispatch |

**Gate G: COMPLETE WRITE EXECUTION CONTRACT — PASS (diseño).** La implementación y su evidencia runtime pertenecen a la pasada 2.
