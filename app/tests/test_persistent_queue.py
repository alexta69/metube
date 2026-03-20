"""Integration tests for ``PersistentQueue`` (shelve-backed storage)."""

from __future__ import annotations

import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
