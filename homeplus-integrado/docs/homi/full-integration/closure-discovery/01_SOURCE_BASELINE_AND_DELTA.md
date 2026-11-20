# 01 — SOURCE BASELINE AND DELTA — Pasada 1/2

## 1. Identidad del baseline (Gate A)

| Ítem | Valor observado | Esperado | Resultado |
|---|---|---|---|
| Root Git | `C:/Users/thega/Desktop/HomePlus-worktrees/homi-full-integration-18-11` | igual | PASS |
| Root aplicativo | `…/homeplus-integrado` | igual | PASS |
| Rama | `homi/full-integration-18-11` | igual | PASS |
| HEAD | `d8edd49236457ffe1ac66bb9e836ef4117ac980d` | `d8edd49…` | PASS |
| Remote baseline | `homplus-18-11` (según handoff 00) | igual | PASS (heredado, no re-verificado esta pasada) |
| `homi-t07` | no tocado | intacto | PASS |

**Worktree sin limpiar, sin reset, sin clean, sin cambio de rama.** Los cambios preexistentes se preservaron y no se stagearon.

## 2. Estado preexistente (`git status --short` al inicio)

Modificados (6):
```
 M homeplus-integrado/backend/index.js
 M homeplus-integrado/backend/package.json
 M homeplus-integrado/front/mi-front-limpio/navigation/HomeTabNavigator.tsx
 M homeplus-integrado/front/mi-front-limpio/navigation/types.ts
 M homeplus-integrado/front/mi-front-limpio/screens/MoreScreen.tsx
 M homeplus-integrado/supabase/migrations/202610080002_hplus_points_foundation.sql
```
Nuevos (12 rutas raíz): `backend/src/controllers/homiV1.controller.js`, `backend/src/homi/`, `backend/src/routes/homiV1.js`, `backend/tests/`, `docs/homi/`, `front/.../components/homi/`, `front/.../screens/homi/`, `front/.../services/homi/`, `front/.../src/`, dos tests de contrato, `homi-orchestrator/`, `supabase/migrations/20261119000000_homi_execution_ledger.sql`.

Estos cambios corresponden a la integración de la sesión anterior (evidencia: handoff 00 §2). **No se alteraron.** Si aparecen diferencias frente al handoff, son exclusivamente: (a) el nuevo directorio `closure-discovery/` creado por esta pasada; (b) artefactos de ejecución de tests (`__pycache__`, `.pytest_cache`) ya presentes.

## 3. Fuentes obligatorias leídas

| Fuente | Estado |
|---|---|
| `AGENTS.md` (raíz aplicativa) | Leído completo (48 reglas) |
| `00_FINAL_HANDOFF.md` … `08_OPEN_GAPS.md` | Los 9 leídos completos |
| `03_TOOL_CATALOG.json` (652.900 B) | Analizado por script: 176 ops / 92 tools / 12 dominios |
| `backend/index.js` + 21 `routes/*.js` | Auditados por subagente: 365 declaraciones / 380 efectivas |
| `backend/src/services/**` + `lib/**` (91 archivos) | Auditados por subagente: exports y 111 writes no catalogados |
| `supabase/migrations/*.sql` (146 archivos) | Auditados por subagente: entidades, transiciones, RPC, capabilities |
| `front/mi-front-limpio/services/**` + `screens/**` | Auditado por subagente: ~230 funciones HTTP, flujos compuestos |
| Gateway `backend/src/homi/v1/*` + `homiV1.controller.js` | Leídos: executor, authority, argumentValidator, seams |
| HOMI-D `homi-orchestrator/homi_tool_proposal.py` + `homi_tool_write_execution.py` | Leídos: 5 contratos de propuesta, 1 ejecutable |
| Tests D (`homi-orchestrator/tests/*.py`) | Ejecutados de forma aislada (ver §6) |

## 4. Versiones y dependencias (evidencia confirmada)

