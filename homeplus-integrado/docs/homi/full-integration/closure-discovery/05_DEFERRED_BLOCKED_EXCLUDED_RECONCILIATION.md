# 05 — DEFERRED / BLOCKED / EXCLUDED RECONCILIATION — Pasada 1/2

**Política aplicada (Actor A):** maximizar cobertura. Está **prohibido** mantener una operación como `DEFERRED` por complejidad o por «no aportar al recorrido HOMI V1». Solo se mantienen fuera del contrato las operaciones con razón funcional, técnica o de seguridad **demostrable** y citada.

**Resultado:** de las 176 operaciones anteriores (92 IMPLEMENT / 59 DEFERRED / 15 BLOCKED / 10 EXCLUDED), **todas** tienen destino final. Las 59 `DEFERRED` se reclasificaron: 51 pasaron a objetivo, 3 a bloqueo real, 3 a exclusión por no-producto/seguridad, 2 a decisión de producto. Se incorporaron 174 operaciones nuevas.

## 1. Resumen por destino final

| Destino | Cantidad | Significado |
|---|---:|---|
| TARGET IMPLEMENT | 307 | Contrato completo en 04 |
| BLOCKED DEPENDENCY | 12 | Operación no disponible desde HOMI; resto del dominio sí |
| BLOCKED AUTHORITY | 9 | Operación no disponible; se informa al usuario con razón |
| EXCLUDED SECURITY | 7 | Sin consecuencia: nunca fue apta para el modelo |
| PRODUCT DECISION | 6 | Default seguro: no exponer hasta decisión |
| BLOCKED UNSAFE | 5 | La funcionalidad sigue en la app nativa/HUI |
| EXCLUDED NOT PRODUCT | 4 | Sin consecuencia: no existe producto que exponer |

## 2. Análisis individual (todas las operaciones no objetivo)

Cada fila incluye justificación objetiva, responsable, condición de desbloqueo y consecuencia funcional. La dificultad técnica **nunca** es justificación suficiente por sí sola.

### BLOCKED DEPENDENCY — 12 operaciones

**Responsable:** Actor C + proveedor/backend canónico · **Condición de desbloqueo:** Proveedor disponible o corrección del servicio canónico + validación con fixture

| Operación | Antes | Origen | Justificación objetiva (evidencia) | Consecuencia |
|---|---|---|---|---|
| `identity.avatar.update` | DEFERRED | 176 | Multipart + compresion de imagen; requiere UI nativa (PD-05) | Operación no disponible desde HOMI; resto del dominio sí |
| `planner.tasks.evidence` | DEFERRED | 176 | Requiere foto/comentario; depende de SEE/adjuntos reales. | Operación no disponible desde HOMI; resto del dominio sí |
| `finance.transfers.create` | BLOCKED | 176 | R1-b: hash de idempotencia con scopeType fijo PERSONAL; colision entre contextos no descartada. | Operación no disponible desde HOMI; resto del dominio sí |
| `homecloud.content.access` | BLOCKED | 176 | URL firmada a bytes: requiere SEE/HOMI-B real; no inventar contenido. | Operación no disponible desde HOMI; resto del dominio sí |
| `homecloud.content.analyze` | BLOCKED | 176 | HOMI-B no garantizado; sin procesamiento visual no se devuelve resultado. | Operación no disponible desde HOMI; resto del dominio sí |
| `homecloud.content.register` | DEFERRED | 176 | Carga de archivos: requiere UI de seleccion real (PD-05). | Operación no disponible desde HOMI; resto del dominio sí |
| `messages.attachments.download` | BLOCKED | 176 | URL firmada a bytes 300s; requiere SEE/HOMI-B. | Operación no disponible desde HOMI; resto del dominio sí |
| `homecloud.content.upload-authorize` | — | NEW | URL firmada y bytes: requiere flujo de archivo; no apto para LLM sin UI de seleccion (PD-05) | Operación no disponible desde HOMI; resto del dominio sí |
| `homecloud.content.verify` | — | NEW | Parte del ciclo de carga; requiere archivo real | Operación no disponible desde HOMI; resto del dominio sí |
| `homecloud.content.finalize` | — | NEW | Parte del ciclo de carga; requiere archivo real | Operación no disponible desde HOMI; resto del dominio sí |
| `messages.attachments.upload-authorize` | — | NEW | URL firmada; requiere archivo real | Operación no disponible desde HOMI; resto del dominio sí |
| `messages.attachments.verify-upload` | — | NEW | Requiere archivo real | Operación no disponible desde HOMI; resto del dominio sí |

