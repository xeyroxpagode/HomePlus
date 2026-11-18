# HOMePLUS — Universal Visual Ergonomics (UVE), Parte 1/2

Fecha: 2026-10-14  
Estado: auditoría y selección. **Sin implementación de producto.**

## 1. UVE definition

UVE es la disciplina transversal que convierte contexto y prioridad de producto en una interfaz físicamente cómoda, visualmente inequívoca y accesible. Anticipatory UX decide **qué/cuándo**; UVE decide **cómo/dónde/con qué jerarquía**. Ninguna decisión UVE puede modificar autoridad, permisos, privacidad, comportamiento de dominio o navegación canónica.

| Dimensión | Definición operativa | Evidencia esperada |
|---|---|---|
| UVE-01 Jerarquía visual | Un foco primario, secundarios subordinados y metadata silenciosa | Test de 1 y 3 segundos |
| UVE-02 Densidad | Información suficiente sin aire improductivo ni compresión | Escaneo sin saltos/scroll artificial |
| UVE-03 Legibilidad | Tamaño, peso, ancho de línea y truncado comprensibles | Font scaling y textos largos |
| UVE-04 Espaciado | Ritmo basado en tokens, agrupación por relación semántica | Escala 4/8/12/16/24/32 |
| UVE-05 Touch ergonomics | Hit area cómoda aunque el símbolo sea pequeño | Objetivo aproximado ≥44×44 |
| UVE-06 Reachability | Frecuencia, importancia y riesgo definen alcance | Una mano; destructivas deliberadas |
| UVE-07 Action placement | CTA primario reconocible y estable | No tres primarias equivalentes |
| UVE-08 Color semantics | Terracota para activo/selección/foco/CTA | Estado comprensible sin decorar |
| UVE-09 Contrast | Texto, icono y estado superan contraste funcional | Claro/oscuro/disabled/error |
| UVE-10 Geometry | Alturas, radios y proporciones coherentes | Primitives y grids compartidos |
| UVE-11 Component consistency | Mismo propósito usa mismo primitive | Estados iguales entre módulos |
| UVE-12 Optical alignment | Corrección perceptiva, no sólo matemática | Baseline, iconos y centros |
| UVE-13 Information priority | Datos de decisión antes que metadata | Primary/secondary/background explícitos |
| UVE-14 One-hand comfort | Acción frecuente alcanzable sin reordenar todo abajo | Portrait, tamaños diversos |
| UVE-15 Cognitive calm | Menos competencia, ruido y decisiones simultáneas | Una lectura predecible |
| UVE-16 Motion ergonomics | Movimiento explica transición y respeta Reduce Motion | 150–300 ms, sin bounce decorativo |
| UVE-17 Spatial continuity | Origen y destino conservan relación espacial | Tabs, sheets, detail/back |
| UVE-18 Feedback clarity | Press/loading/success/error sin saltos | Estado inline y recuperable |
| UVE-19 Accessibility | Roles, labels, state, scaling y orden comprensibles | Screen reader + font scale |
| UVE-20 Responsive robustness | Safe areas, teclado, anchos y plataformas | Android/iOS, phone widths |

## 2. CURRENT design system audit

### Tokens

**KEEP:** paleta canónica exacta, semantic colors, tipografía Manrope, spacing 4–64, grid de 4 columnas, `contentMaxWidth=720`, radios, sombras, component sizes, motion y touch targets 44/56. Existe dark palette, senior typography y Reduce Motion.

**Gaps demostrados:**

1. Varios primitives (`AppText`, `AppButton`, `AppInput`, `AppCard`, `IconButton`) importan `colors` estáticos, mientras sólo 58 archivos usan `useAppTheme`; dark mode no es universal aunque el provider exista.
2. `seniorTypography` está definido y expuesto, pero `AppText` no lo consume. SimpleShell compensa con primitives propios; no debe conectarse globalmente sin validar layouts.
3. `AppScreen.bottomInsets` usa 96/112 fijos y no deriva de las métricas reales de navbar/FAB.
4. El código todavía contiene 726 coincidencias de spacing numérico y 253 colores hex fuera de tokens, concentradas sobre todo en superficies legacy. No todos son defectos, pero impiden garantizar consistencia automáticamente.

### Componentes transversales

