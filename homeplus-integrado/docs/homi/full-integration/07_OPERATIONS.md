# 07 — OPERATIONS — Arranque, puertos, health checks y recuperación

## 1. Topología local

| Servicio | Puerto | Base/URL | Estado al cierre |
|---|---|---|---|
| Supabase local (REST / DB) | 56221 / 56222 | `http://127.0.0.1:56221` | UP (Docker) |
| Backend HomePlus + HOMI gateway | 3100 | `http://127.0.0.1:3100` | UP |
| HOMI-D portado | 8001 | `http://127.0.0.1:8001` | UP |
| Metro (preexistente) | 8081 | `exp://100.81.185.53:8081` / `exp://192.168.0.11:8081` | UP |
| HOMI-A THINK | 18011 | — | **DOWN** |
| HOMI-C STT | 8010 / 8012 | — | **DOWN** |
| LiveKit | 7880 | — | DOWN (T31 cancelado) |
| T07 anterior | 3002 | — | UP (no usado por la integración nueva) |

---

## 2. Arranque exacto (orden)

```powershell
$ROOT = "C:\Users\thega\Desktop\HomePlus-worktrees\homi-full-integration-18-11\homeplus-integrado"

# 1) Base de datos local aislada (aplica las 146 migraciones, incluida la del ledger)
cd $ROOT
supabase start
supabase db reset            # sólo entorno local; reproduce todas las migraciones

# 2) Backend (terminal propia)
cd $ROOT\backend
npm ci                        # ya ejecutado en esta sesión
node index.js                 # PORT=3100 desde backend/.env

# 3) HOMI-D (terminal propia)
$env:PYTHONPATH = "$ROOT\homi-orchestrator"
C:\Homi\orchestrator\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001

# 4) Cliente móvil (terminal propia)
cd $ROOT\front\mi-front-limpio
npm ci
npx expo start --clear
```

---

## 3. Health checks

```powershell
Invoke-RestMethod http://127.0.0.1:56221/rest/v1/          # Supabase (puede 404/401, responde)
Invoke-RestMethod http://127.0.0.1:3100/health             # { ok:true, service:"homeplus-backend" }
Invoke-RestMethod http://127.0.0.1:3100/api/homi/v1/health # { ok:true, service:"homi-v1-gateway", catalog:… }
Invoke-RestMethod http://127.0.0.1:8001/health             # { ok:true, node_id:"homi-d" }
```

**Sin exposición pública**: D escucha en `127.0.0.1`; el backend usa `0.0.0.0:3100` sólo en la red local de desarrollo. No se crearon túneles nuevos.

---

## 4. Cuenta QA y datos controlados

La sesión aprovisionó `homi.qa.1811@example.test` / contraseña local de prueba, con un hogar `Hogar QA HOMI 18-11`. No se usaron datos de producción. El token de QA se guardó fuera del worktree en `C:\Users\thega\AppData\Local\Temp\opencode\homi_qa_token.txt` (no entregable, no commitear).

Reprovisionar: `node C:\Users\thega\AppData\Local\Temp\opencode\homi_provision_qa.js` (script auxiliar de la sesión; requiere backend UP).

---

## 5. Pruebas

```powershell
cd $ROOT\backend
npm run test:homi          # 8/8 catálogo/autoridad
node tests/homi/v1-e2e-smoke.js    # 18/18 E2E real (requiere token QA y servicios UP)

cd $ROOT\front\mi-front-limpio
npx tsc --noEmit
node --test tests/homiVoiceSimple.contract.test.js tests/homiTransport.contract.test.js

cd $ROOT
npm run typecheck
npm run test:backend
npm run test:frontend
npm run test:contracts
```

---

## 6. Configuración local (sin secretos reales)

- `backend/.env`: `SUPABASE_URL=http://127.0.0.1:56221`, claves demo locales de Supabase, `PORT=3100`, `HOMI_D_BASE_URL=http://127.0.0.1:8001`, `HOMI_SELF_BASE_URL=http://127.0.0.1:3100`, `HOMI_INTERNAL_WRITE_SECRET` demo.
- `homi-orchestrator/.env.homi`: BD local `127.0.0.1:56222`, usuario `postgres`, esquema `homi`.
- `front/mi-front-limpio/.env`: `EXPO_PUBLIC_API_URL=http://127.0.0.1:3100`.

> Nota: el proceso de esta sesión tiene `HOMI_INTERNAL_WRITE_SECRET` en el entorno de PowerShell con un valor previo; `dotenv` no lo sobrescribe. El valor efectivo es el del entorno del proceso, no el del archivo. Para reproducir de cero, limpiar esa variable antes de arrancar el backend.

---

## 7. Expo Go / QA físico (Actor A)

1. iPhone con Expo Go SDK 58 en la misma red o Tailscale.
2. Escanear `exp://100.81.185.53:8081` (tailnet) o `exp://192.168.0.11:8081` (LAN).
3. Iniciar sesión; abrir **Más → Homie**.
4. Guion completo: T32 §12 (`C:\Homi\orchestrator\t32\T32_VOICE_SIMPLE_HANDOFF.md`), 15 pasos.
5. Registros: access log del backend `:3100`, log de HOMI-D `:8001`, consola Expo Go.

**No se declara QA físico ejecutado.**

---

## 8. Recuperación

| Situación | Acción |
|---|---|
| Supabase caído | `cd $ROOT; supabase start` → `supabase db reset` (local) |
| Backend no carga `.env` | verificar variables; reiniciar `node index.js` |
| 403 `homi_internal_write_forbidden` | el header `x-homi-internal-write` debe igualar `HOMI_INTERNAL_WRITE_SECRET` efectivo del proceso |
| `homi_forbidden_capability` | revisar matriz 04 y capabilities del hogar QA |
| 412 `version_conflict` | re-leer entidad, regenerar propuesta con `expected_version` vigente |
| HOMI-D no arranca | verificar `.env.homi` y que el esquema `homi` exista (`supabase db reset`) |
| THINK/STT DOWN | iniciar proveedores con sus launchers oficiales; no simular inferencia |
| Tests D con ancla vieja | ver 08; requieren actualización de contratos congelados |
