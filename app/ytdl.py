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
from functools import partial
import logging
import re
import types
from typing import Any, Optional

import yt_dlp.networking.impersonate
from yt_dlp.utils import STR_FORMAT_RE_TMPL, STR_FORMAT_TYPES
from dl_formats import get_format, get_opts, AUDIO_FORMATS
from datetime import datetime
from state_store import AtomicJsonStore, from_json_compatible, read_legacy_shelf, to_json_compatible
from subscriptions import _entry_id

log = logging.getLogger('ytdl')


# Characters that are invalid in Windows/NTFS path components. These are pre-
# sanitised when substituting playlist/channel titles into output templates so
# that downloads do not fail on NTFS-mounted volumes or Windows Docker hosts.
_WINDOWS_INVALID_PATH_CHARS = re.compile(r'[\\:*?"<>|]')


def _sanitize_path_component(value: Any) -> Any:
    """Replace characters that are invalid in Windows path components with '_'.

    Non-string values (int, float, None, …) are passed through unchanged so
    that numeric format specs (e.g. ``%(playlist_index)02d``) still work.
    Only string values are sanitised because Windows-invalid characters are
    only a concern for human-readable strings (titles, channel names, etc.)
    that may end up as directory names.
    """
    if not isinstance(value, str):
        return value
    return _WINDOWS_INVALID_PATH_CHARS.sub('_', value)


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
        for block in re.split(r"\n{2,}", content):
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue
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
        self.download_phase = None
        self.size = None
        self.timestamp = time.time_ns()
        self.error = error
        self.filename = None
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
        self.chapter_files = []
        self.subtitle_files = []

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
        if not hasattr(self, "filename"):
            self.filename = None
        if not hasattr(self, "clip_start"):
            self.clip_start = None
        if not hasattr(self, "clip_end"):
            self.clip_end = None
        if not hasattr(self, "download_phase"):
            self.download_phase = None


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
    "status",
    "download_phase",
    "timestamp",
    "error",
    "msg",
    "filename",
    "size",
    "chapter_files",
)


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
    if not hasattr(info, "download_phase"):
        info.download_phase = None
    if not hasattr(info, "size"):
        info.size = None
    if not hasattr(info, "error"):
        info.error = None
    return info


def _quality_suffix_value(dl: DownloadInfo) -> str:
    quality = str(getattr(dl, 'quality', '') or '')
    download_type = getattr(dl, 'download_type', '')
    if download_type == 'video':
        if quality == 'best':
            return '%(height)sp'
        if re.fullmatch(r'\d+', quality):
            return f'{quality}p'
    if download_type == 'audio':
        if quality == 'best':
            return '%(abr).0fkbps'
        if re.fullmatch(r'\d+', quality):
            return f'{quality}kbps'
    return quality


def _codec_suffix_value(dl: DownloadInfo) -> str:
    if getattr(dl, 'download_type', '') != 'video':
        return ''

    codec_value = str(getattr(dl, 'codec', '') or '')
    if codec_value.lower() != 'auto':
        return codec_value

    entry = getattr(dl, 'entry', None) or {}
    resolved = None
    if isinstance(entry, dict):
        vc = entry.get('vcodec')
        ac = entry.get('acodec')
        if vc:
            resolved = vc
        elif ac:
            resolved = ac
        else:
            for fld in ('requested_formats', 'formats'):
                lst = entry.get(fld) or []
                if isinstance(lst, list):
                    for it in lst:
                        if isinstance(it, dict):
                            if it.get('vcodec'):
                                resolved = it.get('vcodec')
                                break
                            if it.get('acodec'):
                                resolved = it.get('acodec')
                                break
                if resolved:
                    break

    if not resolved:
        return codec_value

    resolved_value = str(resolved).lower()
    if 'avc' in resolved_value or 'h264' in resolved_value:
        return 'h264'
    if 'hevc' in resolved_value or 'h265' in resolved_value or 'h.265' in resolved_value:
        return 'h265'
    if 'av01' in resolved_value or 'av1' in resolved_value:
        return 'av1'
    if 'vp9' in resolved_value or 'vp09' in resolved_value:
        return 'vp9'
    return re.sub(r'[^0-9a-zA-Z]+', '_', resolved_value)

