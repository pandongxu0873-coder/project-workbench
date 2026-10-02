export function commercialText(result, kind) {
  if (kind === 'internal') return result?.internal_approval || '';
  if (!result?.customer_email || result.contact_blocked) return '';
  return `主题：${result.customer_email.subject}\n\n${result.customer_email.body}`;
}
export function commercialOutputKey(result) {
  return JSON.stringify([result?.draft?.confirmation_fingerprint, result?.approval_ready,
    result?.contact_blocked, commercialText(result, 'internal'), commercialText(result, 'customer')]);
}
