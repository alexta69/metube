import os
import shutil
import yt_dlp
from collections import OrderedDict
import shelve
import time
import asyncio
import multiprocessing
import logging
import re
import types
import dbm
import subprocess
from typing import Any
from functools import lru_cache

import yt_dlp.networking.impersonate
from yt_dlp.utils import STR_FORMAT_RE_TMPL, STR_FORMAT_TYPES
from dl_formats import get_format, get_opts, AUDIO_FORMATS
from datetime import datetime

log = logging.getLogger('ytdl')


@lru_cache(maxsize=None)
def _compile_outtmpl_pattern(field: str) -> re.Pattern:
    """Compile a regex pattern to match a specific field in an output template, including optional format specifiers."""
    conversion_types = f"[{re.escape(STR_FORMAT_TYPES)}]"
    return re.compile(STR_FORMAT_RE_TMPL.format(re.escape(field), conversion_types))


def _outtmpl_substitute_field(template: str, field: str, value: Any) -> str:
    """Substitute a single field in an output template, applying any format specifiers to the value."""
    pattern = _compile_outtmpl_pattern(field)

    def replacement(match: re.Match) -> str:
        if match.group("has_key") is None:
            return match.group(0)

        prefix = match.group("prefix") or ""
        format_spec = match.group("format")

        if not format_spec:
            return f"{prefix}{value}"

        conversion_type = format_spec[-1]
        try:
            if conversion_type in "diouxX":
                coerced_value = int(value)
            elif conversion_type in "eEfFgG":
                coerced_value = float(value)
            else:
                coerced_value = value

            return f"{prefix}{('%' + format_spec) % coerced_value}"
        except (ValueError, TypeError):
            return f"{prefix}{value}"

    return pattern.sub(replacement, template)

def _convert_generators_to_lists(obj):
    """Recursively convert generators to lists in a dictionary to make it pickleable."""
    if isinstance(obj, types.GeneratorType):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: _convert_generators_to_lists(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return type(obj)(_convert_generators_to_lists(item) for item in obj)
    else:
        return obj


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
        format,
        folder,
        custom_name_prefix,
        error,
        entry,
        playlist_item_limit,
        split_by_chapters,
        chapter_template,
        subtitle_format="srt",
        subtitle_language="en",
        subtitle_mode="prefer_manual",
    ):
        self.id = id if len(custom_name_prefix) == 0 else f'{custom_name_prefix}.{id}'
        self.title = title if len(custom_name_prefix) == 0 else f'{custom_name_prefix}.{title}'
        self.url = url
        self.quality = quality
        self.format = format
        self.folder = folder
        self.custom_name_prefix = custom_name_prefix
        self.msg = self.percent = self.speed = self.eta = None
        self.status = "pending"
        self.size = None
        self.timestamp = time.time_ns()
        self.error = error
        # Convert generators to lists to make entry pickleable
        self.entry = _convert_generators_to_lists(entry) if entry is not None else None
        self.playlist_item_limit = playlist_item_limit
        self.split_by_chapters = split_by_chapters
        self.chapter_template = chapter_template
        self.subtitle_format = subtitle_format
        self.subtitle_language = subtitle_language
        self.subtitle_mode = subtitle_mode
        self.subtitle_files = []

