"""Explicitly linked K100 follow-up outbox. No model calls and no legacy CRM changes."""
import ctypes
import fcntl
import hashlib
import json
import os
import re
import ssl
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

BASE = os.environ.get('WORKBENCH_CRM_BASE_URL', 'https://crm.example.invalid').rstrip('/')
SERVICE = b'com.salesworkbench.crm-session'
ACCOUNT = b'local-user'
ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,160}$')
TYPES = {'CUSTOMER_VISIT': '客户拜访', 'PHONE_CALL': '电话沟通', 'WECHAT': '微信沟通', 'BUSINESS_MEETING': '商务会议', 'OPPORTUNITY_PROGRESS': '商机推进', 'GENERAL_NOTE': '普通备注', 'INTERNAL_COMMUNICATION': '内部沟通'}
NON_EFFECTIVE = {'GENERAL_NOTE', 'INTERNAL_COMMUNICATION'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class SyncError(ValueError):
    def __init__(self, message, kind='failed'):
        super().__init__(message)
        self.kind = kind


def keychain(value=None):
    from macos_keychain import security
    lib = security()
    size, data, item = ctypes.c_uint32(), ctypes.c_void_p(), ctypes.c_void_p()
    code = lib.SecKeychainFindGenericPassword(None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT, ctypes.byref(size), ctypes.byref(data), ctypes.byref(item))
    if code not in (0, -25300):
        raise SyncError('新 K100 本机凭据暂不可读取', 'needs_login')
    prior = None
    if code == 0:
        try:
            prior = json.loads(ctypes.string_at(data, size.value).decode())
        finally:
            lib.SecKeychainItemFreeContent(None, data)
    try:
        if value is not None:
            raw = json.dumps(value).encode()
            if code == 0:
                lib.SecKeychainItemModifyAttributesAndData.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p]
                result = lib.SecKeychainItemModifyAttributesAndData(item, None, len(raw), raw)
            else:
                result = lib.SecKeychainAddGenericPassword(None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT, len(raw), raw, None)
            if result:
                raise SyncError('新 K100 会话未能保存到本机钥匙串', 'needs_login')
        return prior
    finally:
        if item.value:
            cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
            cf.CFRelease.argtypes = [ctypes.c_void_p]
            cf.CFRelease(item)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, method='GET', body=None, credential=None):
    # Only paths constructed inside this module; never expose a generic proxy.
    credential = credential or keychain()
    if not credential:
        raise SyncError('请连接新 K100 登录会话；本地内容已保留', 'needs_login')
    headers = {'Accept': 'application/json', 'Cookie': 'K100_SESSION=' + credential['session'] + '; XSRF-TOKEN=' + credential['csrf'], 'X-XSRF-TOKEN': credential['csrf'], 'Origin': BASE, 'Referer': BASE + '/sales-workspace'}
    raw = None
    if body is not None:
        raw = json.dumps(body, ensure_ascii=False).encode()
        headers['Content-Type'] = 'application/json'
        headers['X-Idempotency-Key'] = body['clientRequestId']
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    opener = build_opener(HTTPSHandler(context=context), NoRedirect())
    try:
        with opener.open(Request(BASE + path, data=raw, headers=headers, method=method), timeout=20) as response:
            response_bytes = response.read()
            value = json.loads(response_bytes) if response_bytes.strip() else {}
    except HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308, 401):
            raise SyncError('新 K100 登录已失效，请重新连接；没有丢弃本地记录', 'needs_login') from None
        if exc.code == 403:
            raise SyncError('新 K100 权限或会话校验未通过；未标记同步成功', 'needs_login') from None
        raise SyncError(f'新 K100 返回 HTTP {exc.code}，待核对后处理', 'uncertain' if method == 'POST' and exc.code >= 500 else 'failed') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise SyncError('新 K100 连接或响应异常；写入结果需回读核对', 'uncertain' if method == 'POST' else 'failed') from None
    if not isinstance(value, (dict, list)):
        raise SyncError('新 K100 返回格式未识别', 'uncertain' if method == 'POST' else 'failed')
    return value


