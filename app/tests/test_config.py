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
        with patch.dict(os.environ, _base_env(URL_PREFIX="foo"), clear=True):
            c = Config()
        self.assertEqual(c.URL_PREFIX, "foo/")

    def test_public_host_url_gets_trailing_slash(self):
        with patch.dict(
            os.environ,
            _base_env(PUBLIC_HOST_URL="https://ytdl.example.com"),
            clear=False,
        ):
            c = Config()
        self.assertEqual(c.PUBLIC_HOST_URL, "https://ytdl.example.com/")

    def test_public_host_audio_url_gets_trailing_slash(self):
        with patch.dict(
            os.environ,
            _base_env(PUBLIC_HOST_AUDIO_URL="https://audio.example.com"),
            clear=False,
        ):
            c = Config()
        self.assertEqual(c.PUBLIC_HOST_AUDIO_URL, "https://audio.example.com/")

    def test_public_host_url_empty_stays_empty(self):
        with patch.dict(
            os.environ,
            _base_env(PUBLIC_HOST_URL="", PUBLIC_HOST_AUDIO_URL=""),
            clear=False,
        ):
            c = Config()
        self.assertEqual(c.PUBLIC_HOST_URL, "")
        self.assertEqual(c.PUBLIC_HOST_AUDIO_URL, "")

    def test_public_host_url_already_slashed_unchanged(self):
        with patch.dict(
            os.environ,
            _base_env(
                PUBLIC_HOST_URL="https://ytdl.example.com/",
                PUBLIC_HOST_AUDIO_URL="https://audio.example.com/",
            ),
            clear=False,
        ):
            c = Config()
        self.assertEqual(c.PUBLIC_HOST_URL, "https://ytdl.example.com/")
        self.assertEqual(c.PUBLIC_HOST_AUDIO_URL, "https://audio.example.com/")

    def test_ytdl_options_json_loaded(self):
        opts = {"quiet": True, "no_warnings": True}
        with patch.dict(
            os.environ,
            _base_env(YTDL_OPTIONS=json.dumps(opts)),
            clear=True,
        ):
            c = Config()
        self.assertEqual(c.YTDL_OPTIONS["quiet"], True)

    def test_ytdl_option_presets_json_loaded(self):
        presets = {"Audio extras": {"embed_thumbnail": True}}
        with patch.dict(
            os.environ,
            _base_env(YTDL_OPTIONS_PRESETS=json.dumps(presets)),
            clear=True,
        ):
            c = Config()
        self.assertEqual(c.YTDL_OPTIONS_PRESETS["Audio extras"]["embed_thumbnail"], True)

    def test_invalid_ytdl_options_exits(self):
        with patch.dict(os.environ, _base_env(YTDL_OPTIONS="not-json"), clear=True):
            with self.assertRaises(SystemExit):
                Config()

    def test_invalid_boolean_env_exits(self):
        with patch.dict(os.environ, _base_env(CUSTOM_DIRS="maybe"), clear=True):
            with self.assertRaises(SystemExit):
                Config()

    def test_frontend_safe_excludes_secrets(self):
        with patch.dict(os.environ, _base_env(), clear=True):
            c = Config()
        safe = c.frontend_safe()
        self.assertNotIn("YTDL_OPTIONS", safe)
        self.assertNotIn("HOST", safe)
        self.assertNotIn("METUBE_PASSWORD", safe)
        self.assertEqual(safe["ALLOW_YTDL_OPTIONS_OVERRIDES"], False)

    def test_allow_ytdl_options_overrides_boolean_loaded(self):
        with patch.dict(os.environ, _base_env(ALLOW_YTDL_OPTIONS_OVERRIDES="true"), clear=True):
            c = Config()
        self.assertTrue(c.ALLOW_YTDL_OPTIONS_OVERRIDES)

    def test_runtime_override_roundtrip(self):
        with patch.dict(os.environ, _base_env(), clear=True):
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
                clear=True,
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
                clear=True,
            ):
                c = Config()
            self.assertIn("With subtitles", c.YTDL_OPTIONS_PRESETS)
        finally:
            os.unlink(path)

    def test_metube_password_loaded_from_env(self):
        with patch.dict(os.environ, _base_env(METUBE_PASSWORD="secret"), clear=True):
            c = Config()
        self.assertEqual(c.METUBE_PASSWORD, "secret")

    def test_metube_password_loaded_from_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("secret\n")
            path = f.name
        try:
            with patch.dict(os.environ, _base_env(METUBE_PASSWORD_FILE=path), clear=True):
                c = Config()
            self.assertEqual(c.METUBE_PASSWORD, "secret")
        finally:
            os.unlink(path)

    def test_metube_password_and_file_conflict_exits(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("secret")
            path = f.name
        try:
            with patch.dict(os.environ, _base_env(METUBE_PASSWORD="secret", METUBE_PASSWORD_FILE=path), clear=True):
                with self.assertRaises(SystemExit):
                    Config()
        finally:
            os.unlink(path)

    def test_metube_session_max_age_loaded(self):
        with patch.dict(os.environ, _base_env(METUBE_SESSION_MAX_AGE="300"), clear=True):
            c = Config()
        self.assertEqual(c.METUBE_SESSION_MAX_AGE, 300)

    def test_invalid_metube_session_max_age_exits(self):
        with patch.dict(os.environ, _base_env(METUBE_SESSION_MAX_AGE="soon"), clear=True):
            with self.assertRaises(SystemExit):
                Config()


if __name__ == "__main__":
    unittest.main()
