#!/usr/bin/env python3
# pylint: disable=no-member,method-hidden

import os
import sys
import asyncio
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from aiohttp import web
from aiohttp.log import access_logger
import ssl
import socket
import socketio
import logging
import json
import pathlib
import re
from watchfiles import DefaultFilter, Change, awatch

from ytdl import DownloadQueueNotifier, DownloadQueue, Download
from subscriptions import SubscriptionManager, SubscriptionNotifier, SubscriptionInfo
from yt_dlp.version import __version__ as yt_dlp_version

log = logging.getLogger('main')

def parseLogLevel(logLevel):
    if not isinstance(logLevel, str):
        return None
    return getattr(logging, logLevel.upper(), None)

# Configure logging before Config() uses it so early messages are not dropped.
# Only configure if no handlers are set (avoid clobbering hosting app settings).
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=parseLogLevel(os.environ.get('LOGLEVEL', 'INFO')) or logging.INFO)

class Config:
    _DEFAULTS = {
        'DOWNLOAD_DIR': '.',
        'AUDIO_DOWNLOAD_DIR': '%%DOWNLOAD_DIR',
        'TEMP_DIR': '%%DOWNLOAD_DIR',
        'DOWNLOAD_DIRS_INDEXABLE': 'false',
        'CUSTOM_DIRS': 'true',
        'CREATE_CUSTOM_DIRS': 'true',
        'CUSTOM_DIRS_EXCLUDE_REGEX': r'(^|/)[.@].*$',
        'DELETE_FILE_ON_TRASHCAN': 'false',
        'STATE_DIR': '.',
        'URL_PREFIX': '',
        'PUBLIC_HOST_URL': 'download/',
        'PUBLIC_HOST_AUDIO_URL': 'audio_download/',
        'OUTPUT_TEMPLATE': '%(title)s.%(ext)s',
        'OUTPUT_TEMPLATE_CHAPTER': '%(title)s - %(section_number)02d - %(section_title)s.%(ext)s',
        'OUTPUT_TEMPLATE_PLAYLIST': '%(playlist_title)s/%(title)s.%(ext)s',
        'OUTPUT_TEMPLATE_CHANNEL': '%(channel)s/%(title)s.%(ext)s',
        'DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT' : '0',
        'SUBSCRIPTION_DEFAULT_CHECK_INTERVAL': '60',
        'SUBSCRIPTION_SCAN_PLAYLIST_END': '50',
        'SUBSCRIPTION_MAX_SEEN_IDS': '50000',
        'CLEAR_COMPLETED_AFTER': '0',
        'YTDL_OPTIONS': '{}',
        'YTDL_OPTIONS_FILE': '',
        'YTDL_OPTIONS_PRESETS': '{}',
        'YTDL_OPTIONS_PRESETS_FILE': '',
        'ALLOW_YTDL_OPTIONS_OVERRIDES': 'false',
        'CORS_ALLOWED_ORIGINS': '',
        'ROBOTS_TXT': '',
        'HOST': '0.0.0.0',
        'PORT': '8081',
        'HTTPS': 'false',
        'CERTFILE': '',
        'KEYFILE': '',
        'METUBE_PASSWORD': '',
        'METUBE_PASSWORD_FILE': '',
        'METUBE_SESSION_MAX_AGE': '86400',
        'BASE_DIR': '',
        'DEFAULT_THEME': 'auto',
        'MAX_CONCURRENT_DOWNLOADS': '3',
        'LOGLEVEL': 'INFO',
        'ENABLE_ACCESSLOG': 'false',
    }

    _BOOLEAN = ('DOWNLOAD_DIRS_INDEXABLE', 'CUSTOM_DIRS', 'CREATE_CUSTOM_DIRS', 'DELETE_FILE_ON_TRASHCAN', 'HTTPS', 'ENABLE_ACCESSLOG', 'ALLOW_YTDL_OPTIONS_OVERRIDES')

    def __init__(self):
        for k, v in self._DEFAULTS.items():
            setattr(self, k, os.environ.get(k, v))

        for k, v in self.__dict__.items():
            if isinstance(v, str) and v.startswith('%%'):
                setattr(self, k, getattr(self, v[2:]))
            if k in self._BOOLEAN:
                if v not in ('true', 'false', 'True', 'False', 'on', 'off', '1', '0'):
                    log.error(f'Environment variable "{k}" is set to a non-boolean value "{v}"')
                    sys.exit(1)
                setattr(self, k, v in ('true', 'True', 'on', '1'))

        if not self.URL_PREFIX.endswith('/'):
            self.URL_PREFIX += '/'

        for attr in ('PUBLIC_HOST_URL', 'PUBLIC_HOST_AUDIO_URL'):
            val = getattr(self, attr)
            if val and not val.endswith('/'):
                setattr(self, attr, val + '/')

        # Convert relative addresses to absolute addresses to prevent the failure of file address comparison
        if self.YTDL_OPTIONS_FILE and self.YTDL_OPTIONS_FILE.startswith('.'):
            self.YTDL_OPTIONS_FILE = str(Path(self.YTDL_OPTIONS_FILE).resolve())
        if self.YTDL_OPTIONS_PRESETS_FILE and self.YTDL_OPTIONS_PRESETS_FILE.startswith('.'):
            self.YTDL_OPTIONS_PRESETS_FILE = str(Path(self.YTDL_OPTIONS_PRESETS_FILE).resolve())
        if self.METUBE_PASSWORD_FILE and self.METUBE_PASSWORD_FILE.startswith('.'):
            self.METUBE_PASSWORD_FILE = str(Path(self.METUBE_PASSWORD_FILE).resolve())

        self._runtime_overrides = {}
        self.METUBE_PASSWORD = self._load_optional_secret('METUBE_PASSWORD')

        try:
            self.METUBE_SESSION_MAX_AGE = int(self.METUBE_SESSION_MAX_AGE)
        except (TypeError, ValueError):
            log.error('Environment variable "METUBE_SESSION_MAX_AGE" must be an integer')
            sys.exit(1)
        if self.METUBE_SESSION_MAX_AGE < 0:
            log.error('Environment variable "METUBE_SESSION_MAX_AGE" must be zero or greater')
            sys.exit(1)

        success,_ = self.load_ytdl_options()
        if not success:
            sys.exit(1)
        success,_ = self.load_ytdl_option_presets()
        if not success:
            sys.exit(1)

    def set_runtime_override(self, key, value):
        self._runtime_overrides[key] = value
        self.YTDL_OPTIONS[key] = value

    def remove_runtime_override(self, key):
        self._runtime_overrides.pop(key, None)
        self.YTDL_OPTIONS.pop(key, None)

    def _apply_runtime_overrides(self):
        self.YTDL_OPTIONS.update(self._runtime_overrides)

    def _load_optional_secret(self, key: str) -> str:
        value = getattr(self, key, '') or ''
        file_key = f'{key}_FILE'
        file_value = getattr(self, file_key, '') or ''

        if value and file_value:
            log.error(f'Only one of "{key}" or "{file_key}" may be set')
            sys.exit(1)

        if not file_value:
            return value

        try:
            with open(file_value, encoding='utf-8') as secret_file:
                secret = secret_file.read().rstrip('\r\n')
        except OSError as exc:
            log.error(f'Could not read "{file_key}" from "{file_value}": {exc}')
            sys.exit(1)

        if not secret:
            log.error(f'File "{file_value}" referenced by "{file_key}" is empty')
            sys.exit(1)

        return secret

    # Keys sent to the browser. Sensitive or server-only keys (YTDL_OPTIONS,
    # paths, TLS config, etc.) are intentionally excluded.
    _FRONTEND_KEYS = (
        'CUSTOM_DIRS',
        'CREATE_CUSTOM_DIRS',
        'OUTPUT_TEMPLATE_CHAPTER',
        'PUBLIC_HOST_URL',
        'PUBLIC_HOST_AUDIO_URL',
        'DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT',
        'SUBSCRIPTION_DEFAULT_CHECK_INTERVAL',
        'ALLOW_YTDL_OPTIONS_OVERRIDES',
    )

    def frontend_safe(self) -> dict:
        """Return only the config keys that are safe to expose to browser clients.

        Sensitive or server-only keys (YTDL_OPTIONS, file-system paths, TLS
        settings, etc.) are intentionally excluded.
        """
        return {k: getattr(self, k) for k in self._FRONTEND_KEYS}

    def load_ytdl_options(self) -> tuple[bool, str]:
        try:
            self.YTDL_OPTIONS = json.loads(os.environ.get('YTDL_OPTIONS', '{}'))
            assert isinstance(self.YTDL_OPTIONS, dict)
        except (json.decoder.JSONDecodeError, AssertionError):
            msg = 'Environment variable YTDL_OPTIONS is invalid'
            log.error(msg)
            return (False, msg)

        if not self.YTDL_OPTIONS_FILE:
            self._apply_runtime_overrides()
            return (True, '')

        log.info(f'Loading yt-dlp custom options from "{self.YTDL_OPTIONS_FILE}"')
        if not os.path.exists(self.YTDL_OPTIONS_FILE):
            msg = f'File "{self.YTDL_OPTIONS_FILE}" not found'
            log.error(msg)
            return (False, msg)
        try:
            with open(self.YTDL_OPTIONS_FILE) as json_data:
                opts = json.load(json_data)
            assert isinstance(opts, dict)
        except (json.decoder.JSONDecodeError, AssertionError):
            msg = 'YTDL_OPTIONS_FILE contents is invalid'
            log.error(msg)
            return (False, msg)

        self.YTDL_OPTIONS.update(opts)
        self._apply_runtime_overrides()
        return (True, '')

    def load_ytdl_option_presets(self) -> tuple[bool, str]:
        try:
            self.YTDL_OPTIONS_PRESETS = json.loads(os.environ.get('YTDL_OPTIONS_PRESETS', '{}'))
            assert isinstance(self.YTDL_OPTIONS_PRESETS, dict)
            assert all(isinstance(name, str) and isinstance(options, dict) for name, options in self.YTDL_OPTIONS_PRESETS.items())
        except (json.decoder.JSONDecodeError, AssertionError):
            msg = 'Environment variable YTDL_OPTIONS_PRESETS is invalid'
            log.error(msg)
            return (False, msg)

        if not self.YTDL_OPTIONS_PRESETS_FILE:
            return (True, '')

        log.info(f'Loading yt-dlp option presets from "{self.YTDL_OPTIONS_PRESETS_FILE}"')
        if not os.path.exists(self.YTDL_OPTIONS_PRESETS_FILE):
            msg = f'File "{self.YTDL_OPTIONS_PRESETS_FILE}" not found'
            log.error(msg)
            return (False, msg)
        try:
            with open(self.YTDL_OPTIONS_PRESETS_FILE) as json_data:
                opts = json.load(json_data)
            assert isinstance(opts, dict)
            assert all(isinstance(name, str) and isinstance(options, dict) for name, options in opts.items())
        except (json.decoder.JSONDecodeError, AssertionError):
            msg = 'YTDL_OPTIONS_PRESETS_FILE contents is invalid'
            log.error(msg)
            return (False, msg)

        self.YTDL_OPTIONS_PRESETS.update(opts)
        return (True, '')

