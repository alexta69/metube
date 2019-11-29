#!/usr/bin/env python3

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
    }

    def __init__(self):
        for k, v in self._DEFAULTS.items():
            setattr(self, k, os.environ[k] if k in os.environ else v)

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
sio.attach(app)
routes = web.RouteTableDef()

class Notifier(DownloadQueueNotifier):
    async def added(self, dl):
        await sio.emit('added', serializer.encode(dl))

    async def updated(self, dl):
        await sio.emit('updated', serializer.encode(dl))

    async def deleted(self, id):
        await sio.emit('deleted', serializer.encode(id))

dqueue = DownloadQueue(config, Notifier())

@routes.post('/add')
async def add(request):
    post = await request.json()
    url = post.get('url')
    if not url:
        raise web.HTTPBadRequest()
    status = await dqueue.add(url)
    return web.Response(text=serializer.encode(status))

@routes.post('/delete')
async def delete(request):
    post = await request.json()
    ids = post.get('ids')
    if not ids:
        raise web.HTTPBadRequest()
    status = await dqueue.delete(ids)
    return web.Response(text=serializer.encode(status))

@routes.get('/queue')
def queue(request):
    ret = dqueue.get()
    return web.Response(text=serializer.encode(ret))

@sio.event
async def connect(sid, environ):
    ret = dqueue.get()
    #ret = [["XeNTV0kyHaU", {"id": "XeNTV0kyHaU", "title": "2020 Mercedes ACTROS \u2013 Digital Side Mirrors, Electronic Stability, Auto Braking, Side Guard Safety", "url": "XeNTV0kyHaU", "status": None, "percentage": 0}], ["76wlIusQe9U", {"id": "76wlIusQe9U", "title": "Toyota HIACE 2020 \u2013 Toyota Wagon /  Toyota HIACE 2019 and 2020", "url": "76wlIusQe9U", "status": None, "percentage": 0}], ["n_d5LPwflMM", {"id": "n_d5LPwflMM", "title": "2020 Toyota GRANVIA \u2013 Toyota 8 Seater LUXURY VAN / ALL-NEW Toyota GRANVIA 2020", "url": "n_d5LPwflMM", "status": None, "percentage": 0}], ["Dv4ZFhCpF1M", {"id": "Dv4ZFhCpF1M", "title": "Toyota SIENNA 2019 vs Honda ODYSSEY 2019", "url": "Dv4ZFhCpF1M", "status": None, "percentage": 0}], ["GjHJFb3Mgqw", {"id": "GjHJFb3Mgqw", "title": "How It's Made (Buses) \u2013 How Buses are made? SETRA BUS Production", "url": "GjHJFb3Mgqw", "status": None, "percentage": 0}]]
    await sio.emit('queue', serializer.encode(ret), to=sid)

@routes.get('/')
def index(request):
    return web.FileResponse('ui/dist/metube/index.html')

routes.static('/favicon/', 'favicon')
routes.static('/', 'ui/dist/metube')

app.add_routes(routes)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    web.run_app(app, port=8081)
