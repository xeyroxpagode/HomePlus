# 13 — RUNTIME READINESS — Pasada 1/2

## 1. Topología observada (2026-11-19)

| Servicio | Puerto | Estado observado | Evidencia |
|---|---:|---|---|
| Supabase REST / DB | 56221 / 56222 | OPEN | TCP |
| Backend + gateway HOMI | 3100 | HTTP 200 | `/health` y `/api/homi/v1/health` |
| HOMI-D | 8001 | HTTP 200 | `/health` → `node_id:"homi-d", role:"CONTROL"` |
| Metro | 8081 | OPEN | TCP |
| HOMI-A THINK | 18011 | OPEN, HTTP 404 en `/` | Proceso escucha; **inferencia no confirmada** |
| HOMI-C STT | 8010 / 8012 | closed | TCP |
| LiveKit | 7880 | closed | T31 cancelado, no aplica |
| T07 anterior | 3002 | OPEN | No usado |

**Sin exposición pública:** D en `127.0.0.1`; backend en `0.0.0.0:3100` solo red local. No se crearon túneles.

## 2. Orden de arranque (sin mutar configuración productiva)

```powershell
$ROOT = "C:\Users\thega\Desktop\HomePlus-worktrees\homi-full-integration-18-11\homeplus-integrado"

# 1) BD local aislada (solo entorno local)
cd $ROOT
supabase start
supabase db reset          # reproduce migraciones; SOLO local

# 2) Backend
cd $ROOT\backend
node index.js              # PORT=3100 desde backend/.env

# 3) HOMI-D
$env:PYTHONPATH = "$ROOT\homi-orchestrator"
C:\Homi\orchestrator\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001

# 4) Cliente
cd $ROOT\front\mi-front-limpio
npx expo start --clear
```

## 3. Preflight (checks obligatorios antes de E2E)

| # | Check | Criterio |
|---:|---|---|
| 1 | `GET :3100/health` | 200 `{ok:true}` |
| 2 | `GET :3100/api/homi/v1/health` | 200 y catálogo = **307 tools**, digest = ancla de `04` |
| 3 | `GET :8001/health` | 200 `{ok:true,node_id:"homi-d"}` |
| 4 | Catálogo D vs gateway | Mismo digest; 0 divergencias; loader acepta |
| 5 | Bindings | 307/307 resuelven a servicio canónico; 0 `require` dinámico |
| 6 | Propuestas | 193/193 WRITE con familia tipada; seam rechaza no-confirmadas |
| 7 | Ledger | `homi.execution_runs` / `homi.execution_steps` accesibles; DDL aplicado en BD local |
| 8 | **THINK** | Turno `infer_with_tools` real con tool call → `PASS`; si no, `BLOCKED` |
| 9 | **STT** | `/v1/voice/transcript` con audio de prueba → transcripción no vacía; si no, `BLOCKED` |
| 10 | **SEE** | `homecloud.content.access` devuelve bytes válidos; si no, tools de píxeles `BLOCKED` |
| 11 | Cuenta QA | Token vigente, membership `active`, hogar de prueba aislado |
| 12 | Multi-rol | Fixtures de 6 roles + otro hogar disponibles |
| 13 | Front | `npx tsc --noEmit` limpio; contratos voz/transporte PASS |
| 14 | Red iPhone | LAN/tailnet real verificada antes de QA físico |

**No se declara disponibilidad permanente.** Un servicio UP al inicio no garantiza disponibilidad al final; el preflight se repite antes de cada gate E2E.

## 4. Configuración sin secretos

- `backend/.env`: `SUPABASE_URL=http://127.0.0.1:56221`, claves demo locales, `PORT=3100`, `HOMI_D_BASE_URL=http://127.0.0.1:8001`, `HOMI_SELF_BASE_URL=http://127.0.0.1:3100`, `HOMI_INTERNAL_WRITE_SECRET` demo.
- `homi-orchestrator/.env.homi`: BD local `127.0.0.1:56222`, usuario `postgres`, esquema `homi`.
- `front/mi-front-limpio/.env`: `EXPO_PUBLIC_API_URL=http://127.0.0.1:3100`.
- **Precaución heredada:** el proceso de PowerShell puede tener `HOMI_INTERNAL_WRITE_SECRET` con valor previo; `dotenv` no lo sobrescribe. Limpiar la variable antes de arrancar para reproducir de cero.
- No imprimir tokens, claves ni contenido financiero en logs o entregables (AGENTS #29).

## 5. Estrategia de fixtures

- BD local aislada; cuenta QA y hogar de prueba creados en la sesión anterior; **nunca producción**.
- Datos controlados por dominio: una tarea, una cuenta, un producto, un bien, un álbum, una conversación.
- Multi-rol: aprovisionar los 6 roles reales, membership `suspended` y `pending`, segundo hogar, feature flag off.
- Cada WRITE E2E se verifica por lectura posterior; el ledger se consulta por `proposal_id`.

## 6. Recuperación

| Situación | Acción |
|---|---|
| Supabase caído | `supabase start` → `supabase db reset` (local) |
| Backend no carga `.env` | verificar variables; reiniciar `node index.js` |
| 403 `homi_internal_write_forbidden` | header `x-homi-internal-write` = secreto efectivo del proceso |
| 403 `homi_forbidden_capability` | revisar §06 y capabilities del hogar QA |
| 412 `version_conflict` | re-leer entidad, nueva propuesta con `expected_version` vigente |
| HOMI-D no arranca | verificar `.env.homi` y esquema `homi` |
| THINK/STT DOWN | launchers oficiales; **no simular inferencia** |
| Suite D con ancla vieja | `T-FOUND-04`: actualizar contratos al catálogo 307 |
| Divergencia de catálogos | regenerar desde `04`, fallar cerrado |

## 7. Criterios para runtime listo para E2E

1. Checks 1–7 PASS y catálogo único verificado.
2. Al menos un turno `infer_with_tools` real (check 8) o declaración `BLOCKED` con evidencia.
3. STT verificado o declarado `BLOCKED`; el flujo de texto sigue disponible.
4. SEE verificado o tools de píxeles declaradas `BLOCKED`; metadatos disponibles.
5. Fixtures multi-rol listas; QA físico agendado con Actor A.

**Gate K: RUNTIME PREPARATION SPECIFIED — PASS (procedimiento), con preflight de proveedores pendiente en la pasada 2.**
