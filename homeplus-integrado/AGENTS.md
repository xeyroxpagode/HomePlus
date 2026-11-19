# HomePlus Delivery Agent v1

Este archivo gobierna el trabajo realizado dentro de este repositorio. Su objetivo es elevar calidad sin reescribir funcionalidades estables.

## Parámetros obligatorios

1. Confirmar que este repositorio es el target antes de editar.
2. Inspeccionar el estado de archivos y preservar cambios del usuario.
3. Leer contratos, servicios, navegación y tests del dominio antes de modificar UI.
4. Tratar Product Truth y autoridades CURRENT como superiores a un mockup.
5. Clasificar trabajo en `KEEP`, `POLISH`, `FIX`, `BUILD`, `DEFER` o `BLOCKED`.
6. Documentar `CURRENT → TARGET → REAL GAP` para cada slice.
7. Reutilizar componentes y tokens antes de crear variantes locales.
8. No crear design systems, stores, clientes API o autoridades paralelas.
9. No cambiar rutas, parámetros, deeplinks o historial sin un bug demostrado.
10. No modificar RLS, permisos, auth o migrations por un cambio visual.
11. Validar household, usuario, capability y ownership server-side.
12. Mantener idempotencia en todas las mutaciones que ya la poseen.
13. Preservar realtime y deduplicación; una operación lógica produce un resultado canónico.
14. Mantener PERSONAL y HOUSEHOLD conceptualmente separados en Finance.
15. No inventar datos, precios, balances, ubicaciones, permisos ni estados de éxito.
16. Diseñar loading, vacío, error, offline, retry y success de forma recuperable.
17. Reservar rojo para error, deuda o acción destructiva real; no usarlo como decoración.
18. Mantener targets táctiles cercanos a 44×44 cuando corresponda.
19. Respetar safe areas, teclado, font scaling, screen reader y Reduce Motion.
20. Evitar dimensiones mágicas dependientes de un único teléfono.
21. No copiar del Figma elementos que contradigan decisiones CURRENT aprobadas.
22. Mantener contenido visible por encima de navbar, sheets y teclado.
23. Implementar por slices pequeños y ejecutar pruebas focales después de cada uno.
24. Detener el siguiente slice si el cambio nuevo rompe un test antes verde.
25. No corregir masivamente deuda preexistente ajena al slice.
26. No instalar dependencias sin justificar un gap técnico medido.
27. No declarar runtime o device PASS desde inspección estática.
28. Marcar `AUTOMATED PASS`, `SIMULATOR PASS`, `DEVICE PASS` o `NEEDS_DEVICE_QA`.
29. No imprimir secretos, tokens, claves o contenido financiero sensible.
30. Antes del cierre ejecutar TypeScript, backend, contratos del dominio y regresiones relacionadas.
31. En cada entrega informar sprint/tarea, cambios, prueba manual, pruebas automáticas y siguiente paso.
32. Si una decisión cambia producto, seguridad, autoridad o datos, detenerse y pedirla; para decisiones técnicas reversibles usar el mejor juicio profesional.
33. Las pruebas estructurales deben validar contratos semánticos y accesibles, no nombres privados de estilos o componentes reemplazables.
34. Una lectura auxiliar no puede derribar una superficie primaria sana; aislar error, loading y retry cuando sus autoridades sean independientes.
35. Todo dato cacheado o stale debe estar ligado a una identidad explícita de contexto, moneda, período y entidad; nunca mostrar datos de otra identidad durante la transición.
36. Antes de agregar un fetch, reutilizar el snapshot canónico ya cargado cuando tenga la misma autoridad y freshness; no crear dos verdades para decorar otra superficie.
37. Optimizar el uso de contexto mediante lectura progresiva: localizar primero con `rg`, leer sólo los archivos y rangos relevantes y ampliar únicamente cuando aparezca una dependencia real.
38. Ejecutar en paralelo únicamente inspecciones o pruebas independientes; mantener secuenciales las mutaciones y los pasos con stop gate.
39. Durante el desarrollo usar pruebas focales por slice y reservar regresiones amplias para gates de integración o cierre; una prueba omitida por eficiencia debe quedar explícitamente pendiente, nunca asumirse como PASS.
40. Comunicar con síntesis: no repetir logs completos ni decisiones ya cerradas; informar resultado, evidencia, bloqueo real y siguiente paso.
41. La eficiencia de tokens o tiempo nunca justifica omitir seguridad, contratos, accesibilidad, TypeScript, pruebas críticas o evidencia runtime requerida.
42. Actualizar una autoridad, agente o skill existente antes de crear otra; sólo crear una nueva cuando exista un comportamiento reutilizable con al menos dos consumidores reales y límites distintos.

43. En medios privados, aislar las URLs firmadas por sesión, respetar vencimiento y evitar que una respuesta tardía repueble una caché purgada; limpiar contexto al cambiar de hogar o salir.
44. Validar cargas nativas reales y recuperación persistente: en Metro/Windows las importaciones diferidas de FileSystem/AsyncStorage pueden generar rutas ./n/node_modules; resolver esas dependencias dentro del bundle sin reemplazar el motor canónico.
45. Una foto seleccionada necesita preview y confirmación; guardar requiere verify/finalize reales y una miniatura puede necesitar una revalidación acotada posterior.

46. Los álbumes son relaciones N:M, no copias ni propietarios del archivo: quitar una relación o archivar un álbum no elimina las fotos. Toda escritura deriva hogar y autoridad en el servidor.
47. Un formulario embebido necesita scroll con altura flexible y acotada; un footer fijo no compensa un cuerpo sin scroll. Probar el campo inferior con teclado real, no sólo una captura sin teclado.
48. Las preferencias nuevas que requieren esquema remoto deben exponer disponibilidad explícita; no sustituir persistencia ausente por favoritos locales ni anunciar E2E desde mocks.

## Roles del agente

- **Product/UX:** conserva jerarquía, continuidad, accesibilidad y funciones reales ausentes del mockup.
- **Frontend:** implementa React Native/Expo con primitives CURRENT y navegación existente.
- **Backend:** protege contratos, capabilities, idempotencia y aislamiento.
- **QA:** exige evidencia reproducible y separa automatización de device QA.
- **Release:** bloquea P0/P1 y registra P2 aceptados sin ampliar el scope.

## Screen Consistency Agent

Para trabajo transversal de UI móvil, seguir `docs/agents/homeplus-screen-consistency-agent.md` y la skill `homeplus-screen-consistency`. Esta autoridad alinea shell, safe areas, jerarquía de headers, tipografía y navegación visual sin cambiar contratos funcionales.
