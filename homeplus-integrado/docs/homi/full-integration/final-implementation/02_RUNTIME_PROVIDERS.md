# Proveedores y runtime observado

| Componente | Endpoint probado | Resultado |
|---|---|---|
| THINK HOMI-A | `127.0.0.1:18011/invoke` por túnel SSH existente | `SUCCESS`, modelo `Qwen_Qwen3.5-9B-Q5_K_M`, respuesta `HOMI`, usage 25 tokens |
| HOMI-D integrado | `127.0.0.1:8002` | Health y conversaciones reales; endpoint interno de propuestas probado |
| Gateway integrado | `192.168.0.11:3101` | Health, siete READ y una WRITE confirmada con persistencia |
| STT HOMI-C | `homi-c:8010`/`:8012` vía red privada | WAV español transcrito: “Dale, te aviso cuando llegues…”; motor `faster-whisper` |
| SEE | No se probó proveedor de imagen real | `BLOCKED_EXTERNAL` para análisis de píxeles; T23 attachments 16/16, T17 ingestion 12/12 y T18 FIND 8/8 son pruebas focales |
| Supabase local | `127.0.0.1:56221` REST, `:56222` DB | Contenedor `supabase_db_HomePlus`; migraciones HOMI aplicadas sólo allí |

El proceso previo de Metro `:8081` sirve `homi-t07`; no se tocó. Los procesos previos `:3100` y `:8001` tampoco se reiniciaron. La ejecución validada se aisló en `:3101` y `:8002`.

Para recuperar el stack, verificar primero PIDs y puertos. El backend requiere `PORT=3101`, `HOMI_D_BASE_URL=http://127.0.0.1:8002`, `HOMI_SELF_BASE_URL=http://127.0.0.1:3101` y el secreto local efectivo de `backend/.env`. HOMI-D requiere el mismo `HOMI_INTERNAL_WRITE_SECRET`, `HOMI_TOOL_BASE_URL` y `HOMI_INTERNAL_WRITE_BASE_URL` apuntando a `:3101`. `dotenv` no reemplaza una variable heredada: la primera WRITE falló sin efecto por un secreto antiguo heredado. No iniciar con secretos distintos.

El túnel THINK existente escucha en `:18011` y responde inferencia real. HOMI-C estuvo alcanzable directamente por `homi-c`; no se instaló ni reemplazó modelo. La transcripción se envió como multipart a `/api/homi/v1/voice/transcript`, con `semantic_turn=false`, `tools_executed=false`, `tts_generated=false`.
