"""Read-only Tencent Meeting CLI adapter. No cookies, credentials or permission requests.

Unknown schemas or incomplete transcripts are gaps, never a successful empty sync.
Original transcript paragraphs remain distinct from AI minutes and sales decisions.
"""
from __future__ import annotations
import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path
from tools.communication_pipeline import Failure, TZ, runtime_env

READ_COMMANDS={('meeting','list-ended'),('meeting','get'),('record','list'),
               ('record','transcript-paragraphs'),('record','transcript-get')}
LIMITATIONS='腾讯会议机器逐字稿，未逐字校听；发言人昵称不等于客户身份。只读采集，不申请他人权限。纪要由工作台按原文提炼，与微信、邮件、合同、工单交叉核验；方案确认、审批申请与实际履行分别判断。'

def executable(cfg):
    candidate=cfg.get('tencent_meeting',{}).get('cli') or shutil.which('tmeet',path=runtime_env()['PATH'])
    if not candidate or not Path(candidate).is_file():raise Failure('腾讯会议官方读取工具尚未安装')
    return str(candidate)

def probe(cfg):
    if not cfg.get('tencent_meeting',{}).get('enabled'):
        return {'configured':False,'available':False,'reason':'腾讯会议尚未启用'}
    try:
        p=subprocess.run([executable(cfg),'auth','status'],capture_output=True,text=True,timeout=30,env=runtime_env())
        # Status output can contain account identity. Persist only this boolean.
        ready=p.returncode==0 and 'Logged in' in p.stdout and 'RefreshToken: expired' not in p.stdout and 'Session has expired' not in p.stdout
        return {'configured':True,'available':ready,'reason':'' if ready else '腾讯会议需要本人完成官方账号授权','scope':'当前账号可读的会议逐字稿，包括已获阅读权限的共享记录；不代表全部同事录制'}
    except (Failure,OSError,subprocess.TimeoutExpired):
        return {'configured':True,'available':False,'reason':'腾讯会议连接检查未完成'}

def call(cfg,command,**params):
    if tuple(command) not in READ_COMMANDS:raise Failure('腾讯会议同步只允许读取')
    args=[executable(cfg),*command,'--format','json']
    for key,value in params.items():
        if value is not None and value!='':args += ['--'+key.replace('_','-'),str(value)]
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=120,env=runtime_env())
        if p.returncode:raise Failure('腾讯会议读取失败或权限不足；已有资料保留')
        result=json.loads(p.stdout)
        if not isinstance(result,dict) or not isinstance(result.get('data'),dict):raise ValueError()
        return result['data']
    except (OSError,ValueError,subprocess.TimeoutExpired):raise Failure('腾讯会议返回结构异常或读取超时；未视为无新记录') from None

def listed(cfg,command,key,**params):
    rows=[];seen=set();token=''
    for _ in range(100):
        data=call(cfg,command,page_token=token,page_size=30,**params)
        page=data.get(key)
        # Official record list omits its nil slice (and zero total_count) for a
        # truly empty directory. Accept only the exact explicit zero-page shape
        # observed from the CLI; unknown schemas and missing cursors still fail.
        empty_keys={'current_page','current_size','has_more','next_page_token','total_page','total_count',key}
        explicit_empty=not token and not rows and type(data.get('current_page')) is int and data['current_page']==1 and all(type(data.get(k)) is int and data[k]==0 for k in ('current_size','total_page')) and ('total_count' not in data or type(data['total_count']) is int and data['total_count']==0)
        if tuple(command)==('record','list') and page is None and set(data)<=empty_keys and explicit_empty and data.get('has_more') is False and data.get('next_page_token')=='':page=[]
        if not isinstance(page,list) or any(not isinstance(row,dict) for row in page):raise Failure('腾讯会议列表结构变化；未宣称完整')
        rows+=page;token=data.get('next_page_token','')
        if not token:
            if data.get('has_more') is True:raise Failure('腾讯会议仍有后续页但没有游标；未宣称完整')
            return rows
        if not isinstance(token,str) or token in seen:raise Failure('腾讯会议分页没有推进；已读结果不代表全部')
        seen.add(token)
    raise Failure('腾讯会议列表超过读取上限，保留来源缺口')

