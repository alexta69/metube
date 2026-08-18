"""Tests for pure helpers and migration logic in ``ytdl``."""

from __future__ import annotations

import os
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


class _YoutubeDL:
    """Minimal stand-in so ``_ConfinedYoutubeDL`` can subclass it under the shim.

    ``prepare_filename`` is patched per-test; the real containment logic lives in
    the ``_ConfinedYoutubeDL`` override, which is what the tests exercise.
    """

    def __init__(self, params=None, **kwargs):
        self.params = params or {}

    def prepare_filename(self, *args, **kwargs):
        return ""

    def add_post_processor(self, *args, **kwargs):
        pass


fake_utils.DownloadError = type("DownloadError", (Exception,), {})
fake_utils.YoutubeDLError = fake_utils.DownloadError
fake_yt_dlp.YoutubeDL = _YoutubeDL
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

import ytdl
from ytdl import (
    Download,
    DownloadInfo,
    MusicMetadataPreProcessor,
    _compact_persisted_entry,
    _convert_srt_to_txt_file,
    _pot_provider_urls,
    _AlbumArtistPostProcessor,
    _resolve_outtmpl_fields,
    _sanitize_entry_for_pickle,
    _sanitize_path_component,
    _short_title_for_failed_url,
)

# Detect whether the real yt-dlp is loaded (as opposed to the minimal fake
# shim above).  _resolve_outtmpl_fields needs YoutubeDL.evaluate_outtmpl at
# runtime, which the shim's YoutubeDL stand-in deliberately does not provide.
_has_real_ytdlp = hasattr(
    getattr(sys.modules.get("yt_dlp"), "YoutubeDL", None), "evaluate_outtmpl"
)


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

        with patch('ytdl._ConfinedYoutubeDL', return_value=fake_ydl):
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

        with patch('ytdl._ConfinedYoutubeDL', return_value=fake_ydl):
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


