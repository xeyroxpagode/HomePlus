# HOMEPLUS + HOMI V1 — handoff operativo final

**Fecha:** 2026-11-20 · **Rama:** `homi/full-integration-18-11` · **HEAD:** `d8edd49236457ffe1ac66bb9e836ef4117ac980d`
**Veredicto detallado:** `06_FINAL_GATE_VERDICT.md` · **Evidencia browser:** `qa-evidence/BROWSER_QA_EVIDENCE.md`

## 1. Cambios de Codex conservados

Catálogo 307 tools (114 READ / 193 WRITE, digest `624e4659…`), gateway HOMI V1, seam reforzado con claim `EXECUTING`/secreto/hash/actor/hogar, verificador post-escritura, contrato `dueDate`/`dueTime`, migraciones del ledger/attachment/FIND, suites focales de ejecución ambigua/CREATE/validación/attachment/ingestion, dependencia Babel del frontend y correcciones de helpers Python. Nada fue revertido.

## 2. Correcciones adicionales de OpenCode

- `scripts/runtime_smoke_test.js`: `Animated.createAnimatedComponent`, `stopAnimation`, `LocaleConfig`, mock de `react-native-maps`, tema de navegación y provider de tema listo para SSR → runtime smoke PASS.
- `scripts/homeplus_core_contract_tests.js`: cobertura legítima de `httpErrors`, envelope middleware y permisos de hogar; sin bajar thresholds ni quitar assertions.
- `front/mi-front-limpio/package.json` + lock: `yaml` para el gate de CI workflow syntax.
- `front/mi-front-limpio/.env`: URL LAN real y claves públicas locales de Supabase.
- `front/mi-front-limpio/metro.config.js` + `web-shims/react-native-maps.web.tsx`: compatibilidad Expo Web sin afectar nativo.
- `services/planner/reliability/{operationScheduler,runtime}.ts`: timers con binding para Chrome.
- **Cierre G3 (esta sesión):** proyección model-facing versionada `2.1.0` en `homi_tool_loop.py`, con alias reversibles sobre la paleta v1 de THINK, filtro por dominio/familia, alias `lifecycle_state` y canonicalización determinista antes de la validación. Catálogo canónico `planner-read-tools.v1.json` intacto; la autoridad sigue siendo el gateway 307 tools.
- `homi_tool_client.py`: ruta integrada `/api/homi/v1/tools` y envelope real `{tool_id, data, meta}` (antes ruta/envelope históricos).
- `homi_tool_normalize.py`: acepta cuerpo directo y envelope anidado; proyección acotada de `finance.accounts.list` e `inventory.items.list`; la búsqueda canónica `planner.tasks.search` usa la misma proyección que `planner.search.query`.
- `backend/src/homi/v1/executor.js`: adaptadores de transporte de `query → q` y descarte de `context` inválido en `/api/planner/search`; no cambia authority ni scope derivado del token.

## 3. Resultado Python

- Suite amplia: **880 PASS / 130 FAIL / 1 SKIP / 356 subtests** (excluyendo `test_t18_find.py` por access violation de PyTorch/sentence-transformers en Windows).
- Focales vigentes: `test_t23_attachments.py`, `test_t17_find.py`, `test_t32_stt_only.py` → **32/32 PASS**; `test_tool_catalog.py` → **45/45 PASS**.
- Los 130 fallos son **HISTORICAL_CONTRACT**: T09/T11/T12 esperan el catálogo congelado de 1–5 WRITE tools; el catálogo actual tiene 193. Ejemplo verificado: `test_canonical_write_allowlist_is_exactly_one_tool` recibe 188 tools extra. Los invariantes vigentes están cubiertos por los focales y por `npm run test:homi` (22/22). No se eliminaron tests.
- Focales de cierre G3: `test_model_projection_compat.py`, `test_t24_i1_read_tools.py`, `test_t09_f_normalize.py`, `test_tool_catalog.py`, `test_tool_decision_contract.py` → **170 PASS / 344 subtests PASS**.
- E2E real G3 contra backend `:3101`, HOMI-D `:8002` y THINK `:18011`: **8/8 PASS** (tareas, pendientes, mañana, eventos, Finanzas, Inventario, ambigüedad y entidad inexistente). Evidencia: `C:\Users\thega\AppData\Local\Temp\opencode\g3_live_e2e.js` (helper de sesión, excluido del commit).

