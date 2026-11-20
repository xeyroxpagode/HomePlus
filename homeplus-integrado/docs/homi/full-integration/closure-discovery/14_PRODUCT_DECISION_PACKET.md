# 14 — PRODUCT DECISION PACKET — Para Actor A

**Regla:** Actor C **no toma decisiones de negocio**. Cada decisión tiene un **resultado por defecto seguro** que permite continuar la pasada 2 sin permiso implícito. Las tools afectadas **no están en el catálogo final** mientras la decisión esté abierta.

---

## PD-01 — Finalizar compra registrando un gasto

- **Problema:** `inventory.purchases.finalize` acepta `register_in_finance`. Si HOMI lo ejecuta sin petición explícita, crea un gasto real en Finance.
- **Evidencia:** `inventory.js:32`; `purchases.service.js:13-14` (gasto deduplicado por `finance_transaction_sources`; fallo silencioso con `finance_sync_status:'failed'`); catálogo anterior lo marcó `PRODUCT_DECISION_REQUIRED`.
- **Opciones:** (A) exigir que el usuario diga explícitamente «registrá el gasto»; (B) registrar siempre; (C) nunca desde HOMI.
- **Implicaciones:** A mantiene intención y gasto separados; B automatiza contabilidad con riesgo; C reduce cobertura.
- **Recomendación técnica:** A.
- **Default seguro:** **A** — HOMI solo inicia/pausa/reanuda compras; `finalize` con gasto requiere instrucción textual explícita y confirmación reforzada.
- **Afectadas:** `inventory.purchases.finalize`, `inventory.purchases.finance.retry`.

## PD-02 — Presencia y ubicación

- **Problema:** `presence.locations.list` y `presence.my-location.update` existen en backend, pero el consentimiento vigente no es verificable por el modelo.
- **Evidencia:** `routes/presence.js:9-10`; `MIG/20260904010000:39-116,324-411` (grants, guardianes de menores, geofences); RLS `presence_locations_select_visible_only`.
- **Opciones:** (A) mantener fuera de HOMI; (B) implementar flujo de consentimiento verificable en servidor y exponer solo ubicación propia; (C) exponer ubicaciones del hogar.
- **Implicaciones:** B/C requieren producto de consentimiento nuevo, no solo una tool; C es sensible para menores.
- **Recomendación técnica:** A para V1; B como proyecto separado.
- **Default seguro:** **A** — sin seguimiento silencioso; ambas tools quedan `BLOCKED_AUTHORITY`.
- **Afectadas:** `presence.locations.list`, `presence.my-location.update`.

## PD-03 — Operaciones financieras de autoridad humana

- **Problema:** corrección de saldo y registro de pagos crean/alteran movimientos reales; no hay compensatorios ficticios.
- **Evidencia:** `finance.balance.correction` (catálogo BLOCKED); `finance.payments.dues.register` → `registerPayment` (`finance.payment.service.js:1312-1336`), R1-d `scopeFilters` no reforzado en despacho; `MIG/20260819020000`, `MIG/20260826000000`.
- **Opciones:** (A) solo UI financiera; (B) exponer con confirmación reforzada tras corregir R1-d; (C) exponer solo corrección con doble aprobación.
- **Implicaciones:** B/C amplían autoridad del asistente sobre dinero real.
- **Recomendación técnica:** A para V1; reevaluar B tras arreglo técnico de R1-d.
- **Default seguro:** **A** — ambas fuera del catálogo; el resto de Finance (62 tools) se implementa igual.
- **Afectadas:** `finance.balance.correction`, `finance.payments.dues.register`.

## PD-04 — Administración de hogar y acciones permanentes

- **Problema:** cambiar rol de miembro, aprobar/rechazar solicitudes de rol, crear/cambiar hogar, expulsar miembros y borrado permanente de producto son acciones privilegiadas o irreversibles.
- **Evidencia:** `householdConstants.js:1-4`; `MIG/202607050001` (role requests); `MIG/202606210009` (finalize/set-active); `inventory.destroy` en `MIG/20261019000001:283` sin espejo en catálogo; `inventory.products.permanent-delete`.
- **Opciones:** (A) solo UI para coordinadores; (B) exponer a coordinadores desde HOMI con confirmación reforzada; (C) exponer todo.
- **Implicaciones:** B es coherente con «maximizar cobertura» pero eleva privilegios desde lenguaje natural.
- **Recomendación técnica:** A para workspace/expulsión; B evaluable para aprobación de solicitudes si Actor A lo autoriza.
- **Default seguro:** **A** — admin de hogar y borrado permanente fuera; las invitaciones y solicitudes de propia solicitud sí están en el catálogo.
- **Afectadas:** `households.member.role.update`, `households.role-request.approve`, `households.role-request.reject`, `households.create`, `households.set-active`, `households.finalize-member`, `inventory.products.permanent-delete`.

## PD-05 — SEE / carga de archivos desde HOMI

- **Problema:** `homecloud.content.access/analyze`, `messages.attachments.download`, `homecloud.content.register/upload/verify/finalize` y `identity.avatar.update` requieren proveedor visual o UI de selección real.
- **Evidencia:** `homi_see_orchestrator.py`; URLs firmadas TTL 3600/300 s; `MIG/20260910000004` buckets privados; AGENTS #43-45.
- **Opciones:** (A) HOMI solo metadatos; (B) integrar HOMI-B para análisis de contenido; (C) permitir carga desde el asistente con picker nativo.
- **Implicaciones:** B/C requieren proveedor y UX adicional; sin SEE real, exponer sería inventar contenido.
- **Recomendación técnica:** A para V1; B/C como ampliación posterior.
- **Default seguro:** **A** — 23 tools de HomeCloud metadatos funcionan; las de píxeles/carga quedan `BLOCKED_DEPENDENCY`.
- **Afectadas:** `homecloud.content.access`, `homecloud.content.analyze`, `homecloud.content.register/upload-authorize/verify/finalize`, `messages.attachments.download`, `messages.attachments.upload-authorize/verify-upload`, `identity.avatar.update`.

## PD-06 — Variante móvil expo-go

- **Problema:** `front/mi-front-expo-go` es copia histórica sin CI; `mi-front-limpio` es el cliente principal/QA.
- **Evidencia:** `01_CURRENT_AUDIT.md §1`; CI `.github/workflows/homeplus-quality.yml`; `tests/run.js:7`.
- **Opciones:** (A) solo `mi-front-limpio`; (B) replicar tile/ruta en ambas desde una fuente común.
- **Implicaciones:** B duplica superficie y riesgo de divergencia sin CI que lo detecte.
- **Recomendación técnica:** A.
- **Default seguro:** **A** — HOMI V1 se entrega solo en `mi-front-limpio`.
- **Afectadas:** superficie móvil (no tools individuales).

---

## Resumen

| Código | Default seguro | Se puede implementar el resto sin esperar |
|---|---|---|
| PD-01 | Exigir petición explícita de gasto | Sí |
| PD-02 | Sin presencia | Sí |
| PD-03 | Solo UI financiera para ajustes/pagos | Sí |
| PD-04 | Solo UI para admin/permanente | Sí |
| PD-05 | Solo metadatos | Sí |
| PD-06 | Solo mi-front-limpio | Sí |

**Ninguna decisión bloquea la pasada 2.** Si Actor A no se pronuncia antes del inicio, se aplican los defaults y las tools afectadas permanecen fuera del catálogo ejecutable.
