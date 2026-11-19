# homplus-18-11 — 18/11/2026

Snapshot integrado del workspace foreground-gps. Frontend principal: front/mi-front-limpio.

- Álbumes N:M: crear desde preview, seleccionar, filtrar, renombrar y eliminar conservando fotos.
- Eventos: presentación completa, fecha explícita y protección de borrador.
- Teclado: infraestructura compartida y formularios focales corregidos.
- TypeScript y 78 pruebas focales PASS; Home 53/53, Reactive UI y Experience Mode PASS.
- Export Android/iOS/web PASS; export no equivale a QA iOS.

## Pendientes conocidos

- Aplicar y validar supabase/migrations/20261118000000_homecloud_photo_preferences_v1.sql antes de habilitar portadas y favoritos. No se aplicó remotamente.
- Segunda cuenta, aislamiento real entre hogares, iOS y matriz completa de teclado pendientes.
- El error histórico 500 de eventos no se reprodujo; creación/fecha/detalle reales verificados en Android.
- Dos hallazgos previos de ESLint (diagnóstico PlanFormHost y handler de Actividad); suite histórica Event V1 falla una expectativa textual de hash delegado.

No se publican entornos locales, sesiones, artefactos, capturas privadas ni credenciales.