config = Config()
# Align root logger level with Config (keeps a single source of truth).
# This re-applies the log level after Config loads, in case LOGLEVEL was
# overridden by config file settings or differs from the environment variable.
logging.getLogger().setLevel(parseLogLevel(str(config.LOGLEVEL)) or logging.INFO)

@dataclass
class AuthSession:
    expires_at: float | None
    socket_ids: set[str] = field(default_factory=set)


class AuthManager:
    COOKIE_NAME = 'metube_session'

    def __init__(self, password: str, *, cookie_path: str, secure_cookie: bool, session_max_age: int):
        self.password = password
        self.cookie_path = cookie_path or '/'
        self.secure_cookie = secure_cookie
        self.session_max_age = session_max_age
        self._sessions: dict[str, AuthSession] = {}
        self._sid_to_session: dict[str, str] = {}
        self._expiry_tasks: dict[str, asyncio.Task[None]] = {}
        self._disconnect_socket: Callable[[str], Awaitable[None]] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.password)

    def authenticate(self, password: str) -> bool:
        return self.enabled and secrets.compare_digest(password, self.password)

    def set_socket_disconnect_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._disconnect_socket = callback

    def _expires_at(self) -> float | None:
        if self.session_max_age <= 0:
            return None
        return time.time() + self.session_max_age

    def _is_expired(self, session: AuthSession) -> bool:
        return session.expires_at is not None and time.time() >= session.expires_at

    def _get_session(self, session_id: str | None) -> AuthSession | None:
        if not session_id:
            return None
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if self._is_expired(session):
            self.revoke_session(session_id)
            return None
        return session

    def _schedule_expiry(self, session_id: str) -> None:
        if self.session_max_age <= 0:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = self._expiry_tasks.pop(session_id, None)
        if task is not None:
            task.cancel()
        self._expiry_tasks[session_id] = loop.create_task(self._expire_session_after(session_id, self.session_max_age))

    async def _expire_session_after(self, session_id: str, delay: int) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        self._expiry_tasks.pop(session_id, None)
        sids = self.revoke_session(session_id, cancel_expiry=False)
        if not sids:
            return

        log.info('Authentication session expired')
        if self._disconnect_socket is None:
            return
        for sid in sids:
            try:
                await self._disconnect_socket(sid)
            except Exception:
                log.debug('Socket for expired session already disconnected: %s', sid)

    def create_session(self) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = AuthSession(expires_at=self._expires_at())
        self._schedule_expiry(session_id)
        return session_id

    def get_session_id(self, request: web.Request | None) -> str | None:
        if request is None:
            return None
        session_id = request.cookies.get(self.COOKIE_NAME)
        return session_id if self._get_session(session_id) else None

    def is_authenticated(self, request: web.Request | None) -> bool:
        return self.get_session_id(request) is not None

    def status_payload(self, request: web.Request | None) -> dict:
        return {
            'status': 'ok',
            'enabled': self.enabled,
            'authenticated': self.is_authenticated(request),
        }

    def set_cookie(self, response: web.StreamResponse, session_id: str) -> None:
        response.set_cookie(
            self.COOKIE_NAME,
            session_id,
            httponly=True,
            samesite='Lax',
            secure=self.secure_cookie,
            path=self.cookie_path,
            max_age=self.session_max_age if self.session_max_age > 0 else None,
        )

    def clear_cookie(self, response: web.StreamResponse) -> None:
        response.del_cookie(
            self.COOKIE_NAME,
            httponly=True,
            samesite='Lax',
            secure=self.secure_cookie,
            path=self.cookie_path,
        )

    def register_socket(self, sid: str, session_id: str | None) -> None:
        session = self._get_session(session_id)
        if session is None:
            return
        session.socket_ids.add(sid)
        self._sid_to_session[sid] = session_id

    def unregister_socket(self, sid: str) -> None:
        session_id = self._sid_to_session.pop(sid, None)
        if not session_id:
            return
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.socket_ids.discard(sid)

    def revoke_session(self, session_id: str, *, cancel_expiry: bool = True) -> list[str]:
        if cancel_expiry:
            task = self._expiry_tasks.pop(session_id, None)
            if task is not None:
                task.cancel()

        session = self._sessions.pop(session_id, None)
        if session is None:
            return []

        sids = list(session.socket_ids)
        for sid in sids:
            self._sid_to_session.pop(sid, None)
        return sids


