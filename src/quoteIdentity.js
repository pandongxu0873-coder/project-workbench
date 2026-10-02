export function sameQuoteScope(identity, values) {
  return identity?.customer === values.customer.trim() && identity?.requirement === values.requirement.trim();
}
export function quoteIdentity(saved) {
  return { quote_id: saved.quote_id, revision: saved.revision, customer: saved.values.customer.trim(), requirement: saved.values.requirement.trim() };
}
export function selectQuoteIdentity(current, values, newId) {
  if (current?.revision > 0 && sameQuoteScope(current, values)) return current;
  return { quote_id: newId(), revision: 0, customer: values.customer.trim(), requirement: values.requirement.trim() };
}
