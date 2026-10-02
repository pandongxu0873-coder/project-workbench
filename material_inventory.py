"""Reconcile a successful desktop inventory with indexed material versions.

This is an index join, not a content review, customer match or business task.
"""
import json
import re
from pathlib import Path


def reconcile(state_root, index, receipt):
    unavailable = {'status': 'awaiting_scan'}
    if receipt.get('status') not in ('ok', 'partial', 'unavailable'):
        return unavailable
    try:
        snapshot = json.loads((Path(state_root) / 'desktop_scan_snapshot.json').read_text())
        paths = snapshot['observed_paths']
        # The cache also retains failed/missing files. Only this scan's successful
        # reads may count; never join an older scope or an in-flight receipt.
        retained = receipt['status'] == 'unavailable'
        if ((not retained and snapshot.get('checked_at') != receipt.get('checked_at')) or
                snapshot.get('scope') != receipt.get('scope') or
                snapshot.get('scan_status') not in ('ok', 'partial') or
                not isinstance(paths, list) or len(paths) != snapshot.get('observed_count') or
                (not retained and len(paths) != receipt.get('observed'))):
            return unavailable
        groups = {}
        for value in paths:
            if not isinstance(value, str) or not value or Path(value).is_absolute() or '..' in Path(value).parts:
                return unavailable
            item = snapshot['files'][value]
            sha = item['sha256']
            if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{64}', sha):
                return unavailable
            groups.setdefault(sha, set()).add(value)
        if sum(len(values) for values in groups.values()) != len(paths):
            return unavailable
    except (OSError, ValueError, TypeError, KeyError):
        return unavailable

    indexed = {row.get('sha256') for group in ('files', 'recordings')
               for row in index.get(group, []) if isinstance(row.get('sha256'), str)}
    unmatched = [
        {'id': sha, 'title': Path(sorted(values)[0]).name,
         'paths': sorted(values), 'copy_count': len(values)}
        for sha, values in groups.items() if sha not in indexed
    ]
    unmatched.sort(key=lambda row: row['paths'][0])
    return {'status': 'ready', 'checked_at': snapshot['checked_at'],
            'scope': snapshot['scope'], 'partial_scan': snapshot['scan_status'] == 'partial',
            'retained_scan': retained,
            'file_count': len(paths), 'unique_count': len(groups),
            'duplicate_count': len(paths) - len(groups),
            'indexed_count': len(groups) - len(unmatched),
            'unindexed_count': len(unmatched), 'unindexed_files': unmatched}
