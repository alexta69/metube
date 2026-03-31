#!/usr/bin/env python3
# pylint: disable=no-member,method-hidden

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import re
import socket
import ssl
import sys
from contextlib import suppress
from typing import Any

import socketio
from aiohttp import web
from aiohttp.log import access_logger
from watchfiles import Change, DefaultFilter, awatch
from yarl import URL

from config import Settings, SettingsError
from ytdl import Download, DownloadQueue, DownloadQueueNotifier
from yt_dlp.version import __version__ as yt_dlp_version

log = logging.getLogger("main")


def parseLogLevel(logLevel):
    if not isinstance(logLevel, str):
        return None
    return getattr(logging, logLevel.upper(), None)


def configure_logging(raw_loglevel: str | None = None) -> None:
    level = parseLogLevel(raw_loglevel or "INFO") or logging.INFO
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=level)
    logging.getLogger().setLevel(level)


def load_settings() -> Settings:
    configure_logging(os.environ.get("LOGLEVEL"))
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        log.error(str(exc))
        raise SystemExit(1) from exc
    configure_logging(settings.LOGLEVEL)
    return settings


Config = Settings


class ObjectSerializer(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
            try:
                return list(obj)
            except Exception:
                pass
        return json.JSONEncoder.default(self, obj)


serializer = ObjectSerializer()

SETTINGS_KEY = web.AppKey("settings", Settings)
SOCKETIO_KEY = web.AppKey("socketio", socketio.AsyncServer)
DQUEUE_KEY = web.AppKey("download_queue", DownloadQueue)
WATCH_TASK_KEY = web.AppKey("watch_task", asyncio.Task | None)
CUSTOM_DIRS_CACHE_KEY = web.AppKey("custom_dirs_cache", dict)

VALID_SUBTITLE_FORMATS = {"srt", "txt", "vtt", "ttml", "sbv", "scc", "dfxp"}
VALID_SUBTITLE_MODES = {"auto_only", "manual_only", "prefer_manual", "prefer_auto"}
SUBTITLE_LANGUAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,34}$")
VALID_DOWNLOAD_TYPES = {"video", "audio", "captions", "thumbnail"}
VALID_VIDEO_CODECS = {"auto", "h264", "h265", "av1", "vp9"}
VALID_VIDEO_FORMATS = {"any", "mp4", "ios"}
VALID_AUDIO_FORMATS = {"m4a", "mp3", "opus", "wav", "flac"}
VALID_THUMBNAIL_FORMATS = {"jpg"}


def _settings_from(request: web.Request) -> Settings:
    return request.app[SETTINGS_KEY]


def _dqueue_from(request: web.Request) -> DownloadQueue:
    return request.app[DQUEUE_KEY]


def _socketio_from(container: web.Request | web.Application) -> socketio.AsyncServer:
    app = container.app if isinstance(container, web.Request) else container
    return app[SOCKETIO_KEY]


def _migrate_legacy_request(post: dict) -> dict:
    if "download_type" in post:
        return post

    old_format = str(post.get("format") or "any").strip().lower()
    old_quality = str(post.get("quality") or "best").strip().lower()
    old_video_codec = str(post.get("video_codec") or "auto").strip().lower()

    if old_format in VALID_AUDIO_FORMATS:
        post["download_type"] = "audio"
        post["codec"] = "auto"
        post["format"] = old_format
    elif old_format == "thumbnail":
        post["download_type"] = "thumbnail"
        post["codec"] = "auto"
        post["format"] = "jpg"
        post["quality"] = "best"
    elif old_format == "captions":
        post["download_type"] = "captions"
        post["codec"] = "auto"
        post["format"] = str(post.get("subtitle_format") or "srt").strip().lower()
        post["quality"] = "best"
    else:
        post["download_type"] = "video"
        post["codec"] = old_video_codec
        if old_quality == "best_ios":
            post["format"] = "ios"
            post["quality"] = "best"
        elif old_quality == "audio":
            post["download_type"] = "audio"
            post["codec"] = "auto"
            post["format"] = "m4a"
            post["quality"] = "best"
        else:
            post["format"] = old_format
            post["quality"] = old_quality

    return post


