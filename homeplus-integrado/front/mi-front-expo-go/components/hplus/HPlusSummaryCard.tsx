import React, { useCallback, useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { AppCard } from '../ui/AppCard';
import { AppText } from '../ui/AppText';
import { colors, radius, spacing } from '../../constants/theme';
import { useAuth } from '../../context/AuthContext';
import { useHousehold } from '../../context/HouseholdContext';
import { supabase } from '../../supabase';
import { getHPlusSummary, type HPlusSummary } from '../../services/hplus';

export function HPlusSummaryCard() {
  const { session } = useAuth();
  const { currentHousehold } = useHousehold();
  const [summary, setSummary] = useState<HPlusSummary | null>(null);
  const [error, setError] = useState(false);
  const load = useCallback(async () => {
    if (!session?.access_token) return;
    try { setSummary(await getHPlusSummary(session.access_token)); setError(false); } catch { setError(true); }
  }, [session?.access_token]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!session?.access_token || !currentHousehold?.id) return undefined;
    let channel: ReturnType<typeof supabase.channel> | null = null;
    void supabase.realtime.setAuth(session.access_token).then(() => {
      channel = supabase.channel(`hplus:${currentHousehold.id}`)
        .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'hplus_ledger_entries', filter: `household_id=eq.${currentHousehold.id}` }, () => void load())
        .subscribe();
    }).catch(() => undefined);
    return () => { if (channel) void supabase.removeChannel(channel); };
  }, [currentHousehold?.id, load, session?.access_token]);

  return <View testID="hplus.summary"><AppCard variant="default" padding="default" style={styles.card}>
    <View style={styles.heading}><View style={styles.mark}><AppText variant="body" weight="800" style={{ color: colors.terracotta[600] }}>H+</AppText></View><View><AppText variant="bodySmall" weight="800">Tus contribuciones</AppText><AppText variant="caption" tone="secondary">Acciones reales que ayudan al hogar</AppText></View></View>
    {error ? <AppText variant="bodySmall" tone="secondary">No pudimos actualizar H+ ahora.</AppText> : <><AppText variant="hero" weight="800" style={styles.points}>{summary?.my_points ?? '—'} <AppText variant="bodySmall" tone="secondary">puntos</AppText></AppText><AppText variant="caption" tone="secondary">{summary?.recent_entries.length ? `${summary.recent_entries.length} contribución${summary.recent_entries.length === 1 ? '' : 'es'} reciente${summary.recent_entries.length === 1 ? '' : 's'}` : 'Todavía no hay contribuciones registradas.'}</AppText></>}
  </AppCard></View>;
}
const styles = StyleSheet.create({ card: { marginBottom: spacing[4] }, heading: { flexDirection: 'row', alignItems: 'center', gap: spacing[2] }, mark: { width: 38, height: 38, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.terracotta[50] }, points: { marginTop: spacing[3], color: colors.text.primary } });
