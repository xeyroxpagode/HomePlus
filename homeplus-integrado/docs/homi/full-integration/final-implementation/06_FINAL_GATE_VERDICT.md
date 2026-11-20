# Veredicto final de gates (2026-11-20)

| Gate | Estado | Evidencia o bloqueo |
|---|---|---|
| G1 Python pertinente | PASS parcial | 32/32 focales vigentes + 45/45 catálogo; 130 fallos son contratos históricos de 1–5 WRITE vs 193 actuales; `test_t18_find.py` aislado por PyTorch OOM/access violation |
| G2 `npm run quality` | PASS | 18 comandos, cobertura 87.66/77.03/80.49, secret scan y CI syntax PASS |
| G3 THINK real con READ válido | **PASS** | E2E real 8/8: tareas, pendientes, mañana, eventos, Finanzas, Inventario, ambigüedad y entidad inexistente. Proyección `2.1.0` con aliases reversibles sobre la paleta v1 de THINK; catálogo canónico intacto; HOMI-A no modificado |
| G4 THINK real con WRITE confirmado | PASS | `prop_5746c5c302ea369c` propuesta y confirmación desde navegador, respuesta `Creé la tarea en tu hogar.` |
| G5 STT real | PASS | faster-whisper, transcripción española no vacía, sin turno/TTS/auto-send |
| G6 Seguridad y permisos | PASS | seam 403/409, claims forjadas rechazadas, sin relajación de validaciones |
| G7 Ledger e idempotencia | PASS | `status=VERIFIED`, `uncertain=False` en BD; segunda confirmación sin duplicado |
| G8 Cobertura por dominio | PASS parcial | 307 contratos y bindings; E2E real en Planner y READs, resto en integration/contract-only |
| G9 Expo Web real | PASS | `:8083` sirve la app real, bundle compilado, sin crashes |
| G10 Browser login y navegación | PASS | Home, Más, Planner, Finanzas, Inventario, Assets, HomeCloud, Feed y Homie renderizados |
| G11 Browser HOMI READ | PASS | “Leí 7 tareas de tu Planner.” con datos reales |
| G12 Browser HOMI WRITE | PASS | Propuesta + botón Confirmar + resultado desde la UI |
| G13 Verificación entre pantallas | PASS | Tarea visible en Planner como `Tarea QA Browser Check — 21-nov, 09:00` |
| G14 Errores adversos | PASS parcial | Negativos del seam cubiertos por 21/21 tests; escenarios adversos de UI no todos ejecutados |
| G15 Bundle nativo / Expo Go | PREPARADO | Metro `:8082` UP, `.env` LAN correcto; export iOS verificado en sesión previa, no repetido |
| G16 Evidencia visual y handoff | PASS parcial | Tab real abierto en Review pane, evidencia DOM/consola/requests y handoff actualizado; screenshot bloqueado por visibilidad de ventana del desktop |
| G17 Intake HomeCloud real | PASS | HC-2A 29/29 + HC-2C 13/13: register/upload/verify/finalize, household y ownership server-side, staging/active, idempotencia, acceso cruzado negativo |
| G18 Builds y seguridad de cierre | PASS | `expo export --platform web` OK, typecheck/contracts/core/secrets OK, `npm run test:homi` 22/22, `git diff --check` limpio |

## Veredicto

`HOMEPLUS + HOMI V1 — RELEASE CANDIDATE READY FOR PUSH`.

No quedan gates P1 abiertos en el código. G3 pasó con inferencia real y se preservaron catálogo canónico, autoridad del gateway y fail-closed. La publicación efectiva sigue supeditada a la configuración de entorno del servidor (en particular `HOMECLOUD_MAX_UPLOAD_BYTES`) y a la aceptación física en dispositivo de Actor A. No se ejecutaron commit, push ni deploy.
