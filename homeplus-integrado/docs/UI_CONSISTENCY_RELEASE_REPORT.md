# HomePlus — UI compartida, interacción y publicación

Fecha: 2026-11-17. Workspace exclusivo: Family-Hub-Own-foreground-gps; front principal: front/mi-front-limpio.

## A. CURRENT y correcciones
| Pantalla | Antes | Después |
|---|---|---|
| Familia | Sin título; selector absoluto sobre contenido; fondo blanco fijo | AppPageHeader Familia, selector en flujo y superficie temática |
| Organizador | Título distinto y selector de destinos independiente | Header común y UnderlineTabs, conservando selección/visitedTabs |
| Más | Título y padding superior distintos | Header común; grid estable conservado, ancho explícito en fallback accesible |
| Objetos | Root sin retorno; subtítulo alteraba baseline | Retorno real condicionado por stack y título común |
| Archivos | Header con otro padding; Archivos repetido en toolbar raíz | Header alineado; toolbar conserva nombre de carpeta únicamente cuando existe |
| Actividad | Header propio y tipografía distinta | Header común. La entrada de Más continúa siendo DEMOSTRACIÓN, sin convertir mocks en datos reales |
| Finanzas | Implementación local de header y filas | Consume AppPageHeader y Row manteniendo sus callbacks, importes y estados |
| Inventario | Identidad de producto con geometría local | Header común e identidad en Row; controles y mutaciones de stock intactos |

La línea de título es independiente del subtítulo: ambos headers con y sin descripción conservan baseline. No se tocó navbar inferior, shells ni navegación funcional. Root tabs no reciben flechas decorativas.

## B. Componentes reales reutilizados
- components/ui/AppPageHeader.tsx: títulos de las ocho superficies, más consumidores CURRENT. Fila mínima 48, targets laterales >=44, centrado simétrico, AppText title1 y tokens existentes.
- components/ui/Row.tsx: variante plana/card, 72 de alto mínimo según la referencia Tareas; permite contenido de dominio, estados accesibles, slots y callback canónico. Consumidores: TaskRow, AssetRow, MemberRow, FinanceListRow, identidad InventoryItemCard y timeline ActivityRow.
- UnderlineTabs: Finanzas y Organizador para destinos pares. SegmentedControl conserva contextos/modos locales.
- IconButton, AppButton, AppInput y ActionSheet: reutilizados, sin nueva biblioteca.
- Grillas de Más y previews de archivos permanecen grillas: no se fuerzan a filas porque representan trabajos distintos. El feed demo conserva sus publicaciones como cards.

## C. Interacción y teclado
InteractivePressable reutiliza useReducedMotion (un listener nativo compartido). Las filas planas usan pressScale=1 y opacidad 0.92: feedback de contacto sin rasterizar texto/iconos. La prueba con promesa deliberadamente pendiente demuestra pressed -> request -> confirmación; no mide milisegundos físicos.

No se agregaron operaciones optimistas sobre dinero, permisos ni acciones sensibles. AppButton conserva tamaño en loading y bloqueo de doble envío. Cachés, invalidación, particiones por contexto y dedup CURRENT se conservaron.

QA detectó un defecto real en PlannerSheetHost: el viewport fijo dejaba el footer de TaskForm detrás del teclado Android. Ese host es distinto de ActionSheet. Se ajusta su altura y espacio inferior con el frame real de teclado, conserva scroll/submit ownership y limpia listeners. Screenshot posterior y recorrido abrir -> foco -> CTA visible -> back -> cerrar PASS, sin crear registros. El sheet genérico quedó sin cambios netos.

Durante un intento anterior hubo un ANR al BACK coincidente con recarga de desarrollo. No se atribuye una causa definitiva sin thread trace; tras arranque limpio y corrección, el recorrido final de teclado pasó. No se borró información del emulador.

## D. QA y límites
- TypeScript de frontend y tests PASS.
- 45 contratos PASS: UI compartida, UVE, temas, Assets UX, Finance y auth/me.
- Casa/M9: 53/53 PASS (es la misma suite, no se cuenta dos veces).
- Reactive UI, Presence, Experience Mode y backend/core contracts PASS.
- ESLint focal de primitives/consumidores sin errores nuevos. Family mantiene 3 errores de memoización, Feed demo 1 de pureza y PlannerSheetHost 1 de pureza; comparación before/after confirma que ya existían. No se desactivaron reglas. Continúan warnings previos.
- Android dev build compatible: recorrido Maestro por las ocho entradas en claro y oscuro PASS; retorno de Objetos y formulario con teclado PASS. Capturas locales en artifacts/ui-consistency, excluidas del repositorio público por privacidad.
- 24 taps ADB a los cuatro tabs: captura y jerarquía final muestran Más y nav.more selected=true, otros false. El repeat Maestro se interrumpió tras el primer ciclo para ejecutar el estrés sin esperas de instrumentación; no se presenta como suite Maestro completa de estrés.
- Medición real en emulador/debug bajo estrés: dumpsys registró 51 frames y 48 janky (94.12%), p50 150ms y p95 300ms. No es FPS de producción ni comparación before/after. No se demuestra fluidez física ni <100ms. INTERACTION QA PARTIAL.
- Red real: lecturas observadas entre aproximadamente 2.4 y 4.4s; la estructura se monta antes de completar solicitudes. Se observó también un error DNS transitorio directo de Supabase durante desarrollo, ajeno a esta modificación visual; no se cambió la URL ni se ocultó el error.
- El intento compacto 360dp/130% detectó una tile estrecha pese al salto a una columna; se añadió width explícito al grid. La captura posterior coincidió con reinicialización/navegación, por lo que no acredita el resultado final: compact/font scaling completo queda pendiente. Los parámetros físicos del emulador fueron restaurados a 1080x2400, density 420, font 1.0.
- Sin QA físico iOS, sin comparación renderizada actual de Figma, sin prueba completa de todos los CRUD/permisos/roles y sin benchmark de release. No se declara fidelidad pixel-perfect ni seguridad remota revalidada por tests estáticos.