class ConfinedYoutubeDLTests(unittest.TestCase):
    """The chokepoint: ``_ConfinedYoutubeDL.prepare_filename`` validates the
    *resolved* output path (after yt-dlp expands the template) and refuses any
    write outside the allowed roots. This is the single guard for the download-
    directory invariant across the main file, split-chapter files, thumbnails,
    subtitles, etc. — the ``..`` only exists post-expansion, so it is caught here
    rather than by any ingress string check.
    """

    def setUp(self):
        self.base = os.path.realpath(tempfile.mkdtemp())

    def _prepared_path(self, resolved, roots=None):
        ydl = ytdl._ConfinedYoutubeDL.__new__(ytdl._ConfinedYoutubeDL)
        ydl._allowed_roots = [self.base] if roots is None else roots
        with patch.object(
            ytdl.yt_dlp.YoutubeDL, "prepare_filename", return_value=resolved
        ):
            return ydl.prepare_filename({})

    def test_chapter_traversal_via_metadata_is_blocked(self):
        # e.g. chapter_template '%(section_title)s/%(section_title)s/pwned.%(ext)s'
        # with a chapter titled '..' expands to '../../pwned.mp4'.
        escaping = os.path.join(self.base, "..", "..", "pwned.mp4")
        with self.assertRaises(ytdl.yt_dlp.utils.DownloadError):
            self._prepared_path(escaping)

    def test_absolute_output_path_is_blocked(self):
        with self.assertRaises(ytdl.yt_dlp.utils.DownloadError):
            self._prepared_path("/etc/cron.d/evil")

    def test_path_inside_download_dir_is_allowed(self):
        ok = os.path.join(self.base, "Playlist", "video.mp4")
        self.assertEqual(self._prepared_path(ok), ok)

    def test_sibling_prefix_directory_is_blocked(self):
        # base '/x/downloads' must not be escapable to '/x/downloads-secret'.
        sibling = self.base + "-secret"
        with self.assertRaises(ytdl.yt_dlp.utils.DownloadError):
            self._prepared_path(os.path.join(sibling, "video.mp4"))

    def test_empty_and_stdout_targets_pass_through(self):
        self.assertEqual(self._prepared_path(""), "")
        self.assertEqual(self._prepared_path("-"), "-")

    def test_overlong_name_is_trimmed_to_fit_the_filesystem(self):
        # A title long enough to blow the filename limit is what made these
        # downloads fail outright with [Errno 36] File name too long.
        long_path = os.path.join(self.base, "a" * 400 + ".mp4")

        result = self._prepared_path(long_path)

        name = os.path.basename(result)
        self.assertTrue(name.endswith(".mp4"))
        self.assertLessEqual(len(name.encode("utf-8")), 255 - 32)
        self.assertEqual(os.path.dirname(result), self.base)
        # The file must still be writable once yt-dlp adds its own suffixes.
        self.assertLessEqual(len(f"{name}.f1229065279304024v.part".encode("utf-8")), 255)

    def test_name_within_the_limit_is_left_alone(self):
        ok = os.path.join(self.base, "Ordinary Title.mp4")
        self.assertEqual(self._prepared_path(ok), ok)

    def test_limit_counts_bytes_not_characters(self):
        # 200 CJK characters are 600 bytes: a character count would pass this.
        long_path = os.path.join(self.base, "音" * 200 + ".mp4")

        name = os.path.basename(self._prepared_path(long_path))

        self.assertLessEqual(len(name.encode("utf-8")), 255 - 32)
        # A trim landing mid-character must not leave a broken byte sequence.
        self.assertEqual(name, name.encode("utf-8").decode("utf-8"))
        self.assertTrue(name.endswith(".mp4"))

    def test_a_long_tail_is_not_mistaken_for_an_extension(self):
        # os.path.splitext on a title containing a dot late in the string would
        # otherwise "preserve" a 100-character extension and trim nothing.
        long_path = os.path.join(self.base, "b" * 300 + "." + "c" * 100)

        name = os.path.basename(self._prepared_path(long_path))

        self.assertLessEqual(len(name.encode("utf-8")), 255 - 32)

    def test_trimming_still_cannot_escape_the_download_directory(self):
        escaping = os.path.join(self.base, "..", "..", "d" * 400 + ".mp4")
        with self.assertRaises(ytdl.yt_dlp.utils.DownloadError):
            self._prepared_path(escaping)


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


class DownloadLoggerTests(unittest.TestCase):
    def test_routes_messages_and_retains_only_non_empty_warnings(self):
        logger = ytdl._DownloadYtdlLogger()

        with self.assertLogs('ytdl', level='DEBUG') as logs:
            logger.debug('debug detail')
            logger.warning(' useful warning ')
            logger.warning('   ')
            logger.error('error detail')

        self.assertEqual(logger.warnings, ['useful warning'])
        self.assertIn('DEBUG:ytdl:debug detail', logs.output)
        self.assertIn('WARNING:ytdl: useful warning ', logs.output)
        self.assertIn('ERROR:ytdl:error detail', logs.output)

    def test_retains_only_the_last_distinct_warnings(self):
        logger = ytdl._DownloadYtdlLogger()
        cap = ytdl._MAX_RETAINED_WARNINGS

        with self.assertLogs('ytdl', level='WARNING') as logs:
            for index in range(cap + 3):
                logger.warning(f'fragment {index} not found')

        self.assertEqual(
            logger.warnings,
            [f'fragment {index} not found' for index in range(3, cap + 3)],
        )
        # Every warning still reaches the log; only the retained list is bounded.
        self.assertEqual(len(logs.output), cap + 3)

    def test_repeated_warning_is_retained_once(self):
        logger = ytdl._DownloadYtdlLogger()

        with self.assertLogs('ytdl', level='WARNING'):
            logger.warning('Requested format is not available')
            logger.warning('Only images are available for download')
            logger.warning('Requested format is not available')

        self.assertEqual(
            logger.warnings,
            ['Requested format is not available', 'Only images are available for download'],
        )

    def test_failure_message_puts_the_error_last(self):
        logger = ytdl._DownloadYtdlLogger()

        with self.assertLogs('ytdl', level='WARNING'):
            logger.warning('Only images are available for download')

        self.assertEqual(
            logger.failure_message('ERROR: [youtube] u2HSc2Ym1Vk: No video formats found!'),
            'Only images are available for download\n'
            'ERROR: [youtube] u2HSc2Ym1Vk: No video formats found!',
        )

    def test_failure_message_skips_a_last_warning_that_repeats_the_error(self):
        logger = ytdl._DownloadYtdlLogger()

        with self.assertLogs('ytdl', level='WARNING'):
            logger.warning('Video unavailable')
            # yt-dlp labels errors but hands warnings to the logger unlabelled,
            # so the same text can arrive through both routes.
            logger.warning('Requested format is not available')

        self.assertEqual(
            logger.failure_message('ERROR: Requested format is not available'),
            'Video unavailable\nERROR: Requested format is not available',
        )

    def test_failure_message_without_warnings_is_the_error_alone(self):
        logger = ytdl._DownloadYtdlLogger()

        self.assertEqual(logger.failure_message('ERROR: boom'), 'ERROR: boom')


