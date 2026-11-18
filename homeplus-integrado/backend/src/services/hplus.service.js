const { createHttpError } = require('../lib/httpErrors')

const MAX_HISTORY = 50

// H+ reads are always scoped by the authenticated Planner context.  The
// ledger is authoritative; totals are derived at read time, never mutated.
const getSummary = async (context) => {
  const [{ data: totals, error: totalsError }, { data, error }] = await Promise.all([
    context.client.rpc('hplus_get_summary', { p_household_id: context.householdId }).maybeSingle(),
    context.client
      .from('hplus_ledger_entries')
      .select('id, membership_id, event_type, source_type, source_id, points, occurred_at, created_at, metadata')
      .eq('household_id', context.householdId)
      .order('occurred_at', { ascending: false })
      .limit(5),
  ])
  if (totalsError) throw createHttpError(500, 'No pudimos consultar las contribuciones.', 'hplus_read_failed')
  if (error) throw createHttpError(500, 'No pudimos consultar las contribuciones.', 'hplus_read_failed')
  const entries = data ?? []
  return {
    my_points: Number(totals?.my_points ?? 0),
    household_points: Number(totals?.household_points ?? 0),
    recent_entries: entries.filter((entry) => entry.membership_id === context.membershipId).slice(0, 5),
  }
}

const listHistory = async (context, limit = 30) => {
  const safeLimit = Math.min(Math.max(Number.parseInt(limit, 10) || 30, 1), MAX_HISTORY)
  const { data, error } = await context.client
    .from('hplus_ledger_entries')
    .select('id, membership_id, event_type, source_type, source_id, points, occurred_at, created_at, metadata')
    .eq('household_id', context.householdId)
    .order('occurred_at', { ascending: false })
    .limit(safeLimit)
  if (error) throw createHttpError(500, 'No pudimos consultar las contribuciones.', 'hplus_read_failed')
  return { entries: data ?? [] }
}

module.exports = { getSummary, listHistory }
