import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  StyleSheet,
  View,
} from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';

import { useAuth } from '../../context/AuthContext';
import { useAppRefresh } from '../../context/AppRefreshContext';
import {
  ActionSheet,
  AppButton,
  AppCard,
  AppInput,
  AppPageHeader,
  AppScreen,
  AppText,
  ErrorState,
  IconButton,
  Toggle,
  UndoToast,
} from '../../components/ui';
import { HomePlusIcon } from '../../constants/icons';
import { radius, spacing } from '../../constants/theme';
import { ApiError, generateMutationId } from '../../services/api';
import {
  finalizeInventoryPurchase,
  getInventoryIntegrations,
  getInventoryPurchaseDetail,
  retryInventoryPurchaseFinance,
  setInventoryPurchaseLine,
  transitionInventoryPurchase,
  type InventoryIntegrations,
  type InventoryPurchaseLine,
  type InventoryPurchaseResponse,
  type MutationIdentity,
  type VersionedMutationIdentity,
} from '../../services/inventoryV2';

const localDate = () => {
  const date = new Date();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
};

const newIdentity = (operation: string): MutationIdentity => {
  const mutationId = generateMutationId();
  return { mutationId, idempotencyKey: `inventory-purchase-${operation}-${mutationId}` };
};

const formatQuantity = (value: number) => Number.isInteger(value) ? String(value) : String(value).replace('.', ',');

const parseAmountMinor = (value: string): number | null => {
  const raw = value.trim();
  if (!raw) return null;
  const normalized = raw
    .replace(/\s/g, '')
    .replace(/\./g, '')
    .replace(',', '.');
  const amount = Number(normalized);
  return Number.isFinite(amount) && amount >= 0 ? Math.round(amount * 100) : null;
};

const parseQuantity = (value: string): number | null => {
  const parsed = Number(value.trim().replace(',', '.'));
  return Number.isFinite(parsed) && parsed >= 0 && Math.round(parsed * 1000) === parsed * 1000 ? parsed : null;
};

/**
 * The checkout companion for the shared shopping list. All stock and finance
 * effects remain server-owned: this screen only sends versioned, idempotent
 * commands and reloads canonical state after every mutation.
 */