| Componente | Evaluación | KEEP | Gap real | Clase |
|---|---|---|---|---|
| AppButton | GOOD | 52 dp primario, loading conserva tamaño, estados semánticos | `sm=42` queda por debajo del objetivo táctil aproximado | B |
| IconButton | EXCELLENT | 44 dp, label obligatorio, variantes semánticas | Ninguno demostrado | A |
| AppInput | GOOD | 50/52 dp, label/helper/error, focus visible | Borde 1→2 en focus puede producir microcambio interior | C |
| AppCard | GOOD | Padding tokenizado, variantes y jerarquía | Haptic por defecto en toda card requiere validación por uso | B |
| Row | GOOD | Altura efectiva cómoda, truncado y slots | API no expone state/destructive explícito | B |
| FilterChip | IMPROVE | Visual compacto y estado claro | Superficie interactiva efectiva de 36 dp | C |
| StatusBadge | EXCELLENT | No interactivo, color + texto/icono | Ninguno | A |
| SegmentedControl | GOOD | Shared primitive, motion, roles, Reduce Motion | Opción compacta mide 40 dp dentro de track 44 | C |
| AppTopBar | GOOD | Safe area, household/role, simetría estructural | Centro puede competir con actions en anchos/font scale altos | B |
| FloatingNavigationBar | GOOD | 44 dp, ruta real, motion nítido, no haptics | QA físico iOS pendiente | A |
| AppScreen | GOOD | Safe area, keyboard, max width, scroll | Insets tab/FAB mágicos | C |
| ActionSheet | EXCELLENT | Content/regular/near-full, safe area, keyboard | Mantener current | A |
| Modal/overlays | GOOD | Sheets centralizados en flujos modernos | Algunas pantallas legacy usan Modal/Pressable propios | B |
| UndoToast | WEAK | Patrón canónico y acción Undo | `bottom:100`, valores crudos, Touchable sin label/state y pseudoanimación fija | C |
| EmptyState/ErrorState | GOOD | Jerarquía y recuperación reutilizable | Revisar wrapping con font scale alto | B |
| Skeleton | GOOD | Variantes coherentes y calma durante carga | Debe reflejar estructura real por screen | A/B |
| Snackbar/Family feedback | GOOD | Feedback inline y no modal | Dos implementaciones paralelas (Family y UndoToast) | E |
| FAB/Quick action | GOOD | Acción central estable, 50–56 dp | No ampliar jerarquía ni reubicar | A |
| Map controls | IMPROVE | Acciones explícitas, permisos y context navigation | Cuatro capas inferiores compiten en mapa pequeño/fallback | D |
| Viewer/HomeCloud | GOOD | Signed content, controles contextuales | Retorno/scroll y scaling físico aún no universalmente verificados | B/E |

### Evidencia cuantitativa

- 301 `Pressable/TouchableOpacity` directos: no son automáticamente defectos, pero escapan a garantías uniformes.
- Messages Conversation tiene 19 pressables directos y 29 atributos accessibility: alta cobertura, baja reutilización.
- Planner Tasks/Calendar e Inventory consumen ampliamente primitives actuales y no justifican reescritura.
- SimpleShell mantiene touch targets de 56 dp y jerarquía separada; **KEEP CURRENT**.

## 3. UVE score por screen/módulo

Orden de métricas: **Cl claridad · J jerarquía · D densidad · L legibilidad · T touch · A alcance · C consistencia · X accesibilidad · N continuidad · Q calidad**.

