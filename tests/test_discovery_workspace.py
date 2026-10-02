import tempfile
import unittest
from pathlib import Path
from discovery_workspace import save_note, load_notes
from discovery_handoff import signature


class DiscoveryTest(unittest.TestCase):
    def test_evidence_required_and_revision_conflict_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            leads = [{"id": "fixture", "company": "测试主体"}]
            payload = {"kind": "lead", "source_id": "fixture", "revision": 0, "entity_version": signature(leads[0]), "owner_scope": "mine", "protection": "none", "demand": "unknown"}
            with self.assertRaises(ValueError):
                save_note(payload, root, leads, [])
            payload.update(checked_at="2026-09-01", ownership_evidence="测试查询依据")
            with self.assertRaises(ValueError):
                save_note({**payload, "demand": "confirmed"}, root, leads, [])
            result = save_note(payload, root, leads, [])
            self.assertEqual(result["revision"], 1)
            self.assertEqual(load_notes(root)["items"]["lead:fixture"]["demand"], "unknown")
            with self.assertRaises(ValueError):
                save_note(payload, root, leads, [])
            self.assertEqual(load_notes(root)["revision"], 1)
