import type {
  AssetDto,
  AssetHolder,
  AssetPlacement,
  AssetProfile,
  AssetResponsible,
  AssetLifecycleStatus,
  ManualCareDto,
} from '../../services/assets';

/**
 * Proyección humana canónica del contexto (Target §8, Personas y ubicación).
 * Frases naturales, en este orden de prioridad:
 *   1. Quién lo tiene (Holder).
 *   2. Dónde está (Placement).
 *   3. Responsable.
 *   4. Categoría.
 * Nunca se muestran todas simultáneamente y nunca tres "Sin especificar".
 */
export const describeHolder = (holder: AssetHolder): string | null => {
  if (!holder || holder.kind === 'none') return null;
  if (holder.kind === 'member') {
    const name = holder.display_name ?? 'un miembro del hogar';
    return `Lo tiene ${name}`;
  }
  const label = holder.label?.trim();
  return label ? `Lo tiene ${label}` : null;
};

export const describePlacement = (placement: AssetPlacement): string | null => {
  if (!placement || placement.kind === 'none') return null;
  if (placement.kind === 'text') {
    const text = placement.text?.trim();
    return text ? `Está en ${text}` : null;
  }
  const property = placement.property_name?.trim() || 'una propiedad';
  const detail = placement.detail?.trim();
  return detail ? `Está en ${property} · ${detail}` : `Está en ${property}`;
};

export const describeResponsible = (responsible: AssetResponsible): string | null => {
  if (!responsible) return null;
  const name = responsible.display_name ?? 'un miembro del hogar';
  return `A cargo de ${name}`;
};

export const describeContextLine = (asset: AssetDto): string | null => {
  return (
    describeHolder(asset.holder) ??
    describePlacement(asset.placement) ??
    describeResponsible(asset.responsible) ??
    (asset.category?.name ? asset.category.name : null)
  );
};

export type LifecyclePill = {
  label: string;
  tone: 'neutral' | 'warning' | 'danger';
} | null;

/** Pill sólo cuando informa algo: ACTIVE no lleva pill. */
export const lifecyclePill = (status: AssetLifecycleStatus): LifecyclePill => {
  switch (status) {
    case 'ACTIVE':
      return null;
    case 'INACTIVE':
      return { label: 'Inactivo', tone: 'neutral' };
    case 'ARCHIVED':
      return { label: 'Archivado', tone: 'warning' };
    case 'TRASH':
      return { label: 'En papelera', tone: 'danger' };
    default:
      return null;
  }
};

export const LIFECYCLE_LABEL: Record<AssetLifecycleStatus, string> = {
  ACTIVE: 'Activo',
  INACTIVE: 'Inactivo',
  ARCHIVED: 'Archivado',
  TRASH: 'En la papelera',
};

/**
 * Profiles de V1 en lenguaje humano. Fuente canónica: el create la usa para
 * elegir y el cambio de tipo la usa para mostrar, así el mismo dato nunca se
 * lee de dos formas.
 */
export const PROFILE_LABEL: Record<AssetProfile, string> = {
  STANDARD: 'Objeto o equipo',
  VEHICLE: 'Vehículo',
  PET: 'Mascota',
  PROPERTY: 'Propiedad',
};

/**
 * Motivos de archivado en lenguaje humano. Es la fuente canónica: la hoja de
 * archivado la usa para elegir y el historial la usa para mostrar, así el
 * mismo dato nunca se lee de dos formas.
 */
export const ARCHIVE_DISPOSITION_LABEL: Record<string, string> = {
  SOLD: 'Vendido',
  GIFTED: 'Regalado',
  DISPOSED: 'Desechado',
  LOST: 'Perdido',
  STOLEN: 'Robado',
  REPLACED: 'Reemplazado',
  DECEASED: 'Falleció (mascota)',
  OTHER: 'Otro motivo',
};

/** El motivo en humano; si el backend manda algo desconocido, se muestra tal cual. */
export const describeDisposition = (disposition: string | null | undefined): string | null => {
  if (!disposition) return null;
  return ARCHIVE_DISPOSITION_LABEL[disposition] ?? disposition;
};

/**
 * Los identificadores por perfil. Es la fuente canónica: el alta y la edición
 * ofrecen exactamente los mismos campos, con la misma etiqueta y el mismo
 * ejemplo.
 */
export const ASSET_IDENTIFIER_FIELDS: Record<
  string,
  { key: string; label: string; placeholder: string }[]
> = {
  STANDARD: [],
  VEHICLE: [
    { key: 'plate', label: 'Patente', placeholder: 'Ej: ABC 123 CD' },
    { key: 'vin', label: 'VIN', placeholder: 'Ej: 17 alfanuméricos' },
  ],
  PET: [
    { key: 'microchip', label: 'Microchip', placeholder: 'Ej: 985112345678901' },
    { key: 'species', label: 'Especie', placeholder: 'Ej: Perro' },
    { key: 'breed', label: 'Raza', placeholder: 'Ej: Labrador' },
  ],
  PROPERTY: [
    { key: 'cadastral_ref', label: 'Referencia catastral', placeholder: 'Ej: C-1234-5678' },
    { key: 'address_text', label: 'Dirección', placeholder: 'Ej: Av. Siempre Viva 742' },
  ],
};

/** Identidad compacta del activo para filas y fichas (sin duplicar datos). */
export const describeIdentity = (asset: AssetDto): string | null => {
  const parts = [asset.brand?.trim(), asset.model?.trim()].filter(
    (part): part is string => Boolean(part),
  );
  if (parts.length > 0) return parts.join(' ');
  return asset.category?.name ?? null;
};

/**
 * La fecha de un cuidado, en el mismo formato en toda la app (dd/mm/aaaa).
 * La precisión decide el detalle: día exacto, mes+año o sólo año.
 */
export const formatCareDate = (care: ManualCareDto): string => {
  switch (care.date_precision) {
    case 'exact':
      return care.occurred_on
        ? (() => {
            const [y, m, d] = care.occurred_on.split('-').map(Number);
            return `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}`;
          })()
        : 'Fecha desconocida';
    case 'month_year':
      return `${String(care.occurred_month ?? '').padStart(2, '0')}/${care.occurred_year ?? ''}`;
    case 'year':
      return String(care.occurred_year ?? '');
    default:
      return 'Sin fecha';
  }
};