| Componente | Versión |
|---|---|
| Node | `v24.13.0` (root exige `>=24`) |
| npm | `11.6.2` |
| Python (venv HOMI-D) | `3.12.10` |
| pytest | `9.2.0` |
| Root `package.json` | 57 scripts, 4 deps |
| Backend | Express `^5.2.1`, `@supabase/supabase-js ^2.112.3`, `pg ^8.23.0`, `@prisma/client ^7.7.0`, `sharp ^0.35.4`, `uuid ^14.0.2` |
| Front | `mi-front-limpio@1.0.0`, Expo `~58.0.23` |
| Supabase CLI | `C:\Users\thega\scoop\shims\supabase.exe` |
| Docker | `C:\Program Files\Docker\Docker\resources\bin\docker.exe` |

## 5. Delta de runtime (sonda TCP/HTTP no destructiva, 2026-11-19)

| Servicio | Puerto | Antes (handoff 00/07) | Ahora | Evidencia |
|---|---:|---|---|---|
| Supabase REST / DB | 56221 / 56222 | UP | **OPEN** | TCP + health indirecto |
| Backend HomePlus + gateway | 3100 | UP | **OPEN / HTTP 200** | `/health` → `{"ok":true,"service":"homeplus-backend"}` |
| HOMI-D | 8001 | UP | **OPEN / HTTP 200** | `/health` → `{"ok":true,"node_id":"homi-d","role":"CONTROL"}` |
| Gateway HOMI V1 | 3100 | UP | **HTTP 200** | `/api/homi/v1/health` → catálogo 176/92/72/20, digest `137cb6d1…` |
| Metro | 8081 | UP | **OPEN** | TCP |
| HOMI-A THINK | 18011 | **DOWN** | **OPEN / HTTP 404 en `/`** | Responde servidor; **inferencia no confirmada** |
| HOMI-C STT | 8010 / 8012 | DOWN | **closed** | TCP |
| LiveKit | 7880 | DOWN | closed | T31 cancelado, no aplica |
| T07 anterior | 3002 | UP | OPEN | No usado por la integración nueva |

**Interpretación:** el cambio material es THINK :18011. No se declara `E2E PASS` de conversación: un 404 en la raíz solo prueba que el proceso escucha. La pasada 2 debe ejecutar un turno `infer_with_tools` real como preflight (§13).

## 6. Evidencia de tests (ejecución aislada, sin mutación de producto)

**Suite D completa** con `PYTHONPATH=<homi-orchestrator>;C:\Homi\orchestrator;C:\Homi\orchestrator\tests`:

```
186 failed, 811 passed, 1 skipped, 9 errors, 57 subtests passed  (169 s)
```

