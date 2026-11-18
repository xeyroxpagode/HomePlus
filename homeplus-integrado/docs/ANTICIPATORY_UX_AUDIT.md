# HOMePLUS — Anticipatory UX audit and implementation record

Fecha: 2026-10-14  
Alcance: frontend móvil CURRENT, sin cambios de backend, permisos, RLS, contratos ni arquitectura de navegación.

## 1. Navbar regression

### Root cause

La regresión no provenía de blur, `renderToHardwareTextureAndroid`, `shouldRasterizeIOS`, bitmap caching ni remount. `HomePlusIcon` usa un glyph vectorial de Ionicons. El polish anterior dibujaba dos glyphs idénticos superpuestos —activo e inactivo— con opacidades inversas, dentro de otro `Animated.View` con escala `1 → 1.025`. En Android, la combinación de alpha + escala de glyph produjo una capa intermedia antialiasada/offscreen que se percibía borrosa hasta finalizar la transición.

### Fix

- Un único glyph por destino durante todos los frames.
- Eliminadas la escala animada del icono y las dos capas cross-fade.
- El movimiento espacial permanece en una sola superficie activa, con `translateX` retargeteable.
- Color derivado directamente de la ruta real; opacidad discreta `0.82 → 1` sin cambio de geometría.
- Press de navbar sin transform (`pressScale={1}`), con feedback de opacidad; haptic sigue en `none`.
- Se conservan 44 dp de indicador, 300 ms y `cubic-bezier(0.22, 1, 0.36, 1)`.

Archivos: `front/mi-front-limpio/components/ui/FloatingNavigationBar.tsx` y espejo Expo Go.

Evidencia: TypeScript y ESLint de ambos fronts; contrato estático; 30 cambios rápidos en Android API 35 terminaron con ruta e indicador correctos, sin iconos duplicados. Nitidez táctil en hardware físico: `NEEDS_DEVICE_QA`.

## 2. CURRENT audit por módulo

| Área | A. Ya anticipa | B. Parcial | C. KEEP CURRENT | D–J. Gap y criterio |
|---|---|---|---|---|
| Navegación global | Tab activo deriva de la ruta, safe area, teclado, destino central, Reduce Motion | Algunas listas dependen del montaje para conservar estado | StandardShell/SimpleShell separados; no añadir navbar a SimpleShell | Evitar estados paralelos, desmontajes y retornos genéricos. Navbar corregida sin tocar rutas.
| UI compartida | `AppButton` mantiene dimensiones en loading; `ActionSheet` adapta altura/safe area/teclado; `UndoToast` reusable | Undo no cubre todos los dominios | Loading estable y sheet actual | Expandir sólo si existe mutación reversible y contrato canónico.
| Home | Agrupa Hoy/Próximo/Atención; prioridades temporales; completar Task con Undo | Varias cards abren raíz Planner, no entidad/origen exacto | Orden temporal predecible; no convertir Home en feed mágico | Deep link exacto exige resolver correctamente retorno a Home; se difiere antes que romper historial.
| Planner/Tareas | `source`, `returnTo`, presets, due date contextual, today/tomorrow, capacidades, acción primaria por estado, conflictos canónicos | Scroll/filtro dependen de mantener screen montada | Planner es autoridad; Complete/Claim/Approve/Reactivate contextuales | Mejorar restauración durable sólo con lifecycle explícito; no tocar Evidence/review/audit.
| Planner/Calendario/Planes | Tab persistido por usuario/hogar, fecha y Plan contextuales, drafts/revisions | Confirmación posterior a creación no siempre ofrece próximo paso | Draft privado y publicación canónica | No añadir automatismos que publiquen o asignen.
| Inventario | Búsqueda/categoría, low/out-of-stock, edición y restock task | Retorno exacto, filtros y feedback aún locales | Reglas actuales de stock | Prefill de compras depende de autoridad Shopping aún fuera de alcance.
| Compras | Categoría Planner `shopping`; no se encontró autoridad Shopping productiva independiente | Flujo completo no existe | No inventar fuente paralela | Cualquier lista/compra contextual queda diferida hasta contrato real.
| Finanzas | Contexto PERSONAL/HOUSEHOLD, account/category drafts, correcciones, Trash/Restore, Undo en varias superficies | Persistencia de algunos filtros es local | Dominio, RLS y ledger financiero intactos | Prefill sólo inequívoco; no inferir datos sensibles.
| Familia | Roles/capabilities canónicos, feedback contextual | Selección local puede perderse si remonta | Permisos/ownership | No optimizar para coordinador a costa de vigilancia.
| Mapa/Presence | Separa permiso de sharing, `mapWasMovedByUser`, center/fitted guards, miembro seleccionado | Retorno/selección no siempre durable | No recentrar tras gesto; no activar sharing | Sólo preservar cámara/selección con lifecycle seguro.
| Mensajes/Feed | Sequence, optimistic/HTTP/realtime dedup, read cursors, reactions, Rich Media, Task Context y Message→Task | Un efecto llevaba siempre al final al llegar mensajes; Task creada no ofrecía próximo paso | Contratos canónicos y Planner authority | Slice implementado: preservar lectura y confirmación inline con “Ver tarea”.
| HomeCloud/Archivos/Recuerdos | Folders/albums/capabilities, signed previews, upload engine, memories por tipo | Folder/query/scroll/viewer return dependen del screen vivo | Authority y Office Viewer | Persistencia robusta requiere estado de retorno tipado; no duplicar cache.
| Homi | Existe hook de `MessageActionSuggestion` sin AI falsa | No hay producto inteligente productivo | Mantener sugerencias explícitas/no automáticas | Diferir hasta Product Truth y backend real.
| Perfil | Edición modal, feedback inline, H+ summary | Contexto de retorno no cubre cada entrada | Estado canónico y accesibilidad | Defaults seguros únicamente.
| Configuración | `originTab` para Notificaciones/Seguridad | No toda subsección tiene el mismo descriptor | Retorno al tab de origen | No esconder settings ni decidir por el usuario.
| Auth/household/roles | Hidratación, household activo y capabilities compartidas | Estados locales deben limpiarse al cambiar household | Auth/RLS/roles | Toda restauración debe estar scoped por usuario + household para evitar contexto viejo.