## 4. `quality`

`HOMEPLUS TEST SUITE: quality PASSED (18 commands, 192370 ms)` (sesión previa). Cobertura final `87.66% líneas / 77.03% ramas / 80.49% funciones`.

**Verificación de cierre ejecutada en esta sesión:**
- `npm run test:homi` → **22/22 PASS**
- `npm run typecheck` → **PASS** (frontend y tests TypeScript)
- `npm run test:contracts` → **PASS** (51 + 33 assertions)
- `npm run test:core:backend` → **PASS**
- `npm run test:secrets` → **PASS** (2245 paths, sin imprimir valores)
- `npm run lint` (front) → **0 errores**, 53 warnings preexistentes
- `npx tsc --noEmit` → exit 0
- Contratos voz/transporte HOMI → **10/10 PASS**
- `npx expo export --platform web` → **BUILD PASS**, 1747 módulos, 3 bundles web (salida en temp, fuera del repo)
- `git diff --check` → sin findings; nada stageado.

## 5. THINK

Real y operativo: inferencia directa (`HOLA`, `provider_id: think-primary`), propuesta WRITE confirmada con modelo real y **READ en texto libre resuelto (G3 = 8/8)**.

Causa raíz y corrección sin tocar el proveedor remoto:
- THINK-A rechaza los 307 descriptores juntos (HTTP 400 por tamaño) y su gramática v2 fuerza campos aditivos de WRITE que luego prohíbe en READ no-legacy; su gramática v1 sólo admite ocho IDs Planner.
- D proyecta versionadamente `2.1.0` por dominio/familia, usa esos ocho IDs como paleta del modelo y los mapea de vuelta a los tools canónicos antes de revalidar; `status` se expone como `lifecycle_state` y se traduce deterministicamente.
- Finanzas e Inventario usan aliases sobre la misma paleta y proyecciones normalizables; la intención explícita de búsqueda expone únicamente `planner.search.query`, mapeado al canónico `planner.tasks.search`.
- Se descartan en READ los campos aditivos emitidos en `null` (`target`, `checklist_patch`, `assign_member_name`, `proposal_edit_patch`, `proposal_action`); cualquier valor no nulo sigue fallando en closed.
- El catálogo canónico, los contratos y las validaciones del gateway permanecen intactos. HOMI-A no fue modificado ni reiniciado.

## 6. STT

Real: WAV español vía multipart `/api/homi/v1/voice/transcript` → `faster-whisper` (`small.multilingual`), transcripción no vacía “Hola homi, esta es una prueba a Alevos.”, `semantic_turn=false`, `tools_executed=false`, `tts_generated=false`.

## 7. E2E WRITE VERIFIED

Dos escrituras reales verificadas en BD: `prop_4f8a6e016aad1761` y `prop_5746c5c302ea369c` (`planner.tasks.create`, `status=VERIFIED`, `uncertain=False`). La segunda se ejecutó **desde el navegador** con el botón real `Confirmar`; tarea `8f99cc06-bdc1-4d06-998d-39d6b2198a8b` persistida y visible en Planner (`21-nov, 09:00`). Repetición de confirmación sin duplicado.

## 8. Cobertura por dominio y tool

307 tools con binding, autoridad y schema en el gateway (`22/22` tests). Nivel A (contrato) completo. Nivel B real verificado en Planner, Finanzas, Inventario, ambigüedad, búsqueda de entidad inexistente y WRITE confirmada; el resto de las 193 WRITE permanece en `PASS_INTEGRATION`/`PASS_CONTRACT_ONLY` según `03_TOOL_AND_WRITE_ACCEPTANCE.json`. No se contabilizan como E2E real.

## 9. Permisos, idempotencia y ledger

Seam: `homi_internal_write_forbidden` sin secreto, `homi_proposal_not_confirmed` para propuesta no confirmada, `409` con argumentos adulterados, claims forjadas → 403. Confirmaciones expiradas/desactualizadas se rechazan. Ledger con `execution_runs`/`execution_steps`, sin resultados inciertos marcados como SUCCESS.