### EXCLUDED SECURITY — 7 operaciones

**Responsable:** Permanente — no se desbloquea · **Condición de desbloqueo:** Ninguna: credenciales/service-role/dispositivo nativo no son tools del modelo

| Operación | Antes | Origen | Justificación objetiva (evidencia) | Consecuencia |
|---|---|---|---|---|
| `identity.register` | EXCLUDED | 176 | Credenciales/sesion: nunca herramienta del LLM. | Sin consecuencia: nunca fue apta para el modelo |
| `identity.login` | EXCLUDED | 176 | Credenciales/sesion: el inicio de sesion pertenece a la app, nunca al modelo. | Sin consecuencia: nunca fue apta para el modelo |
| `identity.refresh` | EXCLUDED | 176 | Renovacion de token: credenciales de sesion, fuera de la autoridad del LLM. | Sin consecuencia: nunca fue apta para el modelo |
| `identity.logout` | EXCLUDED | 176 | Cierre de sesion: credenciales de sesion, gestion exclusivo de la app. | Sin consecuencia: nunca fue apta para el modelo |
| `identity.user-metadata.update` | EXCLUDED | 176 | Escribe auth.users.user_metadata via service-role (ADG-9). | Sin consecuencia: nunca fue apta para el modelo |
| `notifications.preferences.update` | EXCLUDED | 176 | Requiere service-role; sin bandeja real. | Sin consecuencia: nunca fue apta para el modelo |
| `notifications.devices.register` | EXCLUDED | 176 | Registro de dispositivo nativo, no del asistente. | Sin consecuencia: nunca fue apta para el modelo |

### BLOCKED UNSAFE — 5 operaciones

**Responsable:** Actor A (PD-04) / diseño de tools tipadas · **Condición de desbloqueo:** Rediseño como tool tipada o UI dedicada; nunca acceso directo desde LLM

| Operación | Antes | Origen | Justificación objetiva (evidencia) | Consecuencia |
|---|---|---|---|---|
| `households.create` | BLOCKED | 176 | Cambia el workspace raiz durante la conversacion; alternativa UI dedicada (PD-04). | La funcionalidad sigue en la app nativa/HUI |
| `households.set-active` | BLOCKED | 176 | Cambia el hogar activo e invalida el contexto de la propuesta (PD-04). | La funcionalidad sigue en la app nativa/HUI |
| `households.finalize-member` | BLOCKED | 176 | Expulsion de persona: accion administrativa destructiva (PD-04). | La funcionalidad sigue en la app nativa/HUI |
| `planner.plans.structure` | BLOCKED | 176 | Changeset estructural completo: no seguro desde lenguaje natural. | La funcionalidad sigue en la app nativa/HUI |
| `planner.plans.legacy.write` | — | NEW | Writes de grafo completo; usar herramientas estructuradas dedicadas (planner.plans.structure ya BLOCKED) | La funcionalidad sigue en la app nativa/HUI |

### EXCLUDED NOT PRODUCT — 4 operaciones

**Responsable:** Permanente salvo cambio de producto · **Condición de desbloqueo:** Existencia real de backend/producto (hoy no existe)

| Operación | Antes | Origen | Justificación objetiva (evidencia) | Consecuencia |
|---|---|---|---|---|
| `households.join` | EXCLUDED | 176 | Flujo de onboarding de la app, no del asistente. | Sin consecuencia: no existe producto que exponer |
| `planner.drafts.autosave` | DEFERRED | 176 | Autoguardado lo hace la app; el asistente no debe generar borradores implicitos (razon funcional, no pereza). | Sin consecuencia: no existe producto que exponer |
| `feed.posts.list` | EXCLUDED | 176 | MOCK_POSTS en memoria; no existe backend. | Sin consecuencia: no existe producto que exponer |
| `feed.posts.create` | EXCLUDED | 176 | useState local; no existe backend. | Sin consecuencia: no existe producto que exponer |

### PRODUCT DECISION — 6 operaciones

**Responsable:** ACTOR A · **Condición de desbloqueo:** Resolución explícita en 14_PRODUCT_DECISION_PACKET.md

