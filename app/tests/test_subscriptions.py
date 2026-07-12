from __future__ import annotations

import asyncio
import json
import os
import shelve
import sys
import tempfile
import time
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

from subscriptions import (
    SubscriptionInfo,
    SubscriptionManager,
    _is_subscriber_only_entry,
    coerce_optional_bool,
    extract_flat_playlist,
)


class _Config:
    def __init__(self, state_dir: str):
        self.STATE_DIR = state_dir
        self.SUBSCRIPTION_SCAN_PLAYLIST_END = 50
        self.SUBSCRIPTION_MAX_SEEN_IDS = 50000
        self.DOWNLOAD_DIR = state_dir
        self.TEMP_DIR = state_dir
        self.YTDL_OPTIONS = {}
        self.YTDL_OPTIONS_PRESETS = {}


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


class SubscriberOnlyHelperTests(unittest.TestCase):
    def test_is_subscriber_only_detects_availability(self):
        self.assertTrue(_is_subscriber_only_entry({"availability": "subscriber_only"}))
        self.assertFalse(_is_subscriber_only_entry({"availability": None}))
        self.assertFalse(_is_subscriber_only_entry({}))

    def test_coerce_optional_bool_defaults_and_fields(self):
        self.assertFalse(coerce_optional_bool(None, default=False))
        self.assertTrue(coerce_optional_bool(True))
        self.assertFalse(coerce_optional_bool(False))
        with self.assertRaises(ValueError):
            coerce_optional_bool("maybe", field_name="skip_subscriber_only")


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

    async def test_check_now_queues_subscriber_only_when_skip_disabled(self):
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
                            {
                                "id": "v2",
                                "title": "Members",
                                "webpage_url": "https://example.com/v2",
                                "availability": "subscriber_only",
                            },
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
                    skip_subscriber_only=False,
                )
                self.assertFalse(mgr.list_all()[0].skip_subscriber_only)
                await mgr.check_now([result["subscription"]["id"]])

            sub = mgr.list_all()[0]
            self.assertIsNone(sub.error)
            self.assertEqual(sub.seen_ids[:2], ["v2", "v1"])
            self.assertEqual([entry["webpage_url"] for entry, _, _ in queue.entries], ["https://example.com/v2"])

    async def test_check_now_skips_subscriber_only_when_skip_enabled(self):
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
                            {
                                "id": "v2",
                                "title": "Members",
                                "webpage_url": "https://example.com/v2",
                                "availability": "subscriber_only",
                            },
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
                    skip_subscriber_only=True,
                )
                self.assertTrue(mgr.list_all()[0].skip_subscriber_only)
                await mgr.check_now([result["subscription"]["id"]])

            sub = mgr.list_all()[0]
            self.assertIsNone(sub.error)
            self.assertEqual(sub.seen_ids[:2], ["v2", "v1"])
            self.assertEqual(queue.entries, [])

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
            update_result = await mgr.update_subscription(sub_id, {"enabled": "maybe"})
            self.assertEqual(update_result["status"], "error")
            stored = mgr.get(sub_id)
            self.assertTrue(stored.enabled)

            update_result = await mgr.update_subscription(
                sub_id, {"check_interval_minutes": "abc"}
            )
            self.assertEqual(update_result["status"], "error")
            self.assertEqual(mgr.get(sub_id).check_interval_minutes, 60)

    async def test_add_subscription_rejects_invalid_title_regex(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
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
                    title_regex="[",
                )
            self.assertEqual(result["status"], "error")
            self.assertIn("title_regex", result["msg"].lower())
            self.assertEqual(mgr.list_all(), [])

    async def test_add_subscription_stores_and_exposes_title_regex(self):
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
                    title_regex="EPISODE",
                )
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["subscription"]["title_regex"], "EPISODE")
            self.assertEqual(mgr.list_all()[0].title_regex, "EPISODE")

    async def test_check_now_title_regex_queues_only_matches_and_marks_unmatched_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())
            with patch(
                "subscriptions.extract_flat_playlist",
                side_effect=[
                    (
                        {"_type": "channel", "title": "Channel"},
                        [{"id": "v1", "title": "Old", "webpage_url": "https://example.com/v1"}],
                    ),
                    (
                        {"_type": "channel", "title": "Channel"},
                        [
                            {
                                "id": "v2",
                                "title": "Minecraft | EPISODE 1",
                                "webpage_url": "https://example.com/v2",
                            },
                            {
                                "id": "v3",
                                "title": "Unrelated IRL",
                                "webpage_url": "https://example.com/v3",
                            },
                            {
                                "id": "v1",
                                "title": "Old",
                                "webpage_url": "https://example.com/v1",
                            },
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
                    title_regex="EPISODE",
                )
                await mgr.check_now([result["subscription"]["id"]])
            self.assertEqual([e["webpage_url"] for e, _, _ in queue.entries], ["https://example.com/v2"])
            sub = mgr.list_all()[0]
            self.assertEqual(sub.seen_ids[:3], ["v2", "v3", "v1"])

    async def test_check_now_title_regex_queue_failure_keeps_matched_id_unseen(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = _Queue()
            mgr = SubscriptionManager(_Config(tmp), queue, _Notifier())
            with patch(
                "subscriptions.extract_flat_playlist",
                side_effect=[
                    (
                        {"_type": "channel", "title": "Channel"},
                        [{"id": "v1", "title": "Old", "webpage_url": "https://example.com/v1"}],
                    ),
                    (
                        {"_type": "channel", "title": "Channel"},
                        [
                            {
                                "id": "v2",
                                "title": "Show | EPISODE 1",
                                "webpage_url": "https://example.com/v2",
                            },
                            {
                                "id": "v3",
                                "title": "Other",
                                "webpage_url": "https://example.com/v3",
                            },
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
                    title_regex="EPISODE",
                )
                queue.fail = True
                await mgr.check_now([result["subscription"]["id"]])
            sub = mgr.list_all()[0]
            self.assertEqual(sub.error, "queue failed")
            self.assertEqual(set(sub.seen_ids), {"v1", "v3"})
            self.assertNotIn("v2", sub.seen_ids)

    async def test_update_subscription_rejects_invalid_title_regex(self):
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
            upd = await mgr.update_subscription(sub_id, {"title_regex": "("})
            self.assertEqual(upd["status"], "error")
            self.assertEqual(mgr.list_all()[0].title_regex, "")

    async def test_update_subscription_persists_valid_title_regex(self):
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
            upd = await mgr.update_subscription(sub_id, {"title_regex": "foo|bar"})
            self.assertEqual(upd["status"], "ok")
            self.assertEqual(upd["subscription"]["title_regex"], "foo|bar")
            self.assertEqual(mgr.list_all()[0].title_regex, "foo|bar")

    async def test_update_subscription_skip_subscriber_only(self):
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
            self.assertFalse(mgr.list_all()[0].skip_subscriber_only)
            upd = await mgr.update_subscription(sub_id, {"skip_subscriber_only": True})
            self.assertEqual(upd["status"], "ok")
            self.assertTrue(upd["subscription"]["skip_subscriber_only"])
            self.assertTrue(mgr.list_all()[0].skip_subscriber_only)

    async def test_update_subscription_rejects_invalid_skip_subscriber_only(self):
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
            upd = await mgr.update_subscription(sub_id, {"skip_subscriber_only": "maybe"})
            self.assertEqual(upd["status"], "error")
            self.assertFalse(mgr.list_all()[0].skip_subscriber_only)

    def test_persistence_includes_title_regex(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "subscriptions.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "schema_version": 2,
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
                                "ytdl_options_presets": [],
                                "ytdl_options_overrides": {},
                                "title_regex": "EPISODE",
                                "last_checked": None,
                                "seen_ids": [],
                                "error": None,
                            }
                        ],
                    },
                    f,
                )
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
            self.assertEqual(mgr.list_all()[0].title_regex, "EPISODE")
            self.assertFalse(mgr.list_all()[0].skip_subscriber_only)

    def test_persistence_includes_skip_subscriber_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "subscriptions.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "schema_version": 2,
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
                                "ytdl_options_presets": [],
                                "ytdl_options_overrides": {},
                                "title_regex": "",
                                "skip_subscriber_only": True,
                                "last_checked": None,
                                "seen_ids": [],
                                "error": None,
                            }
                        ],
                    },
                    f,
                )
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
            self.assertTrue(mgr.list_all()[0].skip_subscriber_only)


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

    def test_extra_opts_applied_on_top_of_config_options(self):
        captured: dict = {}

        class _FakeYDL:
            def __init__(self, params):
                captured.update(params)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                return {"_type": "video"}

        cfg = _Config(tempfile.mkdtemp())
        with patch("subscriptions.yt_dlp.YoutubeDL", _FakeYDL, create=True):
            extract_flat_playlist(cfg, "https://example.com/v1", 50, extra_opts={"cookiefile": "x"})

        self.assertEqual(captured.get("cookiefile"), "x")