### 9.1 Intake HomeCloud real (esta sesión)

- `scripts/homecloud_2a_runtime_intake_tests.js` → **29/29 PASS** contra Supabase local `:56221`: register (staging, household derivado del servidor, ruta canónica, `uploaded_at=NULL`), idempotencia por `intakeRequestId`, autorización de subida, verify, finalize (activo, `uploaded_at` y sólo entonces), re-finalización idempotente, lectura activa, y rechazo de acceso cruzado Hogar A → Hogar B y de escritura Storage sin autenticar.
- `scripts/homecloud_2c_runtime_intake_tests.js` → **13/13 PASS**: pertenencia a álbum exactamente una vez, álbum cross-household/inexistente/trashed rechazado, FILE + álbum rechazado, replay/conflicto sin duplicar memberships.
- Requerimiento de despliegue confirmado: `HOMECLOUD_MAX_UPLOAD_BYTES` debe existir en la configuración de producción (no está en `backend/.env`; las pruebas lo inyectaron como `52428800`). Sin él, `register` falla en `HOMECLOUD_MAX_UPLOAD_BYTES must be a positive integer byte limit`.

## 10. Expo / Metro

- Metro Expo Go del worktree: **`:8082` UP** (PID 6416). El proceso `:8081` pertenece a `homi-t07` y no fue tocado.
- Expo Web: **`:8083` UP**, bundle compilado y app navegada en Chromium real.
- Backend `:3101`, HOMI-D `:8002`, THINK `:18011`, Supabase `:56221/:56222` operativos.
- **Build web de producción:** `npx expo export --platform web` → PASS (1747 módulos, 3 bundles, artefactos en `C:\Users\thega\AppData\Local\Temp\opencode\expo-web-export`, fuera del repo).
- Browser smoke (esta sesión): Home, Familia, Organizador, Más, Finanzas, Inventario (estado vacío resuelto), Archivos y Homie con datos reales. Chat HOMI envió `Mostrame mis tareas` y mostró la respuesta grounded (`8 tareas`, `source_tool_id=planner.tasks.list`) con HTTP 200.
- Warnings preexistentes de RN‑Web (`accessibilityElementsHidden`, `importantForAccessibility`, `<button>` anidado, `onLayout` en Fragment) y `404 /api/telemetry/event`: no bloquean funcionalidad; se registran como P2/P3 conocidos.

## 11. URL LAN para iPhone

API: `http://192.168.0.11:3101` · Supabase: `http://192.168.0.11:56221` · Metro: `exp://192.168.0.11:8082` (alternativa Tailscale `100.81.185.53`). IP verificada con `Get-NetIPAddress`; conectividad verificada por health check.

## 12. Comandos exactos de arranque

```powershell
$ROOT = "C:\Users\thega\Desktop\HomePlus-worktrees\homi-full-integration-18-11\homeplus-integrado"
cd $ROOT; supabase start
cd $ROOT\backend; node index.js                     # PORT=3101 desde .env
$env:PYTHONPATH="$ROOT\homi-orchestrator"
C:\Homi\orchestrator\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8002
cd $ROOT\front\mi-front-limpio; npx expo start --go --lan --port 8082
cd $ROOT\front\mi-front-limpio; npx expo start --web --port 8083
```

## 13. Limitaciones y deuda conocida (ninguna bloquea el push)

1. 130 tests históricos T09/T11/T12 incompatibles con el catálogo 307 (requieren migración de contrato, no regresión del producto).
2. `test_t18_find.py` derriba la suite por un access violation de PyTorch/sentence-transformers en Windows; se ejecuta aislado.
3. No hay aceptación física en iPhone (compete a Actor A). Browser QA es `AUTOMATED BROWSER PASS`, no `DEVICE PASS`.
4. Warnings React de RN‑Web y `404 /api/telemetry/event`: P2/P3 preexistentes, sin pérdida funcional observada.
5. El despliegue público requiere configurar `HOMECLOUD_MAX_UPLOAD_BYTES` y el resto de variables de `backend/.env.example`; no se ejecutó deploy en esta sesión.
6. Las 193 WRITE tools no tienen E2E real una por una; su estado es `PASS_INTEGRATION`/`PASS_CONTRACT_ONLY` según el artifact de aceptación.

