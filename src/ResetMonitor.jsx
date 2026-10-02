import React, { useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Sparkles } from 'lucide-react';
import { safeNewsLink, newsTime } from './aiHotData.js';
import { beijingDay, eventDay, monthDays, percentage, resetForecast, resetStatus, resetType, shiftDay, shiftMonth } from './resetMonitorData.js';
import './reset-monitor.css';
function Link({ url, children }) {
  const safe = safeNewsLink(url);
  return safe ? <a href={safe} target="_blank" rel="noopener noreferrer">{children} ↗</a> : null;
}
const time = value => newsTime({ publishedAt: value }) || '时间未明确';
const dayLabel = day => day ? `${Number(day.slice(5, 7))}月${Number(day.slice(-2))}日` : '日期未明确';
const stateLabel = e => e.status === 'confirmed' ? e.type === 'reset_credit' ? '已发卡' : '已重置' : '已预告';
function Post({ post, event, compact = false }) {
  const stage = event.status === 'confirmed' && post.stage?.endsWith('预告') ? '原预告' : post.stage;
  return <article className={`reset-post ${compact ? 'is-current' : ''}`}>
    <header><div className="reset-author"><span aria-hidden="true">T</span><div><strong>Tibo</strong><small>@thsottiaux</small></div></div><time>{time(post.publishedAt)} 发布</time></header>
    <blockquote>{post.text}</blockquote>
    {!compact && stage?.includes('预告') && event.schedule?.label && <p>{stage === '原预告' ? '原预告' : '预告时间'}：{event.schedule.label}</p>}
    <footer><span>{stage} · 中文译文</span><Link url={post.url}>在 X 查看原帖</Link></footer>
  </article>;
}
function currentPost(event) {
  if (!event) return null;
  return event.posts?.find(p => event.status === 'confirmed' && p.stage?.startsWith('确认')) || event.posts?.[0];
}
export function ResetMonitor({ data, stale }) {
  const events = Array.isArray(data.events) ? data.events : [];
  const ordered = useMemo(() => [...events].sort((a, b) => (eventDay(b) || '').localeCompare(eventDay(a) || '') || Date.parse(b.confirmedAt || b.createdAt) - Date.parse(a.confirmedAt || a.createdAt)), [data]);
  const latest = ordered[0];
  const latestReset = ordered.find(e => e.type === 'direct_reset');
  const hasAnnouncement = latestReset?.status === 'announced';
  const latestDay = eventDay(latest || {}) || beijingDay(data.checkedAt) || beijingDay(new Date().toISOString());
  const [selected, setSelected] = useState(latestDay);
  const [month, setMonth] = useState(latestDay.slice(0, 7));
  const grid = useRef(null);
  const days = monthDays(month);
  const today = beijingDay(new Date().toISOString());
  const forecast = useMemo(() => resetForecast(events, data.checkedAt), [data]);
  const selectedEvents = ordered.filter(e => eventDay(e) === selected);
  const monthEvents = events.filter(e => eventDay(e).startsWith(month));
  const post = currentPost(latest);
  function select(day, focus = false) {
    setSelected(day); setMonth(day.slice(0, 7));
    if (focus) requestAnimationFrame(() => grid.current?.querySelector(`[data-day="${day}"]`)?.focus());
  }
  function moveMonth(offset) {
    const target = shiftMonth(month, offset);
    select(eventDay(ordered.find(e => eventDay(e).startsWith(target)) || {}) || `${target}-01`);
  }
  const dateContext = latest?.occurredOn ? '核实发生日期' : latest?.confirmedAt ? '确认帖时间' : latest?.status === 'announced' ? '原预告时间' : '按发帖日期收录 · 发放日期未明确';
  return <div className="reset-monitor">
    <div className="reset-top-grid">
      <section className="reset-overview" aria-label="最新重置状态">
        <div className="reset-status-panel"><div className="reset-panel-label"><h2>{latest?.status === 'announced' ? '最新重置预告' : latest?.type === 'reset_credit' ? '最近一次发卡' : '最近一次重置'}</h2><span>{latest ? stateLabel(latest) : '暂无记录'}</span></div>
          <div className="reset-big-date">{latest ? dayLabel(latestDay) : '尚无核验记录'}{latest?.confirmedAt && <strong>{time(latest.confirmedAt).split(' ').at(-1)}</strong>}</div>
          <p>{latestDay.slice(0, 4)}年 · {dateContext}</p>
          <p className="reset-next-note">{stale ? '当前为上次快照，请刷新核对' : hasAnnouncement ? (latestReset.schedule?.label || '已有预告，具体时间待定') : '下一次重置时间未知'}</p>
        </div>
        {post && <Post post={post} event={latest} compact />}
      </section>
      <aside className="reset-prediction" aria-label="下一次重置概率预测"><header><h2><Sparkles size={17} />重置预测</h2><span>历史估计</span></header>
        {hasAnnouncement ? <div className="reset-prediction-message"><strong>已有预告</strong><p>以 Tibo 原帖给出的时间为准。</p></div> : forecast ? <><p>下一次额度重置 · 北京时间</p><ol>{forecast.probabilities.map(row => <li key={row.day}><div><time>{dayLabel(row.day)}</time><strong>{percentage(row.probability)}<small>%</small></strong></div><meter min="0" max="1" value={row.probability} aria-label={`${row.day} 重置估计概率`} /></li>)}</ol><div className="reset-prediction-foot"><span>{time(forecast.asOf)} 起算</span><span>更晚 {percentage(forecast.laterProbability)}%</span></div><small>历史 {forecast.sampleCount} 次确认记录 · 仅供参考</small></> : <p className="reset-prediction-message">当前样本不足以估计概率。</p>}
      </aside>
    </div>
    <header className="reset-calendar-heading"><h2>重置日历</h2><p>选择日期，查看重置状态与原帖记录。</p></header>
    <div className="reset-calendar-surface">
      <section className="reset-calendar-pane" aria-label="重置日历">
        <header><h3>{month.slice(0, 4)} 年 {Number(month.slice(5))} 月</h3><div><button onClick={() => select(latestDay)}>回到最近</button><button aria-label="上个月" onClick={() => moveMonth(-1)}><ChevronLeft size={17} /></button><button aria-label="下个月" onClick={() => moveMonth(1)}><ChevronRight size={17} /></button></div></header>
        <p className="reset-month-count">本月：{monthEvents.filter(e => e.type === 'direct_reset').length} 条全员重置 · {monthEvents.filter(e => e.type === 'reset_credit').length} 条发重置卡</p>
        <table ref={grid} aria-label={`${month} 重置记录，方向键可切换日期`}><thead><tr>{['一','二','三','四','五','六','日'].map(d => <th key={d} scope="col">{d}</th>)}</tr></thead><tbody>{Array.from({length: days.length / 7}, (_, week) => <tr key={week}>{days.slice(week * 7, week * 7 + 7).map(day => {
          const rows = events.filter(e => eventDay(e) === day);
          const kinds = [...new Set(rows.map(e => e.type))];
          return <td key={day}><button data-day={day} aria-pressed={day === selected} aria-label={`${day}${day === today ? '，今天' : ''}，${rows.length ? kinds.map(type => resetType({type})).join('，') : '暂无记录'}`} className={`${day.startsWith(month) ? '' : 'is-outside'} ${kinds.length ? 'has-event' : ''} ${day === today ? 'is-today' : ''}`} onClick={() => select(day)} onKeyDown={e => {const delta = {ArrowLeft:-1, ArrowRight:1, ArrowUp:-7, ArrowDown:7}[e.key]; if(delta) {e.preventDefault(); select(shiftDay(day, delta), true);}}}><span>{Number(day.slice(-2))}{rows.length > 1 && <sup>+{rows.length-1}</sup>}</span><small>{kinds.map(type => <span key={type} className={type === 'reset_credit' ? 'is-credit' : ''}>{resetType({type})}</span>)}</small></button></td>;
        })}</tr>)}</tbody></table>
        <p className="reset-calendar-note">● 全员重置　<span>● 发重置卡</span>　○ 今天</p><p className="reset-calendar-note">日期不明的发卡记录，按发帖日期收录。</p>
      </section>
      <section className="reset-day-detail" aria-label="所选日期的原帖与说明"><header><h3>{dayLabel(selected)}</h3><span>{selected.slice(0,4)} · {selectedEvents.length} 条记录</span></header>
        {selectedEvents.length ? selectedEvents.map(event => <article className="reset-day-event" key={event.id}><span className="reset-state">{stateLabel(event)} · {resetStatus(event)}</span><h3>{event.title}</h3>{event.scope && <p>适用范围：{event.scope}</p>}{event.confirmationBasis === 'receipt_review' && <p>依据回执核验确认，下面保留原预告。</p>}{event.type === 'reset_credit' && !event.occurredOn && !event.confirmedAt && <p>发放日期未明确，按发帖日期收录。</p>}{event.posts?.map(p => <Post key={p.id} post={p} event={event} />)}</article>) : <div className="reset-no-record"><h3>这一天暂无记录</h3><p>没有当天的核验记录，不代表当天一定没有重置。</p><button onClick={() => select(latestDay)}>查看最近一次重置</button></div>}
      </section>
    </div>
    <details className="reset-method"><summary>这份日历与预测，怎么来的？</summary><p>记录来自 AIHOT 公开接口。预告、原帖确认、回执核验分别标注；确认帖时间不等于精确执行时间。</p><p>概率按原站公开的历史间隔方法在本地计算：仅使用有原帖的已确认全员重置，拟合历史间隔，估计从核验时刻起未来三天及更晚的概率。发卡与未确认预告不进入样本。它不是官方承诺，也不是个人额度重置时间。</p><p>以源站核验时间起算，首日仅计算当天剩余时段；来源未更新时保留旧估计，不冒充实时预测。</p><Link url="https://aihot.news/codex-reset">查看 AIHOT 原站</Link></details>
    <footer className="reset-source-note">已核验至 {time(data.checkedAt)} · 北京时间 · AIHOT 整理，非 OpenAI 官方页面</footer>
  </div>;
}
