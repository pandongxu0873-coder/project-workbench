import React, { useLayoutEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
const wan = value => (value / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
export function PerformanceChart({ trend, granularity }) {
  const line = useRef(null), [active, setActive] = useState(null);
  const W = 660, H = 172, left = 44, top = 16, bottom = 138;
  const max = Math.max(10000, ...trend.map(row => row.amount));
  const min = Math.min(0, ...trend.map(row => row.amount));
  const y = value => bottom - ((value - min) / (max - min)) * (bottom - top);
  const points = trend.map((row, i) => ({ ...row, x: trend.length === 1 ? (W + left) / 2 : left + i / (trend.length - 1) * (W - left - 14), y: y(row.amount) }));
  const fingerprint = JSON.stringify(trend);
  useLayoutEffect(() => {
    setActive(null);
    const el = line.current;
    if (!el) return;
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      const length = el.getTotalLength();
      return gsap.fromTo(el, { strokeDasharray: length, strokeDashoffset: length }, { strokeDashoffset: 0, duration: .8, ease: 'power2.out', clearProps: 'strokeDasharray,strokeDashoffset' });
    });
    return () => mm.revert();
  }, [fingerprint]);
  if (!points.length) return <div className="chart-unavailable">CRM 尚未提供此周期趋势</div>;
  const ticks = [...new Set([min, (max + min) / 2, max])];
  return <figure className="performance-trend"><figcaption><strong>签约节奏</strong><span>{active == null ? `${granularity}业绩 · 万元` : `${points[active]?.label} · ¥${points[active]?.amount.toLocaleString('zh-CN')}`}</span></figcaption>
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${granularity}签约业绩：${points.map(p => `${p.label} ${wan(p.amount)}万元`).join('，')}`}>
      {ticks.map(value => <g key={value}><line x1={left} x2={W-8} y1={y(value)} y2={y(value)} className="trend-grid"/><text x={left-10} y={y(value)+4} textAnchor="end" className="trend-label">{wan(value)}</text></g>)}
      <path ref={line} d={points.map((p,i)=>`${i?'L':'M'} ${p.x} ${p.y}`).join(' ')} className="trend-line" />
      {points.map((p,i)=><g key={`${p.label}-${i}`}><circle cx={p.x} cy={p.y} r="3.5" className="trend-dot"/><circle cx={p.x} cy={p.y} r="12" fill="transparent" tabIndex="0" role="button" aria-label={`${p.label}，${wan(p.amount)}万元`} onFocus={()=>setActive(i)} onBlur={()=>setActive(null)} onMouseEnter={()=>setActive(i)} onMouseLeave={()=>setActive(null)} />{(points.length<8 || i%Math.ceil(points.length/7)===0 || i===points.length-1)&&<text x={p.x} y="162" textAnchor="middle" className="trend-label">{p.label}</text>}</g>)}
    </svg>
    <details className="trend-values"><summary>查看精确数值</summary><div>{points.map((p,i)=><span key={i}>{p.label}<strong>¥{p.amount.toLocaleString('zh-CN',{minimumFractionDigits:2})}</strong></span>)}</div></details>
  </figure>;
}