def business_date(value):
    try:
        if isinstance(value,(int,float)) or (isinstance(value,str) and value.isdigit()):
            return dt.datetime.fromtimestamp(float(value),TZ).date().isoformat()
        parsed=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError()
        return parsed.astimezone(TZ).date().isoformat()
    except (ValueError,TypeError,OverflowError,OSError):return ''

def transcript(cfg,record):
    fid=record.get('record_file_id');mid=record.get('meeting_id','')
    if not isinstance(fid,str) or not fid:raise Failure('腾讯会议缺少录制文件标识')
    meta=call(cfg,('record','transcript-paragraphs'),record_file_id=fid,meeting_id=mid)
    pids=meta.get('pids');total=meta.get('total')
    if not isinstance(pids,list) or not isinstance(total,int) or isinstance(total,bool) or total!=len(pids) or not 0<total<=100000:
        raise Failure('腾讯会议段落目录未完整读取，不能用摘要冒充逐字稿')
    expected=[str(p.get('pid')) for p in pids if isinstance(p,dict) and p.get('pid') is not None]
    if len(expected)!=total or len(set(expected))!=total:raise Failure('腾讯会议段落目录不完整')
    paragraphs={};expected_set=set(expected)
    def consume(data):
        minutes=data.get('minutes',{});page=minutes.get('paragraphs') if isinstance(minutes,dict) else None
        if not isinstance(page,list):raise Failure('腾讯会议逐字稿结构变化；待适配')
        for row in page:
            if not isinstance(row,dict) or row.get('pid') is None:raise Failure('腾讯会议缺少段落编号')
            ident=str(row['pid'])
            if ident not in expected_set:raise Failure('腾讯会议返回其他段落，未合并')
            if ident in paragraphs and paragraphs[ident]!=row:raise Failure('腾讯会议逐字稿读取期间发生变化')
            paragraphs[ident]=row
    # The official CLI returns the whole transcript when pid/limit are omitted.
    # Prove coverage against its independently read paragraph directory. Only
    # fall back to bounded pages if it explicitly reports more content.
    data=call(cfg,('record','transcript-get'),record_file_id=fid,meeting_id=mid)
    consume(data)
    if set(paragraphs)!=expected_set and data.get('more') is True:
        for offset in range(0,total,30):
            if set(expected[offset:offset+30]).issubset(paragraphs):continue
            consume(call(cfg,('record','transcript-get'),record_file_id=fid,meeting_id=mid,pid=expected[offset],limit=30))
    if set(paragraphs)!=set(expected):raise Failure('腾讯会议逐字稿仍有缺页；原记录保留，下次续读')
    ordered=[paragraphs[i] for i in expected];lines=[]
    for row in ordered:
        sentences=row.get('sentences')
        if not isinstance(sentences,list):raise Failure('腾讯会议句子结构变化')
        content=[]
        for sentence in sentences:
            if not isinstance(sentence,dict) or not isinstance(sentence.get('words'),list):raise Failure('腾讯会议原话结构不完整')
            words=sentence['words']
            if any(not isinstance(w,dict) or not isinstance(w.get('text'),str) for w in words):raise Failure('腾讯会议原话结构变化')
            content.append(''.join(w['text'] for w in words))
        info=row.get('speaker_info',row.get('speaker')) or {}
        if not isinstance(info,dict):raise Failure('腾讯会议发言人结构变化，身份未核实')
        speaker=info.get('username') or info.get('user_name') or '发言身份未核实'
        if not isinstance(speaker,str):raise Failure('腾讯会议发言人昵称结构异常')
        stamp=row.get('start_time','')
        lines.append(f'[{stamp}] {speaker}：'+''.join(content))
    if not any(line.split('：',1)[-1].strip() for line in lines):raise Failure('腾讯会议未取得有效逐字稿正文')
    return {'record_file_id':fid,'meeting_id':mid,'paragraph_index':pids,'paragraphs':ordered},'\n'.join(lines)