auth_manager = AuthManager(
    config.METUBE_PASSWORD,
    cookie_path=(config.URL_PREFIX if config.URL_PREFIX.startswith('/') else f'/{config.URL_PREFIX}'),
    secure_cookie=config.HTTPS,
    session_max_age=config.METUBE_SESSION_MAX_AGE,
)

class ObjectSerializer(json.JSONEncoder):
    def default(self, obj):
        # First try to use __dict__ for custom objects
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        # Convert iterables (generators, dict_items, etc.) to lists
        # Exclude strings and bytes which are also iterable
        elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
            try:
                return list(obj)
            except Exception:
                pass
        # Fall back to default behavior
        return json.JSONEncoder.default(self, obj)

serializer = ObjectSerializer()
_PROTECTED_PATHS = {
    config.URL_PREFIX + 'add',
    config.URL_PREFIX + 'presets',
    config.URL_PREFIX + 'cancel-add',
    config.URL_PREFIX + 'subscribe',
    config.URL_PREFIX + 'subscriptions',
    config.URL_PREFIX + 'subscriptions/update',
    config.URL_PREFIX + 'subscriptions/delete',
    config.URL_PREFIX + 'subscriptions/check',
    config.URL_PREFIX + 'delete',
    config.URL_PREFIX + 'start',
    config.URL_PREFIX + 'upload-cookies',
    config.URL_PREFIX + 'delete-cookies',
    config.URL_PREFIX + 'cookie-status',
    config.URL_PREFIX + 'history',
    config.URL_PREFIX + 'version',
}
_PROTECTED_PREFIXES = (
    config.URL_PREFIX + 'download',
    config.URL_PREFIX + 'audio_download',
    config.URL_PREFIX + 'socket.io',
)


def _requires_auth_for_path(path: str) -> bool:
    if path in _PROTECTED_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PROTECTED_PREFIXES)


def _unauthorized_response(request: web.Request | None = None) -> web.Response:
    response = web.json_response({'status': 'error', 'msg': 'Authentication required'}, status=401)
    if request is not None and request.cookies.get(auth_manager.COOKIE_NAME):
        auth_manager.clear_cookie(response)
    return response


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if request.method == 'OPTIONS' or not auth_manager.enabled or not _requires_auth_for_path(request.path):
        return await handler(request)
    if auth_manager.is_authenticated(request):
        return await handler(request)
    return _unauthorized_response(request)

