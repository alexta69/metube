"""Tests for pure helpers and migration logic in ``ytdl``."""

from __future__ import annotations

import pickle
import signal
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

fake_yt_dlp = types.ModuleType("yt_dlp")
fake_networking = types.ModuleType("yt_dlp.networking")
fake_impersonate = types.ModuleType("yt_dlp.networking.impersonate")
fake_postprocessor = types.ModuleType("yt_dlp.postprocessor")
fake_postprocessor_common = types.ModuleType("yt_dlp.postprocessor.common")
fake_utils = types.ModuleType("yt_dlp.utils")


class _ImpersonateTarget:
    @staticmethod
    def from_str(value):
        return value


class _PostProcessor:
    def __init__(self, downloader=None):
        self._downloader = downloader


fake_impersonate.ImpersonateTarget = _ImpersonateTarget
fake_networking.impersonate = fake_impersonate
fake_postprocessor_common.PostProcessor = _PostProcessor
# The inner ``key`` group mirrors the real ``STR_FORMAT_RE_TMPL`` so that
# ``_OUTTMPL_FIELD_RE`` (compiled at import time) has the named group that
# ``_resolve_outtmpl_fields`` reads via ``match.group('key')``.
fake_utils.STR_FORMAT_RE_TMPL = r"(?P<prefix>)%\((?P<has_key>(?P<key>{}))\)(?P<format>[-0-9.]*{})"
fake_utils.STR_FORMAT_TYPES = "diouxXeEfFgGcrsa"
fake_yt_dlp.networking = fake_networking
fake_yt_dlp.postprocessor = fake_postprocessor
fake_yt_dlp.utils = fake_utils
sys.modules.setdefault("yt_dlp", fake_yt_dlp)
sys.modules.setdefault("yt_dlp.networking", fake_networking)
sys.modules.setdefault("yt_dlp.networking.impersonate", fake_impersonate)
sys.modules.setdefault("yt_dlp.postprocessor", fake_postprocessor)
sys.modules.setdefault("yt_dlp.postprocessor.common", fake_postprocessor_common)
sys.modules.setdefault("yt_dlp.utils", fake_utils)

from ytdl import (
    Download,
    DownloadInfo,
    MusicMetadataPreProcessor,
    _compact_persisted_entry,
    _convert_srt_to_txt_file,
    _AlbumArtistPostProcessor,
    _output_dir_escapes,
    _resolve_outtmpl_fields,
    _sanitize_entry_for_pickle,
    _sanitize_path_component,
)

# Detect whether the real yt-dlp is loaded (as opposed to the minimal fake
# shim above).  _resolve_outtmpl_fields needs YoutubeDL at runtime.
_has_real_ytdlp = hasattr(sys.modules.get("yt_dlp"), "YoutubeDL")


