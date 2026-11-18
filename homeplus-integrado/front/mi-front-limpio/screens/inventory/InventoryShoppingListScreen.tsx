import { useAppTheme } from '../../context/AppThemeContext';
import { useThemeStyles } from '../../hooks/useThemeStyles';
import { type AppResolvedTheme } from '../../constants/theme';
import React, { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  StyleSheet,
  View,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';

import { useAuth } from '../../context/AuthContext';
import {
  AppButton,
  AppCard,
  AppInput,
  AppPageHeader,
  AppScreen,
  AppText,
  ActionSheet,
  EmptyState,
  ErrorState,
  IconButton,
  UndoToast,
} from '../../components/ui';
import { HomePlusIcon } from '../../constants/icons';
import { radius, spacing } from '../../constants/theme';
import { ApiError, generateMutationId } from '../../services/api';
import {
  addInventoryShoppingItem,
  clearInventoryShoppingList,
  createInventoryShoppingPlannerTask,
  discoverInventoryShopping,
  getInventoryIntegrations,
  getInventoryShoppingList,
  removeInventoryShoppingItem,
  startInventoryPurchase,
  updateInventoryShoppingItem,
  type InventoryIntegrations,
  type InventoryShoppingItem,
  type InventoryShoppingResponse,
  type MutationIdentity,
} from '../../services/inventoryV2';

const newIdentity = (operation: string): MutationIdentity => {
  const mutationId = generateMutationId();
  return { mutationId, idempotencyKey: `inventory-shopping-${operation}-${mutationId}` };
};

const validQuantity = (value: string) => {
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed * 1000) / 1000 : null;
};

/**
 * Inventory V2 shopping surface. It intentionally uses the shared V2 HTTP
 * authority directly instead of a second client-side store: the screen stays
 * safe to mount only after its remote migration has been applied, while the
 * existing V1 inventory surface remains untouched.
 */