app = web.Application(middlewares=[auth_middleware])
_cors_origins = [o.strip() for o in config.CORS_ALLOWED_ORIGINS.split(',') if o.strip()] if config.CORS_ALLOWED_ORIGINS else []
sio = socketio.AsyncServer(cors_allowed_origins=_cors_origins if _cors_origins else [])
sio.attach(app, socketio_path=config.URL_PREFIX + 'socket.io')
auth_manager.set_socket_disconnect_callback(sio.disconnect)
routes = web.RouteTableDef()
VALID_SUBTITLE_FORMATS = {'srt', 'txt', 'vtt', 'ttml', 'sbv', 'scc', 'dfxp'}
VALID_SUBTITLE_MODES = {'auto_only', 'manual_only', 'prefer_manual', 'prefer_auto'}
SUBTITLE_LANGUAGE_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{0,34}$')
VALID_DOWNLOAD_TYPES = {'video', 'audio', 'captions', 'thumbnail'}
VALID_VIDEO_CODECS = {'auto', 'h264', 'h265', 'av1', 'vp9'}
VALID_VIDEO_FORMATS = {'any', 'mp4', 'ios'}
VALID_AUDIO_FORMATS = {'m4a', 'mp3', 'opus', 'wav', 'flac'}
VALID_THUMBNAIL_FORMATS = {'jpg'}
def _parse_ytdl_options_overrides(value, *, enabled: bool) -> dict:
    if value is None or value == '':
        return {}

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise web.HTTPBadRequest(reason='ytdl_options_overrides must be valid JSON') from exc

    if not isinstance(value, dict):
        raise web.HTTPBadRequest(reason='ytdl_options_overrides must be a JSON object')

    if value and not enabled:
        raise web.HTTPBadRequest(reason='ytdl_options_overrides are disabled')

    return value


def _parse_ytdl_options_presets(post: dict) -> list[str]:
    """Normalize preset names from add/subscribe body; supports list or legacy singular string."""
    raw = post.get('ytdl_options_presets')
    if raw is None:
        raw = post.get('ytdl_options_preset')
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    raise web.HTTPBadRequest(
        reason='ytdl_options_presets must be a JSON array of strings (or legacy ytdl_options_preset string)',
    )


def _migrate_legacy_request(post: dict) -> dict:
    """
    BACKWARD COMPATIBILITY: Translate old API request schema into the new one.

    Old API:
      format (any/mp4/m4a/mp3/opus/wav/flac/thumbnail/captions)
      quality
      video_codec
      subtitle_format (only when format=captions)

    New API:
      download_type (video/audio/captions/thumbnail)
      codec
      format
      quality
    """
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
        # old_format is usually any/mp4 (legacy video path)
        post["download_type"] = "video"
        post["codec"] = old_video_codec
        if old_quality == "best_ios":
            post["format"] = "ios"
            post["quality"] = "best"
        elif old_quality == "audio":
            # Legacy "audio only" under video format maps to m4a audio.
            post["download_type"] = "audio"
            post["codec"] = "auto"
            post["format"] = "m4a"
            post["quality"] = "best"
        else:
            post["format"] = old_format
            post["quality"] = old_quality

    return post

class Notifier(DownloadQueueNotifier):
    async def added(self, dl):
        log.info(f"Notifier: Download added - {dl.title}")
        await sio.emit('added', serializer.encode(dl))

    async def updated(self, dl):
        log.debug(f"Notifier: Download updated - {dl.title}")
        await sio.emit('updated', serializer.encode(dl))

    async def completed(self, dl):
        log.info(f"Notifier: Download completed - {dl.title}")
        await sio.emit('completed', serializer.encode(dl))

    async def canceled(self, id):
        log.info(f"Notifier: Download canceled - {id}")
        await sio.emit('canceled', serializer.encode(id))

    async def cleared(self, id):
        log.info(f"Notifier: Download cleared - {id}")
        await sio.emit('cleared', serializer.encode(id))

dqueue = DownloadQueue(config, Notifier())
app.on_startup.append(lambda app: dqueue.initialize())
app.on_cleanup.append(lambda app: Download.shutdown_manager())


class MetubeSubscriptionNotifier(SubscriptionNotifier):
    async def subscription_added(self, sub: SubscriptionInfo):
        log.info("Subscription added: %s", sub.name)
        await sio.emit('subscription_added', serializer.encode(sub.to_public_dict()))

    async def subscription_updated(self, sub: SubscriptionInfo):
        await sio.emit('subscription_updated', serializer.encode(sub.to_public_dict()))

    async def subscription_removed(self, sub_id: str):
        log.info("Subscription removed: %s", sub_id)
        await sio.emit('subscription_removed', serializer.encode(sub_id))

    async def subscriptions_all(self, subs: list[SubscriptionInfo]):
        await sio.emit('subscriptions_all', serializer.encode([s.to_public_dict() for s in subs]))


submgr = SubscriptionManager(config, dqueue, MetubeSubscriptionNotifier())
app.on_cleanup.append(lambda app: submgr.close())


async def _subscription_loop_startup(app):
    """aiohttp on_startup requires awaitable receivers; start_background_loop is sync."""
    submgr.start_background_loop()


app.on_startup.append(_subscription_loop_startup)

class FileOpsFilter(DefaultFilter):
    def __call__(self, change_type: int, path: str) -> bool:
        # Check if this path matches our YTDL_OPTIONS_FILE
        if path != config.YTDL_OPTIONS_FILE:
            return False

        # For existing files, use samefile comparison to handle symlinks correctly
        if os.path.exists(config.YTDL_OPTIONS_FILE):
            try:
                if not os.path.samefile(path, config.YTDL_OPTIONS_FILE):
                    return False
            except (OSError, IOError):
                # If samefile fails, fall back to string comparison
                if path != config.YTDL_OPTIONS_FILE:
                    return False

        # Accept all change types for our file: modified, added, deleted
        return change_type in (Change.modified, Change.added, Change.deleted)

def get_options_update_time(success=True, msg=''):
    result = {
        'success': success,
        'msg': msg,
        'update_time': None
    }

    # Only try to get file modification time if YTDL_OPTIONS_FILE is set and file exists
    if config.YTDL_OPTIONS_FILE and os.path.exists(config.YTDL_OPTIONS_FILE):
        try:
            result['update_time'] = os.path.getmtime(config.YTDL_OPTIONS_FILE)
        except (OSError, IOError) as e:
            log.warning(f"Could not get modification time for {config.YTDL_OPTIONS_FILE}: {e}")
            result['update_time'] = None

    return result