## 3. Catálogo de exactamente 50 ideas

Escalas: BP=`valor/comodidad/riesgo frustración`; BS=`valor/facilidad/riesgo confusión`; UX=`impacto`; C=`complejidad`; RT=`riesgo técnico`; RP=`riesgo producto`.

| ID / nombre | Problema CURRENT · módulos | Contexto conocido | Comportamiento exacto propuesto | Nunca automático | BP · BS | UX/C/RT/RP · privacidad | CURRENT · dependencias · decisión · justificación |
|---|---|---|---|---|---|---|---|
| AX-001 Ruta activa continua | Un shell puede hidratar o volver de background; Global | Ruta real, índice, insets | Indicador nace y termina en el route activo, retargetea taps | Estado paralelo o push duplicado | 4/5/1 · 4/5/1 | 4/2/2/1 · LOW | YA IMPLEMENTADO BIEN · navigator · KEEP · evita desincronización |
| AX-002 Movimiento nítido navbar | Glyph borroso durante transición; Global | Route e índice anterior/nuevo | Un glyph nítido + indicador único móvil | Rasterizar o reducir calidad | 4/5/2 · 4/5/1 | 4/2/2/1 · LOW | EXISTE PERO REQUIERE POLISH · Animated · IMPROVE · regresión demostrada |
| AX-003 Restauración de scroll tipada | Detail→lista puede perder posición; transversal | Route/origen/list key/offset | Guardar offset por screen instance y restaurar sólo al volver | Restaurar tras cambio de dataset/hogar | 5/5/1 · 4/5/1 | 5/4/3/2 · LOW | IMPLEMENTADO PARCIAL · listas+navegación · DEFER · requiere lifecycle común |
| AX-004 Búsqueda y filtros al volver | Rehacer filtros tras Detail; listas | Query/filtros/origen | Mantener filtros mientras viva la sesión de lista | Persistir filtros obsoletos entre hogares | 5/5/1 · 4/5/1 | 5/3/2/2 · LOW | IMPLEMENTADO PARCIAL · screen state · IMPROVE · alto valor, slice por dominio |
| AX-005 Acción contextual prioritaria | Menús genéricos obligan a releer estado; transversal | Estado/capabilities | Ordenar primero la acción válida más probable | Ejecutarla ni ocultar alternativas | 5/5/1 · 5/5/1 | 5/3/2/2 · LOW | IMPLEMENTADO PARCIAL · domain adapters · IMPROVE · reduce decisión |
| AX-006 Loading sin salto | Botón podría cambiar tamaño; transversal | Dimensión/contenido actual | Mantener contenido invisible como medida y spinner interno | Bloquear layout global | 4/5/1 · 4/5/1 | 4/1/1/1 · LOW | YA IMPLEMENTADO BIEN · AppButton · KEEP · profesional y reusable |
| AX-007 Teclado Next/Done | Formularios largos fuerzan taps; forms | Orden lógico/campo válido | `returnKeyType`, focus siguiente y Done coherente | Saltar validación o guardar | 4/4/2 · 4/4/2 | 4/3/2/1 · LOW | IMPLEMENTADO PARCIAL · inputs/refs · IMPROVE · por formulario |
| AX-008 Menú anclado al origen | Acción puede aparecer lejos del dedo; popovers | Layout del trigger | Posicionar menú junto al trigger con fallback seguro | Tapar teclado/área crítica | 3/4/1 · 4/4/1 | 3/4/3/2 · LOW | IMPLEMENTADO PARCIAL · measurement/overlay · DEFER · sheets actuales son estables |
| AX-009 Sheet proporcional | Sheets sobredimensionados agregan recorrido; transversal | Altura de contenido/insets | Usar tamaños content/regular/near-full existentes | Cambiar de alto impredeciblemente | 4/5/1 · 4/5/1 | 4/1/1/1 · LOW | YA IMPLEMENTADO BIEN · ActionSheet · KEEP · ya resuelto |
| AX-010 Undo para reversible | Confirmaciones frenan acciones recuperables; transversal | Mutation inverse/id/version | Ejecutar, mostrar Undo temporal y reconciliar canónico | Undo para irreversible o sin contrato | 5/5/2 · 4/5/2 | 5/4/3/3 · MEDIUM | IMPLEMENTADO PARCIAL · domain inverse · IMPROVE · sólo donde es seguro |
| AX-011 Home temporal estable | Home podría saturarse o moverse solo; Home | Hoy/próximo/atención | Mantener secciones temporales y acciones relevantes estables | Feed “inteligente” impredecible | 5/5/1 · 5/5/1 | 5/1/1/1 · LOW | YA IMPLEMENTADO BIEN · Home projections · KEEP · reduce carga mental |
| AX-012 Home→entidad exacta | Card abre raíz del módulo; Home/Planner | Entity id/origen | Abrir Detail exacto y volver a Home/offset | Cambiar return contract incompleto | 5/5/1 · 4/5/1 | 5/3/3/2 · LOW | IMPLEMENTADO PARCIAL · typed return · DEFER · retorno Home no está cerrado |
| AX-013 Completar en Home + Undo | Entrar a Planner para una acción breve; Home/Planner | Task/capability/status | Completar inline y ofrecer Undo canónico | Completar sin permiso | 5/5/1 · 5/5/1 | 5/2/2/2 · MEDIUM | YA IMPLEMENTADO BIEN · Planner mutation · KEEP · flujo correcto |
| AX-014 Atención abre causa | “Atención” genérica obliga investigar; Home | Alerta + entity id | CTA lleva a causa concreta con copy seguro | Revelar datos sin permiso | 5/5/1 · 4/4/2 | 5/3/3/2 · MEDIUM | IMPLEMENTADO PARCIAL · projections/routes · IMPROVE · por tipo |
| AX-015 Tab Planner recordado | Reabrir siempre en Tareas rompe continuidad; Planner | User/household/revision | Restaurar tab canónico scoped | Usar preferencia de otro household | 4/5/1 · 4/5/1 | 4/2/2/1 · LOW | YA IMPLEMENTADO BIEN · preferences · KEEP · guardas actuales sólidas |
| AX-016 Crear desde fecha | Repetir fecha al crear desde Calendario; Planner | Día seleccionado | Abrir Task con due date sugerida/editable | Guardar sin confirmación | 5/5/1 · 4/5/1 | 5/2/2/1 · LOW | YA IMPLEMENTADO BIEN · initialDueDate · KEEP · contexto obvio |
| AX-017 Crear dentro de Plan | Repetir Plan de origen; Planner | planId/goal | Preseleccionar Plan, editable antes de guardar | Publicar/asignar | 5/5/1 · 4/5/1 | 5/2/2/1 · LOW | YA IMPLEMENTADO BIEN · form request · KEEP |
| AX-018 Acción Task por estado | Mismo menú pese a estado; Planner | status/evidence/review/capability | Pendiente→Completar; completada→Reactivar; review→Aprobar | Omitir acciones permitidas | 5/5/1 · 5/5/1 | 5/2/2/2 · MEDIUM | YA IMPLEMENTADO BIEN · task adapters · KEEP |
| AX-019 Task list retorno exacto | Filter/offset pueden perderse; Planner | Filter/query/offset/task id | Volver al mismo conjunto y posición si revisión coincide | Restaurar sobre lista incompatible | 5/5/1 · 4/5/1 | 5/4/3/2 · LOW | IMPLEMENTADO PARCIAL · list lifecycle · DEFER |
| AX-020 Draft de formulario continuo | Picker/teclado/back puede perder entrada; Planner | Draft local/owner/version | Mantener draft y ofrecer reanudar/descartar | Publicar draft | 5/5/2 · 3/3/2 | 5/3/2/2 · MEDIUM | YA IMPLEMENTADO BIEN · private drafts · KEEP |
| AX-021 Conflicto con estado canónico | Retry puede sobrescribir cambio remoto; Planner | version/canonical response | Explicar conflicto y recargar estado autoritativo | Last-write-wins visual | 5/4/2 · 4/4/2 | 5/3/3/2 · MEDIUM | YA IMPLEMENTADO BIEN · Planner conflict · KEEP |
| AX-022 Post-create cercano | Tras crear, usuario busca la entidad; Planner | Task/Plan recién creado/origen | Permanecer en origen y ofrecer “Ver” inline | Navegar automáticamente | 4/5/1 · 4/5/1 | 4/2/2/1 · LOW | IMPLEMENTADO PARCIAL · result id · IMPROVE |
| AX-023 Inventario conserva vista | Editar y volver obliga buscar producto; Inventario | Query/category/item/offset | Conservar filtro y volver al ítem | Retener entre hogares | 5/5/1 · 4/5/1 | 5/3/2/2 · LOW | IMPLEMENTADO PARCIAL · list state · IMPROVE |
| AX-024 Agotado→reposición prefill | Reescribir producto para pedir reposición; Inventario/Planner | Product name/location/status | Crear Task de reposición prellenada y editable | Inventar cantidad/precio/comprador | 5/5/1 · 5/5/1 | 5/2/2/2 · LOW | IMPLEMENTADO PARCIAL · Planner create · IMPROVE |
| AX-025 Cantidad con Undo | Error de tap obliga editar otra vez; Inventario | Previous quantity/version | Actualizar y Undo si backend admite inverse segura | Undo con stock ya cambiado por otro | 4/5/2 · 4/5/2 | 4/4/3/3 · MEDIUM | NO IMPLEMENTADO · concurrency contract · DEFER |
| AX-026 CTA por bajo stock | Card no prioriza siguiente paso; Inventario | Threshold/current qty | Mostrar “Reponer” primero sólo cuando low/out | Crear compra sola | 5/5/1 · 5/5/1 | 5/2/2/2 · LOW | IMPLEMENTADO PARCIAL · status projection · IMPROVE |
| AX-027 Producto→Shopping | No existe flujo Shopping canónico completo | Product id/name | Prefill futuro Shopping authority | Crear lista paralela | 5/5/1 · 5/5/1 | 5/3/3/4 · MEDIUM | NO IMPLEMENTADO · Shopping authority · DEFER |
| AX-028 Compra→stock sugerido | Después de comprar hay doble carga | Shopping/Inventory | Ofrecer actualización controlada post-compra | Modificar stock automáticamente | 5/5/2 · 4/4/2 | 5/4/4/4 · MEDIUM | NO APLICA · Shopping lifecycle · DEFER |
| AX-029 Contexto financiero persistente | Rehacer PERSONAL/HOUSEHOLD/período; Finanzas | User/household/tab/filter | Mantener contexto scoped al retorno | Mezclar hogares o esconder scope | 5/5/1 · 3/4/2 | 5/3/3/3 · HIGH | IMPLEMENTADO PARCIAL · finance state · IMPROVE |
| AX-030 Cuenta/categoría inequívoca | Repetir selección frecuente; Finanzas | Origen explícito/última cuenta válida | Prefill sólo desde origen inequívoco y visible | Inferir gasto sensible | 4/4/3 · 2/3/4 | 3/3/3/4 · HIGH | IMPLEMENTADO PARCIAL · explicit origin · DEFER |
| AX-031 Acción según pago | Menú genérico exige interpretar due/paid | Finanzas | Payment status/capability | Due→Registrar; paid→Ver/corregir; overdue→resolver | Pagar, corregir o refund automático | 5/5/1 · 4/5/1 | 5/3/3/3 · HIGH | IMPLEMENTADO PARCIAL · finance lifecycle · IMPROVE |
| AX-032 Trash/Restore + Undo | Confirmaciones/reconstrucción; Finanzas | Trash id/version | Usar Undo existente y Restore canónico | Borrar definitivamente | 5/5/1 · 4/5/1 | 5/2/2/2 · HIGH | YA IMPLEMENTADO BIEN · UndoToast/domain · KEEP |
| AX-033 Guardado financiero inline | Modal extra corta continuidad; Finanzas | Mutation result/origin | Feedback inline estable y mantener contexto | Saltar revisión de montos | 4/5/1 · 3/4/2 | 4/2/2/2 · HIGH | IMPLEMENTADO PARCIAL · sheet result · IMPROVE |
| AX-034 Mensajes preserva lectura | Incoming forzaba scroll al final; Mensajes | Offset/near-bottom/sender | Sólo seguir si ya está abajo o mensaje propio | Mover al usuario leyendo historia | 5/5/1 · 5/5/1 | 5/2/2/1 · LOW | EXISTE PERO REQUIERE POLISH · FlatList · IMPROVE · implementado |
| AX-035 Salto explícito a nuevos | Preservar scroll podía ocultar llegada | Mensajes | Hay incoming debajo | Pill “Nuevos mensajes” junto al composer | Abrir/marcar interacción por sí sola | 5/5/1 · 5/5/1 | 5/2/1/1 · LOW | NO IMPLEMENTADO · AX-034 · BUILD · implementado |
| AX-036 Message→Task próximo paso | Task se creaba y modal desaparecía | Mensajes/Planner | task id/title/origen chat | Confirmación inline con “Ver tarea”, sin salir | Navegar automáticamente | 5/5/1 · 5/5/1 | 5/2/2/1 · LOW | IMPLEMENTADO PARCIAL · canonical create/link · IMPROVE · implementado |
| AX-037 Acciones según message type | Menú puede mostrar opciones irrelevantes | Mensajes | type/delivery/capability | Ordenar Abrir/Reproducir/Reaccionar/Convertir | Ejecutar acción | 4/5/1 · 5/5/1 | 4/3/2/2 · LOW | IMPLEMENTADO PARCIAL · renderer/actions · DEFER · evitar ampliar M2 |
| AX-038 Draft por conversación | Cambiar chat puede perder texto | Mensajes | conversation id/local draft | Cache efímera scoped y limpiar al enviar/logout | Sincronizar texto privado al backend | 5/5/1 · 4/5/1 | 5/4/3/3 · MEDIUM | NO IMPLEMENTADO · secure lifecycle · DEFER |
| AX-039 HomeCloud retorno exacto | Viewer→colección puede perder folder/query/scroll | HomeCloud | folder/query/sort/item/offset | Return descriptor restaura vista compatible | Restaurar tras borrar/mover colección | 5/5/1 · 4/5/1 | 5/4/3/2 · MEDIUM | IMPLEMENTADO PARCIAL · typed return · DEFER |
| AX-040 Upload revela resultado | Tras upload hay que buscar archivo | HomeCloud | folder + new file id | Permanecer en colección, enfocar/highlight discreto | Abrir archivo automáticamente | 4/5/1 · 4/5/1 | 4/3/2/2 · MEDIUM | IMPLEMENTADO PARCIAL · upload result · IMPROVE |
| AX-041 Viewer anterior/siguiente | Navegar atrás para cada archivo | HomeCloud | Colección ordenada actual | Controles previo/siguiente sin perder índice | Preload masivo | 3/4/2 · 4/4/2 | 3/4/3/3 · MEDIUM | NO IMPLEMENTADO · viewer contract · DEFER |
| AX-042 Upload preselecciona folder | Repetir carpeta actual | HomeCloud | current folder/permissions | Folder actual sugerido y editable | Mover/compartir solo | 5/5/1 · 4/5/1 | 5/2/2/1 · MEDIUM | YA IMPLEMENTADO BIEN · upload intake · KEEP |
| AX-043 Miembro seleccionado continuo | People↔Map obliga reselección | Familia/Mapa | selected membership + permission | Mantener selección mientras siga visible/autorizada | Seleccionar/rastrear sin gesto | 4/5/2 · 4/5/2 | 4/3/3/3 · HIGH | IMPLEMENTADO PARCIAL · shared local state · DEFER |
| AX-044 Viewport del mapa respetado | Recentrado destruye orientación | Mapa | user pan/camera/visible members | No recentrar tras gesto; centrar sólo explícito/inicial seguro | Seguir movimiento automáticamente | 5/5/1 · 5/5/1 | 5/2/2/2 · HIGH | YA IMPLEMENTADO BIEN · map guards · KEEP |
| AX-045 Presence explícita | Anticipación puede sentirse vigilancia | Familia/Mapa | sharing state/capability | Mostrar acción válida y estado claro | Activar sharing o pedir ubicación en startup | 5/5/1 · 5/5/1 | 5/1/1/1 · HIGH | YA IMPLEMENTADO BIEN · permissions · KEEP |
| AX-046 Recuperación de permiso inline | Denial obliga adivinar cómo continuar | Mapa | permission status | Explicar y ofrecer retry/settings cuando corresponde | Abrir Settings sin tap | 4/5/1 · 4/5/1 | 4/2/2/2 · HIGH | IMPLEMENTADO PARCIAL · OS status · IMPROVE |
| AX-047 Homi sugiere próximo paso | Información puede no volverse acción | Homi/domains | Contexto explícito actual | Card de sugerencia explicable y descartable | Ejecutar/crear sin confirmación | 4/3/3 · 2/2/4 | 3/5/5/5 · HIGH | NO IMPLEMENTADO · Product Truth/backend · DEFER |
| AX-048 Homi prefill confirmado | Repetir datos tras aceptar sugerencia | Homi/forms | Suggestion + source context | Abrir form prellenado, todos campos editables | Inventar confidence/datos | 4/4/2 · 3/3/3 | 4/4/4/4 · HIGH | NO IMPLEMENTADO · AX-047 · DEFER |
| AX-049 Settings retorna al origen | Configuración rompe recorrido | Perfil/Settings | originTab | Volver al tab de entrada | Elegir tab por heurística | 4/5/1 · 4/5/1 | 4/1/1/1 · LOW | YA IMPLEMENTADO BIEN · settingsNavigation · KEEP |
| AX-050 Reset de contexto por household | Estado viejo puede aparecer en otro hogar | transversal | auth user + household id + generation | Scope/cache keys y descartar state incompatible | Migrar selección privada entre hogares | 5/5/1 · 5/5/1 | 5/3/3/2 · HIGH | YA IMPLEMENTADO BIEN · contexts/generations · KEEP |