| Screen/módulo | Cl/J/D/L/T/A/C/X/N/Q | Total | Nivel | Primary / secondary / background | Reach | Diagnóstico concreto |
|---|---|---:|---|---|---|---|
| StandardShell + navbar | 5/4/4/4/5/4/4/4/5/5 | 44 | GOOD — POLISH ONLY | Ruta activa / acción central / chrome | EASY | Nítida y estable; falta device QA |
| SimpleShell | 5/5/4/5/5/5/4/5/4/4 | 46 | EXCELLENT — KEEP | Próxima acción / estado / soporte | EASY | 56 dp y lectura universal |
| Home Coordinador | 4/4/4/5/5/4/4/4/4/4 | 42 | GOOD | Hoy / próximo-atención / metadata hogar | NEUTRAL | Clara; cards pueden alinear mejor foco/CTA |
| Home Adulto | 4/4/4/4/5/4/4/4/4/4 | 41 | GOOD | Propias acciones / hogar / metadata | NEUTRAL | Mantener rol sin fragmentar sistema |
| Home Adolescente | 4/4/4/4/5/5/4/4/4/4 | 42 | GOOD | Lo propio / próximo / hogar | EASY | Rápida; verificar tono y densidad real |
| Home Adulto mayor | 5/5/4/5/5/5/4/5/4/4 | 46 | EXCELLENT | Acción esencial / explicación / extras | EASY | Primitives Simple cubren necesidad |
| Planner hub | 4/4/4/4/5/4/4/4/5/4 | 42 | GOOD | Tab actual / filtros-crear / metadata | NEUTRAL | Mucha capacidad, jerarquía aceptable |
| Planner Tareas | 5/4/4/4/5/4/4/4/5/4 | 43 | GOOD | Lista/estado / filtros / metadata | NEUTRAL | Acciones por estado bien resueltas |
| Task Detail | 4/4/3/4/5/3/4/4/5/4 | 40 | GOOD | Estado/acción / detalle / audit metadata | HARD | Vertical largo; evitar sumar CTAs fuertes |
| Task Form | 4/3/3/4/4/3/3/4/4/4 | 36 | IMPROVE | Título/guardar / contexto / opcionales | HARD | Formulario potente, densidad y teclado parciales |
| Planner Calendario | 4/4/4/4/5/4/4/4/5/4 | 42 | GOOD | Día/agenda / navegación / metadata | NEUTRAL | Shared segmented y proyección claras |
| Planner Planes lista | 4/4/4/4/5/4/4/4/4/4 | 41 | GOOD | Plan activo / crear-filtrar / metadata | NEUTRAL | Sin gap estructural demostrado |
| Plan Detail/estructura | 4/3/3/4/4/3/3/4/4/4 | 36 | IMPROVE | Outcome / estructura / metadata | HARD | Muchas acciones/estados; requiere slice propio |
| Responsabilidades | 4/4/4/4/5/4/5/4/4/4 | 42 | GOOD | Responsabilidad / acción / frecuencia | NEUTRAL | Primitives modernas; mantener |
| Inventario | 4/4/3/4/4/4/4/4/4/4 | 39 | GOOD — POLISH ONLY | Stock/alerta / buscar-filtrar / metadata | NEUTRAL | Alto volumen; chip hit area y retorno son gaps |
| Compras | — | N/A | SIN SCREEN CANÓNICA | — | — | No inventar UI ni score; autoridad productiva ausente |
| Finanzas Resumen | 4/3/3/4/5/3/4/4/4/4 | 38 | IMPROVE | Balance/scope / tabs / metadata | HARD | Dos niveles segmentados compiten arriba |
| Finanzas Movimientos/Pagos | 4/4/3/4/5/4/4/4/4/4 | 40 | GOOD | Estado/importe / filtros / metadata | NEUTRAL | Semántica fuerte; no inferir datos |
| Finanzas forms/management | 4/3/3/4/4/3/4/4/4/4 | 37 | IMPROVE | Importe/guardar / cuenta-categoría / ayuda | HARD | Densos, pero domain safety prima sobre compactar |
| Familia — Personas | 4/4/4/4/5/4/4/4/4/4 | 41 | GOOD | Integrantes / pending-invite / roles | NEUTRAL | Sheets/capabilities correctos |
| Familia — Mapa | 3/3/2/4/5/3/3/4/4/3 | 34 | IMPROVE | Mapa/selected context / overlays | EASY+COLLISION | Selector superior, share, estado, context rail y navbar compiten |
| Mensajes Inbox | 5/4/4/4/5/4/4/4/5/4 | 43 | GOOD | Conversación/unread / timestamp / preview | NEUTRAL | Clara y canónica |
| Conversación | 4/4/3/4/5/5/3/4/5/4 | 41 | GOOD | Mensajes/composer / states-actions / metadata | EASY | Preserva lectura; action sheet local muy densa |
| Actividad del hogar/feed | 3/3/2/4/4/3/2/3/3/2 | 29 | WEAK | Feed compite con hitos / reactions / timestamps | HARD | Demo/legacy, emojis y cards grandes; requiere decisión de producto |
| HomeCloud raíz/Archivos | 4/4/3/4/4/3/4/3/4/4 | 37 | IMPROVE | Colección / upload-filter / metadata | HARD | Retorno, touch y viewer necesitan QA focal |
| HomeCloud Recuerdos | 3/3/2/4/4/3/3/3/3/3 | 31 | IMPROVE | Recuerdo / tipo-fecha / metadata | HARD | Representaciones heterogéneas y densidad variable |
| HomeCloud Viewer | 4/4/4/4/4/3/4/4/3/4 | 38 | IMPROVE | Contenido / controles / metadata | NEUTRAL | Continuidad de retorno no completamente cerrada |
| Homi | — | N/A | SIN SCREEN PRODUCTIVA | — | — | Sólo extension point; no diseñar inteligencia falsa |
| Perfil | 4/4/3/4/4/3/4/4/4/4 | 38 | IMPROVE | Identidad / editar-H+ / metadata | HARD | Screen extensa; feedback inline correcto |
| Configuración Notificaciones | 5/4/4/4/5/4/4/4/5/4 | 43 | GOOD | Preferencia / explicación / metadata | NEUTRAL | Predecible y retorno al origen |
| Configuración Seguridad | 5/4/4/4/5/4/4/4/5/4 | 43 | GOOD | Estado/acción / explicación / metadata | NEUTRAL | No ocultar opciones |
| Más | 5/4/4/4/5/4/4/4/5/4 | 43 | GOOD | Destinos / descripciones / dev-only | NEUTRAL | Agrupación clara; harness sólo DEV |
| Auth/Login/Registro | 4/4/3/4/4/4/3/4/4/4 | 38 | IMPROVE | Credenciales/submit / recovery / legal | EASY | Formularios legacy aún no totalmente tokenizados |

## 4. Buyer principal analysis

| Flujo | ¿Reduce o aumenta carga mental? | Veredicto UVE |
|---|---|---|
| Home | Reduce: Hoy/Próximo/Atención ya condensan estado; la jerarquía no debe volverse feed variable | KEEP + microalineación |
| Planner | Reduce: estado y capacidad determinan acciones; forms/detail concentran demasiada profundidad pero es complejidad real | Pulir formularios, no simplificar reglas |
| Inventario | Reduce parcialmente: búsqueda y status son claros; targets compactos y retorno obligan precisión/memoria | Mejorar hit areas y continuidad |
| Finanzas | Reduce reconstrucción, pero scope + subtab + contenido compiten visualmente; un error es sensible | Separar jerarquías sin inferir defaults |
| Familia | Reduce coordinación mediante roles/pending; no sumar prominencia a administración cotidiana | KEEP capacidades; priorizar personas |
| Mapa | La cantidad de capas visibles aumenta carga y oculta el mapa, especialmente sin datos | Reordenar capas, nunca activar/recentrar solo |
| Mensajes | Reduce al convertir conversación en acción; composer y resultados están al alcance | Mantener; normalizar sheet y contraste |
| Feed | Aumenta: hitos, cards, emojis y reactions compiten sin una decisión principal clara | No pulir superficialmente; Product Truth primero |
| HomeCloud | Reduce búsqueda sólo mientras conserva colección; viewer/retorno aún exige reconstrucción | Slice de continuidad antes que decoración |
| Perfil/Settings | Mayormente neutro y predecible; Profile concentra muchas secciones | Mejorar escaneo, no esconder settings |
| SimpleShell | Reduce carga correctamente con targets y jerarquía mayores | KEEP CURRENT |

