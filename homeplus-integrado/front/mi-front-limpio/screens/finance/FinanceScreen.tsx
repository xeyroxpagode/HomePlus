import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute, type RouteProp } from '@react-navigation/native';

import {
  EditPaymentDueSheet,
  DirectCreditCardPaymentSheet,
  FinanceUpcomingPaymentsSummary,
  MovementDetailSheet,
  NewMovementSheet,
  NewPaymentSheet,
  PaymentDetailSheet,
  PaymentsList,
  PayCreditCardSheet,
  RegisterPaymentSheet,
  TransactionCorrectionSheet,
  TransferDetailSheet,
} from '../../components/finance';
import {
  AppCard,
  AppScreen,
  AppPageHeader,
  AppText,
  ActionSheet,
  EmptyState,
  ErrorState,
  FilterChip,
  InteractivePressable,
  SearchField,
  SegmentedControl,
  Skeleton,
  UnderlineTabs,
  type SegmentOption,
  UndoToast,
} from '../../components/ui';
import {
  FinancePeriodNavigator,
  FinanceIconAction,
  FinanceIconBox,
  FinanceListRow,
  FinanceSection,
  FinanceEmptyState,
  FinanceErrorState,
  FinanceOverviewCards,
  FinanceGroupedSurface,
  financeSpacing,
} from '../../components/finance/ui';
import { HomePlusIcon } from '../../constants/icons';
import { useAuth } from '../../context/AuthContext';
import { useAppTheme } from '../../context/AppThemeContext';
import { useHousehold } from '../../context/HouseholdContext';
import { parseFinanceEntryParams } from '../../navigation/financeNavigation';
import type { MoreStackParamList } from '../../navigation/types';
import { AbortError, ApiError } from '../../services/api';
import { formatFinanceAmount, financeMovementTitle, financeTransferTitle, isZeroDecimalString } from '../../services/finance/financeDisplay';
import {
  FINANCE_CONTEXT_TYPES,
  FINANCE_TAB_LABELS,
  FINANCE_TABS,
  financeContextLabel,
  financeContextViewState,
  selectFinanceContext,
  selectFinanceTab,
  type FinanceContextType,
  type FinanceTabKey,
} from '../../services/finance/financeContext';
import {
  getFinanceSummary,
  getFinanceTransactionDetail,
  listFinanceMovements,
  type FinanceExpenseMovementDto,
  type FinanceTransactionDetailDto,
  type FinanceUnifiedMovementDto,
  type FinanceSummaryCurrencyDto,
  type GetFinanceSummaryResponse,
  type ListFinanceMovementsResponse,
} from '../../services/finance/financeMovements';
import type { TransactionCorrectionDetailPrefetch } from '../../services/finance/transactionCorrectionDetailLoad';
import {
  financeMonthFromLocalDate,
  formatFinanceDateGroupLabel,
  formatFinancePeriodLabel,
  isCurrentFinanceMonth,
  shiftFinanceMonth,
} from '../../services/finance/financePeriod';
import type { PaymentDueDto } from '../../services/finance/financePayments';
import type { FinanceAccountDto } from '../../services/finance/financeAccounts';
import type { FinanceOperationKind } from '../../components/finance/NewMovementSheet';
import {
  getFinanceAnalysis,
  type FinanceAnalysisResponse,
} from '../../services/finance/financeAnalysis';
import {
  getFinanceCategoryPresentationByLabel,
  type FinanceCategoryPresentation,
} from '../../services/finance/financeCategories';

type TransactionMovementDto = Extract<FinanceUnifiedMovementDto, { kind: 'EXPENSE' | 'INCOME' }>;
type FinanceReadState = {
  key: string | null;
  loading: boolean;
  error: string | null;
  movements: ListFinanceMovementsResponse | null;
  summary: GetFinanceSummaryResponse | null;
};

const EMPTY_READ_STATE: FinanceReadState = {
  key: null,
  loading: false,
  error: null,
  movements: null,
  summary: null,
};
const EMPTY_SUMMARY_CURRENCIES: FinanceSummaryCurrencyDto[] = [];

// Stage 7B.1 — Finance root authority: single segmented families for tabs + scope.
const FINANCE_TAB_OPTIONS: SegmentOption<FinanceTabKey>[] = FINANCE_TABS.map((tab) => ({
  value: tab,
  label: FINANCE_TAB_LABELS[tab],
}));

function groupMovementsByTransactionDate(movements: FinanceUnifiedMovementDto[]) {
  const groups: { date: string; movements: FinanceUnifiedMovementDto[] }[] = [];
  const indexByDate = new Map<string, number>();

  movements.forEach((movement) => {
    const existingIndex = indexByDate.get(movement.date);
    if (existingIndex === undefined) {
      indexByDate.set(movement.date, groups.length);
      groups.push({ date: movement.date, movements: [movement] });
      return;
    }
    groups[existingIndex].movements.push(movement);
  });

  return groups;
}

type MovementTypeFilterKey = 'expense' | 'income' | 'transfer';
type MovementFilterKey = MovementTypeFilterKey;

const MOVEMENT_FILTER_OPTIONS: SegmentOption<MovementTypeFilterKey>[] = [
  { value: 'expense', label: 'Gastos' },
  { value: 'income', label: 'Ingresos' },
  { value: 'transfer', label: 'Transferencias' },
];

const ALL_MOVEMENT_TYPE_FILTERS: MovementTypeFilterKey[] = ['expense', 'income', 'transfer'];

function normalizeMovementFilters(filters: MovementTypeFilterKey[]): MovementTypeFilterKey[] {
  const unique = ALL_MOVEMENT_TYPE_FILTERS.filter((type) => filters.includes(type));
  return unique.length === 0 ? ALL_MOVEMENT_TYPE_FILTERS : unique;
}

function toggleMovementFilter(
  currentFilters: MovementTypeFilterKey[],
  nextFilter: MovementFilterKey,
): MovementTypeFilterKey[] {
  const current = normalizeMovementFilters(currentFilters);
  if (current.includes(nextFilter) && current.length === 1) return current;
  const next = current.includes(nextFilter)
    ? current.filter((type) => type !== nextFilter)
    : [...current, nextFilter];
  return normalizeMovementFilters(next);
}

function movementMatchesFilter(movement: FinanceUnifiedMovementDto, filters: MovementTypeFilterKey[]): boolean {
  const normalized = normalizeMovementFilters(filters);
  // Root-unit semantics (backend is primary authority): a dependent Transfer
  // commission never matches root Gastos/Ingresos filters on its own. It is
  // disclosed through its root Transfer only.
  if (movement.kind === 'EXPENSE' || movement.kind === 'INCOME') {
    if (movement.transferId) return false;
    if (normalized.length === ALL_MOVEMENT_TYPE_FILTERS.length) return true;
    if (movement.kind === 'EXPENSE') return normalized.includes('expense');
    return normalized.includes('income');
  }
  if (normalized.length === ALL_MOVEMENT_TYPE_FILTERS.length) return true;
  return normalized.includes('transfer');
}