## 4. Buyer principal review

Pregunta aplicada una por una: “¿Realmente me saca trabajo mental o solamente agrega una función?”. En cada respuesta se condensan pasos, información reconstruida, aprendizaje, previsibilidad/control y frecuencia.

| ID | Clasificación | Respuesta del coordinador natural |
|---|---|---|
| 001 | MUY VALIOSA | Cero pasos extra; no tengo que comprobar dónde estoy; no se aprende; resultado inmediato, control total, uso constante. |
| 002 | VALIOSA | No reduce datos, pero elimina una señal visual defectuosa frecuente; conducta obvia y controlada en cada cambio de módulo. |
| 003 | MUY VALIOSA | Ahorra volver a buscar y recordar posición; invisible de aprender; predecible si sólo restaura al volver; uso diario. |
| 004 | MUY VALIOSA | Evita reconstruir query y filtros; cero aprendizaje; mantiene control y acelera cada consulta repetida. |
| 005 | MUY VALIOSA | Reduce lectura y decisión en cada menú; no quita opciones; se entiende por estado; alta frecuencia. |
| 006 | VALIOSA | No añade función: evita salto y duda durante guardado; totalmente predecible; frecuente. |
| 007 | VALIOSA | Reduce taps y recorrido físico; patrón conocido; mantiene validación; frecuente en altas. |
| 008 | VALIOSA | Acerca la decisión al objeto y evita reorientación; patrón claro, aunque no urgente mientras los sheets sean consistentes. |
| 009 | VALIOSA | Menos recorrido y mejor alcance; no requiere aprender; ya resuelto y frecuente. |
| 010 | MUY VALIOSA | Elimina confirmaciones y miedo en acciones reversibles; Undo visible conserva control; sólo vale con reversión real. |
| 011 | MUY VALIOSA | Me muestra hoy/próximo/atención sin que yo reconstruya todo; alta frecuencia; debe permanecer estable. |
| 012 | MUY VALIOSA | Ahorra abrir módulo, buscar y volver; control intacto; muy frecuente, pero el retorno debe ser perfecto. |
| 013 | MUY VALIOSA | Resuelve una tarea en un tap y permite corregir; quita trabajo real, no agrega función. |
| 014 | MUY VALIOSA | Evita investigar qué generó una alerta; acción directa y reversible por navegación; frecuente. |
| 015 | VALIOSA | Evita cambiar de pestaña repetidamente; invisible y predecible si está aislado por hogar. |
| 016 | MUY VALIOSA | La fecha ya está clara; evita repetirla y sigue editable; alta frecuencia. |
| 017 | MUY VALIOSA | El Plan ya se conoce; elimina selección redundante; control total antes de guardar. |
| 018 | MUY VALIOSA | Me ofrece Completar/Aprobar/Reactivar según realidad; ahorra interpretación; uso constante. |
| 019 | MUY VALIOSA | Evita perder una lista filtrada extensa; cero aprendizaje; debe invalidarse si la lista cambió. |
| 020 | MUY VALIOSA | No pierdo trabajo al interrumpirme; recuperación explícita y privada; alta relevancia. |
| 021 | MUY VALIOSA | Evita sobrescribir trabajo ajeno y muestra la verdad; puede sumar un paso, pero preserva confianza. |
| 022 | VALIOSA | Me deja seguir y ofrece detalle cerca; evita navegación automática; frecuencia media-alta. |
| 023 | MUY VALIOSA | No vuelvo a buscar el producto después de editar; poca novedad, gran continuidad. |
| 024 | MUY VALIOSA | Evita escribir qué reponer; sigue editable y no inventa cantidad; valor cotidiano alto. |
| 025 | VALIOSA | Corrige taps rápidos sin reabrir edición; útil, pero una carrera de stock podría confundir. |
| 026 | MUY VALIOSA | Pone “Reponer” donde corresponde; elimina la decisión obvia sin actuar por mí. |
| 027 | MUY VALIOSA | Sería un ahorro real, pero sin Shopping canónico sólo crearía otra carga; esperar. |
| 028 | VALIOSA | Reduce doble carga después de comprar, siempre como propuesta; depende del flujo de compra real. |
| 029 | MUY VALIOSA | Evita reconstruir scope y período financiero; crítico que el scope sea explícito y seguro. |
| 030 | NEUTRA | Puede ahorrar taps, pero una inferencia financiera errónea cuesta más que seleccionar; sólo origen inequívoco. |
| 031 | MUY VALIOSA | Pago pendiente muestra el siguiente paso correcto; reduce decisiones frecuentes sin ejecutar nada. |
| 032 | MUY VALIOSA | Trash/Restore y Undo reducen miedo; ya funciona y no debe reescribirse. |
| 033 | VALIOSA | Mantenerme donde estaba después de guardar evita reconstrucción; feedback inline basta. |
| 034 | MUY VALIOSA | No me arranca de una conversación antigua por una llegada nueva; conserva lectura y control. |
| 035 | MUY VALIOSA | Sé que llegó algo y llego en un tap; complementa la preservación sin sorpresa. |
| 036 | MUY VALIOSA | Creo la tarea sin perder el chat y tengo “Ver tarea” disponible; siguiente paso probable, no impuesto. |
| 037 | VALIOSA | Menos opciones irrelevantes; útil, pero el menú actual ya cubre el vertical principal. |
| 038 | MUY VALIOSA | No pierdo mensajes a medio escribir al consultar otro chat; requiere privacidad/lifecycle bien resueltos. |
| 039 | MUY VALIOSA | No tengo que recordar carpeta, búsqueda ni archivo; ahorro grande en colecciones extensas. |
| 040 | VALIOSA | Veo dónde quedó lo recién subido sin abrirlo a la fuerza; acción posterior clara. |
| 041 | NEUTRA | Ayuda en revisión repetida, pero agrega controles y complejidad a un uso menos frecuente. |
| 042 | MUY VALIOSA | La carpeta actual es el default obvio; evita una pregunta redundante y sigue editable. |
| 043 | VALIOSA | Mantiene a la persona que estoy coordinando; útil si nunca implica seguimiento automático. |
| 044 | MUY VALIOSA | No pierdo la orientación que armé en el mapa; conducta esperable y frecuente durante coordinación. |
| 045 | MUY VALIOSA | Estado y acción claros sin compartir solo; reduce dudas respetando control. |
| 046 | VALIOSA | Me dice cómo recuperarme de un permiso denegado; ahorra diagnóstico sin presionarme. |
| 047 | NEUTRA | Podría descargarme trabajo, pero una sugerencia opaca añade decisiones y desconfianza; no ahora. |
| 048 | VALIOSA | Si acepté una sugerencia, no quiero reescribir; sólo después de una fuente confiable y visible. |
| 049 | VALIOSA | Vuelvo donde estaba al ajustar algo; simple, predecible y ya resuelto. |
| 050 | MUY VALIOSA | Nunca debo reconstruir ni corregir contexto mezclado entre hogares; seguridad y confianza básicas. |

