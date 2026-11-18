import { ApiError } from '../api';

export function homeCloudUploadErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.code === 'file_too_large') {
      return 'El archivo supera el tamaño máximo permitido para este hogar.';
    }
    if (error.status === 401) {
      return 'Tu sesión venció. Volvé a ingresar e intentá nuevamente.';
    }
    if (error.status === 403) {
      return 'No tenés permiso para agregar contenido en este hogar.';
    }
    if (error.status === 0) {
      return 'No pudimos conectarnos para completar la carga. Revisá tu conexión y reintentá.';
    }
    if (error.status >= 500) {
      return 'No pudimos preparar la carga. Intentá nuevamente.';
    }
  }

  const message = error instanceof Error ? error.message.toLowerCase() : '';
  if (message.includes('upload transport failed') || message.includes('network') || message.includes('timeout')) {
    return 'No pudimos conectarnos para completar la carga. Revisá tu conexión y reintentá.';
  }

  // Never expose the upload state-machine internals as product copy. The
  // retry action remains the same and the durable job preserves its identity.
  return fallback;
}