class Notifier(DownloadQueueNotifier):
    def __init__(self, app: web.Application):
        self.app = app

    async def added(self, dl):
        log.info("Notifier: Download added - %s", dl.title)
        await _socketio_from(self.app).emit("added", serializer.encode(dl))

    async def updated(self, dl):
        log.debug("Notifier: Download updated - %s", dl.title)
        await _socketio_from(self.app).emit("updated", serializer.encode(dl))

    async def completed(self, dl):
        log.info("Notifier: Download completed - %s", dl.title)
        await _socketio_from(self.app).emit("completed", serializer.encode(dl))

    async def canceled(self, identifier):
        log.info("Notifier: Download canceled - %s", identifier)
        await _socketio_from(self.app).emit("canceled", serializer.encode(identifier))

    async def cleared(self, identifier):
        log.info("Notifier: Download cleared - %s", identifier)
        await _socketio_from(self.app).emit("cleared", serializer.encode(identifier))


class FileOpsFilter(DefaultFilter):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def __call__(self, change_type: int, path: str) -> bool:
        options_file = self.settings.YTDL_OPTIONS_FILE
        if not options_file or path != options_file:
            return False

        if os.path.exists(options_file):
            try:
                if not os.path.samefile(path, options_file):
                    return False
            except (OSError, IOError):
                if path != options_file:
                    return False
        return change_type in (Change.modified, Change.added, Change.deleted)


def get_options_update_time(settings: Settings, success: bool = True, msg: str = "") -> dict[str, Any]:
    result = {"success": success, "msg": msg, "update_time": None}
    if settings.YTDL_OPTIONS_FILE and os.path.exists(settings.YTDL_OPTIONS_FILE):
        try:
            result["update_time"] = os.path.getmtime(settings.YTDL_OPTIONS_FILE)
        except (OSError, IOError) as exc:
            log.warning("Could not get modification time for %s: %s", settings.YTDL_OPTIONS_FILE, exc)
    return result


async def _watch_ytdl_options(app: web.Application) -> None:
    settings = app[SETTINGS_KEY]
    sio = _socketio_from(app)
    log.info("Starting Watch File: %s", settings.YTDL_OPTIONS_FILE)
    try:
        async for _changes in awatch(
            settings.YTDL_OPTIONS_FILE,
            watch_filter=FileOpsFilter(settings),
        ):
            success, msg = settings.load_ytdl_options()
            await sio.emit(
                "ytdl_options_changed",
                serializer.encode(get_options_update_time(settings, success, msg)),
            )
    except asyncio.CancelledError:
        raise


async def _initialize_app(app: web.Application) -> None:
    settings = app[SETTINGS_KEY]
    if settings.COOKIES_PATH.exists():
        settings.set_runtime_override("cookiefile", str(settings.COOKIES_PATH))
        log.info("Cookie file detected at %s", settings.COOKIES_PATH)

    await app[DQUEUE_KEY].initialize()

    if settings.YTDL_OPTIONS_FILE:
        app[WATCH_TASK_KEY] = asyncio.create_task(_watch_ytdl_options(app))


async def _cleanup_app(app: web.Application) -> None:
    watch_task = app[WATCH_TASK_KEY]
    if watch_task is not None:
        watch_task.cancel()
        with suppress(asyncio.CancelledError):
            await watch_task
    Download.shutdown_manager()


async def _read_json_request(request: web.Request) -> dict:
    try:
        post = await request.json()
    except json.JSONDecodeError as exc:
        raise web.HTTPBadRequest(reason="Invalid JSON request body") from exc
    if not isinstance(post, dict):
        raise web.HTTPBadRequest(reason="JSON request body must be an object")
    return post


def _normalize_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    try:
        url = URL(origin)
    except Exception:
        return None
    if not url.scheme or not url.host:
        return None
    try:
        return str(url.origin())
    except ValueError:
        return None


def _request_origin(request: web.Request) -> str | None:
    try:
        return str(request.url.origin())
    except ValueError:
        origin = f"{request.scheme}://{request.host}"
        return _normalize_origin(origin)


def _origin_allowed(request: web.Request, settings: Settings) -> str | None:
    origin = _normalize_origin(request.headers.get("Origin"))
    if origin is None:
        return None
    if origin == _request_origin(request):
        return origin
    if origin in settings.TRUSTED_ORIGINS:
        return origin
    return None


