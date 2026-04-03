"""Tests for ``Config`` (env parsing, yt-dlp options, frontend_safe)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from main import Config


def _base_env(**overrides: str) -> dict[str, str]:
    env = {k: str(v) for k, v in Config._DEFAULTS.items()}
    env.update(overrides)
    return env


class ConfigTests(unittest.TestCase):
    def test_url_prefix_gets_trailing_slash(self):
        with patch.dict(os.environ, _base_env(URL_PREFIX="foo"), clear=False):
            c = Config()
        self.assertEqual(c.URL_PREFIX, "foo/")

    def test_ytdl_options_json_loaded(self):
        opts = {"quiet": True, "no_warnings": True}
        with patch.dict(
            os.environ,
            _base_env(YTDL_OPTIONS=json.dumps(opts)),
            clear=False,
        ):
            c = Config()
        self.assertEqual(c.YTDL_OPTIONS["quiet"], True)

    def test_ytdl_option_presets_json_loaded(self):
        presets = {"Audio extras": {"embed_thumbnail": True}}
        with patch.dict(
            os.environ,
            _base_env(YTDL_OPTIONS_PRESETS=json.dumps(presets)),
            clear=False,
        ):
            c = Config()
        self.assertEqual(c.YTDL_OPTIONS_PRESETS["Audio extras"]["embed_thumbnail"], True)

    def test_invalid_ytdl_options_exits(self):
        with patch.dict(os.environ, _base_env(YTDL_OPTIONS="not-json"), clear=False):
            with self.assertRaises(SystemExit):
                Config()

    def test_invalid_boolean_env_exits(self):
        with patch.dict(os.environ, _base_env(CUSTOM_DIRS="maybe"), clear=False):
            with self.assertRaises(SystemExit):
                Config()

    def test_frontend_safe_excludes_secrets(self):
        with patch.dict(os.environ, _base_env(), clear=False):
            c = Config()
        safe = c.frontend_safe()
        self.assertNotIn("YTDL_OPTIONS", safe)
        self.assertNotIn("HOST", safe)

    def test_runtime_override_roundtrip(self):
        with patch.dict(os.environ, _base_env(), clear=False):
            c = Config()
            c.set_runtime_override("cookiefile", "/tmp/c.txt")
            self.assertEqual(c.YTDL_OPTIONS.get("cookiefile"), "/tmp/c.txt")
            c.remove_runtime_override("cookiefile")
            self.assertIsNone(c.YTDL_OPTIONS.get("cookiefile"))

    def test_ytdl_options_file_merges(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"extractor_args": {"youtube": {"player_client": ["web"]}}}, f)
            path = f.name
        try:
            with patch.dict(
                os.environ,
                _base_env(YTDL_OPTIONS="{}", YTDL_OPTIONS_FILE=path),
                clear=False,
            ):
                c = Config()
            self.assertIn("extractor_args", c.YTDL_OPTIONS)
        finally:
            os.unlink(path)

    def test_ytdl_option_presets_file_merges(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"With subtitles": {"writesubtitles": True}}, f)
            path = f.name
        try:
            with patch.dict(
                os.environ,
                _base_env(YTDL_OPTIONS_PRESETS="{}", YTDL_OPTIONS_PRESETS_FILE=path),
                clear=False,
            ):
                c = Config()
            self.assertIn("With subtitles", c.YTDL_OPTIONS_PRESETS)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
