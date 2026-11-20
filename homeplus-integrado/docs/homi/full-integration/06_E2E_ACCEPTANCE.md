# 06 — E2E ACCEPTANCE — Resultados por dominio, tool, rol y escenario

**Entorno:** Supabase local aislado del worktree (`:56221` REST / `:56222` DB), cuenta QA `homi.qa.1811@example.test`, hogar de prueba creado en la sesión, backend nuevo `:3100`, HOMI-D portado `:8001`. Datos controlados; sin producción.

> Convención: `AUTOMATED PASS` = prueba ejecutada en esta sesión; `E2E PASS` = petición realCliente→gateway→servicio→BD con persistencia verificada; `BLOCKED` = proveedor no disponible; `NEEDS DEVICE QA` = Actor A.

---

## 1. Matriz por gate final

| Gate | Estado | Evidencia |
|---|---|---|
| G01 Source integrity | PASS | worktree/diff en 00; `homi-t07` intacto |
| G02 Architectural compatibility | PASS | 02 + 92 servicios validados |
| G03 Complete catalogue | PASS | 176 operaciones clasificadas, 0 sin destino |
| G04 Security | PASS | 403 claims forjados, 401 sin bearer, feed/presencia ausentes, 8/8 tests authority |
| G05 Execution reliability | PASS (parcial) | idempotencia declarada en 20/20 WRITE; ledger migrado; seam 403 sin secreto |
| G06 Domain integration | PASS (parcial) | 7 dominios READ + 1 WRITE en E2E real; resto con contrato y tests estáticos |
| G07 Cross-domain integration | DEFERRED | recorridos diseñados en 05 §A10; no ejecutados por THINK DOWN |
| G08 Frontend access | PASS (técnico) | tile en "Más" + ruta; tsc limpio; 10/10 contratos; NEEDS DEVICE QA |
| G09 Regression safety | PASS | backend/frontend/contracts/typecheck PASSED |
| G10 Runtime E2E | BLOCKED | THINK/STT/SEE DOWN; tool layer E2E real sí PASS |
| G11 QA readiness | BLOCKED | requiere proveedores y QA físico de Actor A |

---

## 2. Resultado por dominio

| Dominio | Tools IMPLEMENT | E2E real | Estado |
|---|---|---|---|
| identity | 4 (session/profile/households/capabilities) | `identity.session.get` vía discovery y `me` | IMPLEMENTED / E2E PASS |
| households | 6 READ | `households.family.get` → 200 con miembros del hogar QA | IMPLEMENTED / E2E PASS |
| home | 3 READ | `home.summary.get` → 200 con conteos y `partial_errors` | IMPLEMENTED / E2E PASS |
| planner | 16 READ + 8 WRITE | `planner.tasks.list` 200; `planner.tasks.create` 201 + persistencia | IMPLEMENTED / E2E PASS (WRITE parcial) |
| finance | 14 READ + 2 WRITE | `finance.accounts.list` 200 con `contextType=household` mapeado | IMPLEMENTED / E2E PASS (WRITE con contrato) |
| inventory | 10 READ + 6 WRITE | `inventory.products.list` 200 | IMPLEMENTED / E2E PASS (WRITE con contrato) |
| assets | 6 READ | contrato + capability; sin E2E dedicada | IMPLEMENTED / AUTOMATED PASS |
| homecloud | 9 READ (metadatos) | `homecloud.files.list` 200; `homecloud.capabilities` visible | IMPLEMENTED / E2E PASS (metadatos) |
| homecloud SEE | 2 | proveedor sin garantizar | BLOCKED |
| messages | 3 READ + 1 WRITE | `messages.conversations.list` 200 (tras corregir migración) | IMPLEMENTED / E2E PASS |
| messages adjuntos SEE | 1 | URL firmada a bytes sin visión | BLOCKED |
| presence | 2 | consentimiento no verificable por el LLM | BLOCKED / EXCLUDED |
| notifications | 1 READ | preferencias en `me` | IMPLEMENTED / AUTOMATED PASS |
| feed | 0 | no existe backend | EXCLUDED BY CONTRACT |

---

## 3. Escenarios ejecutados (E2E smoke, 18/18)

| # | Escenario | Resultado |
|---|---|---|
| 1 | Sin bearer → 401 | PASS |
| 2 | Discovery autenticado → 92 tools | PASS |
| 3 | Proyección al modelo = `{tool_id, description, input_schema}` | PASS |
| 4 | `home.summary.get` incluido | PASS |
| 5 | `feed.*` no incluido | PASS |
| 6 | Claims `actor_id`/`household_id` forjados → 403 | PASS |
| 7 | `home.summary.get` | PASS 200 |
| 8 | `planner.tasks.list` | PASS 200 |
| 9 | `finance.accounts.list` | PASS 200 |
| 10 | `inventory.products.list` | PASS 200 |
| 11 | `households.family.get` | PASS 200 |
| 12 | `messages.conversations.list` | PASS 200 |
| 13 | `homecloud.files.list` | PASS 200 |
| 14 | Input inválido → 400 (no 500) | PASS |
| 15 | Tool desconocida → 400 | PASS |
| 16 | Escritura `planner.tasks.create` con proposal_id → 201 | PASS |
| 17 | Tarea creada se lee de vuelta (persistencia) | PASS |
| 18 | Seam interno sin secreto → 403 | PASS |

---

## 4. Matriz de roles (diseñada; ejecución parcial)

Ejecutado: actor con membership `active` en el hogar QA (coordinator). No ejecutado en esta sesión por falta de fixtures multi-rol: rol restringido, otro hogar, sesión expirada, cambio de hogar durante operación, feature flag deshabilitada. **No se declara PASS para esos escenarios**; el control está implementado en `backend/src/homi/v1/authority.js` y cubierto por el test `descubrimiento respeta capability y fail-closed sin contexto` (8/8 suite estática).

---

## 5. Conversación y voz

| Escenario | Estado |
|---|---|
| Consulta simple vía THINK | BLOCKED — HOMI-A `:18011` DOWN |
| Confirmación/cancelación de propuesta | PASS técnico (D local, tests históricos 108 PASS) / BLOCKED E2E con THINK |
| STT real → borrador editable → envío manual | BLOCKED — HOMI-C DOWN; contrato 10/10 PASS |
| T31 / turn talking / VAD / TTS | NO APLICA — cancelado por Actor A (T32) |
| QA físico iPhone (15 pasos T32) | NEEDS DEVICE QA — Actor A |

---

## 6. Limitaciones honestas

- Ningún resultado de simulación o contrato estático se elevó a DEVICE PASS.
- La escritura E2E se ejecutó por el seam con `proposal_id`; el ciclo completo THINK→propuesta→confirmación no pudo ejercitarse sin HOMI-A.
- Las tools BLOCKED no devuelven resultados inventados.
