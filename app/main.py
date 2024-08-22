#!/usr/bin/env python3
# pylint: disable=no-member,method-hidden

import os
import sys
from aiohttp import web
import socketio
import logging
import json
import pathlib

from ytdl import DownloadQueueNotifier, DownloadQueue

log = logging.getLogger('main')

class Config:
    _DEFAULTS = {
        'DOWNLOAD_DIR': '.',
        'AUDIO_DOWNLOAD_DIR': '%%DOWNLOAD_DIR',
        'TEMP_DIR': '%%DOWNLOAD_DIR',
        'DOWNLOAD_DIRS_INDEXABLE': 'false',
        'CUSTOM_DIRS': 'true',
        'CREATE_CUSTOM_DIRS': 'true',
        'DELETE_FILE_ON_TRASHCAN': 'false',
        'STATE_DIR': '.',
        'URL_PREFIX': '',
        'PUBLIC_HOST_URL': 'download/',
        'PUBLIC_HOST_AUDIO_URL': 'audio_download/',
        'OUTPUT_TEMPLATE': '%(title)s.%(ext)s',
        'OUTPUT_TEMPLATE_CHAPTER': '%(title)s - %(section_number)s %(section_title)s.%(ext)s',
        'YTDL_OPTIONS': '{}',
        'YTDL_OPTIONS_FILE': '',
        'HOST': '0.0.0.0',
        'PORT': '8081',
        'BASE_DIR': '',
        'DEFAULT_THEME': 'auto'
    }

    _BOOLEAN = ('DOWNLOAD_DIRS_INDEXABLE', 'CUSTOM_DIRS', 'CREATE_CUSTOM_DIRS', 'DELETE_FILE_ON_TRASHCAN')

    def __init__(self):
        for k, v in self._DEFAULTS.items():
            setattr(self, k, os.environ[k] if k in os.environ else v)

        for k, v in self.__dict__.items():
            if v.startswith('%%'):
                setattr(self, k, getattr(self, v[2:]))
            if k in self._BOOLEAN:
                if v not in ('true', 'false', 'True', 'False', 'on', 'off', '1', '0'):
                    log.error(f'Environment variable "{k}" is set to a non-boolean value "{v}"')
                    sys.exit(1)
                setattr(self, k, v in ('true', 'True', 'on', '1'))

        if not self.URL_PREFIX.endswith('/'):
            self.URL_PREFIX += '/'

        try:
            self.YTDL_OPTIONS = json.loads(self.YTDL_OPTIONS)
            assert isinstance(self.YTDL_OPTIONS, dict)
        except (json.decoder.JSONDecodeError, AssertionError):
            log.error('YTDL_OPTIONS is invalid')
            sys.exit(1)

        if self.YTDL_OPTIONS_FILE:
            log.info(f'Loading yt-dlp custom options from "{self.YTDL_OPTIONS_FILE}"')
            if not os.path.exists(self.YTDL_OPTIONS_FILE):
                log.error(f'File "{self.YTDL_OPTIONS_FILE}" not found')
                sys.exit(1)
            try:
                with open(self.YTDL_OPTIONS_FILE) as json_data:
                    opts = json.load(json_data)
                assert isinstance(opts, dict)
            except (json.decoder.JSONDecodeError, AssertionError):
                log.error('YTDL_OPTIONS_FILE contents is invalid')
                sys.exit(1)
            self.YTDL_OPTIONS.update(opts)

config = Config()

class ObjectSerializer(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, object):
            return obj.__dict__
        else:
            return json.JSONEncoder.default(self, obj)

serializer = ObjectSerializer()
app = web.Application()
sio = socketio.AsyncServer(cors_allowed_origins='*')
sio.attach(app, socketio_path=config.URL_PREFIX + 'socket.io')
routes = web.RouteTableDef()

class Notifier(DownloadQueueNotifier):
    async def added(self, dl):
        await sio.emit('added', serializer.encode(dl))

    async def updated(self, dl):
        await sio.emit('updated', serializer.encode(dl))

    async def completed(self, dl):
        await sio.emit('completed', serializer.encode(dl))

    async def canceled(self, id):
        await sio.emit('canceled', serializer.encode(id))

    async def cleared(self, id):
        await sio.emit('cleared', serializer.encode(id))

dqueue = DownloadQueue(config, Notifier())
app.on_startup.append(lambda app: dqueue.initialize())