async def add(request):
    settings = _settings_from(request)
    dqueue = _dqueue_from(request)

    log.info("Received request to add download")
    post = await _read_json_request(request)
    post = _migrate_legacy_request(post)
    log.info(
        "Add download request: type=%s quality=%s format=%s has_folder=%s auto_start=%s",
        post.get("download_type"),
        post.get("quality"),
        post.get("format"),
        bool(post.get("folder")),
        post.get("auto_start"),
    )
    url = post.get("url")
    download_type = post.get("download_type")
    codec = post.get("codec")
    format_value = post.get("format")
    quality = post.get("quality")
    if not url or not quality or not download_type:
        log.error("Bad request: missing 'url', 'download_type', or 'quality'")
        raise web.HTTPBadRequest()

    folder = post.get("folder")
    custom_name_prefix = post.get("custom_name_prefix")
    playlist_item_limit = post.get("playlist_item_limit")
    auto_start = post.get("auto_start")
    split_by_chapters = post.get("split_by_chapters")
    chapter_template = post.get("chapter_template")
    subtitle_language = post.get("subtitle_language")
    subtitle_mode = post.get("subtitle_mode")

    if custom_name_prefix is None:
        custom_name_prefix = ""
    if custom_name_prefix and (
        ".." in custom_name_prefix
        or custom_name_prefix.startswith("/")
        or custom_name_prefix.startswith("\\")
    ):
        raise web.HTTPBadRequest(
            reason='custom_name_prefix must not contain ".." or start with a path separator'
        )

    if auto_start is None:
        auto_start = True
    if playlist_item_limit is None:
        playlist_item_limit = settings.DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT
    if split_by_chapters is None:
        split_by_chapters = False
    if chapter_template is None:
        chapter_template = settings.OUTPUT_TEMPLATE_CHAPTER
    if subtitle_language is None:
        subtitle_language = "en"
    if subtitle_mode is None:
        subtitle_mode = "prefer_manual"

    download_type = str(download_type).strip().lower()
    codec = str(codec or "auto").strip().lower()
    format_value = str(format_value or "").strip().lower()
    quality = str(quality).strip().lower()
    subtitle_language = str(subtitle_language).strip()
    subtitle_mode = str(subtitle_mode).strip()

    if chapter_template and (
        ".." in chapter_template
        or chapter_template.startswith("/")
        or chapter_template.startswith("\\")
    ):
        raise web.HTTPBadRequest(
            reason='chapter_template must not contain ".." or start with a path separator'
        )
    if not SUBTITLE_LANGUAGE_RE.fullmatch(subtitle_language):
        raise web.HTTPBadRequest(
            reason="subtitle_language must match pattern [A-Za-z0-9-] and be at most 35 characters"
        )
    if subtitle_mode not in VALID_SUBTITLE_MODES:
        raise web.HTTPBadRequest(
            reason=f"subtitle_mode must be one of {sorted(VALID_SUBTITLE_MODES)}"
        )
    if download_type not in VALID_DOWNLOAD_TYPES:
        raise web.HTTPBadRequest(
            reason=f"download_type must be one of {sorted(VALID_DOWNLOAD_TYPES)}"
        )
    if codec not in VALID_VIDEO_CODECS:
        raise web.HTTPBadRequest(reason=f"codec must be one of {sorted(VALID_VIDEO_CODECS)}")

    if download_type == "video":
        if format_value not in VALID_VIDEO_FORMATS:
            raise web.HTTPBadRequest(
                reason=f"format must be one of {sorted(VALID_VIDEO_FORMATS)} for video"
            )
        if quality not in {"best", "worst", "2160", "1440", "1080", "720", "480", "360", "240"}:
            raise web.HTTPBadRequest(
                reason="quality must be one of ['best', '2160', '1440', '1080', '720', '480', '360', '240', 'worst'] for video"
            )
    elif download_type == "audio":
        if format_value not in VALID_AUDIO_FORMATS:
            raise web.HTTPBadRequest(
                reason=f"format must be one of {sorted(VALID_AUDIO_FORMATS)} for audio"
            )
        allowed_audio_qualities = {"best"}
        if format_value == "mp3":
            allowed_audio_qualities |= {"320", "192", "128"}
        elif format_value == "m4a":
            allowed_audio_qualities |= {"192", "128"}
        if quality not in allowed_audio_qualities:
            raise web.HTTPBadRequest(
                reason=f"quality must be one of {sorted(allowed_audio_qualities)} for format {format_value}"
            )
        codec = "auto"
    elif download_type == "captions":
        if format_value not in VALID_SUBTITLE_FORMATS:
            raise web.HTTPBadRequest(
                reason=f"format must be one of {sorted(VALID_SUBTITLE_FORMATS)} for captions"
            )
        quality = "best"
        codec = "auto"
    elif download_type == "thumbnail":
        if format_value not in VALID_THUMBNAIL_FORMATS:
            raise web.HTTPBadRequest(
                reason=f"format must be one of {sorted(VALID_THUMBNAIL_FORMATS)} for thumbnail"
            )
        quality = "best"
        codec = "auto"

    try:
        playlist_item_limit = int(playlist_item_limit)
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(reason="playlist_item_limit must be an integer") from exc

    status = await dqueue.add(
        url,
        download_type,
        codec,
        format_value,
        quality,
        folder,
        custom_name_prefix,
        playlist_item_limit,
        auto_start,
        split_by_chapters,
        chapter_template,
        subtitle_language,
        subtitle_mode,
    )
    return web.Response(text=serializer.encode(status))


