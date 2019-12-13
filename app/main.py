#!/usr/bin/env python3
# pylint: disable=no-member,method-hidden

import os
from aiohttp import web
import asyncio
import socketio
import time
import logging
import json

from ytdl import DownloadQueueNotifier, DownloadQueue

log = logging.getLogger('main')

class Config:
    _DEFAULTS = {
        'DOWNLOAD_DIR': '.',
        'URL_PREFIX': '',
    }

    def __init__(self):
        for k, v in self._DEFAULTS.items():
            setattr(self, k, os.environ[k] if k in os.environ else v)
        if not self.URL_PREFIX.endswith('/'):
            self.URL_PREFIX += '/'

config = Config()

class ObjectSerializer(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, object):
            return obj.__dict__
        else:
            return json.JSONEncoder.default(self, obj)

serializer = ObjectSerializer()
app = web.Application()
sio = socketio.AsyncServer()
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
    status = await dqueue.add(url, quality)
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


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    web.run_app(app, port=8081)
