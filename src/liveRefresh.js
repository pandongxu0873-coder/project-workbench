// Quiet reads only. Hidden tabs stop polling; returning to the app rechecks immediately.
export function installLiveRefresh(read, { doc = document, win = window, schedule = setInterval, cancel = clearInterval, interval = 60000 } = {}) {
  let stopped = false, pending = false;
  const check = async () => {
    if (stopped || pending || doc.visibilityState === 'hidden') return;
    pending = true;
    try { await read(); } catch { /* The owning surface displays read failures. */ }
    finally { pending = false; }
  };
  const timer = schedule(check, interval);
  doc.addEventListener('visibilitychange', check);
  win.addEventListener('focus', check);
  win.addEventListener('workbench-refresh', check);
  return () => { stopped = true; cancel(timer); doc.removeEventListener('visibilitychange', check); win.removeEventListener('focus', check); win.removeEventListener('workbench-refresh', check); };
}