async def cancel_add(request):
    _dqueue_from(request).cancel_add()
    return web.Response(
        text=serializer.encode({"status": "ok"}),
        content_type="application/json",
    )


async def delete(request):
    dqueue = _dqueue_from(request)
    post = await _read_json_request(request)
    ids = post.get("ids")
    where = post.get("where")
    if not ids or where not in ["queue", "done"]:
        log.error("Bad request: missing 'ids' or incorrect 'where' value")
        raise web.HTTPBadRequest()
    status = await (dqueue.cancel(ids) if where == "queue" else dqueue.clear(ids))
    log.info("Download delete request processed for ids: %s, where: %s", ids, where)
    return web.Response(text=serializer.encode(status))


async def start(request):
    dqueue = _dqueue_from(request)
    post = await _read_json_request(request)
    ids = post.get("ids")
    log.info("Received request to start pending downloads for ids: %s", ids)
    status = await dqueue.start_pending(ids)
    return web.Response(text=serializer.encode(status))


async def upload_cookies(request):
    settings = _settings_from(request)
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "cookies":
        return web.Response(
            status=400,
            text=serializer.encode({"status": "error", "msg": "No cookies file provided"}),
        )

    max_size = 1_000_000
    size = 0
    content = bytearray()
    while True:
        chunk = await field.read_chunk()
        if not chunk:
            break
        size += len(chunk)
        if size > max_size:
            return web.Response(
                status=400,
                text=serializer.encode(
                    {"status": "error", "msg": "Cookie file too large (max 1MB)"}
                ),
            )
        content.extend(chunk)

    tmp_cookie_path = settings.COOKIES_PATH.with_suffix(".txt.tmp")
    with tmp_cookie_path.open("wb") as handle:
        handle.write(content)
    os.replace(tmp_cookie_path, settings.COOKIES_PATH)
    settings.set_runtime_override("cookiefile", str(settings.COOKIES_PATH))
    log.info("Cookies file uploaded (%s bytes)", size)
    return web.Response(
        text=serializer.encode({"status": "ok", "msg": f"Cookies uploaded ({size} bytes)"})
    )


async def delete_cookies(request):
    settings = _settings_from(request)

    has_uploaded_cookies = settings.COOKIES_PATH.exists()
    configured_cookiefile = settings.YTDL_OPTIONS.get("cookiefile")
    has_manual_cookiefile = (
        isinstance(configured_cookiefile, str)
        and configured_cookiefile
        and configured_cookiefile != str(settings.COOKIES_PATH)
    )

    if not has_uploaded_cookies:
        if has_manual_cookiefile:
            return web.Response(
                status=400,
                text=serializer.encode(
                    {
                        "status": "error",
                        "msg": "Cookies are configured manually via YTDL_OPTIONS (cookiefile). Remove or change that setting manually; UI delete only removes uploaded cookies.",
                    }
                ),
            )
        return web.Response(
            status=400,
            text=serializer.encode({"status": "error", "msg": "No uploaded cookies to delete"}),
        )

    settings.COOKIES_PATH.unlink()
    settings.remove_runtime_override("cookiefile")
    success, msg = settings.load_ytdl_options()
    if not success:
        log.error("Cookies file deleted, but failed to reload YTDL_OPTIONS: %s", msg)
        return web.Response(
            status=500,
            text=serializer.encode(
                {
                    "status": "error",
                    "msg": f"Cookies file deleted, but failed to reload YTDL_OPTIONS: {msg}",
                }
            ),
        )

    log.info("Cookies file deleted")
    return web.Response(text=serializer.encode({"status": "ok"}))


