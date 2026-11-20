# 08 — OPEN GAPS — Gaps reales, decisiones pendientes y pruebas físicas

Sólo gaps **reales**. No se listan suposiciones ni decisiones inventadas.

---

## G1 — Proveedores de inferencia y voz (BLOQUEADO)

| Dependencia | Estado | Consecuencia |
|---|---|---|
| HOMI-A / THINK `:18011` | DOWN | `/api/homi/v1/text/turn` no puede completar inferencia; recorridos compuestos (05 §A10) no ejecutables. |
| HOMI-C / STT `:8010`,`:8012` | DOWN | `/voice/transcript` sin transcripción real; dictado editable no certificable en runtime. |
| SEE / HOMI-B | no garantizado | `homecloud.content.access`, `homecloud.content.analyze`, `messages.attachments.download` → BLOCKED. No se inventa contenido visual. |
| LiveKit `:7880` | DOWN | No aplica: T31 cancelado por decisión de Actor A (T32). |

**No se simula PASS.** Iniciar con los launchers oficiales existentes; no crear túneles nuevos.

---

## G2 — Aceptación física (NEEDS DEVICE QA — Actor A)

Guion de 15 pasos en `t32/T32_VOICE_SIMPLE_HANDOFF.md §12`. Incluye micrófono, edición de borrador, envío manual, cancelación, permisos iOS, 5 grabaciones consecutivas y verificación de ausencia de TTS. Sin ejecución de Actor A no se emite `HOMI V1 VOICE CLOSED`.

---

## G3 — Contratos D congelados (R1_REQUIRED)

`pytest` focal: **108 PASS / 11 FAIL**. Las 11 fallidas son todas por el cambio intencional del catálogo (anclas y enums antiguos), no por regresiones de autoridad:

| Test | Causa |
|---|---|
| `test_catalogue_is_byte_identical_to_the_t07_source` | el catálogo ya no es byte-idéntico al de `homi-t07` (intencional) |
| `test_derived_catalogue_digest_matches_the_trust_anchor` | ancla vieja `9039…` → nueva `A1C40F55…` |
| `test_derived_catalogue_is_accepted_by_the_loader` | idem |
| `test_t07_worktree_is_at_the_frozen_commit` | el target ya no es el commit congelado T07 |
| `test_tool_id_enum_is_the_eight_canonical_ids_plus_null` | el enum ya no es de 8 ids |
| `test_effective_tool_ids_default_off` / `test_is_t24_read_enabled_default_false` | gate ahora habilitado por defecto (67 tools v2) |
| `test_t24_gate_open_accepts_precheck` / `test_t24_precheck_rejects_forbidden_keys` / `test_t24_precheck_requires_period_for_finance` | precheck con catálogo ampliado |
| `test_normalize_family_members_list` | proyección de salida cambiada por DTO 18/11 |

Acción pendiente: actualizar esos contratos al nuevo catálogo en un lote dedicado. **No se modificaron expectativas para encubrir fallas**: el cambio de catálogo es real y está documentado.

---

## G4 — Escrituras HOMI-D (R1_REQUIRED)

El seam `/api/homi/v1/internal/tools/:toolId/execute` ejecuta las 20 herramientas WRITE del catálogo con `proposal_id`, pero el módulo `homi_tool_proposal.py` sólo tiene contratos de propuesta para 5 herramientas (`planner.tasks.create|update|complete|trash|restore`). Las otras 15 escrituras (eventos, metas, finanzas, inventario, mensajes) dependen del ciclo completo de propuesta de D, no certificado sin THINK. Acción: ampliar los contratos de propuesta de D alineados con `03_TOOL_CATALOG.json`.

---

## G5 — Riesgos heredados del CURRENT 18/11 (R1_REQUIRED)

Ver 01 §6: idempotencia ausente en `createExpense`/`createIncome` (mitigada por hash generado por HOMI en el gateway), `scopeType` fijo en el hash de transferencias (tool BLOCKED), DTO `Number(amount)` en respuestas de mutación (precisión), `registerPayment` con scope no reforzado en despacho (BLOCKED). **No se modificó lógica contable canónica.**

---

## G6 — Defecto preexistente corregido (documentado)

`supabase/migrations/202610080002_hplus_points_foundation.sql` tenía dos bloques `do $$` sin `$$;` de cierre (líneas ~133 y ~200). Impedía `supabase db reset` desde cero y, por tanto, la existencia de los RPC de Mensajería. Se agregaron dos líneas `$$;`. Sin cambio de semántica de producto. Verificar en el repo autoritativo si se desea portar el fix.

---

## G7 — Frontend expo-go (DEFERRED)

`front/mi-front-expo-go` es copia histórica sin CI (evidencia en 01 §7). La superficie HOMI se integró sólo en `mi-front-limpio`, que es el cliente principal/QA. Si Actor A decide soportar expo-go, replicar el tile y la ruta; no hacerlo por defecto para evitar dos verdades.

---

## G8 — Cobertura E2E multi-rol (DEFERRED)

No se aprovisionaron fixtures de segundo hogar, rol restringido, sesión expirada ni feature flag deshabilitada. Los controles existen en código y en la suite estática 8/8, pero no hay evidencia runtime para esos escenarios. No se declara PASS.

---

## G9 — Tool chaining (DEFERRED)

Los recorridos `Planner→Calendario`, `Inventario→Planner`, `Finanzas`, `Familia`, `Mensajería` y `HomeCloud` están diseñados en 05 §A10 pero no ejecutados de extremo a extremo por THINK DOWN. El recorrido `Inventario→Finanzas` (finalizar compra con gasto) queda además `PRODUCT_DECISION_REQUIRED` si no hay pedido explícito de registrar el gasto.
