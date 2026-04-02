"""Integration tests for ``PersistentQueue`` using the JSON state store."""

from __future__ import annotations

import json
import os
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


class PersistentQueueTests(unittest.TestCase):
    def test_put_get_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            dl = _FakeDownload(_make_info("http://a.example"))
            pq.put(dl)
            self.assertTrue(os.path.exists(path + ".json"))
            self.assertTrue(pq.exists("http://a.example"))
            self.assertFalse(pq.empty())
            got = pq.get("http://a.example")
            self.assertEqual(got.info.url, "http://a.example")
            pq.delete("http://a.example")
            self.assertFalse(pq.exists("http://a.example"))

    def test_saved_items_sorted_by_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            a = _FakeDownload(_make_info("http://first.example"))
            b = _FakeDownload(_make_info("http://second.example"))
            a.info.timestamp = 100
            b.info.timestamp = 200
            pq.put(a)
            pq.put(b)
            keys = [k for k, _ in pq.saved_items()]
            self.assertEqual(keys, ["http://first.example", "http://second.example"])

    def test_load_restores_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq1 = PersistentQueue("queue", path)
            pq1.put(_FakeDownload(_make_info("http://load.example")))
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

    def test_queue_persists_only_compact_entry_subset(self):
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
            pq.put(_FakeDownload(info))

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

    def test_completed_queue_does_not_persist_entry_or_transient_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "completed")
            pq = PersistentQueue("completed", path)
            info = _make_info("http://done.example")
            info.status = "finished"
            info.percent = 88
            info.speed = 123
            info.eta = 9
            info.entry = {
                "playlist_index": "01",
                "playlist_title": "Playlist",
                "formats": [{"id": "huge"}],
            }
            info.filename = "done.mp4"
            pq.put(_FakeDownload(info))

            with open(path + ".json", encoding="utf-8") as f:
                payload = json.load(f)

            record = payload["items"][0]["info"]
            self.assertNotIn("entry", record)
            self.assertNotIn("percent", record)
            self.assertNotIn("speed", record)
            self.assertNotIn("eta", record)
            self.assertEqual(record["filename"], "done.mp4")

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

    def test_put_rollbacks_in_memory_queue_when_state_write_fails(self):
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
                    pq.put(dl)

            self.assertFalse(pq.exists("http://rollback.example"))

    def test_put_rollbacks_to_previous_download_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            first = _FakeDownload(_make_info("http://same.example"))
            second = _FakeDownload(_make_info("http://same.example"))
            second.info.title = "Replaced title"
            pq.put(first)

            orig_save = __import__("state_store").AtomicJsonStore.save

            def bad_save(store, data):
                if store.path == path + ".json":
                    raise OSError("simulated shelf failure")
                return orig_save(store, data)

            with patch("ytdl.AtomicJsonStore.save", bad_save):
                with self.assertRaises(OSError):
                    pq.put(second)

            self.assertEqual(pq.get("http://same.example").info.title, "Title")


if __name__ == "__main__":
    unittest.main()
