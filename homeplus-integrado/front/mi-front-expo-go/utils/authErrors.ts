const AUTH_ERROR_MESSAGES: Array<[string, string]> = [
  ['invalid login credentials', 'El correo o la contraseña no coinciden. Revisá los datos y probá de nuevo.'],
  ['email not confirmed', 'Tu cuenta todavía no está confirmada. Revisá tu correo y probá de nuevo.'],
  ['user already registered', 'Ya existe una cuenta con ese correo. Podés iniciar sesión o recuperar tu contraseña.'],
  ['password should be at least', 'La contraseña debe tener al menos 6 caracteres.'],
  ['network request failed', 'No pudimos conectarnos. Revisá tu conexión y probá de nuevo.'],
  ['unable to validate email address', 'Ingresá un correo válido.'],
  ['auth session missing', 'El enlace de recuperación ya no es válido. Solicitá uno nuevo.'],
  ['same password', 'Elegí una contraseña diferente a la anterior.'],
];

const FALLBACK_ERROR_MESSAGE = 'No pudimos completar la acción. Probá de nuevo en unos segundos.';

export const getAuthErrorMessage = (
  error: unknown,
  fallbackMessage = FALLBACK_ERROR_MESSAGE,
) => {
  const rawMessage =
    typeof error === 'string'
      ? error
      : typeof error === 'object' &&
          error !== null &&
          'message' in error &&
          typeof error.message === 'string'
        ? error.message
        : '';

  const normalizedMessage = rawMessage.trim().toLowerCase();

  for (const [matcher, friendlyMessage] of AUTH_ERROR_MESSAGES) {
    if (normalizedMessage.includes(matcher)) {
      return friendlyMessage;
    }
  }

  return fallbackMessage;
};