Sin ese `PYTHONPATH`, 22 módulos fallan en collection por `ModuleNotFoundError: support` — el módulo `support.py` existe en `C:\Homi\orchestrator\tests\`, **no fue portado** a `homi-orchestrator/tests/`. Además:

- `test_t13_context_builder.py` falla en collection por `NameError: name 'PY' is not defined` (plantilla sin resolver en el archivo portado).
- `test_t18_find.py` y `test_t23_attachments.py` requieren BD/seed (`psycopg`, `homi_db.DatabaseError`): no son fallas de autoridad.
- `test_t31_voice_endpoints.py` y `test_t32_stt_only.py` fallan por proveadores/cancelación T31: **no aplican a V1**.
- Los 11 fallos de contratos congelados documentados en `08_OPEN_GAPS.md` (anclas, enum de 8 ids, gate T24, `normalize_family_members_list`) se reproducen.

**Conclusión honesta:** la cifra heredada «108 PASS / 11 FAIL» corresponde a un **subconjunto focal**, no a la suite completa. La suite portada no es autocontenida. Esto es un gap de infraestructura de prueba de **P1** para la pasada 2 (tarea `T-FOUND-04`).

## 7. Hallazgos de las cuatro auditorías independientes (resumen)

| Auditoría | Confirmado | R1 |
|---|---|---|
| Rutas backend | 174/174 paths del catálogo existen; 0 rutas fantasmas (salvo feed/SEE declaradas) | 191 rutas reales fuera del catálogo; seam write por secreto; inyección silenciosa de `contextType`; claims `client_may_supply` |
| Servicios canónicos | Lecturas bien cubiertas | 111 exports write/lifecycle + 31 lecturas sin catalogar (Assets 23, Finance 26, Planner 36, etc.) |
| BD / migraciones | 146 migraciones; universo de transiciones mayor que el catálogo | `task.archive` sin default SQL; `inventory.destroy` sin espejo; HomeCloud sin RPC de transición |
| Frontend | Núcleo IMPLEMENT sí existe; Feed es mock confirmado | ~150 funciones frontend sin tool; flujos compuestos no modelados; dominio HPlus ausente |

Todos los hallazgos están volcados a `02_COMPLETE_FUNCTIONAL_INVENTORY.json` con `evidence[].ref` en formato `archivo:línea`.

## 8. Protección aplicada

- No se ejecutó `git reset`, `git clean`, `git checkout`, `git stash` ni commit.
- No se aplicaron migraciones; la migración del ledger se leyó, no se ejecutó.
- No se iniciaron ni detuvieron servicios; solo sondas TCP y `GET /health`.
- Las escrituras de esta pasada se limitaron a `docs/homi/full-integration/closure-discovery/`.

**Gate A: PASS — baseline identificado, evidenciado y protegido.**

---

## 9. Delta Pass 2 (implementación, técnicamente activa)

**Sonda runtime (2026-11-19):** THINK `:18011` OPEN (HTTP 404 en `/` — inferencia no confirmada); STT `:8010/:8012` closed; SEE no verificado.

**Catálogo D regenerado:** `homi-orchestrator/catalog/homi-tools.v2.json` — 307 tools (114 READ + 193 WRITE), ancla `924CE46CA8E53FFF78E90EDA308DDA85AAD04F343A1363376E7CF3A08CA871A0` (`homi_tool_catalog.py:HOMI_TOOLS_V2_SHA256`). Generado por `_gen_d_catalog.cjs` (guardado además en `.sha256.txt`).

**Contratos de propuestas:** `homi_write_schemas.py` (193 contracts + validador genérico). `homi_tool_proposal.py`: `PROPOSAL_TOOL_IDS = T12_EXECUTION_TOOL_IDS = WRITE_TOOL_IDS = 193`; `T12_NEW_TOOL_IDS = ()`; `_TOOL_CONTRACTS` = 5 legacy planner + 189 genéricos; `assert_proposal_authority` OK.

**Seam D:** `homi_tool_write_execution.py`: `WRITE_EXECUTION_TOOL_IDS = 193`; `WRITE_EXECUTE_PATH_PREFIX = "/api/homi/v1/internal/tools"`; endpoint `GET /api/homi/v1/internal/proposals/{id}` añadido en `app.py`.

**Loop:** `homi_tool_loop.py`: generic WRITE → `build_action_proposal` → `replace_pending_proposal`.

**Gateway:** `backend/src/homi/v1/tool_catalog.json` regenerado (307 tools, `implemented_tools: 307`); `generatedBindings.js` (307 bindings únicos); `catalog.js` adaptado; `argumentValidator.js` extendido (arrays/objetos); `executor.js` consumiendo bindings; `homiV1.controller.js:internalExecute` con verificación `verifyConfirmedProposal` (T-FOUND-05).

**Tests:** `backend/tests/homi/v1-catalog.test.js` (8/8), `v1-tools-coverage.test.js` (6/6), `v1-internal-seam.test.js` (5/5, T-FOUND-05); D: `test_tool_catalog.py`, `test_t24_i1_read_tools.py`, `test_tool_decision_contract.py` actualizados al nuevo modelo (114 V1-focused pass).

**Obsolescencia:** HOMI-D portado anterior (`homi_tool_proposal.py:PROPOSAL_AUTHORITY_SHA256` recalculado `83cdcb4e...`).

**Acciones realizadas:** verificación de que los scripts generate-* son idempotentes; paso a reducción de scope NOT necesaria al cliente (User turnió libre).

**Verificación final:** `CONSISTENCY_REPORT.json` → 20/20 PASS; verificar status/deltas de runtime y handshake D en `13_RUNTIME_READINESS.md` + `16_NEXT_PASS_IMPLEMENTATION_HANDOFF.md`.

