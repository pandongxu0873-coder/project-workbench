import React from 'react';
import { Check, CircleAlert, LoaderCircle, RefreshCw } from 'lucide-react';
import { WORKBENCH_READS } from './api.js';
import './workbench-loading.css';
function Steps({ progress = [], compact = false }) {
  return <div className={`update-steps ${compact ? 'is-compact' : ''}`}>{WORKBENCH_READS.map(item => {
    const state = progress.find(row => row.key === item.key)?.state || 'loading';
    const Icon = state === 'ready' ? Check : state === 'error' ? CircleAlert : LoaderCircle;
    return <div key={item.key} className={`update-step is-${state}`}><Icon size={14} aria-hidden="true" /><span>{item.label}</span><small>{state === 'ready' ? '已更新' : state === 'error' ? '未能更新' : '读取中'}</small></div>;
  })}</div>;
}
export function UpdateProgress({ progress }) {
  const complete = progress.filter(item => item.state === 'ready').length;
  return <aside className="update-progress" role="status" aria-live="polite"><div className="update-progress-title"><RefreshCw size={16} /><strong>正在更新工作台</strong><span>{complete} / {WORKBENCH_READS.length} 已更新</span><small>当前内容仍可浏览</small></div><Steps progress={progress} compact /></aside>;
}
export function ProjectListSkeleton() {
  return <div className="project-list-skeleton" role="status" aria-label="正在读取项目简报"><div className="startup-skeleton-caption"><LoaderCircle size={15} /><span>正在整理项目进展</span></div><div aria-hidden="true">{[0,1,2,3].map(row => <div className="project-skeleton-row" key={row}><div><i className="skeleton-bar wide" /><i className="skeleton-bar short" /></div><i className="skeleton-bar" /><i className="skeleton-bar" /><i className="skeleton-bar wide" /></div>)}</div></div>;
}
export function WorkbenchLoading({ title, progress }) {
  return <section className="workbench-loading" role="status" aria-live="polite"><header><span className="startup-mark"><RefreshCw size={23} /></span><div><span className="startup-eyebrow">项目管理工作台</span><h1>正在准备{title}</h1><p>汇总最新进展，其他页面可以正常打开。</p></div></header><Steps progress={progress} /><div aria-hidden="true" className="startup-content-preview"><div className="startup-skeleton-summary">{[0,1,2].map(i=><div key={i}><i className="skeleton-bar short"/><i className="skeleton-bar wide"/></div>)}</div>{[0,1,2].map(i=><div className="project-skeleton-row" key={i}><i className="skeleton-bar wide"/><i className="skeleton-bar"/><i className="skeleton-bar wide"/></div>)}</div></section>;
}