class DownloadResultTests(unittest.TestCase):
    def _run_download(self, result=0, warnings=(), error=None):
        download = _make_test_download()
        statuses = []
        download.status_queue = types.SimpleNamespace(put=statuses.append)
        captured_params = {}

        class FakeYoutubeDL:
            def download(self, urls):
                self.urls = urls
                for warning in warnings:
                    captured_params['logger'].warning(warning)
                if error is not None:
                    raise error
                return result

        def make_youtube_dl(params):
            captured_params.update(params)
            return FakeYoutubeDL()

        with patch.object(download, '_make_youtube_dl', side_effect=make_youtube_dl), \
             patch('ytdl.install_socket_guard'), \
             patch('ytdl.os.setpgrp'):
            download._download()

        return statuses, captured_params

    def test_nonzero_result_includes_warning_context_and_forwards_logs(self):
        warnings = [
            'The uploader has blocked this video in your country',
            'No video formats found',
        ]

        with self.assertLogs('ytdl', level='WARNING') as logs:
            statuses, params = self._run_download(result=1, warnings=warnings)

        self.assertEqual(
            statuses[-1],
            {'status': 'error', 'msg': '\n'.join(warnings)},
        )
        self.assertIs(params['logger'].__class__, ytdl._DownloadYtdlLogger)
        for warning in warnings:
            self.assertTrue(any(warning in entry for entry in logs.output))

    def test_nonzero_result_without_warning_uses_fallback_message(self):
        statuses, _ = self._run_download(result=2)

        self.assertEqual(
            statuses[-1],
            {'status': 'error', 'msg': 'yt-dlp failed with exit code 2'},
        )

    def test_warning_does_not_change_success_status(self):
        statuses, _ = self._run_download(result=0, warnings=['A recoverable warning'])

        self.assertEqual(statuses[-1], {'status': 'finished'})

    def test_youtube_dl_error_carries_the_warnings_that_explain_it(self):
        # The sequence from issue #1047: yt-dlp raises DownloadError, so the
        # warnings naming the real cause only reach the user if the exception
        # branch carries them too.
        statuses, _ = self._run_download(
            warnings=[
                '[youtube] Video unavailable. This video contains content from bryhuangpub,'
                ' who has blocked it from display on this website or application',
                'Only images are available for download. use --list-formats to see them',
                'Requested format is not available',
            ],
            error=ytdl.yt_dlp.utils.YoutubeDLError(
                'ERROR: [youtube] u2HSc2Ym1Vk: No video formats found!'
            ),
        )

        self.assertEqual(
            statuses[-1],
            {
                'status': 'error',
                'msg': '[youtube] Video unavailable. This video contains content from bryhuangpub,'
                ' who has blocked it from display on this website or application\n'
                'Only images are available for download. use --list-formats to see them\n'
                'Requested format is not available\n'
                'ERROR: [youtube] u2HSc2Ym1Vk: No video formats found!',
            },
        )

    def test_youtube_dl_error_drops_a_last_warning_that_repeats_it(self):
        statuses, _ = self._run_download(
            warnings=['Earlier warning', 'Requested format is not available'],
            error=ytdl.yt_dlp.utils.YoutubeDLError('ERROR: Requested format is not available'),
        )

        self.assertEqual(
            statuses[-1],
            {
                'status': 'error',
                'msg': 'Earlier warning\nERROR: Requested format is not available',
            },
        )

    def test_youtube_dl_error_message_is_bounded(self):
        cap = ytdl._MAX_RETAINED_WARNINGS
        statuses, _ = self._run_download(
            warnings=[f'fragment {index} not found' for index in range(cap + 4)],
            error=ytdl.yt_dlp.utils.YoutubeDLError('ERROR: giving up'),
        )

        msg = statuses[-1]['msg']
        self.assertEqual(
            msg.split('\n'),
            [f'fragment {index} not found' for index in range(4, cap + 4)] + ['ERROR: giving up'],
        )

    def test_nonzero_result_message_is_bounded(self):
        cap = ytdl._MAX_RETAINED_WARNINGS
        statuses, _ = self._run_download(
            result=1,
            warnings=[f'fragment {index} not found' for index in range(cap + 4)],
        )

        self.assertEqual(
            statuses[-1]['msg'].split('\n'),
            [f'fragment {index} not found' for index in range(4, cap + 4)],
        )