async def cookie_status(request):
    settings = _settings_from(request)
    configured_cookiefile = settings.YTDL_OPTIONS.get("cookiefile")
    has_configured_cookies = isinstance(configured_cookiefile, str) and os.path.exists(
        configured_cookiefile
    )
    exists = settings.COOKIES_PATH.exists() or has_configured_cookies
    return web.Response(text=serializer.encode({"status": "ok", "has_cookies": exists}))


async def history(request):
    dqueue = _dqueue_from(request)
    result = {"done": [], "queue": [], "pending": []}
    for _, item in dqueue.queue.saved_items():
        result["queue"].append(item)
    for _, item in dqueue.done.saved_items():
        result["done"].append(item)
    for _, item in dqueue.pending.saved_items():
        result["pending"].append(item)
    log.info("Sending download history")
    return web.Response(text=serializer.encode(result))


def get_custom_dirs(app: web.Application):
    settings = app[SETTINGS_KEY]
    cache = app[CUSTOM_DIRS_CACHE_KEY]
    cache_ttl_seconds = 5
    now = asyncio.get_running_loop().time()
    cache_key = (
        settings.DOWNLOAD_DIR,
        settings.AUDIO_DOWNLOAD_DIR,
        settings.CUSTOM_DIRS_EXCLUDE_REGEX,
    )
    cached = cache.get(cache_key)
    if cached and (now - cached["time"]) < cache_ttl_seconds:
        return cached["value"]

    def recursive_dirs(base: str) -> list[str]:
        path = pathlib.Path(base)

        def convert(directory: pathlib.Path) -> str:
            stringified = str(directory)
            if stringified.startswith(base):
                stringified = stringified[len(base) :]
            if stringified.startswith("/"):
                stringified = stringified[1:]
            return stringified

        def include_dir(directory: str) -> bool:
            if len(settings.CUSTOM_DIRS_EXCLUDE_REGEX) == 0:
                return True
            return re.search(settings.CUSTOM_DIRS_EXCLUDE_REGEX, directory) is None

        directories = list(filter(include_dir, map(convert, path.glob("**/"))))
        if "" not in directories:
            directories.insert(0, "")
        return directories

    download_dir = recursive_dirs(settings.DOWNLOAD_DIR)
    audio_download_dir = download_dir
    if settings.DOWNLOAD_DIR != settings.AUDIO_DOWNLOAD_DIR:
        audio_download_dir = recursive_dirs(settings.AUDIO_DOWNLOAD_DIR)

    result = {
        "download_dir": download_dir,
        "audio_download_dir": audio_download_dir,
    }
    cache[cache_key] = {"time": now, "value": result}
    return result


async def index(request):
    settings = _settings_from(request)
    response = web.FileResponse(settings.UI_DIST_DIR / "index.html")
    if "metube_theme" not in request.cookies:
        response.set_cookie("metube_theme", settings.DEFAULT_THEME)
    return response


async def robots(request):
    settings = _settings_from(request)
    if settings.ROBOTS_TXT_PATH:
        return web.FileResponse(settings.ROBOTS_TXT_PATH)
    return web.Response(
        text="User-agent: *\nDisallow: /download/\nDisallow: /audio_download/\n"
    )


async def version(request):
    return web.json_response({"yt-dlp": yt_dlp_version, "version": os.getenv("METUBE_VERSION", "dev")})


async def index_redirect_root(request):
    return web.HTTPFound(_settings_from(request).URL_PREFIX)


async def index_redirect_dir(request):
    return web.HTTPFound(_settings_from(request).URL_PREFIX)


async def add_cors(request):
    response = web.Response(text=serializer.encode({"status": "ok"}))
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


async def on_prepare(request, response):
    origin = _origin_allowed(request, _settings_from(request))
    if origin is None:
        return
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Vary"] = "Origin"


