from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime

from state_store import AtomicJsonStore, from_json_compatible, to_json_compatible


class StateStoreTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")
            store.save({"items": [{"key": "a", "info": {"title": "hello"}}]})

            payload = store.load()

            self.assertEqual(payload["kind"], "persistent_queue:queue")
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["items"][0]["info"]["title"], "hello")

    def test_invalid_file_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken")

            store = AtomicJsonStore(path, kind="persistent_queue:queue")
            payload = store.load()

            self.assertIsNone(payload)
            self.assertTrue(
                any(name.startswith("queue.json.invalid.") for name in os.listdir(tmp))
            )

    def test_json_compat_helpers_roundtrip_bytes_and_datetime(self):
        raw = {
            "payload": b"abc",
            "timestamp": datetime(2024, 1, 2, 3, 4, 5),
            "items": (1, 2, 3),
        }

        restored = from_json_compatible(to_json_compatible(raw))

        self.assertEqual(restored["payload"], b"abc")
        self.assertEqual(restored["timestamp"], datetime(2024, 1, 2, 3, 4, 5))
        self.assertEqual(restored["items"], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