def _capture_ytdl_params(download: Download) -> dict:
    """Run ``_download`` far enough to capture the params it builds."""
    fake_ydl = MagicMock()
    fake_ydl.download.return_value = 0
    download.status_queue = types.SimpleNamespace(put=lambda _: None)

    with patch('ytdl.install_socket_guard'), \
            patch.object(Download, '_make_youtube_dl', return_value=fake_ydl) as make:
        download._download()

    params, = make.call_args.args
    return params


class SponsorBlockPostprocessorTests(unittest.TestCase):
    def test_no_sponsorblock_postprocessors_when_disabled(self):
        download = _make_test_download()

        params = _capture_ytdl_params(download)

        keys = [pp['key'] for pp in params.get('postprocessors', [])]
        self.assertNotIn('SponsorBlock', keys)
        self.assertNotIn('ModifyChapters', keys)

    def test_sponsorblock_pair_matches_the_cli(self):
        download = _make_test_download()
        download.info.sponsorblock = True

        params = _capture_ytdl_params(download)

        self.assertEqual(
            params['postprocessors'],
            [
                {
                    'key': 'SponsorBlock',
                    'categories': ['sponsor'],
                    'when': 'after_filter',
                },
                {
                    'key': 'ModifyChapters',
                    'remove_sponsor_segments': ['sponsor'],
                    'force_keyframes': False,
                },
            ],
        )

    def test_segment_removal_runs_before_the_chapter_split(self):
        # yt-dlp runs same-stage postprocessors in list order, so ModifyChapters
        # has to rewrite the chapter list before FFmpegSplitChapters cuts the
        # file up -- the order the CLI builds for
        # --sponsorblock-remove sponsor --split-chapters.
        download = _make_test_download()
        download.info.sponsorblock = True
        download.info.split_by_chapters = True
        download.info.chapter_template = '%(section_number)s.%(ext)s'

        params = _capture_ytdl_params(download)

        keys = [pp['key'] for pp in params['postprocessors']]
        self.assertEqual(keys, ['SponsorBlock', 'ModifyChapters', 'FFmpegSplitChapters'])
        self.assertEqual(params['outtmpl']['chapter'], '%(section_number)s.%(ext)s')


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
    # cancel() now sends SIGINT first (so yt-dlp/ffmpeg can finalize the
    # partial file) and schedules a SIGKILL escalation via the event loop
    # after ytdl._CANCEL_GRACE_SECONDS, instead of SIGKILLing immediately.

    def test_cancel_sends_sigint_to_group_and_schedules_sigkill_escalation(self):
        # Child successfully ran os.setpgrp(): its pgid equals its own pid.
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321)
        dl.status_queue = types.SimpleNamespace(put=lambda _item: None)
        dl.loop = MagicMock()

        with patch.object(Download, "running", return_value=True), \
             patch("ytdl.os.getpgid", return_value=4321) as mock_getpgid, \
             patch("ytdl.os.killpg") as mock_killpg:
            dl.cancel()

        mock_getpgid.assert_called_once_with(4321)
        mock_killpg.assert_called_once_with(4321, signal.SIGINT)
        dl.loop.call_later.assert_called_once_with(ytdl._CANCEL_GRACE_SECONDS, dl._kill_if_alive)
        self.assertTrue(dl.canceled)

    def test_cancel_does_not_killpg_parent_group_signals_child_only(self):
        # Child has NOT become its own group leader yet (pgid != pid, e.g. it is
        # still in the server's process group). killpg must NOT be called — that
        # would signal the whole server — and we fall back to os.kill(pid, SIGINT).
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321)
        dl.status_queue = types.SimpleNamespace(put=lambda _item: None)
        dl.loop = MagicMock()

        with patch.object(Download, "running", return_value=True), \
             patch("ytdl.os.getpgid", return_value=999), \
             patch("ytdl.os.killpg") as mock_killpg, \
             patch("ytdl.os.kill") as mock_kill:
            dl.cancel()

        mock_killpg.assert_not_called()
        mock_kill.assert_called_once_with(4321, signal.SIGINT)
        dl.loop.call_later.assert_called_once_with(ytdl._CANCEL_GRACE_SECONDS, dl._kill_if_alive)
        self.assertTrue(dl.canceled)

    def test_cancel_falls_back_to_pid_signal_when_getpgid_unavailable(self):
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321)
        dl.status_queue = types.SimpleNamespace(put=lambda _item: None)
        dl.loop = MagicMock()

        with patch.object(Download, "running", return_value=True), \
             patch("ytdl.os.getpgid", side_effect=OSError("no such process")), \
             patch("ytdl.os.kill") as mock_kill:
            dl.cancel()

        mock_kill.assert_called_once_with(4321, signal.SIGINT)
        dl.loop.call_later.assert_called_once_with(ytdl._CANCEL_GRACE_SECONDS, dl._kill_if_alive)
        self.assertTrue(dl.canceled)

    def test_cancel_kills_immediately_when_signal_delivery_fails(self):
        # Neither killpg nor os.kill succeed (process already gone): cancel()
        # must fall through to an immediate SIGKILL attempt instead of
        # scheduling a pointless escalation.
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321, kill=MagicMock())
        dl.status_queue = types.SimpleNamespace(put=lambda _item: None)
        dl.loop = MagicMock()

        with patch.object(Download, "running", return_value=True), \
             patch("ytdl.os.getpgid", side_effect=OSError("no such process")), \
             patch("ytdl.os.kill", side_effect=ProcessLookupError()):
            dl.cancel()

        dl.loop.call_later.assert_not_called()
        dl.proc.kill.assert_called_once()
        self.assertTrue(dl.canceled)

    def test_cancel_schedules_escalation_even_without_running_loop(self):
        # dl.loop is None (e.g. cancel() called before start()'s run_in_executor
        # set it up): _kill_if_alive() must run synchronously instead of being
        # scheduled, since there's no loop to schedule it on.
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321)
        dl.status_queue = types.SimpleNamespace(put=lambda _item: None)
        self.assertIsNone(dl.loop)

        with patch.object(Download, "running", side_effect=[True, True]), \
             patch("ytdl.os.getpgid", return_value=4321), \
             patch("ytdl.os.killpg") as mock_killpg:
            dl.cancel()

        # First SIGINT, then _kill_if_alive() ran inline and sent SIGKILL.
        mock_killpg.assert_has_calls([
            unittest.mock.call(4321, signal.SIGINT),
            unittest.mock.call(4321, signal.SIGKILL),
        ])
        self.assertTrue(dl.canceled)


