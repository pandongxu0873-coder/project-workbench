import React, { useLayoutEffect, useRef } from 'react';
import { gsap } from 'gsap';

export function AnimatedNumber({ value, format = String, className = '' }) {
  // Amounts and business counts are immediately readable; motion belongs to state changes.
  const formatted = value == null ? '—' : format(value);
  return <span className={`animated-number ${className}`}>{formatted}</span>;
}

export function useWorkbenchMotion(ref, view) {
  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      const seen = new WeakSet(), tweens = new Set();
      const reveal = () => {
        const nodes = [...root.querySelectorAll('.page-header,.overview-heading,.performance-chapter,.performance-heading,.project-overview-table,.aihot-header,.aihot-tools,.aihot-grid,.reset-top-grid,.reset-calendar-surface,.communication-sync > header,.workbench-loading,.crm-empty,.ledger-detail,.project-execution-receipt,.pursuit-header,.pursuit-modes,.pursuit-card,.pursuit-brief,.signal-row,.discovery-judgement-row')].filter(el => !seen.has(el) && el.getClientRects().length);
        nodes.forEach(el => seen.add(el));
        if (nodes.length) tweens.add(gsap.fromTo(nodes, { y: 6, opacity: .8 }, { y: 0, opacity: 1, duration: .2, stagger: { amount: .06 }, ease: 'power2.out', clearProps: 'transform,opacity' }));
      };
      reveal();
      let frame;
      const observer = new MutationObserver(records => {
        if (records.some(record => [...record.addedNodes].some(n => n.nodeType === 1))) { cancelAnimationFrame(frame); frame = requestAnimationFrame(reveal); }
      });
      observer.observe(root, { childList: true, subtree: true });
      const toggle = event => {
        if (event.target.tagName !== 'DETAILS' || !event.target.open) return;
        const nodes = [...event.target.children].filter(el => el.tagName !== 'SUMMARY');
        tweens.add(gsap.fromTo(nodes, { y: 5, opacity: .5 }, { y: 0, opacity: 1, duration: .18, clearProps: 'transform,opacity' }));
      };
      root.addEventListener('toggle', toggle, true);
      return () => { observer.disconnect(); cancelAnimationFrame(frame); root.removeEventListener('toggle', toggle, true); tweens.forEach(t => t.revert()); };
    });
    return () => mm.revert();
  }, [view]);
}

export function GoalBar({ rate, label }) {
  const ref = useRef(null), previous = useRef(0);
  const share = Math.max(0, Math.min(1, (rate || 0) / 100));
  useLayoutEffect(() => {
    if (!ref.current) return;
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => gsap.fromTo(ref.current, { scaleX: previous.current }, { scaleX: share, duration: .22, ease: 'power2.out', transformOrigin: 'left center' }));
    previous.current = share;
    return () => mm.revert();
  }, [share]);
  return <div className="graphite-goal-track" role="img" aria-label={label}><i ref={ref} style={{ transform: `scaleX(${share})` }} /></div>;
}
