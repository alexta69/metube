"""Integration tests for ``PersistentQueue`` using the JSON state store."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import shelve
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

fake_yt_dlp = types.ModuleType("yt_dlp")
fake_networking = types.ModuleType("yt_dlp.networking")
fake_impersonate = types.ModuleType("yt_dlp.networking.impersonate")
fake_utils = types.ModuleType("yt_dlp.utils")


class _ImpersonateTarget:
    @staticmethod
    def from_str(value):
        return value


fake_impersonate.ImpersonateTarget = _ImpersonateTarget
fake_networking.impersonate = fake_impersonate
fake_utils.STR_FORMAT_RE_TMPL = r"(?P<prefix>)%\((?P<has_key>{})\)(?P<format>[-0-9.]*{})"
fake_utils.STR_FORMAT_TYPES = "diouxXeEfFgGcrsa"
fake_yt_dlp.networking = fake_networking
fake_yt_dlp.utils = fake_utils
sys.modules.setdefault("yt_dlp", fake_yt_dlp)
sys.modules.setdefault("yt_dlp.networking", fake_networking)
sys.modules.setdefault("yt_dlp.networking.impersonate", fake_impersonate)
sys.modules.setdefault("yt_dlp.utils", fake_utils)

from ytdl import DownloadInfo, PersistentQueue


class _FakeDownload:
    __slots__ = ("info",)

    def __init__(self, info: DownloadInfo):
        self.info = info


def _make_info(url: str = "https://example.com/v") -> DownloadInfo:
    return DownloadInfo(
        id="id1",
        title="Title",
        url=url,
        quality="best",
        download_type="video",
        codec="auto",
        format="any",
        folder="",
        custom_name_prefix="",
        error=None,
        entry=None,
        playlist_item_limit=0,
        split_by_chapters=False,
        chapter_template="",
    )


def _create_legacy_shelf(path: str, *infos: DownloadInfo) -> None:
    with shelve.open(path, "c") as shelf:
        for info in infos:
            shelf[info.url] = info


class PersistentQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_put_get_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            dl = _FakeDownload(_make_info("http://a.example"))
            await pq.put(dl)
            self.assertTrue(os.path.exists(path + ".json"))
            self.assertTrue(pq.exists("http://a.example"))
            self.assertFalse(pq.empty())
            got = pq.get("http://a.example")
            self.assertEqual(got.info.url, "http://a.example")
            await pq.delete("http://a.example")
            self.assertFalse(pq.exists("http://a.example"))

    async def test_saved_items_sorted_by_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            a = _FakeDownload(_make_info("http://first.example"))
            b = _FakeDownload(_make_info("http://second.example"))
            a.info.timestamp = 100
            b.info.timestamp = 200
            await pq.put(a)
            await pq.put(b)
            keys = [k for k, _ in pq.saved_items()]
            self.assertEqual(keys, ["http://first.example", "http://second.example"])

    async def test_load_restores_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq1 = PersistentQueue("queue", path)
            await pq1.put(_FakeDownload(_make_info("http://load.example")))
            pq2 = PersistentQueue("queue", path)
            pq2.load()
            self.assertTrue(pq2.exists("http://load.example"))

    def test_load_imports_legacy_shelve(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            _create_legacy_shelf(path, _make_info("http://legacy.example"))
            pq = PersistentQueue("queue", path)
            pq.load()
            self.assertTrue(pq.exists("http://legacy.example"))
            self.assertTrue(os.path.exists(path + ".json"))

    async def test_queue_persists_only_compact_entry_subset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            info = _make_info("http://entry.example")
            info.entry = {
                "playlist_index": "01",
                "playlist_title": "Playlist",
                "channel_index": "02",
                "channel_title": "Channel",
                "formats": [{"id": "huge"}],
                "description": "very large payload",
            }
            await pq.put(_FakeDownload(info))

            with open(path + ".json", encoding="utf-8") as f:
                payload = json.load(f)

            record = payload["items"][0]["info"]
            self.assertEqual(
                record["entry"],
                {
                    "playlist_index": "01",
                    "playlist_title": "Playlist",
                    "channel_index": "02",
                    "channel_title": "Channel",
                },
            )
            self.assertNotIn("formats", record["entry"])
            self.assertNotIn("description", record["entry"])

    async def test_completed_queue_persists_only_failed_retry_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "completed")
            pq = PersistentQueue("completed", path)
            info = _make_info("http://done.example")
            info.status = "error"
            info.percent = 88
            info.speed = 123
            info.eta = 9
            info.entry = {
                "playlist_index": "01",
                "playlist_title": "Playlist",
                "formats": [{"id": "huge"}],
            }
            info.filename = "done.mp4"
            await pq.put(_FakeDownload(info))

            with open(path + ".json", encoding="utf-8") as f:
                payload = json.load(f)

            record = payload["items"][0]["info"]
            self.assertEqual(
                record["entry"],
                {
                    "playlist_index": "01",
                    "playlist_title": "Playlist",
                },
            )
            self.assertNotIn("percent", record)
            self.assertNotIn("speed", record)
            self.assertNotIn("eta", record)
            self.assertEqual(record["filename"], "done.mp4")

            info.status = "finished"
            await pq.put(_FakeDownload(info))
            with open(path + ".json", encoding="utf-8") as f:
                payload = json.load(f)
            self.assertNotIn("entry", payload["items"][0]["info"])

    def test_invalid_json_is_quarantined_and_legacy_is_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            _create_legacy_shelf(path, _make_info("http://legacy.example"))
            with open(path + ".json", "w", encoding="utf-8") as f:
                f.write("{not valid json")

            pq = PersistentQueue("queue", path)
            pq.load()

            self.assertTrue(pq.exists("http://legacy.example"))
            self.assertTrue(
                any(name.startswith("queue.json.invalid.") for name in os.listdir(tmp))
            )

    def test_loading_old_json_rewrites_to_compact_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            with open(path + ".json", "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "schema_version": 1,
                        "kind": "persistent_queue:queue",
                        "items": [
                            {
                                "key": "http://legacy-json.example",
                                "info": {
                                    "id": "id1",
                                    "title": "Title",
                                    "url": "http://legacy-json.example",
                                    "quality": "best",
                                    "download_type": "video",
                                    "codec": "auto",
                                    "format": "any",
                                    "folder": "",
                                    "custom_name_prefix": "",
                                    "playlist_item_limit": 0,
                                    "split_by_chapters": False,
                                    "chapter_template": "",
                                    "subtitle_language": "en",
                                    "subtitle_mode": "prefer_manual",
                                    "status": "pending",
                                    "timestamp": 1,
                                    "entry": {
                                        "playlist_index": "01",
                                        "playlist_title": "Playlist",
                                        "formats": [{"id": "huge"}],
                                    },
                                    "percent": 15,
                                    "speed": 20,
                                    "eta": 30,
                                },
                            }
                        ],
                    },
                    f,
                )

            pq = PersistentQueue("queue", path)
            pq.load()

            with open(path + ".json", encoding="utf-8") as f:
                payload = json.load(f)

            record = payload["items"][0]["info"]
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(record["entry"], {"playlist_index": "01", "playlist_title": "Playlist"})
            self.assertNotIn("percent", record)
            self.assertNotIn("speed", record)
            self.assertNotIn("eta", record)

    async def test_put_rollbacks_in_memory_queue_when_state_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            dl = _FakeDownload(_make_info("http://rollback.example"))
            self.assertFalse(pq.exists("http://rollback.example"))

            orig_save = __import__("state_store").AtomicJsonStore.save

            def bad_save(store, data):
                if store.path == path + ".json":
                    raise OSError("simulated shelf failure")
                return orig_save(store, data)

            with patch("ytdl.AtomicJsonStore.save", bad_save):
                with self.assertRaises(OSError):
                    await pq.put(dl)

            self.assertFalse(pq.exists("http://rollback.example"))

    async def test_put_rollbacks_to_previous_download_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            first = _FakeDownload(_make_info("http://same.example"))
            second = _FakeDownload(_make_info("http://same.example"))
            second.info.title = "Replaced title"
            await pq.put(first)

            orig_save = __import__("state_store").AtomicJsonStore.save

            def bad_save(store, data):
                if store.path == path + ".json":
                    raise OSError("simulated shelf failure")
                return orig_save(store, data)

            with patch("ytdl.AtomicJsonStore.save", bad_save):
                with self.assertRaises(OSError):
                    await pq.put(second)

            self.assertEqual(pq.get("http://same.example").info.title, "Title")


class StateWriteOffEventLoopTests(unittest.IsolatedAsyncioTestCase):
    """State writes fsync twice; on a slow disk that must not stall the loop.

    Before this, put()/delete() wrote inline, so a queue mutation blocked every
    other request the server was serving for as long as the filesystem took.
    See issue #980.
    """

    async def test_save_runs_off_the_event_loop_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            pq = PersistentQueue("queue", os.path.join(tmp, "queue"))
            self.addCleanup(pq.close)
            loop_thread = threading.get_ident()
            save_threads = []

            orig_save = __import__("state_store").AtomicJsonStore.save

            def recording_save(store, data):
                save_threads.append(threading.get_ident())
                return orig_save(store, data)

            with patch("ytdl.AtomicJsonStore.save", recording_save):
                await pq.put(_FakeDownload(_make_info("http://a.example")))

            self.assertEqual(len(save_threads), 1)
            self.assertNotEqual(save_threads[0], loop_thread)

    async def test_a_slow_write_does_not_stall_other_coroutines(self):
        with tempfile.TemporaryDirectory() as tmp:
            pq = PersistentQueue("queue", os.path.join(tmp, "queue"))
            self.addCleanup(pq.close)
            orig_save = __import__("state_store").AtomicJsonStore.save

            def slow_save(store, data):
                time.sleep(0.3)
                return orig_save(store, data)

            ticks = 0

            async def ticker():
                nonlocal ticks
                while True:
                    await asyncio.sleep(0.01)
                    ticks += 1

            ticking = asyncio.create_task(ticker())
            try:
                with patch("ytdl.AtomicJsonStore.save", slow_save):
                    await pq.put(_FakeDownload(_make_info("http://a.example")))
            finally:
                ticking.cancel()

            # An inline write would have starved the loop for the whole 0.3s and
            # left ticks at 0.
            self.assertGreater(ticks, 5)
            self.assertTrue(pq.exists("http://a.example"))


if __name__ == "__main__":
    unittest.main()