class AlbumArtistPostProcessorTests(unittest.TestCase):
    def setUp(self):
        self.postprocessor = _AlbumArtistPostProcessor()

    def test_fills_album_artist_from_artist(self):
        info = {'album': 'CrasH Talk', 'artist': 'ScHoolboy Q'}

        _, result = self.postprocessor.run(info)

        self.assertEqual(result['album_artist'], 'ScHoolboy Q')

    def test_uses_main_artist_for_featured_track(self):
        info = {
            'album': 'CrasH Talk',
            'artists': ['ScHoolboy Q · Travis Scott'],
        }

        _, result = self.postprocessor.run(info)

        self.assertEqual(result['album_artist'], 'ScHoolboy Q')

    def test_uses_topic_channel_artist_for_joint_album(self):
        info = {
            'album': 'Watch the Throne',
            'artists': ['JAY-Z', 'Kanye West'],
            'channel': 'JAY-Z & Kanye West - Topic',
        }

        _, result = self.postprocessor.run(info)

        self.assertEqual(result['album_artist'], 'JAY-Z & Kanye West')

    def test_uses_topic_uploader_and_strips_suffix_for_compilation(self):
        info = {
            'album': 'Compilation',
            'artist': 'Track Artist',
            'channel': 'Regular Channel',
            'uploader': 'Various Artists - Topic',
        }

        _, result = self.postprocessor.run(info)

        self.assertEqual(result['album_artist'], 'Various Artists')

    def test_regular_channel_falls_back_to_main_artist(self):
        info = {
            'album': 'Album',
            'artist': 'Track Artist',
            'channel': 'Label Channel',
        }

        _, result = self.postprocessor.run(info)

        self.assertEqual(result['album_artist'], 'Track Artist')

    def test_preserves_explicit_various_artists(self):
        info = {
            'album': 'Revenge of the Dreamers III',
            'artist': 'J. Cole',
            'album_artist': 'Various Artists',
        }

        _, result = self.postprocessor.run(info)

        self.assertEqual(result['album_artist'], 'Various Artists')

    def test_preserves_existing_album_artists_list(self):
        info = {
            'album': 'Album',
            'artist': 'Track Artist',
            'album_artists': ['Album Artist'],
        }

        _, result = self.postprocessor.run(info)

        self.assertEqual(result['album_artists'], ['Album Artist'])
        self.assertNotIn('album_artist', result)

    def test_uses_first_artist_when_artist_list_has_multiple_entries(self):
        info = {'album': 'Album', 'artists': ['Main Artist', 'Featured Artist']}

        _, result = self.postprocessor.run(info)

        self.assertEqual(result['album_artist'], 'Main Artist')

    def test_does_not_fill_without_album(self):
        info = {'artist': 'Standalone Artist'}

        _, result = self.postprocessor.run(info)

        self.assertNotIn('album_artist', result)
        self.assertNotIn('album_artists', result)

    def test_does_not_fill_without_artist(self):
        info = {'album': 'Instrumental Album'}

        _, result = self.postprocessor.run(info)

        self.assertNotIn('album_artist', result)
        self.assertNotIn('album_artists', result)


class AlbumArtistRegistrationTests(unittest.TestCase):
    def test_audio_download_registers_pre_process_postprocessor(self):
        download = _make_test_download()
        download.info.download_type = 'audio'
        fake_ydl = MagicMock()

        with patch('ytdl.yt_dlp.YoutubeDL', return_value=fake_ydl):
            result = download._make_youtube_dl({'quiet': True})

        self.assertIs(result, fake_ydl)
        album_artist_call = fake_ydl.add_post_processor.call_args_list[0]
        postprocessor, = album_artist_call.args
        self.assertIsInstance(postprocessor, _AlbumArtistPostProcessor)
        self.assertEqual(album_artist_call.kwargs, {'when': 'pre_process'})
        metadata_pre_call = fake_ydl.add_post_processor.call_args_list[1]
        metadata_preprocessor, = metadata_pre_call.args
        self.assertIsInstance(metadata_preprocessor, MusicMetadataPreProcessor)
        self.assertEqual(metadata_pre_call.kwargs, {'when': 'pre_process'})
        self.assertEqual(fake_ydl.add_post_processor.call_count, 2)

    def test_video_download_does_not_register_postprocessor(self):
        download = _make_test_download()
        fake_ydl = MagicMock()

        with patch('ytdl.yt_dlp.YoutubeDL', return_value=fake_ydl):
            download._make_youtube_dl({'quiet': True})

        fake_ydl.add_post_processor.assert_not_called()


class SanitizePathComponentTests(unittest.TestCase):
    def test_replaces_windows_invalid_chars(self):
        self.assertEqual(_sanitize_path_component('a:b*c?d"e<f>g|h'), "a_b_c_d_e_f_g_h")

    def test_non_string_passthrough(self):
        self.assertIs(_sanitize_path_component(None), None)
        self.assertEqual(_sanitize_path_component(42), 42)

    def test_strips_path_separators_and_traversal(self):
        result = _sanitize_path_component('../../../../etc/x')
        self.assertNotIn('..', result)
        self.assertNotIn('/', result)
        self.assertNotIn('\\', result)

    def test_strips_leading_absolute_path_separator(self):
        result = _sanitize_path_component('/tmp/x')
        self.assertFalse(result.startswith('/'))
        self.assertFalse(result.startswith('\\'))
        self.assertEqual(result, '_tmp_x')

    def test_collapses_slashes_in_legitimate_titles(self):
        self.assertEqual(_sanitize_path_component('AC/DC'), 'AC_DC')

    def test_empty_after_strip_becomes_underscore(self):
        self.assertEqual(_sanitize_path_component('   '), '_')