class Download:
    manager = None

    @classmethod
    def shutdown_manager(cls):
        if cls.manager is not None:
            cls.manager.shutdown()
            cls.manager = None

    def __init__(self, download_dir, temp_dir, output_template, output_template_chapter, quality, format, ytdl_opts, info):
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.output_template = output_template
        self.output_template_chapter = output_template_chapter
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
        self.paused = getattr(self.info, 'status', None) == 'paused'
        self.tmpfilename = None
        self.status_queue = None
        self.proc = None
        self.loop = None
        self.notifier = None
        self.start_generation = 0

    def _download_phase_from_status(self, st):
        info_dict = st.get('info_dict') if isinstance(st, dict) else None
        if not isinstance(info_dict, dict):
            return None

        vcodec = str(info_dict.get('vcodec') or '').lower()
        acodec = str(info_dict.get('acodec') or '').lower()

        # Check requested_formats when top-level codecs are both "none"
        # (common when yt-dlp uses separate downloaders for video+audio streams)
        if (not vcodec or vcodec == 'none') and (not acodec or acodec == 'none'):
            requested = info_dict.get('requested_formats')
            if isinstance(requested, list) and requested:
                has_video = any(
                    str(f.get('vcodec') or '').lower() not in ('', 'none')
                    for f in requested if isinstance(f, dict)
                )
                has_audio = any(
                    str(f.get('acodec') or '').lower() not in ('', 'none')
                    for f in requested if isinstance(f, dict)
                )
                if has_video and has_audio:
                    return 'media'
                if has_video:
                    return 'video'
                if has_audio:
                    return 'audio'

        if vcodec and vcodec != 'none' and (not acodec or acodec == 'none'):
            return 'video'
        if acodec and acodec != 'none' and (not vcodec or vcodec == 'none'):
            return 'audio'
        if vcodec and vcodec != 'none' and acodec and acodec != 'none':
            return 'media'
        return None

    def _download(self):
        log.info(f"Starting download for: {self.info.title} ({self.info.url})")
        try:
            debug_logging = logging.getLogger().isEnabledFor(logging.DEBUG)
            def put_status(st):
                status = {k: v for k, v in st.items() if k in (
                    'tmpfilename',
                    'filename',
                    'status',
                    'msg',
                    'total_bytes',
                    'total_bytes_estimate',
                    'downloaded_bytes',
                    'speed',
                    'eta',
                )}
                phase = self._download_phase_from_status(st)
                if phase:
                    status['download_phase'] = phase
                log.debug(f"put_status: status={status.get('status')}, phase={phase}, "
                          f"vcodec={st.get('info_dict', {}).get('vcodec') if isinstance(st.get('info_dict'), dict) else 'N/A'}, "
                          f"acodec={st.get('info_dict', {}).get('acodec') if isinstance(st.get('info_dict'), dict) else 'N/A'}")
                self.status_queue.put(status)

            def put_status_postprocessor(d):
                if d.get('status') == 'started':
                    self.status_queue.put({
                        'status': 'postprocessing',
                        'download_phase': 'postprocessing',
                        'msg': d.get('postprocessor'),
                    })
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
                    elif getattr(self.info, 'download_type', '') == 'thumbnail':
                        info_dict = d.get('info_dict', {}) or {}
                        image_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')

                        def enqueue_if_image(path: str | None):
                            if isinstance(path, str) and path.lower().endswith(image_exts):
                                self.status_queue.put({'thumbnail_file': path})

                        # Common yt-dlp structures where thumbnail paths may appear.
                        enqueue_if_image(info_dict.get('thumbnail'))
                        for thumb in (info_dict.get('thumbnails') or []):
                            if isinstance(thumb, dict):
                                enqueue_if_image(thumb.get('filepath') or thumb.get('filename') or thumb.get('url'))
                        for item in (info_dict.get('requested_downloads') or []):
                            if isinstance(item, dict):
                                enqueue_if_image(item.get('filepath') or item.get('filename'))

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

            ret = yt_dlp.YoutubeDL(params=ytdl_params).download([self.info.url])
            self.status_queue.put({'status': 'finished' if ret == 0 else 'error', 'download_phase': None})
            log.info(f"Finished download for: {self.info.title}")
        except yt_dlp.utils.YoutubeDLError as exc:
            log.error(f"Download error for {self.info.title}: {str(exc)}")
            self.status_queue.put({'status': 'error', 'msg': str(exc), 'download_phase': None})

    async def start(self, notifier):
        log.info(f"Preparing download for: {self.info.title}")
        self.paused = False
        if Download.manager is None:
            Download.manager = multiprocessing.Manager()
        self.status_queue = Download.manager.Queue()
        self.proc = multiprocessing.Process(target=self._download)
        self.proc.start()
        self.loop = asyncio.get_running_loop()
        self.notifier = notifier
        self.info.status = 'preparing'
        self.info.download_phase = None
        await self.notifier.updated(self.info)
        self.status_task = asyncio.create_task(self.update_status())
        await self.loop.run_in_executor(None, self.proc.join)
        # Signal update_status to stop and wait for it to finish
        # so that all status updates (including MoveFiles with correct
        # file size) are processed before _post_download_cleanup runs.
        if self.status_queue is not None:
            self.status_queue.put(None)
        await self.status_task

    def cancel(self):
        log.info(f"Cancelling download: {self.info.title}")
        if self.running():
            try:
                self.proc.kill()
            except Exception as e:
                log.error(f"Error killing process for {self.info.title}: {e}")
        self.canceled = True
        if self.status_queue is not None:
            self.status_queue.put(None)

    def pause(self):
        log.info(f"Pausing download: {self.info.title}")
        self.paused = True
        self.start_generation += 1
        self.info.status = 'paused'
        self.info.download_phase = None
        self.info.speed = None
        self.info.eta = None
        if self.running():
            try:
                self.proc.kill()
            except Exception as e:
                log.error(f"Error killing process for {self.info.title}: {e}")
        if self.status_queue is not None:
            self.status_queue.put(None)

    def close(self):
        log.info(f"Closing download process for: {self.info.title}")
        if self.started():
            self.proc.close()

    def running(self):
        try:
            return self.proc is not None and self.proc.is_alive()
        except ValueError:
            return False

    def started(self):
        return self.proc is not None

    async def update_status(self):
        while True:
            status = await self.loop.run_in_executor(None, self.status_queue.get)
            if status is None:
                log.info(f"Status update finished for: {self.info.title}")

                return
            if self.paused:
                self.info.status = 'paused'
                self.info.download_phase = None
                self.info.speed = None
                self.info.eta = None
                await self.notifier.updated(self.info)
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
                if getattr(self.info, 'download_type', '') == 'thumbnail':
                    if not rel_name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')):
                        continue
                self.info.filename = rel_name
                self.info.size = os.path.getsize(fileName) if os.path.exists(fileName) else None

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
                continue

            if 'thumbnail_file' in status:
                thumbnail_file = status.get('thumbnail_file')
                if thumbnail_file and os.path.isfile(thumbnail_file):
                    rel_path = os.path.relpath(thumbnail_file, self.download_dir)
                    self.info.filename = rel_path
                    self.info.size = os.path.getsize(thumbnail_file)
                continue

            # All remaining messages must have a 'status' key
            if 'status' not in status:
                log.warning(f"Skipping status update without 'status' key for {self.info.title}: {list(status.keys())}")
                continue

            self.info.status = status['status']
            self.info.msg = status.get('msg')
            if 'download_phase' in status:
                self.info.download_phase = status['download_phase']
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
        if not os.path.isdir(pdir):
            os.mkdir(pdir)
        self.legacy_path = path
        self.path = f"{path}.json"
        self.store = AtomicJsonStore(self.path, kind=f"persistent_queue:{name}")
        self.dict = OrderedDict()

    def load(self):
        for k, v in self.saved_items():
            self.dict[k] = Download(None, None, None, None, getattr(v, 'quality', 'best'), getattr(v, 'format', 'any'), {}, v)

    def exists(self, key):
        return self._resolve_key(key) is not None

    def get(self, key):
        resolved = self._resolve_key(key)
        if resolved is None:
            raise KeyError(key)
        return self.dict[resolved]

    def items(self):
        return self.dict.items()

    def _resolve_key(self, key):
        if key in self.dict:
            return key
        for existing_key, download in self.dict.items():
            if getattr(download.info, "url", None) == key:
                return existing_key
        return None

    def saved_items(self):
        items = [
            (item["key"], _download_info_from_record(item["info"]))
            for item in self._load_state_items()
        ]
        return sorted(items, key=lambda item: item[1].timestamp)

    def _should_persist_entry(self) -> bool:
        return self.identifier != "completed"

    def _serialize_items(self):
        return [
            {
                "key": key,
                "info": _download_info_to_record(
                    download.info,
                    include_entry=self._should_persist_entry(),
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
                            include_entry=self._should_persist_entry(),
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
                    include_entry=self._should_persist_entry(),
                ),
            }
            for key, value in sorted(legacy_items, key=lambda item: item[1].timestamp)
        ]
        self.store.save({"items": items})
        return items

    def put(self, value):
        key = getattr(value.info, "key", value.info.url)
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
        resolved = self._resolve_key(key)
        if resolved is not None:
            old = self.dict[resolved]
            del self.dict[resolved]
            try:
                self._save_dict()
            except Exception:
                self.dict[resolved] = old
                raise

    def next(self):
        k, v = next(iter(self.dict.items()))
        return k, v

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
        self.done.load()
        self._add_generation = 0
        self._canceled_urls = set()  # URLs canceled during current playlist add

    @staticmethod
    def _download_key(dl: DownloadInfo) -> str:
        return "|".join([
            dl.url,
            dl.download_type,
            dl.codec,
            dl.format,
            dl.quality,
            dl.folder or "",
            dl.custom_name_prefix or "",
            str(dl.playlist_item_limit or 0),
            "1" if dl.split_by_chapters else "0",
            dl.chapter_template or "",
            dl.subtitle_language or "",
            dl.subtitle_mode or "",
            str(dl.clip_start if dl.clip_start is not None else ""),
            str(dl.clip_end if dl.clip_end is not None else ""),
        ])

    def cancel_add(self):
        self._add_generation += 1
        log.info('Playlist add operation canceled by user')

    async def __import_queue(self):
        for k, v in self.queue.saved_items():
            await self.__add_download(v, True)

    async def __import_pending(self):
        for k, v in self.pending.saved_items():
            await self.__add_download(v, False)

    async def initialize(self):
        log.info("Initializing DownloadQueue")
        asyncio.create_task(self.__import_queue())
        asyncio.create_task(self.__import_pending())

    async def __start_download(self, download, generation):
        if generation != download.start_generation or download.canceled or download.paused:
            log.info(f"Download {download.info.title} was canceled or paused, skipping start.")
            return
        async with self.semaphore:
            if generation != download.start_generation or download.canceled or download.paused:
                log.info(f"Download {download.info.title} was canceled or paused, skipping start.")
                return
            await download.start(self.notifier)
            self._post_download_cleanup(download)

    def _post_download_cleanup(self, download):
        key = getattr(download.info, 'key', download.info.url)
        if download.paused:
            download.info.status = 'paused'
            download.info.download_phase = None
            download.info.speed = None
            download.info.eta = None
            download.close()
            if self.queue.exists(key):
                self.queue.put(download)
                asyncio.create_task(self.notifier.updated(download.info))
            return
        if download.info.status != 'finished':
            if download.tmpfilename and os.path.isfile(download.tmpfilename):
                try:
                    os.remove(download.tmpfilename)
                except OSError:
                    pass
            download.info.status = 'error'
        else:
            # Captions-only downloads that produced no subtitle files should be
            # reported as an error rather than a silent "success".  This can
            # happen when the requested language (e.g. "en") is unavailable and
            # yt-dlp silently skips subtitle extraction without raising an
            # error.
            if getattr(download.info, 'download_type', '') == 'captions' and not getattr(download.info, 'filename', None):
                subtitle_files = getattr(download.info, 'subtitle_files', [])
                if not subtitle_files:
                    log.warning(
                        f"Captions download for \"{download.info.title}\" produced no files. "
                        f"Requested language: {getattr(download.info, 'subtitle_language', 'en')}, "
                        f"mode: {getattr(download.info, 'subtitle_mode', 'prefer_manual')}"
                    )
                    download.info.status = 'error'
                    download.info.error = (
                        f"No subtitles found for language \"{getattr(download.info, 'subtitle_language', 'en')}\". "
                        f"The video may not have subtitles in the requested language."
                    )
            # Thumbnail-only downloads that produced no image file should also
            # be reported as an error for the same reason.
            elif getattr(download.info, 'download_type', '') == 'thumbnail' and not getattr(download.info, 'filename', None):
                log.warning(
                    f"Thumbnail download for \"{download.info.title}\" produced no file."
                )
                download.info.status = 'error'
                download.info.error = "No thumbnail found for this video."
        download.close()
        if self.queue.exists(key):
            self.queue.delete(key)
            if download.canceled:
                asyncio.create_task(self.notifier.canceled(key))
            else:
                self.done.put(download)
                asyncio.create_task(self.notifier.completed(download.info))
                try:
                    clear_after = int(self.config.CLEAR_COMPLETED_AFTER)
                except ValueError:
                    log.error(f'CLEAR_COMPLETED_AFTER is set to an invalid value "{self.config.CLEAR_COMPLETED_AFTER}", expected an integer number of seconds')
                    clear_after = 0
                if clear_after > 0:
                    task = asyncio.create_task(self.__auto_clear_after_delay(key, clear_after))
                    task.add_done_callback(lambda t: log.error(f'Auto-clear task failed: {t.exception()}') if not t.cancelled() and t.exception() else None)

    async def __auto_clear_after_delay(self, key, delay_seconds):
        await asyncio.sleep(delay_seconds)
        if self.done.exists(key):
            log.debug(f'Auto-clearing completed download: {key}')
            await self.clear([key])

    def _build_ytdl_options(self, ytdl_options_presets=None, ytdl_options_overrides=None):
        """Merge global options, presets (in order), and per-download overrides."""
        opts = dict(self.config.YTDL_OPTIONS)
        for preset_name in ytdl_options_presets or []:
            opts.update(self.config.YTDL_OPTIONS_PRESETS.get(preset_name, {}))
        opts.update(ytdl_options_overrides or {})
        return opts

    def __extract_info(self, url, ytdl_options_presets=None, ytdl_options_overrides=None):
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
            if not dldirectory.startswith(real_base_directory):
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
        suffix = None
        if not getattr(dl, 'custom_name_prefix', None):
            parts = []
            quality_suffix = _quality_suffix_value(dl)
            if quality_suffix:
                parts.append(quality_suffix)
            codec_suffix = _codec_suffix_value(dl)
            if codec_suffix:
                parts.append(codec_suffix)
            if parts:
                suffix = '_'.join(_sanitize_path_component(p) for p in parts if p)

        if getattr(dl, 'custom_name_prefix', None):
            output = self.config.OUTPUT_TEMPLATE if len(dl.custom_name_prefix) == 0 else f'{dl.custom_name_prefix}.{self.config.OUTPUT_TEMPLATE}'
        else:
            output = self.config.OUTPUT_TEMPLATE
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
        if suffix:
            token = '%(ext)s'
            idx = output.rfind(token)
            if idx != -1:
                output = output[:idx] + f'{suffix}.{token}'
            else:
                output = f'{output}.{suffix}'
        ytdl_options = self._build_ytdl_options(
            getattr(dl, 'ytdl_options_presets', None),
            getattr(dl, 'ytdl_options_overrides', {}) or {},
        )
        playlist_item_limit = getattr(dl, 'playlist_item_limit', 0)
        if playlist_item_limit > 0:
            log.info(f'playlist limit is set. Processing only first {playlist_item_limit} entries')
            ytdl_options['playlistend'] = playlist_item_limit
        download = Download(dldirectory, self.config.TEMP_DIR, output, output_chapter, dl.quality, dl.format, ytdl_options, dl)
        if auto_start is True:
            self.queue.put(download)
            download.start_generation += 1
            asyncio.create_task(self.__start_download(download, download.start_generation))
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
            dt_ts = datetime.fromtimestamp(entry.get("release_timestamp")).strftime('%Y-%m-%d %H:%M:%S %z')
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
                etr[etype] = entry.get("id") or entry.get("channel_id") or entry.get("channel")
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
        elif etype == 'video' or (etype.startswith('url') and 'id' in entry and 'title' in entry):
            log.debug('Processing as a video')
            key = entry.get('webpage_url') or entry['url']
            if key in self._canceled_urls:
                log.info(f'Skipping canceled URL: {entry.get("title") or key}')
                return {'status': 'ok'}
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
            )
            dl.key = self._download_key(dl)
            if not self.queue.exists(dl.key):
                await self.__add_download(dl, auto_start)
            return {'status': 'ok'}
        return {'status': 'error', 'msg': f'Unsupported resource "{etype}"'}

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
        try:
            entry = await asyncio.get_running_loop().run_in_executor(
                None,
                partial(self.__extract_info, url, ytdl_options_presets, ytdl_options_overrides),
            )
        except yt_dlp.utils.YoutubeDLError as exc:
            return {'status': 'error', 'msg': str(exc)}
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
            if self.queue.exists(id):
                dl = self.queue.get(id)
                if getattr(dl.info, 'status', None) == 'paused' or dl.paused:
                    dl.paused = False
                    dl.info.status = 'pending'
                    dl.info.speed = None
                    dl.info.eta = None
                    self.queue.put(dl)
                    dl.start_generation += 1
                    asyncio.create_task(self.__start_download(dl, dl.start_generation))
                continue
            if not self.pending.exists(id):
                log.warning(f'requested start for non-existent download {id}')
                continue
            dl = self.pending.get(id)
            self.queue.put(dl)
            self.pending.delete(id)
            dl.start_generation += 1
            asyncio.create_task(self.__start_download(dl, dl.start_generation))
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
            if getattr(dl.info, 'status', None) == 'paused' or dl.paused:
                dl.cancel()
                self.queue.delete(id)
                await self.notifier.canceled(id)
                continue
            if dl.started():
                dl.cancel()
            else:
                dl.canceled = True
                self.queue.delete(id)
                await self.notifier.canceled(id)
        return {'status': 'ok'}

    async def pause(self, ids):
        for id in ids:
            if not self.queue.exists(id):
                log.warning(f'requested pause for non-existent download {id}')
                continue
            dl = self.queue.get(id)
            dl.pause()
            self.queue.put(dl)
            await self.notifier.updated(dl.info)
        return {'status': 'ok'}

    async def clear(self, ids):
        for id in ids:
            if not self.done.exists(id):
                log.warning(f'requested delete for non-existent download {id}')
                continue
            if self.config.DELETE_FILE_ON_TRASHCAN:
                dl = self.done.get(id)
                try:
                    dldirectory, _ = self.__calc_download_path(dl.info.download_type, dl.info.folder)
                    os.remove(os.path.join(dldirectory, dl.info.filename))
                except Exception as e:
                    log.warning(f'deleting file for download {id} failed with error message {e!r}')
            self.done.delete(id)
            await self.notifier.cleared(id)
        return {'status': 'ok'}

    def get(self):
        return (list((k, v.info) for k, v in self.queue.items()) +
                list((k, v.info) for k, v in self.pending.items()),
                list((k, v.info) for k, v in self.done.items()))
