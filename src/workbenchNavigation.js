const KEY = 'salesWorkbenchNavigation';
export function readNavigationContext(storage, history) {
  try { return history?.state?.[KEY]?.route || JSON.parse(storage.getItem('workbench-context')) || {}; }
  catch { return {}; }
}

// Restore the current history entry before asking about unsaved work. Cancelling
// therefore preserves both the forward stack and the form that owns the guard.
export function createWorkbenchNavigation({ window: win, initial, canLeave, apply, capture = () => ({}) }) {
  const previous = win.history.state?.[KEY];
  let current = previous || { index: 0, route: initial, snapshot: {} };
  let phase = null, disposed = false;
  const write = (entry, replace = false) => win.history[replace ? 'replaceState' : 'pushState']({ ...win.history.state, [KEY]: entry }, '');
  write(current, true);
  const snapshot = () => { current = { ...current, snapshot: capture() }; write(current, true); };
  const deliver = entry => { current = entry; apply(entry.route, entry.snapshot); };
  async function onPop(event) {
    if (disposed) return;
    const target = event.state?.[KEY];
    if (!target) return; // Leaving the document uses the native beforeunload guard.
    if (phase?.kind === 'restore') {
      const pending = phase;
      if (target.index !== current.index) { win.history.go(current.index - target.index); return; }
      write(current, true);
      phase = { kind: 'asking' };
      let allowed = false;
      try { allowed = await canLeave(); } catch { /* Preserve inputs on failure. */ }
      if (disposed) return;
      if (allowed) { phase = { kind: 'commit', target: pending.target }; win.history.go(pending.target.index - current.index); }
      else phase = null;
      return;
    }
    if (phase?.kind === 'commit' && target.index === phase.target.index) { phase = null; deliver(target); return; }
    if (phase) { if (target.index !== current.index) win.history.go(current.index - target.index); return; }
    if (target.index === current.index) return;
    // The outgoing entry's scroll was already remembered by capture listeners.
    phase = { kind: 'restore', target };
    win.history.go(current.index - target.index);
  }
  win.addEventListener('popstate', onPop);
  return {
    push(route) {
      if (phase) return false;
      snapshot();
      current = { index: current.index + 1, route, snapshot: {} }; write(current);
      return true;
    },
    replace(route) { if (!phase) { current = { ...current, route }; write(current, true); } },
    // Scroll can fire dozens of times a second; keep it in memory until the
    // entry is left/restored instead of hitting the browser history write limit.
    remember() { if (!phase) current = { ...current, snapshot: capture() }; },
    back() { if (!phase && current.index > 0) win.history.back(); },
    busy: () => Boolean(phase),
    canGoBack: () => current.index > 0,
    destroy() { disposed = true; win.removeEventListener('popstate', onPop); },
  };
}