async def watch_files():
    async def _watch_files():
        async for changes in awatch(config.YTDL_OPTIONS_FILE, watch_filter=FileOpsFilter()):
            success, msg = config.load_ytdl_options()
            result = get_options_update_time(success, msg)
            await sio.emit('ytdl_options_changed', serializer.encode(result))

    log.info(f'Starting Watch File: {config.YTDL_OPTIONS_FILE}')
    asyncio.create_task(_watch_files())

if config.YTDL_OPTIONS_FILE:
    app.on_startup.append(lambda app: watch_files())


async def _read_json_request(request: web.Request) -> dict:
    try:
        post = await request.json()
    except json.JSONDecodeError as exc:
        raise web.HTTPBadRequest(reason='Invalid JSON request body') from exc
    if not isinstance(post, dict):
        raise web.HTTPBadRequest(reason='JSON request body must be an object')
    return post


async def _disconnect_auth_session(session_id: str) -> None:
    for sid in auth_manager.revoke_session(session_id):
        try:
            await sio.disconnect(sid)
        except Exception:
            log.debug('Socket for revoked session already disconnected: %s', sid)


def _auth_status_response(request: web.Request) -> web.Response:
    response = web.json_response(auth_manager.status_payload(request))
    if request.cookies.get(auth_manager.COOKIE_NAME) and not auth_manager.is_authenticated(request):
        auth_manager.clear_cookie(response)
    return response


def parse_download_options(post: dict) -> dict:
    """Validate add/subscribe body; raise HTTPBadRequest on invalid input."""
    post = _migrate_legacy_request(dict(post))
    url = post.get('url')
    download_type = post.get('download_type')
    codec = post.get('codec')
    format = post.get('format')
    quality = post.get('quality')
    if not url or not quality or not download_type:
        raise web.HTTPBadRequest(reason="missing 'url', 'download_type', or 'quality'")
    url = str(url).strip()
    folder = post.get('folder')
    custom_name_prefix = post.get('custom_name_prefix')
    playlist_item_limit = post.get('playlist_item_limit')
    auto_start = post.get('auto_start')
    split_by_chapters = post.get('split_by_chapters')
    chapter_template = post.get('chapter_template')
    subtitle_language = post.get('subtitle_language')
    subtitle_mode = post.get('subtitle_mode')
    ytdl_options_overrides = post.get('ytdl_options_overrides')

    if custom_name_prefix is None:
        custom_name_prefix = ''
    if custom_name_prefix and ('..' in custom_name_prefix or custom_name_prefix.startswith('/') or custom_name_prefix.startswith('\\')):
        raise web.HTTPBadRequest(reason='custom_name_prefix must not contain ".." or start with a path separator')
    if auto_start is None:
        auto_start = True
    if playlist_item_limit is None:
        playlist_item_limit = config.DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT
    if split_by_chapters is None:
        split_by_chapters = False
    if chapter_template is None:
        chapter_template = config.OUTPUT_TEMPLATE_CHAPTER
    if subtitle_language is None:
        subtitle_language = 'en'
    if subtitle_mode is None:
        subtitle_mode = 'prefer_manual'
    download_type = str(download_type).strip().lower()
    codec = str(codec or 'auto').strip().lower()
    format = str(format or '').strip().lower()
    quality = str(quality).strip().lower()
    subtitle_language = str(subtitle_language).strip()
    subtitle_mode = str(subtitle_mode).strip()
    ytdl_options_presets = _parse_ytdl_options_presets(post)
    ytdl_options_overrides = _parse_ytdl_options_overrides(
        ytdl_options_overrides,
        enabled=config.ALLOW_YTDL_OPTIONS_OVERRIDES,
    )

    if chapter_template and ('..' in chapter_template or chapter_template.startswith('/') or chapter_template.startswith('\\')):
        raise web.HTTPBadRequest(reason='chapter_template must not contain ".." or start with a path separator')
    if not SUBTITLE_LANGUAGE_RE.fullmatch(subtitle_language):
        raise web.HTTPBadRequest(reason='subtitle_language must match pattern [A-Za-z0-9-] and be at most 35 characters')
    if subtitle_mode not in VALID_SUBTITLE_MODES:
        raise web.HTTPBadRequest(reason=f'subtitle_mode must be one of {sorted(VALID_SUBTITLE_MODES)}')
    for preset_name in ytdl_options_presets:
        if preset_name not in config.YTDL_OPTIONS_PRESETS:
            raise web.HTTPBadRequest(reason='ytdl_options_presets must only contain configured preset names')

    if download_type not in VALID_DOWNLOAD_TYPES:
        raise web.HTTPBadRequest(reason=f'download_type must be one of {sorted(VALID_DOWNLOAD_TYPES)}')
    if codec not in VALID_VIDEO_CODECS:
        raise web.HTTPBadRequest(reason=f'codec must be one of {sorted(VALID_VIDEO_CODECS)}')

    if download_type == 'video':
        if format not in VALID_VIDEO_FORMATS:
            raise web.HTTPBadRequest(reason=f'format must be one of {sorted(VALID_VIDEO_FORMATS)} for video')
        if quality not in {'best', 'worst', '2160', '1440', '1080', '720', '480', '360', '240'}:
            raise web.HTTPBadRequest(reason="quality must be one of ['best', '2160', '1440', '1080', '720', '480', '360', '240', 'worst'] for video")
    elif download_type == 'audio':
        if format not in VALID_AUDIO_FORMATS:
            raise web.HTTPBadRequest(reason=f'format must be one of {sorted(VALID_AUDIO_FORMATS)} for audio')
        allowed_audio_qualities = {'best'}
        if format == 'mp3':
            allowed_audio_qualities |= {'320', '192', '128'}
        elif format == 'm4a':
            allowed_audio_qualities |= {'192', '128'}
        if quality not in allowed_audio_qualities:
            raise web.HTTPBadRequest(reason=f'quality must be one of {sorted(allowed_audio_qualities)} for format {format}')
        codec = 'auto'
    elif download_type == 'captions':
        if format not in VALID_SUBTITLE_FORMATS:
            raise web.HTTPBadRequest(reason=f'format must be one of {sorted(VALID_SUBTITLE_FORMATS)} for captions')
        quality = 'best'
        codec = 'auto'
    elif download_type == 'thumbnail':
        if format not in VALID_THUMBNAIL_FORMATS:
            raise web.HTTPBadRequest(reason=f'format must be one of {sorted(VALID_THUMBNAIL_FORMATS)} for thumbnail')
        quality = 'best'
        codec = 'auto'

    try:
        playlist_item_limit = int(playlist_item_limit)
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(reason='playlist_item_limit must be an integer') from exc

    return {
        'url': url,
        'download_type': download_type,
        'codec': codec,
        'format': format,
        'quality': quality,
        'folder': folder,
        'custom_name_prefix': custom_name_prefix,
        'playlist_item_limit': playlist_item_limit,
        'auto_start': auto_start,
        'split_by_chapters': split_by_chapters,
        'chapter_template': chapter_template,
        'subtitle_language': subtitle_language,
        'subtitle_mode': subtitle_mode,
        'ytdl_options_presets': ytdl_options_presets,
        'ytdl_options_overrides': ytdl_options_overrides,
    }