def configure(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        credential = {k: value[k] for k in ('session', 'csrf')}
        if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_=%+./-]{8,4096}', v) for v in credential.values()):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise SyncError('登录会话格式不正确') from None
    me = request('/api/auth/me', credential=credential)
    if not isinstance(me, dict) or not me.get('userId') or me.get('impersonating'):
        raise SyncError('请使用本人正常登录会话连接')
    prior = keychain()
    if prior and str(prior.get('identity', {}).get('userId')) != str(me['userId']):
        raise SyncError('账号与既有连接不同，未覆盖会话或发送待同步内容')
    credential['identity'] = me
    keychain(credential)
    return {'ok': True, 'configured': True, 'message': '新 K100 登录已验证，会话仅存本机钥匙串', 'identity_fields': sorted(me) if isinstance(me, dict) else []}


def valid_id(value):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise SyncError('客户编号无效')
    return value


def customer_detail(customer_id):
    return request('/api/sales/customers/' + valid_id(customer_id))


def customers():
    rows, seen, total = [], set(), None
    for page in range(100):
        data = request('/api/sales/customers?' + urlencode({'page': page, 'size': 10, 'quickView': 'ALL_CUSTOMERS', 'sort': 'UPDATED_DESC'}))
        if not isinstance(data, dict) or not isinstance(data.get('items'), list) or type(data.get('totalElements')) is not int:
            raise SyncError('客户分页结构未识别')
        if total is None:
            total = data['totalElements']
        if data['totalElements'] != total or data.get('page') != page:
            raise SyncError('读取中客户范围发生变化，请重试')
        for row in data['items']:
            cid = valid_id(row.get('id'))
            if cid in seen:
                raise SyncError('客户分页出现重复，未标记读取完整')
            seen.add(cid)
            rows.append({k: row.get(k) for k in ('id', 'legalName', 'linghangCustomerId', 'isMine', 'updatedAt')})
        if len(rows) == total:
            return {'ok': True, 'items': rows}
        if not data['items'] or len(rows) > total:
            raise SyncError('客户分页数量不一致')
    raise SyncError('超出本次客户读取上限')


@contextmanager
def locked(root):
    folder = Path(root) / 'k100_sync'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / 'state.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield folder


def read_state(folder):
    path = folder / 'state.json'
    return json.loads(path.read_text()) if path.exists() else {'links': {}, 'events': {}}


def write_state(folder, state):
    fd, name = tempfile.mkstemp(prefix='.state-', dir=folder)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(state, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, folder / 'state.json')
    finally:
        if os.path.exists(name):
            os.unlink(name)


def identity():
    credential = keychain()
    if not credential:
        raise SyncError('新 K100 需要重新连接，本地进展已保留', 'needs_login')
    me = request('/api/auth/me', credential=credential)
    if not me.get('userId') or me.get('impersonating') or str(me['userId']) != str(credential['identity'].get('userId')):
        raise SyncError('登录身份发生变化，未发送待同步进展', 'needs_login')
    return str(me['userId'])


def target(customer_id):
    user_id = identity()
    customer = customer_detail(customer_id).get('customer', {})
    if customer.get('id') != customer_id or customer.get('isMine') is not True:
        raise SyncError('客户编号或当前归属不一致，未写入新 K100', 'blocked')
    if 'ADD_FOLLOW_UP' not in customer.get('availableActions', []):
        raise SyncError('该主体当前不提供新增客户跟进入口，未绕过页面权限', 'blocked')
    return user_id, customer


