"""Read-only calendar attribution from exact event IDs in cited project evidence."""
import re
from pathlib import Path


def link_project_calendar_items(items, projects, knowledge_root):
    root = Path(knowledge_root).resolve()
    links = {}
    for project in projects:
        customer = project.get('customer', '')
        if not customer or customer == '客户关联待核实':
            continue
        for source in project.get('sources', []):
            if source.get('relation') != 'explicit_evidence' or not source.get('readable'):
                continue
            path = (root / source['path']).resolve()
            if root not in path.parents or not path.is_file():
                continue
            try:
                body = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                continue
            for event_id in re.findall(r'^\s*-?\s*事件\s*ID\s*[:：]\s*([A-Za-z0-9_-]+)\s*$', body, re.M):
                links.setdefault(event_id, {})[project['id']] = project
    result = []
    for original in items:
        item = dict(original)
        event_id = (item.get('calendar') or {}).get('event_id', '')
        candidates = links.get(event_id, {})
        if item.get('source_type') == 'feishu_calendar' and len(candidates) == 1:
            project = next(iter(candidates.values()))
            # Existing customer attribution wins on disagreement. Never invent an account ID.
            if not item.get('matched_customer') or item.get('customer') == project['customer']:
                item.update(customer=project['customer'], matched_customer=True,
                            project_id=project['id'], projectLine=project['title'],
                            project_source_path=project['source_path'],
                            customer_match_source='explicit_project_calendar_evidence')
        result.append(item)
    return result
