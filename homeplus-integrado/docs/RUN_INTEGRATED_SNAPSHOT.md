# Ejecutar el snapshot integrado

Entrar a `homeplus-integrado/` después de clonar la rama del mismo nombre. El proyecto productivo original permanece en foreground-gps; esta carpeta remota es una copia de código sanitizada.

1. Usar Node.js compatible con los engines actuales (24 o superior) y npm.
2. Ejecutar `npm ci` en esta carpeta; repetir en `backend/` y en `front/mi-front-limpio/`. Cada carpeta conserva su lockfile.
3. Copiar los ejemplos .env.example a .env y completar los valores propios. Backend: URL/keys del proyecto Supabase y PORT. Front: EXPO_PUBLIC_API_URL, EXPO_PUBLIC_SUPABASE_URL y clave pública de cliente. Nunca copiar service-role al front.
4. Mantener la base remota y sus migraciones verificadas; no ejecutar automáticamente toda la historia SQL sobre un proyecto existente.
5. Iniciar backend con `node index.js` dentro de backend. Iniciar el front principal con `npx expo start --dev-client --lan` dentro de front/mi-front-limpio.
6. Usar un cliente nativo compatible con Expo SDK y React Native del lockfile. Un APK antiguo no es suficiente; el perfil development necesita Metro. Ver docs/DEPLOYMENT_EXHIBITION_READINESS.md para una demo sin LAN ni Metro.
7. Validar con `npm run typecheck`, `npm run test:home`, `npm run test:reactive-ui`, `npm run test:presence` y los contratos focales. Algunas pruebas DB/integración requieren entorno de QA explícito y datos sintéticos.

Se conservó la carpeta front/mi-front-expo-go como fuente secundaria histórica; la interfaz integrada de esta entrega está en front/mi-front-limpio. No se publican env reales, sesiones, seeds con identidades personales, capturas de usuarios ni resultados de QA locales.

La ausencia de secretos/artefactos es intencional; no faltan tablas o código por no incluir una base de datos local. La configuración de infraestructura y la firma se completan fuera de Git.

## Firma de desarrollo Android
El debug.keystore local se excluye de Git. Para compilar Android nativo desde un clon hay que generar una clave debug local con keytool (o usar EAS con sus credenciales). No copiar una clave de producción ni subirla. La configuración CURRENT de release usa signingConfig.debug: antes de una entrega de tienda requiere configurar firma de producción; esta sesión no la cambió.
