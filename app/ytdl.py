import os
import sys
import youtube_dl
from collections import OrderedDict
import asyncio
import multiprocessing
import logging

log = logging.getLogger('ytdl')

class DownloadInfo:
    def __init__(self, id, title, url):
        self.id, self.title, self.url = id, title, url
        self.status = self.msg = self.percent = self.speed = self.eta = None

class Download:
    manager = None

    def __init__(self, download_dir, info):
        self.download_dir = download_dir
        self.info = info
        self.tmpfilename = None
        self.status_queue = None
        self.proc = None
        self.loop = None
    
    def _download(self):
        try:
            ret = youtube_dl.YoutubeDL(params={
                'quiet': True,
                'no_color': True,
                #'skip_download': True,
                'outtmpl': os.path.join(self.download_dir, '%(title)s.%(ext)s'),
                'cachedir': False,
                'socket_timeout': 30,
                'progress_hooks': [lambda d: self.status_queue.put(d)],
            }).download([self.info.url])
            self.status_queue.put({'status': 'finished' if ret == 0 else 'error'})
        except youtube_dl.utils.YoutubeDLError as exc:
            self.status_queue.put({'status': 'error', 'msg': str(exc)})
    
    async def start(self):
        if Download.manager is None:
            Download.manager = multiprocessing.Manager()
        self.status_queue = Download.manager.Queue()
        self.proc = multiprocessing.Process(target=self._download)
        self.proc.start()
        self.loop = asyncio.get_running_loop()
        return await self.loop.run_in_executor(None, self.proc.join) 

    def cancel(self):
        if self.running():
            self.proc.kill()

    def close(self):
        if self.proc is not None:
            self.proc.close()
            self.status_queue.put(None)

    def running(self):
        try:
            return self.proc is not None and self.proc.is_alive()
        except ValueError:
            return False

    async def update_status(self, updated_cb):
        await updated_cb()
        while self.running():
            status = await self.loop.run_in_executor(None, self.status_queue.get)
            if status is None:
                return
            self.tmpfilename = status.get('tmpfilename')
            self.info.status = status['status']
            self.info.msg = status.get('msg')
            if 'downloaded_bytes' in status:
                total = status.get('total_bytes') or status.get('total_bytes_estimate')
                if total:
                    self.info.percent = status['downloaded_bytes'] / total * 100
            self.info.speed = status.get('speed')
            self.info.eta = status.get('eta')
            await updated_cb()

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

class DownloadQueue:
    def __init__(self, config, notifier):
        self.config = config
        self.notifier = notifier
        self.queue = OrderedDict()
        self.done = OrderedDict()
        self.event = asyncio.Event()
        asyncio.ensure_future(self.__download())

    def __extract_info(self, url):
        return youtube_dl.YoutubeDL(params={
            'quiet': True,
            'no_color': True,
            'extract_flat': True,
        }).extract_info(url, download=False)

    async def add(self, url):
        log.info(f'adding {url}')
        try:
            info = await asyncio.get_running_loop().run_in_executor(None, self.__extract_info, url)
        except youtube_dl.utils.YoutubeDLError as exc:
            return {'status': 'error', 'msg': str(exc)}
        etype = info.get('_type') or 'video'
        if etype == 'playlist':
            entries = info['entries']
            log.info(f'playlist detected with {len(entries)} entries')
        elif etype == 'video':
            entries = [info]
            log.info('single video detected')
        else:
            return {'status': 'error', 'msg': f'Unsupported resource requested: {etype}, please enter video or playlist URLs only'}
        for entry in entries:
            if entry['id'] not in self.queue:
                dl = DownloadInfo(entry['id'], entry['title'], entry.get('webpage_url') or entry['url'])
                self.queue[entry['id']] = Download(self.config.DOWNLOAD_DIR, dl)
                await self.notifier.added(dl)
        self.event.set()
        return {'status': 'ok'}
    
    async def cancel(self, ids):
        for id in ids:
            if id not in self.queue:
                log.warn(f'requested cancel for non-existent download {id}')
                continue
            self.queue[id].cancel()
            del self.queue[id]
            await self.notifier.canceled(id)
        return {'status': 'ok'}

    async def clear(self, ids):
        for id in ids:
            if id not in self.done:
                log.warn(f'requested delete for non-existent download {id}')
                continue
            del self.done[id]
            await self.notifier.cleared(id)
        return {'status': 'ok'}

    def get(self):
        return(list((k, v.info) for k, v in self.queue.items()),
               list((k, v.info) for k, v in self.done.items()))
    
    async def __download(self):
        while True:
            while not self.queue:
                log.info('waiting for item to download')
                await self.event.wait()
                self.event.clear()
            id, entry = next(iter(self.queue.items()))
            log.info(f'downloading {entry.info.title}')
            entry.info.status = 'preparing'
            start_aw = entry.start()
            async def updated_cb(): await self.notifier.updated(entry.info)
            asyncio.ensure_future(entry.update_status(updated_cb))
            await start_aw
            if entry.info.status != 'finished':
                if entry.tmpfilename and os.path.isfile(entry.tmpfilename):
                    try:
                        os.remove(entry.tmpfilename)
                    except:
                        pass
                entry.info.status = 'error'
            entry.close()
            if id in self.queue:
                del self.queue[id]
                self.done[id] = entry
                await self.notifier.completed(entry.info)