def _make_scan_capturing_fake_ydl(captured_params: list, entries: list[dict]):
    class _FakeYDL:
        def __init__(self, params):
            captured_params.append(params)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {"_type": "channel", "title": "Channel", "entries": entries}

    return _FakeYDL


class SubscriptionScanExtraOptsTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_subscription_scan_applies_presets_and_overrides(self):
        captured_params: list = []
        fake_ydl = _make_scan_capturing_fake_ydl(
            captured_params,
            [{"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"}],
        )

        with tempfile.TemporaryDirectory() as tmp:
            cfg = _Config(tmp)
            cfg.YTDL_OPTIONS_PRESETS = {"mypreset": {"cookiefile": "preset.txt"}}
            mgr = SubscriptionManager(cfg, _Queue(), _Notifier())

            with patch("subscriptions.yt_dlp.YoutubeDL", fake_ydl, create=True):
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
                    ytdl_options_presets=["mypreset"],
                    ytdl_options_overrides={"extra": "override"},
                )

        self.assertTrue(captured_params)
        self.assertEqual(captured_params[0].get("cookiefile"), "preset.txt")
        self.assertEqual(captured_params[0].get("extra"), "override")

    async def test_check_now_scan_applies_stored_subscription_presets(self):
        entries = [{"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"}]

        with tempfile.TemporaryDirectory() as tmp:
            cfg = _Config(tmp)
            cfg.YTDL_OPTIONS_PRESETS = {"mypreset": {"cookiefile": "preset.txt"}}
            mgr = SubscriptionManager(cfg, _Queue(), _Notifier())

            add_captured: list = []
            with patch(
                "subscriptions.yt_dlp.YoutubeDL",
                _make_scan_capturing_fake_ydl(add_captured, entries),
                create=True,
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
                    ytdl_options_presets=["mypreset"],
                )
            sub_id = result["subscription"]["id"]

            check_captured: list = []
            with patch(
                "subscriptions.yt_dlp.YoutubeDL",
                _make_scan_capturing_fake_ydl(check_captured, entries),
                create=True,
            ):
                await mgr.check_now([sub_id])

        self.assertTrue(check_captured)
        self.assertEqual(check_captured[0].get("cookiefile"), "preset.txt")


class SubscriptionEventLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_now_does_not_block_event_loop(self):
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

            def _slow_extract(config, url, playlistend, **kwargs):
                time.sleep(0.3)
                return (
                    {"_type": "channel", "title": "Channel"},
                    [{"id": "v1", "title": "One", "webpage_url": "https://example.com/v1"}],
                )

            with patch("subscriptions.extract_flat_playlist", side_effect=_slow_extract):
                check_task = asyncio.ensure_future(mgr.check_now([sub_id]))
                # If check_now() blocked the event loop, this would not complete
                # until after the slow extraction finishes.
                await asyncio.wait_for(asyncio.sleep(0.05), timeout=0.2)
                self.assertFalse(check_task.done())
                await check_task

    async def test_check_many_isolates_a_crashing_subscription(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())

            good = SubscriptionInfo(id="good", name="Good", url="https://example.com/good")
            bad = SubscriptionInfo(id="bad", name="Bad", url="https://example.com/bad")
            other = SubscriptionInfo(id="other", name="Other", url="https://example.com/other")

            checked: list[str] = []

            async def fake_check(sub):
                if sub.id == "bad":
                    raise RuntimeError("boom")
                checked.append(sub.id)

            with patch.object(mgr, "_check_one_unlocked", side_effect=fake_check):
                # The crashing subscription must not prevent the others running.
                await mgr._check_many([good, bad, other])

            self.assertIn("good", checked)
            self.assertIn("other", checked)

    async def test_check_many_bounded_concurrency(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SubscriptionManager(_Config(tmp), _Queue(), _Notifier())
            subs = [
                SubscriptionInfo(id=str(i), name=str(i), url=f"https://example.com/{i}")
                for i in range(10)
            ]

            import subscriptions as subs_mod

            concurrent = 0
            peak = 0

            async def fake_check(sub):
                nonlocal concurrent, peak
                concurrent += 1
                peak = max(peak, concurrent)
                await asyncio.sleep(0.02)
                concurrent -= 1

            with patch.object(mgr, "_check_one_unlocked", side_effect=fake_check):
                await mgr._check_many(subs)

            # Never exceed the configured bound, but do run more than one at once.
            self.assertLessEqual(peak, subs_mod._MAX_CONCURRENT_CHECKS)
            self.assertGreater(peak, 1)


if __name__ == "__main__":
    unittest.main()
