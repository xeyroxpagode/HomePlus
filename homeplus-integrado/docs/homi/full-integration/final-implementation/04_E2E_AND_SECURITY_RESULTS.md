# E2E y seguridad

**Entorno:** Supabase CLI local `HomePlus`, backend integrado `:3101`, HOMI-D integrado `:8002`, cuenta QA local autenticada. El token fue renovado mediante Supabase Auth para la cuenta existente y quedó fuera del worktree. No se usó service-role como identidad de tool.

| Prueba | Resultado |
|---|---|
| THINK sin tool: saludo | `SUCCESS`, `direct_response`, modelo real |
| THINK con READ: tareas de mañana | `SUCCESS`, `tool_request`, `planner.tasks.list`, respuesta fundada en resultado real |
| READ autenticadas | 200 y tool ID correcto: `home.summary.get`, `planner.tasks.list`, `finance.accounts.list`, `inventory.products.list`, `households.family.get`, `messages.conversations.list`, `homecloud.files.list` |
| WRITE sin secreto interno | 403, sin efecto |
| Claim inexistente o no ejecutable | Rechazo en HOMI-D/gateway |
| Claim de otro hogar | 403 en prueba del endpoint interno |
| Argumentos cambiados después de confirmar | 409 en prueba de seam; sin dispatch |
| Primer intento QA con secretos distintos | `FAILED` en ledger, tarea ausente |
| Segundo intento QA con schema `date` incorrecto | `HOMI_TOOL_ARGUMENT_INVALID`, tarea ausente; corregido en catálogo fuente y runtime |
| `planner.tasks.create` corregida | Preview `{title,dueDate:2026-11-20,dueTime:08:00}`, confirmación `action_executed`, tarea con fecha y hora legible mediante `planner.tasks.get`, un run `VERIFIED` |
| Repetición de confirmación | Conteo de tarea 1 → 1; sin segunda escritura |
| STT manual | Transcripción española no vacía; sin envío automático ni TTS |

La primera escritura persistida quedó `SUCCEEDED` sin verificación interna porque el seam devolvía un resultado envuelto y el lector usaba una ruta antigua. Tras corregir ambos contratos, una nueva escritura recibió `VERIFIED`: Planner devolvió el ID, título, fecha y hora esperados y el ledger quedó `VERIFIED`. La respuesta de una escritura cuya lectura posterior falle ahora expone `UNVERIFIED`. Esto no eleva las otras 192 WRITE a E2E. Faltan negativos por rol real, otro hogar de usuario, revocación, versión y secuencias de todos los dominios. La matriz completa está en `03_TOOL_AND_WRITE_ACCEPTANCE.json`.