@unittest.skipUnless(_has_real_ytdlp, "requires real yt-dlp")
class ResolveOuttmplFieldsTests(unittest.TestCase):
    """Tests for _resolve_outtmpl_fields (delegates to yt-dlp's template engine)."""

    def test_simple_playlist_substitution(self):
        info = {"playlist_title": "My PL", "playlist_index": "03"}
        result = _resolve_outtmpl_fields("%(playlist_title)s/%(title)s.%(ext)s", info, ("playlist",))
        self.assertEqual(result, "My PL/%(title)s.%(ext)s")

    def test_format_spec_int(self):
        info = {"playlist_index": "3"}
        result = _resolve_outtmpl_fields("%(playlist_index)02d-%(title)s", info, ("playlist",))
        self.assertEqual(result, "03-%(title)s")

    def test_non_targeted_fields_unchanged(self):
        info = {"playlist_title": "PL"}
        result = _resolve_outtmpl_fields("%(title)s/%(ext)s", info, ("playlist",))
        self.assertEqual(result, "%(title)s/%(ext)s")

    def test_default_value(self):
        info = {"playlist_index": "1"}
        result = _resolve_outtmpl_fields("%(playlist_title|Unknown)s/%(playlist_index)s", info, ("playlist",))
        self.assertEqual(result, "Unknown/1")

    def test_channel_prefix(self):
        info = {"channel": "MyChan", "channel_index": "05"}
        result = _resolve_outtmpl_fields("%(channel)s/%(channel_index)02d-%(title)s", info, ("channel",))
        self.assertEqual(result, "MyChan/05-%(title)s")

    def test_math_operation(self):
        info = {"playlist_index": "3"}
        result = _resolve_outtmpl_fields("%(playlist_index+100)d", info, ("playlist",))
        self.assertEqual(result, "103")

    def test_playlist_count_and_autonumber(self):
        info = {
            "playlist_title": "My PL",
            "playlist_index": "03",
            "playlist_count": 10,
            "playlist_autonumber": 3,
            "n_entries": 10,
            "__last_playlist_index": 10,
        }
        result = _resolve_outtmpl_fields(
            "%(playlist_title)s/%(playlist_autonumber)s of %(playlist_count)s - %(title)s.%(ext)s",
            info,
            ("playlist",),
        )
        # playlist_autonumber is auto-padded by yt-dlp using __last_playlist_index
        self.assertEqual(result, "My PL/03 of 10 - %(title)s.%(ext)s")

    def test_conditional_playlist_index(self):
        info = {
            "playlist_index": "5",
            "playlist_count": 10,
        }
        result = _resolve_outtmpl_fields(
            "%(playlist_index&{} - |)s%(title)s.%(ext)s",
            info,
            ("playlist",),
        )
        self.assertEqual(result, "5 - %(title)s.%(ext)s")

    def test_malicious_playlist_title_cannot_escape_via_template(self):
        malicious_title = '/tmp/METUBE_ARBITRARY_WRITE_POC'
        entry = {
            'playlist_title': malicious_title,
            'playlist_index': '1',
            'title': 'video',
            'ext': 'mp4',
        }
        sanitized = {k: _sanitize_path_component(v) for k, v in entry.items()}
        template = '%(playlist_title)s/%(title)s.%(ext)s'
        result = _resolve_outtmpl_fields(template, sanitized, ('playlist',))
        marker = result.find('%(')
        literal_prefix = result[:marker] if marker != -1 else result
        self.assertNotIn('..', literal_prefix)
        self.assertFalse(literal_prefix.startswith('/'))
        self.assertFalse(literal_prefix.startswith('\\'))


