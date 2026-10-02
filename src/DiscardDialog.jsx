import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

const DiscardContext = createContext(null);
export const NavigationGuardContext = createContext(null);
export const useDiscardChanges = () => useContext(DiscardContext);

export function DiscardChangesProvider({ children }) {
  const [message, setMessage] = useState('');
  const pending = useRef(null), dialog = useRef(null);
  const ask = useCallback((description = '离开会放弃尚未保存的修改，已保存记录不受影响。') => {
    if (pending.current) return Promise.resolve(false);
    setMessage(description);
    return new Promise(resolve => { pending.current = resolve; });
  }, []);
  const answer = value => { const resolve = pending.current; pending.current = null; setMessage(''); resolve?.(value); };
  useEffect(() => { if (message) dialog.current?.showModal(); }, [message]);
  useEffect(() => () => { pending.current?.(false); }, []);
  return <DiscardContext.Provider value={ask}>{children}{message && <dialog ref={dialog} className="project-leave-dialog" aria-labelledby="leave-workbench-title" onCancel={e => { e.preventDefault(); e.stopPropagation(); answer(false); }}>
    <h2 id="leave-workbench-title">内容尚未保存</h2><p>{message}</p><div className="workspace-shortcuts"><button autoFocus onClick={() => answer(false)}>继续编辑</button><button onClick={() => answer(true)}>放弃修改并继续</button></div>
  </dialog>}</DiscardContext.Provider>;
}
