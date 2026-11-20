# 09 — FRONTEND AND ACCESS CONTRACT — Pasada 1/2

## 1. Acceso actual confirmado (evidencia de diff)

```
front/mi-front-limpio/screens/MoreScreen.tsx     → tile { id:'homi', label: productNames.homi ('Homie'),
                                                      icon:'sparkles', screen:'Homi', isDemo:false }
front/mi-front-limpio/navigation/types.ts        → MoreStackParamList.Homi: undefined
front/mi-front-limpio/navigation/HomeTabNavigator.tsx → <MoreStack.Screen name="Homi" ... headerShown:false />
```

**Acceso definitivo para la pasada 2:** `Más → Homie`, conservando esa integración. No se diseña una interfaz paralela.

## 2. Arquitectura de navegación aplicable

- `App.tsx` → providers → `AppNavigator` → `ExperienceResolver` → `SimpleShell` | `StandardShell` → `HomeTabNavigator`.
- `HomeTabNavigator`: 5 tabs (Home | Family | QuickAction | Planner | More). **No se agrega sexto tab**, botón flotante ni deeplink nuevo (`AGENTS.md:9`, `01_CURRENT_AUDIT.md:72`).
- Convención «Más»: solo módulos con pantalla real (`docs/implementation/h042_3_appshell_topbar_navigation.md:107-116`). HOMI ya tiene pantalla real.
- Se reutilizan `productNames.homi`, `AppScreen bottomInset="tab"`, `AppPageHeader` y el patrón de permisos existente. **No se toca SimpleShell.**

## 3. Gate de disponibilidad

Doble gate **feature flag + capability**, con scope `accountId:householdId` y default deny:
- Hoy solo existe el flag `planner.search_entry` (`defaultValue:false`, `client_visible`). No hay flag HOMI. La pasada 2 debe agregar uno explícito o reutilizar la proyección de capabilities; **no asumir disponibilidad**.
- Capabilities se proyectan desde `GET /api/planner/capabilities`; el front no deriva capacidades del rol y el backend re-verifica.
- Si no hay hogar activo o membership no `active`: la tile se oculta y el acceso directo devuelve al usuario a la app con mensaje accionable.

## 4. Superficie de chat y propuestas

| Elemento | Requisito |
|---|---|
| Composer | Texto editable; envío manual; sin envío automático tras STT |
| Mensajes | Lista con estados de carga/vacío/error/reintento; contenido tratado como dato no confiable |
| Propuestas | Preview con args normalizados, efecto y `expected_version`; botones **Confirmar / Editar / Cancelar** |
| Edición | Cambiar un argumento recalcula hash e invalida la confirmación anterior |
| Adjuntos | Selección y preview antes de subir; sin TTS; limpieza de caché al cambiar de hogar |
| Errores | 400/403/404/409/412/422 traducidos a mensajes semánticos; 5xx reintentable sin duplicar write |
| Accesibilidad | Targets ~44×44, safe areas, teclado visible, screen reader, Reduce Motion, font scaling |
| Teclado | Contenido por encima de navbar, sheets y teclado; scroll flexible en formularios embebidos |

## 5. Voz (modalidad cerrada)

`MANUAL RECORD → STT → EDITABLE DRAFT → TEXT SEND`

- Transporte: `src/voice/createHomiVoiceTransport.ts` (factory siempre manual), `expoManualDictationTransport.ts`, `homiDictation.ts`, `homiMultipart.ts`.
- `playAnswer()` es no-op. **No TTS, no Turn Talking, no barge-in, no VAD, no LiveKit** (T31 cancelado por Actor A, decisión 2026-11-18; no se reabre).
- STT `:8010/:8012` está caído en esta sesión: el contrato 10/10 PASS es estático; el dictado real queda `BLOCKED` hasta preflight (`§13`).
- Aceptación física: 15 pasos del guion `t32/T32_VOICE_SIMPLE_HANDOFF.md §12`, ejecutados por **Actor A**. No se declara PASS.

## 6. Proyecto móvil autoritativo

| Proyecto | Estado | Decisión |
|---|---|---|
| `front/mi-front-limpio` | Principal/QA: CI `.github/workflows/homeplus-quality.yml`, runner `tests/run.js`, 599 archivos, Android+Maestro, Expo 58 | **Autoritativo**; recibe toda la implementación |
| `front/mi-front-expo-go` | Copia histórica divergente, mismo `name`, App.tsx más antiguo, sin CI | No se toca en V1 (PD-06) |

Para evitar divergencias: un único `productNames`, un único transporte de voz y un único cliente HOMI. Si Actor A decide soportar expo-go, se replican tile y ruta desde la misma fuente, sin crear una segunda autoridad.

## 7. Errores y continuidad

- Cambio de hogar: limpiar caché y contexto de medios; URLs firmadas por sesión; una respuesta tardía no debe repoblar una caché purgada (AGENTS #43).
- Sesión expirada: volver a login sin perder el hilo local; la propuesta pendiente se descarta con aviso.
- Offline: el composer conserva el borrador; sin write duplicado al reconectar.
- `NEEDS DEVICE QA`: todo lo que dependa de micrófono, teclado real, permisos iOS y 5 grabaciones consecutivas.

**Gate J: HOMI APPLICATION INTEGRATION SPECIFIED — PASS (técnico), con `NEEDS DEVICE QA` y PD-06 pendientes.**
