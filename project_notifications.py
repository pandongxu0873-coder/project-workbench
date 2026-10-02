"""Local change inbox. Observes existing reads; never scans, syncs or runs models."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@contextmanager
def database(root):
    folder = Path(root) / 'project_notifications'
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / 'inbox.sqlite3', timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, observed INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0, read_revision INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL, customer TEXT NOT NULL, changed_at TEXT NOT NULL,
            changes TEXT NOT NULL DEFAULT '[]')''')
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def snapshot(project):
    # Hashes come from text already read by build_projects. Never re-open materials here.
    sources = {s['path']: {'hash': s.get('content_sha256') or 'nontext-present', 'readable': bool(s.get('content_sha256')), 'title': s.get('title') or s.get('label') or s['path'],
                          'path': s['path'], 'date': s.get('evidence_date', '')}
               for s in project.get('sources', []) if (s.get('content_sha256') or (s.get('exists') and not s.get('readable'))) and
               s.get('relation') in ('project_source', 'explicit_evidence')}
    return {'sources': sources, 'decision':project.get('notification_state',{}).get('decision'), 'plan': project.get('notification_state', {}).get('plan', ''),
            'round': project.get('notification_state', {}).get('round', ''),
            'analysis': project.get('notification_state', {}).get('analysis', ''),
            'correction': project.get('notification_state', {}).get('correction', ''),
            'archive': project.get('archive', {}).get('revision', 0),
            'archived': bool(project.get('archive', {}).get('archived'))}


def observe(projects, root, observed):
    """Older in-flight reads cannot roll back the newest observed snapshot."""
    with database(root) as db:
        initialized = db.execute("SELECT value FROM meta WHERE key='initialized'").fetchone() is not None
        now = datetime.now(timezone.utc).isoformat()
        for project in projects:
            pid = project['id']
            row = db.execute('SELECT * FROM projects WHERE id=?', (pid,)).fetchone()
            if row and observed <= row['observed']:
                continue
            current = snapshot(project)
            changes = []
            if row:
                old = json.loads(row['snapshot'])
                for path, source in current['sources'].items():
                    previous = old['sources'].get(path)
                    duplicate=not previous and source['hash']!='nontext-present' and any(x['hash']==source['hash'] for x in old['sources'].values())
                    if (not previous or previous['hash'] != source['hash']) and not duplicate:
                        changes.append({'kind': 'material', 'label': '新增资料' if not previous else '资料内容已更新',
                                        **{k: v for k, v in source.items() if k != 'hash'}})
                # A temporarily missing/unreadable source is not a new source on reappearance.
                current['sources'] = {**old['sources'], **current['sources']}
                for key, label in [('plan', '项目行动计划已调整'), ('round', '沟通与执行记录已调整'),
                                   ('correction', '项目补充已保存')]:
                    if current[key] is None:
                        current[key] = old.get(key, '')  # read failed, not a change
                    elif current[key] != old.get(key, ''):
                        changes.append({'kind': key, 'label': label})
                if old.get('decision') and current.get('decision') and current['decision']!=old['decision']:
                    changes.append({'kind':'decision','label':'项目推进状态已变化'})
                if current['archive'] != old['archive']:
                    changes.append({'kind': 'archive', 'label': '项目已归档' if current['archived'] else '项目已恢复跟进'})
            elif initialized:
                changes.append({'kind': 'project', 'label': '新增项目，待查看'})
            revision = (row['revision'] if row else 0) + bool(changes)
            read_revision = row['read_revision'] if row else 0
            previous_changes = json.loads(row['changes']) if row else []
            # Merge all changes since last read. Same material appears once with newest details.
            if changes:
                previous_changes = previous_changes if row and row['revision'] > read_revision else []
                merged = {(c['kind'], c.get('path', '')): c for c in previous_changes}
                merged.update({(c['kind'], c.get('path', '')): {**c, 'at': now} for c in changes})
                previous_changes = list(merged.values())
            db.execute('''INSERT OR REPLACE INTO projects
                (id,snapshot,observed,revision,read_revision,title,customer,changed_at,changes)
                VALUES (?,?,?,?,?,?,?,?,?)''', (pid, json.dumps(current, ensure_ascii=False), observed,
                revision, read_revision, project.get('title', pid), project.get('customer', ''),
                now if changes else row['changed_at'] if row else '', json.dumps(previous_changes, ensure_ascii=False)))
        db.execute("INSERT OR REPLACE INTO meta VALUES ('initialized','1')")
        db.execute("INSERT OR REPLACE INTO meta VALUES ('last_observed',?)", (now,))
        db.execute("DELETE FROM meta WHERE key='error'")


def listing(root):
    with database(root) as db:
        rows = db.execute('SELECT * FROM projects WHERE revision>0 ORDER BY (revision>read_revision) DESC, changed_at DESC').fetchall()
        meta = dict(db.execute('SELECT key,value FROM meta').fetchall())
        return {'ok': True, 'initialized': 'initialized' in meta, 'observed_at': meta.get('last_observed', ''),
                'observation_error': meta.get('error', ''),
                'unread_count': sum(r['revision'] > r['read_revision'] for r in rows),
                'items': [{'project_id': r['id'], 'title': r['title'], 'customer': r['customer'],
                           'revision': r['revision'], 'unread': r['revision'] > r['read_revision'],
                           'at': r['changed_at'], 'archived': json.loads(r['snapshot'])['archived'],
                           'changes': json.loads(r['changes'])} for r in rows]}


def acknowledge(root, payload):
    items = payload.get('items')
    if not isinstance(items, list) or len(items) > 10000:
        raise ValueError('请提交当前显示的消息版本')
    if any(not isinstance(i, dict) or not isinstance(i.get('project_id'), str) or
           type(i.get('revision')) is not int or i['revision'] < 1 for i in items):
        raise ValueError('消息版本无效，请刷新后重试')
    with database(root) as db:
        for i in items:
            row = db.execute('SELECT revision FROM projects WHERE id=?', (i['project_id'],)).fetchone()
            if not row or i['revision'] > row['revision']:
                raise ValueError('消息版本无效，请刷新后重试')
        for i in items:
            # Never mark a newer unseen change read, including another window's race.
            db.execute('UPDATE projects SET read_revision=MAX(read_revision,?) WHERE id=?', (i['revision'], i['project_id']))
    return listing(root)


def observe_safely(projects, root, observed):
    try:
        observe(projects, root, observed)
    except (OSError, sqlite3.Error, ValueError):
        import logging
        logging.exception('Project notification observation failed; business records unchanged')
        try:
            with database(root) as db:
                db.execute("INSERT OR REPLACE INTO meta VALUES ('error','本次变化核对未完成，已有消息保留')")
        except (OSError, sqlite3.Error):
            pass


def handle(h, root):
    from urllib.parse import urlparse
    if urlparse(h.path).path != '/api/project-notifications':
        return False
    from local_resources import guard, read_json
    from local_http import LocalError
    try:
        guard(h)
        result = acknowledge(root, read_json(h)) if h.command == 'POST' else listing(root)
        h._send_json(result)
    except LocalError as e:
        h._send_json({'ok': False, 'error': str(e)}, status=e.status)
    except (ValueError, TypeError):
        h._send_json({'ok': False, 'error': '消息版本无效，请刷新后重试'}, status=400)
    except (OSError, sqlite3.Error):
        h._send_json({'ok': False, 'error': '消息未读到或未保存，请重试'}, status=500)
    return True
