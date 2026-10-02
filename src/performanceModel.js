// Display-only projections. CRM aggregates remain authoritative; order rows never replace them.
export function finiteAmount(value) {
  if (value == null || value === '' || typeof value === 'boolean') return null;
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : null;
}
export function performanceModel(data = {}) {
  const target = data.personalTargetAchievement?.totalPerformance;
  const amount = finiteAmount(data.totalPerformance?.amount);
  const goal = target?.configured ? finiteAmount(target.target) : null;
  const actual = finiteAmount(target?.actual);
  const rate = goal > 0 && actual != null ? actual / goal * 100 : null;
  // CRM trend buckets are period amounts, not cumulative amounts.
  const useWeeks = data.periodType !== 'YEAR' && Boolean(data.signingTrends?.WEEK);
  const source = (useWeeks ? data.signingTrends.WEEK : data.signingTrends?.MONTH) || data.signingTrend || [];
  const trend = source.filter(row => finiteAmount(row.totalAmount) != null).map(row => ({ label: row.label, amount: Number(row.totalAmount), rangeStart: row.rangeStart }));
  return { amount, goal: goal > 0 ? goal : null, rate, gap: rate == null ? null : Math.max(0, goal - actual),
    trend, granularity: useWeeks ? '每周' : '每月',
    pending: finiteAmount(data.pendingReceivable?.amount), overdue: finiteAmount(data.pendingReceivable?.secondaryAmount),
    // No subtraction from performance: CRM has not provided a same-scope received total.
    received: null,
  };
}
export function periodOrders(snapshot, data) {
  const resource = snapshot?.resources?.orders;
  const rows = resource?.data?.list || [];
  const start = Date.parse(data?.rangeStart), end = Date.parse(data?.rangeEnd);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return [];
  // rangeEnd is a local calendar date at midnight, inclusive for that whole date.
  return rows.filter(row => {
    const date = Date.parse(row.orderDate);
    return Number.isFinite(date) && date >= start && date < end + 86400000;
  }).sort((a, b) => Date.parse(b.orderDate) - Date.parse(a.orderDate));
}

export function projectPayments(orders = []) {
  const unique = [...new Map(orders.map(order => [order.id, order])).values()];
  const groups = new Map();
  for (const order of unique) {
    // Only explicit CRM opportunity IDs join orders into a project. Never match by fuzzy customer name.
    const key = order.opportunityId ? `opportunity:${order.opportunityId}` : `order:${order.id}`;
    if (!groups.has(key)) groups.set(key, { key, title: order.opportunityName || order.bizCode, customer: order.customerName, orders: [] });
    groups.get(key).orders.push(order);
  }
  const sum = (rows, field) => rows.length && rows.every(row => finiteAmount(row[field]) != null) ? rows.reduce((total, row) => total + Math.round(Number(row[field]) * 100), 0) / 100 : null;
  return { groups: [...groups.values()].map(group => ({ ...group, amount: sum(group.orders,'orderAmount'), received: sum(group.orders,'receivedAmount'), pending: sum(group.orders,'pendingReceivableAmount') })), received: sum(unique,'receivedAmount'), pending: sum(unique,'pendingReceivableAmount'), count: unique.length };
}
