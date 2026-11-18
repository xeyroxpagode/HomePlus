# HOMePLUS — Roadmap acelerado: release gate

Fecha de conciliación: 2026-11-01  
Fuente: `Roadmap_HomePlus_7_dias.xlsx` (HP-001 a HP-049).

## Alcance congelado

El cierre cubre exclusivamente:

- Finance: navegación, dashboard, movimientos, categorías/límites, estados, accesibilidad y QA.
- GPS/Mapa: permisos, precisión, ubicación inicial, búsqueda, selección, fallos y device QA.
- Mensajes: navegación, texto, media, audio, recuperación y Conversation → Action.
- Modo Simple: navegación, flujos esenciales, estados y accesibilidad.
- UI/UX global: tokens y primitives existentes, estados, formularios y navegación.
- Motion: continuidad funcional, Reduce Motion y rendimiento; no motion ornamental.
- Release: E2E, aceptación multidispositivo, RC, observabilidad, rollback y Go/No-Go.

Fuera de alcance: features nuevas, Video, context cards nuevas, cambios de autoridad de dominio, migraciones no requeridas, reemplazo de navegación, rediseños sin Figma aprobado y deuda P2 sin impacto de release.

## Severidad

- **P0 — bloqueo absoluto:** pérdida/corrupción de datos; bypass de auth/RLS/permisos; crash reproducible en camino crítico; app no inicia; release no instala.
- **P1 — bloqueo de release:** camino crítico no puede completarse; duplicación o inconsistencia canónica; navegación rota; CTA inaccesible; permiso sin salida; error infinito; regresión grave de accesibilidad.
- **P2 — no bloqueante con decisión:** problema visual menor, copy o fricción con workaround seguro; requiere responsable, impacto y seguimiento.

## Autoridad de estado

La columna `Completada` del Excel no refleja el CURRENT: registra 0/49. Ninguna tarea se considera pendiente o completa por esa columna. La verdad de cierre es:

1. código CURRENT;
2. contrato/prueba automatizada;
3. runtime real cuando corresponda;
4. evidencia física para hardware/permisos;
5. decisión explícita para limitaciones.

## Gates por bloque

| Gate | Evidencia mínima | Responsable de decisión |
|---|---|---|
| Finance Freeze | TypeScript + suite Finance aplicable + navegación + QA visual Figma/dispositivo | Producto + QA |
| GPS/Mapa Freeze | contratos + permisos/precisión/búsqueda + iOS/Android físicos | QA de dispositivo |
| Mensajes Freeze | M+H1/M2 + realtime/dedup + media física + Message → Task | Producto + QA |
| Modo Simple Freeze | Experience Mode + flujos esenciales + texto grande/lector | Producto + QA |
| UI/Motion Freeze | UVE + Anticipatory + navegación + Reduce Motion + performance | Diseño + QA |
| Release Candidate | suite crítica dos veces + instalación limpia + cero P0/P1 | Go/No-Go owner |

## Clasificación inicial del CURRENT

- **IMPLEMENTADO, REQUIERE VALIDACIÓN:** Finance core/UI, Mensajes M+H1/M2, SimpleShell, tokens/primitives UVE, Anticipatory UX y navegación global.
- **PARCIAL / REQUIERE DEVICE QA:** GPS/precisión, permisos, cámara, micrófono, audio, picker y comportamiento físico iOS/Android.
- **PENDIENTE DE CIERRE:** suite Maestro completa, aceptación multidispositivo, EAS RC, observabilidad/rollback y Go/No-Go.
- **FIGMA GATE:** cualquier cambio visual productivo de pantallas. Las correcciones funcionales y contractuales pueden avanzar.

## Convención de evidencia

Cada HP debe terminar con uno de estos estados:

- `AUTOMATED PASS` — prueba repetible local/CI.
- `SIMULATOR PASS` — comprobación de runtime en simulador/emulador.
- `DEVICE PASS` — comprobación en hardware real.
- `NEEDS_DEVICE_QA` — implementación y contrato listos; falta hardware.
- `BLOCKED` — dependencia externa concreta con dueño y siguiente acción.
- `DEFERRED P2` — no bloqueante, aceptado explícitamente.

No se admite declarar `PASS` por inspección visual del código ni por el éxito aislado de una migración/build.

## Orden de ejecución

1. Baseline técnico y conciliación de HP-001…HP-049.
2. Finance sin cambios visuales hasta Figma.
3. GPS/Mapa y Mensajes con device QA explícito.
4. Modo Simple, UVE, accesibilidad y motion.
5. E2E, RC, rollback y Go/No-Go.

## Regla de stop

Si un slice introduce una regresión en funcionalidad CURRENT estable, se detiene el siguiente slice hasta resolverla o revertir únicamente el cambio nuevo. No se acumulan fixes encima de un baseline rojo sin causa clasificada.