## 5. Buyer secundario review

Pregunta aplicada una por una: “Si sólo quiero participar, ¿me facilita o me complica?”. Se ponderan comprensión, taps, vigilancia, claridad, autonomía, reversión y decisiones.

| ID | Clasificación | Respuesta del integrante participante |
|---|---|---|
| 001 | MUY VALIOSA | La selección siempre coincide con la pantalla; no necesito entender navegación interna ni hago taps extra. |
| 002 | VALIOSA | Movimiento limpio y sobrio mejora confianza sin pedirme nada. |
| 003 | VALIOSA | Vuelvo al mismo lugar y continúo; no implica vigilancia ni decisiones. |
| 004 | VALIOSA | Mis filtros siguen ahí al volver; menos taps, fácil de corregir. |
| 005 | MUY VALIOSA | La opción válida aparece primero y las demás siguen visibles; entiendo qué puedo hacer. |
| 006 | VALIOSA | Un botón estable comunica que está trabajando; no tengo que interpretar saltos. |
| 007 | VALIOSA | Next/Done hace formularios más fáciles; no cambia reglas ni datos. |
| 008 | VALIOSA | El menú cerca del objeto es más comprensible; riesgo bajo si no tapa contenido. |
| 009 | VALIOSA | Acciones al alcance y sheet del tamaño justo; ya familiar. |
| 010 | VALIOSA | Undo me da autonomía; no quiero confirmaciones para todo, pero debe ser visible. |
| 011 | MUY VALIOSA | “Hoy” y “Atención” me dicen qué aportar sin administrar el sistema. |
| 012 | VALIOSA | Llegar directo evita aprender dónde vive cada cosa; volver debe llevarme al origen. |
| 013 | MUY VALIOSA | Completo lo mío rápido y puedo deshacer; ideal para participar con pocos pasos. |
| 014 | VALIOSA | Una alerta que abre su causa es clara; sólo debe mostrar lo que puedo ver. |
| 015 | VALIOSA | La app recuerda la pestaña y no me obliga a navegar otra vez. |
| 016 | VALIOSA | Si toqué un día, usarlo como sugerencia es obvio y editable. |
| 017 | VALIOSA | Crear dentro de un Plan ya lo preselecciona; menos decisiones. |
| 018 | MUY VALIOSA | Ver una acción adecuada al estado evita aprender el lifecycle completo. |
| 019 | VALIOSA | Regreso al mismo resultado; no me obliga a administrar filtros. |
| 020 | VALIOSA | Recuperar un borrador evita frustración, con elección clara de continuar o descartar. |
| 021 | VALIOSA | Prefiero ver el estado real a creer que sobrescribí a alguien; copy debe ser simple. |
| 022 | VALIOSA | La creación termina donde estaba y “Ver” es opcional; autonomía alta. |
| 023 | VALIOSA | Después de cambiar stock sigo en el mismo producto; menos búsqueda. |
| 024 | MUY VALIOSA | “Reponer este producto” prellenado me deja ayudar sin aprender Inventario/Planner. |
| 025 | VALIOSA | Undo sería cómodo, pero no quiero ver cantidades que luego cambian por una carrera. |
| 026 | MUY VALIOSA | Si falta, “Reponer” es la acción que entiendo; no se crea nada solo. |
| 027 | VALIOSA | Sería directo, pero una lista paralela sería confusa; esperar autoridad real. |
| 028 | VALIOSA | Ofrecer actualizar stock me ayuda; hacerlo solo se sentiría controlante. |
| 029 | NEUTRA | Recordar scope ayuda, pero debo ver claramente si es personal o del hogar. |
| 030 | MOLESTA | Que la app adivine cuenta/categoría puede parecer invasivo y causar errores; no implementar por heurística. |
| 031 | VALIOSA | Un pago pendiente con CTA claro reduce aprendizaje; nada automático. |
| 032 | VALIOSA | Poder deshacer elimina miedo; Trash deja claro que no es definitivo. |
| 033 | VALIOSA | Feedback inline es más tranquilo que otro modal; no me expulsa del flujo. |
| 034 | MUY VALIOSA | Puedo leer mensajes anteriores sin que la pantalla se mueva sola. |
| 035 | MUY VALIOSA | “Nuevos mensajes” es inmediato y voluntario; cero confusión. |
| 036 | MUY VALIOSA | Creo algo útil desde el chat y sigo conversando; “Ver tarea” es opcional. |
| 037 | VALIOSA | Menos acciones irrelevantes facilita el menú, pero no necesito nuevas opciones. |
| 038 | VALIOSA | No pierdo lo que escribía, siempre que el draft quede local y privado. |
| 039 | VALIOSA | Vuelvo al mismo archivo/carpeta sin aprender jerarquías otra vez. |
| 040 | VALIOSA | El archivo nuevo queda visible; no me lleva a una pantalla inesperada. |
| 041 | NEUTRA | Anterior/siguiente puede sumar controles que rara vez uso. |
| 042 | VALIOSA | La carpeta actual preseleccionada es evidente y editable. |
| 043 | NEUTRA | Mantener persona seleccionada ayuda, pero puede sentirse seguimiento si no es explícito. |
| 044 | MUY VALIOSA | El mapa no se mueve solo después de que lo acomodé; conserva autonomía. |
| 045 | MUY VALIOSA | Compartir ubicación sigue siendo decisión mía; estado claro reduce sensación de vigilancia. |
| 046 | VALIOSA | Una recuperación clara de permisos evita quedar bloqueado sin activar nada. |
| 047 | MOLESTA | Sugerencias “inteligentes” pueden exigir evaluación o sentirse como control; diferir. |
| 048 | NEUTRA | Prefill ayuda sólo si antes elegí la sugerencia y veo de dónde sale. |
| 049 | VALIOSA | Volver al origen es simple y no cambia settings. |
| 050 | MUY VALIOSA | Ver sólo el contexto del hogar actual evita confusión y exposición; no requiere aprender nada. |