Conclusión del buyer principal: los mayores beneficios no vienen de “más aire”, sino de targets confiables, una sola acción primaria, jerarquía estable entre controles y contenido, y feedback ubicado sin tapar la siguiente acción.

## 5. Universal user analysis

| Perfil | CURRENT favorable | Fricción | Requirement común |
|---|---|---|---|
| Poco tecnológico | Labels en sheets, estados con texto, navegación estable | Icon-only navbar requiere labels accesibles; forms densos | Acción primaria inequívoca y recuperación explícita |
| Adolescente | Composer/nav rápidos, actions directas | Cards y formularios largos | Densidad eficiente, sin confirmaciones decorativas |
| Adulto mayor | SimpleShell 56 dp y copy directo | Standard chips/segments de 36–40 dp; metadata 11–12 | Hit area ≥44, scaling y contraste sin cambiar de producto |
| Power user | Contexto/filters y optimistic UI | Demasiado aire o sheets lentos penalizarían | No aumentar recorridos; preservar shortcuts actuales |
| Ocasional | Más/Settings y labels descriptivos | Feed/Mapa tienen varias capas o símbolos simultáneos | Jerarquía reconocible después de semanas |
| Frecuente | State preservation y nav persistente | Insets fijos/overlays pueden consumir viewport | Geometría estable y continuidad espacial |

No se recomienda una UI diferente por edad dentro de StandardShell. El sistema común debe cubrir 44 dp, escala tipográfica, lenguaje simple y estados redundantes por texto+color. SimpleShell sigue siendo la adaptación explícita de baja complejidad.

## 6. Anticipatory UX × UVE matrix

Se correlacionan todos los AX previamente aprobados como KEEP, IMPROVE o BUILD. Los deferred/rejected no generan requirements de implementación.

| AX | UVE requirement |
|---|---|
| AX-001 | Indicador activo visible al primer frame; UVE-16/17/18 |
| AX-002 | Glyph único nítido y movimiento sin rasterización; UVE-12/16 |
| AX-004 | Al volver, query/filtros deben reaparecer con foco visual estable; UVE-13/17 |
| AX-005 | Acción probable primero, pero destructiva visualmente subordinada; UVE-07/13/15 |
| AX-006 | Loading ocupa exactamente la geometría previa; UVE-10/18 |
| AX-007 | Next/Done y foco visible con campo no oculto por teclado; UVE-05/06/19/20 |
| AX-009 | Sheet proporcional con CTA alcanzable y safe area; UVE-02/06/14/20 |
| AX-010 | Undo visible cerca del resultado, 44 dp y con tiempo suficiente; UVE-05/18/19 |
| AX-011 | Home estable: un foco temporal, no tres primarias; UVE-01/13/15 |
| AX-013 | Complete accesible, claro y separado de acciones riesgosas; UVE-05/07/18 |
| AX-014 | Alerta muestra causa/CTA como foco y metadata subordinada; UVE-01/08/13 |
| AX-015 | Tab recordado mantiene el mismo anclaje visual; UVE-16/17 |
| AX-016 | Fecha sugerida visible como contexto editable, no escondida; UVE-13/18 |
| AX-017 | Plan preseleccionado visible junto al campo relevante; UVE-01/13 |
| AX-018 | Acción por estado ocupa prioridad primaria; Reactivar/Completar/Aprobar no compiten con Papelera; UVE-07/08/13 |
| AX-020 | Reanudar/descartar distingue primaria y destructiva; UVE-07/08/15 |
| AX-021 | Conflicto muestra estado canónico legible y siguiente paso; UVE-03/18 |
| AX-022 | Success inline estable y “Ver” secundario próximo; UVE-07/17/18 |
| AX-023 | Producto restaurado vuelve visible/en foco sin scroll brusco; UVE-13/17 |
| AX-024 | Prefill de reposición muestra producto/contexto antes del CTA; UVE-01/13/18 |
| AX-026 | Reponer destaca sólo en low/out; demás acciones no compiten; UVE-07/08/13 |
| AX-029 | Scope PERSONAL/HOUSEHOLD siempre visible y separado del contenido; UVE-01/08/13 |
| AX-031 | Pago due/paid usa texto+color y CTA seguro; UVE-07/08/09/13 |
| AX-032 | Restore/Undo alcanzable; eliminación permanente mantiene intención extra; UVE-05/07/18 |
| AX-033 | Guardado no cambia dimensiones y confirma inline; UVE-10/18 |
| AX-034 | Incoming no mueve viewport; indicador nuevo no tapa composer; UVE-15/17/18 |
| AX-035 | “Nuevos mensajes” visible, 44 dp y secundario frente al composer; UVE-05/07/14 |
| AX-036 | Tarea creada se confirma cerca del chat; “Ver tarea” accesible sin expulsar; UVE-07/17/18 |
| AX-040 | Archivo nuevo obtiene énfasis temporal sin reordenar colección; UVE-08/13/16 |
| AX-042 | Carpeta actual visible en upload y fácilmente editable; UVE-01/13 |
| AX-044 | Cámara de mapa permanece quieta tras gesto; controles no invaden viewport; UVE-06/15/17 |
| AX-045 | Sharing usa estado textual, contraste y CTA explícito; UVE-07/08/09/19 |
| AX-046 | Denial explica, ofrece retry/settings y conserva mapa usable; UVE-07/18/19 |
| AX-049 | Back conserva título/origen y transición predecible; UVE-01/17 |
| AX-050 | Cambio de household limpia foco/selección visual incompatible; UVE-13/17/18 |