@routes.post(config.URL_PREFIX + 'add')
async def add(request):
    log.info("Received request to add download")
    post = await _read_json_request(request)
    try:
        o = parse_download_options(post)
    except web.HTTPBadRequest as e:
        log.error("Bad request: %s", e.reason)
        raise
    log.info(
        "Add download request: type=%s quality=%s format=%s has_folder=%s auto_start=%s",
        o['download_type'],
        o['quality'],
        o['format'],
        bool(o.get('folder')),
        o['auto_start'],
    )
    status = await dqueue.add(
        o['url'],
        o['download_type'],
        o['codec'],
        o['format'],
        o['quality'],
        o['folder'],
        o['custom_name_prefix'],
        o['playlist_item_limit'],
        o['auto_start'],
        o['split_by_chapters'],
        o['chapter_template'],
        o['subtitle_language'],
        o['subtitle_mode'],
        o['ytdl_options_presets'],
        o['ytdl_options_overrides'],
    )
    return web.Response(text=serializer.encode(status))


@routes.get(config.URL_PREFIX + 'auth/status')
async def auth_status(request):
    return _auth_status_response(request)


@routes.post(config.URL_PREFIX + 'auth/login')
async def auth_login(request):
    if not auth_manager.enabled:
        return _auth_status_response(request)

    post = await _read_json_request(request)
    password = post.get('password')
    if password is None:
        password = ''
    if not isinstance(password, str):
        password = str(password)

    if not auth_manager.authenticate(password):
        log.warning('Rejected UI login with invalid password')
        return web.json_response(
            {'status': 'error', 'enabled': True, 'authenticated': False, 'msg': 'Invalid password'},
            status=401,
        )

    session_id = auth_manager.create_session()
    response = web.json_response({'status': 'ok', 'enabled': True, 'authenticated': True})
    auth_manager.set_cookie(response, session_id)
    log.info('Authenticated UI session created')
    return response


@routes.post(config.URL_PREFIX + 'auth/logout')
async def auth_logout(request):
    session_id = auth_manager.get_session_id(request)
    if session_id:
        await _disconnect_auth_session(session_id)
    response = web.json_response({'status': 'ok', 'enabled': auth_manager.enabled, 'authenticated': False})
    auth_manager.clear_cookie(response)
    return response


@routes.get(config.URL_PREFIX + 'presets')
async def presets(request):
    return web.Response(
        text=serializer.encode({'presets': sorted(config.YTDL_OPTIONS_PRESETS.keys())}),
        content_type='application/json',
    )

@routes.post(config.URL_PREFIX + 'cancel-add')
async def cancel_add(request):
    dqueue.cancel_add()
    return web.Response(text=serializer.encode({'status': 'ok'}), content_type='application/json')


@routes.post(config.URL_PREFIX + 'subscribe')
async def subscribe(request):
    post = await _read_json_request(request)
    try:
        o = parse_download_options(post)
    except web.HTTPBadRequest:
        raise
    cic = post.get('check_interval_minutes')
    if cic is None:
        cic = config.SUBSCRIPTION_DEFAULT_CHECK_INTERVAL
    try:
        cic = int(cic)
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(reason='check_interval_minutes must be an integer') from exc
    if cic < 1:
        raise web.HTTPBadRequest(reason='check_interval_minutes must be at least 1')

    result = await submgr.add_subscription(
        o['url'],
        check_interval_minutes=cic,
        download_type=o['download_type'],
        codec=o['codec'],
        format=o['format'],
        quality=o['quality'],
        folder=o['folder'] or '',
        custom_name_prefix=o['custom_name_prefix'],
        auto_start=o['auto_start'],
        playlist_item_limit=o['playlist_item_limit'],
        split_by_chapters=o['split_by_chapters'],
        chapter_template=o['chapter_template'],
        subtitle_language=o['subtitle_language'],
        subtitle_mode=o['subtitle_mode'],
        ytdl_options_presets=o['ytdl_options_presets'],
        ytdl_options_overrides=o['ytdl_options_overrides'],
    )
    return web.Response(text=serializer.encode(result))


@routes.get(config.URL_PREFIX + 'subscriptions')
async def subscriptions_list(request):
    return web.Response(text=serializer.encode([s.to_public_dict() for s in submgr.list_all()]))


@routes.post(config.URL_PREFIX + 'subscriptions/update')
async def subscriptions_update(request):
    post = await _read_json_request(request)
    sub_id = post.get('id')
    if not sub_id:
        raise web.HTTPBadRequest(reason='missing subscription id')
    changes = {k: v for k, v in post.items() if k != 'id' and k in ('enabled', 'check_interval_minutes', 'name')}
    if not changes:
        raise web.HTTPBadRequest(reason='no valid fields to update')
    log.info("Subscription update requested for %s: %s", sub_id, sorted(changes.keys()))
    result = await submgr.update_subscription(str(sub_id), changes)
    return web.Response(text=serializer.encode(result))


@routes.post(config.URL_PREFIX + 'subscriptions/delete')
async def subscriptions_delete(request):
    post = await _read_json_request(request)
    ids = post.get('ids')
    if not ids or not isinstance(ids, list):
        raise web.HTTPBadRequest(reason='missing ids list')
    result = await submgr.delete_subscriptions([str(i) for i in ids])
    return web.Response(text=serializer.encode(result))