## E. Exposición multidispositivo
Ver DEPLOYMENT_EXHIBITION_READINESS.md: Railway Express + HTTPS, Supabase demo remoto aislado y EAS preview. API actual depende de LAN; web reescribe hostname a localhost; firma release Android actual usa debug. Esos gates deben resolverse antes de una entrega pública autónoma. No se desplegó ningún servicio ni se contrató un plan.

## F. Seguridad y snapshot Git
El workspace no tenía .git. Staging independiente en .release/HomePlus, clonado del remoto correcto, rama exacta homeplus-integrado basada en origin/main, sin mover el proyecto ni sobrescribir otras ramas. Todo el código se publica dentro de homeplus-integrado/ conservando backend/front/scripts/tests/supabase y lockfiles.

Se excluyen env reales, sesiones, node_modules, caches, builds, APK, firmas, logs, documentos/capturas históricas con posible información personal y un seed con correos reales. Se conservan ejemplos sanitizados. Revisión de JWT, claves, URLs con credenciales, literales sensibles, correos y assets; las credenciales locales de tests sintéticos se distinguen de secretos remotos. Ningún secreto remoto encontrado en el árbol publicable. No se detectó un secreto nuevo comprometido que justificara rotación; los env locales nunca se publicaron.

npm ci --dry-run --ignore-scripts --offline pasó en raíz, backend y front principal: validación de lockfiles, sin instalar ni descargar dependencias. Prisma schema, Proguard, Gradle wrapper y configuración Supabase deben formar parte del árbol; debug.keystore se genera localmente o por EAS, nunca se publica.

Commit/push y SHA se verifican externamente al documento para evitar autorreferencia. No se hace force, no se modifica main ni se abre PR.

## G. Integridad
Sin cambios de backend, endpoints, contratos, roles, RLS, migraciones, reglas financieras o integraciones. Sin H+ nuevo ni conexión Assets/HomeCloud. Sin datos ficticios nuevos en producción. Preferencia de tema y parámetros de emulador se restauran después de QA cuando el entorno lo permite.

## H. Prueba manual breve y pendientes
1. Entrar a las ocho pantallas: comparar título, margen y selector; repetir en oscuro.
2. Más -> Objetos -> volver: debe regresar realmente y conservar el contexto del stack.
3. Organizador -> + -> tocar título: Crear tarea queda encima del teclado; cerrar sin guardar.
4. Alternar tabs rápidamente y terminar en Más: indicador y contenido deben coincidir.
5. Con texto grande, abrir Más y comprobar nombres completos y scroll.

Pendiente QA físico iOS/Android, benchmark en build release, roles/CRUD completos y latencia real. El plan de exposición no equivale a un despliegue. Veredictos conservadores: HOMEPLUS UI CODE PASS — VISUAL QA PENDING; INTERACTION QA PARTIAL. GitHub sólo se declara verificado después de cotejar SHA remoto y carpeta.

Agente/reglas: HomePlus Delivery / Screen Consistency. Skills: homeplus-screen-consistency y figma-design-to-code; no se inventó referencia Figma faltante ni se crearon agentes paralelos.

## Archivos de presentación modificados
- front/mi-front-limpio/screens/FamilyScreen.tsx
- front/mi-front-limpio/screens/HomeCloudFilesScreen.tsx
- front/mi-front-limpio/screens/HomeCloudScreen.tsx
- front/mi-front-limpio/screens/MoreScreen.tsx
- front/mi-front-limpio/components/assets/AssetRow.tsx
- front/mi-front-limpio/components/family/FamilyViewSegmentedControl.tsx
- front/mi-front-limpio/components/family/MemberRow.tsx
- front/mi-front-limpio/components/planner/PlannerSheetHost.tsx
- front/mi-front-limpio/components/ui/AppPageHeader.tsx
- front/mi-front-limpio/components/ui/InteractivePressable.tsx
- front/mi-front-limpio/components/ui/Row.tsx
- front/mi-front-limpio/components/finance/ui/FinanceRows.tsx
- front/mi-front-limpio/screens/assets/AssetsListScreen.tsx
- front/mi-front-limpio/screens/feed/FeedFamiliarScreen.tsx
- front/mi-front-limpio/screens/finance/FinanceScreen.tsx
- front/mi-front-limpio/screens/inventory/InventarioScreen.tsx
- front/mi-front-limpio/screens/planner/PlannerAttentionActivityScreen.tsx
- front/mi-front-limpio/screens/planner/PlannerScreen.tsx
- front/mi-front-limpio/screens/planner/plannerShared.ts
- front/mi-front-limpio/screens/planner/PlannerTasksScreen.tsx

Además: .gitignore, tests/ui_consistency_contract.test.js, reglas del agente y documentos de publicación/ejecución.
