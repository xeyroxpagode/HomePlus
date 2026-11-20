# BROWSER QA — evidencia real (OpenCode Chromium)

**Fecha:** 2026-11-20 (America/Buenos_Aires)
**URL abierta:** `http://localhost:8083` (Expo Web, frontend autoritativo)
**Cuenta:** QA aislada `homi.qa.1811@example.test` (credenciales NO impresas ni guardadas en evidencia)
**Modo:** AUTOMATED BROWSER PASS. No equivale a DEVICE/iPHONE PASS.

> Nota de captura: el tool `browser.screenshot` requiere la ventana del desktop visible; en esta sesión no estuvo disponible. La pestaña real quedó abierta en el Review pane de OpenCode y la evidencia below se obtuvo de DOM vivo, requests reales, consola y consultas de persistencia. No se generó ninguna composición visual falsa.

## 1. Arranque y autenticación

- Splash real: `HomePlus — Organizá la vida de tu casa en un solo lugar. Crear cuenta / Entrar a mi hogar`.
- Login real: `Entrá a tu hogar — Email / Contraseña / Iniciar sesión`.
- Requests reales observadas: `POST :3101/api/auth/login`, `GET :3101/api/auth/me`, `GET :3101/api/feature-flags` y Supabase Auth en `:56221`.
- Selector de experiencia: `¿Cómo querés usar HomePlus?` → `Continuar con la experiencia estándar`.
- Home autenticado: `Hogar QA HOMI 18-11`, rol `Coordinador`, `Buen día, Coordinador`, `Viernes, 20 de noviembre`.
- Sin pantalla blanca ni crashes después de las correcciones web.

## 2. Navegación real

| Superficie | URL observada | Resultado |
|---|---|---|
| Home | `/ExperienceShell/HomeTab` | Datos reales del hogar QA y tareas persistidas |
| Más | `/ExperienceShell/MoreTab/MoreHome` | Módulos Objetos, Archivos, Actividad, Finanzas, Inventario, Homie |
| Homie | `/ExperienceShell/MoreTab/Homi` | Conversación, propuestas y composer |
| Planner | `/ExperienceShell/PlannerTab/PlannerHome` | Tareas HOY / PRÓXIMAS / SIN FECHA |
| Finanzas | `/ExperienceShell/MoreTab/Finance` | Personal / Familia / Inicio / Movimientos / Pagos |
| Inventario | `/ExperienceShell/MoreTab/Inventory` | Ruta montada sin crash |
| Assets | `/ExperienceShell/MoreTab/Assets` | Ruta montada sin crash |
| HomeCloud | `/ExperienceShell/MoreTab/HomeCloud` | Ruta montada sin crash |
| Familia | `nav.family` | Acceso disponible |
| Mensajes | `nav.messages` | Acceso disponible |
| Actividad | `/FeedFamiliar` | Hitos y publicaciones reales de demo |

## 3. HOMI — READ real desde el chat

- Acción: botón real `Ver mis tareas del Planner` dentro de Homie.
- Respuesta visible: **`Leí 7 tareas de tu Planner.`**
- Datos reales listados, incluidas `Tarea QA E2E VERIFICADA — 20-nov · 08:00`.
- Requests: `POST :3101/api/homi/v1/tools/planner.tasks.list/invoke` → datos reales del Planner/Supabase.
- Conclusión: READ real autorizado verificado desde la UI.

**Cierre G3 (esta sesión):** el READ en **texto libre** quedó verificado con inferencia real. En el chat de Homie se envió `Mostrame mis tareas` mediante el visible `textarea[aria-label="Preguntale algo a Homi"]` y el botón visible `Enviar el mensaje`:
- `POST http://localhost:3101/api/homi/v1/text/turn` → **HTTP 200**, `status: SUCCESS`, `decision_kind: tool_request`, `grounded: true`, `source_tool_id: planner.tasks.list`.
- Respuesta visible en pantalla: `Tienes 8 tareas pendientes en HomePlus:` con tareas reales del hogar QA (`Tarea QA E2E VERIFICADA`, `Tarea QA Browser Check — mañana 09:00`, etc.).
- E2E independiente desde API: **8/8 PASS**, incluidos Finanzas, Inventario, ambigüedad (`clarify`) y entidad inexistente (`Buscá la tarea Entidad QA inexistente 9f7c2` → “No se encontraron tareas, eventos ni planes…”).

