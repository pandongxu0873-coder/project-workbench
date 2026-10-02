import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createWorkbenchNavigation, readNavigationContext } from '../src/workbenchNavigation.js';

const settle = () => new Promise(resolve => setImmediate(resolve));
function browser() {
  const listeners = new Set(), entries = [null]; let index = 0;
  const history = {
    get state() { return entries[index]; },
    replaceState(v) { entries[index] = structuredClone(v); },
    pushState(v) { entries.splice(++index); entries[index] = structuredClone(v); },
    go(delta) { if (index + delta < 0 || index + delta >= entries.length) return; index += delta; const state = this.state; queueMicrotask(() => listeners.forEach(fn => fn({ state }))); },
    back() { this.go(-1); }, forward() { this.go(1); },
  };
  return { history, addEventListener(_, fn) { listeners.add(fn); }, removeEventListener(_, fn) { listeners.delete(fn); } };
}
test('project → knowledge → browser back/forward preserves project, source context and origin filters', async () => {
  const win = browser(), visits = []; let snapshot = { overview: 'customer A', scroll: 320 };
  const nav = createWorkbenchNavigation({ window: win, initial: { view: 'projects', projectId: '' }, canLeave: () => true, apply: (r, s) => visits.push([r, s]), capture: () => snapshot });
  nav.push({ view: 'projects', projectId: 'A' });
  snapshot = { overview: 'customer A', scroll: 410 };
  nav.push({ view: 'knowledge', projectId: 'A', sourcePath: 'demo.md' });
  nav.back(); await settle();
  assert.equal(visits.at(-1)[0].projectId, 'A'); assert.equal(visits.at(-1)[0].view, 'projects'); assert.equal(visits.at(-1)[1].scroll, 410);
  nav.back(); await settle();
  assert.equal(visits.at(-1)[0].projectId, ''); assert.equal(visits.at(-1)[1].overview, 'customer A');
  win.history.forward(); await settle(); win.history.forward(); await settle();
  assert.equal(visits.at(-1)[0].sourcePath, 'demo.md');
  nav.destroy();
});
test('cancel back preserves current history and inputs; discard later reaches exact previous entry', async () => {
  const win = browser(), visits = []; let answer;
  const nav = createWorkbenchNavigation({ window: win, initial: { view: 'projects' }, canLeave: () => new Promise(resolve => { answer = resolve; }), apply: r => visits.push(r) });
  nav.push({ view: 'knowledge', projectId: 'A' });
  nav.back(); await settle();
  assert.equal(readNavigationContext(null, win.history).view, 'knowledge'); assert.equal(visits.length, 0);
  assert.equal(nav.push({ view: 'discover' }), false);
  answer(false); await settle(); assert.equal(visits.length, 0);
  nav.back(); await settle(); answer(true); await settle();
  assert.equal(visits.at(-1).view, 'projects');
  nav.destroy();
});
test('reload reads the actual browser entry rather than a newer session context', () => {
  const win = browser(); const nav = createWorkbenchNavigation({ window: win, initial: { view: 'projects', projectId: 'A' }, canLeave: () => true, apply: () => {} });
  assert.equal(readNavigationContext({ getItem: () => '{"view":"pricing"}' }, win.history).projectId, 'A'); nav.destroy();
});
