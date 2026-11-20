# QA de presentación pendiente

**Cliente autoritativo:** `front/mi-front-limpio`. TypeScript y `expo export --platform ios` pasaron con `EXPO_PUBLIC_API_URL=http://192.168.0.11:3101`. La IP `192.168.0.11` fue observada en Ethernet; comprobarla otra vez antes del iPhone. La URL prevista de Expo para Metro `:8082` es `exp://192.168.0.11:8082`, pero Metro no se pudo arrancar desde esta sesión: la revisión automática rechazó tanto el inicio oculto como el directo con `blocked by policy`. **No hay `SIMULATOR PASS` ni `DEVICE PASS`.**

Para el QA físico, verificar que los servicios locales `:56221`, `:56222`, `:3101`, `:8002`, THINK `:18011` y HOMI-C `:8010` respondan. Arrancar Metro sólo desde este cliente con `EXPO_PUBLIC_API_URL` apuntando a la IP LAN actual y un puerto libre; el `:8081` abierto pertenece a otro proyecto. La cuenta QA se aprovisiona por el mecanismo local Supabase Auth existente; no copiar tokens o contraseñas a documentación.

**Guion mínimo para Actor A:** abrir HomePlus en Expo Go, login QA, Home → Más → Homie, preguntar por tareas, crear una tarea de prueba, revisar preview, confirmar, verificarla en Planner, volver a Homie, consultar Finanzas e Inventario, dictar un audio y comprobar que el borrador sea editable antes de enviar. Probar teclado y botón Enviar/Confirmar con iPhone real. Si THINK o STT falla, verificar error recuperable y navegación de regreso; no repetir una WRITE incierta.

La muestra completa de Finanzas/Inventario y los cambios de hogar requieren fixtures y verificación adicional antes de una presentación real.
