# QA E2E local con Maestro

## Requisitos

- Java 17 o superior (`java -version`).
- Android SDK Platform Tools y un dispositivo/emulador en estado `device` (`adb devices`).
- Maestro CLI disponible en una terminal nueva (`maestro --version`).
- Un development build de HomePlus instalado: Android package `com.anonymous.homeplus`; iOS bundle identifier `com.anonymous.homeplus`.

HomePlus usa Expo SDK 57, `expo-dev-client`, `expo-notifications`, `expo-location` y otros plugins nativos. Por eso esta suite prueba un development build o un build preview/release de HomePlus, nunca Expo Go.

## Iniciar el emulador y la app

El AVD existente es `HomePlus_API_35`. Iniciarlo desde una terminal nueva:

```powershell
& 'C:\Android\Sdk\emulator\emulator.exe' -avd HomePlus_API_35
adb devices
```

Cuando el emulador diga `device`, instalá/abrí HomePlus. Si todavía no existe un build Android, el camino mínimo local es, desde este directorio:

```powershell
npx expo run:android --device
```

Ese comando genera el proyecto nativo local de Expo y requiere el emulador iniciado. Si se prefiere el development build remoto, iniciar sesión de Expo/EAS con la cuenta autorizada y ejecutar `npx eas build --platform android --profile development`; descargar e instalar el APK resultante con `adb install <ruta-del-apk>`. No se usan credenciales de EAS ni URLs privadas en este repositorio.

## Estrategia de sesión y datos QA

La suite es autosuficiente: el primer `npm run qa:fixtures` crea `../../.env.qa` ignorado por Git con URL y nombres QA derivables. Para completar el bootstrap hace falta una `QA_SUPABASE_SECRET_KEY` válida (preferida) o una `QA_SUPABASE_SERVICE_ROLE_KEY` legacy válida, disponible sólo en el proceso local/CI QA; el script rechaza claves anon, publishable o públicas y nunca copia ninguna clave administrativa al frontend. Con esa credencial, provisiona/reutiliza las tres cuentas dedicadas (`QA_A_COORDINATOR`, `QA_B_MEMBER`, `QA_C_MEMBER`) y genera contraseñas fuertes locales cuando faltan.

Antes de cada suite autenticada, `npm run qa:fixtures` provisiona/reutiliza exclusivamente esas cuentas QA mediante Supabase Admin, crea sus proyecciones/membresías si faltan y reinicia exclusivamente conversaciones y Tasks de ese hogar QA. No resetea la base y no existe como endpoint móvil. La clave administrativa queda únicamente en el entorno del script local/CI.

`ensure-authenticated.yaml` reutiliza una sesión válida o inicia sesión real con `QA_A`; no hay bypass de Supabase Auth ni de RLS. Cada emulador conserva su almacenamiento aislado.

La carrera exacta de `Me encargo` se prueba en backend con transacciones concurrentes y es la autoridad de integridad. Con tres devices, `test:e2e:multi` ejecuta los claims B/C en jobs separados para comprobar convergencia visual y realtime; esa prueba complementa, pero no reemplaza, el contrato backend.

## Ejecutar

Desde `front\mi-front-limpio`:

```powershell
npm run test:e2e:preflight
npm run test:e2e:auth
npm run test:e2e:smoke
npm run test:e2e
npm run test:e2e:multi
```

Los scripts leen `expo.android.package` de `app.json`, propagan los códigos de error de Maestro y detienen la ejecución si Java, ADB, un dispositivo, la configuración QA o el paquete no están listos. `test:e2e:multi` requiere dos devices; `start-multi-device.ps1` solo detecta y asigna los seriales disponibles, nunca inicia AVDs masivamente.

## Crear un flow

Crear un YAML bajo `.maestro/<dominio>/`. Declarar el `appId`, usar `shared/ensure-authenticated.yaml` cuando requiera una sesión y seleccionar por `testID` o `accessibilityLabel`. Ejecutar primero el flow individual:

```powershell
maestro test -e HOMEPLUS_ANDROID_APP_ID=com.anonymous.homeplus .maestro\<dominio>\mi-flow.yaml
```

Política de selectores: preferir `testID` estable para superficies globales, `accessibilityLabel` semántico para controles de negocio y texto estable solo cuando sea parte del contrato visible. Nunca usar coordenadas absolutas salvo un bloqueo demostrado. Los IDs existentes para esta base incluyen `auth.email`, `auth.password`, `auth.submit`, `auth.error`, `auth.ready`, `app.shell`, `nav.home`, `nav.planner`, `nav.messages`, `header.messages`, `screen.messages.conversation`, `messages.composer.input`, `messages.composer.send`, `messages.action.add` y `messages.action.sheet`.

## Maestro Studio

Maestro Studio es opcional para crear e inspeccionar flows; el CLI es la fuente de ejecución automatizada. Descargar solamente el instalador oficial [MaestroStudio.exe](https://studio.maestro.dev/MaestroStudio.exe), abrirlo y seguir el asistente de Windows. Instalar para el usuario actual si ofrece esa opción, aceptar el acceso de firewall solo si se solicita para el emulador local, y comprobarlo abriendo Studio, seleccionando este directorio como workspace y conectando `HomePlus_API_35`.

## Contrato QA para futuros slices

Cada slice debe entregar: código QA, tests de dominio, un flow Maestro cuando la UI sea automatizable y QA en dispositivo cuando aplique.

Maestro es adecuado para navegación, formularios, sheets, botones, creación/edición, estados de UI, Mensajes, Planner, Profile e Inventory. QA físico es obligatorio para GPS real, push real, background location, cámara, diálogos finales de permisos, realtime crítico entre dos dispositivos y comportamiento específico de iOS físico. Maestro no sustituye esas verificaciones.
