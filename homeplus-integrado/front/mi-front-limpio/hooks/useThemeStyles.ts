import { useMemo } from 'react';
import { useAppTheme } from '../context/AppThemeContext';
import type { AppResolvedTheme } from '../constants/theme';

/** Recompute presentation styles only when their semantic theme changes. */
export function useThemeStyles<T>(factory: (theme: AppResolvedTheme) => T): T {
  const theme = useAppTheme();
  return useMemo(() => factory(theme), [factory, theme]);
}
