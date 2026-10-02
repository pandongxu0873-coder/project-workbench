"""Durable, bounded local upkeep; the browser only reads progress."""
import json
import fcntl
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

LOCK = threading.RLock()
INTERVALS = {'communications': 3600}
CRM_TZ = ZoneInfo('Asia/Shanghai')

def _read_saved_status(root):
    try: return json.loads((root/'background_operations.json').read_text())
    except (OSError, ValueError): return {'jobs':{}}

def _read_object(path):
    try:
        value=json.loads(path.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def _timestamp(value):
    try:return datetime.fromisoformat(value).timestamp() if isinstance(value,str) else 0
    except (ValueError,OverflowError,OSError):return 0

def _pipeline_is_alive(folder,active):
    pid=active.get('pid')
    if type(pid) is not int or pid<=0:return False
    try:
        os.kill(pid,0)
        # An existing lock is opened read-only; observing never creates state.
        with (folder/'pipeline.lock').open('rb') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return True
            fcntl.flock(lock,fcntl.LOCK_UN)
    except (OSError,ValueError):pass
    return False

def read_status(root):
    """Project live communication progress without changing scheduler ownership."""
    state=_read_saved_status(root)
    jobs=state.setdefault('jobs',{});job=jobs.get('communications',{})
    folder=root/'communication_pipeline';active=_read_object(folder/'active_run.json')
    latest=_read_object(folder/'latest.json')
    floor=max(_timestamp(job.get('dispatched_at') or job.get('last_attempt_at')),
              _timestamp(job.get('last_success_at')),_timestamp(job.get('current_finished_at')))
    started=_timestamp(active.get('started_at'));run_id=active.get('run_id');request_id=active.get('request_id')
    valid_run=isinstance(run_id,str) and bool(run_id.strip()) and isinstance(request_id,str) and bool(request_id.strip()) and started>0
    embedded=active.get('receipt',{})
    if not valid_run or not isinstance(embedded,dict) or embedded.get('run_id')!=run_id or _timestamp(embedded.get('checked_at'))<started:embedded={}
    receipts=[r for r in (latest,embedded) if isinstance(r,dict) and r.get('status') in ('completed','partial','failed') and isinstance(r.get('run_id'),str) and r['run_id'].strip() and _timestamp(r.get('checked_at'))>=floor and _timestamp(r.get('checked_at'))>0]
    terminal=max(receipts,key=lambda r:_timestamp(r['checked_at']),default={})
    finished=_timestamp(terminal.get('checked_at'))
    if valid_run and active.get('state')=='running' and started>=floor and started>=finished and _pipeline_is_alive(folder,active):
        jobs['communications']={**job,'status':'running','error':'','live_run_id':run_id,'live_request_id':request_id,
            'current_started_at':active['started_at'],'current_phase':active.get('phase',''),
            'analysis_done':active.get('analysis_done',0),'analysis_total':active.get('analysis_total',0),
            'refresh_done':active.get('refresh_done',0),'refresh_total':active.get('refresh_total',0)}
    elif terminal and (not valid_run or finished>=started):
        status=terminal['status']
        if status=='completed' and (terminal.get('gaps') or terminal.get('refresh_pending') or any(terminal.get('unresolved',{}).values())):status='partial'
        jobs['communications']={**job,'status':'ready' if status=='completed' else status,'live_run_id':terminal['run_id'],
            'current_finished_at':terminal['checked_at'],'error':'' if status=='completed' else '部分材料尚未完成，已保留成功结果' if status=='partial' else '本轮未完成，已保留原件与进度'}
    elif valid_run and active.get('state')=='running' and started>=floor:
        jobs['communications']={**job,'status':'needs_input','error':'本轮处理已中断，原件与进度保留，等待后台核对恢复',
            'live_run_id':run_id,'live_request_id':request_id,'current_started_at':active['started_at']}
    jobs.pop('crm', None)  # Retired connector: never present old schedules as active.
    return state

def record(root, key, **changes):
    with LOCK:
        state=_read_saved_status(root)
        state.setdefault('jobs',{}).setdefault(key,{}).update(changes)
        path=root/'background_operations.json';path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(path)

def run_once(root, knowledge, clock=time.time, communications=None):
    if communications is None:
        import communication_jobs as communications
    for key,interval in INTERVALS.items():
        job=_read_saved_status(root).get('jobs',{}).get(key,{})
        now = clock()
        stamp=datetime.fromtimestamp(now, CRM_TZ).isoformat(timespec='seconds')
        if now<job.get('next_epoch',0):continue
        record(root,key,status='running',last_attempt_at=stamp,next_epoch=now+interval,interval_seconds=interval,owner='本机后台')
        try:
            current=communications.status(root,knowledge)
            active=current.get('job',{})
            if active.get('request_id') and active['request_id']!=job.get('request_id') and active.get('started_at','')>=job.get('dispatched_at',stamp):
                adopted={'request_id':active['request_id'],'run_id':active.get('run_id',''),'dispatched_at':active.get('started_at',stamp),'awaiting_result':True,'recovery_attempts':0}
                job={**job,**adopted};record(root,key,**adopted)
            if current.get('job',{}).get('running'):
                record(root,key,status='running',error='',next_epoch=clock()+60);continue
            if job.get('awaiting_result') and current.get('job',{}).get('state')!='interrupted':
                receipt=current.get('receipt',{})
                matching = bool(receipt.get('checked_at') and receipt['checked_at'] >= job.get('dispatched_at', stamp))
                if job.get('run_id'):matching = matching and receipt.get('run_id')==job['run_id']
                if job.get('request_id'):matching = matching and current.get('job',{}).get('request_id')==job['request_id']
                if matching and receipt.get('status')=='completed' and not receipt.get('refresh_pending'):
                    record(root,key,status='ready',last_success_at=receipt['checked_at'],error='',awaiting_result=False,failures=0,recovery_attempts=0)
                    continue
                if matching and receipt.get('status') in ('partial','failed','completed') and not receipt.get('refresh_pending'):
                    record(root,key,status='partial',error='部分来源未完成，已保留成功资料；下一轮继续检查连接',awaiting_result=False)
                    continue
            if current.get('analysis_refresh',{}).get('active'):
                record(root,key,status='running',error='',next_epoch=clock()+60);continue
            recovering=bool(job.get('awaiting_result') or current.get('job',{}).get('state')=='interrupted' or current.get('receipt',{}).get('refresh_pending'))
            recoveries=job.get('recovery_attempts',0)
            if recovering and recoveries>=3:
                # A stalled project analysis must not stop preservation of new files.
                # Reuse the same collector and lock once per day; do not reset the
                # inference recovery budget or clear pending project refreshes.
                if job.get('file_collection_date')!=stamp[:10]:
                    result=communications.start({'action':'collect'},root,knowledge)
                    if result.get('started'):
                        record(root,key,status='running',file_collection_date=stamp[:10],file_collection_at=stamp,
                               request_id=result.get('job',{}).get('request_id',''),run_id=result.get('job',{}).get('run_id',''),
                               dispatched_at=stamp,awaiting_result=False,next_epoch=clock()+interval,
                               error='仅继续采集与原件保全；原有分析待恢复')
                        continue
                record(root,key,status='needs_input',error='原有分析恢复未完成；文件每日采集继续，已保留进度',next_epoch=clock()+interval);continue
            action='resume' if current.get('job',{}).get('state')=='interrupted' or current.get('receipt',{}).get('refresh_pending') else 'run'
            result=communications.start({'action':action},root,knowledge)
            record(root,key,status='running' if result.get('started') or result.get('job',{}).get('running') else 'waiting',awaiting_result=True,recovery_attempts=recoveries+1 if recovering else 0,dispatched_at=stamp,request_id=result.get('job',{}).get('request_id',''),run_id=result.get('job',{}).get('run_id',''),next_epoch=clock()+60,error='')
        except Exception:
            # Never serialize arbitrary exception strings (may include private payloads).
            attempts=job.get('failures',0)+1
            record(root,key,status='error',error='本轮更新未完成，保留历史；后台稍后重试，连接详情可在对应工作区查看',failures=attempts,next_epoch=clock()+min(interval,60*2**min(attempts,5)))

def run_loop(root,knowledge,stop):
    # Let the server become reachable before starting independent upkeep.
    if stop.wait(15):return
    while not stop.is_set():
        try:run_once(root,knowledge)
        except (OSError,ValueError):pass
        stop.wait(30)
