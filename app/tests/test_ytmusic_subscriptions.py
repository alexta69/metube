from __future__ import annotations

import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

# Replicate the yt_dlp fake setup from test_subscriptions.py so this file
# can run independently without yt_dlp installed.
fake_yt_dlp = types.ModuleType("yt_dlp")
fake_networking = types.ModuleType("yt_dlp.networking")
fake_impersonate = types.ModuleType("yt_dlp.networking.impersonate")


class _ImpersonateTarget:
    @staticmethod
    def from_str(value):
        return value


fake_impersonate.ImpersonateTarget = _ImpersonateTarget
fake_networking.impersonate = fake_impersonate
fake_yt_dlp.networking = fake_networking
fake_yt_dlp.utils = types.SimpleNamespace(YoutubeDLError=Exception)
sys.modules.setdefault("yt_dlp", fake_yt_dlp)
sys.modules.setdefault("yt_dlp.networking", fake_networking)
sys.modules.setdefault("yt_dlp.networking.impersonate", fake_impersonate)

from subscriptions import (
    SubscriptionManager,
    _is_ytmusic_artist_url,
    _ytmusic_channel_id,
    extract_ytmusic_artist_releases,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_YTMUSIC_URL = "https://music.youtube.com/channel/UCtest123"
_ARTIST_INFO = {"_type": "channel", "title": "Test Artist"}
_ALBUM_1 = {
    "id": "OLAK5uy_album1",
    "url": "https://music.youtube.com/playlist?list=OLAK5uy_album1",
    "webpage_url": "https://music.youtube.com/playlist?list=OLAK5uy_album1",
    "title": "Album 1",
}
_ALBUM_2 = {
    "id": "OLAK5uy_album2",
    "url": "https://music.youtube.com/playlist?list=OLAK5uy_album2",
    "webpage_url": "https://music.youtube.com/playlist?list=OLAK5uy_album2",
    "title": "Album 2",
}
_SINGLE_1 = {
    "id": "OLAK5uy_single1",
    "url": "https://music.youtube.com/playlist?list=OLAK5uy_single1",
    "webpage_url": "https://music.youtube.com/playlist?list=OLAK5uy_single1",
    "title": "Single 1",
}


class _Config:
    def __init__(self, state_dir: str):
        self.STATE_DIR = state_dir
        self.SUBSCRIPTION_SCAN_PLAYLIST_END = 50
        self.SUBSCRIPTION_MAX_SEEN_IDS = 50000
        self.DOWNLOAD_DIR = state_dir
        self.TEMP_DIR = state_dir
        self.YTDL_OPTIONS = {}


class _Queue:
    def __init__(self):
        self.entries = []
        self.fail = False

    async def add(self, *args, **kwargs):
        return None

    async def add_entry(self, entry, *args, **kwargs):
        if self.fail:
            return {"status": "error", "msg": "queue failed"}
        self.entries.append((entry, args, kwargs))
        return {"status": "ok"}


class _Notifier:
    async def subscription_added(self, sub):
        return None

    async def subscription_updated(self, sub):
        return None

    async def subscription_removed(self, sub_id):
        return None

    async def subscriptions_all(self, subs):
        return None


async def _add_ytmusic_sub(mgr, releases, *, url=_YTMUSIC_URL):
    """Add a YTMusic subscription with mocked extract_ytmusic_artist_releases."""
    with patch(
        "subscriptions.extract_ytmusic_artist_releases",
        return_value=(_ARTIST_INFO, releases),
    ):
        return await mgr.add_subscription(
            url,
            check_interval_minutes=60,
            download_type="audio",
            codec="auto",
            format="opus",
            quality="best",
            folder="",
            custom_name_prefix="",
            auto_start=True,
            playlist_item_limit=0,
            split_by_chapters=False,
            chapter_template="",
            subtitle_language="en",
            subtitle_mode="prefer_manual",
        )


# ---------------------------------------------------------------------------
# URL detection helpers
# ---------------------------------------------------------------------------

class YTMusicUrlHelperTests(unittest.TestCase):
    def test_accepts_music_youtube_channel_url(self):
        self.assertTrue(_is_ytmusic_artist_url("https://music.youtube.com/channel/UCtest123"))

    def test_accepts_http_variant(self):
        self.assertTrue(_is_ytmusic_artist_url("http://music.youtube.com/channel/UCtest123"))

    def test_rejects_regular_youtube_channel(self):
        self.assertFalse(_is_ytmusic_artist_url("https://www.youtube.com/channel/UCtest123"))

    def test_rejects_ytmusic_playlist_url(self):
        self.assertFalse(_is_ytmusic_artist_url("https://music.youtube.com/playlist?list=OLAK5uy_xxx"))

    def test_rejects_ytmusic_watch_url(self):
        self.assertFalse(_is_ytmusic_artist_url("https://music.youtube.com/watch?v=xxx"))

    def test_rejects_empty_string(self):
        self.assertFalse(_is_ytmusic_artist_url(""))

    def test_rejects_none_coerced(self):
        self.assertFalse(_is_ytmusic_artist_url(""))

    def test_channel_id_extracted_correctly(self):
        self.assertEqual(
            _ytmusic_channel_id("https://music.youtube.com/channel/UCtest123"),
            "UCtest123",
        )

    def test_channel_id_returns_none_for_non_matching_url(self):
        self.assertIsNone(_ytmusic_channel_id("https://www.youtube.com/channel/UCtest123"))

    def test_channel_id_returns_none_for_empty(self):
        self.assertIsNone(_ytmusic_channel_id(""))


# ---------------------------------------------------------------------------
# extract_ytmusic_artist_releases
# ---------------------------------------------------------------------------

class ExtractYTMusicReleasesTests(unittest.TestCase):
    def _make_ytm(self, artist_response, albums_response=None, singles_response=None):
        """Build a mock YTMusic instance."""
        ytm = MagicMock()
        ytm.get_artist.return_value = artist_response
        ytm.get_artist_albums.side_effect = lambda browse_id, params: (
            albums_response if "album" in browse_id.lower() or singles_response is None
            else singles_response
        )
        return ytm

    def test_info_dict_has_channel_type_and_artist_title(self):
        ytm = MagicMock()
        ytm.get_artist.return_value = {"name": "Test Artist", "albums": {}, "singles": {}}
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            info, _ = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        self.assertEqual(info["_type"], "channel")
        self.assertEqual(info["title"], "Test Artist")
        self.assertNotIn("channel", info)  # only "title", not redundant "channel" key

    def test_calls_get_artist_albums_when_browse_id_and_params_present(self):
        ytm = MagicMock()
        ytm.get_artist.return_value = {
            "name": "Artist",
            "albums": {"browseId": "MPADUCxxx", "params": "abc"},
            "singles": {},
        }
        ytm.get_artist_albums.return_value = [
            {"playlistId": "OLAK5uy_album1", "title": "Album 1"},
        ]
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            _, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        ytm.get_artist_albums.assert_called_once_with("MPADUCxxx", "abc")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "OLAK5uy_album1")

    def test_falls_back_to_preview_results_when_no_browse_id(self):
        ytm = MagicMock()
        ytm.get_artist.return_value = {
            "name": "Artist",
            "albums": {
                "results": [{"audioPlaylistId": "OLAK5uy_preview", "title": "Preview Album"}]
            },
            "singles": {},
        }
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            _, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        ytm.get_artist_albums.assert_not_called()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "OLAK5uy_preview")

    def test_uses_audio_playlist_id_fallback(self):
        """get_artist() results use audioPlaylistId; should still be picked up."""
        ytm = MagicMock()
        ytm.get_artist.return_value = {
            "name": "Artist",
            "albums": {
                "results": [{"audioPlaylistId": "OLAK5uy_audio", "title": "Album"}]
            },
            "singles": {},
        }
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            _, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        self.assertEqual(entries[0]["id"], "OLAK5uy_audio")

    def test_get_artist_albums_failure_falls_back_to_preview_results(self):
        ytm = MagicMock()
        ytm.get_artist.return_value = {
            "name": "Artist",
            "albums": {
                "browseId": "MPADUCxxx",
                "params": "abc",
                "results": [{"audioPlaylistId": "OLAK5uy_fallback", "title": "Fallback"}],
            },
            "singles": {},
        }
        ytm.get_artist_albums.side_effect = Exception("network error")
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            _, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "OLAK5uy_fallback")

    def test_collects_both_albums_and_singles(self):
        ytm = MagicMock()
        ytm.get_artist.return_value = {
            "name": "Artist",
            "albums": {
                "browseId": "MPADUCalbums",
                "params": "p1",
            },
            "singles": {
                "browseId": "MPADUCsingles",
                "params": "p2",
            },
        }
        ytm.get_artist_albums.side_effect = [
            [{"playlistId": "OLAK5uy_album1", "title": "Album"}],
            [{"playlistId": "OLAK5uy_single1", "title": "Single"}],
        ]
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            _, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        ids = [e["id"] for e in entries]
        self.assertIn("OLAK5uy_album1", ids)
        self.assertIn("OLAK5uy_single1", ids)
        self.assertEqual(len(entries), 2)

    def test_entry_url_points_to_ytmusic_playlist(self):
        ytm = MagicMock()
        ytm.get_artist.return_value = {
            "name": "Artist",
            "albums": {
                "results": [{"audioPlaylistId": "OLAK5uy_xxx", "title": "Album"}]
            },
            "singles": {},
        }
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            _, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        expected_url = "https://music.youtube.com/playlist?list=OLAK5uy_xxx"
        self.assertEqual(entries[0]["url"], expected_url)
        self.assertEqual(entries[0]["webpage_url"], expected_url)

    def test_skips_releases_without_playlist_id(self):
        ytm = MagicMock()
        ytm.get_artist.return_value = {
            "name": "Artist",
            "albums": {
                "results": [
                    {"title": "No ID release"},
                    {"audioPlaylistId": "OLAK5uy_valid", "title": "Valid"},
                ]
            },
            "singles": {},
        }
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            _, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "OLAK5uy_valid")

    def test_get_artist_failure_returns_none_and_empty(self):
        ytm = MagicMock()
        ytm.get_artist.side_effect = Exception("API error")
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            info, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        self.assertIsNone(info)
        self.assertEqual(entries, [])

    def test_ytmusicapi_not_installed_returns_none_and_empty(self):
        with patch.dict("sys.modules", {"ytmusicapi": None}):
            info, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        self.assertIsNone(info)
        self.assertEqual(entries, [])

    def test_empty_artist_returns_empty_entries(self):
        ytm = MagicMock()
        ytm.get_artist.return_value = {"name": "Artist", "albums": {}, "singles": {}}
        with patch("ytmusicapi.YTMusic", return_value=ytm):
            info, entries = extract_ytmusic_artist_releases(_YTMUSIC_URL)
        self.assertIsNotNone(info)
        self.assertEqual(entries, [])