class Download:
    manager = None

    def __init__(self, download_dir, temp_dir, output_template, output_template_chapter, quality, format, ytdl_opts, info):
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.output_template = output_template
        self.output_template_chapter = output_template_chapter
        self.info = info
        self.format = get_format(format, quality)
        self.ytdl_opts = get_opts(
            format,
            quality,
            ytdl_opts,
            subtitle_format=getattr(info, 'subtitle_format', 'srt'),
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

    def _download(self):
        log.info(f"Starting download for: {self.info.title} ({self.info.url})")
        try:
            debug_logging = logging.getLogger().isEnabledFor(logging.DEBUG)
            def put_status(st):
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

            def put_status_postprocessor(d):
                if d['postprocessor'] == 'MoveFiles' and d['status'] == 'finished':
                    filepath = d['info_dict']['filepath']
                    if '__finaldir' in d['info_dict']:
                        finaldir = d['info_dict']['__finaldir']
                        # Compute relative path from temp dir to preserve
                        # subdirectory structure from the output template.
                        try:
                            rel_path = os.path.relpath(filepath, self.temp_dir)
                        except ValueError:
                            rel_path = os.path.basename(filepath)
                        if rel_path.startswith('..'):
                            # filepath is not under temp_dir, fall back to basename
                            rel_path = os.path.basename(filepath)
                        filename = os.path.join(finaldir, rel_path)
                    else:
                        filename = filepath
                    self.status_queue.put({'status': 'finished', 'filename': filename})
                    # For captions-only downloads, yt-dlp may still report a media-like
                    # filepath in MoveFiles. Capture subtitle outputs explicitly so the
                    # UI can link to real caption files.
                    if self.info.format == 'captions':
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

            ret = yt_dlp.YoutubeDL(params=ytdl_params).download([self.info.url])
            self.status_queue.put({'status': 'finished' if ret == 0 else 'error'})
            log.info(f"Finished download for: {self.info.title}")
        except yt_dlp.utils.YoutubeDLError as exc:
            log.error(f"Download error for {self.info.title}: {str(exc)}")
            self.status_queue.put({'status': 'error', 'msg': str(exc)})

    async def start(self, notifier):
        log.info(f"Preparing download for: {self.info.title}")
        if Download.manager is None:
            Download.manager = multiprocessing.Manager()
        self.status_queue = Download.manager.Queue()
        self.proc = multiprocessing.Process(target=self._download)
        self.proc.start()
        self.loop = asyncio.get_running_loop()
        self.notifier = notifier
        self.info.status = 'preparing'
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
            if self.canceled:
                log.info(f"Download {self.info.title} is canceled; stopping status updates.")
                return
            self.tmpfilename = status.get('tmpfilename')
            if 'filename' in status:
                fileName = status.get('filename')
                rel_name = os.path.relpath(fileName, self.download_dir)
                # For captions mode, ignore media-like placeholders and let subtitle_file
                # statuses define the final file shown in the UI.
                if self.info.format == 'captions':
                    requested_subtitle_format = str(getattr(self.info, 'subtitle_format', '')).lower()
                    allowed_caption_exts = ('.txt',) if requested_subtitle_format == 'txt' else ('.vtt', '.srt', '.sbv', '.scc', '.ttml', '.dfxp')
                    if not rel_name.lower().endswith(allowed_caption_exts):
                        continue
                self.info.filename = rel_name
                self.info.size = os.path.getsize(fileName) if os.path.exists(fileName) else None
                if self.info.format == 'thumbnail':
                    self.info.filename = re.sub(r'\.webm$', '.jpg', self.info.filename)

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
                if self.info.format == 'captions' and str(getattr(self.info, 'subtitle_format', '')).lower() == 'txt':
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
                if self.info.format == 'captions' and (
                    not getattr(self.info, 'filename', None) or
                    str(getattr(self.info, 'subtitle_format', '')).lower() == 'txt'
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
        if not os.path.isdir(pdir):
            os.mkdir(pdir)
        with shelve.open(path, 'c'):
            pass

        self.path = path
        self.repair()
        self.dict = OrderedDict()

    def load(self):
        for k, v in self.saved_items():
            self.dict[k] = Download(None, None, None, None, None, None, {}, v)

    def exists(self, key):
        return key in self.dict

    def get(self, key):
        return self.dict[key]

    def items(self):
        return self.dict.items()

    def saved_items(self):
        with shelve.open(self.path, 'r') as shelf:
            return sorted(shelf.items(), key=lambda item: item[1].timestamp)

    def put(self, value):
        key = value.info.url
        self.dict[key] = value
        with shelve.open(self.path, 'w') as shelf:
            shelf[key] = value.info

    def delete(self, key):
        if key in self.dict:
            del self.dict[key]
            with shelve.open(self.path, 'w') as shelf:
                shelf.pop(key, None)

    def next(self):
        k, v = next(iter(self.dict.items()))
        return k, v

    def empty(self):
        return not bool(self.dict)

    def repair(self):
        # check DB format
        type_check = subprocess.run(
            ["file", self.path],
            capture_output=True,
            text=True
        )
        db_type = type_check.stdout.lower()

        # create backup (<queue>.old)
        try:
            shutil.copy2(self.path, f"{self.path}.old")
        except Exception as e:
            # if we cannot backup then its not safe to attempt a repair
            #  since it could be due to a filesystem error
            log.debug(f"PersistentQueue:{self.identifier} backup failed, skipping repair")
            return

        if "gnu dbm" in db_type:
            # perform gdbm repair
            log_prefix = f"PersistentQueue:{self.identifier} repair (dbm/file)"
            log.debug(f"{log_prefix} started")
            try:
                result = subprocess.run(
                    ["gdbmtool", self.path],
                    input="recover verbose summary\n",
                    text=True,
                    capture_output=True,
                    timeout=60
                )
                log.debug(f"{log_prefix} {result.stdout}")
                if result.stderr:
                    log.debug(f"{log_prefix} failed: {result.stderr}")
            except FileNotFoundError:
                log.debug(f"{log_prefix} failed: 'gdbmtool' was not found")

            # perform null key cleanup
            log_prefix = f"PersistentQueue:{self.identifier} repair (null keys)"
            log.debug(f"{log_prefix} started")
            deleted = 0
            try:
                with dbm.open(self.path, "w") as db:
                    for key in list(db.keys()):
                        if len(key) > 0 and all(b == 0x00 for b in key):
                            log.debug(f"{log_prefix} deleting key of length {len(key)} (all NUL bytes)")
                            del db[key]
                            deleted += 1
                log.debug(f"{log_prefix} done - deleted {deleted} key(s)")
            except dbm.error:
                log.debug(f"{log_prefix} failed: db type is dbm.gnu, but the module is not available (dbm.error; module support may be missing or the file may be corrupted)")

        elif "sqlite" in db_type:
            # perform sqlite3 recovery
            log_prefix = f"PersistentQueue:{self.identifier} repair (sqlite3/file)"
            log.debug(f"{log_prefix} started")
            try:
                result = subprocess.run(
                    f"sqlite3 {self.path} '.recover' | sqlite3 {self.path}.tmp",
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=60
                )
                if result.stderr:
                    log.debug(f"{log_prefix} failed: {result.stderr}")
                else:
                    shutil.move(f"{self.path}.tmp", self.path)
                    log.debug(f"{log_prefix}{result.stdout or " was successful, no output"}")
            except FileNotFoundError:
                log.debug(f"{log_prefix} failed: 'sqlite3' was not found")

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

    async def __start_download(self, download):
        if download.canceled:
            log.info(f"Download {download.info.title} was canceled, skipping start.")
            return
        async with self.semaphore:
            if download.canceled:
                log.info(f"Download {download.info.title} was canceled, skipping start.")
                return
            await download.start(self.notifier)
            self._post_download_cleanup(download)

    def _post_download_cleanup(self, download):
        if download.info.status != 'finished':
            if download.tmpfilename and os.path.isfile(download.tmpfilename):
                try:
                    os.remove(download.tmpfilename)
                except:
                    pass
            download.info.status = 'error'
        download.close()
        if self.queue.exists(download.info.url):
            self.queue.delete(download.info.url)
            if download.canceled:
                asyncio.create_task(self.notifier.canceled(download.info.url))
            else:
                self.done.put(download)
                asyncio.create_task(self.notifier.completed(download.info))

    def __extract_info(self, url):
        debug_logging = logging.getLogger().isEnabledFor(logging.DEBUG)
        return yt_dlp.YoutubeDL(params={
            'quiet': not debug_logging,
            'verbose': debug_logging,
            'no_color': True,
            'extract_flat': True,
            'ignore_no_formats_error': True,
            'noplaylist': True,
            'paths': {"home": self.config.DOWNLOAD_DIR, "temp": self.config.TEMP_DIR},
            **self.config.YTDL_OPTIONS,
            **({'impersonate': yt_dlp.networking.impersonate.ImpersonateTarget.from_str(self.config.YTDL_OPTIONS['impersonate'])} if 'impersonate' in self.config.YTDL_OPTIONS else {}),
        }).extract_info(url, download=False)

    def __calc_download_path(self, quality, format, folder):
        base_directory = self.config.DOWNLOAD_DIR if (quality != 'audio' and format not in AUDIO_FORMATS) else self.config.AUDIO_DOWNLOAD_DIR
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
        dldirectory, error_message = self.__calc_download_path(dl.quality, dl.format, dl.folder)
        if error_message is not None:
            return error_message
        output = self.config.OUTPUT_TEMPLATE if len(dl.custom_name_prefix) == 0 else f'{dl.custom_name_prefix}.{self.config.OUTPUT_TEMPLATE}'
        output_chapter = self.config.OUTPUT_TEMPLATE_CHAPTER
        entry = getattr(dl, 'entry', None)
        if entry is not None and entry.get('playlist_index') is not None:
            if len(self.config.OUTPUT_TEMPLATE_PLAYLIST):
                output = self.config.OUTPUT_TEMPLATE_PLAYLIST
            for property, value in entry.items():
                if property.startswith("playlist"):
                    output = _outtmpl_substitute_field(output, property, value)
        if entry is not None and entry.get('channel_index') is not None:
            if len(self.config.OUTPUT_TEMPLATE_CHANNEL):
                output = self.config.OUTPUT_TEMPLATE_CHANNEL
            for property, value in entry.items():
                if property.startswith("channel"):
                    output = _outtmpl_substitute_field(output, property, value)
        ytdl_options = dict(self.config.YTDL_OPTIONS)
        playlist_item_limit = getattr(dl, 'playlist_item_limit', 0)
        if playlist_item_limit > 0:
            log.info(f'playlist limit is set. Processing only first {playlist_item_limit} entries')
            ytdl_options['playlistend'] = playlist_item_limit
        download = Download(dldirectory, self.config.TEMP_DIR, output, output_chapter, dl.quality, dl.format, ytdl_options, dl)
        if auto_start is True:
            self.queue.put(download)
            asyncio.create_task(self.__start_download(download))
        else:
            self.pending.put(download)
        await self.notifier.added(dl)

    async def __add_entry(
        self,
        entry,
        quality,
        format,
        folder,
        custom_name_prefix,
        playlist_item_limit,
        auto_start,
        split_by_chapters,
        chapter_template,
        subtitle_format,
        subtitle_language,
        subtitle_mode,
        already,
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
                quality,
                format,
                folder,
                custom_name_prefix,
                playlist_item_limit,
                auto_start,
                split_by_chapters,
                chapter_template,
                subtitle_format,
                subtitle_language,
                subtitle_mode,
                already,
            )
        elif etype == 'playlist' or etype == 'channel':
            log.debug(f'Processing as a {etype}')
            entries = entry['entries']
            # Convert generator to list if needed (for len() and slicing operations)
            if isinstance(entries, types.GeneratorType):
                entries = list(entries)
            log.info(f'{etype} detected with {len(entries)} entries')
            index_digits = len(str(len(entries)))
            results = []
            if playlist_item_limit > 0:
                log.info(f'Item limit is set. Processing only first {playlist_item_limit} entries')
                entries = entries[:playlist_item_limit]
            for index, etr in enumerate(entries, start=1):
                etr["_type"] = "video"
                etr[etype] = entry.get("id") or entry.get("channel_id") or entry.get("channel")
                etr[f"{etype}_index"] = '{{0:0{0:d}d}}'.format(index_digits).format(index)
                for property in ("id", "title", "uploader", "uploader_id"):
                    if property in entry:
                        etr[f"{etype}_{property}"] = entry[property]
                results.append(
                    await self.__add_entry(
                        etr,
                        quality,
                        format,
                        folder,
                        custom_name_prefix,
                        playlist_item_limit,
                        auto_start,
                        split_by_chapters,
                        chapter_template,
                        subtitle_format,
                        subtitle_language,
                        subtitle_mode,
                        already,
                    )
                )
            if any(res['status'] == 'error' for res in results):
                return {'status': 'error', 'msg': ', '.join(res['msg'] for res in results if res['status'] == 'error' and 'msg' in res)}
            return {'status': 'ok'}
        elif etype == 'video' or (etype.startswith('url') and 'id' in entry and 'title' in entry):
            log.debug('Processing as a video')
            key = entry.get('webpage_url') or entry['url']
            if not self.queue.exists(key):
                dl = DownloadInfo(
                    entry['id'],
                    entry.get('title') or entry['id'],
                    key,
                    quality,
                    format,
                    folder,
                    custom_name_prefix,
                    error,
                    entry,
                    playlist_item_limit,
                    split_by_chapters,
                    chapter_template,
                    subtitle_format,
                    subtitle_language,
                    subtitle_mode,
                )
                await self.__add_download(dl, auto_start)
            return {'status': 'ok'}
        return {'status': 'error', 'msg': f'Unsupported resource "{etype}"'}

    async def add(
        self,
        url,
        quality,
        format,
        folder,
        custom_name_prefix,
        playlist_item_limit,
        auto_start=True,
        split_by_chapters=False,
        chapter_template=None,
        subtitle_format="srt",
        subtitle_language="en",
        subtitle_mode="prefer_manual",
        already=None,
    ):
        log.info(
            f'adding {url}: {quality=} {format=} {already=} {folder=} {custom_name_prefix=} '
            f'{playlist_item_limit=} {auto_start=} {split_by_chapters=} {chapter_template=} '
            f'{subtitle_format=} {subtitle_language=} {subtitle_mode=}'
        )
        already = set() if already is None else already
        if url in already:
            log.info('recursion detected, skipping')
            return {'status': 'ok'}
        else:
            already.add(url)
        try:
            entry = await asyncio.get_running_loop().run_in_executor(None, self.__extract_info, url)
        except yt_dlp.utils.YoutubeDLError as exc:
            return {'status': 'error', 'msg': str(exc)}
        return await self.__add_entry(
            entry,
            quality,
            format,
            folder,
            custom_name_prefix,
            playlist_item_limit,
            auto_start,
            split_by_chapters,
            chapter_template,
            subtitle_format,
            subtitle_language,
            subtitle_mode,
            already,
        )

    async def start_pending(self, ids):
        for id in ids:
            if not self.pending.exists(id):
                log.warn(f'requested start for non-existent download {id}')
                continue
            dl = self.pending.get(id)
            self.queue.put(dl)
            self.pending.delete(id)
            asyncio.create_task(self.__start_download(dl))
        return {'status': 'ok'}

    async def cancel(self, ids):
        for id in ids:
            if self.pending.exists(id):
                self.pending.delete(id)
                await self.notifier.canceled(id)
                continue
            if not self.queue.exists(id):
                log.warn(f'requested cancel for non-existent download {id}')
                continue
            if self.queue.get(id).started():
                self.queue.get(id).cancel()
            else:
                self.queue.delete(id)
                await self.notifier.canceled(id)
        return {'status': 'ok'}

    async def clear(self, ids):
        for id in ids:
            if not self.done.exists(id):
                log.warn(f'requested delete for non-existent download {id}')
                continue
            if self.config.DELETE_FILE_ON_TRASHCAN:
                dl = self.done.get(id)
                try:
                    dldirectory, _ = self.__calc_download_path(dl.info.quality, dl.info.format, dl.info.folder)
                    os.remove(os.path.join(dldirectory, dl.info.filename))
                except Exception as e:
                    log.warn(f'deleting file for download {id} failed with error message {e!r}')
            self.done.delete(id)
            await self.notifier.cleared(id)
        return {'status': 'ok'}

    def get(self):
        return (list((k, v.info) for k, v in self.queue.items()) +
                list((k, v.info) for k, v in self.pending.items()),
                list((k, v.info) for k, v in self.done.items()))