class OutputDirEscapesTests(unittest.TestCase):
    def setUp(self):
        self.base_dir = tempfile.mkdtemp()

    def test_relative_traversal_escapes(self):
        self.assertTrue(_output_dir_escapes(self.base_dir, '../../tmp/x/%(title)s.%(ext)s'))

    def test_absolute_path_escapes(self):
        self.assertTrue(_output_dir_escapes(self.base_dir, '/tmp/x/%(title)s.%(ext)s'))

    def test_normal_playlist_dir_stays_inside(self):
        self.assertFalse(_output_dir_escapes(self.base_dir, 'Playlist/%(title)s.%(ext)s'))


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


def _make_test_download() -> Download:
    info = DownloadInfo(
        id="id1",
        title="t",
        url="http://example.com/v",
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
    )
    return Download("/tmp", "/tmp", "%(title)s.%(ext)s", "%(title)s.%(ext)s", "best", "any", {}, info)


class ProgressThrottleTests(unittest.TestCase):
    def test_downloading_ticks_are_throttled(self):
        dl = _make_test_download()
        forwarded = []
        dl.status_queue = types.SimpleNamespace(put=forwarded.append)
        hook = dl._make_progress_hook()

        with patch("ytdl.time.monotonic", side_effect=[100.0, 100.1, 100.6, 100.7]):
            hook({"status": "downloading", "downloaded_bytes": 1})
            hook({"status": "downloading", "downloaded_bytes": 2})
            hook({"status": "downloading", "downloaded_bytes": 3})
            hook({"status": "downloading", "downloaded_bytes": 4})

        # Only the 1st and 3rd ticks are >= 0.5s apart from the last forwarded one.
        self.assertEqual(len(forwarded), 2)

    def test_finished_and_error_statuses_always_forwarded(self):
        dl = _make_test_download()
        forwarded = []
        dl.status_queue = types.SimpleNamespace(put=forwarded.append)
        hook = dl._make_progress_hook()

        with patch("ytdl.time.monotonic", side_effect=[200.0, 200.1]):
            hook({"status": "downloading"})
            hook({"status": "finished"})
            hook({"status": "downloading"})
            hook({"status": "error", "msg": "boom"})

        statuses = [item.get("status") for item in forwarded]
        self.assertIn("finished", statuses)
        self.assertIn("error", statuses)


class CancelProcessGroupTests(unittest.TestCase):
    def test_cancel_kills_group_when_child_is_group_leader(self):
        # Child successfully ran os.setpgrp(): its pgid equals its own pid.
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321)
        dl.status_queue = types.SimpleNamespace(put=lambda _item: None)

        with patch.object(Download, "running", return_value=True), \
             patch("ytdl.os.getpgid", return_value=4321) as mock_getpgid, \
             patch("ytdl.os.killpg") as mock_killpg:
            dl.cancel()

        mock_getpgid.assert_called_once_with(4321)
        mock_killpg.assert_called_once_with(4321, signal.SIGKILL)
        self.assertTrue(dl.canceled)

    def test_cancel_does_not_killpg_parent_group_kills_child_only(self):
        # Child has NOT become its own group leader yet (pgid != pid, e.g. it is
        # still in the server's process group). killpg must NOT be called — that
        # would SIGKILL the whole server — and we fall back to proc.kill().
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321, kill=MagicMock())
        dl.status_queue = types.SimpleNamespace(put=lambda _item: None)

        with patch.object(Download, "running", return_value=True), \
             patch("ytdl.os.getpgid", return_value=999), \
             patch("ytdl.os.killpg") as mock_killpg:
            dl.cancel()

        mock_killpg.assert_not_called()
        dl.proc.kill.assert_called_once()
        self.assertTrue(dl.canceled)

    def test_cancel_falls_back_to_proc_kill_when_getpgid_unavailable(self):
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321, kill=MagicMock())
        dl.status_queue = types.SimpleNamespace(put=lambda _item: None)

        with patch.object(Download, "running", return_value=True), \
             patch("ytdl.os.getpgid", side_effect=OSError("no such process")):
            dl.cancel()

        dl.proc.kill.assert_called_once()
        self.assertTrue(dl.canceled)


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

    def test_vtt_input_strips_header_and_metadata(self):
        # yt-dlp can fall back to VTT even when srt/txt was requested (the
        # extractor may not offer a native srt track); the converter must not
        # leak VTT-only header/metadata lines into the plain-text output.
        vtt = """WEBVTT
Kind: captions
Language: en

NOTE
This is a note block

1
00:00:01.000 --> 00:00:02.000
Hello <b>world</b>

2
00:00:03.000 --> 00:00:04.000
Second line
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub.vtt"
            path.write_text(vtt, encoding="utf-8")
            txt_path = _convert_srt_to_txt_file(str(path))
            self.assertIsNotNone(txt_path)
            content = Path(txt_path).read_text(encoding="utf-8")
            self.assertIn("Hello world", content)
            self.assertIn("Second line", content)
            self.assertNotIn("WEBVTT", content)
            self.assertNotIn("Kind:", content)
            self.assertNotIn("Language:", content)
            self.assertNotIn("This is a note block", content)

    def test_vtt_standalone_header_block_is_stripped(self):
        # Some VTT files put a blank line after WEBVTT, so Kind:/Language: form
        # their own block. That header block (before the first timed cue) must
        # still be stripped.
        vtt = """WEBVTT

