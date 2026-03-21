"""Integration tests for ``PersistentQueue`` (shelve-backed storage)."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

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


class PersistentQueueTests(unittest.TestCase):
    def test_put_get_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            dl = _FakeDownload(_make_info("http://a.example"))
            pq.put(dl)
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

    def test_load_restores_from_shelve(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq1 = PersistentQueue("queue", path)
            pq1.put(_FakeDownload(_make_info("http://load.example")))
            pq2 = PersistentQueue("queue", path)
            pq2.load()
            self.assertTrue(pq2.exists("http://load.example"))

    def test_put_rollbacks_in_memory_queue_when_shelf_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "queue")
            pq = PersistentQueue("queue", path)
            dl = _FakeDownload(_make_info("http://rollback.example"))
            self.assertFalse(pq.exists("http://rollback.example"))

            orig_open = __import__("shelve").open

            def bad_open(filename, flag="c", *args, **kwargs):
                if flag == "w":
                    raise OSError("simulated shelf failure")
                return orig_open(filename, flag, *args, **kwargs)

            with patch("ytdl.shelve.open", bad_open):
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

            orig_open = __import__("shelve").open

            def bad_open(filename, flag="c", *args, **kwargs):
                if flag == "w":
                    raise OSError("simulated shelf failure")
                return orig_open(filename, flag, *args, **kwargs)

            with patch("ytdl.shelve.open", bad_open):
                with self.assertRaises(OSError):
                    pq.put(second)

            self.assertEqual(pq.get("http://same.example").info.title, "Title")


if __name__ == "__main__":
    unittest.main()
