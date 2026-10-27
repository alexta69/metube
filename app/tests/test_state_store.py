from __future__ import annotations

import errno
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
            # Fallback keeps owner-only permissions, matching the atomic path.
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            payload = store.load()
            self.assertEqual(payload["items"], [{"key": "a"}])

    def test_fallback_tightens_permissions_on_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{}")
            os.chmod(path, 0o644)

            store = AtomicJsonStore(path, kind="persistent_queue:queue")
            with patch(
                "state_store.tempfile.mkstemp",
                side_effect=PermissionError(1, "Operation not permitted"),
            ):
                store.save({"items": [{"key": "a"}]})

            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(store.load()["items"], [{"key": "a"}])

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
                with patch(
                    "state_store.os.open",
                    side_effect=PermissionError(13, "Permission denied"),
                ):
                    with self.assertRaises(PermissionError) as ctx:
                        store.save({"items": [{"key": "a"}]})

            self.assertEqual(ctx.exception.errno, 13)
            self.assertFalse(os.path.exists(path))

    def test_unsupported_fsync_keeps_atomic_path(self):
        # fsync being unsupported (EINVAL/ENOSYS) must not by itself trigger the
        # direct-write fallback; the atomic temp-file + rename path still runs.
        import errno as _errno

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")

            with patch(
                "state_store.os.fsync",
                side_effect=OSError(_errno.EINVAL, "Invalid argument"),
            ):
                with self.assertNoLogs("state_store", level="WARNING"):
                    store.save({"items": [{"key": "a"}]})

            self.assertEqual(store.load()["items"], [{"key": "a"}])
            self.assertEqual([], [name for name in os.listdir(tmp) if name.endswith(".tmp")])

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

    def test_serialization_failure_preserves_existing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")
            store.save({"items": [{"key": "good"}]})

            # Even on the fallback path, a non-serializable payload must raise
            # before the existing good state file is touched.
            with patch(
                "state_store.tempfile.mkstemp",
                side_effect=PermissionError(1, "Operation not permitted"),
            ):
                with self.assertRaises(TypeError):
                    store.save({"items": object()})

            self.assertEqual(store.load()["items"], [{"key": "good"}])

    def test_save_retries_when_replace_loses_its_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")
            real_replace = os.replace
            temps = []

            def wrapped_replace(src, dst):
                temps.append(src)
                if len(temps) == 1:
                    os.remove(src)
                    raise FileNotFoundError(errno.ENOENT, "No such file or directory", src)
                return real_replace(src, dst)

            data = {"items": [{"key": "a", "info": {"title": "hello", "complete": True}}]}
            with patch("state_store.os.replace", side_effect=wrapped_replace), patch.object(
                AtomicJsonStore, "_direct_write"
            ) as direct:
                store.save(data)

            self.assertEqual(direct.call_count, 0)
            self.assertEqual(len(temps), 2)
            self.assertNotEqual(temps[0], temps[1])
            self.assertEqual({os.path.dirname(temp) for temp in temps}, {tmp})
            self.assertTrue(all(os.path.basename(temp).endswith(".tmp") for temp in temps))
            self.assertEqual([], [name for name in os.listdir(tmp) if name.endswith(".tmp")])
            payload = store.load()
            self.assertEqual(payload["items"], data["items"])
            self.assertEqual(payload["kind"], "persistent_queue:queue")
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_save_propagates_enoent_after_three_missing_temp_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")
            store.save({"items": [{"key": "good"}]})
            with open(path, encoding="utf-8") as handle:
                previous = handle.read()
            attempts = {"replace": 0, "mkstemp": 0}
            real_mkstemp = tempfile.mkstemp

            def counting_mkstemp(*args, **kwargs):
                attempts["mkstemp"] += 1
                return real_mkstemp(*args, **kwargs)

            def lose_temp(src, _dst):
                attempts["replace"] += 1
                os.remove(src)
                raise FileNotFoundError(errno.ENOENT, "No such file or directory", src)

            with patch("state_store.tempfile.mkstemp", side_effect=counting_mkstemp), patch(
                "state_store.os.replace", side_effect=lose_temp
            ), patch.object(AtomicJsonStore, "_direct_write") as direct:
                with self.assertRaises(FileNotFoundError) as ctx:
                    store.save({"items": [{"key": "new"}]})

            self.assertEqual(ctx.exception.errno, errno.ENOENT)
            self.assertEqual(attempts["replace"], 3)
            self.assertEqual(attempts["mkstemp"], 3)
            self.assertEqual(direct.call_count, 0)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), previous)
            self.assertEqual(store.load()["items"], [{"key": "good"}])
            self.assertEqual([], [name for name in os.listdir(tmp) if name.endswith(".tmp")])

    def test_save_does_not_retry_when_replace_parent_is_missing(self):
        real_mkstemp = tempfile.mkstemp
        attempts = {"mkstemp": 0, "replace": 0}

        def counting_mkstemp(*args, **kwargs):
            attempts["mkstemp"] += 1
            return real_mkstemp(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            parent = os.path.join(tmp, "state")
            os.mkdir(parent)
            path = os.path.join(parent, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")

            def drop_parent(src, _dst):
                attempts["replace"] += 1
                os.remove(src)
                os.rmdir(parent)
                raise FileNotFoundError(errno.ENOENT, "No such file or directory", src)

            with patch("state_store.tempfile.mkstemp", side_effect=counting_mkstemp), patch(
                "state_store.os.replace", side_effect=drop_parent
            ), patch("state_store.os.makedirs") as makedirs, patch.object(
                AtomicJsonStore, "_direct_write"
            ) as direct:
                with self.assertRaises(FileNotFoundError) as ctx:
                    store.save({"items": [{"key": "a"}]})

            self.assertEqual(ctx.exception.errno, errno.ENOENT)
            self.assertEqual(attempts["replace"], 1)
            self.assertEqual(attempts["mkstemp"], 1)
            self.assertEqual(makedirs.call_count, 0)
            self.assertEqual(direct.call_count, 0)
            self.assertFalse(os.path.isdir(parent))
            self.assertEqual([], [name for name in os.listdir(tmp) if name.endswith(".tmp")])

    def test_save_does_not_retry_enoent_when_temp_file_still_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue.json")
            store = AtomicJsonStore(path, kind="persistent_queue:queue")
            store.save({"items": [{"key": "good"}]})
            with open(path, encoding="utf-8") as handle:
                previous = handle.read()
            attempts = {"replace": 0, "mkstemp": 0}
            real_mkstemp = tempfile.mkstemp

            def counting_mkstemp(*args, **kwargs):
                attempts["mkstemp"] += 1
                return real_mkstemp(*args, **kwargs)

            def enoent_with_source(src, _dst):
                attempts["replace"] += 1
                self.assertTrue(os.path.exists(src))
                raise FileNotFoundError(errno.ENOENT, "No such file or directory", src)

            with patch("state_store.tempfile.mkstemp", side_effect=counting_mkstemp), patch(
                "state_store.os.replace", side_effect=enoent_with_source
            ), patch.object(AtomicJsonStore, "_direct_write") as direct:
                with self.assertRaises(FileNotFoundError) as ctx:
                    store.save({"items": [{"key": "new"}]})

            self.assertEqual(ctx.exception.errno, errno.ENOENT)
            self.assertEqual(attempts["replace"], 1)
            self.assertEqual(attempts["mkstemp"], 1)
            self.assertEqual(direct.call_count, 0)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), previous)
            self.assertEqual([], [name for name in os.listdir(tmp) if name.endswith(".tmp")])

    def test_other_storage_errors_skip_missing_temp_retry(self):
        # ENOENT from creating the temp, and ENOSPC/EIO from writing, fsync, or
        # replace, stay on the existing error path: one attempt, no direct write.
        real_mkstemp = tempfile.mkstemp
        real_replace = os.replace
        real_fdopen = os.fdopen
        real_fsync = os.fsync
        failures = (
            ("mkstemp", errno.ENOENT),
            ("write", errno.ENOSPC),
            ("write", errno.EIO),
            ("fsync", errno.ENOSPC),
            ("fsync", errno.EIO),
            ("replace", errno.ENOSPC),
            ("replace", errno.EIO),
        )

        for step, err in failures:
            with self.subTest(step=step, errno=err):
                with tempfile.TemporaryDirectory() as tmp:
                    path = os.path.join(tmp, "queue.json")
                    store = AtomicJsonStore(path, kind="persistent_queue:queue")
                    store.save({"items": [{"key": "good"}]})
                    with open(path, encoding="utf-8") as handle:
                        previous = handle.read()
                    attempts = {"mkstemp": 0, "replace": 0}

                    def counting_mkstemp(*args, **kwargs):
                        attempts["mkstemp"] += 1
                        if step == "mkstemp":
                            raise FileNotFoundError(err, os.strerror(err))
                        return real_mkstemp(*args, **kwargs)

                    def counting_replace(src, dst):
                        attempts["replace"] += 1
                        if step == "replace":
                            raise OSError(err, os.strerror(err))
                        return real_replace(src, dst)

                    def counting_fdopen(fd, mode="r", *args, **kwargs):
                        handle = real_fdopen(fd, mode, *args, **kwargs)
                        if step == "write":
                            def boom(_data):
                                raise OSError(err, os.strerror(err))

                            handle.write = boom
                        return handle

                    def counting_fsync(fd):
                        if step == "fsync":
                            raise OSError(err, os.strerror(err))
                        return real_fsync(fd)

                    with patch("state_store.tempfile.mkstemp", side_effect=counting_mkstemp), patch(
                        "state_store.os.replace", side_effect=counting_replace
                    ), patch("state_store.os.fdopen", side_effect=counting_fdopen), patch(
                        "state_store.os.fsync", side_effect=counting_fsync
                    ), patch.object(AtomicJsonStore, "_direct_write") as direct:
                        with self.assertRaises(OSError) as ctx:
                            store.save({"items": [{"key": "new"}]})

                    self.assertEqual(ctx.exception.errno, err)
                    self.assertEqual(direct.call_count, 0)
                    self.assertEqual(attempts["mkstemp"], 1)
                    self.assertEqual(attempts["replace"], 1 if step == "replace" else 0)
                    with open(path, encoding="utf-8") as handle:
                        self.assertEqual(handle.read(), previous)
                    self.assertEqual([], [name for name in os.listdir(tmp) if name.endswith(".tmp")])

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
