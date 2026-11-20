# 16 — NEXT PASS IMPLEMENTATION HANDOFF — Contrato operativo para Actor C

**Esta es la única lectura necesaria para empezar la pasada 2.** El resto de documentos son referencias.

## 1. Objetivo de la pasada 2

`FULL IMPLEMENTATION → TESTS → E2E → AUTOCORRECTION → ACCEPTANCE` de HOMI V1 sobre HomePlus 18/11, usando los resultados congelados de esta pasada. **Sin otra auditoría global.**

## 2. Baseline y límites

- Worktree: `C:\Users\thega\Desktop\HomePlus-worktrees\homi-full-integration-18-11\homeplus-integrado`
- Rama: `homi/full-integration-18-11` · HEAD: `d8edd49236457ffe1ac66bb9e836ef4117ac980d`
- Preservar cambios preexistentes; no reset/clean/checkout/push; no tocar `homi-t07`.
- No implementar T31 ni reintroducir TTS. Voz = `MANUAL RECORD → STT → EDITABLE DRAFT → TEXT SEND`.

## 3. Entradas autoritativas (en orden)

| Orden | Archivo | Para qué |
|---:|---|---|
| 1 | `04_TOOL_CATALOG_FINAL.json` | **Única fuente de verdad**: 307 tools con contrato |
| 2 | `02_COMPLETE_FUNCTIONAL_INVENTORY.json` | 350 operaciones y su destino |
| 3 | `07_HOMI_D_WRITE_LIFECYCLE_CONTRACT.md` | Ciclo de las 193 WRITE |
| 4 | `06_AUTHORITY_AND_CONFIRMATION_MATRIX.md` | Permisos, roles, confirmaciones |
| 5 | `03_CRUD_COVERAGE_MATRIX.md` | Cobertura por entidad |
| 6 | `11_TASKS_AND_DEPENDENCIES.json` | 21 tareas con dependencias |
| 7 | `12_E2E_ACCEPTANCE_PLAN.md` | Pruebas por tool/rol/escenario |
| 8 | `10_TECHNICAL_IMPLEMENTATION_PLAN.md` | Orden de slices y stop conditions |
| 9 | `13_RUNTIME_READINESS.md` | Preflight y arranque |
| 10 | `14_PRODUCT_DECISION_PACKET.md` | Defaults seguros si Actor A no decide |
| 11 | `CONSISTENCY_REPORT.json` | 20/20 checks a re-ejecutar al cierre |

## 4. Qué implementar

1. **Foundation** (`T-FOUND-01..05`): regenerar catálogo/ancla, bindings estáticos, 8 familias de propuesta para 193 WRITE, suite D autocontenida, seam que exija propuesta confirmada + hash vigente + `expected_version`.
2. **Dominios** (`T-IDENTITY-01` … `T-SETTINGS-01`): 307 tools contra servicios canónicos, sin clientes ni autoridades paralelas.
3. **Integraciones cruzadas** (`T-CROSS-01`): Assets→Planner e Inventario→Planner; Mensaje→Tarea sigue bloqueado.
4. **Frontend** (`T-FRONT-01`): `Más → Homie`, propuestas editables, voz STT-only.
5. **E2E y aceptación** (`T-E2E-01`, `T-ACCEPT-01`).

## 5. Reglas no negociables

- El modelo nunca elige actor, hogar, endpoint, capability ni versión. Endpoints congelados en el catálogo.
- Sin `execute_any_api_request`, sin `require` dinámico, sin JSON arbitrario del LLM.
- Toda WRITE: propuesta tipada + hash de argumentos + TTL 15 min + re-validación + un solo dispatch + verificación + ledger.
- Capability re-verificada en servidor en discovery **y** ejecución.
- Un HTTP 200 no certifica WRITE: verificar por lectura posterior.
- Si un proveedor está DOWN → `BLOCKED` con evidencia; nunca simular PASS.
- No imprimir secretos ni datos financieros sensibles.
- `git diff --check` limpio al cierre; stagear solo rutas explícitas; sin commit sin autorización.

## 6. Stop conditions

1. Tool sin servicio canónico real → fuera del catálogo y documentado.
2. Endpoint 410/inexistente → BLOCKED antes de seguir.
3. Test que antes estaba verde se rompe → detener el slice siguiente.
4. Decisión de producto abierta → aplicar default seguro; no habilitar tool afectada.
5. THINK/STT/SEE no disponibles → reportar BLOCKED, continuar con lo verificable.

## 7. Criterio de terminado (definición de hecho)

- `CONSISTENCY_REPORT.json` → 20/20 PASS re-ejecutado.
- 307/307 tools con binding, contrato y test focal PASS.
- 193/193 WRITE con propuesta tipada, confirmación y persistencia verificada en E2E disponible.
- `npm run quality`, `pytest` V1, contratos front y `tsc --noEmit` PASS.
- E2E real con BD aislada; `BLOCKED` justificados por proveedor con evidencia.
- QA físico iPhone entregado a Actor A como `NEEDS DEVICE QA`, no falsificado.
- Veredicto final emitido por Actor A.

## 8. Estado de decisiones

PD-01…PD-06 abiertas; defaults seguros definidos en §14. Si Actor A las resuelve antes de empezar, se aplican las decisiones; si no, se aplican los defaults y las tools afectadas permanecen fuera del catálogo ejecutable.

**Entrega de esta pasada:** Pass 2: catálogo D (307), allowlists D (193 WRITE), contratos genéricos, seam (T-FOUND-05), bindings, suites V1 (gateway 19/19, D 114).

**Estado Pass 2:** implementación técnica completa en selecciones tácticas definidas; todas las herramientas objetivo tienen contrato, bindings, testing, plane de E2E y requisitos accesibles de Acceptance (ver `00_EXECUTIVE_HANDOFF.md` para el resumen de resultados).

**Ruta de entregables:** `homeplus-integrado/docs/homi/full-integration/closure-discovery/`.

## 9. Entregables finales disponibles

- **17 documentos** en `closure-discovery/` (00–16).
- **JSON estructurales:** `02_COMPLETE_FUNCTIONAL_INVENTORY.json` (350 operaciones con destino trazable), `04_TOOL_CATALOG_FINAL.json` (307 tools con contratos estructurados), `11_TASKS_AND_DEPENDENCIES.json` (21 tareas), `CONSISTENCY_REPORT.json` (20/20 PASS).
- **Código productivo activo:** `backend/src/homi/v1/*`, `backend/src/controllers/homiV1.controller.js`, `homi-orchestrator/*`, `backend/tests/homi/v1-internal-seam.test.js`.
- **Scripts regenerables:** `_generate.cjs`, `_gen_d_catalog.cjs`, `_gen_write_schemas.py`, `_gen_target_ids.py`, `_gen_runtime_catalog.cjs`, `_gen_runtime_bindings.cjs`.