## 14. Veredicto

`HOMEPLUS + HOMI V1 — RELEASE CANDIDATE READY FOR PUSH`. G3 quedó cerrado con **8/8 real**; G1–G16 están PASS o PASS parcial documentado, sin gates P1 abiertos en el código. Public deployment queda condicionado a la configuración de entorno del nuevo servidor y a la aceptación en dispositivo de Actor A. No se hizo commit, push ni deploy: el usuario conserva esa decisión.

## 15. Paquete para push (comandos propuestos)

Repo: `C:\Users\thega\Desktop\HomePlus-worktrees\homi-full-integration-18-11`. Antes de ejecutar, verificar `git status --short` y revisar el diff; hay cambios preexistentes del usuario que deben conservarse.

```powershell
cd C:\Users\thega\Desktop\HomePlus-worktrees\homi-full-integration-18-11
git status --short
git diff --check

# Stagear por rutas explícitas (no `git add -A`)
git add homeplus-integrado/backend/src/homi
git add homeplus-integrado/backend/src/controllers/homiV1.controller.js
git add homeplus-integrado/backend/src/routes/homiV1.js
git add homeplus-integrado/backend/index.js homeplus-integrado/backend/package.json
git add homeplus-integrado/backend/tests/homi
git add homeplus-integrado/homi-orchestrator
git add homeplus-integrado/docs/homi
git add homeplus-integrado/front/mi-front-limpio/components/homi
git add homeplus-integrado/front/mi-front-limpio/screens/homi
git add homeplus-integrado/front/mi-front-limpio/services/homi
git add homeplus-integrado/front/mi-front-limpio/src
git add homeplus-integrado/front/mi-front-limpio/web-shims
git add homeplus-integrado/front/mi-front-limpio/metro.config.js
git add homeplus-integrado/front/mi-front-limpio/tests/homiTransport.contract.test.js
git add homeplus-integrado/front/mi-front-limpio/tests/homiVoiceSimple.contract.test.js
git add homeplus-integrado/supabase/migrations/20261119000000_homi_execution_ledger.sql
git add homeplus-integrado/supabase/migrations/20261119000001_homi_ledger_runtime_alignment.sql
git add homeplus-integrado/supabase/migrations/20261119000002_homi_attachment_metadata.sql
git add homeplus-integrado/supabase/migrations/20261119000003_homi_find_chunks.sql

git diff --cached --name-only
git commit -m "HOMI V1 full integration: G3 READ real, catalog and gateway hardening"
git push origin homi/full-integration-18-11
```

**Exclusiones deliberadas:** `C:\Users\thega\AppData\Local\Temp\opencode\homi_qa_token.txt` (token QA), `g3_live_e2e.js` y helpers de diagnóstico, `expo-web-export` (artefacto de build), `.env` locales y cualquier archivo fuera de las rutas listadas. El secret scan pasó y no imprimió valores.

**Deploy y rollback (propuestos, no ejecutados):**
1. Aplicar migraciones `20261119*` en el entorno destino y verificar `homi.execution_runs`.
2. Configurar variables de `backend/.env.example`, especialmente `HOMECLOUD_MAX_UPLOAD_BYTES` (entero positivo), `HOMI_D_BASE_URL`, `HOMI_TOOL_BASE_URL`, `HOMI_INTERNAL_WRITE_SECRET` y Supabase.
3. Arranque: backend → HOMI-D (con `PYTHONPATH` al orchestrator) → Expo web/nativo. Health checks `:3101/health` y `:8002/health`.
4. Smoke de producción: login QA, `Mostrame mis tareas`, `Buscá la tarea inexistente …`, create + confirm, intake register/upload/verify/finalize.
5. Rollback: revertir el commit en la rama (`git revert <sha>`) y redeploy del artefacto anterior; las migraciones son aditivas y no destructivas. No se ejecutó rollback ni deploy.
