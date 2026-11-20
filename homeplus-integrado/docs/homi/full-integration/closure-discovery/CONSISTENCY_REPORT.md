# CONSISTENCY REPORT — Chequeos automáticos (sección 17)

**Verdict:** PASS · 20/20 checks PASS

| ID | Check | Resultado | Detalle |
|---|---|---|---|
| C01 | Inventario total reconstruido | PASS | 350 operaciones (176 anteriores + 174 nuevas netas) |
| C02 | Unicidad de operation IDs | PASS | duplicados: [] |
| C03 | Unicidad de tool IDs | PASS | duplicados: [] |
| C04 | Cada operación tiene exactamente un destino válido | PASS | destinos: {"TARGET_IMPLEMENT":307,"BLOCKED_DEPENDENCY":12,"EXCLUDED_SECURITY":7,"BLOCKED_UNSAFE":5,"EXCLUDED_NOT_PRODUCT":4,"PRODUCT_DECISION":6,"BLOCKED_AUTHOR |
| C05 | Correspondencia operación → tool (target) | PASS | target sin tool: [] |
| C06 | Correspondencia tool → operación target | PASS | tool sin operación: [] |
| C07 | Tool → contrato estructurado completo | PASS | tools incompletos: 0 |
| C08 | Tool → tarea de implementación | PASS | tools sin tarea: [] |
| C09 | WRITE → política de confirmación | PASS | WRITE sin confirmación: 0 |
| C10 | Tool → permisos y campos prohibidos | PASS | tools sin autoridad: 0 |
| C11 | Tool → plan de pruebas | PASS | tools con pruebas insuficientes: 0 |
| C12 | Handler → servicio canónico real | PASS | tools sin servicio: [] |
| C13 | Sin referencias HTTP inválidas | PASS | paths inválidos: 0 |
| C14 | Sin operaciones sin clasificar | PASS | sin razón: 0 |
| C15 | Exclusiones con razón demostrada | PASS | excluidas: 11 |
| C16 | Tareas con criterio de aceptación | PASS | tareas: 21 |
| C17 | Bloqueos con responsable y condición | PASS | bloqueadas: 26 |
| C18 | Dependencias de tareas válidas | PASS | todas las dependencias apuntan a tareas existentes |
| C19 | Decisiones de producto aisladas | PASS | PD: households.member.role.update, households.role-request.approve, households.role-request.reject, finance.balance.correction, finance.payments.dues.register,  |
| C20 | Sin doble fuente de verdad del catálogo | PASS | catálogo=307, objetivo=307 |

## Cuantitativo

```json
{
  "operations_total": 350,
  "target_operations": 307,
  "target_tools": 307,
  "read_tools": 114,
  "write_tools": 193,
  "excluded": 11,
  "blocked": 26,
  "product_decisions": 6,
  "tasks": 21
}
```
