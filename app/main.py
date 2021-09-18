#!/usr/bin/env python3
# pylint: disable=no-member,method-hidden

import os
import sys
from aiohttp import web
import socketio
import logging
import json

from ytdl import DownloadQueueNotifier, DownloadQueue

log = logging.getLogger('main')

class Config:
    _DEFAULTS = {
        'DOWNLOAD_DIR': '.',
        'AUDIO_DOWNLOAD_DIR': '%%DOWNLOAD_DIR',
        'URL_PREFIX': '',
        'OUTPUT_TEMPLATE': '%(title)s.%(ext)s',
        'YTDL_OPTIONS': '{}',
    }

    def __init__(self):
        for k, v in self._DEFAULTS.items():
            setattr(self, k, os.environ[k] if k in os.environ else v)
        for k, v in self.__dict__.items():
            if v.startswith('%%'):
                setattr(self, k, getattr(self, v[2:]))
        if not self.URL_PREFIX.endswith('/'):
            self.URL_PREFIX += '/'
        try:
            self.YTDL_OPTIONS = json.loads(self.YTDL_OPTIONS)
            assert isinstance(self.YTDL_OPTIONS, dict)
        except (json.decoder.JSONDecodeError, AssertionError):
            log.error('YTDL_OPTIONS is invalid')
            sys.exit(1)

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

@routes.post(config.URL_PREFIX + 'add')
async def add(request):
    post = await request.json()
    url = post.get('url')
    quality = post.get('quality')
    if not url or not quality:
        raise web.HTTPBadRequest()
    format = post.get('format')
    status = await dqueue.add(url, quality, format)
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

@sio.event
async def connect(sid, environ):
    await sio.emit('all', serializer.encode(dqueue.get()), to=sid)

@routes.get(config.URL_PREFIX)
def index(request):
    return web.FileResponse('ui/dist/metube/index.html')

if config.URL_PREFIX != '/':
    @routes.get('/')
    def index_redirect_root(request):
        return web.HTTPFound(config.URL_PREFIX)

    @routes.get(config.URL_PREFIX[:-1])
    def index_redirect_dir(request):
        return web.HTTPFound(config.URL_PREFIX)

routes.static(config.URL_PREFIX + 'favicon/', 'favicon')
routes.static(config.URL_PREFIX, 'ui/dist/metube')
app.add_routes(routes)


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
    web.run_app(app, port=8081)
