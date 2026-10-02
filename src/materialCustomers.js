// Display aliases from reviewed material labels. Original attribution remains visible in details.
// Customer-specific aliases and reviewed recording labels stay in local configuration.
const GROUPS = {};
export function customerFacet(value) {
  if (typeof value !== "string" || !value.trim()) return "归属待核";
  return GROUPS[value] || value;
}