@routes.post(config.URL_PREFIX + 'subscriptions/check')
async def subscriptions_check(request):
    post = await _read_json_request(request)
    ids = post.get('ids')
    if ids is not None and not isinstance(ids, list):
        raise web.HTTPBadRequest(reason='ids must be a list')
    log.info("Subscription check-now requested for ids=%s", ids if ids else "all-enabled")
    result = await submgr.check_now([str(i) for i in ids] if ids else None)
    return web.Response(text=serializer.encode(result))

@routes.post(config.URL_PREFIX + 'delete')
async def delete(request):
    post = await _read_json_request(request)
    ids = post.get('ids')
    where = post.get('where')
    if not ids or where not in ['queue', 'done']:
        log.error("Bad request: missing 'ids' or incorrect 'where' value")
        raise web.HTTPBadRequest()
    status = await (dqueue.cancel(ids) if where == 'queue' else dqueue.clear(ids))
    log.info(f"Download delete request processed for ids: {ids}, where: {where}")
    return web.Response(text=serializer.encode(status))

@routes.post(config.URL_PREFIX + 'start')
async def start(request):
    post = await _read_json_request(request)
    ids = post.get('ids')
    log.info(f"Received request to start pending downloads for ids: {ids}")
    status = await dqueue.start_pending(ids)
    return web.Response(text=serializer.encode(status))


COOKIES_PATH = os.path.join(config.STATE_DIR, 'cookies.txt')

@routes.post(config.URL_PREFIX + 'upload-cookies')
async def upload_cookies(request):
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != 'cookies':
        return web.Response(status=400, text=serializer.encode({'status': 'error', 'msg': 'No cookies file provided'}))

    max_size = 1_000_000  # 1MB limit
    size = 0
    content = bytearray()
    while True:
        chunk = await field.read_chunk()
        if not chunk:
            break
        size += len(chunk)
        if size > max_size:
            return web.Response(status=400, text=serializer.encode({'status': 'error', 'msg': 'Cookie file too large (max 1MB)'}))
        content.extend(chunk)

    tmp_cookie_path = f"{COOKIES_PATH}.tmp"
    with open(tmp_cookie_path, 'wb') as f:
        f.write(content)
    os.replace(tmp_cookie_path, COOKIES_PATH)
    config.set_runtime_override('cookiefile', COOKIES_PATH)
    log.info(f'Cookies file uploaded ({size} bytes)')
    return web.Response(text=serializer.encode({'status': 'ok', 'msg': f'Cookies uploaded ({size} bytes)'}))

@routes.post(config.URL_PREFIX + 'delete-cookies')
async def delete_cookies(request):
    has_uploaded_cookies = os.path.exists(COOKIES_PATH)
    configured_cookiefile = config.YTDL_OPTIONS.get('cookiefile')
    has_manual_cookiefile = isinstance(configured_cookiefile, str) and configured_cookiefile and configured_cookiefile != COOKIES_PATH

    if not has_uploaded_cookies:
        if has_manual_cookiefile:
            return web.Response(
                status=400,
                text=serializer.encode({
                    'status': 'error',
                    'msg': 'Cookies are configured manually via YTDL_OPTIONS (cookiefile). Remove or change that setting manually; UI delete only removes uploaded cookies.'
                })
            )
        return web.Response(status=400, text=serializer.encode({'status': 'error', 'msg': 'No uploaded cookies to delete'}))

    os.remove(COOKIES_PATH)
    config.remove_runtime_override('cookiefile')
    success, msg = config.load_ytdl_options()
    if not success:
        log.error(f'Cookies file deleted, but failed to reload YTDL_OPTIONS: {msg}')
        return web.Response(status=500, text=serializer.encode({'status': 'error', 'msg': f'Cookies file deleted, but failed to reload YTDL_OPTIONS: {msg}'}))

    log.info('Cookies file deleted')
    return web.Response(text=serializer.encode({'status': 'ok'}))

@routes.get(config.URL_PREFIX + 'cookie-status')
async def cookie_status(request):
    configured_cookiefile = config.YTDL_OPTIONS.get('cookiefile')
    has_configured_cookies = isinstance(configured_cookiefile, str) and os.path.exists(configured_cookiefile)
    has_uploaded_cookies = os.path.exists(COOKIES_PATH)
    exists = has_uploaded_cookies or has_configured_cookies
    return web.Response(text=serializer.encode({'status': 'ok', 'has_cookies': exists}))

@routes.get(config.URL_PREFIX + 'history')
async def history(request):
    history = { 'done': [], 'queue': [], 'pending': []}

    for _, v in dqueue.queue.saved_items():
        history['queue'].append(v)
    for _, v in dqueue.done.saved_items():
        history['done'].append(v)
    for _, v in dqueue.pending.saved_items():
        history['pending'].append(v)

    log.info("Sending download history")
    return web.Response(text=serializer.encode(history))

@sio.event
async def connect(sid, environ):
    request = environ.get('aiohttp.request')
    session_id = auth_manager.get_session_id(request)
    if auth_manager.enabled and not session_id:
        log.info('Rejected socket connection for unauthenticated client: %s', sid)
        raise ConnectionRefusedError('Authentication required')
    auth_manager.register_socket(sid, session_id)
    log.info(f"Client connected: {sid}")
    await sio.emit('all', serializer.encode(dqueue.get()), to=sid)
    await sio.emit('subscriptions_all', serializer.encode([s.to_public_dict() for s in submgr.list_all()]), to=sid)
    await sio.emit('configuration', serializer.encode(config.frontend_safe()), to=sid)
    if config.CUSTOM_DIRS:
        await sio.emit('custom_dirs', serializer.encode(get_custom_dirs()), to=sid)
    if config.YTDL_OPTIONS_FILE:
        await sio.emit('ytdl_options_changed', serializer.encode(get_options_update_time()), to=sid)


@sio.event
async def disconnect(sid):
    auth_manager.unregister_socket(sid)
    log.info('Client disconnected: %s', sid)