# ---------------------------------------------------------------------------
# SubscriptionManager integration
# ---------------------------------------------------------------------------

class YTMusicSubscriptionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_subscription_uses_extract_ytmusic_not_flat_playlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
            with patch("subscriptions.extract_flat_playlist") as flat, \
                 patch("subscriptions.extract_ytmusic_artist_releases",
                       return_value=(_ARTIST_INFO, [_ALBUM_1])) as ytm:
                await _add_ytmusic_sub(mgr, [_ALBUM_1])
            flat.assert_not_called()

    async def test_add_subscription_ytmusic_marks_existing_releases_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())
            result = await _add_ytmusic_sub(mgr, [_ALBUM_1, _ALBUM_2])
            self.assertEqual(result["status"], "ok")
            sub = mgr.list_all()[0]
            self.assertIn("OLAK5uy_album1", sub.seen_ids)
            self.assertIn("OLAK5uy_album2", sub.seen_ids)
            self.assertEqual(queue.entries, [])  # no downloads queued on subscribe

    async def test_add_subscription_ytmusic_uses_artist_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
            result = await _add_ytmusic_sub(mgr, [_ALBUM_1])
            self.assertEqual(result["subscription"]["name"], "Test Artist")

    async def test_add_subscription_ytmusic_extract_failure_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
            with patch(
                "subscriptions.extract_ytmusic_artist_releases",
                return_value=(None, []),
            ):
                result = await mgr.add_subscription(
                    _YTMUSIC_URL,
                    check_interval_minutes=60,
                    download_type="audio",
                    codec="auto",
                    format="opus",
                    quality="best",
                    folder="",
                    custom_name_prefix="",
                    auto_start=True,
                    playlist_item_limit=0,
                    split_by_chapters=False,
                    chapter_template="",
                    subtitle_language="en",
                    subtitle_mode="prefer_manual",
                )
            self.assertEqual(result["status"], "error")
            self.assertEqual(mgr.list_all(), [])

    async def test_check_now_ytmusic_queues_new_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())
            # Subscribe with album1 already seen
            result = await _add_ytmusic_sub(mgr, [_ALBUM_1])
            sub_id = result["subscription"]["id"]
            # Check: album1 still seen, album2 is new
            with patch(
                "subscriptions.extract_ytmusic_artist_releases",
                return_value=(_ARTIST_INFO, [_ALBUM_1, _ALBUM_2]),
            ):
                await mgr.check_now([sub_id])
            queued_urls = [e["webpage_url"] for e, _, _ in queue.entries]
            self.assertIn(_ALBUM_2["webpage_url"], queued_urls)
            self.assertNotIn(_ALBUM_1["webpage_url"], queued_urls)

    async def test_check_now_ytmusic_does_not_requeue_seen_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())
            result = await _add_ytmusic_sub(mgr, [_ALBUM_1])
            sub_id = result["subscription"]["id"]
            # Check: same releases, nothing new
            with patch(
                "subscriptions.extract_ytmusic_artist_releases",
                return_value=(_ARTIST_INFO, [_ALBUM_1]),
            ):
                await mgr.check_now([sub_id])
            self.assertEqual(queue.entries, [])

    async def test_check_now_ytmusic_updates_seen_ids_after_queueing(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())
            result = await _add_ytmusic_sub(mgr, [_ALBUM_1])
            sub_id = result["subscription"]["id"]
            with patch(
                "subscriptions.extract_ytmusic_artist_releases",
                return_value=(_ARTIST_INFO, [_ALBUM_1, _ALBUM_2]),
            ):
                await mgr.check_now([sub_id])
            sub = mgr.list_all()[0]
            self.assertIn("OLAK5uy_album1", sub.seen_ids)
            self.assertIn("OLAK5uy_album2", sub.seen_ids)
            self.assertIsNone(sub.error)

    async def test_check_now_ytmusic_sets_error_on_extract_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
            result = await _add_ytmusic_sub(mgr, [_ALBUM_1])
            sub_id = result["subscription"]["id"]
            with patch(
                "subscriptions.extract_ytmusic_artist_releases",
                return_value=(None, []),
            ):
                await mgr.check_now([sub_id])
            sub = mgr.list_all()[0]
            self.assertIsNotNone(sub.error)

    async def test_check_now_ytmusic_does_not_call_extract_flat_playlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
            result = await _add_ytmusic_sub(mgr, [_ALBUM_1])
            sub_id = result["subscription"]["id"]
            with patch("subscriptions.extract_flat_playlist") as flat, \
                 patch("subscriptions.extract_ytmusic_artist_releases",
                       return_value=(_ARTIST_INFO, [_ALBUM_1])):
                await mgr.check_now([sub_id])
            flat.assert_not_called()

    async def test_regular_channel_url_still_uses_extract_flat_playlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())
            with patch(
                "subscriptions.extract_flat_playlist",
                return_value=(
                    {"_type": "channel", "title": "Channel"},
                    [{"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"}],
                ),
            ) as flat:
                await mgr.add_subscription(
                    "https://www.youtube.com/channel/UCregular",
                    check_interval_minutes=60,
                    download_type="video",
                    codec="auto",
                    format="any",
                    quality="best",
                    folder="",
                    custom_name_prefix="",
                    auto_start=True,
                    playlist_item_limit=0,
                    split_by_chapters=False,
                    chapter_template="",
                    subtitle_language="en",
                    subtitle_mode="prefer_manual",
                )
            flat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
