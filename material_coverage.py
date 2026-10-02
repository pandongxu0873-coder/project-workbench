"""Local processing receipts. Source access, classification and confirmation stay separate."""
import fcntl
import hashlib
import json
import os
import tempfile
import re
import uuid
from datetime import datetime
from pathlib import Path

CHANNELS = {
    'computer': ('电脑录音', '2026 年起；不读更早录音'),
    'phone': ('手机录音', '2026 年 8 月起；排除旧手机迁移'),
    'desktop': ('桌面文件', '已授权桌面材料；保留原件'),
    'email': ('客户邮件与附件', '相关客户往来；邮件和附件分别核验'),
    'feishu': ('飞书聊天与审批', '相关项目群及华中特批群；不自动发送'),
    'tencent_meeting': ('腾讯会议逐字稿', '当前账号可读的会议及共享记录；不代表同事全部录制'),
}

def stamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def read(root):
    p = Path(root) / 'material_coverage.json'
    if not p.exists():
        return {'revision': 0, 'items': {}, 'channels': {}}
    try:
        value = json.loads(p.read_text())
        if not isinstance(value, dict) or type(value.get('revision')) is not int:
            raise ValueError()
        if any(not isinstance(value.get(k), dict) or any(not isinstance(v, dict) for v in value[k].values()) for k in ('items', 'channels')):
            raise ValueError()
        for item in value['items'].values():
            if any(not isinstance(item.get(k), str) or not re.fullmatch(r'[a-f0-9]{64}', item[k]) for k in ('version','classification_version')):
                raise ValueError()
            datetime.fromisoformat(item['checked_at'])
        return value
    except (ValueError, TypeError, KeyError):
        raise ValueError('资料处理记录暂不可用；原记录已保留')

