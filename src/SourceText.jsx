import React from 'react';
import { readableSource } from './sourceText.js';
import './source-text.css';

export function SourceText({ content = '', path = '', truncated = false }) {
  const { body, folded } = readableSource(content, path);
  return <div className="source-text">
    {truncated && <p className="source-truncated" role="status">原文较长，当前显示部分内容，请打开或下载原文件核对全文。</p>}
    <pre className="source-body" tabIndex="0" aria-label="资料正文">{body || '原文暂无可显示内容'}</pre>
    {folded && <details className="source-original">
      <summary>{truncated ? '已加载原文（含归档信息）' : '完整原文（含归档信息）'}</summary>
      <pre tabIndex="0" aria-label="完整原文">{content}</pre>
    </details>}
  </div>;
}