| Operación | Antes | Origen | Justificación objetiva (evidencia) | Consecuencia |
|---|---|---|---|---|
| `households.member.role.update` | DEFERRED | 176 | Cambio de privilegios: exponer a coordinator via HOMI o solo UI (PD-04). | Default seguro: no exponer hasta decisión |
| `households.role-request.approve` | DEFERRED | 176 | Aprobacion de privilegios (PD-04). | Default seguro: no exponer hasta decisión |
| `households.role-request.reject` | DEFERRED | 176 | Rechazo de privilegios (PD-04). | Default seguro: no exponer hasta decisión |
| `finance.balance.correction` | BLOCKED | 176 | Correccion de saldo: decision financiera humana; sin compensatorios ficticios (PD-03). | Default seguro: no exponer hasta decisión |
| `finance.payments.dues.register` | BLOCKED | 176 | R1-d: crea transaccion real, scope no reforzado en despacho (PD-03). | Default seguro: no exponer hasta decisión |
| `inventory.purchases.finalize` | BLOCKED | 176 | Requiere register_in_finance y decision de gasto explicita (PD-01). | Default seguro: no exponer hasta decisión |

### BLOCKED AUTHORITY — 9 operaciones

**Responsable:** Actor A (decisión) + backend/RLS · **Condición de desbloqueo:** Consentimiento/capability verificable en servidor o decisión funcional aprobada

| Operación | Antes | Origen | Justificación objetiva (evidencia) | Consecuencia |
|---|---|---|---|---|
| `planner.tasks.verify` | DEFERRED | 176 | Prohibida auto-verificacion; exige otro actor. | Operación no disponible; se informa al usuario con razón |
| `planner.plans.unarchive` | BLOCKED | 176 | Capability goal.archive=false para los 6 roles por defecto (MIG/20260722040000:355). | Operación no disponible; se informa al usuario con razón |
| `planner.presets.publish` | BLOCKED | 176 | Publicacion global de preset: no apta para agente; requiere UI editorial. | Operación no disponible; se informa al usuario con razón |
| `presence.locations.list` | BLOCKED | 176 | Geolocalizacion de terceros: consentimiento vigente no verificable por el LLM (PD-02). | Operación no disponible; se informa al usuario con razón |
| `presence.my-location.update` | BLOCKED | 176 | Seguimiento de ubicacion: requiere decision funcional explicita (PD-02). | Operación no disponible; se informa al usuario con razón |
| `finance.payments.dues.settle` | — | NEW | Liquidacion de tarjeta: decision financiera humana (PD-03) | Operación no disponible; se informa al usuario con razón |
| `inventory.products.permanent-delete` | — | NEW | Borrado permanente: requiere capability inventory.destroy no expuesta por defecto (PD-04) | Operación no disponible; se informa al usuario con razón |
| `planner.tasks.fulfillment.verify` | — | NEW | Prohibida auto-verificacion; requiere otro actor (catalogo ya tenia verify DEFERRED) | Operación no disponible; se informa al usuario con razón |
| `messages.actions.link-task` | — | NEW | P1: implementacion usa admin client (RLS bypass) para leer planner_tasks; requiere correccion antes de exponer | Operación no disponible; se informa al usuario con razón |

## 3. Decisiones que NO se tomaron en esta pasada

- No se decidió si HOMI puede finalizar compras registrando un gasto (PD-01).
- No se decidió si se implementa un flujo de consentimiento de presencia (PD-02).
- No se decidieron operaciones financieras de autoridad humana (PD-03).
- No se decidió exponer la administración de hogares/roles a coordinadores desde HOMI (PD-04).
- No se decidió invertir en SEE/HOMI-B ni en carga de archivos desde el asistente (PD-05).
- No se decidió soportar `front/mi-front-expo-go` (PD-06).

Ninguna ausencia de decisión se convirtió en permiso implícito: las tools correspondientes **no están en el catálogo final**.

## 4. Casos límite resueltos

1. **`identity.profile.update`**: antes DEFERRED con razón «no aporta al recorrido». Se **reclama** porque es una escritura segura sin service-role. La razón anterior era inadmisible según la política actual.
2. **`planner.drafts.autosave`**: se mantiene fuera no por complejidad sino porque el autoguardado es propiedad de la app; un borrador implícito generado por el asistente cambiaría el contrato de producto.
3. **`assets.*`**: 5 escrituras antes, 26 ahora. No se excluyó ninguna por «difícil»: cada una tiene capability, idempotencia y confirmación definidas.
4. **`planner.plans.create/update/transition`**: antes DEFERRED por payload complejo. Se reclaman con **tools tipadas por sección**, sin JSON arbitrario.
5. **`homecloud.content.register`**: bloqueo real de dependencia (archivo+firmado), no decisión de producto.

**Gate D: PASS — todas las operaciones anteriores y nuevas tienen destino definitivo y trazable.**
