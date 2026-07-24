import os
import shutil
import yt_dlp
import collections
import collections.abc
import copy
import pickle
from collections import OrderedDict
import time
import asyncio
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import logging
import re
import signal
import sys
import types
from typing import Any, Optional

import yt_dlp.networking.impersonate
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import STR_FORMAT_RE_TMPL, STR_FORMAT_TYPES
import bg_tasks
from dl_formats import get_format, get_opts, AUDIO_FORMATS, merge_ytdl_option_layers
from music_metadata import MusicMetadataPreProcessor
from datetime import datetime
from state_store import AtomicJsonStore, from_json_compatible, read_legacy_shelf, to_json_compatible
from subscriptions import _entry_id
from url_guard import validate_url, install_socket_guard
from urllib.parse import urlsplit

log = logging.getLogger('ytdl')

# Python 3.14 switches the default multiprocessing start method on Linux
# (this app's only supported deployment target, per the Dockerfile) from fork
# to forkserver. Download._download relies on inheriting process state the
# way fork provides, so pin it back on Linux specifically.
#
# This must NOT be widened to "prefer fork wherever available": on macOS the
# platform default has long been spawn (never fork) precisely because forking
# a multi-threaded parent is hazardous — inherited locks held by threads that
# vanish in the child can deadlock it silently before it does any work. This
# app creates background threads (executors, notifier callbacks) well before
# any download starts, so forcing fork there reproduces exactly that hazard.
_MP_CTX = (
    multiprocessing.get_context("fork")
    if sys.platform.startswith("linux") and "fork" in multiprocessing.get_all_start_methods()
    else multiprocessing.get_context()
)

# Grace period between SIGINT (lets yt-dlp/ffmpeg finalize the partial file,
# e.g. when cancelling a livestream) and SIGKILL escalation.
_CANCEL_GRACE_SECONDS = 15

_LIVE_CHECK_INTERVAL = 60
_LIVE_MAX_CHECK_INTERVAL = 3600
# Consecutive probe failures (network blips, rate limits, transient extractor
# errors) tolerated before a scheduled live download is abandoned as errored.
_LIVE_PROBE_MAX_FAILURES = 5


class _AlbumArtistPostProcessor(PostProcessor):
    """Fill missing album-artist metadata from yt-dlp's album-level signals."""

    _TOPIC_SUFFIX = ' - Topic'

    @staticmethod
    def _has_value(value: Any) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple)):
            return any(_AlbumArtistPostProcessor._has_value(item) for item in value)
        return value is not None

    @staticmethod
    def _main_artist(info) -> Optional[str]:
        artists = info.get('artists')
        candidates = artists if isinstance(artists, list) else [info.get('artist')]
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            # YouTube Music uses a spaced middle dot between credited artists.
            # The first credit is the primary artist for normal albums.
            return candidate.split(' · ', 1)[0].strip()
        return None

    @classmethod
    def _topic_artist(cls, info) -> Optional[str]:
        for field in ('channel', 'uploader'):
            value = info.get(field)
            if not isinstance(value, str) or not value.endswith(cls._TOPIC_SUFFIX):
                continue
            if artist := value[:-len(cls._TOPIC_SUFFIX)].strip():
                return artist
        return None

    def run(self, info):
        if not self._has_value(info.get('album')):
            return [], info
        if self._has_value(info.get('album_artist')) or self._has_value(info.get('album_artists')):
            return [], info

        if artist := self._topic_artist(info) or self._main_artist(info):
            info['album_artist'] = artist
        return [], info


def _is_within_directory(real_base: str, real_target: str) -> bool:
    """True if ``real_target`` is inside (or equal to) ``real_base``.

    Both arguments must already be resolved with ``os.path.realpath``. Uses
    ``commonpath`` rather than ``startswith`` so a sibling directory sharing a
    name prefix (e.g. base ``/downloads`` vs ``/downloads-secret``) cannot be
    reached via ``../downloads-secret``.
    """
    try:
        return os.path.commonpath([real_base, real_target]) == real_base
    except ValueError:
        # Raised when paths are on different drives (Windows) or mix
        # absolute/relative; treat as outside the base directory.
        return False


# Characters that are invalid in Windows/NTFS path components. These are pre-
# sanitised when substituting playlist/channel titles into output templates so
# that downloads do not fail on NTFS-mounted volumes or Windows Docker hosts.
_WINDOWS_INVALID_PATH_CHARS = re.compile(r'[\\:*?"<>|]')
_PATH_SEP_OR_TRAVERSAL = re.compile(r'[\\/]|\.\.')


def _sanitize_path_component(value: Any) -> Any:
    """Replace characters that are invalid in Windows path components with '_'.

    Non-string values (int, float, None, …) are passed through unchanged so
    that numeric format specs (e.g. ``%(playlist_index)02d``) still work.
    Only string values are sanitised because Windows-invalid characters are
    only a concern for human-readable strings (titles, channel names, etc.)
    that may end up as directory names.  Path separators and ``..`` segments
    are also collapsed so attacker-controlled playlist/channel titles cannot
    escape the download directory via the output template.
    """
    if not isinstance(value, str):
        return value
    value = _WINDOWS_INVALID_PATH_CHARS.sub('_', value)
    value = _PATH_SEP_OR_TRAVERSAL.sub('_', value)
    return value.lstrip('.').strip() or '_'


class _ConfinedYoutubeDL(yt_dlp.YoutubeDL):
    """A ``YoutubeDL`` that refuses to emit any output path outside the allowed roots.

    This is the single authoritative enforcement of MeTube's download-directory
    containment invariant. yt-dlp expands output templates at download time using
    metadata that is fully attacker-controlled (``%(title)s``, ``%(uploader)s``,
    ``%(section_title)s`` from chapter titles, …) and, on POSIX hosts, does *not*
    neutralise a ``..`` path component — so any template segment resolving to
    ``..`` next to a literal separator (or an absolute template) can traverse out
    of the download directory. Every output path — main file, split-chapter files,
    thumbnails, subtitles, infojson — is produced by ``prepare_filename``, so
    validating its result here covers them all, regardless of which template or
    metadata field carries the traversal. Checking the resolved path (rather than
    the template string) is what makes this robust: the ``..`` only exists after
    expansion, so no ingress string check can see it.
    """

    def __init__(self, params=None, *, allowed_roots=(), **kwargs):
        self._allowed_roots = [os.path.realpath(r) for r in allowed_roots if r]
        super().__init__(params=params, **kwargs)

    def prepare_filename(self, *args, **kwargs):
        filename = super().prepare_filename(*args, **kwargs)
        if filename and filename != '-' and self._allowed_roots:
            resolved = os.path.realpath(filename)
            if not any(_is_within_directory(root, resolved) for root in self._allowed_roots):
                raise yt_dlp.utils.DownloadError(
                    f'Refusing to write outside the download directory: {filename}'
                )
        return filename


# Regex matching yt-dlp output-template field references, e.g. ``%(title)s``
# or ``%(playlist_index)03d``.  Built from yt-dlp's own ``STR_FORMAT_RE_TMPL``
# so that it stays in sync with upstream changes to the template syntax.
_OUTTMPL_FIELD_RE = re.compile(
    STR_FORMAT_RE_TMPL.format('[^)]+', f'[{STR_FORMAT_TYPES}ljhqBUDS]')
)


def _resolve_outtmpl_fields(template: str, info_dict: dict, prefixes: tuple[str, ...]) -> str:
    """Resolve specific fields in an output template using yt-dlp's template engine.

    Only field references whose root name starts with one of *prefixes* are
    evaluated.  All other references are left untouched so that yt-dlp can
    resolve them later during the actual download.

    This delegates to ``YoutubeDL.evaluate_outtmpl`` for each targeted field
    reference, giving access to the full yt-dlp template syntax (defaults,
    conditional formatting, math operations, datetime formatting, etc.).
    """
    matches = list(_OUTTMPL_FIELD_RE.finditer(template))
    if not matches:
        return template

    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        for match in reversed(matches):
            key = match.group('key')
            if key is None:
                continue
            root = re.match(r'\w+', key)
            if root is None or not root.group(0).startswith(prefixes):
                continue
            resolved = ydl.evaluate_outtmpl(match.group(0), info_dict)
            template = template[:match.start()] + resolved + template[match.end():]

    return template

_MAX_ENTRY_SANITIZE_DEPTH = 64


