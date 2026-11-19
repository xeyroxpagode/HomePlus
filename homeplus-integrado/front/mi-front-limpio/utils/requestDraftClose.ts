import { Alert } from 'react-native';

/** Explicit decision only when a dismissal would discard an unsaved draft. */
export function requestDraftClose(dirty: boolean, close: () => void) {
  if (!dirty) { close(); return; }
  Alert.alert('¿Descartar los cambios?', 'Todavía no guardaste los cambios.', [
    { text: 'Seguir editando', style: 'cancel' },
    { text: 'Descartar', style: 'destructive', onPress: close },
  ]);
}