## 7. Matriz previa a implementación

| Screen | Score | AX | Problems | KEEP | POLISH | CHANGE | Risk | Priority |
|---|---:|---|---|---|---|---|---|---|
| Shared primitives | 39 | 006/007/009/010/033 | Hit areas compactas, focus geometry, toast fijo | Tokens, loading, sheets | sizes/contrast | FilterChip/Segment/Input/Toast | MEDIUM | P0 |
| StandardShell | 44 | 001/002/015/049 | Insets screen/tab desacoplados | Navbar y topbar | métricas compartidas | AppScreen inset contract | MEDIUM | P0 |
| Home | 42 | 011/013/014 | Cards mezclan título/CTA en eje horizontal | temporal ordering, Undo | alineación y CTA | no structure | LOW | P1 |
| Planner list/calendar | 42 | 004/005/015/018 | Algunos targets/filter state | actions, segmented | touch/focus | no structure | LOW | P2 |
| Planner forms/details | 36–40 | 007/010/016/017/020/021/022 | Densidad, keyboard, múltiples acciones | lifecycle/capabilities | grouping/focus | form footer/detail action hierarchy | MEDIUM | P2 |
| Inventory | 39 | 023/024/026 | Chips 36, state/action proximity | stock semantics | hit area | no authority change | LOW | P3 |
| Compras | N/A | — | Sin authority/screen | nada | nada | nada | HIGH | DEFER |
| Finance | 37–40 | 029/031/032/033 | Scope+subtabs compiten, forms densos | semantic states/Undo | top hierarchy | shared finance header only | HIGH | P4/DEFER |
| Messages | 41–43 | 034/035/036 | Attach options parecen disabled; local Pressables | read/dedup/composer | contrast/touch | action grid primitive later | LOW | P5 |
| HomeCloud | 31–38 | 040/042 | heterogeneidad y retorno | authority/viewers | row/metadata | return context separately | MEDIUM | P6 |
| Family People | 41 | 050 | selector floating ocupa top | permissions/sheets | vertical rhythm | no structure | LOW | P7 |
| Family Map | 34 | 044/045/046 | overlay collision y mapa reducido | privacy/camera guards | spacing/contrast | coordinated bottom stack | MEDIUM | P7 |
| Feed | 29 | — | demo visual, emoji, múltiples focos | runtime isolated | none yet | Product Truth required | HIGH | DEFER |
| Homi | N/A | — | no product surface | hook only | none | none | HIGH | DEFER |
| Profile/Settings | 38–43 | 049 | Profile largo; settings bien | origin/feedback | sections | no hiding | LOW | P9 |
| SimpleShell | 46 | — | sin gap probado | all current | none | none | HIGH if touched | KEEP |

## 8. KEEP list

- Marca, paleta y semántica de color actuales.
- Escala principal de spacing/layout, radii y sombras.
- `AppButton` loading estable.
- `IconButton` 44 dp con label obligatorio.
- `StatusBadge`, Empty/Error/Skeleton actuales.
- `ActionSheet` con tamaños, safe area y teclado.
- Navbar global posterior al fix de nitidez.
- StandardShell y SimpleShell como contratos separados.
- Simple primitives de 56 dp.
- Jerarquía temporal de Home.
- Planner authority, acciones por estado, Evidence, review, drafts y conflictos.
- Finance authority, semantic states, Trash/Restore/Undo.
- Family capabilities y sheets.
- Presence explícita y guardas de cámara.
- Messaging sequence/read/reactions/Rich Media/Task Context.
- HomeCloud authority, signed previews y viewers existentes.
- Settings return-to-origin.

## 9. Problems priorizados