## 6. Professional reconciliation

### A — YA EXISTE Y ESTÁ BIEN: KEEP CURRENT

`001, 006, 009, 011, 013, 015, 016, 017, 018, 020, 021, 032, 042, 044, 045, 049, 050`.

Se preservan porque ya usan autoridad canónica, contexto explícito y patrones previsibles. Reescribirlos agregaría riesgo sin reducir pasos.

### B — YA EXISTE PERO PUEDE PULIRSE

`002, 004, 005, 007, 010, 014, 022, 023, 024, 026, 029, 031, 033, 034, 036, 040, 046`.

Sólo `002`, `034` y `036` entran en este patch porque tienen evidencia directa, límites claros y pruebas focales. El resto requiere un slice del dominio propietario.

### C — NUEVA Y DE ALTO VALOR

`035`. Es la contrapartida necesaria de no mover el chat: avisa que existe contenido debajo y deja el salto bajo control del usuario.

### D — BUENA PERO DE ALTO RIESGO: DEFERRED

`003, 008, 012, 019, 025, 027, 028, 037, 038, 039, 041, 043`.

Requieren lifecycle de retorno, concurrency, autoridad de dominio o privacidad que no conviene resolver transversalmente en un mega-patch.

### E — PARECE INTELIGENTE PERO EMPEORA UX: REJECT

