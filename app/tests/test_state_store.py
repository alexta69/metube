from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

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

    def test_save_falls_back_to_direct_write_when_mkstemp_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")

            with self.assertLogs("state_store", level="WARNING") as logs:
                with patch(
                    "state_store.tempfile.mkstemp",
                    side_effect=PermissionError(1, "Operation not permitted"),
                ):
                    store.save({"items": [{"key": "a"}]})

            self.assertTrue(os.path.exists(path))
            self.assertTrue(any(path in message for message in logs.output))
            payload = store.load()
            self.assertEqual(payload["items"], [{"key": "a"}])

    def test_save_falls_back_to_direct_write_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")

            with patch(
                "state_store.os.replace",
                side_effect=PermissionError(1, "Operation not permitted"),
            ):
                store.save({"items": [{"key": "a"}]})

            self.assertTrue(os.path.exists(path))
            payload = store.load()
            self.assertEqual(payload["items"], [{"key": "a"}])
            self.assertEqual([], [name for name in os.listdir(tmp) if name.endswith(".tmp")])

    def test_save_reraises_when_atomic_and_direct_write_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")

            with patch(
                "state_store.tempfile.mkstemp",
                side_effect=PermissionError(1, "Operation not permitted"),
            ):
                with patch("builtins.open", side_effect=PermissionError(13, "Permission denied")):
                    with self.assertRaises(PermissionError) as ctx:
                        store.save({"items": [{"key": "a"}]})

            self.assertEqual(ctx.exception.errno, 13)
            self.assertFalse(os.path.exists(path))

    def test_save_reraises_and_preserves_state_on_non_atomic_errno(self):
        # A storage failure such as ENOSPC is not an "atomic unavailable"
        # signal, so it must surface instead of falling back to a direct write
        # that would truncate the existing good state file.
        import errno as _errno

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")
            store.save({"items": [{"key": "good"}]})

            with patch(
                "state_store.tempfile.mkstemp",
                side_effect=OSError(_errno.ENOSPC, "No space left on device"),
            ):
                with self.assertRaises(OSError) as ctx:
                    store.save({"items": [{"key": "new"}]})

            self.assertEqual(ctx.exception.errno, _errno.ENOSPC)
            # Existing state is untouched.
            self.assertEqual(store.load()["items"], [{"key": "good"}])

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