def register_socketio_handlers(app: web.Application, sio: socketio.AsyncServer) -> None:
    @sio.event
    async def connect(sid, environ):
        settings = app[SETTINGS_KEY]
        dqueue = app[DQUEUE_KEY]
        log.info("Client connected: %s", sid)
        await sio.emit("all", serializer.encode(dqueue.get()), to=sid)
        await sio.emit("configuration", serializer.encode(settings.frontend_safe()), to=sid)
        if settings.CUSTOM_DIRS:
            await sio.emit("custom_dirs", serializer.encode(get_custom_dirs(app)), to=sid)
        if settings.YTDL_OPTIONS_FILE:
            await sio.emit(
                "ytdl_options_changed",
                serializer.encode(get_options_update_time(settings)),
                to=sid,
            )


def register_routes(app: web.Application) -> None:
    settings = app[SETTINGS_KEY]
    prefix = settings.URL_PREFIX

    app.router.add_post(prefix + "add", add)
    app.router.add_post(prefix + "cancel-add", cancel_add)
    app.router.add_post(prefix + "delete", delete)
    app.router.add_post(prefix + "start", start)
    app.router.add_post(prefix + "upload-cookies", upload_cookies)
    app.router.add_post(prefix + "delete-cookies", delete_cookies)
    app.router.add_get(prefix + "cookie-status", cookie_status)
    app.router.add_get(prefix + "history", history)
    app.router.add_get(prefix, index)
    app.router.add_get(prefix + "robots.txt", robots)
    app.router.add_get(prefix + "version", version)

    if prefix != "/":
        app.router.add_get("/", index_redirect_root)
        app.router.add_get(prefix[:-1], index_redirect_dir)

    app.router.add_static(
        prefix + "download/",
        settings.DOWNLOAD_DIR,
        show_index=settings.DOWNLOAD_DIRS_INDEXABLE,
    )
    app.router.add_static(
        prefix + "audio_download/",
        settings.AUDIO_DOWNLOAD_DIR,
        show_index=settings.DOWNLOAD_DIRS_INDEXABLE,
    )
    app.router.add_static(prefix, str(settings.UI_DIST_DIR))

    app.router.add_route("OPTIONS", prefix + "add", add_cors)
    app.router.add_route("OPTIONS", prefix + "cancel-add", add_cors)
    app.router.add_route("OPTIONS", prefix + "upload-cookies", add_cors)
    app.router.add_route("OPTIONS", prefix + "delete-cookies", add_cors)


def create_app(settings: Settings | None = None) -> web.Application:
    settings = settings or load_settings()
    socket_cors_origins = list(settings.TRUSTED_ORIGINS) if settings.TRUSTED_ORIGINS else None

    app = web.Application()
    app[SETTINGS_KEY] = settings
    app[WATCH_TASK_KEY] = None
    app[CUSTOM_DIRS_CACHE_KEY] = {}

    sio = socketio.AsyncServer(cors_allowed_origins=socket_cors_origins)
    sio.attach(app, socketio_path=settings.URL_PREFIX + "socket.io")
    app[SOCKETIO_KEY] = sio
    app[DQUEUE_KEY] = DownloadQueue(settings, Notifier(app))

    register_socketio_handlers(app, sio)
    register_routes(app)

    app.on_startup.append(_initialize_app)
    app.on_cleanup.append(_cleanup_app)
    app.on_response_prepare.append(on_prepare)
    return app


def supports_reuse_port():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.close()
        return True
    except (AttributeError, OSError):
        return False


def isAccessLogEnabled(settings: Settings):
    if settings.ENABLE_ACCESSLOG:
        return access_logger
    return None


def main() -> None:
    settings = load_settings()
    application = create_app(settings)
    log.info("Listening on %s:%s", settings.HOST, settings.PORT)

    if settings.HTTPS:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=settings.CERTFILE, keyfile=settings.KEYFILE)
        web.run_app(
            application,
            host=settings.HOST,
            port=int(settings.PORT),
            reuse_port=supports_reuse_port(),
            ssl_context=ssl_context,
            access_log=isAccessLogEnabled(settings),
        )
        return

    web.run_app(
        application,
        host=settings.HOST,
        port=int(settings.PORT),
        reuse_port=supports_reuse_port(),
        access_log=isAccessLogEnabled(settings),
    )


if __name__ == "__main__":
    main()
