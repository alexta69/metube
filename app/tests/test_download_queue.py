"""Tests for ``DownloadQueue`` with mocked yt-dlp extraction."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ytdl import DownloadQueue


@pytest.fixture
def dq_env():
    with tempfile.TemporaryDirectory() as tmp:
        dl = os.path.join(tmp, "downloads")
        st = os.path.join(tmp, "state")
        os.makedirs(dl, exist_ok=True)
        os.makedirs(st, exist_ok=True)
        cfg = MagicMock()
        cfg.STATE_DIR = st
        cfg.DOWNLOAD_DIR = dl
        cfg.AUDIO_DOWNLOAD_DIR = dl
        cfg.TEMP_DIR = dl
        cfg.MAX_CONCURRENT_DOWNLOADS = "3"
        cfg.YTDL_OPTIONS = {}
        cfg.CUSTOM_DIRS = True
        cfg.CREATE_CUSTOM_DIRS = True
        cfg.CLEAR_COMPLETED_AFTER = "0"
        cfg.DELETE_FILE_ON_TRASHCAN = False
        cfg.OUTPUT_TEMPLATE = "%(title)s.%(ext)s"
        cfg.OUTPUT_TEMPLATE_CHAPTER = "%(title)s.%(ext)s"
        cfg.OUTPUT_TEMPLATE_PLAYLIST = ""
        cfg.OUTPUT_TEMPLATE_CHANNEL = ""
        yield cfg


def test_cancel_add_increments_generation(dq_env):
    notifier = MagicMock()
    dq = DownloadQueue(dq_env, notifier)
    before = dq._add_generation
    dq.cancel_add()
    assert dq._add_generation == before + 1


def test_get_returns_tuple_of_lists(dq_env):
    notifier = MagicMock()
    dq = DownloadQueue(dq_env, notifier)
    q, done = dq.get()
    assert q == [] and done == []


@pytest.mark.asyncio
async def test_add_single_video_goes_to_pending_when_auto_start_false(dq_env):
    notifier = AsyncMock()

    def fake_extract(self, url):
        return {
            "_type": "video",
            "id": "vid1",
            "title": "Test Video",
            "url": url,
            "webpage_url": url,
        }

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_extract):
        result = await dq.add(
            "https://example.com/watch?v=1",
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=False,
        )
    assert result["status"] == "ok"
    assert dq.pending.exists("https://example.com/watch?v=1")


@pytest.mark.asyncio
async def test_cancel_removes_from_pending(dq_env):
    notifier = AsyncMock()

    def fake_extract(self, url):
        return {
            "_type": "video",
            "id": "vid1",
            "title": "Test Video",
            "url": url,
            "webpage_url": url,
        }

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_extract):
        await dq.add(
            "https://example.com/pending",
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=False,
        )
    url = "https://example.com/pending"
    await dq.cancel([url])
    assert not dq.pending.exists(url)
    notifier.canceled.assert_awaited()


@pytest.mark.asyncio
async def test_start_pending_moves_to_queue(dq_env):
    notifier = AsyncMock()

    def fake_extract(self, url):
        return {
            "_type": "video",
            "id": "vid1",
            "title": "Test Video",
            "url": url,
            "webpage_url": url,
        }

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_extract):
        await dq.add(
            "https://example.com/startme",
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=False,
        )
    url = "https://example.com/startme"
    # Starting will spawn real download — cancel immediately before worker runs much
    with patch.object(DownloadQueue, "_DownloadQueue__start_download", AsyncMock()):
        await dq.start_pending([url])
    assert not dq.pending.exists(url)


@pytest.mark.asyncio
async def test_add_entry_queues_single_video_without_reextracting(dq_env):
    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    entry = {
        "_type": "video",
        "id": "vid1",
        "title": "Test Video",
        "url": "https://example.com/watch?v=1",
        "webpage_url": "https://example.com/watch?v=1",
        "playlist_index": "01",
        "playlist_title": "Playlist",
    }

    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", side_effect=AssertionError("should not re-extract")):
        result = await dq.add_entry(
            entry,
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=False,
        )

    assert result["status"] == "ok"
    assert dq.pending.exists("https://example.com/watch?v=1")