export function InventoryShoppingListScreen() {
  const { colors } = useAppTheme();
  const styles = useThemeStyles(createStylesForTheme);

  const navigation = useNavigation<any>();
  const { session } = useAuth();
  const accessToken = session?.access_token ?? null;

  const [shopping, setShopping] = useState<InventoryShoppingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [saving, setSaving] = useState(false);
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const [startingPurchase, setStartingPurchase] = useState(false);
  const [creatingPlannerTask, setCreatingPlannerTask] = useState(false);
  const [integrations, setIntegrations] = useState<InventoryIntegrations | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [plannerTaskNotice, setPlannerTaskNotice] = useState<{ id: string; existing: boolean } | null>(null);
  const addIdentityRef = useRef<MutationIdentity | null>(null);
  const startPurchaseIdentityRef = useRef<MutationIdentity | null>(null);
  const plannerTaskIdentityRef = useRef<MutationIdentity | null>(null);

  const load = useCallback(async (showLoader = true) => {
    if (!accessToken) {
      setLoading(false);
      return;
    }
    if (showLoader) setLoading(true);
    setError(null);
    try {
      // Planner capability is supplementary. A failure there must never hide
      // the household shopping list, which remains the primary surface.
      const [shoppingResult, integrationsResult] = await Promise.allSettled([
        getInventoryShoppingList(accessToken),
        getInventoryIntegrations(accessToken),
      ]);
      if (shoppingResult.status === 'rejected') throw shoppingResult.reason;
      setShopping(shoppingResult.value);
      setIntegrations(integrationsResult.status === 'fulfilled' ? integrationsResult.value : null);
    } catch (cause) {
      const message = cause instanceof ApiError && cause.status === 401
        ? 'Tu sesión venció. Volvé a ingresar para ver la lista.'
        : 'No pudimos abrir la lista. Confirmá que las migraciones de Inventario V2 estén aplicadas y reintentá.';
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [accessToken]);

  useFocusEffect(useCallback(() => {
    void load();
  }, [load]));

  const closeAdd = () => {
    if (saving) return;
    setAddOpen(false);
    setName('');
    setQuantity('1');
    addIdentityRef.current = null;
  };

  const createItem = async () => {
    const requestedQuantity = validQuantity(quantity);
    if (!accessToken || !name.trim() || !requestedQuantity) return;
    setSaving(true);
    try {
      const identity = addIdentityRef.current ?? newIdentity('add');
      addIdentityRef.current = identity;
      // A manual name that exactly matches an existing household product must
      // keep that product identity. This is what lets a completed purchase add
      // stock back to "Leche" instead of creating an unrelated custom line.
      const normalizedName = name.trim().toLocaleLowerCase('es-AR');
      // Discovery enriches a manual entry when the product already exists in
      // this household. It must never make the basic shopping-list action
      // unavailable if the optional lookup is temporarily unavailable.
      let matchingInventoryItem: { id: string; name?: string } | undefined;
      try {
        const discovery = await discoverInventoryShopping(accessToken, name.trim());
        matchingInventoryItem = discovery.inventory.find((item: { name?: string }) =>
          item.name?.trim().toLocaleLowerCase('es-AR') === normalizedName,
        );
      } catch {
        matchingInventoryItem = undefined;
      }
      const result = await addInventoryShoppingItem(accessToken, matchingInventoryItem
        ? {
          source: 'inventory',
          inventory_item_id: matchingInventoryItem.id,
          quantity: requestedQuantity,
        }
        : {
          source: 'custom',
          name: name.trim(),
          quantity: requestedQuantity,
          track_in_inventory: false,
        }, identity);
      setShopping((current) => {
        if (!current) return current;
        const alreadyThere = current.items.some((item) => item.id === result.item.id);
        return {
          ...current,
          items: alreadyThere
            ? current.items.map((item) => item.id === result.item.id ? result.item : item)
            : [...current.items, result.item],
        };
      });
      closeAdd();
      setFeedback(matchingInventoryItem
        ? `${name.trim()} quedó vinculada a Inventario.`
        : `${name.trim()} se agregó a la lista.`);
    } catch {
      // Preserve identity so an explicit retry cannot create a second line.
      Alert.alert('No pudimos agregarlo', 'Reintentá. Tu producto no se duplicará.');
    } finally {
      setSaving(false);
    }
  };

  const updateQuantity = async (item: InventoryShoppingItem, nextQuantity: number) => {
    if (!accessToken || nextQuantity <= 0) return;
    setBusyItemId(item.id);
    setShopping((current) => current ? {
      ...current,
      items: current.items.map((entry) => entry.id === item.id
        ? { ...entry, requested_quantity: nextQuantity, version: entry.version + 1 }
        : entry),
    } : current);
    try {
      const result = await updateInventoryShoppingItem(accessToken, item.id, { requested_quantity: nextQuantity }, {
        ...newIdentity('quantity'),
        expectedVersion: item.version,
      });
      setShopping((current) => current ? {
        ...current,
        items: current.items.map((entry) => entry.id === item.id ? result.item : entry),
      } : current);
    } catch {
      setShopping((current) => current ? {
        ...current,
        items: current.items.map((entry) => entry.id === item.id ? item : entry),
      } : current);
      Alert.alert('La lista cambió', 'Actualizamos la lista para conservar el cambio más reciente.');
      await load(false);
    } finally {
      setBusyItemId(null);
    }
  };

  const removeItem = (item: InventoryShoppingItem) => {
    if (!accessToken) return;
    Alert.alert('Quitar de la lista', `¿Quitar ${item.name_snapshot}?`, [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'Quitar',
        style: 'destructive',
        onPress: () => void (async () => {
          setBusyItemId(item.id);
          try {
            await removeInventoryShoppingItem(accessToken, item.id, {
              ...newIdentity('remove'),
              expectedVersion: item.version,
            });
            await load(false);
          } catch {
            Alert.alert('No pudimos quitarlo', 'Actualizá la lista e intentá nuevamente.');
          } finally {
            setBusyItemId(null);
          }
        })(),
      },
    ]);
  };

  const clearList = () => {
    if (!accessToken || !shopping?.items.length) return;
    Alert.alert('Vaciar lista', 'Se quitarán los productos de esta lista. El stock no cambia.', [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'Vaciar',
        style: 'destructive',
        onPress: () => void (async () => {
          try {
            await clearInventoryShoppingList(accessToken, newIdentity('clear'));
            await load(false);
          } catch {
            Alert.alert('No pudimos vaciarla', 'Intentá nuevamente.');
          }
        })(),
      },
    ]);
  };

  const openPurchase = async () => {
    if (!accessToken || !shopping) return;
    if (shopping.active_purchase) {
      navigation.navigate('InventoryPurchase', { purchaseId: shopping.active_purchase.id });
      return;
    }
    setStartingPurchase(true);
    try {
      const identity = startPurchaseIdentityRef.current ?? newIdentity('purchase-start');
      startPurchaseIdentityRef.current = identity;
      const result = await startInventoryPurchase(accessToken, identity);
      navigation.navigate('InventoryPurchase', { purchaseId: result.session.id });
      startPurchaseIdentityRef.current = null;
    } catch {
      // Keep the idempotency identity for the explicit retry: a failed response
      // can still correspond to a purchase already created by the server.
      Alert.alert('No pudimos iniciar la compra', 'Reintentá. La compra no se duplicará.');
    } finally {
      setStartingPurchase(false);
    }
  };

  const openPlannerTask = (taskId: string) => {
    navigation.getParent()?.navigate('PlannerTab', {
      screen: 'TaskDetail',
      params: { entityId: taskId, source: 'unknown', returnTo: 'previous' },
    });
  };

  const createPlannerTask = async () => {
    if (!accessToken || !shopping?.items.length || !integrations?.planner.can_create_household_task) return;
    setCreatingPlannerTask(true);
    try {
      const identity = plannerTaskIdentityRef.current ?? newIdentity('planner-task');
      plannerTaskIdentityRef.current = identity;
      const result = await createInventoryShoppingPlannerTask(accessToken, identity);
      plannerTaskIdentityRef.current = null;
      setPlannerTaskNotice({ id: result.task.id, existing: result.outcome === 'existing' });
    } catch {
      // Keep the identity for an explicit retry: an interrupted response may
      // already have created the canonical Planner task on the server.
      Alert.alert('No pudimos crear la tarea', 'Reintentá. La tarea no se duplicará.');
    } finally {
      setCreatingPlannerTask(false);
    }
  };

  return (
    <>
      <AppScreen
        scroll
        bottomInset="tab"
        scrollProps={{
          refreshControl: (
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => { setRefreshing(true); void load(false); }}
              tintColor={colors.terracotta[500]}
            />
          ),
        }}
      >
        <AppPageHeader
          title="Lista de compras"
          subtitle={shopping?.list.assignee?.display_name ? `Encargado: ${shopping.list.assignee.display_name}` : 'Compartida con tu hogar'}
          leading={
            <IconButton
              icon="chevron-back-outline"
              variant="plain"
              onPress={() => navigation.goBack()}
              accessibilityLabel="Volver a Inventario"
            />
          }
          action={<IconButton icon="add" onPress={() => setAddOpen(true)} accessibilityLabel="Agregar a la lista" variant="brandSoft" />}
          style={styles.header}
        />

        {loading ? (
          <View style={styles.loading}><ActivityIndicator color={colors.terracotta[500]} /><AppText tone="secondary">Cargando lista…</AppText></View>
        ) : error ? (
          <ErrorState description={error} onRetry={() => void load()} />
        ) : shopping?.items.length ? (
          <View style={styles.content}>
            <AppCard variant="quiet" padding="default" style={styles.summary}>
              <View style={styles.summaryIcon}><HomePlusIcon name="cart-outline" size={22} color={colors.terracotta[600]} /></View>
              <View style={styles.summaryCopy}>
                <AppText weight="700">{shopping.items.length} {shopping.items.length === 1 ? 'producto pendiente' : 'productos pendientes'}</AppText>
                <AppText variant="caption" tone="secondary">Prepará la compra sin perder el contexto del hogar.</AppText>
              </View>
            </AppCard>

            <View style={styles.actionRow}>
              <AppButton title="Agregar producto" variant="secondary" size="sm" onPress={() => setAddOpen(true)} style={styles.grow} />
              {integrations?.planner.can_create_household_task ? (
                <AppButton
                  title="Crear tarea"
                  variant="secondary"
                  size="sm"
                  loading={creatingPlannerTask}
                  onPress={() => void createPlannerTask()}
                  style={styles.grow}
                  testID="inventory.shopping.createPlannerTask"
                />
              ) : null}
            </View>
            <AppButton title="Vaciar lista" variant="ghost" size="sm" onPress={clearList} style={styles.clearButton} />
            <AppButton
              title={shopping.active_purchase ? 'Continuar compra' : 'Empezar compra'}
              loading={startingPurchase}
              onPress={() => void openPurchase()}
              accessibilityLabel={shopping.active_purchase ? 'Continuar compra activa' : 'Empezar compra y actualizar el stock al finalizar'}
            />

            <View style={styles.list}>
              {shopping.items.map((item) => {
                const busy = busyItemId === item.id;
                return (
                  <AppCard key={item.id} variant="default" padding="default" style={styles.itemCard}>
                    <View style={styles.itemTop}>
                      <View style={styles.itemCopy}>
                        <AppText weight="700">{item.name_snapshot}</AppText>
                        <AppText variant="caption" tone="tertiary">
                          {item.auto_managed ? 'Reposición sugerida' : item.inventory_item?.location_name ?? 'Producto de la lista'}
                        </AppText>
                      </View>
                      <IconButton icon="close" variant="plain" disabled={busy} onPress={() => removeItem(item)} accessibilityLabel={`Quitar ${item.name_snapshot}`} />
                    </View>
                    <View style={styles.quantityRow}>
                      <AppText variant="caption" tone="secondary">Cantidad</AppText>
                      <View style={styles.stepper}>
                        <IconButton icon="remove" variant="plain" disabled={busy || item.requested_quantity <= 1} onPress={() => void updateQuantity(item, item.requested_quantity - 1)} accessibilityLabel={`Restar ${item.name_snapshot}`} />
                        <AppText weight="700" style={styles.quantity}>{item.requested_quantity}</AppText>
                        <IconButton icon="add" variant="plain" disabled={busy} onPress={() => void updateQuantity(item, item.requested_quantity + 1)} accessibilityLabel={`Sumar ${item.name_snapshot}`} />
                      </View>
                    </View>
                  </AppCard>
                );
              })}
            </View>
          </View>
        ) : (
          <EmptyState
            title="Tu lista está vacía"
            description="Agregá lo que necesitás comprar y mantenelo visible para todo el hogar."
            actionLabel="Agregar producto"
            onAction={() => setAddOpen(true)}
          />
        )}
      </AppScreen>

      <ActionSheet
        visible={addOpen}
        title="Agregar a la lista"
        subtitle="Podés ajustar la cantidad después."
        onRequestClose={closeAdd}
        closeDisabled={saving}
        size="content"
        keyboardAware
        footer={(
          <View style={styles.modalActions}>
            <AppButton title="Cancelar" variant="ghost" disabled={saving} onPress={closeAdd} style={styles.grow} />
            <AppButton title="Agregar" loading={saving} disabled={!name.trim() || !validQuantity(quantity)} onPress={() => void createItem()} style={styles.grow} />
          </View>
        )}
      >
        <View style={styles.addSheetContent}>
          <AppInput label="Producto" value={name} onChangeText={setName} placeholder="Ej. Leche" autoFocus />
          <AppInput label="Cantidad" value={quantity} onChangeText={setQuantity} keyboardType="decimal-pad" errorText={quantity && !validQuantity(quantity) ? 'Ingresá una cantidad mayor a 0.' : undefined} />
        </View>
      </ActionSheet>
      <UndoToast visible={Boolean(feedback)} message={feedback ?? ''} onDismiss={() => setFeedback(null)} />
      <ActionSheet
        visible={Boolean(plannerTaskNotice)}
        title={plannerTaskNotice?.existing ? 'La tarea ya existe' : 'Tarea lista'}
        subtitle={plannerTaskNotice?.existing
          ? "Esta lista ya tiene una tarea pendiente en Organizador."
          : "La lista quedó vinculada a una tarea de Organizador."}
        onRequestClose={() => setPlannerTaskNotice(null)}
        size="content"
        footer={(
          <View style={styles.taskNoticeActions}>
            <AppButton title="Seguir en la lista" variant="secondary" onPress={() => setPlannerTaskNotice(null)} style={styles.grow} />
            <AppButton title="Ver tarea" onPress={() => {
              const taskId = plannerTaskNotice?.id;
              setPlannerTaskNotice(null);
              if (taskId) openPlannerTask(taskId);
            }} style={styles.grow} />
          </View>
        )}
      >
        <AppText variant="bodySmall" tone="secondary">
          La tarea queda propuesta para hoy. Podés cambiar su fecha o responsable desde Organizador.
        </AppText>
      </ActionSheet>
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
  actionRow: { flexDirection: 'row', alignItems: 'center', gap: spacing[2] },
  grow: { flex: 1 },
  clearButton: { alignSelf: 'flex-start' },
  list: { gap: spacing[2] },
  itemCard: { gap: spacing[3] },
  itemTop: { flexDirection: 'row', alignItems: 'center', gap: spacing[2] },
  itemCopy: { flex: 1, gap: spacing[1] },
  quantityRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: spacing[1], backgroundColor: colors.surface.soft, borderRadius: radius.pill, paddingHorizontal: spacing[1] },
  quantity: { minWidth: 28, textAlign: 'center' },
  addSheetContent: { gap: spacing[4] },
  modalKeyboard: { flex: 1, backgroundColor: 'rgba(26,23,20,0.3)' },
  modalScrollContent: { flexGrow: 1, justifyContent: 'flex-end' },
  modalCard: { backgroundColor: colors.surface.card, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing[5], gap: spacing[4] },
  modalHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing[3] },
  modalTitle: { flex: 1, gap: spacing[1] },
  modalActions: { flexDirection: 'row', gap: spacing[3] },
  taskNoticeActions: { flexDirection: 'row', gap: spacing[3] },
});
}