def get_custom_dirs():
    cache_ttl_seconds = 5
    now = asyncio.get_running_loop().time()
    cache_key = (
        config.DOWNLOAD_DIR,
        config.AUDIO_DOWNLOAD_DIR,
        config.CUSTOM_DIRS_EXCLUDE_REGEX,
    )
    if (
        hasattr(get_custom_dirs, "_cache_key")
        and hasattr(get_custom_dirs, "_cache_value")
        and hasattr(get_custom_dirs, "_cache_time")
        and get_custom_dirs._cache_key == cache_key
        and (now - get_custom_dirs._cache_time) < cache_ttl_seconds
    ):
        return get_custom_dirs._cache_value

    def recursive_dirs(base):
        path = pathlib.Path(base)

        # Converts PosixPath object to string, and remove base/ prefix
        def convert(p):
            s = str(p)
            if s.startswith(base):
                s = s[len(base):]

            if s.startswith('/'):
                s = s[1:]

            return s

        # Include only directories which do not match the exclude filter
        def include_dir(d):
            if len(config.CUSTOM_DIRS_EXCLUDE_REGEX) == 0:
                return True
            else:
                return re.search(config.CUSTOM_DIRS_EXCLUDE_REGEX, d) is None

        # Recursively lists all subdirectories of DOWNLOAD_DIR.
        # Always include '' (the base directory itself) even when the
        # directory is empty or does not yet exist.
        dirs = list(filter(include_dir, map(convert, path.glob('**/'))))
        if '' not in dirs:
            dirs.insert(0, '')

        return dirs

    download_dir = recursive_dirs(config.DOWNLOAD_DIR)

    audio_download_dir = download_dir
    if config.DOWNLOAD_DIR != config.AUDIO_DOWNLOAD_DIR:
        audio_download_dir = recursive_dirs(config.AUDIO_DOWNLOAD_DIR)

    result = {
        "download_dir": download_dir,
        "audio_download_dir": audio_download_dir
    }
    get_custom_dirs._cache_key = cache_key
    get_custom_dirs._cache_time = now
    get_custom_dirs._cache_value = result
    return result

@routes.get(config.URL_PREFIX)
async def index(request):
    response = web.FileResponse(os.path.join(config.BASE_DIR, 'ui/dist/metube/browser/index.html'))
    if 'metube_theme' not in request.cookies:
        response.set_cookie('metube_theme', config.DEFAULT_THEME)
    return response

@routes.get(config.URL_PREFIX + 'robots.txt')
async def robots(request):
    if config.ROBOTS_TXT:
        response = web.FileResponse(os.path.join(config.BASE_DIR, config.ROBOTS_TXT))
    else:
        response = web.Response(
            text="User-agent: *\nDisallow: /download/\nDisallow: /audio_download/\n"
        )
    return response

@routes.get(config.URL_PREFIX + 'version')
async def version(request):
    return web.json_response({
        "yt-dlp": yt_dlp_version,
        "version": os.getenv("METUBE_VERSION", "dev")
    })

if config.URL_PREFIX != '/':
    @routes.get('/')
    async def index_redirect_root(request):
        return web.HTTPFound(config.URL_PREFIX)

    @routes.get(config.URL_PREFIX[:-1])
    async def index_redirect_dir(request):
        return web.HTTPFound(config.URL_PREFIX)

routes.static(config.URL_PREFIX + 'download/', config.DOWNLOAD_DIR, show_index=config.DOWNLOAD_DIRS_INDEXABLE)
routes.static(config.URL_PREFIX + 'audio_download/', config.AUDIO_DOWNLOAD_DIR, show_index=config.DOWNLOAD_DIRS_INDEXABLE)
routes.static(config.URL_PREFIX, os.path.join(config.BASE_DIR, 'ui/dist/metube/browser'))
try:
    app.add_routes(routes)
except ValueError as e:
    if 'ui/dist/metube/browser' in str(e):
        raise RuntimeError('Could not find the frontend UI static assets. Please run `node_modules/.bin/ng build` inside the ui folder') from e
    raise e

# https://github.com/aio-libs/aiohttp/pull/4615 waiting for release
# @routes.options(config.URL_PREFIX + 'add')
async def add_cors(request):
    return web.Response(text=serializer.encode({"status": "ok"}))

app.router.add_route('OPTIONS', config.URL_PREFIX + 'add', add_cors)
app.router.add_route('OPTIONS', config.URL_PREFIX + 'cancel-add', add_cors)
app.router.add_route('OPTIONS', config.URL_PREFIX + 'subscribe', add_cors)
app.router.add_route('OPTIONS', config.URL_PREFIX + 'subscriptions', add_cors)
app.router.add_route('OPTIONS', config.URL_PREFIX + 'subscriptions/update', add_cors)
app.router.add_route('OPTIONS', config.URL_PREFIX + 'subscriptions/delete', add_cors)
app.router.add_route('OPTIONS', config.URL_PREFIX + 'subscriptions/check', add_cors)
app.router.add_route('OPTIONS', config.URL_PREFIX + 'upload-cookies', add_cors)
app.router.add_route('OPTIONS', config.URL_PREFIX + 'delete-cookies', add_cors)

async def on_prepare(request, response):
    origin = request.headers.get('Origin')
    if origin and _cors_origins and ('*' in _cors_origins or origin in _cors_origins):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'

app.on_response_prepare.append(on_prepare)

def supports_reuse_port():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.close()
        return True
    except (AttributeError, OSError):
        return False

def isAccessLogEnabled():
    if config.ENABLE_ACCESSLOG:
        return access_logger
    else:
        return None

if __name__ == '__main__':
    logging.getLogger().setLevel(parseLogLevel(config.LOGLEVEL) or logging.INFO)
    log.info(f"Listening on {config.HOST}:{config.PORT}")


    # Auto-detect cookie file on startup
    if os.path.exists(COOKIES_PATH):
        config.set_runtime_override('cookiefile', COOKIES_PATH)
        log.info(f'Cookie file detected at {COOKIES_PATH}')

    if config.HTTPS:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=config.CERTFILE, keyfile=config.KEYFILE)
        web.run_app(app, host=config.HOST, port=int(config.PORT), reuse_port=supports_reuse_port(), ssl_context=ssl_context, access_log=isAccessLogEnabled())
    else:
        web.run_app(app, host=config.HOST, port=int(config.PORT), reuse_port=supports_reuse_port(), access_log=isAccessLogEnabled())