export function InventoryPurchaseScreen() {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const purchaseId = route.params?.purchaseId as string | undefined;
  const { session } = useAuth();
  const { markHomeChanged } = useAppRefresh();
  const accessToken = session?.access_token ?? null;

  const [purchase, setPurchase] = useState<InventoryPurchaseResponse | null>(null);
  const [integrations, setIntegrations] = useState<InventoryIntegrations | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyLineId, setBusyLineId] = useState<string | null>(null);
  const [transitioning, setTransitioning] = useState(false);
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [total, setTotal] = useState('');
  const [registerInFinance, setRegisterInFinance] = useState(false);
  const [retryingFinance, setRetryingFinance] = useState(false);
  const [editingLine, setEditingLine] = useState<InventoryPurchaseLine | null>(null);
  const [purchasedQuantity, setPurchasedQuantity] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);

  const lineIdentityRef = useRef(new Map<string, VersionedMutationIdentity>());
  const transitionIdentityRef = useRef<VersionedMutationIdentity | null>(null);
  const finalizeIdentityRef = useRef<VersionedMutationIdentity | null>(null);
  const retryFinanceIdentityRef = useRef<MutationIdentity | null>(null);

  const load = useCallback(async (showLoader = true) => {
    if (!accessToken || !purchaseId) {
      setLoading(false);
      setError('No pudimos identificar esta compra. Volvé a la lista e intentá de nuevo.');
      return;
    }
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const [detail, integrationData] = await Promise.all([
        getInventoryPurchaseDetail(accessToken, purchaseId),
        getInventoryIntegrations(accessToken),
      ]);
      setPurchase(detail);
      setIntegrations(integrationData);
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 401
        ? 'Tu sesión venció. Volvé a ingresar para continuar la compra.'
        : 'No pudimos abrir esta compra. Confirmá que Inventario V2 esté actualizado e intentá de nuevo.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [accessToken, purchaseId]);

  useFocusEffect(useCallback(() => {
    void load();
  }, [load]));

  const updateLineQuantity = async (line: InventoryPurchaseLine, nextQuantity: number) => {
    if (!accessToken || !purchase || purchase.session.status !== 'active') return;
    const operationKey = `${line.id}:${nextQuantity}`;
    const identity = lineIdentityRef.current.get(operationKey) ?? {
      ...newIdentity(`line-${line.id}-${nextQuantity}`),
      expectedVersion: line.version,
    };
    lineIdentityRef.current.set(operationKey, identity);
    setBusyLineId(line.id);
    setPurchase((current) => {
      if (!current) return current;
      const lines = current.lines.map((entry) => entry.id === line.id
        ? { ...entry, purchased_quantity: nextQuantity, version: entry.version + 1 }
        : entry);
      return {
        ...current,
        lines,
        session: {
          ...current.session,
          purchased_count: lines.filter((entry) => entry.purchased_quantity > 0).length,
          pending_count: lines.filter((entry) => entry.purchased_quantity <= 0).length,
        },
      };
    });
    try {
      const result = await setInventoryPurchaseLine(accessToken, purchase.session.id, line.id, nextQuantity, identity);
      setPurchase((current) => {
        if (!current) return current;
        const lines = current.lines.map((entry) => entry.id === line.id ? result.line : entry);
        return {
          ...current,
          lines,
          session: {
            ...current.session,
            purchased_count: lines.filter((entry) => entry.purchased_quantity > 0).length,
            pending_count: lines.filter((entry) => entry.purchased_quantity <= 0).length,
          },
        };
      });
      lineIdentityRef.current.delete(operationKey);
      setEditingLine(null);
    } catch {
      setPurchase((current) => current ? { ...current, lines: current.lines.map((entry) => entry.id === line.id ? line : entry) } : current);
      Alert.alert('La compra cambió', 'Actualizamos el estado para conservar el último cambio del hogar.');
      await load(false);
    } finally {
      setBusyLineId(null);
    }
  };

  const setLinePurchased = async (line: InventoryPurchaseLine) => {
    await updateLineQuantity(line, line.purchased_quantity > 0 ? 0 : line.requested_quantity);
  };

  const openQuantityEditor = (line: InventoryPurchaseLine) => {
    if (!active) return;
    setEditingLine(line);
    setPurchasedQuantity(formatQuantity(line.purchased_quantity || line.requested_quantity));
  };

  const transition = async (action: 'pause' | 'resume') => {
    if (!accessToken || !purchase) return;
    const identity = transitionIdentityRef.current ?? {
      ...newIdentity(action),
      expectedVersion: purchase.session.version,
    };
    transitionIdentityRef.current = identity;
    setTransitioning(true);
    try {
      await transitionInventoryPurchase(accessToken, purchase.session.id, action, identity);
      transitionIdentityRef.current = null;
      await load(false);
    } catch {
      Alert.alert('No pudimos actualizar la compra', 'Reintentá. El estado no se duplicará.');
    } finally {
      setTransitioning(false);
    }
  };

  const cancelPurchase = () => {
    if (!accessToken || !purchase) return;
    Alert.alert('Cancelar compra', 'La lista de compras se conserva. El stock todavía no cambia.', [
      { text: 'Volver', style: 'cancel' },
      {
        text: 'Cancelar compra',
        style: 'destructive',
        onPress: () => void (async () => {
          const identity = {
            ...newIdentity('cancel'),
            expectedVersion: purchase.session.version,
          };
          setTransitioning(true);
          try {
            await transitionInventoryPurchase(accessToken, purchase.session.id, 'cancel', identity);
            navigation.goBack();
          } catch {
            Alert.alert('No pudimos cancelar la compra', 'Actualizá e intentá nuevamente.');
          } finally {
            setTransitioning(false);
          }
        })(),
      },
    ]);
  };

  const closeFinalize = () => {
    if (!finalizing) setFinalizeOpen(false);
  };

  const finalize = async () => {
    if (!accessToken || !purchase) return;
    const amountMinor = parseAmountMinor(total);
    if (total.trim() && amountMinor === null) return;
    const identity = finalizeIdentityRef.current ?? {
      ...newIdentity('finalize'),
      expectedVersion: purchase.session.version,
    };
    finalizeIdentityRef.current = identity;
    setFinalizing(true);
    try {
      const result = await finalizeInventoryPurchase(accessToken, purchase.session.id, {
        total_amount_minor: amountMinor,
        local_date: localDate(),
        register_in_finance: Boolean(registerInFinance && amountMinor !== null && integrations?.finance.can_register_household_expense),
      }, identity);
      finalizeIdentityRef.current = null;
      setFinalizeOpen(false);
      await load(false);
      markHomeChanged();
      setFeedback(result.finance_sync_status === 'failed'
        ? 'Compra terminada: el stock ya se actualizó. Podés reintentar el gasto desde esta compra.'
        : result.finance_sync_status === 'linked'
          ? 'Compra terminada: actualizamos el stock y registramos el gasto.'
          : 'Compra terminada: actualizamos el stock.');
    } catch {
      // Identity is intentionally retained: a response loss cannot duplicate
      // the stock update or the linked household expense.
      Alert.alert('No pudimos terminar la compra', 'Reintentá. La compra no se duplicará.');
    } finally {
      setFinalizing(false);
    }
  };

  const retryFinance = async () => {
    if (!accessToken || !purchase) return;
    const identity = retryFinanceIdentityRef.current ?? newIdentity('finance-retry');
    retryFinanceIdentityRef.current = identity;
    setRetryingFinance(true);
    try {
      await retryInventoryPurchaseFinance(accessToken, purchase.session.id, identity);
      retryFinanceIdentityRef.current = null;
      await load(false);
    } catch {
      Alert.alert('No pudimos registrar el gasto', 'Reintentá más tarde. El stock ya actualizado no se modifica.');
    } finally {
      setRetryingFinance(false);
    }
  };

  const active = purchase?.session.status === 'active';
  const canFinish = Boolean(active && purchase && purchase.session.purchased_count > 0);
  const financeEnabled = Boolean(integrations?.finance.can_register_household_expense && (parseAmountMinor(total) ?? 0) >= 100);

  return (
    <>
      <AppScreen
        scroll
        bottomInset="tab"
        scrollProps={{
          refreshControl: <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(false); }} tintColor={colors.terracotta[500]} />,
        }}
      >
        <AppPageHeader
          title="Compra"
          subtitle={purchase?.session.status === 'paused' ? 'Compra pausada' : 'Marcá lo que ya compraste'}
          leading={<IconButton icon="chevron-back-outline" variant="plain" onPress={() => navigation.goBack()} accessibilityLabel="Volver a la lista de compras" />}
          action={active ? <IconButton icon="pause-outline" variant="plain" disabled={transitioning} onPress={() => void transition('pause')} accessibilityLabel="Pausar compra" /> : purchase?.session.status === 'paused' ? <IconButton icon="play-outline" variant="plain" disabled={transitioning} onPress={() => void transition('resume')} accessibilityLabel="Reanudar compra" /> : undefined}
          style={styles.header}
        />

        {loading ? (
          <View style={styles.loading}><ActivityIndicator color={colors.terracotta[500]} /><AppText tone="secondary">Cargando compra…</AppText></View>
        ) : error ? (
          <ErrorState description={error} onRetry={() => void load()} />
        ) : purchase ? (
          <View style={styles.content}>
            <AppCard variant="quiet" padding="default" style={styles.summary}>
              <View style={styles.summaryIcon}><HomePlusIcon name="cart-outline" size={22} color={colors.terracotta[600]} /></View>
              <View style={styles.summaryCopy}>
                <AppText weight="700">{purchase.session.purchased_count} de {purchase.session.total_count} comprados</AppText>
                <AppText variant="caption" tone="secondary">El stock cambia recién al terminar la compra.</AppText>
              </View>
            </AppCard>

            {purchase.session.finance_sync_status === 'failed' ? (
              <AppCard variant="quiet" padding="default" style={styles.financeWarning}>
                <View style={styles.summaryCopy}>
                  <AppText weight="700" tone="danger">El stock ya se actualizó</AppText>
                  <AppText variant="caption" tone="secondary">Falta registrar el gasto en Finanzas.</AppText>
                </View>
                <AppButton title="Reintentar" size="sm" variant="secondary" loading={retryingFinance} onPress={() => void retryFinance()} />
              </AppCard>
            ) : null}

            <View style={styles.list}>
              {purchase.lines.map((line) => {
                const purchased = line.purchased_quantity > 0;
                const busy = busyLineId === line.id;
                return (
                  <AppCard key={line.id} variant="default" padding="default" style={styles.lineCard}>
                    <IconButton
                      icon={purchased ? 'checkmark' : 'ellipse-outline'}
                      variant={purchased ? 'brandSoft' : 'plain'}
                      disabled={!active || busy}
                      onPress={() => void setLinePurchased(line)}
                      accessibilityLabel={purchased ? `Desmarcar ${line.name_snapshot}` : `Marcar ${line.name_snapshot} como comprado`}
                    />
                    <Pressable
                      style={styles.lineCopy}
                      disabled={!active || busy}
                      onPress={() => openQuantityEditor(line)}
                      accessibilityRole="button"
                      accessibilityLabel={`Editar cantidad comprada de ${line.name_snapshot}`}
                    >
                      <AppText weight="700" style={purchased ? styles.purchasedText : undefined}>{line.name_snapshot}</AppText>
                      <AppText variant="caption" tone="secondary">{formatQuantity(line.requested_quantity)} {line.requested_quantity === 1 ? 'unidad' : 'unidades'}</AppText>
                    </Pressable>
                    {purchased ? <AppText variant="caption" tone="success" weight="700">Comprado</AppText> : null}
                  </AppCard>
                );
              })}
            </View>

            {active ? (
              <View style={styles.actions}>
                <AppButton title="Finalizar compra" disabled={!canFinish} onPress={() => setFinalizeOpen(true)} accessibilityLabel="Finalizar compra y actualizar stock" />
                <AppButton title="Cancelar compra" variant="ghost" disabled={transitioning} onPress={cancelPurchase} />
              </View>
            ) : purchase.session.status === 'paused' ? (
              <AppButton title="Reanudar compra" loading={transitioning} onPress={() => void transition('resume')} />
            ) : null}
          </View>
        ) : null}
      </AppScreen>

      <ActionSheet
        visible={finalizeOpen}
        title="Finalizar compra"
        subtitle="Confirmá el total si querés registrarlo también en Finanzas."
        onRequestClose={closeFinalize}
        closeDisabled={finalizing}
        size="content"
        keyboardAware
        footer={(
          <View style={styles.sheetActions}>
            <AppButton title="Volver" variant="ghost" disabled={finalizing} onPress={closeFinalize} style={styles.grow} />
            <AppButton title="Actualizar stock" loading={finalizing} onPress={() => void finalize()} style={styles.grow} />
          </View>
        )}
      >
        <View style={styles.sheetContent}>
          <AppInput
            label="Total de la compra (opcional)"
            value={total}
            onChangeText={setTotal}
            keyboardType="decimal-pad"
            placeholder="Ej. 12.500"
            accessibilityLabel="Total de la compra, opcional"
          />
          {integrations?.finance.can_register_household_expense ? (
            <View style={styles.financeToggle}>
              <View style={styles.toggleCopy}>
                <AppText weight="700">Registrar gasto en Finanzas</AppText>
                <AppText variant="caption" tone="secondary">Se crea una sola vez al finalizar.</AppText>
              </View>
              <Toggle
                value={registerInFinance}
                onValueChange={(value) => setRegisterInFinance(value ? financeEnabled : false)}
                disabled={!financeEnabled && !registerInFinance}
                accessibilityLabel="Registrar gasto de compra en Finanzas"
              />
            </View>
          ) : null}
          {registerInFinance && !financeEnabled ? <AppText variant="caption" tone="tertiary">Ingresá un total para registrar el gasto.</AppText> : null}
        </View>
      </ActionSheet>

      <ActionSheet
        visible={Boolean(editingLine)}
        title="Cantidad comprada"
        subtitle={editingLine?.name_snapshot}
        onRequestClose={() => { if (!busyLineId) setEditingLine(null); }}
        closeDisabled={Boolean(busyLineId)}
        size="content"
        keyboardAware
        footer={(
          <View style={styles.sheetActions}>
            <AppButton title="Volver" variant="ghost" disabled={Boolean(busyLineId)} onPress={() => setEditingLine(null)} style={styles.grow} />
            <AppButton
              title="Guardar"
              loading={Boolean(busyLineId)}
              disabled={parseQuantity(purchasedQuantity) === null}
              onPress={() => {
                const next = parseQuantity(purchasedQuantity);
                if (editingLine && next !== null) void updateLineQuantity(editingLine, next);
              }}
              style={styles.grow}
            />
          </View>
        )}
      >
        <View style={styles.sheetContent}>
          <AppText variant="bodySmall" tone="secondary">Solicitado: {editingLine ? formatQuantity(editingLine.requested_quantity) : '0'}. Podés registrar una compra parcial.</AppText>
          <AppInput
            label="Cantidad que compraste"
            value={purchasedQuantity}
            onChangeText={setPurchasedQuantity}
            keyboardType="decimal-pad"
            errorText={purchasedQuantity && parseQuantity(purchasedQuantity) === null ? 'Ingresá 0 o una cantidad válida.' : undefined}
          />
        </View>
      </ActionSheet>
      <UndoToast visible={Boolean(feedback)} message={feedback ?? ''} onDismiss={() => setFeedback(null)} />
    </>
  );
}



function createStylesForTheme({ colors }: Pick<AppResolvedTheme, 'colors'>) {
  return StyleSheet.create({
  header: { marginBottom: spacing[4] },
  loading: { minHeight: 180, alignItems: 'center', justifyContent: 'center', gap: spacing[3] },
  content: { gap: spacing[3] },
  summary: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
  summaryIcon: { width: 44, height: 44, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.terracotta[100] },
  summaryCopy: { flex: 1, gap: spacing[1] },
  financeWarning: { flexDirection: 'row', alignItems: 'center', gap: spacing[3], borderColor: colors.warning.base, borderWidth: 1 },
  list: { gap: spacing[2] },
  lineCard: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
  lineCopy: { flex: 1, gap: spacing[1] },
  purchasedText: { textDecorationLine: 'line-through', color: colors.text.tertiary },
  actions: { gap: spacing[1] },
  sheetContent: { gap: spacing[4] },
  financeToggle: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing[3] },
  toggleCopy: { flex: 1, gap: spacing[1] },
  sheetActions: { flexDirection: 'row', gap: spacing[3] },
  grow: { flex: 1 },
});
}