La corrección fue local y reversible: proyección model-facing `2.1.0`, aliases sobre la paleta v1 de THINK y canonicalización antes de la validación. El catálogo canónico y el gateway 307 tools siguen siendo la autoridad; HOMI-A no fue modificado ni reiniciado.

## 4. HOMI — WRITE real desde el navegador

1. Mensaje enviado con el control real: `Crea una tarea llamada Tarea QA Browser Check para mañana a las 09:00`.
2. THINK respondió `Preparé una propuesta para crear la tarea.`
3. Propuesta visible en pantalla:
   - `proposal_id`: `prop_5746c5c302ea369c`
   - `tool_id`: `planner.tasks.create`
   - `Título: Tarea QA Browser Check`
   - `Fecha: 21/11/2026`, `Hora: 09:00`
   - `risk: LOW_MUTATION`, `confirmation: REQUIRED`, `status: PROPOSED`
4. Botón real `Confirmar` ejecutado desde la UI → respuesta **`Creé la tarea en tu hogar.`**
5. Sin persistencia previa confirmada: la lista de tareas no contenía el título antes de confirmar.
6. Persistencia verificada por lectura autenticada independiente:
   - `id`: `8f99cc06-bdc1-4d06-998d-39d6b2198a8b`
   - `title`: `Tarea QA Browser Check`
   - `due_date`: `2026-11-21`, `due_time`: `09:00:00`
7. Verificación entre pantallas: en Planner aparece bajo **PRÓXIMAS** como `Tarea QA Browser Check — 21-nov, 09:00`.
8. Ledger consultado en BD local (`homi.execution_runs`):
   - `RUN prop_5746c5c302ea369c planner.tasks.create status= VERIFIED uncertain= False completed= True`
9. Idempotencia: tras la confirmación el botón `Confirmar` desaparece y no existe un segundo camino de confirmación para la misma propuesta; la repetición por API había sido verificada previamente sin duplicado.

## 5. Correcciones web aplicadas durante Browser QA

| Archivo | Corrección | Motivo |
|---|---|---|
| `front/mi-front-limpio/.env` | `EXPO_PUBLIC_SUPABASE_URL` y `EXPO_PUBLIC_SUPABASE_ANON_KEY` añadidos; API URL a LAN `:3101` | La app web fallaba con "Falta EXPO_PUBLIC_SUPABASE_URL" |
| `metro.config.js` (nuevo) | Resolver web de `react-native-maps` | `codegenNativeComponent` no existe en react-native-web; nativo intacto |
| `web-shims/react-native-maps.web.tsx` (nuevo) | Superficie web equivalente | Solo se resuelve en `platform === 'web'` |
| `services/planner/reliability/operationScheduler.ts` | `setTimeout`/`clearTimeout` envueltos en funciones flecha | `Illegal invocation` en Chrome |
| `services/planner/reliability/runtime.ts` | mismo fix en el clock por defecto | Origen real del crash post-login |

TypeScript posterior: `npx tsc --noEmit` → exit 0.

## 6. Consola y red

- Sin errores JS bloqueantes después de las correcciones.
- Warnings no críticos observados: props nativas `accessibilityElementsHidden` / `importantForAccessibility` en DOM web, `<button>` anidado y `onLayout` en Fragment (limpieza cosmética, sin pérdida funcional).
- Las peticiones HOMI y de autenticación devolvieron datos reales; no se registraron 4xx/5xx funcionales en los recorridos de READ/WRITE.
- Se observó `404 http://localhost:3101/api/telemetry/event` (P2 preexistente, fuera del flujo HOMI); Drawer/Inventario resolvieron su estado vacío correctamente.

## 7. Alcance

- `BROWSER QA PASS` para login, navegación, READ real, WRITE confirmado, persistencia, ledger y verificación entre pantallas.
- `NATIVE BUNDLE PASS` no certificado en esta sesión (Metro 8082 operativo; export iOS verificado en la sesión previa de Codex).
- `IPHONE QA PASS` corresponde exclusivamente a Actor A.