def write(root, value):
    root = Path(root)
    fd, tmp = tempfile.mkstemp(prefix='.material-coverage-', dir=root)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, root / 'material_coverage.json')
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def record_scan(root, channel, result):
    """Collector-only API: dates/counts come from a real scan receipt, never the UI."""
    if channel not in CHANNELS or result.get('status') not in ('ok', 'partial', 'unavailable'):
        raise ValueError('来源扫描记录无效')
    if not result.get('receipt') or not result.get('checked_at') or not result.get('scope'):
        raise ValueError('扫描记录需要实际范围、时间与回执')
    datetime.fromisoformat(result['checked_at'])
    for k in ('observed', 'new_count', 'changed_count', 'excluded'):
        if k in result and (type(result[k]) is not int or result[k] < 0): raise ValueError('扫描数量无效')
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    with (root / 'material_coverage.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        value = read(root); old = value['channels'].get(channel, {})
        entry = dict(result)
        if result['status'] == 'ok' and result.get('complete_scope') is True:
            entry['last_complete_scan'] = result['checked_at']
        elif old.get('last_complete_scan') and old.get('scope') == result['scope']:
            entry['last_complete_scan'] = old['last_complete_scan']
        if old == entry: return value
        value['channels'][channel] = entry; value['revision'] += 1
        # Scan receipts are immutable, including failed attempts.
        history = root / 'material_scan_history'; history.mkdir(exist_ok=True)
        with (history / f"{value['revision']}-{channel}-{uuid.uuid4().hex}.json").open('x') as out:
            json.dump(entry,out,ensure_ascii=False,indent=2)
        write(root, value)
        return value

def original_file_refs(knowledge_root, original, refs, registered):
    """Match registered originals; supporting notes never substitute for a file."""
    root = Path(knowledge_root).absolute()
    if 'archive_paths' in original:
        paths = set()
        for value in original.get('archive_paths') or []:
            if not isinstance(value, str) or not value:
                continue
            p = Path(value)
            if '..' in p.parts:
                continue
            try:
                relative = p.relative_to(root) if p.is_absolute() else p
            except ValueError:
                continue
            paths.add(str(relative))
        return [a for a in refs if registered.get(a, {}).get('path') in paths]
    # Older rows without archive metadata must identify the original by name.
    title = original.get('title')
    return [a for a in refs if title and Path(registered.get(a, {}).get('path', '')).name == title]

def enrich(root, knowledge_root, index, recordings, files):
    import material_library as material
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    with (root / 'material_coverage.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(root); changed = False
        assets = {}
        for aid, a in index.get('assets', {}).items():
            if material._sensitive(a):
                assets[aid] = {'state': 'restricted', 'signature': 'restricted'}
                continue
            try:
                with material._open(knowledge_root, a.get('path')) as f:
                    s = os.fstat(f.fileno())
                    # Text dependencies are small enough to hash in full. Audio only checks
                    # availability/version metadata: this is not a transcription receipt.
                    signature = [s.st_size, s.st_mtime_ns]
                    if Path(a['path']).suffix.lower() in material.TEXT_SUFFIXES:
                        h = hashlib.sha256()
                        while True:
                            data = f.read(65536)
                            if not data: break
                            h.update(data)
                        signature = [s.st_size, h.hexdigest()]
                assets[aid] = {'state': 'available', 'signature': signature}
            except (OSError, material.MaterialError):
                assets[aid] = {'state': 'unavailable', 'signature': 'unavailable'}
        exceptions = []
        for group, rows in (('recordings', recordings), ('files', files)):
            originals = {x.get('id'): x for x in index.get(group, [])}
            for row in rows:
                rid = row.get('id'); original = originals.get(rid, {})
                if not rid: continue
                refs = [s.get('id') for s in row.get('sources', []) if s.get('id')]
                states = [assets.get(a, {'state': 'unavailable', 'signature': 'unavailable'}) for a in refs]
                meta = digest({k: v for k, v in original.items() if k not in ('processing',)})
                version = digest([meta, [(a, assets.get(a)) for a in refs]])
                old = state['items'].get(rid, {})
                # The first receipt is a baseline of imported classification, not a
                # claim that every amount or customer acceptance has been verified.
                baseline = old.get('classification_version', version)
                stale = baseline != version
                missing = [a for a in refs if assets.get(a, {}).get('state', 'unavailable') == 'unavailable']
                acquired = any(s['state'] == 'available' for s in states)
                primary_refs = original_file_refs(knowledge_root, original, refs, index['assets']) if group == 'files' else refs
                original_available = any(assets.get(a, {}).get('state') == 'available' and (
                    group == 'files' or index['assets'].get(a, {}).get('kind') == 'audio' or
                    Path(index['assets'].get(a, {}).get('path', '')).suffix.lower() in ('.m4a','.mp3','.wav','.aac')) for a in primary_refs)
                transcript = any(s.get('available') and s.get('readable') and re_text(index['assets'].get(s['id'], {})) for s in row.get('sources', []))
                classified = original.get('processing') == 'reviewed' and not stale
                linked = bool(row.get('project_id'))
                detail = {'version': version, 'classification_version': baseline, 'checked_at': stamp()}
                if old.get('version') != version:
                    state['items'][rid] = detail; changed = True
                pipeline = {
                    'acquired': acquired, 'original_available': original_available, 'text_ready': transcript, 'classified': classified,
                    'linked': linked, 'confirmation': 'claim_specific', 'stale': stale,
                    'restricted_count': sum(s['state'] == 'restricted' for s in states),
                    'missing_asset_ids': missing,
                    'label': '内容变化待复核' if stale else '来源暂不可读' if missing else '已分类' if classified else '已归档' if acquired else '未提供在线原件',
                }
                row['pipeline'] = pipeline
                if stale or missing:
                    exceptions.append({'id': rid, 'title': row.get('title'), 'project_id': row.get('project_id'), 'customer': row.get('customer'), 'reason': pipeline['label'], 'kind': group})
        if changed:
            state['revision'] += 1; write(root, state)
        channels = []
        config_path=root/'material_collectors.json'
        config=json.loads(config_path.read_text()) if config_path.exists() else {}
        excluded=config.get('excluded_channels',[])
        for key, (label, scope) in CHANNELS.items():
            receipt = state['channels'].get(key, {})
            channel = {'id': key, 'label': label, 'scope': scope, **receipt, 'status': receipt.get('status', 'unknown')}
            if key == 'desktop':
                from material_inventory import reconcile
                channel['inventory'] = reconcile(root, index, receipt)
            if key in excluded:
                if receipt.get('mode')=='manual_import':
                    channel.update(auto_sync=False,note=receipt.get('note','')+' 本次指定范围为手动导入；日常后台仍不持续读取此来源。')
                else:
                    channel.update(status='excluded',scope='已排除本轮同步；保留历史归档',note='按你的设置，不再采集此来源。已有归档仍可查看。',pending_files=[],failed_files=[])
            channels.append(channel)
        return {'checked_at': stamp(), 'revision': state['revision'], 'channels': channels,
                'exceptions': exceptions, 'summary': {
                    'available_count': sum(r['pipeline']['acquired'] for r in recordings + files),
                    'text_count': sum(r['pipeline']['text_ready'] for r in recordings),
                    'linked_count': sum(r['pipeline']['linked'] for r in recordings),
                    'exception_count': len(exceptions),
                }}

def re_text(asset):
    # A downloaded workbook or generated source manifest is not a transcript.
    path = str(asset.get('path', '')).lower()
    return Path(path).suffix in ('.md', '.txt') and ('transcript' in path or any(x in str(asset.get('label', '')) for x in ('转写', '听写', '摘录', '原文')))