def _sanitize_entry_for_pickle(obj, _depth=0):
    """Recursively normalize yt-dlp ``info_dict`` data so it can be stored in shelve/pickle.

    Live streams and newer yt-dlp versions may nest generators, iterators, sets, or
    non-serializable objects (e.g. locks) inside the extracted metadata. The previous
    helper only walked plain dict/list/tuple and only expanded ``types.GeneratorType``.
    """
    if _depth > _MAX_ENTRY_SANITIZE_DEPTH:
        return None
    if obj is None or isinstance(obj, (bool, int, float, str, bytes)):
        return obj
    if isinstance(obj, types.GeneratorType):
        return _sanitize_entry_for_pickle(list(obj), _depth + 1)
    if isinstance(obj, collections.abc.Mapping):
        return {k: _sanitize_entry_for_pickle(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_sanitize_entry_for_pickle(x, _depth + 1) for x in obj)
    if isinstance(obj, (set, frozenset)):
        return [_sanitize_entry_for_pickle(x, _depth + 1) for x in obj]
    if isinstance(obj, collections.deque):
        return [_sanitize_entry_for_pickle(x, _depth + 1) for x in obj]
    if isinstance(obj, collections.abc.Iterator):
        try:
            return _sanitize_entry_for_pickle(list(obj), _depth + 1)
        except Exception:
            return None
    try:
        pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        return obj
    except Exception:
        return None


def _convert_srt_to_txt_file(subtitle_path: str):
    """Convert an SRT subtitle file into plain text by stripping cue numbers/timestamps."""
    txt_path = os.path.splitext(subtitle_path)[0] + ".txt"
    try:
        with open(subtitle_path, "r", encoding="utf-8", errors="replace") as infile:
            content = infile.read()

        # Normalize newlines so cue splitting is consistent across platforms.
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        cues = []
        # The caption format may resolve to a VTT file even when srt/txt was
        # requested (yt-dlp falls back when the extractor doesn't offer the
        # requested ext). VTT header metadata (WEBVTT/NOTE/STYLE and
        # "Kind:"/"Language:" fields) only ever appears BEFORE the first timed
        # cue, so only strip it while still in that header region — otherwise a
        # real caption line like "Kind: regards" would be dropped as metadata.
        seen_cue = False
        for block in re.split(r"\n{2,}", content):
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue
            has_timing = any("-->" in line for line in lines)
            if not seen_cue and not has_timing:
                # Still in the header region: drop metadata-only blocks
                # (WEBVTT/NOTE/STYLE, or blocks made entirely of "Key: value"
                # header fields such as a standalone "Kind:/Language:" block).
                if re.match(r"^(WEBVTT|NOTE|STYLE)\b", lines[0]) or all(
                    re.match(r"^[A-Za-z][\w-]*:\s", line) for line in lines
                ):
                    continue
            if has_timing:
                seen_cue = True
            if re.fullmatch(r"\d+", lines[0]):
                lines = lines[1:]
            if lines and "-->" in lines[0]:
                lines = lines[1:]

            text_lines = []
            for line in lines:
                if "-->" in line:
                    continue
                clean_line = re.sub(r"<[^>]+>", "", line).strip()
                if clean_line:
                    text_lines.append(clean_line)
            if text_lines:
                cues.append(" ".join(text_lines))

        with open(txt_path, "w", encoding="utf-8") as outfile:
            if cues:
                outfile.write("\n".join(cues))
                outfile.write("\n")
        return txt_path
    except OSError as exc:
        log.warning(f"Failed to convert subtitle file {subtitle_path} to txt: {exc}")
        return None

class DownloadQueueNotifier:
    async def added(self, dl):
        raise NotImplementedError

    async def updated(self, dl):
        raise NotImplementedError

    async def completed(self, dl):
        raise NotImplementedError

    async def canceled(self, id):
        raise NotImplementedError

    async def cleared(self, id):
        raise NotImplementedError

class DownloadInfo:
    def __init__(
        self,
        id,
        title,
        url,
        quality,
        download_type,
        codec,
        format,
        folder,
        custom_name_prefix,
        error,
        entry,
        playlist_item_limit,
        split_by_chapters,
        chapter_template,
        subtitle_language="en",
        subtitle_mode="prefer_manual",
        ytdl_options_presets=None,
        ytdl_options_overrides=None,
        clip_start=None,
        clip_end=None,
        live_status=None,
        live_release_timestamp=None,
    ):
        self.id = id if len(custom_name_prefix) == 0 else f'{custom_name_prefix}.{id}'
        self.title = title if len(custom_name_prefix) == 0 else f'{custom_name_prefix}.{title}'
        self.url = url
        self.quality = quality
        self.download_type = download_type
        self.codec = codec
        self.format = format
        self.folder = folder
        self.custom_name_prefix = custom_name_prefix
        self.msg = self.percent = self.speed = self.eta = None
        self.status = "pending"
        self.size = None
        self.timestamp = time.time_ns()
        self.error = error
        # Strip non-pickleable values (generators, iterators, locks, etc.) for shelve
        self.entry = _sanitize_entry_for_pickle(entry) if entry is not None else None
        self.playlist_item_limit = playlist_item_limit
        self.split_by_chapters = split_by_chapters
        self.chapter_template = chapter_template
        self.subtitle_language = subtitle_language
        self.subtitle_mode = subtitle_mode
        self.ytdl_options_presets = list(ytdl_options_presets or [])
        self.ytdl_options_overrides = dict(ytdl_options_overrides or {})
        self.clip_start = clip_start
        self.clip_end = clip_end
        self.live_status = live_status
        self.live_release_timestamp = live_release_timestamp
        self.subtitle_files = []

    # Fields that are useful server-side but must not be broadcast to browser
    # clients: ``entry`` is the full yt-dlp info-dict (potentially large and
    # re-sent on every progress tick) and ``subtitle_files`` is only used
    # internally to derive the primary caption ``filename``.
    _PUBLIC_EXCLUDED_FIELDS = ("entry", "subtitle_files")

    def to_public_dict(self) -> dict:
        """Return the client-facing view, omitting server-only/bulky fields."""
        return {
            k: v
            for k, v in self.__dict__.items()
            if k not in self._PUBLIC_EXCLUDED_FIELDS
        }

    def __setstate__(self, state):
        """BACKWARD COMPATIBILITY: migrate old DownloadInfo from persistent queue files."""
        self.__dict__.update(state)
        if 'download_type' not in state:
            old_format = state.get('format', 'any')
            old_video_codec = state.get('video_codec', 'auto')
            old_quality = state.get('quality', 'best')
            old_subtitle_format = state.get('subtitle_format', 'srt')

            if old_format in AUDIO_FORMATS:
                self.download_type = 'audio'
                self.codec = 'auto'
            elif old_format == 'thumbnail':
                self.download_type = 'thumbnail'
                self.codec = 'auto'
                self.format = 'jpg'
            elif old_format == 'captions':
                self.download_type = 'captions'
                self.codec = 'auto'
                self.format = old_subtitle_format
            else:
                self.download_type = 'video'
                self.codec = old_video_codec
                if old_quality == 'best_ios':
                    self.format = 'ios'
                    self.quality = 'best'
                elif old_quality == 'audio':
                    self.download_type = 'audio'
                    self.codec = 'auto'
                    self.format = 'm4a'
                    self.quality = 'best'
            self.__dict__.pop('video_codec', None)
            self.__dict__.pop('subtitle_format', None)

        if not getattr(self, "codec", None):
            self.codec = "auto"
        if not hasattr(self, "folder"):
            self.folder = ""
        if not hasattr(self, "custom_name_prefix"):
            self.custom_name_prefix = ""
        if not hasattr(self, "playlist_item_limit"):
            self.playlist_item_limit = 0
        if not hasattr(self, "split_by_chapters"):
            self.split_by_chapters = False
        if not hasattr(self, "chapter_template"):
            self.chapter_template = ""
        if not hasattr(self, "subtitle_language"):
            self.subtitle_language = "en"
        if not hasattr(self, "subtitle_mode"):
            self.subtitle_mode = "prefer_manual"
        legacy_preset = self.__dict__.pop("ytdl_options_preset", None)
        if "ytdl_options_presets" not in self.__dict__:
            if isinstance(legacy_preset, str) and legacy_preset.strip():
                self.ytdl_options_presets = [legacy_preset.strip()]
            elif isinstance(legacy_preset, list):
                self.ytdl_options_presets = [str(x).strip() for x in legacy_preset if str(x).strip()]
            else:
                self.ytdl_options_presets = []
        if not hasattr(self, "ytdl_options_overrides"):
            self.ytdl_options_overrides = {}
        if not hasattr(self, "entry"):
            self.entry = None
        if not hasattr(self, "subtitle_files"):
            self.subtitle_files = []
        if not hasattr(self, "chapter_files"):
            self.chapter_files = []
        if not hasattr(self, "clip_start"):
            self.clip_start = None
        if not hasattr(self, "clip_end"):
            self.clip_end = None
        if not hasattr(self, "live_status"):
            self.live_status = None
        if not hasattr(self, "live_release_timestamp"):
            self.live_release_timestamp = None


_PERSISTED_DOWNLOAD_FIELDS = (
    "id",
    "title",
    "url",
    "quality",
    "download_type",
    "codec",
    "format",
    "folder",
    "custom_name_prefix",
    "playlist_item_limit",
    "split_by_chapters",
    "chapter_template",
    "subtitle_language",
    "subtitle_mode",
    "ytdl_options_presets",
    "ytdl_options_overrides",
    "clip_start",
    "clip_end",
    "live_status",
    "live_release_timestamp",
    "status",
    "timestamp",
    "error",
    "msg",
    "filename",
    "size",
    "chapter_files",
)


def _short_title_for_failed_url(url: str) -> str:
    """A concise display title for a URL that failed before yt-dlp could extract a
    real title (unsupported URL, SSRF-rejected, extraction error). The full URL
    remains available in DownloadInfo.url and the error-detail panel."""
    try:
        hostname = urlsplit(url).hostname
    except ValueError:
        hostname = None
    return hostname or url


_COMPACT_ENTRY_EXTRA_KEYS = frozenset(("n_entries", "__last_playlist_index"))


def _compact_persisted_entry(entry: Any) -> Optional[dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    compact = {
        key: value
        for key, value in entry.items()
        if key.startswith("playlist") or key.startswith("channel") or key in _COMPACT_ENTRY_EXTRA_KEYS
    }
    return compact or None


def _download_info_to_record(
    info: DownloadInfo,
    *,
    include_entry: bool,
) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key in _PERSISTED_DOWNLOAD_FIELDS:
        if hasattr(info, key):
            value = getattr(info, key)
            if value is not None:
                record[key] = to_json_compatible(value)
    if include_entry:
        compact_entry = _compact_persisted_entry(getattr(info, "entry", None))
        if compact_entry is not None:
            record["entry"] = to_json_compatible(compact_entry)
    return record


def _download_info_from_record(record: dict[str, Any]) -> DownloadInfo:
    info = DownloadInfo.__new__(DownloadInfo)
    info.__setstate__({key: from_json_compatible(value) for key, value in record.items()})
    if not hasattr(info, "msg"):
        info.msg = None
    if not hasattr(info, "percent"):
        info.percent = None
    if not hasattr(info, "speed"):
        info.speed = None
    if not hasattr(info, "eta"):
        info.eta = None
    if not hasattr(info, "status"):
        info.status = "pending"
    if not hasattr(info, "size"):
        info.size = None
    if not hasattr(info, "error"):
        info.error = None
    return info

class Download:
    manager = None

    @classmethod
    def shutdown_manager(cls):
        if cls.manager is not None:
            cls.manager.shutdown()
            cls.manager = None

    def __init__(self, download_dir, temp_dir, output_template, output_template_chapter, quality, format, ytdl_opts, info, allow_private=False):
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.output_template = output_template
        self.output_template_chapter = output_template_chapter
        self.allow_private = allow_private
        self.info = info
        self.format = get_format(
            getattr(info, 'download_type', 'video'),
            getattr(info, 'codec', 'auto'),
            format,
            quality,
        )
        self.ytdl_opts = get_opts(
            getattr(info, 'download_type', 'video'),
            getattr(info, 'codec', 'auto'),
            format,
            quality,
            ytdl_opts,
            subtitle_language=getattr(info, 'subtitle_language', 'en'),
            subtitle_mode=getattr(info, 'subtitle_mode', 'prefer_manual'),
        )
        if "impersonate" in self.ytdl_opts:
            self.ytdl_opts["impersonate"] = yt_dlp.networking.impersonate.ImpersonateTarget.from_str(self.ytdl_opts["impersonate"])
        self.canceled = False
        self.tmpfilename = None
        self.status_queue = None
        self.proc = None
        self.loop = None
        self.notifier = None
        self._executor = None

    # Minimum interval between forwarded 'downloading' progress ticks. yt-dlp
    # emits these many times per second; without throttling, each active
    # download broadcasts hundreds of socket.io events/sec to every client.
    _PROGRESS_THROTTLE_SECONDS = 0.5

    def _make_progress_hook(self):
        last_forward = 0.0

        def put_status(st):
            nonlocal last_forward
            if st.get('status') == 'downloading':
                now = time.monotonic()
                if now - last_forward < self._PROGRESS_THROTTLE_SECONDS:
                    return
                last_forward = now
            self.status_queue.put({k: v for k, v in st.items() if k in (
                'tmpfilename',
                'filename',
                'status',
                'msg',
                'total_bytes',
                'total_bytes_estimate',
                'downloaded_bytes',
                'speed',
                'eta',
            )})

        return put_status

    def _make_youtube_dl(self, params):
        ydl = _ConfinedYoutubeDL(
            params=params,
            allowed_roots=(self.download_dir, self.temp_dir),
        )
        if getattr(self.info, 'download_type', '') == 'audio':
            ydl.add_post_processor(_AlbumArtistPostProcessor(ydl), when='pre_process')
            ydl.add_post_processor(
                MusicMetadataPreProcessor(
                    ydl,
                    source_entry=getattr(self.info, 'entry', None),
                ),
                when='pre_process',
            )
        return ydl

    def _download(self):
        # Run in our own process group so cancel() can SIGKILL the whole
        # group (yt-dlp + any ffmpeg children it spawned for merge/postproc),
        # instead of orphaning ffmpeg when only the yt-dlp process is killed.
        if hasattr(os, 'setpgrp'):
            try:
                os.setpgrp()
            except OSError:
                pass
        # Re-validate every outbound connection at fetch time. validate_url only
        # saw the submitted URL string; this catches redirects and DNS rebinding
        # to internal hosts (cloud metadata, RFC1918) that it cannot. Skipped when
        # ALLOW_PRIVATE_ADDRESSES trusts the environment (e.g. Fake-IP proxies).
        install_socket_guard(self.allow_private)
        log.info(f"Starting download for: {self.info.title} ({self.info.url})")
        try:
            debug_logging = logging.getLogger().isEnabledFor(logging.DEBUG)
            put_status = self._make_progress_hook()

            def put_status_postprocessor(d):
                if d['postprocessor'] == 'MoveFiles' and d['status'] == 'finished':
                    filepath = d['info_dict']['filepath']
                    if '__finaldir' in d['info_dict']:
                        finaldir = d['info_dict']['__finaldir']
                        filename = os.path.join(finaldir, os.path.basename(filepath))
                    else:
                        filename = filepath
                    self.status_queue.put({'status': 'finished', 'filename': filename})
                    # For captions-only downloads, yt-dlp may still report a media-like
                    # filepath in MoveFiles. Capture subtitle outputs explicitly so the
                    # UI can link to real caption files.
                    if getattr(self.info, 'download_type', '') == 'captions':
                        requested_subtitles = d.get('info_dict', {}).get('requested_subtitles', {}) or {}
                        for subtitle in requested_subtitles.values():
                            if isinstance(subtitle, dict) and subtitle.get('filepath'):
                                self.status_queue.put({'subtitle_file': subtitle['filepath']})

                # Capture all chapter files when SplitChapters finishes
                elif d.get('postprocessor') == 'SplitChapters' and d.get('status') == 'finished':
                    chapters = d.get('info_dict', {}).get('chapters', [])
                    if chapters:
                        for chapter in chapters:
                            if isinstance(chapter, dict) and 'filepath' in chapter:
                                log.info(f"Captured chapter file: {chapter['filepath']}")
                                self.status_queue.put({'chapter_file': chapter['filepath']})
                    else:
                        log.warning("SplitChapters finished but no chapter files found in info_dict")

            ytdl_params = {
                'quiet': not debug_logging,
                'verbose': debug_logging,
                'no_color': True,
                'paths': {"home": self.download_dir, "temp": self.temp_dir},
                'outtmpl': { "default": self.output_template, "chapter": self.output_template_chapter },
                'format': self.format,
                'socket_timeout': 30,
                'ignore_no_formats_error': True,
                'progress_hooks': [put_status],
                'postprocessor_hooks': [put_status_postprocessor],
                **self.ytdl_opts,
            }

            # Add chapter splitting options if enabled
            if self.info.split_by_chapters:
                ytdl_params['outtmpl']['chapter'] = self.info.chapter_template
                if 'postprocessors' not in ytdl_params:
                    ytdl_params['postprocessors'] = []
                ytdl_params['postprocessors'].append({
                    'key': 'FFmpegSplitChapters',
                    'force_keyframes': False
                })

            clip_start = getattr(self.info, 'clip_start', None)
            clip_end = getattr(self.info, 'clip_end', None)
            if clip_start is not None or clip_end is not None:
                start = float(clip_start) if clip_start is not None else 0.0
                end = float(clip_end) if clip_end is not None else float('inf')
                ytdl_params['download_ranges'] = yt_dlp.utils.download_range_func(
                    None,
                    [(start, end)],
                )

            ret = self._make_youtube_dl(ytdl_params).download([self.info.url])
            self.status_queue.put({'status': 'finished' if ret == 0 else 'error'})
            log.info(f"Finished download for: {self.info.title}")
        except yt_dlp.utils.YoutubeDLError as exc:
            log.error(f"Download error for {self.info.title}: {str(exc)}")
            self.status_queue.put({'status': 'error', 'msg': str(exc)})

    async def start(self, notifier, executor=None):
        log.info(f"Preparing download for: {self.info.title}")
        if Download.manager is None:
            Download.manager = _MP_CTX.Manager()
        self.status_queue = Download.manager.Queue()
        self.proc = _MP_CTX.Process(target=self._download)
        self.proc.start()
        self.loop = asyncio.get_running_loop()
        self.notifier = notifier
        self._executor = executor
        self.info.status = 'preparing'
        await self.notifier.updated(self.info)
        self.status_task = asyncio.create_task(self.update_status())
        await self.loop.run_in_executor(self._executor, self.proc.join)
        # Signal update_status to stop and wait for it to finish
        # so that all status updates (including MoveFiles with correct
        # file size) are processed before _post_download_cleanup runs.
        if self.status_queue is not None:
            self.status_queue.put(None)
        await self.status_task

    def _signal_group(self, sig):
        """Send *sig* to the download's process group, falling back to the
        process itself. Returns True if a signal was delivered.

        Only signal the whole group when the child actually became its own
        group leader via os.setpgrp() in _download() — that sets its pgid
        equal to its own pid. If it hasn't run setpgrp() yet, or setpgrp()
        failed, its pgid is still the SERVER's group and killpg would signal
        the entire MeTube process (PID 1 in Docker). Fall back to signalling
        just the child process by pid in that case.
        """
        try:
            pgid = os.getpgid(self.proc.pid)
            if pgid == self.proc.pid:
                os.killpg(pgid, sig)
                return True
        except (OSError, AttributeError):
            pass
        try:
            if sig == signal.SIGINT:
                os.kill(self.proc.pid, sig)
            else:
                self.proc.kill()
            return True
        except Exception as e:
            log.error(f"Error signalling process for {self.info.title}: {e}")
            return False

    def _kill_if_alive(self):
        if self.running():
            log.info(f"Escalating cancel to SIGKILL for: {self.info.title}")
            self._signal_group(signal.SIGKILL)

    def cancel(self):
        log.info(f"Cancelling download: {self.info.title}")
        if self.running():
            # SIGINT first so yt-dlp/ffmpeg can finalize the partial file
            # (livestream recordings stay playable); SIGKILL after a grace
            # period if the process ignores it.
            interrupted = self._signal_group(signal.SIGINT)
            if interrupted and self.loop is not None:
                self.loop.call_later(_CANCEL_GRACE_SECONDS, self._kill_if_alive)
            else:
                self._kill_if_alive()
        self.canceled = True
        if self.status_queue is not None:
            self.status_queue.put(None)

    def close(self):
        log.info(f"Closing download process for: {self.info.title}")
        try:
            if self.started():
                self.proc.close()
        finally:
            self.status_queue = None

    def running(self):
        try:
            return self.proc is not None and self.proc.is_alive()
        except ValueError:
            return False

    def started(self):
        return self.proc is not None

    async def update_status(self):
        while True:
            try:
                status = await self.loop.run_in_executor(self._executor, self.status_queue.get)
            except RuntimeError:
                # The download executor was shut down (server shutting down);
                # stop polling instead of raising a noisy background-task error.
                log.info(f"Status polling stopped (executor shut down) for: {self.info.title}")
                return
            if status is None:
                log.info(f"Status update finished for: {self.info.title}")
                return
            if self.canceled:
                log.info(f"Download {self.info.title} is canceled; stopping status updates.")
                return
            self.tmpfilename = status.get('tmpfilename')
            if 'filename' in status:
                fileName = status.get('filename')
                rel_name = os.path.relpath(fileName, self.download_dir)
                # For captions mode, ignore media-like placeholders and let subtitle_file
                # statuses define the final file shown in the UI.
                if getattr(self.info, 'download_type', '') == 'captions':
                    requested_subtitle_format = str(getattr(self.info, 'format', '')).lower()
                    allowed_caption_exts = ('.txt',) if requested_subtitle_format == 'txt' else ('.vtt', '.srt', '.sbv', '.scc', '.ttml', '.dfxp')
                    if not rel_name.lower().endswith(allowed_caption_exts):
                        continue
                self.info.filename = rel_name
                self.info.size = os.path.getsize(fileName) if os.path.exists(fileName) else None
                if getattr(self.info, 'download_type', '') == 'thumbnail':
                    # The thumbnail convertor always emits a .jpg, but yt-dlp may
                    # report the pre-conversion media/thumbnail extension
                    # (.webm/.mp4/.png/.webp/...). Normalise to .jpg regardless.
                    self.info.filename = os.path.splitext(self.info.filename)[0] + '.jpg'

            # Handle chapter files
            log.debug(f"Update status for {self.info.title}: {status}")
            if 'chapter_file' in status:
                chapter_file = status.get('chapter_file')
                if not hasattr(self.info, 'chapter_files'):
                    self.info.chapter_files = []
                rel_path = os.path.relpath(chapter_file, self.download_dir)
                file_size = os.path.getsize(chapter_file) if os.path.exists(chapter_file) else None
                #Postprocessor hook called multiple times with chapters. Only insert if not already present.
                existing = next((cf for cf in self.info.chapter_files if cf['filename'] == rel_path), None)
                if not existing:
                    self.info.chapter_files.append({'filename': rel_path, 'size': file_size})
                # Skip the rest of status processing for chapter files
                continue

            if 'subtitle_file' in status:
                subtitle_file = status.get('subtitle_file')
                if not subtitle_file:
                    continue
                subtitle_output_file = subtitle_file

                # txt mode is derived from SRT by stripping cue metadata.
                if getattr(self.info, 'download_type', '') == 'captions' and str(getattr(self.info, 'format', '')).lower() == 'txt':
                    converted_txt = _convert_srt_to_txt_file(subtitle_file)
                    if converted_txt:
                        subtitle_output_file = converted_txt
                        if converted_txt != subtitle_file:
                            try:
                                os.remove(subtitle_file)
                            except OSError as exc:
                                log.debug(f"Could not remove temporary SRT file {subtitle_file}: {exc}")

                rel_path = os.path.relpath(subtitle_output_file, self.download_dir)
                file_size = os.path.getsize(subtitle_output_file) if os.path.exists(subtitle_output_file) else None
                existing = next((sf for sf in self.info.subtitle_files if sf['filename'] == rel_path), None)
                if not existing:
                    self.info.subtitle_files.append({'filename': rel_path, 'size': file_size})
                # Prefer first subtitle file as the primary result link in captions mode.
                if getattr(self.info, 'download_type', '') == 'captions' and (
                    not getattr(self.info, 'filename', None) or
                    str(getattr(self.info, 'format', '')).lower() == 'txt'
                ):
                    self.info.filename = rel_path
                    self.info.size = file_size
                continue

            self.info.status = status['status']
            self.info.msg = status.get('msg')
            if 'downloaded_bytes' in status:
                total = status.get('total_bytes') or status.get('total_bytes_estimate')
                if total:
                    self.info.percent = status['downloaded_bytes'] / total * 100
            self.info.speed = status.get('speed')
            self.info.eta = status.get('eta')
            log.debug(f"Updating status for {self.info.title}: {status}")
            await self.notifier.updated(self.info)

class PersistentQueue:
    def __init__(self, name, path):
        self.identifier = name
        pdir = os.path.dirname(path)
        if pdir and not os.path.isdir(pdir):
            os.makedirs(pdir, exist_ok=True)
        self.legacy_path = path
        self.path = f"{path}.json"
        self.store = AtomicJsonStore(self.path, kind=f"persistent_queue:{name}")
        self.dict = OrderedDict()

    def load(self):
        for k, v in self.saved_items():
            self.dict[k] = Download(None, None, None, None, getattr(v, 'quality', 'best'), getattr(v, 'format', 'any'), {}, v)

    def exists(self, key):
        return key in self.dict

    def get(self, key):
        return self.dict[key]

    def items(self):
        return self.dict.items()

    def saved_items(self):
        items = [
            (item["key"], _download_info_from_record(item["info"]))
            for item in self._load_state_items()
        ]
        return sorted(items, key=lambda item: item[1].timestamp)

    def _should_persist_entry(self, info: DownloadInfo | dict[str, Any]) -> bool:
        # Failed downloads need their compact playlist/channel context so a
        # retry after a server restart still resolves the original outtmpl.
        # Successful completed entries continue to omit extractor metadata.
        status = info.get("status") if isinstance(info, dict) else info.status
        return self.identifier != "completed" or status == "error"

    def _serialize_items(self):
        return [
            {
                "key": key,
                "info": _download_info_to_record(
                    download.info,
                    include_entry=self._should_persist_entry(download.info),
                ),
            }
            for key, download in self.dict.items()
        ]

    def _save_dict(self):
        self.store.save({"items": self._serialize_items()})

    def _load_state_items(self):
        payload = self.store.load()
        if payload is not None:
            items = payload.get("items")
            if isinstance(items, list):
                compact_items = [
                    {
                        "key": item["key"],
                        "info": _download_info_to_record(
                            _download_info_from_record(item["info"]),
                            include_entry=self._should_persist_entry(item["info"]),
                        ),
                    }
                    for item in items
                    if isinstance(item, dict) and "key" in item and "info" in item
                ]
                if payload.get("schema_version") != self.store.schema_version or compact_items != items:
                    self.store.save({"items": compact_items})
                return compact_items
            log.warning("PersistentQueue:%s state file did not contain an items list", self.identifier)
            return []

        legacy_items = read_legacy_shelf(self.legacy_path)
        if legacy_items is None:
            return []

        items = [
            {
                "key": key,
                "info": _download_info_to_record(
                    value,
                    include_entry=self._should_persist_entry(value),
                ),
            }
            for key, value in sorted(legacy_items, key=lambda item: item[1].timestamp)
        ]
        self.store.save({"items": items})
        return items

    def put(self, value):
        key = value.info.url
        old = self.dict.get(key)
        self.dict[key] = value
        try:
            self._save_dict()
        except Exception:
            if old is None:
                del self.dict[key]
            else:
                self.dict[key] = old
            raise

    def delete(self, key):
        if key in self.dict:
            old = self.dict[key]
            del self.dict[key]
            try:
                self._save_dict()
            except Exception:
                self.dict[key] = old
                raise

    def empty(self):
        return not bool(self.dict)

class DownloadQueue:
    def __init__(self, config, notifier):
        self.config = config
        self.notifier = notifier
        self.queue = PersistentQueue("queue", self.config.STATE_DIR + '/queue')
        self.done = PersistentQueue("completed", self.config.STATE_DIR + '/completed')
        self.pending = PersistentQueue("pending", self.config.STATE_DIR + '/pending')
        self.active_downloads = set()
        self.semaphore = asyncio.Semaphore(int(self.config.MAX_CONCURRENT_DOWNLOADS))
        # Each active download parks two threads for its whole duration
        # (proc.join + status_queue.get). A dedicated pool keeps those from
        # starving the default executor, which extract_info/live-probes also use.
        self._download_executor = ThreadPoolExecutor(
            max_workers=2 * int(self.config.MAX_CONCURRENT_DOWNLOADS) + 2,
            thread_name_prefix="dl",
        )
        self.done.load()
        self._add_generation = 0
        self._canceled_urls = set()  # URLs canceled during current playlist add
        self._scheduled_probe_at: dict[str, float] = {}
        self._scheduled_probe_failures: dict[str, int] = {}
        self._live_monitor_task: Optional[asyncio.Task] = None
        self._live_monitor_wakeup = asyncio.Event()

    def cancel_add(self):
        self._add_generation += 1
        log.info('Playlist add operation canceled by user')

    @staticmethod
    def __is_channel_extraction(entry):
        """Return True when yt-dlp reported a channel tab as a playlist.

        YouTube channel tabs are extracted with ``_type: 'playlist'`` but set
        ``id`` equal to ``channel_id``; real playlists keep a distinct id.
        """
        channel_id = entry.get('channel_id')
        return bool(channel_id) and entry.get('id') == channel_id

    async def __import_queue(self):
        for k, v in self.queue.saved_items():
            await self.__add_download(v, True)

    async def __import_pending(self):
        for k, v in self.pending.saved_items():
            await self.__add_download(v, False)

    async def initialize(self):
        log.info("Initializing DownloadQueue")
        self._start_live_monitor()
        bg_tasks.create_task(self.__import_queue(), name="import_queue")
        bg_tasks.create_task(self.__import_pending(), name="import_pending")

    def _start_live_monitor(self) -> None:
        if self._live_monitor_task is not None and not self._live_monitor_task.done():
            return
        # bg_tasks.create_task already logs unexpected task failures with the name.
        self._live_monitor_task = bg_tasks.create_task(self._live_monitor_loop(), name="live_monitor")

    def _register_scheduled(self, download: Download) -> None:
        self._scheduled_probe_at[download.info.url] = 0
        self._scheduled_probe_failures.pop(download.info.url, None)
        self._start_live_monitor()
        self._wake_live_monitor()

    def _unregister_scheduled(self, url: str) -> None:
        self._scheduled_probe_at.pop(url, None)
        self._scheduled_probe_failures.pop(url, None)

    def _wake_live_monitor(self) -> None:
        try:
            self._live_monitor_wakeup.set()
        except RuntimeError:
            pass

    def _probe_interval_seconds(self, release_timestamp: Any) -> float:
        if release_timestamp is not None:
            try:
                diff = float(release_timestamp) - time.time()
                if diff > 0:
                    return max(_LIVE_CHECK_INTERVAL, min(diff, _LIVE_MAX_CHECK_INTERVAL))
            except (TypeError, ValueError):
                pass
        return float(_LIVE_CHECK_INTERVAL)

    def _seconds_until_next_probe(self) -> Optional[float]:
        """Time until the earliest scheduled probe, or None when nothing is scheduled."""
        if not self._scheduled_probe_at:
            return None
        return max(0.0, min(self._scheduled_probe_at.values()) - time.time())

    async def _live_monitor_loop(self) -> None:
        while True:
            timeout = self._seconds_until_next_probe()
            try:
                await asyncio.wait_for(self._live_monitor_wakeup.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            self._live_monitor_wakeup.clear()
            now = time.time()
            due: list[Download] = []
            for url, probe_at in list(self._scheduled_probe_at.items()):
                if now < probe_at:
                    continue
                if not self.queue.exists(url):
                    self._unregister_scheduled(url)
                    continue
                download = self.queue.get(url)
                if download.info.status != 'scheduled' or download.canceled:
                    self._unregister_scheduled(url)
                    continue
                due.append(download)
            for download in due:
                try:
                    await self._probe_scheduled_download(download)
                except Exception as exc:
                    # Defensive: _probe_scheduled_download handles its own errors,
                    # but never let an unexpected failure leave probe_at in the past
                    # (which would spin this loop) or kill the monitor task.
                    log.exception("Scheduled live probe crashed for %s: %s", download.info.url, exc)
                    if download.info.url in self._scheduled_probe_at:
                        self._scheduled_probe_at[download.info.url] = time.time() + _LIVE_CHECK_INTERVAL

    async def _probe_scheduled_download(self, download: Download) -> None:
        url = download.info.url
        info = download.info
        if info.status != 'scheduled' or download.canceled:
            self._unregister_scheduled(url)
            return

        try:
            entry = await asyncio.get_running_loop().run_in_executor(
                None,
                partial(
                    self.__extract_info,
                    url,
                    getattr(info, 'ytdl_options_presets', None),
                    getattr(info, 'ytdl_options_overrides', {}) or {},
                ),
            )
        except Exception as exc:
            # Treat all probe failures (transient network blips, rate limits,
            # extractor errors) as recoverable up to a point: retry on the next
            # interval and only give up after repeated consecutive failures so a
            # momentary glitch doesn't abandon a stream the user is waiting for.
            fails = self._scheduled_probe_failures.get(url, 0) + 1
            self._scheduled_probe_failures[url] = fails
            if fails >= _LIVE_PROBE_MAX_FAILURES:
                log.warning(
                    "Giving up on scheduled live probe for %s after %d consecutive failures: %s",
                    info.title, fails, exc,
                )
                info.status = 'error'
                info.msg = str(exc)
                if not info.error:
                    info.error = str(exc)
                self._unregister_scheduled(url)
                self.queue.delete(url)
                self.done.put(download)
                await self.notifier.completed(info)
            else:
                log.warning(
                    "Scheduled live probe failed for %s (attempt %d/%d), will retry: %s",
                    info.title, fails, _LIVE_PROBE_MAX_FAILURES, exc,
                )
                self._scheduled_probe_at[url] = time.time() + _LIVE_CHECK_INTERVAL
            return

        # Successful probe resets the transient-failure streak.
        self._scheduled_probe_failures.pop(url, None)

        release_ts = entry.get('release_timestamp')
        live_status = entry.get('live_status')
        if release_ts is not None:
            info.live_release_timestamp = release_ts
        if live_status is not None:
            info.live_status = live_status

        if live_status == 'is_upcoming':
            self._scheduled_probe_at[url] = time.time() + self._probe_interval_seconds(release_ts)
            await self.notifier.updated(info)
            return

        self._unregister_scheduled(url)
        info.status = 'pending'
        # Clear the "scheduled to start at ..." placeholder now that the stream
        # is live and a real download is about to begin.
        info.error = None
        info.msg = None
        await self.notifier.updated(info)
        bg_tasks.create_task(self.__start_download(download), name="start_download")

    def _schedule_upcoming_download(self, download: Download) -> None:
        download.info.status = 'scheduled'
        self.queue.put(download)
        self._register_scheduled(download)

    def _force_start_scheduled(self, download: Download) -> None:
        self._unregister_scheduled(download.info.url)
        download.info.status = 'pending'
        download.info.error = None
        download.info.msg = None
        bg_tasks.create_task(self.__start_download(download), name="start_download")

    async def __start_download(self, download):
        if download.canceled:
            log.info(f"Download {download.info.title} was canceled, skipping start.")
            return
        async with self.semaphore:
            if download.canceled:
                log.info(f"Download {download.info.title} was canceled, skipping start.")
                return
            await download.start(self.notifier, self._download_executor)
            self._post_download_cleanup(download)

    def _post_download_cleanup(self, download):
        if download.info.status != 'finished':
            if download.tmpfilename and os.path.isfile(download.tmpfilename):
                try:
                    os.remove(download.tmpfilename)
                except OSError:
                    pass
            download.info.status = 'error'
            # A progress tick may have set filename to a temp-directory
            # relative path before the error occurred; clear it so the UI
            # doesn't render a broken link (or, worse, so a later trashcan
            # delete doesn't act on a path outside the download directory).
            # Captions downloads may still have captured valid subtitle
            # files even when the overall status is 'error' — keep those.
            has_captured_subtitles = bool(getattr(download.info, 'subtitle_files', None))
            if not (download.info.download_type == 'captions' and has_captured_subtitles):
                download.info.filename = None
                download.info.size = None
        download.close()
        if self.queue.exists(download.info.url):
            self.queue.delete(download.info.url)
            if download.canceled:
                bg_tasks.create_task(self.notifier.canceled(download.info.url), name="notify_canceled")
            else:
                self.done.put(download)
                bg_tasks.create_task(self.notifier.completed(download.info), name="notify_completed")
                try:
                    clear_after = int(self.config.CLEAR_COMPLETED_AFTER)
                except ValueError:
                    log.error(f'CLEAR_COMPLETED_AFTER is set to an invalid value "{self.config.CLEAR_COMPLETED_AFTER}", expected an integer number of seconds')
                    clear_after = 0
                if clear_after > 0:
                    # bg_tasks.create_task already logs unexpected task failures.
                    bg_tasks.create_task(
                        self.__auto_clear_after_delay(download.info.url, clear_after),
                        name="auto_clear",
                    )

    async def __auto_clear_after_delay(self, url, delay_seconds):
        await asyncio.sleep(delay_seconds)
        if self.done.exists(url):
            log.debug(f'Auto-clearing completed download: {url}')
            await self.clear([url])

    def _build_ytdl_options(self, ytdl_options_presets=None, ytdl_options_overrides=None):
        """Merge global options, presets (in order), and per-download overrides."""
        opts = dict(self.config.YTDL_OPTIONS)
        opts.update(merge_ytdl_option_layers(
            ytdl_options_presets, ytdl_options_overrides, self.config.YTDL_OPTIONS_PRESETS
        ))
        return opts

    def __extract_info(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
        # NOTE: extraction runs in the main process, so the connect-time socket
        # guard (installed only in the download subprocess) does not apply here.
        # The ingress validate_url check guards the submitted URL, but redirects
        # followed during extraction are not re-validated. See url_guard's module
        # docstring for why the guard can't be installed process-wide.
        debug_logging = logging.getLogger().isEnabledFor(logging.DEBUG)
        user_opts = self._build_ytdl_options(ytdl_options_presets, ytdl_options_overrides)
        params = {
            **user_opts,
            'quiet': not debug_logging,
            'verbose': debug_logging,
            'no_color': True,
            'extract_flat': True,
            'ignore_no_formats_error': True,
            'noplaylist': True,
            'paths': {"home": self.config.DOWNLOAD_DIR, "temp": self.config.TEMP_DIR},
        }
        imp = user_opts.get('impersonate')
        if imp is not None:
            params['impersonate'] = yt_dlp.networking.impersonate.ImpersonateTarget.from_str(imp)
        return yt_dlp.YoutubeDL(params=params).extract_info(url, download=False)

    def __calc_download_path(self, download_type, folder):
        base_directory = self.config.AUDIO_DOWNLOAD_DIR if download_type == 'audio' else self.config.DOWNLOAD_DIR
        if folder:
            if not self.config.CUSTOM_DIRS:
                return None, {'status': 'error', 'msg': 'A folder for the download was specified but CUSTOM_DIRS is not true in the configuration.'}
            dldirectory = os.path.realpath(os.path.join(base_directory, folder))
            real_base_directory = os.path.realpath(base_directory)
            if not _is_within_directory(real_base_directory, dldirectory):
                return None, {'status': 'error', 'msg': f'Folder "{folder}" must resolve inside the base download directory "{real_base_directory}"'}
            if not os.path.isdir(dldirectory):
                if not self.config.CREATE_CUSTOM_DIRS:
                    return None, {'status': 'error', 'msg': f'Folder "{folder}" for download does not exist inside base directory "{real_base_directory}", and CREATE_CUSTOM_DIRS is not true in the configuration.'}
                os.makedirs(dldirectory, exist_ok=True)
        else:
            dldirectory = base_directory
        return dldirectory, None

    async def __add_download(self, dl, auto_start):
        dldirectory, error_message = self.__calc_download_path(dl.download_type, dl.folder)
        if error_message is not None:
            return error_message
        output = self.config.OUTPUT_TEMPLATE if len(dl.custom_name_prefix) == 0 else f'{dl.custom_name_prefix}.{self.config.OUTPUT_TEMPLATE}'
        output_chapter = self.config.OUTPUT_TEMPLATE_CHAPTER
        entry = getattr(dl, 'entry', None)
        if entry is not None and entry.get('playlist_index') is not None:
            if len(self.config.OUTPUT_TEMPLATE_PLAYLIST):
                output = self.config.OUTPUT_TEMPLATE_PLAYLIST
            sanitized = {k: _sanitize_path_component(v) for k, v in entry.items()}
            output = _resolve_outtmpl_fields(output, sanitized, ('playlist',))
        if entry is not None and entry.get('channel_index') is not None:
            if len(self.config.OUTPUT_TEMPLATE_CHANNEL):
                output = self.config.OUTPUT_TEMPLATE_CHANNEL
            sanitized = {k: _sanitize_path_component(v) for k, v in entry.items()}
            output = _resolve_outtmpl_fields(output, sanitized, ('channel',))
        ytdl_options = self._build_ytdl_options(
            getattr(dl, 'ytdl_options_presets', None),
            getattr(dl, 'ytdl_options_overrides', {}) or {},
        )
        playlist_item_limit = getattr(dl, 'playlist_item_limit', 0)
        if playlist_item_limit > 0:
            log.info(f'playlist limit is set. Processing only first {playlist_item_limit} entries')
            ytdl_options['playlistend'] = playlist_item_limit
        download = Download(dldirectory, self.config.TEMP_DIR, output, output_chapter, dl.quality, dl.format, ytdl_options, dl, allow_private=self.config.ALLOW_PRIVATE_ADDRESSES)
        is_upcoming = (
            getattr(dl, 'live_status', None) == 'is_upcoming'
            or getattr(dl, 'status', None) == 'scheduled'
        )
        if auto_start is True:
            if is_upcoming:
                self._schedule_upcoming_download(download)
            else:
                self.queue.put(download)
                bg_tasks.create_task(self.__start_download(download), name="start_download")
        else:
            self.pending.put(download)
        await self.notifier.added(dl)

    async def __add_entry(
        self,
        entry,
        download_type,
        codec,
        format,
        quality,
        folder,
        custom_name_prefix,
        playlist_item_limit,
        auto_start,
        split_by_chapters,
        chapter_template,
        subtitle_language,
        subtitle_mode,
        ytdl_options_presets,
        ytdl_options_overrides,
        clip_start,
        clip_end,
        already,
        _add_gen=None,
    ):
        if not entry:
            return {'status': 'error', 'msg': "Invalid/empty data was given."}

        error = None
        if "live_status" in entry and "release_timestamp" in entry and entry.get("live_status") == "is_upcoming":
            # astimezone() makes this an aware datetime in the server's local
            # zone; a naive datetime's %z renders as an empty string.
            dt_ts = datetime.fromtimestamp(entry.get("release_timestamp")).astimezone().strftime('%Y-%m-%d %H:%M:%S %z')
            error = f"Live stream is scheduled to start at {dt_ts}"
        else:
            if "msg" in entry:
                error = entry["msg"]

        etype = entry.get('_type') or 'video'

        if etype.startswith('url'):
            log.debug('Processing as a url')
            return await self.add(
                entry['url'],
                download_type,
                codec,
                format,
                quality,
                folder,
                custom_name_prefix,
                playlist_item_limit,
                auto_start,
                split_by_chapters,
                chapter_template,
                subtitle_language,
                subtitle_mode,
                ytdl_options_presets,
                ytdl_options_overrides,
                clip_start,
                clip_end,
                already,
                _add_gen,
            )
        elif etype == 'playlist' or etype == 'channel':
            if etype == 'playlist' and self.__is_channel_extraction(entry):
                etype = 'channel'
            log.debug(f'Processing as a {etype}')
            entries = entry['entries']
            # Convert generator to list if needed (for len() and slicing operations)
            if isinstance(entries, types.GeneratorType):
                entries = list(entries)
            total_entries = len(entries)
            log.info(f'{etype} detected with {total_entries} entries')
            index_digits = len(str(total_entries))
            results = []
            if playlist_item_limit > 0:
                log.info(f'Item limit is set. Processing only first {playlist_item_limit} entries')
                entries = entries[:playlist_item_limit]
            for index, etr in enumerate(entries, start=1):
                if _add_gen is not None and self._add_generation != _add_gen:
                    log.info(f'Playlist add canceled after processing {len(already)} entries')
                    return {'status': 'ok', 'msg': f'Canceled - added {len(already)} items before cancel'}
                if "id" not in etr:
                    etr["id"] = _entry_id(etr)
                etr["_type"] = "video"
                if etype == 'channel':
                    etr["channel"] = (
                        entry.get("channel")
                        or entry.get("uploader")
                        or entry.get("title")
                        or entry.get("id")
                    )
                else:
                    etr["playlist"] = entry.get("id") or entry.get("channel_id") or entry.get("channel")
                etr[f"{etype}_index"] = '{{0:0{0:d}d}}'.format(index_digits).format(index)
                etr[f"{etype}_count"] = total_entries
                etr[f"{etype}_autonumber"] = index
                # n_entries: standard yt-dlp field for total count (used by template engine)
                # __last_playlist_index: yt-dlp internal field for auto-padding autonumber
                etr["n_entries"] = total_entries
                etr["__last_playlist_index"] = total_entries
                for property in ("id", "title", "uploader", "uploader_id"):
                    if property in entry:
                        etr[f"{etype}_{property}"] = entry[property]
                results.append(
                    await self.__add_entry(
                        etr,
                        download_type,
                        codec,
                        format,
                        quality,
                        folder,
                        custom_name_prefix,
                        playlist_item_limit,
                        auto_start,
                        split_by_chapters,
                        chapter_template,
                        subtitle_language,
                        subtitle_mode,
                        ytdl_options_presets,
                        ytdl_options_overrides,
                        clip_start,
                        clip_end,
                        already,
                        _add_gen,
                    )
                )
            if any(res['status'] == 'error' for res in results):
                return {'status': 'error', 'msg': ', '.join(res['msg'] for res in results if res['status'] == 'error' and 'msg' in res)}
            return {'status': 'ok'}
        elif etype == 'video':
            log.debug('Processing as a video')
            key = entry.get('webpage_url') or entry['url']
            if key in self._canceled_urls:
                log.info(f'Skipping canceled URL: {entry.get("title") or key}')
                return {'status': 'ok'}
            if self.queue.exists(key) or self.pending.exists(key):
                # Surface the skip instead of silently no-op'ing, and avoid
                # clobbering an existing pending entry's options with a
                # fresh DownloadInfo built from possibly-different args.
                title = entry.get('title') or key
                return {'status': 'ok', 'msg': f'Already in queue: {title}'}
            dl = DownloadInfo(
                id=entry['id'],
                title=entry.get('title') or entry['id'],
                url=key,
                quality=quality,
                download_type=download_type,
                codec=codec,
                format=format,
                folder=folder,
                custom_name_prefix=custom_name_prefix,
                error=error,
                entry=entry,
                playlist_item_limit=playlist_item_limit,
                split_by_chapters=split_by_chapters,
                chapter_template=chapter_template,
                subtitle_language=subtitle_language,
                subtitle_mode=subtitle_mode,
                ytdl_options_presets=ytdl_options_presets,
                ytdl_options_overrides=ytdl_options_overrides,
                clip_start=clip_start,
                clip_end=clip_end,
                live_status=entry.get('live_status'),
                live_release_timestamp=entry.get('release_timestamp'),
            )
            await self.__add_download(dl, auto_start)
            return {'status': 'ok'}
        return {'status': 'error', 'msg': f'Unsupported resource "{etype}"'}

    async def __record_add_failure(
        self,
        url,
        msg,
        download_type,
        codec,
        format,
        quality,
        folder,
        custom_name_prefix,
        playlist_item_limit,
        split_by_chapters,
        chapter_template,
        subtitle_language,
        subtitle_mode,
        ytdl_options_presets,
        ytdl_options_overrides,
        clip_start,
        clip_end,
        entry=None,
    ):
        """Surface a URL that failed before a DownloadInfo could be created (unsupported
        URL, SSRF-rejected, extraction error) as a failed entry in the done list, so the
        frontend shows it with the same red-cross/retry/error-detail treatment as a
        download that failed mid-stream, instead of only a toast and a server log line."""
        info = DownloadInfo(
            id=url,
            title=_short_title_for_failed_url(url),
            url=url,
            quality=quality,
            download_type=download_type,
            codec=codec,
            format=format,
            folder=folder,
            custom_name_prefix=custom_name_prefix,
            error=msg,
            entry=entry,
            playlist_item_limit=playlist_item_limit,
            split_by_chapters=split_by_chapters,
            chapter_template=chapter_template,
            subtitle_language=subtitle_language,
            subtitle_mode=subtitle_mode,
            ytdl_options_presets=ytdl_options_presets,
            ytdl_options_overrides=ytdl_options_overrides,
            clip_start=clip_start,
            clip_end=clip_end,
        )
        info.status = 'error'
        info.msg = msg
        download = Download(None, None, None, None, quality, format, {}, info)
        self.done.put(download)
        await self.notifier.completed(info)

    async def add(
        self,
        url,
        download_type,
        codec,
        format,
        quality,
        folder,
        custom_name_prefix,
        playlist_item_limit,
        auto_start=True,
        split_by_chapters=False,
        chapter_template=None,
        subtitle_language="en",
        subtitle_mode="prefer_manual",
        ytdl_options_presets=None,
        ytdl_options_overrides=None,
        clip_start=None,
        clip_end=None,
        already=None,
        _add_gen=None,
        retry_entry=None,
    ):
        if ytdl_options_presets is None:
            ytdl_options_presets = []
        log.info(
            f'adding {url}: {download_type=} {codec=} {format=} {quality=} {already=} {folder=} {custom_name_prefix=} '
            f'{playlist_item_limit=} {auto_start=} {split_by_chapters=} {chapter_template=} '
            f'{subtitle_language=} {subtitle_mode=} {ytdl_options_presets=} {clip_start=} {clip_end=}'
        )
        if already is None:
            _add_gen = self._add_generation
            self._canceled_urls.clear()
        already = set() if already is None else already
        if url in already:
            log.info('recursion detected, skipping')
            return {'status': 'ok'}
        else:
            already.add(url)
        # SSRF guard: reject non-http(s) schemes and hosts resolving to
        # internal/loopback/link-local/metadata addresses before yt-dlp fetches
        # anything. run_in_executor because validate_url may perform a DNS lookup.
        url_error = await asyncio.get_running_loop().run_in_executor(
            None, partial(validate_url, url, allow_private=self.config.ALLOW_PRIVATE_ADDRESSES))
        if url_error is not None:
            log.warning('Rejected URL "%s": %s', url, url_error)
            await self.__record_add_failure(
                url, url_error, download_type, codec, format, quality, folder,
                custom_name_prefix, playlist_item_limit, split_by_chapters, chapter_template,
                subtitle_language, subtitle_mode, ytdl_options_presets, ytdl_options_overrides,
                clip_start, clip_end, retry_entry,
            )
            return {'status': 'error', 'msg': url_error}
        try:
            entry = await asyncio.get_running_loop().run_in_executor(
                None,
                partial(self.__extract_info, url, ytdl_options_presets, ytdl_options_overrides),
            )
        except yt_dlp.utils.YoutubeDLError as exc:
            msg = str(exc)
            await self.__record_add_failure(
                url, msg, download_type, codec, format, quality, folder,
                custom_name_prefix, playlist_item_limit, split_by_chapters, chapter_template,
                subtitle_language, subtitle_mode, ytdl_options_presets, ytdl_options_overrides,
                clip_start, clip_end, retry_entry,
            )
            return {'status': 'error', 'msg': msg}
        retry_context = _compact_persisted_entry(retry_entry)
        if isinstance(entry, dict) and retry_context is not None:
            entry = {**entry, **copy.deepcopy(retry_context)}
        return await self.__add_entry(
            entry,
            download_type,
            codec,
            format,
            quality,
            folder,
            custom_name_prefix,
            playlist_item_limit,
            auto_start,
            split_by_chapters,
            chapter_template,
            subtitle_language,
            subtitle_mode,
            ytdl_options_presets,
            ytdl_options_overrides,
            clip_start,
            clip_end,
            already,
            _add_gen,
        )

    async def retry(self, id):
        if not self.done.exists(id):
            return {'status': 'error', 'msg': 'Failed download no longer exists.'}

        info = self.done.get(id).info
        if info.status != 'error':
            return {'status': 'error', 'msg': 'Only failed downloads can be retried.'}

        return await self.add(
            info.url,
            info.download_type,
            info.codec,
            info.format,
            info.quality,
            info.folder,
            info.custom_name_prefix,
            info.playlist_item_limit,
            True,
            info.split_by_chapters,
            info.chapter_template,
            info.subtitle_language,
            info.subtitle_mode,
            info.ytdl_options_presets,
            info.ytdl_options_overrides,
            info.clip_start,
            info.clip_end,
            retry_entry=info.entry,
        )

    async def add_entry(
        self,
        entry,
        download_type,
        codec,
        format,
        quality,
        folder,
        custom_name_prefix,
        playlist_item_limit,
        auto_start=True,
        split_by_chapters=False,
        chapter_template=None,
        subtitle_language="en",
        subtitle_mode="prefer_manual",
        ytdl_options_presets=None,
        ytdl_options_overrides=None,
        clip_start=None,
        clip_end=None,
    ):
        if ytdl_options_presets is None:
            ytdl_options_presets = []
        normalized_entry = copy.deepcopy(entry) if isinstance(entry, dict) else entry
        already = set()
        return await self.__add_entry(
            normalized_entry,
            download_type,
            codec,
            format,
            quality,
            folder,
            custom_name_prefix,
            playlist_item_limit,
            auto_start,
            split_by_chapters,
            chapter_template,
            subtitle_language,
            subtitle_mode,
            ytdl_options_presets,
            ytdl_options_overrides,
            clip_start,
            clip_end,
            already,
            None,
        )

    async def start_pending(self, ids):
        for id in ids:
            if self.pending.exists(id):
                dl = self.pending.get(id)
                self.pending.delete(id)
                if getattr(dl.info, 'live_status', None) == 'is_upcoming':
                    self._schedule_upcoming_download(dl)
                else:
                    self.queue.put(dl)
                    bg_tasks.create_task(self.__start_download(dl), name="start_download")
                continue
            if self.queue.exists(id):
                dl = self.queue.get(id)
                if dl.info.status == 'scheduled':
                    self._force_start_scheduled(dl)
                continue
            log.warning(f'requested start for non-existent download {id}')
        return {'status': 'ok'}

    async def cancel(self, ids):
        for id in ids:
            # Track URL so playlist add loop won't re-queue it
            self._canceled_urls.add(id)
            if self.pending.exists(id):
                self.pending.delete(id)
                await self.notifier.canceled(id)
                continue
            if not self.queue.exists(id):
                log.warning(f'requested cancel for non-existent download {id}')
                continue
            dl = self.queue.get(id)
            if dl.info.status == 'scheduled':
                self._unregister_scheduled(id)
            if dl.started():
                dl.cancel()
            else:
                dl.canceled = True
                self.queue.delete(id)
                await self.notifier.canceled(id)
        return {'status': 'ok'}

    async def clear(self, ids):
        for id in ids:
            if not self.done.exists(id):
                log.warning(f'requested delete for non-existent download {id}')
                continue
            if self.config.DELETE_FILE_ON_TRASHCAN:
                dl = self.done.get(id)
                dldirectory, calc_error = self.__calc_download_path(dl.info.download_type, dl.info.folder)
                if calc_error is not None or not dldirectory:
                    log.warning(f'deleting files for download {id} skipped: could not resolve download directory')
                else:
                    # Remove the primary output plus any per-chapter / per-subtitle
                    # outputs. Each filename is relative to the download directory.
                    rel_names = []
                    if getattr(dl.info, 'filename', None):
                        rel_names.append(dl.info.filename)
                    for extra in (getattr(dl.info, 'chapter_files', None) or []):
                        if isinstance(extra, dict) and extra.get('filename'):
                            rel_names.append(extra['filename'])
                    for extra in (getattr(dl.info, 'subtitle_files', None) or []):
                        if isinstance(extra, dict) and extra.get('filename'):
                            rel_names.append(extra['filename'])
                    real_base_directory = os.path.realpath(dldirectory)
                    for rel_name in rel_names:
                        full_path = os.path.realpath(os.path.join(dldirectory, rel_name))
                        if not _is_within_directory(real_base_directory, full_path):
                            log.warning(f'skipping deletion of "{rel_name}" for download {id}: resolves outside the download directory')
                            continue
                        try:
                            os.remove(full_path)
                        except FileNotFoundError:
                            pass
                        except OSError as e:
                            log.warning(f'deleting file "{rel_name}" for download {id} failed with error message {e!r}')
            self.done.delete(id)
            await self.notifier.cleared(id)
        return {'status': 'ok'}

    def get(self):
        return (list((k, v.info) for k, v in self.queue.items()) +
                list((k, v.info) for k, v in self.pending.items()),
                list((k, v.info) for k, v in self.done.items()))

    def close(self):
        # Kill any still-running download subprocesses (and their ffmpeg
        # children) before tearing down the executor, so they aren't orphaned
        # when the server exits. Their queue entries stay persisted and are
        # re-imported/restarted on next startup.
        for _key, download in list(self.queue.items()):
            if download.started() and download.running():
                download.cancel()
        self._download_executor.shutdown(wait=False, cancel_futures=True)