def link_project(root, project_id, customer_id, knowledge_root):
    from project_workspace import build_projects
    project = next((p for p in build_projects(knowledge_root, root) if p['id'] == project_id), None)
    if not project or project.get('archive', {}).get('archived'):
        raise SyncError('请选择一个未归档的本地项目')
    customer_id = valid_id(customer_id)
    uid, customer = target(customer_id)
    with locked(root) as folder:
        state = read_state(folder)
        existing = state['links'].get(project_id)
        if existing and existing['customer_id'] != customer_id:
            raise SyncError('已有主体对应关系；为避免待发送内容写错客户，本入口不覆盖旧关联')
        state['links'][project_id] = {'project_id': project_id, 'project_title': project['title'], 'customer_id': customer_id, 'customer_name': customer['legalName'], 'user_id': uid, 'linked_at': now(), 'enabled': True}
        write_state(folder, state)
    return status(root, project_id)


def identity_audit(root, knowledge_root, roster=None, projects=None):
    """Reuse source-bound order evidence and explicit party lines, never brand similarity."""
    from project_workspace import build_projects
    import project_crm
    roster = roster if roster is not None else customers()['items']
    projects = projects if projects is not None else build_projects(knowledge_root, root)
    by_name = {}
    for row in roster:
        if row.get('isMine') is True:
            by_name.setdefault(row.get('legalName', '').strip(), []).append(row)
    with locked(root) as folder:
        links = read_state(folder)['links']
    items = []
    for project in projects:
        if project.get('archive', {}).get('archived') or project['id'] in links:
            continue
        proofs = []
        audited = project_crm.audit(project['id'], knowledge_root, root, project_snapshot=project, include_quote=False)
        for match in audited['matches']:
            order = match['order']
            rows = [x for x in roster if x.get('isMine') is True and
                    str(x.get('linghangCustomerId')) == str(order.get('customerId')) and
                    x.get('legalName') == order.get('customerName')]
            if len(rows) == 1:
                proofs.append({'customer_id': rows[0]['id'], 'customer_name': rows[0]['legalName'],
                               'basis': '原订单编号与迁移客户编号一致', 'evidence': match['evidence']})
        # Full, explicitly labelled party declarations in this project's direct sources.
        # Background references and mentions inside prose are not identity declarations.
        for source in project.get('sources', []):
            if source.get('relation') == 'background_reference' or not source.get('readable'):
                continue
            path = (Path(knowledge_root) / source['path']).resolve()
            if Path(knowledge_root).resolve() not in path.parents or not path.is_file():
                continue
            raw = path.read_bytes()
            for line in raw.decode('utf-8', errors='replace').splitlines():
                plain = re.sub(r'^[\s>*-]+', '', line).replace('**', '').strip()
                party = re.fullmatch(r'甲方[：:]\s*(.+?)\s*', plain)
                if not party:
                    continue
                name = party[1].strip()
                rows = by_name.get(name, [])
                if len(rows) == 1:
                    proofs.append({'customer_id': rows[0]['id'], 'customer_name': name,
                                   'basis': '本项目原文明确列出甲方',
                                   'evidence': {'path': source['path'], 'quote': line,
                                                'sha256': hashlib.sha256(raw).hexdigest()}})
        ids = {x['customer_id'] for x in proofs}
        items.append({'project_id': project['id'], 'project_title': project['title'],
                      'customer': project.get('customer', ''),
                      'state': 'verified' if len(ids) == 1 and not audited['issues'] else 'needs_identity',
                      'proofs': proofs,
                      'question': '这个项目应归到哪个 K100 客户主体？',
                      'reason': '原文出现不同主体，不能自动合并' if len(ids) > 1 else
                                '已有对应证据发生变化，需要核对' if audited['issues'] else
                                '已核对项目直接引用资料，尚无唯一的采购/客户主体依据'})
    return {'ok': True, 'items': items}


def link_verified(root, project_id, knowledge_root):
    result = identity_audit(root, knowledge_root)
    item = next((x for x in result['items'] if x['project_id'] == project_id), None)
    if not item or item['state'] != 'verified':
        raise SyncError('当前依据不足以自动关联，请核对具体主体')
    proof = item['proofs'][0]
    # Existing link path rechecks ownership/permissions and never sends old progress.
    value = link_project(root, project_id, proof['customer_id'], knowledge_root)
    with locked(root) as folder:
        state = read_state(folder)
        state['links'][project_id]['identity_evidence'] = item['proofs']
        state['links'][project_id]['identity_method'] = 'source_verified'
        write_state(folder, state)
    return status(root, project_id)


