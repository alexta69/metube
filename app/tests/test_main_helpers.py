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
        self.assertIn("ALLOW_YTDL_OPTIONS_OVERRIDES", safe)


class ParseYtdlOverridesTests(unittest.TestCase):
    def test_empty_override_string_returns_empty_dict(self):
        self.assertEqual(main._parse_ytdl_options_overrides("", enabled=False), {})

    def test_rejects_non_object_json(self):
        with self.assertRaises(main.web.HTTPBadRequest):
            main._parse_ytdl_options_overrides('["bad"]', enabled=True)

    def test_rejects_non_empty_overrides_when_disabled(self):
        with self.assertRaises(main.web.HTTPBadRequest):
            main._parse_ytdl_options_overrides('{"exec": "rm -rf /"}', enabled=False)

    def test_allows_any_keys_when_enabled(self):
        self.assertEqual(
            main._parse_ytdl_options_overrides('{"exec": "rm -rf /"}', enabled=True),
            {"exec": "rm -rf /"},
        )


class ParseDownloadOptionsTests(unittest.TestCase):
    def test_accepts_known_preset_and_overrides(self):
        previous = dict(main.config.YTDL_OPTIONS_PRESETS)
        previous_allow = main.config.ALLOW_YTDL_OPTIONS_OVERRIDES
        main.config.YTDL_OPTIONS_PRESETS = {"With subtitles": {"writesubtitles": True}}
        main.config.ALLOW_YTDL_OPTIONS_OVERRIDES = True
        try:
            parsed = main.parse_download_options({
                "url": "https://example.com/v",
                "download_type": "video",
                "codec": "auto",
                "format": "any",
                "quality": "best",
                "ytdl_options_preset": "With subtitles",
                "ytdl_options_overrides": '{"writesubtitles": true}',
            })
        finally:
            main.config.YTDL_OPTIONS_PRESETS = previous
            main.config.ALLOW_YTDL_OPTIONS_OVERRIDES = previous_allow
        self.assertEqual(parsed["ytdl_options_presets"], ["With subtitles"])
        self.assertEqual(parsed["ytdl_options_overrides"], {"writesubtitles": True})

    def test_accepts_multiple_presets_in_order(self):
        previous = dict(main.config.YTDL_OPTIONS_PRESETS)
        main.config.YTDL_OPTIONS_PRESETS = {
            "A": {"writesubtitles": True},
            "B": {"writesubtitles": False},
        }
        try:
            parsed = main.parse_download_options({
                "url": "https://example.com/v",
                "download_type": "video",
                "codec": "auto",
                "format": "any",
                "quality": "best",
                "ytdl_options_presets": ["A", "B"],
            })
        finally:
            main.config.YTDL_OPTIONS_PRESETS = previous
        self.assertEqual(parsed["ytdl_options_presets"], ["A", "B"])

    def test_legacy_singular_preset_string_normalized_to_list(self):
        previous = dict(main.config.YTDL_OPTIONS_PRESETS)
        main.config.YTDL_OPTIONS_PRESETS = {"Solo": {}}
        try:
            parsed = main.parse_download_options({
                "url": "https://example.com/v",
                "download_type": "video",
                "codec": "auto",
                "format": "any",
                "quality": "best",
                "ytdl_options_preset": "Solo",
            })
        finally:
            main.config.YTDL_OPTIONS_PRESETS = previous
        self.assertEqual(parsed["ytdl_options_presets"], ["Solo"])

    def test_rejects_unknown_preset(self):
        with self.assertRaises(main.web.HTTPBadRequest):
            main.parse_download_options({
                "url": "https://example.com/v",
                "download_type": "video",
                "codec": "auto",
                "format": "any",
                "quality": "best",
                "ytdl_options_presets": ["Missing preset"],
            })

    def test_rejects_unknown_preset_in_list(self):
        previous = dict(main.config.YTDL_OPTIONS_PRESETS)
        main.config.YTDL_OPTIONS_PRESETS = {"Known": {}}
        try:
            with self.assertRaises(main.web.HTTPBadRequest):
                main.parse_download_options({
                    "url": "https://example.com/v",
                    "download_type": "video",
                    "codec": "auto",
                    "format": "any",
                    "quality": "best",
                    "ytdl_options_presets": ["Known", "Nope"],
                })
        finally:
            main.config.YTDL_OPTIONS_PRESETS = previous


if __name__ == "__main__":
    unittest.main()