class KillIfAliveTests(unittest.TestCase):
    def test_kill_if_alive_sigkills_running_process(self):
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321)

        with patch.object(Download, "running", return_value=True), \
             patch("ytdl.os.getpgid", return_value=4321), \
             patch("ytdl.os.killpg") as mock_killpg:
            dl._kill_if_alive()

        mock_killpg.assert_called_once_with(4321, signal.SIGKILL)

    def test_kill_if_alive_noop_when_process_already_exited(self):
        dl = _make_test_download()
        dl.proc = types.SimpleNamespace(pid=4321)

        with patch.object(Download, "running", return_value=False), \
             patch("ytdl.os.killpg") as mock_killpg, \
             patch("ytdl.os.kill") as mock_kill:
            dl._kill_if_alive()

        mock_killpg.assert_not_called()
        mock_kill.assert_not_called()


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


class ShortTitleForFailedUrlTests(unittest.TestCase):
    def test_uses_hostname_for_a_normal_url(self):
        self.assertEqual(
            _short_title_for_failed_url("https://example.com/watch?v=1"),
            "example.com",
        )

    def test_falls_back_to_raw_value_when_there_is_no_hostname(self):
        # file:// URIs and bare search terms/video IDs have no netloc to extract.
        self.assertEqual(_short_title_for_failed_url("file:///etc/passwd"), "file:///etc/passwd")
        self.assertEqual(_short_title_for_failed_url("ytsearch:some query"), "ytsearch:some query")

    def test_falls_back_to_raw_value_on_unparseable_input(self):
        # A malformed IPv6-looking host raises ValueError in urlsplit().hostname.
        malformed = "https://[::1/watch"
        self.assertEqual(_short_title_for_failed_url(malformed), malformed)