def status(root, project_id=''):
    with locked(root) as folder:
        state = read_state(folder)
    events = sorted((e for e in state['events'].values() if not project_id or e.get('project_id') == project_id), key=lambda e: e['created_at'], reverse=True)
    return {'ok': True, 'configured': bool(keychain()), 'link': state['links'].get(project_id), 'events': [public_event(e) for e in events[:20]], 'types': TYPES}


def public_event(event):
    return {k: event.get(k) for k in ('id', 'project_id', 'customer_name', 'type', 'content', 'occurred_at', 'state', 'message', 'created_at', 'verified_at', 'remote_id', 'effective', 'protection_refreshed', 'release_at', 'last_valid_followup_at', 'audit_id', 'test')}


def validate_progress(body):
    kind = body.get('type', 'GENERAL_NOTE')
    content = body.get('content', '').strip()
    if kind not in TYPES or not content or len(content) > 6000:
        raise SyncError('请选择跟进类型并填写不超过 6000 字的真实进展')
    try:
        occurred = datetime.fromisoformat(body['occurredAt'].replace('Z', '+00:00'))
        if occurred.tzinfo is None or occurred.timestamp() > datetime.now(timezone.utc).timestamp() + 60:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise SyncError('请填写真实发生时间；不能用未来时间刷新保护期') from None
    if body.get('test') and (kind != 'GENERAL_NOTE' or '技术接入测试' not in content):
        raise SyncError('技术验证只能使用明确标注的普通备注')
    if kind not in NON_EFFECTIVE and ('技术接入测试' in content or body.get('test')):
        raise SyncError('测试备注不能作为有效跟进')
    return kind, content, occurred.astimezone(timezone.utc).isoformat(timespec='seconds')


def audit_records(customer_id):
    result = request('/api/sales/operation-records?' + urlencode({'entityType': 'CUSTOMER', 'entityId': customer_id, 'page': 0, 'size': 20}))
    if not isinstance(result, dict) or not isinstance(result.get('items'), list):
        raise SyncError('操作记录暂不可回读')
    return result['items']


def progress(root, body, knowledge_root=None):
    kind, content, occurred = validate_progress(body)
    project_id = body.get('project_id', '')
    test = body.get('test') is True
    source_id = body.get('source_id', '')
    if not isinstance(source_id, str) or not ID_RE.fullmatch(source_id):
        raise SyncError('缺少本次更新的稳定编号')
    with locked(root) as folder:
        state = read_state(folder)
        if test:
            if project_id:
                raise SyncError('技术测试独立保存，不冒充项目业务进展')
            customer_id = valid_id(body.get('customer_id'))
            link = None
        else:
            link = state['links'].get(project_id)
            if not link or not link['enabled']:
                raise SyncError('本项目尚未关联新 K100；进展仍保留在工作台', 'needs_link')
            customer_id = link['customer_id']
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'k100:{project_id}:{source_id}'))
        digest = hashlib.sha256(json.dumps([customer_id, kind, content, occurred, test], ensure_ascii=False).encode()).hexdigest()
        if event_id in state['events']:
            event = state['events'][event_id]
            if event['digest'] != digest:
                raise SyncError('同一更新编号的内容已变化，未重复提交')
            return {'ok': True, 'event': public_event(event)}
        event = {'id': event_id, 'project_id': project_id, 'source_id': source_id, 'customer_id': customer_id, 'customer_name': link['customer_name'] if link else '', 'user_id': link['user_id'] if link else None, 'type': kind, 'content': content, 'occurred_at': occurred, 'created_at': now(), 'digest': digest, 'test': test, 'state': 'pending', 'message': '本地已保存，待写入新 K100'}
        state['events'][event_id] = event
        write_state(folder, state)
    return deliver(root, event_id, knowledge_root)


