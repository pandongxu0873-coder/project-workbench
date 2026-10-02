import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// GFM tables stay readable in the narrow Agent pane. Links still require a
// source receipt from this conversation; autolinks cannot open arbitrary URLs.
export default function AgentAnswer({content,sources=[],conversationId}){
 return React.createElement(ReactMarkdown,{
  remarkPlugins:[remarkGfm],
  components:{
   table:({children})=>React.createElement('div',{className:'agent-table-frame'},React.createElement('small',{className:'agent-table-hint'},'左右滚动查看完整表格'),React.createElement('div',{className:'agent-answer-table',tabIndex:0,role:'region','aria-label':'Agent 回答表格，可横向滚动'},React.createElement('table',null,children))),
   a:({href,children})=>{
    const source=sources.find(s=>s.path===href);
    return source?React.createElement('a',{href:`/api/agent/source?id=${conversationId}&path=${encodeURIComponent(source.path)}`},children):React.createElement('span',null,children);
   }
  }
 },content);
}