class PotProviderUrlsTests(unittest.TestCase):
    """#1064: the connect-time guard must let the download reach the PO token
    provider, so it has to know every endpoint yt-dlp might dial for one."""

    def test_bundled_provider_by_default(self):
        self.assertEqual(_pot_provider_urls({}), ("http://127.0.0.1:4416",))

    def test_configured_base_url_is_added(self):
        urls = _pot_provider_urls({
            "extractor_args": {"youtubepot-bgutilhttp": {"base_url": ["http://pot:4416"]}},
        })
        # The bundled server runs regardless, so both stay reachable.
        self.assertEqual(urls, ("http://127.0.0.1:4416", "http://pot:4416"))

    def test_deprecated_base_url_arg_is_honoured(self):
        urls = _pot_provider_urls({
            "extractor_args": {"youtube": {"getpot_bgutil_baseurl": ["http://pot:4416"]}},
        })
        self.assertEqual(urls, ("http://127.0.0.1:4416", "http://pot:4416"))

    def test_unrelated_extractor_args_are_ignored(self):
        urls = _pot_provider_urls({
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        })
        self.assertEqual(urls, ("http://127.0.0.1:4416",))

    def test_malformed_extractor_args_do_not_raise(self):
        # YTDL_OPTIONS is operator-supplied JSON and reaches here unvalidated.
        for opts in (
            {"extractor_args": None},
            {"extractor_args": "youtube:player_client=web"},
            {"extractor_args": {"youtubepot-bgutilhttp": "http://pot:4416"}},
            {"extractor_args": {"youtubepot-bgutilhttp": {"base_url": []}}},
        ):
            with self.subTest(opts=opts):
                self.assertEqual(_pot_provider_urls(opts), ("http://127.0.0.1:4416",))


if __name__ == "__main__":

    unittest.main()
