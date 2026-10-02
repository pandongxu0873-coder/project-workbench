"""Shared local API error and timestamp primitives."""
from datetime import datetime, timezone
class LocalError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status=status
def now():
    return datetime.now(timezone.utc).isoformat()
