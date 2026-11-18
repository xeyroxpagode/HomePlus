# Entorno Expo Go separado

`setup-expo-go-copy.cmd` crea o actualiza `front\mi-front-expo-go` desde este workspace sin copiar `android`, `ios`, `node_modules`, `.expo`, `.maestro`, Gradle ni APK/AAB. La copia usa el mismo código TypeScript/JavaScript, pero mantiene su propio `.env` para no mezclar la red de un teléfono físico con la del emulador Android.

Ejecutar en **CMD** desde este directorio:

```cmd
scripts\expo-go\setup-expo-go-copy.cmd
scripts\expo-go\start-expo-go.cmd
```

Los scripts resuelven aliases de carpeta como `C:\HP` antes de localizar la
copia Expo Go, para que tanto la sincronización como Metro utilicen siempre
`front\mi-front-expo-go` y sus dependencias actuales.

En la primera creación, abrir `front\mi-front-expo-go\.env` y cambiar solo esta variable por la IP LAN actual de la PC:

```dotenv
EXPO_PUBLIC_API_URL=http://<IP_DE_TU_PC>:3001
```

`10.0.2.2` se reserva para el emulador Android y debe mantenerse únicamente en el workspace de Android Studio/Maestro (`mi-front-limpio`). Las siguientes sincronizaciones preservan el `.env` específico de Expo Go.

Instalar Expo Go compatible con SDK 57 en el teléfono Android y escanear el QR que muestra Metro. Ambos equipos deben estar en la misma red; si LAN no conecta, detener Metro y usar `npx expo start --go --tunnel --port 8080` dentro de `front\mi-front-expo-go`.

Expo Go sirve para iterar UI y JavaScript. No sustituye el development build: en Android no admite push remoto de `expo-notifications` y no debe usarse para validar background location, configuración nativa, permisos finales, cámara/Maps específicos ni Maestro.
