"""Tests for ``DownloadQueue`` with mocked yt-dlp extraction."""

from __future__ import annotations

import os
import re
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import time

from ytdl import Download, DownloadInfo, DownloadQueue


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


def test_download_queue_has_dedicated_executor_sized_from_config(dq_env):
    notifier = MagicMock()
    dq = DownloadQueue(dq_env, notifier)
    assert dq._download_executor is not None
    assert dq._download_executor._max_workers == 2 * int(dq_env.MAX_CONCURRENT_DOWNLOADS) + 2
    dq.close()


def test_close_cancels_running_downloads_before_shutdown(dq_env):
    notifier = MagicMock()
    dq = DownloadQueue(dq_env, notifier)

    running = MagicMock()
    running.started.return_value = True
    running.running.return_value = True
    idle = MagicMock()
    idle.started.return_value = False
    idle.running.return_value = False

    dq.queue.dict["u-running"] = running
    dq.queue.dict["u-idle"] = idle

    dq.close()

    # The active download's subprocess group is killed; the not-started one is
    # left alone. Executor is shut down afterwards.
    running.cancel.assert_called_once()
    idle.cancel.assert_not_called()
    assert dq._download_executor._shutdown


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
async def test_add_unsupported_url_recorded_as_failed_entry(dq_env):
    """An unsupported/unextractable URL must show up as a red-cross entry in the
    done list, not just a transient toast and a server log line."""
    import ytdl

    notifier = AsyncMock()
    url = "https://example.com/not-a-video"

    def boom(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
        raise ytdl.yt_dlp.utils.YoutubeDLError(f'Unsupported URL: {url}')

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", boom):
        result = await dq.add(
            url, "video", "auto", "any", "best", "", "", 0, auto_start=True,
        )
    assert result["status"] == "error"
    assert dq.done.exists(url)
    failed = dq.done.get(url)
    assert failed.info.status == "error"
    assert failed.info.error == result["msg"]
    assert failed.info.url == url
    # The full URL stays in .url/.error for the detail panel; the display
    # title is shortened to the hostname so the Completed row stays readable.
    assert failed.info.title == "example.com"
    notifier.completed.assert_awaited()


@pytest.mark.asyncio
async def test_add_ssrf_rejected_url_recorded_as_failed_entry(dq_env):
    """A URL rejected by the SSRF guard (before yt-dlp ever runs) must also
    surface as a failed entry, not just an error status returned to the caller."""
    notifier = AsyncMock()
    url = "file:///etc/passwd"

    dq = DownloadQueue(dq_env, notifier)
    result = await dq.add(
        url, "video", "auto", "any", "best", "", "", 0, auto_start=True,
    )
    assert result["status"] == "error"
    assert dq.done.exists(url)
    failed = dq.done.get(url)
    assert failed.info.status == "error"
    assert failed.info.error == result["msg"]
    notifier.completed.assert_awaited()


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
async def test_add_entry_duplicate_while_pending_is_skipped_not_clobbered(dq_env):
    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    entry = {
        "_type": "video",
        "id": "vid1",
        "title": "Original Title",
        "url": "https://example.com/watch?v=1",
        "webpage_url": "https://example.com/watch?v=1",
    }

    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", side_effect=AssertionError("should not re-extract")):
        first = await dq.add_entry(entry, "video", "auto", "any", "best", "", "", 0, auto_start=False)
        assert first["status"] == "ok"
        assert "msg" not in first

        dupe_entry = {**entry, "title": "Different Title"}
        second = await dq.add_entry(dupe_entry, "audio", "auto", "mp3", "best", "", "", 0, auto_start=False)

    assert second["status"] == "ok"
    assert "Already in queue" in second["msg"]
    # The original pending download's options must survive untouched.
    pending_dl = dq.pending.get("https://example.com/watch?v=1")
    assert pending_dl.info.download_type == "video"
    assert pending_dl.info.title == "Original Title"


@pytest.mark.asyncio
async def test_add_entry_duplicate_while_queued_is_skipped(dq_env):
    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    entry = {
        "_type": "video",
        "id": "vid1",
        "title": "Test Video",
        "url": "https://example.com/watch?v=1",
        "webpage_url": "https://example.com/watch?v=1",
    }

    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", side_effect=AssertionError("should not re-extract")), \
         patch.object(DownloadQueue, "_DownloadQueue__start_download", new=AsyncMock()):
        first = await dq.add_entry(entry, "video", "auto", "any", "best", "", "", 0, auto_start=True)
        assert first["status"] == "ok"
        assert dq.queue.exists("https://example.com/watch?v=1")

        second = await dq.add_entry(entry, "video", "auto", "any", "best", "", "", 0, auto_start=True)

    assert second["status"] == "ok"
    assert "Already in queue" in second["msg"]


@pytest.mark.asyncio
async def test_channel_download_uses_output_template_when_channel_template_empty(dq_env):
    """Channel tabs reported as playlists must honor OUTPUT_TEMPLATE when OUTPUT_TEMPLATE_CHANNEL is empty."""
    notifier = AsyncMock()
    dq_env.OUTPUT_TEMPLATE = "%(channel)s [YT]/%(title)s.%(ext)s"
    dq_env.OUTPUT_TEMPLATE_CHANNEL = ""
    dq_env.OUTPUT_TEMPLATE_PLAYLIST = ""

    channel_id = "UCabcd123"

    def fake_extract(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
        return {
            "_type": "playlist",
            "id": channel_id,
            "channel_id": channel_id,
            "channel": "Odin",
            "title": "Odin - Videos",
            "entries": [
                {
                    "id": "vid1",
                    "title": "Salvia Plath - Pondering",
                    "url": "https://example.com/watch?v=1",
                    "webpage_url": "https://example.com/watch?v=1",
                    "channel": "Odin",
                    "upload_date": "20130804",
                },
            ],
        }

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_extract):
        result = await dq.add(
            "https://www.youtube.com/@odin/videos",
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
    url = "https://example.com/watch?v=1"
    assert dq.pending.exists(url)
    download = dq.pending.get(url)
    assert download.output_template.startswith("Odin [YT]/")
    assert "Odin - Videos" not in download.output_template


@pytest.mark.asyncio
async def test_playlist_download_not_treated_as_channel(dq_env):
    """Real playlists (id != channel_id) must not be promoted to channel downloads."""
    notifier = AsyncMock()
    dq_env.OUTPUT_TEMPLATE = "%(channel)s [YT]/%(title)s.%(ext)s"
    dq_env.OUTPUT_TEMPLATE_CHANNEL = ""
    dq_env.OUTPUT_TEMPLATE_PLAYLIST = "%(playlist_title)s/%(title)s.%(ext)s"

    def fake_extract(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
        return {
            "_type": "playlist",
            "id": "PLxyz789",
            "channel_id": "UCabcd123",
            "channel": "Odin",
            "title": "My Playlist",
            "entries": [
                {
                    "id": "vid1",
                    "title": "Test Video",
                    "url": "https://example.com/watch?v=1",
                    "webpage_url": "https://example.com/watch?v=1",
                },
            ],
        }

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_extract):
        result = await dq.add(
            "https://www.youtube.com/playlist?list=PLxyz789",
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
    url = "https://example.com/watch?v=1"
    assert dq.pending.exists(url)
    download = dq.pending.get(url)
    assert download.output_template.startswith("My Playlist/")


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
    download = dq.pending.get("https://example.com/clip")
    assert download.info.clip_start == 10.0
    assert download.info.clip_end == 99.5


def _upcoming_entry(url: str, *, release_timestamp: float | None = None) -> dict:
    return {
        "_type": "video",
        "id": "live1",
        "title": "Upcoming Stream",
        "url": url,
        "webpage_url": url,
        "live_status": "is_upcoming",
        "release_timestamp": release_timestamp if release_timestamp is not None else time.time() + 3600,
    }


@pytest.mark.asyncio
async def test_add_upcoming_stream_scheduled_without_starting(dq_env):
    notifier = AsyncMock()
    url = "https://example.com/live-upcoming"
    start_mock = AsyncMock()

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        result = await dq.add_entry(
            _upcoming_entry(url),
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=True,
        )

    assert result["status"] == "ok"
    assert dq.queue.exists(url)
    download = dq.queue.get(url)
    assert download.info.status == "scheduled"
    assert download.info.live_status == "is_upcoming"
    assert download.info.live_release_timestamp is not None
    start_mock.assert_not_called()
    assert url in dq._scheduled_probe_at
    # The "scheduled to start at ..." message must include a UTC offset
    # (a naive datetime's %z would render as an empty string here).
    assert re.search(r"[+-]\d{4}$", download.info.error)


@pytest.mark.asyncio
async def test_probe_scheduled_starts_when_live(dq_env):
    notifier = AsyncMock()
    url = "https://example.com/live-upcoming"
    start_mock = AsyncMock()

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        await dq.add_entry(
            _upcoming_entry(url),
            "video",
            "auto",
            "any",
            "best",
            "",
            "",
            0,
            auto_start=True,
        )

    download = dq.queue.get(url)

    def fake_probe_extract(self, probe_url, ytdl_options_presets=None, ytdl_options_overrides=None):
        assert probe_url == url
        return {
            "_type": "video",
            "id": "live1",
            "title": "Live Now",
            "url": url,
            "webpage_url": url,
            "live_status": "is_live",
            "formats": [{"format_id": "22"}],
        }

    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", fake_probe_extract), \
         patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        await dq._probe_scheduled_download(download)

    assert url not in dq._scheduled_probe_at
    assert download.info.live_status == "is_live"
    assert download.info.status == "pending"
    start_mock.assert_called_once_with(download)


@pytest.mark.asyncio
async def test_import_scheduled_re_registers_monitor(dq_env):
    notifier = AsyncMock()
    url = "https://example.com/live-restart"
    release = time.time() + 7200

    info = DownloadInfo(
        id="live1",
        title="Upcoming Stream",
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
        live_status="is_upcoming",
        live_release_timestamp=release,
    )
    info.status = "scheduled"

    dq = DownloadQueue(dq_env, notifier)
    start_mock = AsyncMock()
    with patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        await dq._DownloadQueue__add_download(info, True)

    assert dq.queue.exists(url)
    assert dq.queue.get(url).info.status == "scheduled"
    assert url in dq._scheduled_probe_at
    start_mock.assert_not_called()


@pytest.mark.asyncio
async def test_probe_transient_error_retries_without_failing(dq_env):
    """A single probe failure must not abandon the scheduled stream."""
    import ytdl

    notifier = AsyncMock()
    url = "https://example.com/live-transient"
    start_mock = AsyncMock()

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        await dq.add_entry(
            _upcoming_entry(url),
            "video", "auto", "any", "best", "", "", 0,
            auto_start=True,
        )
    download = dq.queue.get(url)

    def boom(self, *args, **kwargs):
        raise ytdl.yt_dlp.utils.YoutubeDLError("temporary network glitch")

    before = time.time()
    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", boom):
        await dq._probe_scheduled_download(download)

    # Still scheduled, still monitored, probe rescheduled into the future.
    assert download.info.status == "scheduled"
    assert url in dq._scheduled_probe_at
    assert dq._scheduled_probe_at[url] >= before
    assert dq._scheduled_probe_failures[url] == 1
    notifier.completed.assert_not_called()


@pytest.mark.asyncio
async def test_probe_gives_up_after_max_failures(dq_env):
    import ytdl

    notifier = AsyncMock()
    url = "https://example.com/live-dead"
    start_mock = AsyncMock()

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        await dq.add_entry(
            _upcoming_entry(url),
            "video", "auto", "any", "best", "", "", 0,
            auto_start=True,
        )
    download = dq.queue.get(url)

    def boom(self, *args, **kwargs):
        raise ytdl.yt_dlp.utils.YoutubeDLError("stream was deleted")

    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", boom):
        for _ in range(ytdl._LIVE_PROBE_MAX_FAILURES):
            await dq._probe_scheduled_download(download)

    assert url not in dq._scheduled_probe_at
    assert not dq.queue.exists(url)
    assert dq.done.exists(url)
    assert download.info.status == "error"
    notifier.completed.assert_awaited()


@pytest.mark.asyncio
async def test_probe_recovers_after_transient_then_starts(dq_env):
    """A transient failure followed by a successful live probe should start the download."""
    import ytdl

    notifier = AsyncMock()
    url = "https://example.com/live-recover"
    start_mock = AsyncMock()

    dq = DownloadQueue(dq_env, notifier)
    with patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        await dq.add_entry(
            _upcoming_entry(url),
            "video", "auto", "any", "best", "", "", 0,
            auto_start=True,
        )
    download = dq.queue.get(url)
    # The scheduling placeholder error is set on add.
    assert download.info.error

    def boom(self, *args, **kwargs):
        raise ytdl.yt_dlp.utils.YoutubeDLError("temporary glitch")

    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", boom):
        await dq._probe_scheduled_download(download)
    assert dq._scheduled_probe_failures[url] == 1

    def live_now(self, *args, **kwargs):
        return {
            "_type": "video", "id": "live1", "title": "Live Now",
            "url": url, "webpage_url": url, "live_status": "is_live",
            "formats": [{"format_id": "22"}],
        }

    with patch.object(DownloadQueue, "_DownloadQueue__extract_info", live_now), \
         patch.object(DownloadQueue, "_DownloadQueue__start_download", start_mock):
        await dq._probe_scheduled_download(download)

    assert url not in dq._scheduled_probe_at
    assert url not in dq._scheduled_probe_failures
    assert download.info.status == "pending"
    # Placeholder error/msg cleared now that a real download is starting.
    assert download.info.error is None
    assert download.info.msg is None
    start_mock.assert_called_once_with(download)


def test_seconds_until_next_probe_none_when_empty(dq_env):
    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    assert dq._seconds_until_next_probe() is None


def test_calc_download_path_allows_subfolder(dq_env):
    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    path, err = dq._DownloadQueue__calc_download_path("video", "sub/dir")
    assert err is None
    assert os.path.realpath(path) == os.path.join(os.path.realpath(dq_env.DOWNLOAD_DIR), "sub", "dir")


def test_calc_download_path_rejects_sibling_prefix_escape(dq_env):
    """A folder resolving to a sibling sharing a name prefix must be rejected.

    Regression test: ``startswith`` would have accepted ``../downloads-secret``
    when the base directory is ``.../downloads``.
    """
    notifier = AsyncMock()
    base = os.path.realpath(dq_env.DOWNLOAD_DIR)
    sibling = base + "-secret"
    os.makedirs(sibling, exist_ok=True)
    dq = DownloadQueue(dq_env, notifier)
    escape_folder = os.path.join("..", os.path.basename(sibling), "x")
    path, err = dq._DownloadQueue__calc_download_path("video", escape_folder)
    assert path is None
    assert err is not None and err["status"] == "error"


def test_calc_download_path_rejects_parent_escape(dq_env):
    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    path, err = dq._DownloadQueue__calc_download_path("video", "../../etc")
    assert path is None
    assert err is not None and err["status"] == "error"


def test_download_info_to_public_dict_excludes_server_only_fields():
    info = DownloadInfo(
        id="vid1",
        title="Test Video",
        url="https://example.com/watch?v=1",
        quality="best",
        download_type="video",
        codec="auto",
        format="any",
        folder="",
        custom_name_prefix="",
        error=None,
        entry={"id": "vid1", "huge": "x" * 100000},
        playlist_item_limit=0,
        split_by_chapters=False,
        chapter_template="",
    )
    info.subtitle_files = [{"filename": "a.srt", "size": 10}]
    public = info.to_public_dict()
    assert "entry" not in public
    assert "subtitle_files" not in public
    # Client-facing fields are still present.
    assert public["url"] == "https://example.com/watch?v=1"
    assert public["title"] == "Test Video"
    assert public["status"] == "pending"


def _make_download(dq_env, *, download_type="video", status="downloading", filename=None):
    info = DownloadInfo(
        id="id1",
        title="t",
        url="http://example.com/v",
        quality="best",
        download_type=download_type,
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
    info.status = status
    info.filename = filename
    info.size = 123 if filename else None
    return Download(
        dq_env.DOWNLOAD_DIR, dq_env.TEMP_DIR, "%(title)s.%(ext)s", "%(title)s.%(ext)s", "best", "any", {}, info
    )


def test_download_close_releases_status_queue(dq_env):
    download = _make_download(dq_env)
    status_queue = MagicMock()
    proc = MagicMock()
    download.status_queue = status_queue
    download.proc = proc

    download.close()

    proc.close.assert_called_once()
    assert download.status_queue is None


def test_download_close_releases_status_queue_without_process(dq_env):
    download = _make_download(dq_env)
    download.status_queue = MagicMock()

    download.close()

    assert download.status_queue is None


def test_download_close_releases_status_queue_when_process_close_fails(dq_env):
    download = _make_download(dq_env)
    download.status_queue = MagicMock()
    download.proc = MagicMock()
    download.proc.close.side_effect = RuntimeError('close failed')

    with pytest.raises(RuntimeError, match='close failed'):
        download.close()

    assert download.status_queue is None


@pytest.mark.asyncio
async def test_post_download_cleanup_clears_filename_on_error(dq_env):
    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    download = _make_download(dq_env, status="downloading", filename="../tmp/partial.mp4")
    dq.queue.put(download)

    dq._post_download_cleanup(download)

    assert download.info.status == "error"
    assert download.info.filename is None
    assert download.info.size is None


@pytest.mark.asyncio
async def test_post_download_cleanup_keeps_captured_subtitles_on_error(dq_env):
    notifier = AsyncMock()
    dq = DownloadQueue(dq_env, notifier)
    download = _make_download(dq_env, download_type="captions", status="downloading", filename="en.srt")
    download.info.subtitle_files = [{"filename": "en.srt", "size": 42}]
    dq.queue.put(download)

    dq._post_download_cleanup(download)

    assert download.info.status == "error"
    assert download.info.filename == "en.srt"


@pytest.mark.asyncio
async def test_clear_skips_deletion_outside_download_directory(dq_env):
    notifier = AsyncMock()
    dq_env.DELETE_FILE_ON_TRASHCAN = True
    dq = DownloadQueue(dq_env, notifier)

    outside_dir = tempfile.mkdtemp()
    outside_file = os.path.join(outside_dir, "outside.txt")
    with open(outside_file, "w") as f:
        f.write("do not delete me")

    # A crafted/legacy relative filename that escapes DOWNLOAD_DIR via '..'.
    escaping_filename = os.path.relpath(outside_file, dq_env.DOWNLOAD_DIR)
    download = _make_download(dq_env, status="finished", filename=escaping_filename)
    dq.done.put(download)

    await dq.clear([download.info.url])

    assert os.path.exists(outside_file)
    assert not dq.done.exists(download.info.url)
