"""Anonymous AIHOT reader. No customer data, model calls or business-state writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode

BASE = 'https://aihot.news/api/v1/'
CATEGORIES = {'', 'ai-models', 'ai-products', 'industry', 'paper', 'tip'}
_LOCK = threading.RLock()


class FeedError(Exception):
    def __init__(self, message, *, status=503, retry_after=0, code='unavailable'):
        super().__init__(message)
        self.status, self.retry_after, self.code = status, retry_after, code


def endpoint(params):
    """Only fixed, documented read endpoints; never accept a caller-supplied URL."""
    view = params.get('view', 'selected')
    if view == 'resets':
        return 'codex-resets'
    if view == 'hot':
        return 'hot-topics'
    if view == 'daily':
        date = params.get('date', '')
        if date and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            raise ValueError('日报日期格式不正确')
        return 'dailies/' + date if date else 'dailies?limit=7'
    if view != 'selected':
        raise ValueError('资讯类型不正确')
    window, category, query = params.get('window', '24h'), params.get('category', ''), params.get('q', '').strip()
    if window not in {'24h', '7d'} or category not in CATEGORIES:
        raise ValueError('时间范围或分类不正确')
    if query and not 2 <= len(query) <= 200:
        raise ValueError('关键词请填写 2—200 个字')
    mode = params.get('mode', 'selected')
    if mode not in {'selected', 'all'} or (mode == 'all' and not query):
        raise ValueError('仅关键词补查使用全部公开动态')
    values = {'mode': mode, 'window': window, 'limit': 12}
    if category:
        values['category'] = category
    if query:
        values['q'] = query
    cursor = params.get('cursor', '')
    if cursor:
        if len(cursor) > 4096:
            raise ValueError('翻页标记不正确')
        values['cursor'] = cursor
    return 'items?' + urlencode(values)


def retry_delay(value):
    try:
        return max(1, min(86400, int(value)))
    except (ValueError, TypeError):
        try:
            return max(1, min(86400, int(parsedate_to_datetime(value).timestamp() - time.time())))
        except (ValueError, TypeError, OverflowError):
            return 60


def fetch_public(path, etag=''):
    curl = '/usr/bin/curl' if Path('/usr/bin/curl').exists() else shutil.which('curl')
    if not curl:
        raise FeedError('本机资讯读取工具暂不可用')
    with tempfile.TemporaryDirectory(prefix='aihot-') as tmp:
        headers, body = Path(tmp) / 'headers', Path(tmp) / 'body'
        command = [curl, '--silent', '--show-error', '--compressed', '--proto', '=https',
                   '--connect-timeout', '8', '--max-time', '20', '--max-filesize', '4000000',
                   '--user-agent', 'pdx-workbench-aihot/1.0 (+https://aihot.news/aihot-skill/)',
                   '--header', 'Accept: application/json', '--dump-header', str(headers),
                   '--output', str(body), '--write-out', '%{http_code}']
        if etag and '\r' not in etag and '\n' not in etag:
            command += ['--header', 'If-None-Match: ' + etag]
        try:
            result = subprocess.run(command + [BASE + path], capture_output=True, text=True, timeout=23)
        except subprocess.TimeoutExpired:
            raise FeedError('AI Hot 连接超时，请稍后刷新') from None
        if result.returncode:
            raise FeedError('AI Hot 暂时无法连接，请稍后刷新')
        status = int(result.stdout[-3:]) if result.stdout[-3:].isdigit() else 503
        meta = {}
        for line in headers.read_text(errors='replace').splitlines():
            if line.startswith('HTTP/'):
                meta = {}
            elif ':' in line:
                key, value = line.split(':', 1)
                meta[key.lower()] = value.strip()
        if status == 304:
            return None, meta.get('etag', etag)
        try:
            data = json.loads(body.read_text())
        except (ValueError, OSError):
            raise FeedError('AI Hot 返回了无法读取的内容') from None
        if status != 200:
            code = data.get('code', 'unavailable') if isinstance(data, dict) else 'unavailable'
            messages = {'invalid_cursor': '列表已变化，请从头刷新后继续阅读',
                        'rate_limited': 'AI Hot 请求较多，请稍后再试'}
            raise FeedError(messages.get(code, '该日期尚无日报' if status == 404 else 'AI Hot 暂不可用，请稍后刷新'),
                            status=status, code=code,
                            retry_after=retry_delay(meta.get('retry-after')) if status == 429 else 0)
        if not isinstance(data, dict) or data.get('schemaVersion') != 1:
            raise FeedError('AI Hot 内容格式已变化，暂时保留上次内容')
        if path == 'codex-resets':
            if not isinstance(data.get('events'), list) or not data.get('checkedAt'):
                raise FeedError('重置监控内容不完整')
        elif path.startswith('dailies/'):
            if not isinstance(data.get('report'), dict):
                raise FeedError('日报内容不完整')
        elif not isinstance(data.get('items'), list):
            raise FeedError('资讯列表不完整')
        return data, meta.get('etag', '')


class Client:
    def __init__(self, root, transport=fetch_public, clock=time.time):
        self.root, self.transport, self.clock = Path(root), transport, clock

    def _load(self, file):
        try:
            data = json.loads(file.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, file, data):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = file.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False))
        temporary.replace(file)

    def get(self, path, force=False):
        # A lock coalesces simultaneous refreshes and also protects atomic cache replacement.
        with _LOCK:
            file = self.root / (hashlib.sha256(path.encode()).hexdigest() + '.json')
            cached, now = self._load(file), self.clock()
            data = cached.get('data')
            checked = cached.get('checked_epoch', 0)
            error = ''
            cooldown = self._load(self.root / 'cooldown.json').get('until', 0)
            if cooldown > now:
                error = 'AI Hot 请求较多，请稍后再试'
            elif data is not None and now - checked < (60 if force and path != 'codex-resets' else 300):
                error = cached.get('error', '')
            elif now < cached.get('retry_at', 0):
                error = cached.get('error', 'AI Hot 暂不可用')
            else:
                try:
                    fresh, etag = self.transport(path, cached.get('etag', ''))
                    if fresh is None and data is None:
                        raise FeedError('本地缓存不可用，请稍后刷新')
                    if fresh is not None:
                        data = fresh
                        cached['fetched_at'] = datetime.fromtimestamp(now, timezone.utc).isoformat()
                    cached.update(data=data, etag=etag, checked_epoch=now, error='', retry_at=0)
                    self._save(file, cached)
                except FeedError as exc:
                    error = str(exc)
                    # A rate limit is global, not just per search; never fan out to evade it.
                    if exc.retry_after:
                        self._save(self.root / 'cooldown.json', {'until': now + exc.retry_after})
                    if data is None:
                        raise
                    cached.update(error=error, retry_at=now + max(exc.retry_after, 60))
                    self._save(file, cached)
            if data is None:
                raise FeedError(error or '暂时没有可用资讯')
            return {'data': data, 'fetched_at': cached.get('fetched_at'),
                    'checked_at': datetime.fromtimestamp(cached.get('checked_epoch', 0), timezone.utc).isoformat(),
                    'stale': bool(error), 'error': error}

    def read(self, params):
        force = params.get('refresh') == '1'
        path = endpoint(params)
        result = self.get(path, force)
        if params.get('view') == 'daily' and not params.get('date'):
            index = result
            entries = index['data']['items']
            if entries:
                actual_date = str(entries[0].get('date', ''))
                result = self.get(endpoint({'view': 'daily', 'date': actual_date}), force)
                result['stale'] = result['stale'] or index['stale']
                result['error'] = result['error'] or index['error']
            result['dates'] = [x.get('date') for x in entries if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(x.get('date', '')))]
        # Only keyword searches may widen to the unselected public pool, visibly marked.
        fallback = params.get('mode') == 'all'
        if (params.get('q', '').strip() and not params.get('cursor') and not result['data'].get('items')
                and params.get('view', 'selected') == 'selected' and not result['stale'] and not fallback):
            result = self.get(endpoint({**params, 'mode': 'all'}), force)
            fallback = True
        return {'ok': True, **result, 'unselected_search': fallback}


def read(params, state_root):
    return Client(Path(state_root) / 'aihot').read(params)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='读取 AIHOT 公开资讯；不调用大模型')
    parser.add_argument('--view', choices=['selected', 'hot', 'daily', 'resets'], default='selected')
    parser.add_argument('--window', choices=['24h', '7d'], default='24h')
    parser.add_argument('--category', choices=sorted(CATEGORIES), default='')
    parser.add_argument('--q', default='')
    parser.add_argument('--date', default='')
    parser.add_argument('--cursor', default='')
    parser.add_argument('--mode', choices=['selected', 'all'], default='selected')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--cache-dir', default=str(Path.home() / '.cache' / 'pdx-aihot'))
    args = vars(parser.parse_args())
    cache = args.pop('cache_dir')
    args['refresh'] = '1' if args['refresh'] else '0'
    try:
        print(json.dumps(Client(cache).read(args), ensure_ascii=False))
    except (ValueError, FeedError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
