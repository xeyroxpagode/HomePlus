# 12 — E2E ACCEPTANCE PLAN — Pasada 1/2

**Entorno:** Supabase local aislado del worktree (`:56221` REST / `:56222` DB), backend `:3100`, HOMI-D `:8001`, Metro `:8081`. Cuenta QA local; **sin producción**.

> Convención: `AUTOMATED PASS` = prueba ejecutada; `E2E PASS` = cliente→gateway→servicio→BD con persistencia verificada; `BLOCKED` = proveedor no disponible; `NEEDS DEVICE QA` = Actor A.

## 1. Estructura de la matriz

Cada una de las **307 tools** hereda `test_cases` de `04_TOOL_CATALOG_FINAL.json`:
- READ (8 casos): `happy_path`, `invalid_input`, `capability_denied`, `other_household`, `session_expired`, `empty_result`, `truncation_metadata`, `no_side_effects`.
- WRITE (14 casos): los anteriores aplicables más `preview_shows_exact_args`, `confirmation_binding`, `stale_confirmation_rejected`, `duplicate_submission_idempotent`, `version_conflict_412`, `provider_error_no_double_write`, `persistence_verified`, `ledger_written`, `compensation_not_fabricated`.

**Regla:** un HTTP 200 **no** es prueba de WRITE. Toda escritura se verifica con una lectura posterior contra el servicio canónico y con la fila del ledger.

## 2. Matriz por dominio

| Dominio | Tools | Escenarios E2E prioritarios | Persistencia |
|---|---:|---|---|
| identity | 5 | sesión derivada, perfil, hogares, capabilities; claims forjados → 403 | lectura de `me` |
| households | 12 | family hub enmascarado para no-coordinador; invitaciones; otro hogar → 404 | lectura de members |
| home | 3 | summary con `partial_errors` honestos; sin efectos | — |
| planner | 96 | crear→leer→actualizar→completar→trash→restore; fulfillment V1; milestones; presets; 412 | `planner.tasks.get` / milestone get |
| finance | 62 | scopes PERSONAL/HOUSEHOLD; montos textuales; expenses/incomes; pools; pagos; categorías; cuotas | `finance.transaction.get` / account activity |
| inventory | 54 | producto crear→ajustar→archive→restore; lista→tarea; compra start/pause/resume; retry Finance | `inventory.products.get` / purchases.get |
| assets | 39 | bien crear→identidad→responsable→archive/unarchive; record/care lifecycle; N:M sin borrar archivo | `assets.get` / records.get |
| homecloud | 23 | metadatos, carpetas, álbumes N:M, portada, favorito; sin píxeles | `homecloud.content.get` |
| messages | 9 | conversaciones, envío con confirmación, reacciones, adjuntos (bloqueados) | `messages.messages.list` |
| notifications | 1 | preferencias desde `me` | — |
| hplus | 2 | summary/ledger | — |
| settings | 1 | feature flags | — |

## 3. Matriz por rol (fixtures reales)

| Rol | Lecturas | WRITE | Caso negativo esperado |
|---|---|---|---|
| coordinator | todas | todas salvo BLOCKED | admin de hogar solo UI (PD-04) |
| adult | todas salvo admin | todas salvo `inventory.destroy` | — |
| adolescent | todas salvo búsqueda restringida | Planner/Inventory/Assets/HomeCloud | `planner.search` guest=false |
| child | lecturas | **ninguna WRITE** | 403 `*_forbidden` sin efectos |
| senior | todas | igual que adult | — |
| guest | lecturas limitadas | **ninguna WRITE** | 403; mensajes direct solo participante |

**Escenarios transversales obligatorios:** otro hogar → 404 sin existence leak; membership `suspended`/`pending` → 403; sesión expirada → 401; sin hogar activo → 403; capability limitada → tool no ofrecida **y** rechazada; cambio de hogar durante propuesta → confirmación inválida; feature flag off → tool no ofrecida.

## 4. Escenarios de conversación completa

| # | Intención | Tools | Resultado |
|---:|---|---|---|
| 1 | «¿Qué tengo mañana?» | `home.summary.get`, `planner.calendar.get` | 2 lecturas, mismo hogar |
| 2 | «Creá la tarea X para mañana» | `planner.tasks.create` | preview → confirm → 201 → lectura de vuelta |
| 3 | «Cambiá el vencimiento al jueves» | `planner.tasks.update` | `expected_version`; 412 si cambió |
| 4 | «Agregá leche a la lista» | `inventory.shopping-list.add` | confirm; dedupe por servidor |
| 5 | «Marcá la tarea como hecha» | `planner.tasks.complete` | CONFIRM×2; auditoría |
| 6 | «¿Cuánto gastamos este mes?» | `finance.summary.get{context:'HOUSEHOLD',period}` | montos textuales |
| 7 | «Registrá un gasto de 12.50» | `finance.expenses.create` | confirm reforzada; persistencia |
| 8 | «Dale de baja el bien X» | `assets.lifecycle.set` | doble capability; episodio append-only |
| 9 | «¿Qué archivos guardé?» | `homecloud.files.list` | metadatos; sin SEE |
| 10 | «Mostrame mis conversaciones» | `messages.conversations.list` | contenido = dato no confiable |
| 11 | «No, mejor hacelo para mañana» | edición de propuesta | hash cambia → nueva confirmación |
| 12 | «Confirmá» sobre propuesta vieja | atajo de confirmación D | sin THINK; expirada → EXPIRED |
| 13 | Dictado → borrador → envío | `/voice/transcript` + `text/turn` | STT-only; **BLOCKED** si STT down |
| 14 | Compra con gasto | `inventory.purchases.finalize` | **BLOCKED** por PD-01 |
| 15 | Ubicación de un miembro | `presence.locations.list` | **BLOCKED** por PD-02 |

## 5. Recorridos compuestos

| Recorrido | Verificación | Estado |
|---|---|---|
| Planner → Calendario | mismos filtros de hogar y período | Implementable |
| Inventario → Planner | tarea con `origin_*`, no compra | Implementable |
| Assets → Planner | doble capability verificada en servidor | Implementable |
| Inventario → Finanzas | solo intención; sin gasto | Condicionado PD-01 |
| Mensaje → Tarea | RLS bypass con admin client | **BLOCKED** hasta corrección |

## 6. Criterios de BLOCKED (sin simulación)

- **THINK DOWN:** `/text/turn` no completa inferencia → `BLOCKED` con respuesta del health; se reporta, no se simula.
- **STT DOWN:** `/voice/transcript` sin transcripción real → el composer sigue funcionando por texto.
- **SEE no garantizado:** `homecloud.content.access`, `homecloud.content.analyze`, `messages.attachments.download` → `BLOCKED`; metadatos sí.
- **QA físico iPhone:** 15 pasos T32 §12 → `NEEDS DEVICE QA` (Actor A).

## 7. Regresiones y cierre

`npm run quality` (typecheck, lint, syntax, migraciones, core, g0.3, g0.4, runtime-smoke, db, coverage, secrets, CI, whitespace) + `pytest` V1 + contratos front + `CONSISTENCY_REPORT.json` + `git diff --check`.

**Gate L3/E2E: PLAN PREPARADO.** La ejecución real pertenece a la pasada 2; ningún resultado de esta pasada se eleva a E2E PASS de tools nuevas.
