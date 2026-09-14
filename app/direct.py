"""Direct streaming routes: fetch one media item into a temp dir and serve it.

``GET /watch?v=<id-or-url>`` and ``GET /dl/<name>.<ext>`` hand a URL, a bare
video ID or a search term (derived from the file name) to yt-dlp, download the
single best-matching item into a per-request temporary directory and send that
file straight back — inline by default, as an attachment with ``?download=1``.
Nothing is written to DOWNLOAD_DIR; the temporary directory is removed as soon
as the response body has been sent.
"""

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from urllib.parse import quote

import yt_dlp
import yt_dlp.networking.impersonate
from aiohttp import web
from yt_dlp.postprocessor import FFmpegPostProcessor
from yt_dlp.utils import parse_duration, sanitize_filename

from dl_formats import get_format, get_opts
from url_guard import install_socket_guard, validate_url
from ytdl import _ConfinedYoutubeDL, _pot_provider_urls

log = logging.getLogger('direct')

EXTENSIONS = ('mp4', 'mp3', 'jpg')
# ponytail: fixed 1080p cap for direct video; a quality parameter can follow once someone asks.
VIDEO_QUALITY = '1080'
# Frames are grabbed from a modest video-only stream: plenty for a still, cheap to seek in.
FRAME_FORMAT = 'bv*[ext=mp4][height<=720]/b[ext=mp4]/b'


class FetchError(Exception):
    """yt-dlp or ffmpeg could not produce the requested file."""


def parse_name(name: str) -> tuple[str, str]:
    """Split ``Greenday-Basketcase.mp3`` into a search term and a normalised extension."""
    stem, _, ext = name.rpartition('.')
    ext = ext.lower()
    ext = {'jpeg': 'jpg'}.get(ext, ext)
    if ext not in EXTENSIONS:
        raise web.HTTPBadRequest(reason=f'extension must be one of {list(EXTENSIONS)}')
    term = re.sub(r'[-_+.\s]+', ' ', stem).strip()
    if not term:
        raise web.HTTPBadRequest(reason='missing name before the extension')
    return term, ext


def parse_ts(value) -> float | None:
    """``90``, ``1:30`` and ``1m30s`` all mean ninety seconds; absent means no frame grab."""
    if value is None or value == '':
        return None
    ts = parse_duration(value)
    if ts is None:
        raise web.HTTPBadRequest(reason='ts must be a duration like 90, 1:30 or 1m30s')
    return ts


def parse_flag(value) -> bool:
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def content_disposition(title: str, ext: str, download: bool) -> str:
    """Inline or attachment header carrying the title as file name, ASCII fallback included."""
    title = title or 'media'
    ascii_name = f'{sanitize_filename(title, restricted=True)}.{ext}'
    utf8_name = quote(f'{sanitize_filename(title)}.{ext}')
    kind = 'attachment' if download else 'inline'
    return f'{kind}; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'


def fetch(source: str, ext: str, ts, tmpdir: str, ytdl_opts: dict, allow_private: bool) -> tuple[str, str]:
    """Download (or frame-grab) *source* into *tmpdir*; returns ``(path, title)``.

    Runs in a child process so that the connect-time SSRF guard can be
    installed, exactly as the queue's download subprocess does.
    """
    install_socket_guard(
        allow_private,
        proxy_urls=(ytdl_opts.get('proxy'),),
        service_urls=_pot_provider_urls(ytdl_opts),
    )
    frame = ext == 'jpg' and ts is not None
    params = {
        **ytdl_opts,
        'quiet': True,
        'no_color': True,
        'noplaylist': True,
        'playlist_items': '1',
        'paths': {'home': tmpdir, 'temp': tmpdir},
        'outtmpl': {'default': 'media.%(ext)s'},
        'logger': log,
    }
    if isinstance(params.get('impersonate'), str):
        params['impersonate'] = yt_dlp.networking.impersonate.ImpersonateTarget.from_str(params['impersonate'])
    if ext == 'mp4':
        # Fall back to any merge so sites without a native mp4 still remux into one.
        params['format'] = get_format('video', 'auto', 'mp4', VIDEO_QUALITY) + '/bv*+ba/b'
        params['merge_output_format'] = 'mp4'
    elif ext == 'mp3':
        params['format'] = get_format('audio', 'auto', 'mp3', 'best')
        params = get_opts('audio', 'auto', 'mp3', 'best', params)
    elif frame:
        params['format'] = FRAME_FORMAT
    else:
        params['format'] = get_format('thumbnail', 'auto', 'jpg', 'best')
        params = get_opts('thumbnail', 'auto', 'jpg', 'best', params)

    ydl = _ConfinedYoutubeDL(params, allowed_roots=(tmpdir,))
    try:
        info = ydl.extract_info(source, download=not frame)
    except yt_dlp.utils.YoutubeDLError as exc:
        raise FetchError(str(exc)) from None
    if info is not None and info.get('entries') is not None:
        info = next(iter(info['entries']), None)
    if info is None:
        raise FetchError('no results')

    path = os.path.join(tmpdir, f'media.{ext}')
    if frame:
        _grab_frame(ydl, info, ts, path, allow_private)
    if not os.path.exists(path):
        raise FetchError(f'yt-dlp did not produce a .{ext} file')
    return path, info.get('title') or 'media'


def _grab_frame(ydl, info: dict, ts: float, path: str, allow_private: bool) -> None:
    """One still at *ts* seconds, decoded by ffmpeg straight from the media URL."""
    url = info.get('url')
    if not url:
        raise FetchError('no direct media URL to grab a frame from')
    if (err := validate_url(url, allow_private=allow_private)) is not None:
        raise FetchError(err)
    duration = info.get('duration')
    if duration and ts > duration:
        raise FetchError(f'ts {ts:g} is past the end of the video ({duration:g}s)')
    ffmpeg = FFmpegPostProcessor(ydl).executable
    if not ffmpeg:
        raise FetchError('ffmpeg not found')
    cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y']
    headers = ''.join(f'{k}: {v}\r\n' for k, v in (info.get('http_headers') or {}).items())
    if headers:
        cmd += ['-headers', headers]
    cmd += ['-ss', str(ts), '-i', url, '-frames:v', '1', '-q:v', '2', '-update', '1', path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()
        raise FetchError(tail[-1] if tail else f'ffmpeg exited with {proc.returncode}')


class TempFileResponse(web.FileResponse):
    """A FileResponse whose per-request temp dir is removed once the body is sent."""

    def __init__(self, path: str, tmpdir: tempfile.TemporaryDirectory, **kwargs):
        super().__init__(path, **kwargs)
        self._tmpdir = tmpdir

    async def prepare(self, request):
        try:
            return await super().prepare(request)
        finally:
            # FileResponse closes its handle in the executor after prepare
            # returns; the cleanup goes the same way so it queues behind that
            # close. Errors are ignored: on Windows the handle may still be
            # open, and the OS temp cleanup collects the directory eventually.
            asyncio.get_running_loop().run_in_executor(None, self._tmpdir.cleanup)