1. Hit area menor a 44 en FilterChip y opción compacta de SegmentedControl.
2. AppInput cambia grosor de borde al entrar en foco.
3. UndoToast no es safe-area/nav-aware, no usa toda la infraestructura accesible y su motion no es real.
4. AppScreen codifica 96/112 en vez de compartir métricas con la navegación.
5. Mapa superpone selector superior, share/recenter, estado, rail contextual y navbar; en fallback el área útil se percibe congestionada.
6. Tiles activos de adjuntos en Mensajes tienen `opacity:0.78`, muy cercana a disabled.
7. Cards de Home alternan alineación icono/título/CTA y pueden crear dos focos.
8. Planner Task Form y Plan structure son largos; focus/CTA inferior requieren QA con teclado y font scaling.
9. Finance presenta scope y subtab con peso parecido en la misma región.
10. Primitives estáticos impiden que dark theme sea realmente universal.
11. Senior typography existe pero no está conectada a la jerarquía general.
12. Feed/Actividad necesita decisión de producto, no un maquillaje UVE.
13. HomeCloud Recuerdos/Viewer no tienen todavía un estándar completo de metadata/retorno visual.
14. No existe una suite estática UVE que evite nuevos targets pequeños o valores arbitrarios en primitives.

## 10. UVE change candidates

### UVE-CHANGE-001 — Touch contract para controles compactos

- **Problema / módulo / screen / componente:** targets de 36–40 dp; transversal, Inventory/Planner/Family; `FilterChip`, `SegmentedControl`.
- **Buyer principal:** menos precisión física al filtrar/cambiar vista. **Beneficio universal:** adolescente rápido, adulto mayor seguro, power user no pierde densidad.
- **AX relacionado:** 004, 005, 015, 023, 029, 044.
- **CURRENT → TARGET → REAL GAP:** visual compacto = hit area compacto → visual 36–40 dentro de target ≥44 → falta wrapper/geometry separada.
- **Riesgo / complejidad:** LOW–MEDIUM / 2.
- **Implementación propuesta:** ampliar hit target sin inflar innecesariamente la píldora; mantener distribución y layouts.
- **Tests:** layout contract, a11y state, tap entre opciones adyacentes, font scaling, snapshots Android/iOS.
- **Clasificación:** C — COMPONENT FIX. **SELECTED.**

### UVE-CHANGE-002 — Focus sin micro-layout shift

- **Problema / módulo / screen / componente:** `AppInput` pasa border 1→2; todos los forms; `AppInput`.
- **Buyer principal:** foco más claro sin que el contenido “respire”. **Universal:** continuidad espacial y menor distracción.
- **AX:** 007, 016, 017, 020.
- **CURRENT → TARGET → GAP:** grosor variable → geometría constante con señal de foco → falta separar layout y visual focus.
- **Riesgo / complejidad:** LOW / 1.
- **Implementación:** reservar borde de 2 dp o usar capa de foco que no cambie padding; conservar error priority.
- **Tests:** dimensiones before/focus/error/disabled, keyboard y scaling.
- **Clasificación:** C. **SELECTED.**

### UVE-CHANGE-003 — UndoToast ergonómico y accesible

- **Problema:** fixed `bottom:100`, valores crudos, acción sin label/state, translate constante; transversal; `UndoToast`.
- **Buyer principal:** Undo debe aparecer donde pueda corregir sin tapar CTA. **Universal:** lectura, alcance y screen reader.
- **AX:** 010, 013, 032.
- **CURRENT → TARGET → GAP:** toast aproximado → safe-area/nav-aware, tokenizado, motion real y acción ≥44 → primitive quedó legacy.
- **Riesgo / complejidad:** MEDIUM / 3.
- **Implementación:** props de bottom inset/host, InteractivePressable, live region/alert apropiado, fade+translate Reduce Motion-safe.
- **Tests:** timer cleanup, Undo una vez, nav/sheet layering, a11y, keyboard.
- **Clasificación:** C. **SELECTED.**

### UVE-CHANGE-004 — Bottom inset contract compartido

- **Problema:** `AppScreen` usa 96/112 independientes de navbar; todas las listas StandardShell.
- **Buyer principal:** evita que el último ítem/CTA quede tapado. **Universal:** responsive robustness.
- **AX:** 001, 003, 004, 017, 034.
- **CURRENT → TARGET → GAP:** magic numbers → métrica derivada de navbar + safe area + breathing → falta fuente común sin acoplar screens a navigator.
- **Riesgo / complejidad:** MEDIUM / 3.
- **Implementación:** exportar métricas semánticas desde theme/navigation geometry y consumirlas en AppScreen; no leer navegación global.
- **Tests:** small/tall Android, iPhone inset, keyboard hidden/shown, last-row visibility.
- **Clasificación:** C. **SELECTED con rollout focal primero.**

### UVE-CHANGE-005 — Stack inferior coordinado del mapa

- **Problema:** estado/card contextual + Integrantes/Lugares + navbar compiten; Familia/Mapa; Presence layout.
- **Buyer principal:** el mapa deja de ser el foco y cuesta coordinar. **Universal:** menos solapamiento y targets distinguibles.
- **AX:** 043 diferido, 044, 045, 046.
- **CURRENT → TARGET → GAP:** offsets técnicamente calculados, pero cuatro superficies visibles → una pila con slots mutuamente excluyentes y separación tokenizada → falta priorización visual.
- **Riesgo / complejidad:** MEDIUM / 3.
- **Implementación:** no tocar MapView/camera/presence; definir zona reservada, compactar estado vacío y ocultar card contextual cuando no existe selección.
- **Tests:** mapa/fallback, locations 0/1/n, places/members card, safe area, nav, sheet, gestures.
- **Clasificación:** D — SCREEN STRUCTURE. **SELECTED para prototipo + QA antes de merge.**