@routes.post(config.URL_PREFIX + 'add')
async def add(request):
    post = await request.json()
    url = post.get('url')
    quality = post.get('quality')
    if not url or not quality:
        raise web.HTTPBadRequest()
    format = post.get('format')
    folder = post.get('folder')
    custom_name_prefix = post.get('custom_name_prefix')
    auto_start = post.get('auto_start')
    if custom_name_prefix is None:
        custom_name_prefix = ''
    if auto_start is None:
        auto_start = True
    status = await dqueue.add(url, quality, format, folder, custom_name_prefix, auto_start)
    return web.Response(text=serializer.encode(status))

@routes.post(config.URL_PREFIX + 'delete')
async def delete(request):
    post = await request.json()
    ids = post.get('ids')
    where = post.get('where')
    if not ids or where not in ['queue', 'done']:
        raise web.HTTPBadRequest()
    status = await (dqueue.cancel(ids) if where == 'queue' else dqueue.clear(ids))
    return web.Response(text=serializer.encode(status))

@routes.post(config.URL_PREFIX + 'start')
async def start(request):
    post = await request.json()
    ids = post.get('ids')
    status = await dqueue.start_pending(ids)
    return web.Response(text=serializer.encode(status))

@routes.get(config.URL_PREFIX + 'history')
async def history(request):
    history = { 'done': [], 'queue': []}

    for _ ,v in dqueue.queue.saved_items():
        history['queue'].append(v)
    for _ ,v in dqueue.done.saved_items():
        history['done'].append(v)

    return web.Response(text=serializer.encode(history))

@sio.event
async def connect(sid, environ):
    await sio.emit('all', serializer.encode(dqueue.get()), to=sid)
    await sio.emit('configuration', serializer.encode(config), to=sid)
    if config.CUSTOM_DIRS:
        await sio.emit('custom_dirs', serializer.encode(get_custom_dirs()), to=sid)

def get_custom_dirs():
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

        # Recursively lists all subdirectories of DOWNLOAD_DIR
        dirs = list(filter(None, map(convert, path.glob('**'))))

        return dirs

    download_dir = recursive_dirs(config.DOWNLOAD_DIR)

    audio_download_dir = download_dir
    if config.DOWNLOAD_DIR != config.AUDIO_DOWNLOAD_DIR:
        audio_download_dir = recursive_dirs(config.AUDIO_DOWNLOAD_DIR)

    return {
        "download_dir": download_dir,
        "audio_download_dir": audio_download_dir
    }

@routes.get(config.URL_PREFIX)
def index(request):
    response = web.FileResponse(os.path.join(config.BASE_DIR, 'ui/dist/metube/index.html'))
    if 'metube_theme' not in request.cookies:
        response.set_cookie('metube_theme', config.DEFAULT_THEME)
    return response

if config.URL_PREFIX != '/':
    @routes.get('/')
    def index_redirect_root(request):
        return web.HTTPFound(config.URL_PREFIX)

    @routes.get(config.URL_PREFIX[:-1])
    def index_redirect_dir(request):
        return web.HTTPFound(config.URL_PREFIX)

routes.static(config.URL_PREFIX + 'download/', config.DOWNLOAD_DIR, show_index=config.DOWNLOAD_DIRS_INDEXABLE)
routes.static(config.URL_PREFIX + 'audio_download/', config.AUDIO_DOWNLOAD_DIR, show_index=config.DOWNLOAD_DIRS_INDEXABLE)
routes.static(config.URL_PREFIX, os.path.join(config.BASE_DIR, 'ui/dist/metube'))
try:
    app.add_routes(routes)
except ValueError as e:
    if 'ui/dist/metube' in str(e):
        raise RuntimeError('Could not find the frontend UI static assets. Please run `node_modules/.bin/ng build` inside the ui folder') from e
    raise e

# https://github.com/aio-libs/aiohttp/pull/4615 waiting for release
# @routes.options(config.URL_PREFIX + 'add')
async def add_cors(request):
    return web.Response(text=serializer.encode({"status": "ok"}))

app.router.add_route('OPTIONS', config.URL_PREFIX + 'add', add_cors)


async def on_prepare(request, response):
    if 'Origin' in request.headers:
        response.headers['Access-Control-Allow-Origin'] = request.headers['Origin']
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'

app.on_response_prepare.append(on_prepare)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    log.info(f"Listening on {config.HOST}:{config.PORT}")
    web.run_app(app, host=config.HOST, port=int(config.PORT), reuse_port=True)
