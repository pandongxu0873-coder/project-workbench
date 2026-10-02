async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败（${response.status}）`);
  }
  if (payload && payload.ok === false) {
    const error = new Error(payload.error || payload.message || "工作台数据状态异常");
    error.payload = payload;
    throw error;
  }
  return payload;
}

// Coalesce concurrent reads only. A write invalidates the in-flight generation;
// its readback must never join a request that started before the write.
export function createApi(send=request) {
  const reads=new Map();
  return {
    get(path) {
      if(!reads.has(path)) {
        const task=Promise.resolve().then(()=>send(path));
        reads.set(path,task);
        const clear=()=>{if(reads.get(path)===task)reads.delete(path);};
        task.then(clear,clear);
      }
      return reads.get(path).then(payload=>structuredClone(payload));
    },
    invalidate(){reads.clear();},
    async post(path,data={},options={}) {
      reads.clear();
      try{return await send(path,{...options,method:'POST',body:JSON.stringify(data)});}
      finally{reads.clear();}
    },
  };
}
export const api=createApi();

export const WORKBENCH_READS = [
  { key: 'dashboard', label: '销售进展与业绩', path: '/api/dashboard' },
  { key: 'accounts', label: '客户资料', path: '/api/account-advancement' },
  { key: 'prospecting', label: '机会动态', path: '/api/prospecting' },
  { key: 'reminders', label: '行动与提醒', path: '/api/risk-todos' },
];

export async function loadWorkbenchData({ onProgress = () => {}, get = api.get } = {}) {
  const results = await Promise.allSettled(WORKBENCH_READS.map(async item => {
    onProgress({ ...item, state: 'loading' });
    try {
      const value = await get(item.path);
      onProgress({ ...item, state: 'ready' });
      return value;
    } catch (error) {
      onProgress({ ...item, state: 'error' });
      throw error;
    }
  }));
  const failures = results.flatMap((result, index) => result.status === 'rejected' ? [WORKBENCH_READS[index].label + '：' + (result.reason?.message || '读取失败')] : []);
  if (failures.length) throw new Error(failures.join('；'));
  return Object.fromEntries(results.map((result, index) => [WORKBENCH_READS[index].key, result.value]));
}
