export const CRM_REFRESH_MS = 5 * 60 * 1000;
export function needsCrmRefresh(result, now = Date.now()) {
  if (!result?.configured) return false;
  return ["QUARTER", "MONTH", "YEAR"].some(period => {
    const stamp = Date.parse(result.snapshot?.dashboards?.[period]?.fetched_at);
    return !Number.isFinite(stamp) || now - stamp >= CRM_REFRESH_MS;
  });
}
export function installCrmAutoSync(check, doc = document, schedule = setInterval, cancel = clearInterval) {
  const visibleCheck = () => { if (doc.visibilityState !== "hidden") check(); };
  visibleCheck();
  const timer = schedule(visibleCheck, CRM_REFRESH_MS);
  doc.addEventListener("visibilitychange", visibleCheck);
  return () => { cancel(timer); doc.removeEventListener("visibilitychange", visibleCheck); };
}