`030` en su variante heurística (“usar la última cuenta/categoría”). En Finanzas un tap ahorrado no compensa una imputación errónea. Se conserva únicamente el prefill proveniente de un origen explícito e inequívoco.

### F — REQUIERE NUEVA DECISIÓN DE PRODUCTO

`047, 048`. Homi no debe inventar intención, confianza ni acciones. Requieren Product Truth, explicabilidad y backend real antes de diseñar UI productiva.

## 7. Ideas implementadas profesionalmente y no tocadas

- Home: secciones Hoy/Próximo/Atención y complete + Undo.
- Planner: origen/retorno tipados, fecha/Plan preseleccionados, private drafts, conflictos y acciones por lifecycle.
- UI: loading de `AppButton` sin cambio de tamaño; `ActionSheet` adaptable y keyboard-aware.
- Finanzas: Trash/Restore, corrección y Undo canónicos.
- HomeCloud: carpeta actual como contexto de intake y reads firmados.
- Familia/Mapa: sharing explícito, permisos separados y guardas contra recenter después de un gesto.
- Settings: retorno mediante `originTab`.
- Global: state/caches scoped por usuario/household y SimpleShell sin bottom navbar.

## 8. Ideas seleccionadas para implementación

- `002`: eliminar rasterización percibida durante la transición de navbar sin degradar el movimiento.
- `034`: no destruir la posición de lectura cuando entra un mensaje remoto.
- `035`: exponer “Nuevos mensajes” como salto explícito.
- `036`: después de Message→Task, permanecer en conversación y ofrecer “Ver tarea”; error inline recuperable.

