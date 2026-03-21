"""Tests for pure helpers and migration logic in ``ytdl``."""

from __future__ import annotations

import pickle
import tempfile
import threading
import unittest
from pathlib import Path

from ytdl import (
    DownloadInfo,
    _convert_srt_to_txt_file,
    _outtmpl_substitute_field,
    _sanitize_entry_for_pickle,
    _sanitize_path_component,
)


class SanitizePathComponentTests(unittest.TestCase):
    def test_replaces_windows_invalid_chars(self):
        self.assertEqual(_sanitize_path_component('a:b*c?d"e<f>g|h'), "a_b_c_d_e_f_g_h")

    def test_non_string_passthrough(self):
        self.assertIs(_sanitize_path_component(None), None)
        self.assertEqual(_sanitize_path_component(42), 42)


class OuttmplSubstituteFieldTests(unittest.TestCase):
    def test_simple_substitution(self):
        self.assertEqual(_outtmpl_substitute_field("%(title)s", "title", "Hello"), "Hello")

    def test_format_spec_int(self):
        self.assertEqual(_outtmpl_substitute_field("%(idx)02d", "idx", 3), "03")

    def test_missing_field_unchanged(self):
        self.assertEqual(_outtmpl_substitute_field("%(other)s", "title", "x"), "%(other)s")


class SanitizeEntryForPickleTests(unittest.TestCase):
    def test_nested(self):
        def g():
            yield 1

        obj = {"a": g(), "b": [g()]}
        out = _sanitize_entry_for_pickle(obj)
        self.assertEqual(out, {"a": [1], "b": [[1]]})
        pickle.dumps(out)

    def test_plain(self):
        self.assertEqual(_sanitize_entry_for_pickle(5), 5)

    def test_set_converted_to_list(self):
        obj = {"s": {1, 2}}
        out = _sanitize_entry_for_pickle(obj)
        self.assertEqual(sorted(out["s"]), [1, 2])
        pickle.dumps(out)

    def test_map_iterator(self):
        out = _sanitize_entry_for_pickle({"m": map(int, ["1", "2"])})
        self.assertEqual(out, {"m": [1, 2]})

    def test_lock_replaced_with_none(self):
        lock = threading.Lock()
        out = _sanitize_entry_for_pickle({"k": lock})
        self.assertIsNone(out["k"])
        pickle.dumps(out)

    def test_ordered_dict(self):
        from collections import OrderedDict

        od = OrderedDict([("z", 1), ("a", 2)])
        out = _sanitize_entry_for_pickle(od)
        self.assertEqual(out, {"z": 1, "a": 2})


class ConvertSrtToTxtTests(unittest.TestCase):
    def test_basic_conversion(self):
        srt = """1
00:00:01,000 --> 00:00:02,000
Hello <b>world</b>

2
00:00:03,000 --> 00:00:04,000
Second line
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub.srt"
            path.write_text(srt, encoding="utf-8")
            txt_path = _convert_srt_to_txt_file(str(path))
            self.assertIsNotNone(txt_path)
            self.assertTrue(txt_path.endswith(".txt"))
            content = Path(txt_path).read_text(encoding="utf-8")
            self.assertIn("Hello world", content)
            self.assertIn("Second line", content)


class DownloadInfoSetstateTests(unittest.TestCase):
    def _base_state(self, **kwargs):
        base = {
            "id": "id1",
            "title": "t",
            "url": "http://example.com/v",
            "folder": "",
            "custom_name_prefix": "",
            "error": None,
            "entry": None,
            "playlist_item_limit": 0,
            "split_by_chapters": False,
            "chapter_template": "",
            "msg": None,
            "percent": None,
            "speed": None,
            "eta": None,
            "status": "pending",
            "size": None,
            "timestamp": 0,
        }
        base.update(kwargs)
        return base

    def test_migrates_old_audio_format(self):
        state = self._base_state(format="m4a", quality="best")
        di = DownloadInfo.__new__(DownloadInfo)
        di.__setstate__(state)
        self.assertEqual(di.download_type, "audio")
        self.assertEqual(di.codec, "auto")

    def test_migrates_thumbnail(self):
        state = self._base_state(format="thumbnail", quality="best")
        di = DownloadInfo.__new__(DownloadInfo)
        di.__setstate__(state)
        self.assertEqual(di.download_type, "thumbnail")
        self.assertEqual(di.format, "jpg")

    def test_migrates_captions(self):
        state = self._base_state(format="captions", subtitle_format="vtt", quality="best")
        di = DownloadInfo.__new__(DownloadInfo)
        di.__setstate__(state)
        self.assertEqual(di.download_type, "captions")
        self.assertEqual(di.format, "vtt")

    def test_migrates_best_ios(self):
        state = self._base_state(
            format="any", quality="best_ios", video_codec="auto"
        )
        di = DownloadInfo.__new__(DownloadInfo)
        di.__setstate__(state)
        self.assertEqual(di.format, "ios")
        self.assertEqual(di.quality, "best")

    def test_migrates_quality_audio(self):
        state = self._base_state(format="mp4", quality="audio", video_codec="h264")
        di = DownloadInfo.__new__(DownloadInfo)
        di.__setstate__(state)
        self.assertEqual(di.download_type, "audio")
        self.assertEqual(di.format, "m4a")

    def test_new_state_has_subtitle_files(self):
        state = self._base_state(
            download_type="video",
            codec="auto",
            format="any",
            quality="best",
        )
        di = DownloadInfo.__new__(DownloadInfo)
        di.__setstate__(state)
        self.assertEqual(di.subtitle_files, [])


if __name__ == "__main__":
    unittest.main()