function movementMatchesSearch(movement: FinanceUnifiedMovementDto, query: string): boolean {
  const normalizedQuery = query.trim().toLocaleLowerCase('es-AR');
  if (!normalizedQuery) return true;

  const values = movement.kind === 'TRANSFER'
    ? [
        movement.description,
        movement.sourceAccount.name,
        movement.destinationAccount.name,
        financeTransferTitle(movement),
      ]
    : [
        movement.description,
        movement.categoryLabel,
        movement.accountName,
        financeMovementTitle(movement.kind === 'EXPENSE' ? 'expense' : 'income', movement.description),
      ];

  return values.some((value) => value?.toLocaleLowerCase('es-AR').includes(normalizedQuery));
}

function financeCategoryToneColor(colors: ReturnType<typeof useAppTheme>['colors'], presentation: FinanceCategoryPresentation) {
  if (presentation.tone === 'terracotta') return colors.terracotta[600];
  if (presentation.tone === 'sage') return colors.sage[600];
  if (presentation.tone === 'sand') return colors.sand[600];
  if (presentation.tone === 'info') return colors.info.text;
  return colors.text.tertiary;
}

function safeFinanceReadError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'No pudimos cargar Finanzas. Intenta de nuevo.';
}

export function FinanceScreen() {
  const theme = useAppTheme();
  const { colors } = theme;
  const styles = createStyles(theme);
  const navigation = useNavigation<any>();
  const route = useRoute<RouteProp<MoreStackParamList, 'Finance'>>();
  const entryParams = useMemo(() => parseFinanceEntryParams(route.params), [route.params]);
  const { session, authMe } = useAuth();
  const { currentHousehold, loading, reloading, householdError } = useHousehold();
  const [selectedContext, setSelectedContext] = useState<FinanceContextType>(entryParams.contextType ?? FINANCE_CONTEXT_TYPES.PERSONAL);
  const [selectedTab, setSelectedTab] = useState<FinanceTabKey>(entryParams.initialTab ?? 'resumen');
  const [newMovementVisible, setNewMovementVisible] = useState(false);
  const [newMovementOperation, setNewMovementOperation] = useState<FinanceOperationKind>('expense');
  const [organizeVisible, setOrganizeVisible] = useState(false);
  const [successFeedback, setSuccessFeedback] = useState<string | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState(() => financeMonthFromLocalDate());
  const [selectedMovement, setSelectedMovement] = useState<TransactionMovementDto | null>(null);
  const [movementDetailVisible, setMovementDetailVisible] = useState(false);
  const [movementFilters, setMovementFilters] = useState<MovementTypeFilterKey[]>(ALL_MOVEMENT_TYPE_FILTERS);
  const [movementSearchQuery, setMovementSearchQuery] = useState('');
  const [selectedTransferId, setSelectedTransferId] = useState<string | null>(null);
  const [transferDetailVisible, setTransferDetailVisible] = useState(false);
  const [transferDetailRefreshNonce, setTransferDetailRefreshNonce] = useState(0);
  const [correctionTransactionId, setCorrectionTransactionId] = useState<string | null>(null);
  const [correctionVisible, setCorrectionVisible] = useState(false);
  const [selectedSummaryCurrency, setSelectedSummaryCurrency] = useState<string | null>(null);
  const [readRefreshNonce, setReadRefreshNonce] = useState(0);
  const [readState, setReadState] = useState<FinanceReadState>(EMPTY_READ_STATE);

  const [analysis, setAnalysis] = useState<FinanceAnalysisResponse | null>(null);

  // Payment sheets state
  const [newPaymentVisible, setNewPaymentVisible] = useState(false);
  const [registerPaymentVisible, setRegisterPaymentVisible] = useState(false);
  const [payCreditCardVisible, setPayCreditCardVisible] = useState(false);
  const [paymentDetailVisible, setPaymentDetailVisible] = useState(false);
  const [editPaymentDueVisible, setEditPaymentDueVisible] = useState(false);
  const [selectedPayment, setSelectedPayment] = useState<PaymentDueDto | null>(null);
  const [selectedPaymentId, setSelectedPaymentId] = useState<string | null>(entryParams.paymentDueId ?? null);
  const [selectedDirectCard, setSelectedDirectCard] = useState<FinanceAccountDto | null>(null);
  const [directCardPaymentVisible, setDirectCardPaymentVisible] = useState(false);
  const [paymentDetailRefreshNonce, setPaymentDetailRefreshNonce] = useState(0);
  const [paymentsRefreshNonce, setPaymentsRefreshNonce] = useState(0);
  const [summaryPayments, setSummaryPayments] = useState<PaymentDueDto[]>([]);

  const allowVisibleBackExit = useRef(false);
  const readKeyRef = useRef<string | null>(null);
  const paymentEntryKeyRef = useRef<string | null>(null);
  const detailPrefetchRef = useRef<TransactionCorrectionDetailPrefetch | null>(null);
  const [detailPrefetchSnapshot, setDetailPrefetchSnapshot] = useState<TransactionCorrectionDetailPrefetch | null>(null);

  const openPapelera = () => {
    navigation.navigate('FinancePapelera', {
      contextType: selectedContext,
    });
  };

  const contextLoading = loading || reloading;
  const activeHousehold = useMemo(() => {
    if (!currentHousehold) return null;
    return {
      id: currentHousehold.id,
      name: currentHousehold.nombre,
    };
  }, [currentHousehold]);
  const contextLabel = financeContextLabel(selectedContext, activeHousehold, contextLoading);
  const viewState = financeContextViewState(selectedContext, activeHousehold, contextLoading);
  const readReady = Boolean(session?.access_token) && (
    viewState === 'personal_ready' || viewState === 'household_ready'
  );
  const readScopeKey = `${selectedContext}:${selectedContext === FINANCE_CONTEXT_TYPES.HOUSEHOLD ? activeHousehold?.id ?? 'none' : 'personal'}:${selectedPeriod}`;
  const visibleReadState = readState.key === readScopeKey ? readState : EMPTY_READ_STATE;
  const summaryCurrencies = visibleReadState.summary?.currencies ?? EMPTY_SUMMARY_CURRENCIES;
  const selectedSummaryBucket = summaryCurrencies.find((bucket) => bucket.currency === selectedSummaryCurrency) ?? null;

  // A payment movement restored from Papelera re-settles its obligation
  // (PENDING -> PAID), but PaymentsList stays mounted while Papelera is open.
  // Refetch Pagos whenever this screen regains focus (skips the first focus:
  // the list already loads on mount).
  const paymentsFocusPrimedRef = useRef(false);
  useFocusEffect(
    useCallback(() => {
      if (!paymentsFocusPrimedRef.current) {
        paymentsFocusPrimedRef.current = true;
        return;
      }
      setPaymentsRefreshNonce((current) => current + 1);
    }, []),
  );

  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    const entryContextType = entryParams.contextType;
    const entryInitialTab = entryParams.initialTab;
    const entryPaymentDueId = entryParams.paymentDueId;

    if (entryContextType) {
      setSelectedContext((current) => selectFinanceContext(current, entryContextType));
    }
    if (entryInitialTab) {
      setSelectedTab((current) => selectFinanceTab(current, entryInitialTab));
    }
    if (!entryPaymentDueId) return;

    const key = `${entryContextType ?? 'default'}:${entryPaymentDueId}`;
    if (paymentEntryKeyRef.current === key) return;
    paymentEntryKeyRef.current = key;
    setSelectedTab('pagos');
    setSelectedPayment(null);
    setSelectedPaymentId(entryPaymentDueId);
    setPaymentDetailVisible(true);
  }, [entryParams]);

  useEffect(() => {
    if (!readReady || !session?.access_token) {
      readKeyRef.current = null;
      setReadState(EMPTY_READ_STATE);
      return;
    }

    const requestKey = readScopeKey;
    const controller = new AbortController();
    const scopeChanged = readKeyRef.current !== requestKey;
    readKeyRef.current = requestKey;
    setReadState((current) => ({
      key: requestKey,
      loading: true,
      error: null,
      movements: current.key === requestKey ? current.movements : null,
      summary: current.key === requestKey ? current.summary : null,
    }));

    // Keep same-scope data visible during refresh, but never carry financial
    // data across personal/household/period boundaries.
    setAnalysis((current) => scopeChanged ? null : current);

    const readOptions = {
      accessToken: session.access_token,
      contextType: selectedContext,
      period: selectedPeriod,
      signal: controller.signal,
      contextScope: `finance:${requestKey}`,
    };

    const currency = selectedSummaryCurrency ?? summaryCurrencies[0]?.currency ?? 'ARS';

    const isCancelled = (error: unknown) => (
      error instanceof AbortError || (error instanceof Error && error.name === 'AbortError')
    );

    Promise.all([
      listFinanceMovements(readOptions),
      getFinanceSummary(readOptions),
    ])
      .then(([movements, summary]) => {
        if (readKeyRef.current !== requestKey) return;
        setReadState({
          key: requestKey,
          loading: false,
          error: null,
          movements,
          summary,
        });
      })
      .catch((error) => {
        if (isCancelled(error)) return;
        if (readKeyRef.current !== requestKey) return;
        setReadState((current) => ({
          key: requestKey,
          loading: false,
          error: safeFinanceReadError(error),
          movements: current.key === requestKey ? current.movements : null,
          summary: current.key === requestKey ? current.summary : null,
        }));
      });

    getFinanceAnalysis({ ...readOptions, currency, periodType: 'MONTHLY', period: selectedPeriod })
      .then((analysisData) => {
        if (readKeyRef.current !== requestKey) return;
        setAnalysis(analysisData);
      })
      .catch((error) => {
        if (isCancelled(error) || readKeyRef.current !== requestKey) return;
        // Analysis is optional supporting content. The canonical summary stays
        // usable if this auxiliary read fails.
        setAnalysis(null);
      });

    return () => {
      controller.abort();
    };
  }, [readReady, readScopeKey, readRefreshNonce, selectedContext, selectedPeriod, selectedSummaryCurrency, session?.access_token]);

  useEffect(() => {
    const currencies = summaryCurrencies.map((bucket) => bucket.currency);
    setSelectedSummaryCurrency((current) => {
      if (currencies.length === 0) return null;
      if (current && currencies.includes(current)) return current;
      return currencies[0];
    });
  }, [summaryCurrencies]);
  /* eslint-enable react-hooks/exhaustive-deps */

  const handleVisibleBack = () => {
    allowVisibleBackExit.current = true;
    navigation.goBack();
  };

  const chooseContext = (nextContext: FinanceContextType) => {
    setSelectedContext((current) => {
      if (current === nextContext) return current;
      return selectFinanceContext(current, nextContext);
    });
  };

  const openNewMovement = (operation: FinanceOperationKind = 'expense') => {
    setNewMovementOperation(operation);
    setNewMovementVisible(true);
  };

  const openOrganizerDestination = (destination: () => void) => {
    setOrganizeVisible(false);
    destination();
  };

  const movePeriod = (direction: 'previous' | 'next') => {
    setSelectedPeriod((current) => shiftFinanceMonth(current, direction));
  };

  const retryReads = () => {
    setReadRefreshNonce((current) => current + 1);
  };

  const clearDetailPrefetch = () => {
    detailPrefetchRef.current = null;
    setDetailPrefetchSnapshot(null);
  };

  const prefetchMovementDetail = (movement: FinanceUnifiedMovementDto) => {
    if (!session?.access_token) return;
    if (movement.kind === 'TRANSFER') return;

    const existing = detailPrefetchRef.current;
    if (
      existing?.transactionId === movement.id &&
      existing.contextType === selectedContext &&
      (existing.detail || existing.promise)
    ) {
      setDetailPrefetchSnapshot(existing);
      return;
    }

    const prefetch: TransactionCorrectionDetailPrefetch = {
      transactionId: movement.id,
      contextType: selectedContext,
      detail: null,
      promise: null,
      failed: false,
    };

    prefetch.promise = getFinanceTransactionDetail({
      accessToken: session.access_token,
      contextType: selectedContext,
      transactionId: movement.id,
      contextScope: `finance-transaction-detail-prefetch:${selectedContext}:${movement.id}`,
    })
      .then((detail: FinanceTransactionDetailDto) => {
        if (detailPrefetchRef.current === prefetch) {
          prefetch.detail = detail;
          prefetch.promise = null;
          setDetailPrefetchSnapshot({ ...prefetch });
        }
        return detail;
      })
      .catch((error) => {
        if (detailPrefetchRef.current === prefetch) {
          prefetch.failed = true;
          prefetch.promise = null;
          setDetailPrefetchSnapshot({ ...prefetch });
        }
        throw error;
      });
    void prefetch.promise.catch(() => undefined);

    detailPrefetchRef.current = prefetch;
    setDetailPrefetchSnapshot(prefetch);
  };

  const handleCreateSuccess = (operation: 'expense' | 'income' | 'transfer') => {
    setSuccessFeedback(
      operation === 'expense'
        ? 'Gasto registrado'
        : operation === 'income'
        ? 'Ingreso registrado'
        : 'Transferencia registrada',
    );
    setReadRefreshNonce((current) => current + 1);
    if (operation === 'transfer') {
      setTransferDetailRefreshNonce((current) => current + 1);
    }
  };

  const handleMovementPress = (movement: FinanceUnifiedMovementDto) => {
    if (movement.kind === 'TRANSFER') {
      handleTransferPress(movement);
      return;
    }
    setSelectedMovement(movement);
    setMovementDetailVisible(true);
    prefetchMovementDetail(movement);
  };

  const handleMovementDetailClose = () => {
    setMovementDetailVisible(false);
    setSelectedMovement(null);
    if (!correctionVisible) clearDetailPrefetch();
  };

  const handleTransferPress = (movement: FinanceUnifiedMovementDto) => {
    if (movement.kind !== 'TRANSFER') return;
    setSelectedTransferId(movement.id);
    setTransferDetailRefreshNonce((current) => current + 1);
    setTransferDetailVisible(true);
  };

  const handleTransferDetailClose = () => {
    setTransferDetailVisible(false);
    setSelectedTransferId(null);
  };

  const handleTransferTrashSuccess = () => {
    setSuccessFeedback('Transferencia enviada a Papelera.');
    setReadRefreshNonce((current) => current + 1);
    handleTransferDetailClose();
  };

  const handleCorrectionIntent = (transactionId: string) => {
    setCorrectionTransactionId(transactionId);
    setCorrectionVisible(true);
  };

  const handleCorrectionClose = () => {
    setCorrectionVisible(false);
    setCorrectionTransactionId(null);
    clearDetailPrefetch();
  };

  const handleTrashSuccess = () => {
    setSuccessFeedback('Movimiento enviado a Papelera.');
    setReadRefreshNonce((current) => current + 1);
    // A trashed movement can reopen its payment obligation (PAID -> PENDING),
    // so Pagos must refetch: the list stays mounted while other tabs are open.
    setPaymentsRefreshNonce((current) => current + 1);
    handleMovementDetailClose();
  };

  const handleCorrectionSuccess = () => {
    setSuccessFeedback('Movimiento corregido.');
    setReadRefreshNonce((current) => current + 1);
    setTransferDetailRefreshNonce((current) => current + 1);
    clearDetailPrefetch();
    handleCorrectionClose();
    handleMovementDetailClose();
  };

  const handleRefundSuccess = () => {
    setSuccessFeedback('Devolución guardada.');
    setReadRefreshNonce((current) => current + 1);
  };

  const handlePoolAssignmentSuccess = () => {
    setSuccessFeedback('Pozo actualizado.');
    setReadRefreshNonce((current) => current + 1);
  };

  const handlePaymentCreateSuccess = () => {
    setSuccessFeedback('Pago creado');
    setReadRefreshNonce((current) => current + 1);
    setPaymentsRefreshNonce((current) => current + 1);
  };

  const handlePaymentRegisterSuccess = () => {
    setSuccessFeedback('Pago registrado');
    setReadRefreshNonce((current) => current + 1);
    setPaymentsRefreshNonce((current) => current + 1);
    setPaymentDetailRefreshNonce((current) => current + 1);
    setSelectedPayment(null);
    setSelectedDirectCard(null);
  };

  const handlePaymentRefresh = () => {
    setReadRefreshNonce((current) => current + 1);
    setPaymentsRefreshNonce((current) => current + 1);
  };

  const handlePaymentPress = (payment: PaymentDueDto) => {
    setSelectedPayment(payment);
    setSelectedPaymentId(payment.id);
    setPaymentDetailVisible(true);
  };

  const handlePaymentSummaryChange = useCallback((payments: PaymentDueDto[]) => {
    setSummaryPayments(payments);
  }, []);

  const handlePaymentDetailClose = () => {
    setPaymentDetailVisible(false);
    setSelectedPayment(null);
    setSelectedPaymentId(null);
  };

  const handleRegisterPayment = (payment: PaymentDueDto) => {
    setSelectedPayment(payment);
    setRegisterPaymentVisible(true);
  };

  const handleRegisterCreditCardPayment = (payment: PaymentDueDto) => {
    setSelectedPayment(payment);
    setPayCreditCardVisible(true);
  };

  const handleDirectCardPayment = (card: FinanceAccountDto) => {
    setSelectedDirectCard(card);
    setDirectCardPaymentVisible(true);
  };

  const handleEditPayment = (payment: PaymentDueDto) => {
    setSelectedPayment(payment);
    setEditPaymentDueVisible(true);
  };

  const buildPaymentExpenseMovement = (payment: PaymentDueDto): FinanceExpenseMovementDto | null => {
    const rootId = payment.expenseRootTransactionId;
    if (!rootId || !payment.actualAmount) return null;
    const transactionDate = payment.actualDate ?? payment.dueDate;
    return {
      kind: 'EXPENSE',
      id: rootId,
      rootTransactionId: rootId,
      transferId: null,
      transactionType: 'expense',
      amount: payment.actualAmount,
      grossAmount: payment.actualAmount,
      totalRefunded: '0',
      netAmount: payment.actualAmount,
      refundCount: 0,
      refundEvents: [],
      currency: payment.currency,
      financialContextType: payment.financialContextType,
      transactionDate,
      description: null,
      categoryId: payment.actualCategoryId ?? null,
      categoryLabelSnapshot: payment.actualCategory?.label ?? null,
      createdAt: payment.createdAt,
      updatedAt: payment.updatedAt,
      date: transactionDate,
      categoryLabel: payment.actualCategory?.label ?? null,
      accountId: payment.actualAccountId ?? null,
      accountName: payment.actualAccount?.name ?? null,
      accountCurrency: payment.actualAccount?.currency ?? null,
    };
  };

  const handlePaymentOpenMovement = (payment: PaymentDueDto) => {
    if (payment.kind === 'CREDIT_CARD') {
      if (!payment.transferId) return;
      setSelectedTransferId(payment.transferId);
      setTransferDetailRefreshNonce((current) => current + 1);
      setTransferDetailVisible(true);
      handlePaymentDetailClose();
      return;
    }
    const movement = buildPaymentExpenseMovement(payment);
    if (!movement) return;
    setSelectedMovement(movement);
    setMovementDetailVisible(true);
    handlePaymentDetailClose();
  };

  const movementsReady = selectedTab === 'movimientos' &&
    (viewState === 'personal_ready' || viewState === 'household_ready');
  const summaryReady = selectedTab === 'resumen' &&
    (viewState === 'personal_ready' || viewState === 'household_ready');
  const paymentsReady = viewState === 'personal_ready' || viewState === 'household_ready';

  return (
    <AppScreen
      scroll
      bottomInset="tab"
      background="base"
      safeAreaEdges={['top', 'right', 'bottom', 'left']}
      contentContainerStyle={styles.content}
    >
      <View style={styles.header}>
        <AppPageHeader
          title="Finanzas"
          singleLineTitle
          leading={navigation.canGoBack() ? (
            <FinanceIconAction onPress={handleVisibleBack} haptic="light" accessibilityRole="button" accessibilityLabel="Volver a Más">
              <HomePlusIcon name="chevron-back-outline" size={22} color={colors.terracotta[600]} />
            </FinanceIconAction>
          ) : undefined}
          action={(
            <FinanceIconAction onPress={() => setOrganizeVisible(true)} accessibilityRole="button" accessibilityLabel="Organizar finanzas">
              <HomePlusIcon name="ellipsis-horizontal" size={22} color={colors.text.secondary} />
            </FinanceIconAction>
          )}
        />

        <SegmentedControl
          selectionMode="single"
          value={selectedContext}
          onChange={chooseContext}
          options={[
            { value: FINANCE_CONTEXT_TYPES.PERSONAL, label: 'Personal', accessibilityLabel: 'Finanzas personales' },
            {
              value: FINANCE_CONTEXT_TYPES.HOUSEHOLD,
              label: 'Familia',
              accessibilityLabel: `Finanzas del hogar ${activeHousehold?.name ?? ''}`.trim(),
              disabled: contextLoading || !activeHousehold,
            },
          ]}
          size="compact"
          style={styles.contextSelector}
          accessibilityLabel="Contexto financiero"
          testID="finance-context-selector"
        />
      </View>

      {contextLoading ? (
        <View style={styles.loadingRow}>
          <Skeleton width={120} height={12} />
          <AppText variant="caption" tone="tertiary">
            Actualizando finanzas
          </AppText>
        </View>
      ) : null}

      <UnderlineTabs
        value={selectedTab}
        onChange={(next) => setSelectedTab((current) => selectFinanceTab(current, next))}
        options={FINANCE_TAB_OPTIONS}
        accessibilityLabel="Secciones de Finanzas"
        testID="finance-tab-navigation"
      />

      {householdError ? (
        <ErrorState title="No pudimos actualizar el hogar" description={householdError} />
      ) : null}

      {viewState === 'loading' ? (
        <AppCard variant="quiet" padding="generous">
          <View style={styles.loadingBlock}>
            <Skeleton width="70%" height={18} />
            <Skeleton width="92%" height={14} />
            <Skeleton width="54%" height={14} />
          </View>
        </AppCard>
      ) : null}

      {viewState === 'household_unavailable' ? (
        <AppCard variant="warning" padding="generous">
          <EmptyState
            title="Contexto de hogar no disponible"
            description="Personal sigue disponible. Finanzas no elige ni cambia el hogar global."
            illustration={<HomePlusIcon name="shield-checkmark-outline" size={30} color={colors.warning.strong} />}
          />
        </AppCard>
      ) : null}

      {summaryReady ? (
        <View style={styles.resumenStack}>
          <FinanceSummarySurface
            period={selectedPeriod}
            loading={visibleReadState.loading}
            error={visibleReadState.error}
            currencies={summaryCurrencies}
            selectedCurrency={selectedSummaryCurrency}
            selectedBucket={selectedSummaryBucket}
            onSelectCurrency={setSelectedSummaryCurrency}
            onRetry={retryReads}
            onMovePeriod={movePeriod}
            analysis={analysis}
            navigation={navigation}
            contextType={selectedContext}
            contextLabel={contextLabel}
            onCreateExpense={() => openNewMovement('expense')}
            onCreateIncome={() => openNewMovement('income')}
            onCreateTransfer={() => openNewMovement('transfer')}
          />
          <FinanceUpcomingPaymentsSummary
            payments={summaryPayments}
            onPaymentPress={handlePaymentPress}
            onViewAll={() => setSelectedTab('pagos')}
          />
        </View>
      ) : null}

      {movementsReady ? (
<FinanceMovementsSurface
          period={selectedPeriod}
          loading={visibleReadState.loading}
          error={visibleReadState.error}
          movements={visibleReadState.movements?.movements ?? []}
          filters={movementFilters}
          onFilterChange={(filter) => setMovementFilters((current) => toggleMovementFilter(current, filter))}
          onShowAll={() => setMovementFilters(ALL_MOVEMENT_TYPE_FILTERS)}
          searchQuery={movementSearchQuery}
          onSearchQueryChange={setMovementSearchQuery}
          onRetry={retryReads}
          onMovePeriod={movePeriod}
          onMovementPress={handleMovementPress}
          onCreateMovement={() => openNewMovement('expense')}
        />
      ) : null}

      {paymentsReady ? (
        <View
          style={selectedTab === 'pagos' ? undefined : styles.hiddenTabSurface}
          testID={selectedTab === 'pagos' ? 'finance-payments-surface' : undefined}
        >
          <PaymentsList
            accessToken={session?.access_token ?? null}
            contextType={selectedContext}
            contextLabel={contextLabel}
            activeHousehold={activeHousehold}
            onCreatePayment={() => setNewPaymentVisible(true)}
            onOpenTrash={openPapelera}
            onPaymentPress={handlePaymentPress}
            onCreditCardDuePress={handlePaymentPress}
            onDirectCardPayment={handleDirectCardPayment}
            onRefresh={handlePaymentRefresh}
            onSummaryChange={handlePaymentSummaryChange}
            refreshNonce={paymentsRefreshNonce}
          />
        </View>
      ) : null}

      <ActionSheet
        visible={organizeVisible}
        title="Organizar finanzas"
        subtitle="Herramientas para preparar tu información financiera."
        onRequestClose={() => setOrganizeVisible(false)}
        size="content"
      >
        <View style={styles.organizeActions}>
          <FinanceListRow
            title="Cuentas y tarjetas"
            subtitle="Dónde registrás los movimientos"
            chevron
            onPress={() => openOrganizerDestination(() => navigation.navigate('FinanceAccounts', { contextType: selectedContext }))}
          />
          <FinanceListRow
            title="Categorías"
            subtitle="Cómo se ordenan gastos e ingresos"
            chevron
            onPress={() => openOrganizerDestination(() => navigation.navigate('FinanceCategoryManagement', { contextType: selectedContext, currency: selectedSummaryCurrency ?? 'ARS' }))}
          />
          <FinanceListRow
            title="Límites"
            subtitle="Seguimiento de gastos por categoría"
            chevron
            onPress={() => openOrganizerDestination(() => navigation.navigate('FinanceSpendingLimitsManagement', { contextType: selectedContext, currency: selectedSummaryCurrency ?? 'ARS', period: selectedPeriod }))}
          />
          <FinanceListRow
            title="Pozos"
            subtitle="Dinero separado por objetivo"
            chevron
            onPress={() => openOrganizerDestination(() => navigation.navigate('FinancePoolManagement', { contextType: selectedContext, currency: selectedSummaryCurrency ?? 'ARS' }))}
          />
          <FinanceListRow
            title="Papelera"
            subtitle="Movimientos y pagos eliminados"
            chevron
            divider={false}
            onPress={() => openOrganizerDestination(openPapelera)}
          />
        </View>
      </ActionSheet>

      <NewMovementSheet
        visible={newMovementVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        contextState={viewState}
        activeHousehold={activeHousehold}
        personId={authMe?.person?.id ?? null}
        householdId={selectedContext === FINANCE_CONTEXT_TYPES.HOUSEHOLD ? activeHousehold?.id ?? null : null}
        initialOperation={newMovementOperation}
        onRequestClose={() => setNewMovementVisible(false)}
        onSuccess={handleCreateSuccess}
      />

<MovementDetailSheet
        visible={movementDetailVisible}
        movement={selectedMovement}
        contextType={selectedContext}
        contextLabel={contextLabel}
        accessToken={session?.access_token ?? null}
        personId={authMe?.person?.id ?? null}
        householdId={selectedContext === FINANCE_CONTEXT_TYPES.HOUSEHOLD ? activeHousehold?.id ?? null : null}
        activeHousehold={activeHousehold}
        onRequestClose={handleMovementDetailClose}
        onTrashSuccess={handleTrashSuccess}
        onCorrectionIntent={handleCorrectionIntent}
        onRefundSuccess={handleRefundSuccess}
        onPoolAssignmentSuccess={handlePoolAssignmentSuccess}
      />

      <TransferDetailSheet
        visible={transferDetailVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        transferId={selectedTransferId}
        refreshNonce={transferDetailRefreshNonce}
        personId={authMe?.person?.id ?? null}
        householdId={selectedContext === FINANCE_CONTEXT_TYPES.HOUSEHOLD ? activeHousehold?.id ?? null : null}
        onRequestClose={handleTransferDetailClose}
        onTrashSuccess={handleTransferTrashSuccess}
      />

      <TransactionCorrectionSheet
        key={correctionTransactionId ?? 'none'}
        visible={correctionVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        personId={authMe?.person?.id ?? null}
        householdId={selectedContext === FINANCE_CONTEXT_TYPES.HOUSEHOLD ? activeHousehold?.id ?? null : null}
        transactionId={correctionTransactionId ?? ''}
        prefetchedDetail={detailPrefetchSnapshot}
        onRequestClose={handleCorrectionClose}
        onSuccess={handleCorrectionSuccess}
      />

      <NewPaymentSheet
        visible={newPaymentVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        contextState={viewState}
        activeHousehold={activeHousehold}
        onRequestClose={() => setNewPaymentVisible(false)}
        onSuccess={handlePaymentCreateSuccess}
      />

      <RegisterPaymentSheet
        visible={registerPaymentVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        contextState={viewState}
        activeHousehold={activeHousehold}
        payment={selectedPayment}
        onRequestClose={() => setRegisterPaymentVisible(false)}
        onSuccess={handlePaymentRegisterSuccess}
      />

      <PayCreditCardSheet
        visible={payCreditCardVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        contextState={viewState}
        activeHousehold={activeHousehold}
        payment={selectedPayment}
        onRequestClose={() => setPayCreditCardVisible(false)}
        onSuccess={handlePaymentRegisterSuccess}
      />

      <DirectCreditCardPaymentSheet
        visible={directCardPaymentVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        contextState={viewState}
        activeHousehold={activeHousehold}
        card={selectedDirectCard}
        onRequestClose={() => { setDirectCardPaymentVisible(false); setSelectedDirectCard(null); }}
        onSuccess={handlePaymentRegisterSuccess}
      />

      <EditPaymentDueSheet
        visible={editPaymentDueVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        payment={selectedPayment}
        onRequestClose={() => setEditPaymentDueVisible(false)}
        onSuccess={handlePaymentRefresh}
      />

      <PaymentDetailSheet
        visible={paymentDetailVisible}
        accessToken={session?.access_token ?? null}
        contextType={selectedContext}
        contextLabel={contextLabel}
        paymentId={selectedPaymentId}
        refreshNonce={paymentDetailRefreshNonce}
        onRequestClose={handlePaymentDetailClose}
        onRegisterPayment={handleRegisterPayment}
        onRegisterCreditCardPayment={handleRegisterCreditCardPayment}
        onEditPayment={handleEditPayment}
        onOpenMovement={handlePaymentOpenMovement}
        onRefresh={handlePaymentRefresh}
      />

      <UndoToast
        visible={Boolean(successFeedback)}
        message={successFeedback ?? ''}
        duration={2000}
        onDismiss={() => setSuccessFeedback(null)}
      />
    </AppScreen>
  );
}

function FinancePeriodControl({
  period,
  onMovePeriod,
}: {
  period: string;
  onMovePeriod: (direction: 'previous' | 'next') => void;
}) {
  return (
    <FinancePeriodNavigator
      label={formatFinancePeriodLabel(period)}
      onPrevious={() => onMovePeriod('previous')}
      onNext={() => onMovePeriod('next')}
      previousAccessibilityLabel="Mes anterior"
      nextAccessibilityLabel="Mes siguiente"
    />
  );
}

function FinanceSurfaceLoading() {
  const styles = createStyles(useAppTheme());

  return (
    <AppCard variant="quiet" padding="generous">
      <View style={styles.loadingBlock}>
        <Skeleton width="42%" height={16} />
        <Skeleton width="76%" height={18} />
        <Skeleton width="58%" height={14} />
      </View>
    </AppCard>
  );
}

function FinanceSummarySurface({
  period,
  loading,
  error,
  currencies,
  selectedCurrency,
  selectedBucket,
  onSelectCurrency,
  onRetry,
  onMovePeriod,
  analysis,
  navigation,
  contextType,
  contextLabel,
  onCreateExpense,
  onCreateIncome,
  onCreateTransfer,
}: {
  period: string;
  loading: boolean;
  error: string | null;
  currencies: FinanceSummaryCurrencyDto[];
  selectedCurrency: string | null;
  selectedBucket: FinanceSummaryCurrencyDto | null;
  onSelectCurrency: (currency: string) => void;
  onRetry: () => void;
  onMovePeriod: (direction: 'previous' | 'next') => void;
  analysis: FinanceAnalysisResponse | null;
  navigation: any;
  contextType: import('../../services/finance/financeContext').FinanceContextType;
  contextLabel: string;
  onCreateExpense: () => void;
  onCreateIncome: () => void;
  onCreateTransfer: () => void;
}) {
  const theme = useAppTheme();
  const { colors } = theme;
  const styles = createStyles(theme);

  if (loading && currencies.length === 0) return <FinanceSurfaceLoading />;
  if (error && currencies.length === 0) {
    return (
      <ErrorState
        title="No pudimos cargar el resumen"
        description={error}
        onRetry={onRetry}
      />
    );
  }

  const summaryExpense = analysis?.totals?.netExpense ?? selectedBucket?.expense ?? '0';
  const summaryIncome = analysis?.totals?.income ?? selectedBucket?.income ?? '0';
  const summaryNet = analysis?.totals?.netResult ?? selectedBucket?.net ?? '0';
  const sectionTitle = isCurrentFinanceMonth(period) ? 'Este mes' : 'Mes seleccionado';
  const canOpenAnalysis = Boolean(selectedBucket && analysis);
  const openAnalysis = () => {
    if (!selectedBucket) return;
    navigation.navigate('FinanceAnalysisDetail', {
      contextType,
      currency: selectedBucket.currency,
      periodType: 'MONTHLY',
      period,
    });
  };

  const hasSummaryData = currencies.length > 0 && Boolean(selectedBucket);

  // Inicio uses the same canonical summary authority as the former Resumen
  // tab, but leads with the next meaningful family action.
  return (
    <View style={styles.summarySurface}>
      {hasSummaryData ? (
        <FinanceQuickActions
          onCreateExpense={onCreateExpense}
          onCreateIncome={onCreateIncome}
          onCreateTransfer={onCreateTransfer}
        />
      ) : null}
      {error && currencies.length > 0 ? (
        <FinanceErrorState level="refresh" message={error} onRetry={onRetry} />
      ) : null}
      {!hasSummaryData ? (
        <FinanceStartEmpty
          onCreateExpense={onCreateExpense}
          onCreateIncome={onCreateIncome}
          onCreateTransfer={onCreateTransfer}
        />
      ) : (
        <FinanceSection title={sectionTitle} divided={false}>
          <View style={styles.summaryStack}>
            <FinancePeriodControl period={period} onMovePeriod={onMovePeriod} />
            {currencies.length > 1 ? (
              <SegmentedControl
                size="compact"
                value={selectedCurrency ?? currencies[0]?.currency ?? 'ARS'}
                onChange={onSelectCurrency}
                options={currencies.map((bucket) => ({
                  value: bucket.currency,
                  label: bucket.currency,
                  accessibilityLabel: `Resumen ${bucket.currency}`,
                }))}
                testID="finance-summary-currency"
              />
            ) : null}
            <FinanceOverviewCards
              periodLabel={formatFinancePeriodLabel(period)}
              contextLabel={contextLabel}
              balance={formatFinanceAmount(summaryNet, selectedBucket!.currency, { sign: 'net' })}
              expenses={formatFinanceAmount(summaryExpense, selectedBucket!.currency)}
              income={formatFinanceAmount(summaryIncome, selectedBucket!.currency)}
            />
            {canOpenAnalysis ? (
              <InteractivePressable
                onPress={openAnalysis}
                accessibilityRole="button"
                accessibilityLabel="Ver análisis detallado"
                pressedOpacity={0.82}
                style={styles.analysisLink}
              >
                <AppText variant="bodySmall" tone="brand" weight="700">Ver análisis</AppText>
                <HomePlusIcon name="chevron-forward-outline" size={16} color={colors.terracotta[600]} />
              </InteractivePressable>
            ) : null}
          </View>
        </FinanceSection>
      )}
    </View>
  );
}

function FinanceStartEmpty({
  onCreateExpense,
  onCreateIncome,
  onCreateTransfer,
}: {
  onCreateExpense: () => void;
  onCreateIncome: () => void;
  onCreateTransfer: () => void;
}) {
  const theme = useAppTheme();
  const { colors, radius, spacing, shadows } = theme;

  return (
    <View style={{ alignItems: 'center', paddingTop: spacing[8], paddingHorizontal: spacing[3], gap: spacing[4] }}>
      <View style={{ width: 88, height: 88, borderRadius: radius.xl, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' }}>
        <HomePlusIcon name="cash-outline" size={36} color={colors.terracotta[600]} />
      </View>
      <View style={{ alignItems: 'center', gap: spacing[2] }}>
        <AppText variant="title2" weight="800" style={{ textAlign: 'center' }}>
          Empezá registrando tu primer gasto
        </AppText>
        <AppText variant="body" tone="secondary" style={{ textAlign: 'center' }}>
          Ordená los movimientos de tu hogar desde un lugar simple y compartido.
        </AppText>
      </View>
      <FinanceQuickActions
        variant="empty"
        onCreateExpense={onCreateExpense}
        onCreateIncome={onCreateIncome}
        onCreateTransfer={onCreateTransfer}
      />
    </View>
  );
}

function FinanceQuickActions({
  onCreateExpense,
  onCreateIncome,
  onCreateTransfer,
  variant = 'inline',
}: {
  onCreateExpense: () => void;
  onCreateIncome: () => void;
  onCreateTransfer: () => void;
  variant?: 'inline' | 'empty';
}) {
  const theme = useAppTheme();
  const { colors, motion, radius, spacing } = theme;
  const stacked = variant === 'empty';

  return (
    <View style={{ width: '100%', gap: spacing[3] }}>
      <InteractivePressable
        onPress={onCreateExpense}
        haptic="light"
        pressScale={motion.scale.button}
        pressedOpacity={0.92}
        accessibilityRole="button"
        accessibilityLabel="Registrar gasto"
        style={{ minHeight: 52, alignItems: 'center', justifyContent: 'center', borderRadius: radius.lg, backgroundColor: colors.terracotta[600] }}
      >
        <AppText variant="bodySmall" weight="800" style={{ color: colors.text.inverse }}>Registrar gasto</AppText>
      </InteractivePressable>
      <View style={{ flexDirection: stacked ? 'column' : 'row', gap: spacing[3] }}>
        <InteractivePressable
          onPress={onCreateIncome}
          haptic="light"
          pressScale={motion.scale.button}
          pressedOpacity={0.9}
          accessibilityRole="button"
          accessibilityLabel="Ingreso"
          style={{ flex: stacked ? undefined : 1, minHeight: 48, alignItems: 'center', justifyContent: 'center', borderRadius: radius.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border.default, backgroundColor: colors.surface.card }}
        >
          <AppText variant="bodySmall" weight="700">Ingreso</AppText>
        </InteractivePressable>
        <InteractivePressable
          onPress={onCreateTransfer}
          haptic="light"
          pressScale={motion.scale.button}
          pressedOpacity={0.9}
          accessibilityRole="button"
          accessibilityLabel="Registrar transferencia"
          style={{ flex: stacked ? undefined : 1, minHeight: 48, alignItems: 'center', justifyContent: 'center', borderRadius: radius.lg, borderWidth: stacked ? 0 : StyleSheet.hairlineWidth, borderColor: colors.border.default, backgroundColor: stacked ? 'transparent' : colors.surface.card }}
        >
          <AppText variant="bodySmall" weight="700" tone={stacked ? 'secondary' : 'primary'}>Transferir</AppText>
        </InteractivePressable>
      </View>
    </View>
  );
}

function FinanceMovementsSurface({
  period,
  loading,
  error,
  movements,
  filters,
  onFilterChange,
  onShowAll,
  searchQuery,
  onSearchQueryChange,
  onRetry,
  onMovePeriod,
  onMovementPress,
  onCreateMovement,
}: {
  period: string;
  loading: boolean;
  error: string | null;
  movements: FinanceUnifiedMovementDto[];
  filters: MovementTypeFilterKey[];
  onFilterChange: (filter: MovementFilterKey) => void;
  onShowAll: () => void;
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
  onRetry: () => void;
  onMovePeriod: (direction: 'previous' | 'next') => void;
  onMovementPress?: (movement: FinanceUnifiedMovementDto) => void;
  onCreateMovement: () => void;
}) {
  const theme = useAppTheme();
  const { colors } = theme;
  const styles = createStyles(theme);
  const normalizedFilters = normalizeMovementFilters(filters);
  const allSelected = normalizedFilters.length === ALL_MOVEMENT_TYPE_FILTERS.length;
  const emptyDescription = allSelected
    ? 'Sin movimientos este mes'
    : 'No hay movimientos que coincidan con estos filtros';

  if (loading && movements.length === 0) return <FinanceSurfaceLoading />;
  if (error && movements.length === 0) {
    return (
      <FinanceErrorState
        level="full"
        message={error}
        onRetry={onRetry}
      />
    );
  }

  const groups = groupMovementsByTransactionDate(
    movements.filter((movement) => (
      movementMatchesFilter(movement, normalizedFilters) && movementMatchesSearch(movement, searchQuery)
    )),
  );

  return (
    <View style={styles.surfaceStack}>
      <FinancePeriodNavigator
        label={formatFinancePeriodLabel(period)}
        onPrevious={() => onMovePeriod('previous')}
        onNext={() => onMovePeriod('next')}
        previousAccessibilityLabel="Mes anterior"
        nextAccessibilityLabel="Mes siguiente"
        style={styles.movementPeriodNavigator}
      />
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filterRail}
        keyboardShouldPersistTaps="handled"
        testID="finance-movement-filter"
      >
        <FilterChip label="Todos" selected={allSelected} onPress={onShowAll} />
        {MOVEMENT_FILTER_OPTIONS.map((option) => (
          <FilterChip
            key={option.value}
            label={option.label}
            selected={!allSelected && normalizedFilters.includes(option.value)}
            onPress={() => onFilterChange(option.value)}
          />
        ))}
      </ScrollView>
      <SearchField
        value={searchQuery}
        onChangeText={onSearchQueryChange}
        label="Buscar movimientos"
        placeholder="Comercio, categoría o cuenta"
        returnKeyType="search"
        accessibilityLabel="Buscar movimientos"
        testID="finance-movement-search"
      />
      <InteractivePressable
        onPress={onCreateMovement}
        haptic="light"
        pressScale={theme.motion.scale.button}
        pressedOpacity={0.92}
        accessibilityRole="button"
        accessibilityLabel="Registrar movimiento"
        style={styles.movementPrimaryAction}
        testID="finance-movement-create"
      >
        <HomePlusIcon name="add" size={20} color={colors.text.inverse} />
        <AppText variant="body" weight="800" style={{ color: colors.text.inverse }}>Registrar movimiento</AppText>
      </InteractivePressable>
      {error && movements.length > 0 ? (
        <FinanceErrorState level="refresh" message={error} onRetry={onRetry} />
      ) : null}
      {loading ? <Skeleton width="38%" height={12} /> : null}
      {groups.length === 0 ? (
        <FinanceEmptyState
          level="section"
          title={searchQuery.trim() ? 'No encontramos movimientos' : emptyDescription}
          description={searchQuery.trim()
            ? 'Probá con otro comercio, categoría o cuenta.'
            : allSelected
              ? 'Cuando registres gastos, ingresos o transferencias van a aparecer acá.'
              : 'Probá ajustar los tipos seleccionados.'}
          icon={<HomePlusIcon name="swap-horizontal-outline" size={20} color={colors.text.tertiary} />}
        />
      ) : (
        <View style={styles.movementGroups}>
          {groups.map((group) => (
            <View key={group.date} style={styles.movementGroup}>
              <AppText variant="caption" tone="secondary" weight="800">
                {formatFinanceDateGroupLabel(group.date)}
              </AppText>
              <FinanceGroupedSurface bodyStyle={styles.movementRows}>
                {group.movements.map((movement, index) => (
                  <MovementRow
                    key={`${movement.kind}:${movement.id}`}
                    movement={movement}
                    isLast={index === group.movements.length - 1}
                    onMovementPress={onMovementPress}
                  />
                ))}
              </FinanceGroupedSurface>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function MovementRow({
  movement,
  isLast,
  onMovementPress,
}: {
  movement: FinanceUnifiedMovementDto;
  isLast: boolean;
  onMovementPress?: (movement: FinanceUnifiedMovementDto) => void;
}) {
  const theme = useAppTheme();
  const { colors } = theme;

  if (movement.kind === 'EXPENSE') {
    const hasRefund = !isZeroDecimalString(movement.totalRefunded);
    const presentation = getFinanceCategoryPresentationByLabel(movement.categoryLabel);
    const refundLine = hasRefund
      ? `Devuelto ${formatFinanceAmount(movement.totalRefunded, movement.currency, { sign: 'none' })} · Neto ${formatFinanceAmount(movement.netAmount, movement.currency, { sign: 'none' })}`
      : null;
    const subtitle = movement.categoryLabel
      ? (refundLine ? `${movement.categoryLabel} · ${refundLine}` : movement.categoryLabel)
      : refundLine;
    return (
      <FinanceListRow
        title={financeMovementTitle('expense', movement.description)}
        subtitle={subtitle ?? undefined}
        icon={
          <FinanceIconBox>
            <HomePlusIcon
              name={presentation.iconKey}
              size={18}
              color={financeCategoryToneColor(colors, presentation)}
            />
          </FinanceIconBox>
        }
        value={formatFinanceAmount(movement.amount, movement.currency, {
          sign: 'transaction',
          transactionType: 'expense',
        })}
        valueTone="danger"
        divider={!isLast}
        onPress={onMovementPress ? () => onMovementPress(movement) : undefined}
        accessibilityLabel={financeMovementTitle('expense', movement.description)}
      />
    );
  }

  if (movement.kind === 'INCOME') {
    const presentation = getFinanceCategoryPresentationByLabel(movement.categoryLabel);
    return (
      <FinanceListRow
        title={financeMovementTitle('income', movement.description)}
        subtitle={movement.categoryLabel ?? undefined}
        icon={
          <FinanceIconBox>
            <HomePlusIcon
              name={presentation.iconKey}
              size={18}
              color={financeCategoryToneColor(colors, presentation)}
            />
          </FinanceIconBox>
        }
        value={formatFinanceAmount(movement.amount, movement.currency, {
          sign: 'transaction',
          transactionType: 'income',
        })}
        valueTone="success"
        divider={!isLast}
        onPress={onMovementPress ? () => onMovementPress(movement) : undefined}
        accessibilityLabel={financeMovementTitle('income', movement.description)}
      />
    );
  }

  if (movement.kind === 'TRANSFER') {
    const title = financeTransferTitle(movement);
    const isCrossCurrency = movement.sourceCurrency !== movement.destinationCurrency;
    const amountLabel = isCrossCurrency
      ? `${formatFinanceAmount(movement.sourceAmount, movement.sourceCurrency, { sign: 'none' })} → ${formatFinanceAmount(movement.destinationAmount, movement.destinationCurrency, { sign: 'none' })}`
      : formatFinanceAmount(movement.sourceAmount, movement.sourceCurrency, { sign: 'none' });
    const routeLabel = `${movement.sourceAccount.name} → ${movement.destinationAccount.name}`;
    // ONE root row: the commission is concise supporting copy inside the same
    // row grammar, never a second card/row.
    const commissionLabel = movement.commission?.amount
      ? `Comisión ${formatFinanceAmount(movement.commission.amount, movement.commission.currency ?? movement.sourceCurrency, { sign: 'none' })}`
      : null;
    const subtitleParts = [routeLabel];
    if (movement.description?.trim()) subtitleParts.push(movement.description.trim());
    if (commissionLabel) subtitleParts.push(commissionLabel);
    const subtitle = subtitleParts.join(' · ');
    return (
      <FinanceListRow
        title={title}
        subtitle={subtitle}
        icon={
          <FinanceIconBox>
            <HomePlusIcon name="swap-horizontal-outline" size={18} color={colors.text.tertiary} />
          </FinanceIconBox>
        }
        value={amountLabel}
        valueTone="primary"
        divider={!isLast}
        onPress={onMovementPress ? () => onMovementPress(movement) : undefined}
        accessibilityLabel={`${title}, ${movement.sourceAccount.name} a ${movement.destinationAccount.name}`}
      />
    );
  }

  return null;
}

function createStyles(theme: ReturnType<typeof useAppTheme>) {
  const { colors, radius, spacing, shadows } = theme;

  return StyleSheet.create({
    content: {
      gap: spacing[4],
    },
    hiddenTabSurface: {
      display: 'none',
    },
    header: {
      gap: spacing[3],
      alignItems: 'flex-start',
    },
    contextSelector: {
      alignSelf: 'center',
      width: '58%',
      minWidth: 188,
      maxWidth: 236,
      backgroundColor: colors.surface.glass,
      ...shadows.shadow2,
    },
    loadingRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing[2],
      paddingHorizontal: spacing[2],
    },
    resumenStack: {
      gap: financeSpacing.sectionGap,
    },
    loadingBlock: {
      gap: spacing[3],
    },
    surfaceStack: {
      gap: spacing[8],
    },
    summarySurface: {
      gap: financeSpacing.titleContentGap,
    },
    movementPeriodNavigator: {
      flex: 1,
    },
    summaryStack: {
      gap: spacing[3],
    },
    analysisLink: {
      minHeight: 44,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'flex-end',
      gap: spacing[1],
      paddingHorizontal: spacing[1],
    },
    filterRail: {
      gap: spacing[2],
      paddingRight: spacing[4],
    },
    movementPrimaryAction: {
      minHeight: 56,
      borderRadius: radius.lg,
      backgroundColor: colors.terracotta[600],
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing[2],
    },
    movementGroups: {
      gap: spacing[4],
    },
    movementGroup: {
      gap: spacing[2],
    },
    movementRows: {
      gap: 0,
    },
    flatEmptyState: {
      paddingHorizontal: spacing[4],
      paddingVertical: spacing[5],
    },
    organizeActions: {
      paddingBottom: spacing[2],
    },
  });
}