def collect(pipe):
    config=pipe.cfg.get('tencent_meeting',{})
    if not config.get('enabled'):return
    before_new=pipe.new;before_gaps=len(pipe.gaps)
    # Shared recordings can be granted or finish transcription days after the
    # meeting. Keep their occurrence date; extend only this source's read scope.
    lookback=config.get('lookback_days',30)
    valid_lookback=isinstance(lookback,int) and not isinstance(lookback,bool) and 1<=lookback<=90
    scan_start=min(pipe.start,pipe.end-dt.timedelta(days=lookback-1)) if valid_lookback else pipe.start
    pinned=set();pinned_codes=[]
    def receipt(events=None,unavailable=False):
        from tools.communication_pipeline import save,now
        from material_coverage import record_scan
        events=events or {};gaps=pipe.gaps[before_gaps:];value={'checked_at':now(),'scope':f'{scan_start} 至 {pipe.end}；另回看 {len(pinned_codes)} 场指定共享会议；当前账号可读记录，不代表同事全部录制','requested_window':{'from':str(pipe.start),'to':str(pipe.end)},'lookback_days':lookback if valid_lookback else None,'pinned_meeting_codes':pinned_codes,'status':'unavailable' if unavailable else 'partial' if gaps else 'ok','complete_scope':not gaps and not unavailable,'observed':len(events),'new_count':pipe.new-before_new,'record_file_count':sum(len(v) for v in events.values()),'note':'按原会议日期计数，指定共享会议保留原日期回看；未指定且早于回看范围的记录需历史补录。不同版本不是独立佐证。读取完成不等于分类、项目判断或商务确认完成。','gaps':gaps,'receipt':str(pipe.run_root/'tencent-read-receipt.json')}
        save(pipe.run_root/'tencent-read-receipt.json',value);record_scan(pipe.state,'tencent_meeting',value)
    if not valid_lookback:
        pipe.gap('腾讯会议','回看天数配置无效；需为1至90的整数，未视为无新记录');receipt(unavailable=True);return
    codes=config.get('shared_meeting_codes',[])
    if not isinstance(codes,list) or len(codes)>30:
        pipe.gap('腾讯会议','指定共享会议配置无效或超过30场，未宣称完整');receipt(unavailable=True);return
    if not probe(pipe.cfg)['available']:
        pipe.gap('腾讯会议','腾讯会议需要本人完成官方账号授权；共享记录尚未自动读取');receipt(unavailable=True);return
    params={'start':str(scan_start)+'T00:00:00+08:00','end':str(pipe.end)+'T23:59:59+08:00'}
    candidates=[]
    try:
        meetings=listed(pipe.cfg,('meeting','list-ended'),'meeting_info_list',**params)
        for meeting in meetings:
            records=meeting.get('records')
            if not isinstance(records,list):
                pipe.gap('腾讯会议','部分会议未返回录制目录；不能判断没有录制');continue
            count=meeting.get('records_total_count',len(records))
            if not isinstance(count,int) or isinstance(count,bool):raise Failure('腾讯会议录制数量结构变化')
            if count>len(records):pipe.gap('腾讯会议','部分会议录制目录仅返回最近几项；共享范围尚未完整')
            for record in records:
                if not isinstance(record,dict):raise Failure('腾讯会议录制目录结构变化')
                candidates.append({**record,'meeting_id':meeting.get('meeting_id',''),'meeting_subject':meeting.get('subject','')})
    except Failure as exc:pipe.gap('腾讯会议会议目录',str(exc))
    def add_files(groups):
        result=[]
        for group in groups:
            files=group.get('record_files')
            if not isinstance(files,list):pipe.gap('腾讯会议录制目录','部分可读录制缺少文件编号；未宣称完整');continue
            if any(not isinstance(f,dict) for f in files):raise Failure('腾讯会议录制文件目录结构变化')
            result.extend({**group,**f,'permission_status':'can_view'} for f in files)
        return result
    from tools.communication_pipeline import load,save
    watch_path=Path(getattr(pipe,'root',pipe.state/'communication_pipeline'))/'tencent_watch.json'
    watch=load(watch_path,{'version':1,'meetings':{}})
    if not isinstance(watch,dict) or watch.get('version')!=1 or not isinstance(watch.get('meetings'),dict) or any(not isinstance(ids,list) or len(ids)>100 or any(not isinstance(mid,str) or not mid for mid in ids) for ids in watch['meetings'].values()):
        pipe.gap('腾讯会议','已登记共享会议身份记录不可读；保留原文，未宣称完整');receipt(unavailable=True);return
    watched={code:set(watch['meetings'].get(code,[])) for code in map(str,codes)}
    pinned.update(mid for ids in watched.values() for mid in ids)
    for code in dict.fromkeys(str(code) for code in codes):
        if not re.fullmatch(r'\d{9}',code):
            pipe.gap('腾讯会议','指定共享会议编号无效，未忽略为成功空结果');continue
        pinned_codes.append(code)
        try:
            # Official record list accepts code OR dates, never both. Meeting
            # get's enrichment can silently turn a record-read failure into [];
            # query this directory directly, including its pagination.
            files=add_files(listed(pipe.cfg,('record','list'),'record_meetings',meeting_code=code))
            if not files or any(not isinstance(row.get('meeting_id'),str) or not row['meeting_id'] for row in files):
                pipe.gap('腾讯会议','指定共享会议录制或身份未完整读回；保留原件，不视为没有更新')
            if any(row.get('meeting_code') not in (None,'',code) for row in files):raise Failure('共享目录返回其他会议编号，未合并')
            current_ids={row['meeting_id'] for row in files if isinstance(row.get('meeting_id'),str) and row['meeting_id']}
            # Meeting codes can be reused. Continue watching the exact event ID;
            # a new event under the same code must not retract the older one.
            for mid in sorted(watched[code]-current_ids):
                older=add_files(listed(pipe.cfg,('record','list'),'record_meetings',meeting_id=mid))
                if any(row.get('meeting_id')!=mid for row in older):raise Failure('指定历史会议返回其他事件，未合并')
                if not older:pipe.gap('腾讯会议','已登记共享会议原文未读回；保留既有版本')
                files.extend(older)
            known=watched[code]|current_ids
            if len(known)>100:raise Failure('共享会议历史事件超过回看上限；保留已登记身份并报告缺口')
            watched[code]=known;pinned.update(known)
            candidates.extend(files)
        except Failure as exc:pipe.gap('腾讯会议指定共享记录',str(exc))
    if watched:
        updated={**watch,'version':1,'meetings':{**watch['meetings'],**{code:sorted(ids) for code,ids in watched.items()}}}
        if updated!=watch:save(watch_path,updated)
    # File-level list includes recordings shared with this account even when
    # it cannot access the organizer's meeting-level record.
    try:
        candidates.extend(add_files(listed(pipe.cfg,('record','list'),'record_meetings',**params)))
    except Failure as exc:pipe.gap('腾讯会议可读录制目录',str(exc))
    # Prefer a complete readable variant over a closed or incomplete meeting
    # directory entry. A single file can be shared at file level only.
    def rank(r):
        state=r.get('state','')
        complete=isinstance(state,str) and '完成' in state and not any(x in state for x in ('录制中','转码中'))
        readable=r.get('permission_status')=='can_view'
        dated=bool(business_date(r.get('media_start_time') or r.get('record_start_time')))
        return (not (readable and dated and complete),not readable,not dated,not complete)
    candidates.sort(key=rank)
    seen=set();events={};blocked=set()
    for record in candidates:
        fid=record.get('record_file_id');title=record.get('subject') or record.get('meeting_subject') or '腾讯会议记录'
        if not isinstance(fid,str) or not fid:
            pipe.gap(title,'录制文件编号缺失，不能判断没有新逐字稿');continue
        if fid in seen:continue
        seen.add(fid)
        date=business_date(record.get('media_start_time') or record.get('record_start_time'))
        if not date:pipe.gap(title,'会议发生日期尚未读回，未用采集日期替代');continue
        if date>str(pipe.end) or (date<str(scan_start) and record.get('meeting_id') not in pinned):continue
        if record.get('permission_status')!='can_view':
            pipe.gap(title,'共享记录未取得原文读取权限，未自动向同事申请');continue
        state=record.get('state','')
        if not isinstance(state,str) or '完成' not in state or any(x in state for x in ('录制中','转码中')):
            pipe.gap(title,'录制尚未确认转码完成，下次再读取');continue
        mid=record.get('meeting_id') or ''
        key=(mid if isinstance(mid,str) and mid else 'file-'+fid,date)
        try:
            original,text=transcript(pipe.cfg,record)
            # Different file IDs are source variants of the exact same meeting,
            # never two independent confirmations. Keep every readable original.
            events.setdefault(key,[]).append((record,original,text))
        except Failure as exc:
            blocked.add(key);pipe.gap(title,str(exc))
    # A wholly missing event must be checked too; iterating only events.items()
    # otherwise reports a successful empty scan when all prior versions vanish.
    for entry in pipe.ledger['items'].values():
        event_key=entry.get('key','');date=entry.get('business_date','')
        if entry.get('channel')!='tencent_meeting' or entry.get('status') not in ('archived','archived_reference','ignored') or not event_key.startswith('tencent-event:'):continue
        event=event_key[len('tencent-event:'):]
        if date and date<=str(pipe.end) and (date>=str(scan_start) or event in pinned) and (event,date) not in events:
            pipe.gap(entry.get('title') or event,'已归档会议本轮全部原文版本未读回；保留旧资料，不认定原文撤回或没有更新')
    for (event,date),versions in events.items():
        if (event,date) in blocked:
            pipe.gap(versions[0][0].get('meeting_subject') or event,'同会议部分可读版本未完整取得，保留既有归档，未发布成删减后的新版本');continue
        versions.sort(key=lambda v:v[0]['record_file_id'])
        event_key='tencent-event:'+event
        current_files={r['record_file_id'] for r,_,_ in versions}
        prior=[e for e in pipe.ledger['items'].values() if e.get('key')==event_key and e.get('business_date')==date and e.get('status') in ('archived','archived_reference','ignored')]
        lost=False
        for entry in prior:
            try:
                from tools.communication_pipeline import digest
                path=Path(entry['original'])
                if path.stat().st_size>pipe.cfg.get('max_file_bytes',500_000_000):raise ValueError()
                if digest(path.read_bytes())!=entry.get('sha256'):raise ValueError()
                saved=json.loads(path.read_text())
                text_path=Path(entry.get('text_path',''))
                if not text_path.is_file() or digest(text_path.read_bytes())!=entry.get('text_sha256'):raise ValueError()
                previous_files={v['record_file_id'] for v in saved['source_versions']}
                lost=lost or not previous_files.issubset(current_files)
            except (KeyError,ValueError,OSError,TypeError):
                lost=True
        if lost:
            pipe.gap(event,'已知原文版本本轮未全部读回，保留既有完整归档，不把权限或目录缺失当成内容撤回');continue
        titles=sorted(set(r.get('meeting_subject') or r.get('subject') or '腾讯会议记录' for r,_,_ in versions))
        title=titles[0];originals=[original for _,original,_ in versions]
        envelope={'version':2,'channel':'tencent_meeting','business_date':date,'meeting_event_id':event,'subjects':titles,'source_versions':originals}
        body=json.dumps(envelope,ensure_ascii=False,sort_keys=True).encode()
        sections=[f'会议日期：{date}\n会议主题：{title}\n会议事件编号：{event}\n同一场会议的 {len(versions)} 个原文版本。版本差异保留，重复内容不构成多重独立佐证。']
        for record,_,text in versions:
            sections.append(f'\n## 原文版本 · {record["record_file_id"]}\n逐字稿：\n{text}')
        sections.append('\n读取边界：'+LIMITATIONS)
        text='\n'.join(sections)
        # Avatar URLs and other non-business metadata can change while the exact
        # dated transcript is identical. Keep a read receipt, not a second fact.
        same=next((e for e in prior if e.get('text_sha256') and Path(e.get('text_path','')).is_file() and Path(e['text_path']).read_text()==text),None)
        if same:
            from tools.communication_pipeline import save,digest
            save(pipe.run_root/'read_receipts'/('tencent-'+digest(body)+'.json'),envelope)
            pipe.observed+=1;pipe.duplicates+=1;pipe.records[same['id']]=same
        else:
            pipe.stage(event_key,title,body,'.json','tencent_meeting','tencent-meeting://'+event,date,
                       text=text,limitations=LIMITATIONS+'同会议不同录制版本只算一次沟通事件；不得把两版转写视为相互独立的证明。')
    receipt(events)
