# Inventario Premium V2 — plan de adopción segura

## Current

HomePlus mantiene Inventario V1 operativo: ítems, plantillas, movimientos, alertas y reposiciones. Su interfaz y sus rutas se mantienen durante la transición.

## Target

Incorporar Inventario Premium V2 como una evolución aditiva: catálogo, ubicaciones, productos con ciclo de vida, lista de compras colaborativa, compras, resumen y enlaces canónicos con Planner y Finanzas.

## Límites de integración

- No se elimina ni reemplaza Inventario V1 en esta entrega.
- Planner sigue siendo autoridad de tareas y Finanzas de movimientos financieros.
- Todas las mutaciones usan membresía activa, capabilities, idempotencia y control de versión cuando aplica.
- No se aplican migraciones remotas ni se modifica el historial de migraciones desde este repositorio.

## Secuencia

1. Añadir las cinco migraciones V2 y conservar compatibilidad con el registro V1.
2. Añadir el backend V2 y mantener las rutas V1 existentes.
3. Añadir el cliente tipado V2, sin reemplazar aún la pantalla V1.
4. Ejecutar validación estática y focal local.
5. Gate externo: aplicar las cinco migraciones en orden en el SQL Editor autorizado.
6. Validar runtime real, Storage no aplica a este dominio, y recién entonces habilitar la UI V2 por un slice separado.

## Gate de base de datos

Migraciones requeridas, en este orden:

1. `20261019000001_inventory_v2_foundation.sql`
2. `20261019000002_inventory_v2_atomic_rpc.sql`
3. `20261019000003_inventory_v2_products_ui_read_contract.sql`
4. `20261020000001_inventory_v2_shopping_purchase_domain.sql`
5. `20261020000002_inventory_v2_finance_source_integration.sql`

No aplicar dos veces. No editar manualmente `supabase_migrations`. Si se aplican por SQL Editor, la reconciliación de history queda pendiente hasta relinkear Supabase CLI.

## Evidencia mínima de runtime posterior al gate

- aislamiento household y capabilities;
- ubicación, producto y lista de compras idempotentes;
- compra finalizada genera el movimiento financiero canónico una sola vez;
- compra puede crear una tarea mediante Planner canónico;
- V1 no pierde sus rutas ni su registro de movimientos;
- realtime y UI V2 se habilitan sólo tras esa validación.