Kind: captions
Language: en

1
00:00:01.000 --> 00:00:02.000
Hello world
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub.vtt"
            path.write_text(vtt, encoding="utf-8")
            content = Path(_convert_srt_to_txt_file(str(path))).read_text(encoding="utf-8")
            self.assertIn("Hello world", content)
            self.assertNotIn("Kind:", content)
            self.assertNotIn("Language:", content)

    def test_cue_text_starting_with_metadata_keyword_is_kept(self):
        # A real caption line beginning with "Kind:"/"Language:" must NOT be
        # dropped as if it were VTT header metadata.
        srt = """1
00:00:01,000 --> 00:00:02,000
Kind: regards, everyone

2
00:00:03,000 --> 00:00:04,000
Language: they spoke French
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub.srt"
            path.write_text(srt, encoding="utf-8")
            content = Path(_convert_srt_to_txt_file(str(path))).read_text(encoding="utf-8")
            self.assertIn("Kind: regards, everyone", content)
            self.assertIn("Language: they spoke French", content)


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

    def test_missing_optional_fields_are_defaulted(self):
        state = self._base_state(
            download_type="video",
            codec="auto",
            format="any",
            quality="best",
        )
        state.pop("folder")
        state.pop("custom_name_prefix")
        state.pop("playlist_item_limit")
        state.pop("split_by_chapters")
        state.pop("chapter_template")
        di = DownloadInfo.__new__(DownloadInfo)
        di.__setstate__(state)
        self.assertEqual(di.folder, "")
        self.assertEqual(di.custom_name_prefix, "")
        self.assertEqual(di.playlist_item_limit, 0)
        self.assertFalse(di.split_by_chapters)
        self.assertEqual(di.chapter_template, "")


class CompactPersistedEntryTests(unittest.TestCase):
    def test_keeps_only_playlist_and_channel_keys(self):
        entry = {
            "playlist_index": "01",
            "playlist_title": "Playlist",
            "playlist_count": 10,
            "playlist_autonumber": 1,
            "channel_index": "02",
            "channel_title": "Channel",
            "n_entries": 10,
            "__last_playlist_index": 10,
            "formats": [{"id": "huge"}],
            "description": "big blob",
        }

        compact = _compact_persisted_entry(entry)

        self.assertEqual(
            compact,
            {
                "playlist_index": "01",
                "playlist_title": "Playlist",
                "playlist_count": 10,
                "playlist_autonumber": 1,
                "channel_index": "02",
                "channel_title": "Channel",
                "n_entries": 10,
                "__last_playlist_index": 10,
            },
        )

    def test_returns_none_when_no_restart_relevant_keys_exist(self):
        self.assertIsNone(_compact_persisted_entry({"id": "x", "title": "y"}))


if __name__ == "__main__":
    unittest.main()