No se seleccionaron más cambios: el audit mostró que los siguientes candidatos cruzan contratos de dominio o requieren lifecycle común aún no demostrado.

## 9. Implementation map

| Prioridad / idea | CURRENT → TARGET → REAL GAP | FILES | IMPLEMENTATION | TEST | EVIDENCE |
|---|---|---|---|---|---|
| P0 / 002 | Dos glyphs + alpha + scale → un glyph nítido con continuidad espacial → composición provocaba blur | `FloatingNavigationBar.tsx` en ambos fronts | Quitar scale/capas; conservar indicador único 300 ms; no haptic | TS, lint, contrato, estrés simulator | 30 taps, ruta final/indicador correctos |
| P5 / 034 | Cada incremento hacía `scrollToEnd` → seguir sólo si usuario está abajo o mensaje es propio → faltaba conciencia del viewport | `MessagesConversationScreen.tsx` en ambos fronts | `isNearBottom`, delta de count y sender | TS, Messages M+H1/M2, contrato | incoming no ordena scroll cuando usuario lee arriba |
| P5 / 035 | No había señal si se preservaba offset → salto voluntario → faltaba affordance | mismo archivo | pill accesible junto al composer | contrato + typecheck | ID estable `messages.newMessages` |
| P5 / 036 | Create+link cerraba modal sin siguiente paso → banner inline y “Ver tarea” → resultado canónico no estaba cerca | mismo archivo | canonical task id/title; TaskDetailFromMessage; error inline | Task Context + contracts | `returnTo:'previous'`; chat se conserva |

