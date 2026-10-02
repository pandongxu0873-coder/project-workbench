"""Historical Linghang records only. This module cannot contact a remote system."""
import json

def status(root):
    path = root / 'ka_sales_snapshot.json'
    snapshot = json.loads(path.read_text()) if path.exists() else None
    return {'ok': True, 'mode': 'historical_read_only', 'retired': True,
            'configured': False, 'snapshot': snapshot,
            'message': '业务平台旧CRM接口已停用；仅保留历史快照，新跟进使用 K100。'}