def deliver(root, event_id, knowledge_root=None):
    with locked(root) as folder:
        state = read_state(folder)
        event = state['events'].get(event_id)
        if not event:
            raise SyncError('同步记录不存在')
        if event['state'] in ('confirmed', 'sending', 'uncertain', 'written'):
            return {'ok': True, 'event': public_event(event)}
        try:
            if event.get('project_id'):
                from project_archive import state as archive_state
                if archive_state(root, event['project_id'])['archived']:
                    raise SyncError('项目已归档，未发送待同步进展', 'blocked')
            uid, before = target(event['customer_id'])
            if event.get('user_id') and event['user_id'] != uid:
                raise SyncError('关联账号发生变化，未发送', 'needs_login')
            event['user_id'], event['customer_name'] = uid, before['legalName']
            baseline = audit_records(event['customer_id'])
            event['baseline_audit_ids'] = [x['id'] for x in baseline]
            event['before'] = {k: before.get(k) for k in ('lastValidFollowUpAt', 'k100PoolReleaseAt', 'releaseDeadlineAt')}
            event['state'] = 'sending'
            event['message'] = '本地已保存，正在写入新 K100'
            write_state(folder, state)
            payload = {'type': event['type'], 'occurredAt': event['occurred_at'], 'content': event['content'], 'nextActionTitle': '', 'clientRequestId': event['id']}
            result = request('/api/sales/customers/' + event['customer_id'] + '/follow-ups', 'POST', payload)
            event['response_fields'] = sorted(result) if isinstance(result, dict) else []
            event['remote_id'] = str(result.get('id', '')) if isinstance(result, dict) else ''
            event['state'] = 'written'
            event['message'] = '新 K100 已接受写入，正在回读操作回执'
            write_state(folder, state)
            reconcile_event(event)
        except SyncError as exc:
            if event['state'] in ('written', 'sending') and exc.kind not in ('needs_login', 'failed'):
                event['state'] = 'uncertain'
            elif event['state'] == 'written':
                event['state'] = 'written'
            else:
                event['state'] = exc.kind
            event['message'] = str(exc)
        except Exception:
            event['state'] = 'uncertain' if event['state'] in ('sending', 'written') else 'failed'
            event['message'] = '同步未核实，本地记录保留；不会盲目重发'
        write_state(folder, state)
        return {'ok': True, 'event': public_event(event)}


def reconcile_event(event):
    rows = audit_records(event['customer_id'])
    matches = [r for r in rows if r['id'] not in event.get('baseline_audit_ids', []) and r.get('action') == 'CUSTOMER_FOLLOW_UP_CREATED' and str(r.get('actorId')) == event['user_id'] and any(c.get('field') == '跟进类型' and c.get('after') == TYPES[event['type']] for c in r.get('changes', []))]
    if len(matches) != 1:
        accepted = event['state'] == 'written'
        event['state'] = 'written' if accepted else 'uncertain'
        event['message'] = ('CRM 已接受请求，但独立回执尚未唯一匹配' if accepted else '写入结果尚未唯一核实') + '；不重复提交'
        return
    row = matches[0]
    changes = {c['field']: c.get('after') for c in row.get('changes', [])}
    customer = customer_detail(event['customer_id'])['customer']
    event.update(state='confirmed', message='已同步新 K100，并回读操作回执', audit_id=row['id'], verified_at=now(), effective=changes.get('有效跟进') == '是', protection_refreshed=changes.get('刷新保护计时') == '是', last_valid_followup_at=customer.get('lastValidFollowUpAt'), release_at=customer.get('k100PoolReleaseAt'))
    # Audit readback proves the operation/type, not a complete remote content echo.
    event['content_readback'] = False
    if event['type'] in NON_EFFECTIVE and (event['effective'] or event['protection_refreshed']):
        event.update(state='uncertain', message='普通备注被系统计为有效跟进，需人工核对；已停止重试')


