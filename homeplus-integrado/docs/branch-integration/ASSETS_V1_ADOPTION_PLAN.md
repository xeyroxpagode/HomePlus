# Assets / Bienes V1 — integración selectiva

## Objetivo

Integrar el dominio Assets recuperado de `origin/recovery/assets-v2-s7-20261021`
sin fusionar el snapshot histórico, sin reemplazar Planner ni HomeCloud y sin
degradar los contratos actuales de HomePlus.

## Decisión

- **ADOPT:** persistencia, capacidades, lifecycle, records, care, búsqueda,
  pantallas de Bienes y navegación desde Más.
- **ADAPT:** creación de Task/Event desde un bien, delegando en el Planner
  canónico actual con la misma identidad idempotente del formulario.
- **DEFER:** relaciones Assets → HomeCloud Files hasta que HomeCloud complete
  su cierre runtime. No se importó `20261023000000_assets_file_relations_v1.sql`.
- **REJECT:** merge/cherry-pick completo de la rama, UI histórica ajena al
  design system actual y cualquier autoridad paralela de Planner/HomeCloud.

## Arquitectura integrada

- Backend: `/api/assets` deriva household y membership desde la sesión.
- Seguridad: `assets.view`, `assets.contribute`, `assets.manage` son fail-closed
  en código; los grants se provisionan explícitamente por migración.
- Frontend: Assets vive como `Bienes` dentro de `Más` y reutiliza navegación,
  primitives, tokens y formularios Planner existentes.
- Planner: Assets compone el origen server-side y delega la escritura a Planner.
  El cliente no puede enviar `origin_*` ni crear Tasks/Eventos por una vía
  paralela.
- HomeCloud: conserva autoridad independiente; no existe adjunto automático.

## Orden obligatorio de migraciones

1. `20261006000000_assets_core_persistence_v1.sql`
2. `20261008000000_assets_idempotency_v1.sql`
3. `20261008010000_assets_context_v1.sql`
4. `20261010000000_assets_profile_change_v1.sql`
5. `20261011000000_assets_records_foundation_v1.sql`
6. `20261011010000_assets_idempotency_reserve_race_fix_v1.sql`
7. `20261012000000_assets_record_link_unlink_v1.sql`
8. `20261013000000_assets_record_correction_renewal_v1.sql`
9. `20261013010000_assets_period_correction_timestamp_fix_v1.sql`
10. `20261013020000_assets_period_correction_single_signature_v1.sql`
11. `20261014000000_assets_record_remove_restore_v1.sql`
12. `20261015000000_assets_manual_care_foundation_v1.sql`
13. `20261016000000_assets_care_remove_restore_v1.sql`
14. `20261017000000_assets_identity_category_v1.sql`
15. `20261018000000_assets_lifecycle_archive_v1.sql`
16. `20261019000000_assets_trash_restore_v1.sql`
17. `20261020000000_household_default_permissions_assets_v1.sql`
18. `20261021000000_assets_search_unaccent_v1.sql`
19. `20261022000000_planner_events_origin_fields_v1.sql`
20. `20261022000001_planner_event_origin_write_v1.sql`

Las dos últimas son parte obligatoria del contrato: agregan la referencia
server-side e inmutable que permite a Assets crear y consultar eventos de
Planner sin una tabla puente ni autoridad paralela.

## Apply gate

Estas migraciones **no fueron aplicadas remotamente durante la integración**.
Sólo deben aplicarse por una ruta autorizada y en el orden anterior. No editar
manualmente `supabase_migrations`.

Antes de declarar runtime PASS se debe verificar:

- tablas, FKs, índices, constraints y funciones Assets;
- RLS activa y aislamiento cross-household;
- grants explícitos por household y revocación efectiva;
- create/update/archive/trash/restore;
- records y care;
- búsqueda;
- Task/Event desde un bien con exactly-once y origen server-side.

## Evidencia local

- TypeScript frontend: PASS (`npx tsc --noEmit`).
- Sintaxis backend Assets e integración en `backend/index.js`: PASS.
- Capabilities backend fail-closed: PASS.
- Proyección/caché/data loop frontend: PASS.
- Transporte Planner desde Assets: POST real, identidad estable y sin
  `origin_*` cliente: PASS.
- Origen de Tasks/Eventos: compuesto sólo por integraciones backend; la API
  pública rechaza suplantación y los eventos lo preservan de forma inmutable.
- Lint focal Assets: sin errores propios. Existe un error preexistente en
  `PlannerSheetHost.tsx` por `Math.random()` durante render, fuera de este slice.

## Estado

`ASSETS MIGRATION READY — EXTERNAL SQL APPLY REQUIRED`

No declarar Assets runtime PASS hasta completar apply y validación real.
