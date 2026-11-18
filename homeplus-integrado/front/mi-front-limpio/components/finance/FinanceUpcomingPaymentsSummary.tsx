import React from 'react';

import type { PaymentDueDto } from '../../services/finance/financePayments';
import { FinanceGroupedSurface, FinanceSection } from './ui';
import { PaymentRow } from './PaymentRow';

type FinanceUpcomingPaymentsSummaryProps = {
  payments: PaymentDueDto[];
  onPaymentPress: (payment: PaymentDueDto) => void;
  onViewAll: () => void;
};

const SUMMARY_PAYMENT_LIMIT = 3;

/**
 * Reuses the canonical payment snapshot already loaded by PaymentsList.
 * It never fetches or owns payment state, so Resumen and Pagos cannot drift.
 */
export function FinanceUpcomingPaymentsSummary({
  payments,
  onPaymentPress,
  onViewAll,
}: FinanceUpcomingPaymentsSummaryProps) {
  if (payments.length === 0) return null;

  const visiblePayments = payments.slice(0, SUMMARY_PAYMENT_LIMIT);

  return (
    <FinanceSection
      title="Pagos próximos"
      actionLabel="Ver todos"
      onAction={onViewAll}
      actionAccessibilityLabel="Ver todos los pagos"
      testID="finance-summary-upcoming-payments"
    >
      <FinanceGroupedSurface>
        {visiblePayments.map((payment, index) => (
          <PaymentRow
            key={payment.id}
            payment={payment}
            isLast={index === visiblePayments.length - 1}
            onPress={() => onPaymentPress(payment)}
          />
        ))}
      </FinanceGroupedSurface>
    </FinanceSection>
  );
}