### UVE-CHANGE-006 — Contraste de acciones de adjuntos

- **Problema:** `actionOption` activa tiene opacity 0.78 y parece disabled; Mensajes Conversation.
- **Buyer principal:** duda qué está habilitado. **Universal:** estado inmediato sin depender de lectura secundaria.
- **AX:** 005, 036.
- **CURRENT → TARGET → GAP:** todas las tiles apagadas → activas al 100%, disabled claramente separado → style base mezcla calma con disabled.
- **Riesgo / complejidad:** LOW / 1.
- **Implementación:** quitar opacity base, pressed controlado y disabled semántico; sin cambiar acciones.
- **Tests:** enabled/pressed/disabled, contrast, TalkBack, M2 contracts.
- **Clasificación:** B — MICRO POLISH. **SELECTED.**

### UVE-CHANGE-007 — Jerarquía consistente de Home summary cards

- **Problema:** título, icono y CTA cambian de alineación/peso entre Hoy/Próximo/Qué cambió; Home.
- **Buyer principal:** tarda un instante extra en identificar estado vs acción. **Universal:** escaneo estable.
- **AX:** 011, 014.
- **CURRENT → TARGET → GAP:** cards claras pero patrón variable → header de card consistente, CTA secundario alineado → falta primitive local compartido.
- **Riesgo / complejidad:** LOW / 2.
- **Implementación:** sólo layout; conservar copy, orden y navegación.
- **Tests:** empty/populated/long text, roles, font scaling.
- **Clasificación:** B. **SELECTED después de components P0.**

### UVE-CHANGE-008 — Footer/focus de formularios Planner

- **Problema:** forms extensos, CTA/foco lejos y densidad alta; Task/Plan forms.
- **Buyer principal:** aumenta recorrido, pero simplificar podría ocultar reglas. **Universal:** teclado y alcance.
- **AX:** 007, 016, 017, 020, 022.
- **CURRENT → TARGET → GAP:** form correcto pero largo → grouping, Next/Done y CTA visible sin tapar campos → requiere inventario campo por campo.
- **Riesgo / complejidad:** MEDIUM / 4.
- **Implementación:** un form por slice, sin cambiar schema/validation.
- **Tests:** keyboard, errors, draft recovery, Evidence, font scale.
- **Clasificación:** E — DEFERRED hasta auditoría focal de Planner forms.

### UVE-CHANGE-009 — Jerarquía de navegación Finanzas

- **Problema:** PERSONAL/HOGAR y Resumen/Movimientos/Pagos tienen peso semejante; Finance.
- **Buyer principal:** scope sensible puede leerse como otro tab. **Universal:** reduce imputación contextual incorrecta.
- **AX:** 029, 031, 033.
- **CURRENT → TARGET → GAP:** dos segmented peers → scope explícito y subnav subordinada → falta validar datos cargados y todos los entry points.
- **Riesgo / complejidad:** HIGH / 4.
- **Implementación:** explorar visualmente sin cambiar state/routes; no decidir ahora.
- **Tests:** every scope/tab, deep link, forms, font scale, privacy.
- **Clasificación:** E — DEFERRED.

### UVE-CHANGE-010 — Dynamic theme completo en primitives

- **Problema:** provider dark existe pero primitives importan colores estáticos; transversal.
- **Buyer principal:** inconsistencia nocturna. **Universal:** contraste/coherencia.
- **AX:** transversal indirecto.
- **CURRENT → TARGET → GAP:** tema parcial → cada primitive consume active theme → migración extensa con riesgo visual.
- **Riesgo / complejidad:** HIGH / 5.
- **Implementación:** migración por primitive con visual regression, nunca big bang.
- **Tests:** light/dark every state, screenshots, contrast.
- **Clasificación:** E — DEFERRED como programa propio.

### UVE-CHANGE-011 — Política universal de font scaling

- **Problema:** senior tokens no conectados y layout no probado con escalas altas; transversal/Simple.
- **Buyer principal:** metadata o CTA pueden truncar. **Universal:** adulto mayor/accesibilidad.
- **AX:** todos los flows con return/action.
- **CURRENT → TARGET → GAP:** RN scaling por defecto + Simple custom → política documentada y layouts resilientes → falta test matrix y Product decision sobre Standard vs Simple.
- **Riesgo / complejidad:** HIGH / 5.
- **Implementación:** primero tests y wrapping; no activar seniorTypography globalmente.
- **Tests:** 100/130/160/200%, small width, TalkBack/VoiceOver.
- **Clasificación:** F — REQUIERE DECISIÓN / DEFERRED.

### UVE-CHANGE-012 — Actividad del hogar product truth antes de polish

- **Problema:** hitos, emojis, feed y reactions compiten; Feed.
- **Buyer principal:** agrega ruido y no define siguiente acción. **Universal:** estética/demo no equivale a claridad.
- **AX:** ninguno aprobado.
- **CURRENT → TARGET → GAP:** demo heterogénea → objetivo y gramática reales antes de UI → falta Product Truth.
- **Riesgo / complejidad:** HIGH / 5.
- **Implementación:** ninguna en UVE Parte 2.
- **Tests:** no aplican hasta decisión.
- **Clasificación:** F — REJECTED para este programa.

