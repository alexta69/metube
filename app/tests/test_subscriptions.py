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

from subscriptions import SubscriptionManager, extract_flat_playlist


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


def _create_legacy_shelf(path: str, record) -> None:
    with shelve.open(path, "c") as shelf:
        shelf["sub-1"] = record


class SubscriptionPersistenceTests(unittest.IsolatedAsyncioTestCase):
    def test_load_imports_legacy_subscription_shelf(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy_path = os.path.join(tmp, "subscriptions")
            json_path = os.path.join(tmp, "subscriptions.json")
            _create_legacy_shelf(
                legacy_path,
                {
                    "id": "sub-1",
                    "name": "Channel",
                    "url": "https://example.com/channel",
                    "timestamp": 1.0,
                },
            )

            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())

            self.assertEqual(len(mgr.list_all()), 1)
            self.assertTrue(os.path.exists(json_path))
            with open(json_path, encoding="utf-8") as f:
                payload = json.load(f)
            self.assertEqual(payload["schema_version"], 2)
            self.assertNotIn("timestamp", payload["items"][0])

    def test_invalid_json_is_quarantined_and_legacy_is_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy_path = os.path.join(tmp, "subscriptions")
            json_path = os.path.join(tmp, "subscriptions.json")
            _create_legacy_shelf(
                legacy_path,
                {
                    "id": "sub-1",
                    "name": "Channel",
                    "url": "https://example.com/channel",
                    "timestamp": 1.0,
                },
            )
            with open(json_path, "w", encoding="utf-8") as f:
                f.write("{not valid json")

            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())

            self.assertEqual(len(mgr.list_all()), 1)
            self.assertTrue(
                any(name.startswith("subscriptions.json.invalid.") for name in os.listdir(tmp))
            )

    def test_load_rewrites_old_json_and_trims_seen_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "subscriptions.json")
            cfg = _Config(tmp)
            cfg.SUBSCRIPTION_MAX_SEEN_IDS = 2
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "schema_version": 1,
                        "kind": "subscriptions",
                        "items": [
                            {
                                "id": "sub-1",
                                "name": "Channel",
                                "url": "https://example.com/channel",
                                "enabled": True,
                                "check_interval_minutes": 60,
                                "download_type": "video",
                                "codec": "auto",
                                "format": "any",
                                "quality": "best",
                                "folder": "",
                                "custom_name_prefix": "",
                                "auto_start": True,
                                "playlist_item_limit": 0,
                                "split_by_chapters": False,
                                "chapter_template": "",
                                "subtitle_language": "en",
                                "subtitle_mode": "prefer_manual",
                                "last_checked": None,
                                "seen_ids": ["a", "b", "a", "c"],
                                "error": None,
                                "timestamp": 123,
                            }
                        ],
                    },
                    f,
                )

            mgr = SubscriptionManager(cfg, _Queue(), _Notifier())
            self.assertEqual(mgr.list_all()[0].seen_ids, ["a", "b"])

            with open(json_path, encoding="utf-8") as f:
                payload = json.load(f)

            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["items"][0]["seen_ids"], ["a", "b"])
            self.assertNotIn("timestamp", payload["items"][0])

    async def test_add_subscription_rolls_back_when_state_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())

            orig_save = __import__("state_store").AtomicJsonStore.save

            def bad_save(store, data):
                if store.path == mgr._path:
                    raise OSError("simulated shelf failure")
                return orig_save(store, data)

            with patch(
                "subscriptions.extract_flat_playlist",
                return_value=(
                    {"_type": "channel", "title": "Channel"},
                    [{"id": "v1", "webpage_url": "https://example.com/v1"}],
                ),
            ):
                with patch("subscriptions.AtomicJsonStore.save", bad_save):
                    with self.assertRaises(OSError):
                        await mgr.add_subscription(
                            "https://example.com/channel",
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

            self.assertEqual(mgr.list_all(), [])
            self.assertNotIn("https://example.com/channel", mgr._url_index)

    async def test_add_subscription_marks_existing_videos_seen_without_queueing(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())

            with patch(
                "subscriptions.extract_flat_playlist",
                return_value=(
                    {"_type": "channel", "title": "Channel"},
                    [
                        {"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"},
                        {"id": "v2", "title": "Two", "webpage_url": "https://example.com/v2"},
                        {"id": "v3", "title": "Three", "webpage_url": "https://example.com/v3"},
                    ],
                ),
            ):
                result = await mgr.add_subscription(
                    "https://example.com/channel",
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

            assert result["status"] == "ok"
            sub = mgr.list_all()[0]
            self.assertEqual(sub.seen_ids, ["v1", "v2", "v3"])
            self.assertIsNone(sub.error)
            self.assertEqual(queue.entries, [])

    async def test_add_subscription_skips_collection_tab_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())

            with patch(
                "subscriptions.extract_flat_playlist",
                return_value=(
                    {"_type": "channel", "title": "Channel"},
                    [
                        {
                            "_type": "url",
                            "ie_key": "YoutubeTab",
                            "title": "Channel - Live",
                            "url": "https://example.com/live",
                            "webpage_url": "https://example.com/live",
                        },
                        {
                            "_type": "url",
                            "ie_key": "Youtube",
                            "id": "v1",
                            "title": "One",
                            "duration": 10,
                            "webpage_url": "https://example.com/v1",
                        },
                    ],
                ),
            ):
                result = await mgr.add_subscription(
                    "https://example.com/channel",
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

            self.assertEqual(result["status"], "ok")
            sub = mgr.list_all()[0]
            self.assertEqual(sub.seen_ids, ["v1"])
            self.assertEqual(queue.entries, [])

    async def test_check_now_keeps_failed_queue_items_unseen_and_sets_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())

            with patch(
                "subscriptions.extract_flat_playlist",
                side_effect=[
                    (
                        {"_type": "channel", "title": "Channel"},
                        [{"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"}],
                    ),
                    (
                        {"_type": "channel", "title": "Channel"},
                        [{"id": "v2", "title": "Two", "webpage_url": "https://example.com/v2"}],
                    ),
                ],
            ):
                result = await mgr.add_subscription(
                    "https://example.com/channel",
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
                queue.fail = True
                await mgr.check_now([result["subscription"]["id"]])

            sub = mgr.list_all()[0]
            self.assertEqual(sub.error, "queue failed")
            self.assertEqual(sub.seen_ids, ["v1"])

    async def test_check_now_queues_new_video_and_updates_seen_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())

            with patch(
                "subscriptions.extract_flat_playlist",
                side_effect=[
                    (
                        {"_type": "channel", "title": "Channel"},
                        [{"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"}],
                    ),
                    (
                        {"_type": "channel", "title": "Channel"},
                        [
                            {"id": "v2", "title": "Two", "webpage_url": "https://example.com/v2"},
                            {"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"},
                        ],
                    ),
                ],
            ):
                result = await mgr.add_subscription(
                    "https://example.com/channel",
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
                await mgr.check_now([result["subscription"]["id"]])

            sub = mgr.list_all()[0]
            self.assertIsNotNone(sub.last_checked)
            self.assertIsNone(sub.error)
            self.assertEqual(sub.seen_ids[:2], ["v2", "v1"])
            self.assertEqual([entry["webpage_url"] for entry, _, _ in queue.entries], ["https://example.com/v2"])

    async def test_update_subscription_parses_string_false_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())

            with patch(
                "subscriptions.extract_flat_playlist",
                return_value=(
                    {"_type": "channel", "title": "Channel"},
                    [{"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"}],
                ),
            ):
                result = await mgr.add_subscription(
                    "https://example.com/channel",
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

            sub_id = result["subscription"]["id"]
            update = await mgr.update_subscription(sub_id, {"enabled": "false"})
            self.assertEqual(update["status"], "ok")
            self.assertFalse(mgr.list_all()[0].enabled)

    async def test_update_subscription_rejects_invalid_enabled_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())

            with patch(
                "subscriptions.extract_flat_playlist",
                return_value=(
                    {"_type": "channel", "title": "Channel"},
                    [{"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"}],
                ),
            ):
                result = await mgr.add_subscription(
                    "https://example.com/channel",
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

            sub_id = result["subscription"]["id"]
            with self.assertRaises(ValueError):
                await mgr.update_subscription(sub_id, {"enabled": "maybe"})

class ExtractFlatPlaylistTests(unittest.TestCase):
    def test_descends_one_level_when_root_entries_are_nested_collections(self):
        responses = iter(
            [
                {
                    "_type": "channel",
                    "entries": [
                        {
                            "_type": "url",
                            "ie_key": "YoutubeTab",
                            "title": "Channel - Videos",
                            "url": "https://example.com/videos",
                            "webpage_url": "https://example.com/videos",
                        }
                    ],
                },
                {
                    "_type": "playlist",
                    "entries": [
                        {
                            "_type": "url",
                            "ie_key": "Youtube",
                            "id": "v1",
                            "title": "One",
                            "duration": 10,
                            "webpage_url": "https://example.com/v1",
                        }
                    ],
                },
            ]
        )

        class _FakeYDL:
            def __init__(self, params):
                self.params = params

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                return next(responses)

        cfg = _Config(tempfile.mkdtemp())
        with patch("subscriptions.yt_dlp.YoutubeDL", _FakeYDL, create=True):
            info, entries = extract_flat_playlist(cfg, "https://example.com/channel", 50)

        self.assertEqual(info.get("_type"), "playlist")
        self.assertEqual([entry["webpage_url"] for entry in entries], ["https://example.com/v1"])


if __name__ == "__main__":
    unittest.main()