def reconcile(root, event_id):
    with locked(root) as folder:
        state = read_state(folder)
        event = state['events'].get(event_id)
        if not event:
            raise SyncError('同步记录不存在')
        if event['state'] not in ('written', 'uncertain', 'sending'):
            return {'ok': True, 'event': public_event(event)}
        if identity() != event.get('user_id'):
            raise SyncError('登录身份与原写入不一致')
        reconcile_event(event)
        write_state(folder, state)
        return {'ok': True, 'event': public_event(event)}


def save_round(payload, knowledge_root, root):
    """Use the existing revisioned record as durable source; queue only new feedback."""
    import project_rounds
    metadata = payload.get('k100')
    content = payload.get('feedback') or payload.get('facts', '')
    # Never reuse the previous revision's effective type or occurrence time.
    payload = {**payload, 'k100_type': '', 'k100_occurred_at': ''}
    if metadata is None and content:
        with locked(root) as folder:
            link = read_state(folder)['links'].get(payload.get('project_id'))
        if link and link.get('enabled'):
            metadata = {'type': 'GENERAL_NOTE', 'occurredAt': now()}
    if metadata is not None and content:
        kind, _, occurred = validate_progress({**metadata, 'content': content})
        payload.update(k100_type=kind, k100_occurred_at=occurred)
    result = project_rounds.save_round(payload, knowledge_root, root)
    result['k100'] = sync_round(root, result, knowledge_root)
    return result


def sync_round(root, stored, knowledge_root=None):
    record = stored.get('record') or {}
    if not record.get('k100_type'):
        return None
    content = record.get('feedback') or record.get('facts', '')
    previous = stored['history'][-2]['record'] if len(stored['history']) > 1 else {}
    if content == (previous.get('feedback') or previous.get('facts', '')):
        return {'state': 'unchanged', 'message': '正文没有新变化，未重复写入 CRM'}
    try:
        result = progress(root, {'project_id': stored['project_id'], 'source_id': 'round-' + stored['project_id'] + '-' + str(stored['revision']), 'content': content, 'type': record['k100_type'], 'occurredAt': record['k100_occurred_at']}, knowledge_root)
        return result['event']
    except SyncError as exc:
        return {'state': exc.kind, 'message': str(exc)}
    except Exception:
        return {'state': 'failed', 'message': '本地进展已保存，同步暂未完成；可恢复本版本同步'}



def local_summary(root):
    """Read only saved mappings/receipts; no credential access or remote requests."""
    with locked(root) as folder:
        state = read_state(folder)
    projects = {}
    for pid, link in state['links'].items():
        projects[pid] = {'link': link, 'event': None}
    for event in sorted(state['events'].values(), key=lambda e: e['created_at']):
        if event.get('project_id'):
            projects.setdefault(event['project_id'], {'link': None})['event'] = public_event(event)
    return {'ok': True, 'projects': projects}


def progress_receipt(root, project_id, record_id):
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'k100:{project_id}:progress-{record_id}'))
    with locked(root) as folder:
        state = read_state(folder)
    event = state['events'].get(event_id)
    if event:
        return public_event(event)
    linked = state['links'].get(project_id, {}).get('enabled')
    return {'state': 'not_sent' if linked else 'needs_link',
            'message': '本条尚未同步，可恢复发送' if linked else '未关联 K100，原话已在工作台保存'}


def save_workbench_progress(payload, knowledge_root, root):
    """One durable local progress record feeds the existing K100 outbox.
    Default body-only saves are notes, never inferred effective customer contact.
    A replay keeps its original time/type even after a crash or lost response.
    """
    import project_analysis
    pid, rid = payload.get('project_id'), payload.get('request_id')
    metadata = payload.get('k100')
    if metadata is not None:
        validate_progress({**metadata, 'content': payload.get('text', '')})
    # Persist metadata with the original source, not in another parallel journal.
    saved = project_analysis.save_progress(payload, knowledge_root, root)
    row = next(x for x in project_analysis.read_cache(root, pid)['requests'] if x['request_id'] == rid)
    original = row.get('k100') or {'type': 'GENERAL_NOTE', 'occurredAt': row['submitted_at']}
    try:
        saved['k100'] = progress(root, {'project_id': pid, 'source_id': 'progress-' + rid,
                                      'content': saved['text'], **original}, knowledge_root)['event']
    except SyncError as exc:
        saved['k100'] = {'state': exc.kind, 'message': str(exc)}
    except Exception:
        saved['k100'] = {'state': 'failed', 'message': '本地已保存，同步暂未核实；可恢复本条记录'}
    return saved