Roadmap posterior aprobado, no ejecutado aquí: P1 Home (`014`); P2 Planner (`004/005/007/010/022`); P3 Inventario (`023/024/026`); P4 Finanzas (`029/031/033`); P6 HomeCloud (`040`); P7 Presence (`046`). Cada uno debe ser un slice separado con test del dominio.

## 10. Implementación real

### Slice P0 — navbar

- `front/mi-front-limpio/components/ui/FloatingNavigationBar.tsx`
- `front/mi-front-expo-go/components/ui/FloatingNavigationBar.tsx`

Se removieron únicamente los elementos que causaban pérdida de nitidez. No se cambió geometría, orden, rutas, botón central, badges, shells, mapa, safe area ni navigation framework.

### Slice P5 — continuidad en conversación

- `front/mi-front-limpio/screens/messages/MessagesConversationScreen.tsx`
- `front/mi-front-expo-go/screens/messages/MessagesConversationScreen.tsx`

Un incoming ya no desplaza a quien está leyendo historia. La lista sigue automáticamente para carga inicial, usuario cerca del final o envío propio. Un control accesible permite saltar a lo nuevo. Message→Task muestra resultado inline, abre Planner sólo por decisión del usuario y conserva la conversación al volver. El fallo queda dentro del sheet para reintentar sin perder título/origen.

### Contratos/documentación

- `tests/anticipatory_ux_contract.test.js`
- `package.json` (`test:anticipatory-ux`)
- `docs/ANTICIPATORY_UX_AUDIT.md`

## 11. Tests y regresiones buscadas

Verificación obligatoria del patch:

- una sola representación de glyph por branch;
- ausencia de scale/cross-fade/raster flags en navbar;
- indicador ligado a route real;
- haptics de navbar en `none`;
- no scroll forzado mientras se lee historial;
- mensaje propio sí sigue al final;
- jump explícito para incoming;
- Task canónica + linkage y retorno a conversación;
- botón loading compartido mantiene geometría;
- paridad de los dos fronts;
- TypeScript, Messaging, Task Context, Planner, Reactive UI, Presence y Experience Mode;
- exports Android/iOS.

Resultados ejecutados:

- PASS: TypeScript `--noEmit` en front principal y Expo Go.
- PASS: ESLint focal de navbar y conversación en ambos fronts.
- PASS: `test:anticipatory-ux` (4/4).
- PASS: Core/Messaging contracts, backend, Messages M+H1, Rich Media M2, Task Context, Planner M9, Reactive UI, Presence, Experience Mode, Profile/Settings y H+.
- PASS: export Android y export iOS del front principal.
- PASS simulator: 30 cambios rápidos; el último tap dejó `nav.home selected=true`, sin route mismatch. Captura final nítida y screen recording conservados en el directorio temporal local.
- LIMITACIÓN DE HARNESS: `npm run test:frontend` raíz no comienza la compilación porque el `node_modules` raíz no contiene TypeScript (`npm ls typescript` vacío). No se instalaron dependencias fuera del front; los dos typechecks reales sí pasaron.

Ningún check físico se eleva a PASS por contrato estático o simulador.

## 12. Riesgo y device QA

- Android simulator: navbar, taps rápidos, navegación y screen state.
- `NEEDS_DEVICE_QA`: nitidez percibida a 120 Hz/escala real, safe area iPhone, táctil, keyboard IME físico, map gesture, background→foreground, lectores de pantalla y performance de listas extensas con datos reales.
- No se modificaron backend, DB, Supabase, RLS, permisos, auth, roles, Presence, contratos Rich Messaging, Planner authority ni Experience Mode.

## 13. Estado final por decisión

### DONE

`002, 034, 035, 036`.

### PARTIAL (requiere slice propio)

`004, 005, 007, 010, 014, 022, 023, 024, 026, 029, 031, 033, 040, 046`.

### KEEP CURRENT

`001, 006, 009, 011, 013, 015, 016, 017, 018, 020, 021, 032, 042, 044, 045, 049, 050`.

### DEFERRED

`003, 008, 012, 019, 025, 027, 028, 037, 038, 039, 041, 043, 047, 048`.

### REJECTED

`030` como heurística financiera; se mantiene sólo contexto explícito.

### NEEDS_DEVICE_QA

Navbar física, teclado real, gestures/mapa, safe areas iOS, background/foreground y percepción de motion en hardware.

