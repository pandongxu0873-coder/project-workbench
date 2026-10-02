"""One deployment's finite startup grace; never changes scheduler intervals/settings."""
import json
import math
import threading
import time


def grace_seconds(root, now=None):
    now = time.time() if now is None else now
    try:
        value = float(json.loads((root / 'release_startup_grace.json').read_text())['resume_at'])
        return min(300.0, max(0.0, value-now)) if math.isfinite(value) else 0.0
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


def start_worker(target, args, stop, delay):
    def run():
        if not stop.wait(delay):
            target(*args)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    return worker
