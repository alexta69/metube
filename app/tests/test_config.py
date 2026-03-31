"""Tests for ``Settings`` (env parsing, yt-dlp options, frontend_safe)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Settings, SettingsError


TEST_APP_ROOT = Path(os.environ["METUBE_TEST_APP_ROOT"])


def _base_env(**overrides: str) -> dict[str, str]:
    env = {k: str(v) for k, v in Settings._DEFAULTS.items()}
    env.update(
        {
            "DOWNLOAD_DIR": os.environ["DOWNLOAD_DIR"],
            "AUDIO_DOWNLOAD_DIR": os.environ["DOWNLOAD_DIR"],
            "STATE_DIR": os.environ["STATE_DIR"],
            "TEMP_DIR": os.environ["TEMP_DIR"],
            "YTDL_OPTIONS": "{}",
            "YTDL_OPTIONS_FILE": "",
            "LOGLEVEL": "INFO",
        }
    )
    env.update(overrides)
    return env


class ConfigTests(unittest.TestCase):
    def test_url_prefix_gets_normalized(self):
        with patch.dict(os.environ, _base_env(URL_PREFIX="foo"), clear=False):
            settings = Settings.from_env(app_root=TEST_APP_ROOT)
        self.assertEqual(settings.URL_PREFIX, "/foo/")

    def test_ytdl_options_json_loaded(self):
        opts = {"quiet": True, "no_warnings": True}
        with patch.dict(
            os.environ,
            _base_env(YTDL_OPTIONS=json.dumps(opts)),
            clear=False,
        ):
            settings = Settings.from_env(app_root=TEST_APP_ROOT)
        self.assertTrue(settings.YTDL_OPTIONS["quiet"])

    def test_invalid_ytdl_options_raises(self):
        with patch.dict(os.environ, _base_env(YTDL_OPTIONS="not-json"), clear=False):
            with self.assertRaises(SettingsError):
                Settings.from_env(app_root=TEST_APP_ROOT)

    def test_invalid_boolean_env_raises(self):
        with patch.dict(os.environ, _base_env(CUSTOM_DIRS="maybe"), clear=False):
            with self.assertRaises(SettingsError):
                Settings.from_env(app_root=TEST_APP_ROOT)

    def test_frontend_safe_excludes_secrets(self):
        with patch.dict(os.environ, _base_env(), clear=False):
            settings = Settings.from_env(app_root=TEST_APP_ROOT)
        safe = settings.frontend_safe()
        self.assertNotIn("YTDL_OPTIONS", safe)
        self.assertNotIn("HOST", safe)

    def test_runtime_override_roundtrip(self):
        with patch.dict(os.environ, _base_env(), clear=False):
            settings = Settings.from_env(app_root=TEST_APP_ROOT)
            settings.set_runtime_override("cookiefile", "/tmp/c.txt")
            self.assertEqual(settings.YTDL_OPTIONS.get("cookiefile"), "/tmp/c.txt")
            settings.remove_runtime_override("cookiefile")
            self.assertIsNone(settings.YTDL_OPTIONS.get("cookiefile"))

    def test_ytdl_options_file_merges(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"extractor_args": {"youtube": {"player_client": ["web"]}}}, handle)
            path = handle.name
        try:
            with patch.dict(
                os.environ,
                _base_env(YTDL_OPTIONS="{}", YTDL_OPTIONS_FILE=path),
                clear=False,
            ):
                settings = Settings.from_env(app_root=TEST_APP_ROOT)
            self.assertIn("extractor_args", settings.YTDL_OPTIONS)
        finally:
            os.unlink(path)

    def test_missing_data_directory_raises(self):
        missing = str(TEST_APP_ROOT / "missing-downloads")
        with patch.dict(os.environ, _base_env(DOWNLOAD_DIR=missing), clear=False):
            with self.assertRaises(SettingsError):
                Settings.from_env(app_root=TEST_APP_ROOT)

    def test_https_requires_cert_and_key(self):
        with patch.dict(os.environ, _base_env(HTTPS="true"), clear=False):
            with self.assertRaises(SettingsError):
                Settings.from_env(app_root=TEST_APP_ROOT)

    def test_sensitive_inline_ytdl_option_rejected(self):
        with patch.dict(
            os.environ,
            _base_env(YTDL_OPTIONS=json.dumps({"cookiefile": "/tmp/cookies.txt"})),
            clear=False,
        ):
            with self.assertRaises(SettingsError):
                Settings.from_env(app_root=TEST_APP_ROOT)


if __name__ == "__main__":
    unittest.main()
