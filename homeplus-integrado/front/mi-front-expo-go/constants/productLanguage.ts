/** Canonical user-facing names. Route and API identifiers remain unchanged. */
export const productNames = {
  home: 'Home',
  planner: 'Planner',
  tasks: 'Tareas',
  calendar: 'Calendario',
  plans: 'Planes',
  inventory: 'Inventario',
  shopping: 'Lista de compras',
  finance: 'Finanzas',
  family: 'Familia',
  map: 'Mapa',
  people: 'Personas',
  messages: 'Mensajes',
  files: 'Archivos',
  profile: 'Perfil',
  settings: 'Configuración',
} as const;

export const productActions = {
  add: 'Agregar',
  save: 'Guardar',
  cancel: 'Cancelar',
  createTask: 'Crear tarea',
  claimTask: 'Me encargo',
  approve: 'Aprobar',
  shareLocation: 'Compartir ubicación',
  stopLocation: 'Detener',
  recenterMap: 'Recentrar',
  inviteMember: 'Invitar integrante',
  send: 'Enviar',
  retry: 'Reintentar',
} as const;