def recover_progress(root, body, knowledge_root):
    import project_analysis
    pid, rid = valid_id(body.get('project_id')), valid_id(body.get('record_id'))
    row = next((x for x in project_analysis.read_cache(root, pid).get('requests', [])
                if x.get('kind') == 'progress' and x.get('request_id') == rid), None)
    if not row:
        raise SyncError('未找到原进展记录')
    from project_archive import state as archive_state
    if archive_state(root, pid)['archived']:
        raise SyncError('项目已归档，未发送进展', 'blocked')
    return progress(root, {'project_id': pid, 'source_id': 'progress-' + rid,
                          'content': row['correction'], **(row.get('k100') or
                          {'type': 'GENERAL_NOTE', 'occurredAt': row['submitted_at']})}, knowledge_root)


def handle(handler, root, knowledge_root=None):
    path = urlparse(handler.path).path
    if not path.startswith('/api/k100/'):
        return False
    if not handler._trusted_origin():
        handler._send_json({'error': 'origin not allowed'}, status=403)
        return True
    try:
        if handler.command == 'GET' and path == '/api/k100/business-summary':
            from k100_metrics import business_summary
            query = parse_qs(urlparse(handler.path).query)
            value = business_summary(query.get('period',['QUARTER'])[0], query.get('date',[None])[0])
        elif handler.command == 'GET' and path == '/api/k100/summary':
            value = local_summary(root)
        elif handler.command == 'GET' and path == '/api/k100/identity-audit':
            value = identity_audit(root, knowledge_root)
        elif handler.command == 'POST' and path == '/api/k100/link-verified':
            value = link_verified(root, handler._read_json_body().get('project_id'), knowledge_root)
        elif handler.command == 'POST' and path == '/api/k100/recover-progress':
            value = recover_progress(root, handler._read_json_body(), knowledge_root)
        elif handler.command == 'GET' and path == '/api/k100/status':
            value = status(root, parse_qs(urlparse(handler.path).query).get('project_id', [''])[0])
        elif handler.command == 'GET' and path == '/api/k100/customers':
            value = customers()
        elif handler.command == 'POST' and path == '/api/k100/connect':
            value = configure(handler._read_json_body().get('credential'))
        elif handler.command == 'POST' and path == '/api/k100/link':
            body = handler._read_json_body()
            value = link_project(root, body.get('project_id'), body.get('customer_id'), knowledge_root)
        elif handler.command == 'POST' and path == '/api/k100/progress':
            value = progress(root, handler._read_json_body(), knowledge_root)
        elif handler.command == 'POST' and path == '/api/k100/recover-round':
            import project_rounds
            stored = project_rounds.read_round(handler._read_json_body().get('project_id'), knowledge_root, root)
            value = {'ok': True, 'event': sync_round(root, stored, knowledge_root)}
        elif handler.command == 'POST' and path == '/api/k100/reconcile':
            value = reconcile(root, handler._read_json_body().get('id'))
        elif handler.command == 'POST' and path == '/api/k100/retry':
            value = deliver(root, handler._read_json_body().get('id'), knowledge_root)
        else:
            handler._send_json({'error': 'not found'}, status=404)
            return True
        handler._send_json(value)
    except SyncError as exc:
        handler._send_json({'ok': False, 'error': str(exc), 'state': exc.kind}, status=409)
    except Exception:
        handler._send_json({'ok': False, 'error': '新 K100 操作未完成，本地内容保留'}, status=503)
    return True
