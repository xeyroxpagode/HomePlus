# Exposición multidispositivo — preparación, sin despliegue

Fecha: 2026-11-17. Auditoría de código/configuración, sin tocar servicios remotos.

## CURRENT comprobado
- Express escucha `process.env.PORT || 3000` en `0.0.0.0`; el entorno local usa 3001.
- Front principal y backend apuntan a Supabase remoto. API móvil aún depende de LAN HTTP; no hay túnel configurado en sus env efectivos.
- Backend tiene CORS por ambiente: en producción sin CORS_ORIGIN admite clientes móviles sin Origin, pero no una web pública.
- Supabase Auth, PostgreSQL, Storage y Realtime conservan sus autoridades actuales. No se aplicaron migraciones.
- Ya existe eas.json con development, preview y production; development necesita Metro y no es distribución autónoma.
- En web, services/api.ts reemplaza el hostname de API por localhost: la web pública NO está lista. Corregir y validar ese contrato en un trabajo separado antes de ofrecerla.
- No se midieron capacidad de usuarios, conexiones máximas ni carga concurrente. La configuración de cuotas del proyecto/plan requiere acceso operativo.

## Arquitectura propuesta
1. Entorno demo Supabase separado, con datos sintéticos, Auth, RLS, buckets privados y publicaciones Realtime verificadas.
2. Railway para Express, servicio con raíz `homeplus-integrado/backend`, instalación npm ci, arranque node index.js. PORT lo suministra el proveedor.
3. Configurar secretos exclusivamente en Railway; SUPABASE_SERVICE_ROLE_KEY nunca entra en EXPO_PUBLIC_*.
4. HTTPS público estable para backend y EXPO_PUBLIC_API_URL del build demo. Supabase usa su propia URL HTTPS, sin túnel de base de datos.
5. Expo EAS preview para Android distribuible sin Metro; conservar las credenciales de firma fuera del repositorio.
6. iOS: firma, dispositivo registrado/ad hoc o TestFlight y cuenta Apple habilitada; no equiparar export iOS con instalación o QA físico.

Express necesita PORT y binding público compatibles con Railway: [documentación oficial](https://docs.railway.com/networking/troubleshooting/application-failed-to-respond).
Distribución y firma iOS: [Expo internal distribution](https://docs.expo.dev/build/internal-distribution/) y [permisos Apple Developer](https://docs.expo.dev/app-signing/apple-developer-program-roles-and-permissions/).

## Pasos y aceptación
- Provisionar demo aislado; inventariar migraciones aplicadas y secretos sin copiarlos a Git.
- Verificar instalación limpia del snapshot, permisos, archivos privados, recuperación de sesión y health del backend.
- Configurar CORS solo para origins web reales si se habilita web; CORS no reemplaza autenticación/RLS.
- Publicar backend demo y construir Android preview contra HTTPS; probar desde dos redes distintas, sin PC/Metro.
- Preparar dos hogares de prueba y usuarios autorizados/de lectura. Incrementar participantes por lotes pequeños.
- Probar login simultáneo, lectura y escritura concurrente con idempotencia; una compra no puede duplicar stock o gastos.
- Verificar que ningún usuario vea datos del otro hogar, ni reciba sus eventos Realtime, ni sus URLs de Storage.
- Interrumpir red, reconectar, volver de background y renovar sesión; comprobar dedup, contexto y recuperación.
- Medir p50/p95 de endpoints, errores, CPU/RAM, conexiones y transferencia Storage durante cada lote. Acordar umbrales con QA antes del evento; no hay capacidad máxima demostrada.
- Observar logs sanitizados y preparar rollback del build/API demo, sin alterar producción.

## Costos y límites por verificar
Planes vigentes de Railway (CPU/RAM/egreso), Expo (builds/colas), Apple Developer y Supabase (DB, Storage, egreso y Realtime). No se contrataron planes ni se estimaron importes sin presupuesto.
Las cuotas dependen del plan: [Supabase Realtime limits](https://supabase.com/docs/guides/realtime/limits).

## Riesgos abiertos
Dependencia LAN actual, configuración/firma EAS no verificada en nube, web localhost, pruebas iOS físicas pendientes, carga concurrente sin medir y deuda lint preexistente. Este documento no afirma readiness de producción ni despliega servicios.
