"""Tests for pure helpers in ``main`` (legacy API migration, logging, JSON serializer)."""

from __future__ import annotations

import json
import logging
import unittest

import main


class MigrateLegacyRequestTests(unittest.TestCase):
    def test_already_new_schema_unchanged(self):
        post = {"download_type": "video", "codec": "h264", "format": "mp4", "quality": "1080"}
        before = post.copy()
        self.assertIs(main._migrate_legacy_request(post), post)
        self.assertEqual(post, before)

    def test_legacy_audio_m4a(self):
        post = {"format": "m4a", "quality": "best"}
        main._migrate_legacy_request(post)
        self.assertEqual(post["download_type"], "audio")
        self.assertEqual(post["codec"], "auto")
        self.assertEqual(post["format"], "m4a")

    def test_legacy_thumbnail(self):
        post = {"format": "thumbnail", "quality": "best"}
        main._migrate_legacy_request(post)
        self.assertEqual(post["download_type"], "thumbnail")
        self.assertEqual(post["format"], "jpg")
        self.assertEqual(post["quality"], "best")

    def test_legacy_captions_with_subtitle_format(self):
        post = {"format": "captions", "subtitle_format": "vtt", "quality": "best"}
        main._migrate_legacy_request(post)
        self.assertEqual(post["download_type"], "captions")
        self.assertEqual(post["format"], "vtt")

    def test_legacy_video_best_ios(self):
        post = {"format": "any", "quality": "best_ios", "video_codec": "auto"}
        main._migrate_legacy_request(post)
        self.assertEqual(post["download_type"], "video")
        self.assertEqual(post["format"], "ios")
        self.assertEqual(post["quality"], "best")

    def test_legacy_video_quality_audio_maps_to_m4a(self):
        post = {"format": "mp4", "quality": "audio", "video_codec": "h264"}
        main._migrate_legacy_request(post)
        self.assertEqual(post["download_type"], "audio")
        self.assertEqual(post["format"], "m4a")
        self.assertEqual(post["quality"], "best")

    def test_legacy_video_default(self):
        post = {"format": "mp4", "quality": "1080", "video_codec": "h265"}
        main._migrate_legacy_request(post)
        self.assertEqual(post["download_type"], "video")
        self.assertEqual(post["codec"], "h265")
        self.assertEqual(post["format"], "mp4")
        self.assertEqual(post["quality"], "1080")


class ParseLogLevelTests(unittest.TestCase):
    def test_valid_levels(self):
        self.assertEqual(main.parseLogLevel("INFO"), logging.INFO)
        self.assertEqual(main.parseLogLevel("debug"), logging.DEBUG)

    def test_invalid_returns_none(self):
        self.assertIsNone(main.parseLogLevel("not_a_level"))
        self.assertIsNone(main.parseLogLevel(123))


class ObjectSerializerTests(unittest.TestCase):
    def test_dict_like_object(self):
        class Obj:
            def __init__(self):
                self.a = 1

        ser = main.ObjectSerializer()
        self.assertEqual(json.loads(ser.encode(Obj())), {"a": 1})

    def test_generator_becomes_list(self):
        ser = main.ObjectSerializer()

        def gen():
            yield 1
            yield 2

        self.assertEqual(json.loads(ser.encode(gen())), [1, 2])

    def test_string_not_split_to_chars(self):
        ser = main.ObjectSerializer()
        self.assertEqual(json.loads(ser.encode("hello")), "hello")


class FrontendSafeTests(unittest.TestCase):
    def test_only_expected_keys(self):
        safe = main.config.frontend_safe()
        for key in main.Config._FRONTEND_KEYS:
            self.assertIn(key, safe)
        self.assertNotIn("YTDL_OPTIONS", safe)
        self.assertNotIn("DOWNLOAD_DIR", safe)


if __name__ == "__main__":
    unittest.main()
