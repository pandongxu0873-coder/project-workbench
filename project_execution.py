"""Execution remains completed until new, cited project evidence changes the basis."""
import json
import re
import os
import tempfile
from datetime import date


def snapshot_path(root, project_id, analysis_id):
    if not re.fullmatch(r'[0-9a-f]{20}',project_id) or not re.fullmatch(r'[0-9a-f]{32}',analysis_id):raise ValueError('执行依据身份无效')
    return root / 'project_execution_basis' / project_id / (analysis_id + '.json')


def save_basis(root, project_id, analysis_id, sources):
    path = snapshot_path(root, project_id, analysis_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.basis-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'project_id':project_id,'analysis_id':analysis_id,'sources':sources},handle,ensure_ascii=False)
            handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def execution_state(record, sources, analysis, root, project_id, stale=False):
    record=record or {}
    if record.get('relationship')=='no_contact' or record.get('status')=='暂停跟进':return 'paused'
    if record.get('quick_outcome')!='done':return 'waiting_feedback' if record.get('status')=='已发出等待反馈' else 'actionable'
    try:
        prior=json.loads(snapshot_path(root,project_id,record.get('analysis_id','')).read_text())
        if prior.get('project_id')!=project_id or prior.get('analysis_id')!=record.get('analysis_id'):return 'done_waiting'
        previous=prior['sources']
    except (OSError,ValueError,KeyError):previous=[]
    legacy=not previous
    old={s['path']:s.get('content','') for s in previous}
    changed=[s for s in sources if s.get('relation')!='background_reference' and (not s['path'].startswith('local://') or s['path'].startswith('local://receipt/')) and s.get('content','')!=old.get(s['path'],'')]
    if legacy:
        changed=[s for s in changed if s.get('relation')!='project_source' and s.get('date','')>record.get('saved_at','')[:10] and (s['path'].startswith(('raw/transcripts/','user://correction','local://receipt/')))]
    if not changed:return 'done_waiting'
    if stale:return 'new_evidence_review'
    # A new internal progress quote does not contradict an explicit waiting judgment.
    if (analysis or {}).get('execution_signal')=='waiting_feedback' or ((analysis or {}).get('brief') or {}).get('attention')=='等反馈':
        return 'done_waiting'
    for source in changed:
        if source.get('relation')=='project_source':continue
        day=source.get('date','')
        try:
            if date.fromisoformat(day).isoformat()!=day or day<record.get('saved_at','')[:10] or day>date.today().isoformat():continue
        except ValueError:continue
        for evidence in (analysis or {}).get('evidence',[]):
            quote=evidence.get('quote','').strip()
            # Re-archiving the same quote under a new path is not new feedback.
            if evidence.get('path')==source['path'] and len(quote)>=4 and quote in (source.get('feedback_content','') if source['path'].startswith('local://receipt/') else source.get('content','')) and not any(quote in s.get('content','') for s in previous):
                return 'actionable'
    return 'new_evidence_review'
