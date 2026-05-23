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
        cfg.YTDL_OPTIONS_PRESETS = {}
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

    def fake_extract(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
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

    def fake_extract(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
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
async def test_cancel_before_start_marks_download_canceled(dq_env):
    """Regression test for the race condition where cancel() arrives after the
    download has been placed in the queue and ``__start_download`` has been
    scheduled via ``asyncio.create_task`` but has not yet executed. Without the
    fix, the pending task would run ``download.start()`` despite the user
    cancelling, because its ``download.canceled`` guard was never flipped."""
    notifier = AsyncMock()

    def fake_extract(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
        return {
            "_type": "video",
            "id": "vid1",
            "title": "Test Video",
            "url": url,
            "webpage_url": url,
        }

    dq = DownloadQueue(dq_env, notifier)
    url = "https://example.com/race"
    start_mock = AsyncMock()
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_extract), \
         patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        await dq.add(
            url,
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=True,
        )
        assert dq.queue.exists(url)
        download = dq.queue.get(url)
        assert download.canceled is False
        await dq.cancel([url])
        assert not dq.queue.exists(url)
        assert download.canceled is True
        notifier.canceled.assert_awaited_with(url)


@pytest.mark.asyncio
async def test_start_pending_moves_to_queue(dq_env):
    notifier = AsyncMock()

    def fake_extract(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
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


@pytest.mark.asyncio
async def test_add_merges_global_preset_and_override_options(dq_env):
    notifier = AsyncMock()
    dq_env.YTDL_OPTIONS = {"writesubtitles": False, "cookiefile": "/tmp/global.txt"}
    dq_env.YTDL_OPTIONS_PRESETS = {
        "Preset A": {"writesubtitles": True, "proxy": "http://preset-a"},
        "Preset B": {"writesubtitles": False, "ratelimit": 1000},
    }

    def fake_extract(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
        return {
            "_type": "video",
            "id": "vid2",
            "title": "Preset Video",
            "url": url,
            "webpage_url": url,
        }

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_extract):
        result = await dq.add(
            "https://example.com/preset",
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=False,
            ytdl_options_presets=["Preset A", "Preset B"],
            ytdl_options_overrides={"proxy": "http://override", "embed_thumbnail": True},
        )

    assert result["status"] == "ok"
    queued = dq.pending.get("https://example.com/preset")
    assert queued.ytdl_opts["cookiefile"] == "/tmp/global.txt"
    assert queued.ytdl_opts["writesubtitles"] is False
    assert queued.ytdl_opts["ratelimit"] == 1000
    assert queued.ytdl_opts["proxy"] == "http://override"
    assert queued.ytdl_opts["embed_thumbnail"] is True


@pytest.mark.asyncio
async def test_extract_info_preset_null_download_archive_overrides_global(dq_env):
    """Preset download_archive:null must apply during extract_info (global archive otherwise wins first)."""
    dq_env.YTDL_OPTIONS = {"download_archive": "/tmp/archive.txt"}
    dq_env.YTDL_OPTIONS_PRESETS = {"NoArchive": {"download_archive": None}}

    captured_params: list = []

    class FakeYoutubeDL:
        def __init__(self, params=None):
            captured_params.append(params)

        def extract_info(self, url, download=False):
            return {
                "_type": "video",
                "id": "vid-archive",
                "title": "Archive Test",
                "url": url,
                "webpage_url": url,
            }

    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    with patch("ytdl.yt_dlp.YoutubeDL", FakeYoutubeDL):
        result = await dq.add(
            "https://example.com/archive-test",
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=False,
            ytdl_options_presets=["NoArchive"],
        )

    assert result["status"] == "ok"
    assert len(captured_params) == 1
    extract_params = captured_params[0]
    assert extract_params.get("download_archive") is None
    assert extract_params["extract_flat"] is True
    assert extract_params["noplaylist"] is True


@pytest.mark.asyncio
async def test_extract_info_metube_extract_keys_win_over_preset(dq_env):
    """MeTube's flat-extract settings must not be overridden by presets."""
    dq_env.YTDL_OPTIONS = {}
    dq_env.YTDL_OPTIONS_PRESETS = {
        "TryOverride": {"extract_flat": False, "noplaylist": False},
    }

    captured_params: list = []

    class FakeYoutubeDL:
        def __init__(self, params=None):
            captured_params.append(params)

        def extract_info(self, url, download=False):
            return {
                "_type": "video",
                "id": "vid-flat",
                "title": "Flat Test",
                "url": url,
                "webpage_url": url,
            }

    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    with patch("ytdl.yt_dlp.YoutubeDL", FakeYoutubeDL):
        result = await dq.add(
            "https://example.com/flat-test",
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=False,
            ytdl_options_presets=["TryOverride"],
        )

    assert result["status"] == "ok"
    assert captured_params[0]["extract_flat"] is True
    assert captured_params[0]["noplaylist"] is True


@pytest.mark.asyncio
async def test_add_sets_clip_bounds_on_download_info(dq_env):
    notifier = AsyncMock()

    def fake_extract(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
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
            "https://example.com/clip",
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=False,
            clip_start=10.0,
            clip_end=99.5,
        )

    assert result["status"] == "ok"
    from ytdl import download_queue_key

    url = "https://example.com/clip"
    download = dq.pending.get(download_queue_key(url, 10.0, 99.5))
    assert download.info.clip_start == 10.0
    assert download.info.clip_end == 99.5
    assert download.info.url == url


@pytest.mark.asyncio
async def test_add_allows_multiple_clips_for_same_url(dq_env):
    notifier = AsyncMock()
    url = "https://example.com/watch?v=same"

    def fake_extract(self, _url, ytdl_options_presets=None, ytdl_options_overrides=None):
        return {
            "_type": "video",
            "id": "vid1",
            "title": "Test Video",
            "url": _url,
            "webpage_url": _url,
        }

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_extract):
        first = await dq.add(
            url, "video", "auto", "any", "best", "", "", 0,
            auto_start=False, clip_start=10.0, clip_end=20.0,
        )
        second = await dq.add(
            url, "video", "auto", "any", "best", "", "", 0,
            auto_start=False, clip_start=30.0, clip_end=40.0,
        )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    from ytdl import download_queue_key

    assert dq.pending.exists(download_queue_key(url, 10.0, 20.0))
    assert dq.pending.exists(download_queue_key(url, 30.0, 40.0))
    assert dq.pending.get(download_queue_key(url, 10.0, 20.0)).info.clip_start == 10.0
    assert dq.pending.get(download_queue_key(url, 30.0, 40.0)).info.clip_start == 30.0