### UVE-CHANGE-013 — Metadata/return pattern de HomeCloud

- **Problema:** Files/Memories/Viewer varían densidad y retorno; HomeCloud.
- **Buyer principal:** reconstruye colección/origen. **Universal:** escaneo y continuidad.
- **AX:** 039 diferido, 040, 042.
- **CURRENT → TARGET → GAP:** surfaces productivas heterogéneas → patrón de row/tile + return descriptor → mezcla UX y navegación aún no cerrada.
- **Riesgo / complejidad:** MEDIUM–HIGH / 4.
- **Implementación:** separar continuity slice de visual polish.
- **Tests:** folder/album/search/viewer/delete/move/font scale.
- **Clasificación:** E — DEFERRED.

### UVE-CHANGE-014 — Guardrails UVE automatizados

- **Problema:** regresiones nuevas pueden introducir target pequeño o magic geometry; transversal/tests.
- **Buyer principal:** beneficio indirecto: consistencia sostenida. **Universal:** previene degradación.
- **AX:** 001, 002, 006, 009, 035.
- **CURRENT → TARGET → GAP:** auditoría manual → contratos focales de primitives y métricas → falta suite, no hace falta lint global ruidoso.
- **Riesgo / complejidad:** LOW / 2.
- **Implementación:** tests estructurales sobre primitives, no prohibición absoluta de números.
- **Tests:** la suite es el guardrail; debe fallar con fixture menor a 44.
- **Clasificación:** C. **SELECTED.**

## 11. Selected changes

Seleccionados para una futura Parte 2, en orden:

1. `UVE-CHANGE-014` guardrails primero.
2. `UVE-CHANGE-001` touch targets compactos.
3. `UVE-CHANGE-002` focus geometry de AppInput.
4. `UVE-CHANGE-003` UndoToast.
5. `UVE-CHANGE-004` bottom inset contract con rollout focal.
6. `UVE-CHANGE-006` contraste de attachments en Mensajes.
7. `UVE-CHANGE-007` jerarquía de Home cards.
8. `UVE-CHANGE-005` mapa como slice independiente con prototipo/QA.

Todos cumplen: contexto actual, menos esfuerzo, sin decisiones sensibles, sin cambios de permisos/ownership y resultado corregible.

## 12. Deferred / rejected

### Deferred

- Planner forms/footer hasta auditoría de campos y teclado.
- Finanzas scope/subnav hasta cargar y validar todos los estados reales.
- Dark theme universal como migración independiente.
- Font scaling/senior typography global hasta definir política.
- HomeCloud metadata/return hasta cerrar retorno canónico.
- Shopping y Homi por ausencia de autoridad/surface productiva.

### Rejected

- “Modernizar” Activity Feed sin Product Truth.
- Más terracota como sustituto de jerarquía.
- Aumentar indiscriminadamente aire, radios o sombras.
- Mover todas las acciones al fondo.
- Crear componentes alternativos por edad dentro de StandardShell.
- Reemplazar primitives actuales que ya puntúan GOOD/EXCELLENT.

## 13. Implementation roadmap (Parte 2 propuesta)

| Slice | CURRENT | TARGET | Files probables | Validación / stop gate |
|---|---|---|---|---|
| UVE-P0A Guardrails | Sin suite UVE | Contratos de geometry/touch | `tests/`, theme/primitives read-only | Tests inicialmente describen CURRENT, luego cada fix |
| UVE-P0B Touch/focus | 36–40 dp y border shift | ≥44 hit + geometry estable | FilterChip, SegmentedControl, AppInput | TS/lint/contracts + font scale simulator |
| UVE-P0C Feedback | UndoToast fixed/legacy | Safe-area/nav/a11y aware | UndoToast + hosts consumidores | Home + Finance undo, keyboard, screen reader |
| UVE-P0D Insets | 96/112 mágicos | Shared semantic metrics | theme/AppScreen/navbar metrics | Last row visible Android/iOS; no map regression |
| UVE-P1 Home | Cards variables | Header/CTA rhythm compartido | HomePlannerSections/local component | Empty/populated/roles + visual QA |
| UVE-P5 Messages | Enabled action opacity 0.78 | State contrast inequívoco | Conversation action styles | M2 contracts + enabled/disabled QA |
| UVE-P7 Map | Stack congestionado | Slot inferior coordinado | Family/Presence layout only | No camera/presence changes; fallback+native map QA |

Cada slice debe cerrar TypeScript, lint, tests focales, tests del dominio y visual/device QA antes de comenzar el siguiente. No se propone un `UVEManager`, design system paralelo ni migración masiva.

## 14. Parte 1 status

`UVE PARTE 1 — AUDIT + SELECTION COMPLETE`

- Auditoría: completa sobre CURRENT disponible.
- Implementación: **NO INICIADA**, por stop gate solicitado.
- Evidencia física: Android simulator para Home, Planner, Familia/Mapa, Más y Finance loading; otras superficies auditadas por código/contratos.
- `NEEDS_DEVICE_QA`: iPhone safe areas, font scaling alto, TalkBack/VoiceOver, teclado físico/IME, Map nativo y reachability real.

