import os
import yt_dlp
from collections import OrderedDict
import asyncio
import multiprocessing
import logging

log = logging.getLogger('ytdl')

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
    def __init__(self, id, title, url, quality, format):
        self.id, self.title, self.url = id, title, url
        self.quality = quality
        self.format = format
        self.status = self.msg = self.percent = self.speed = self.eta = None

class Download:
    manager = None

    def __init__(self, download_dir, output_template, quality, format, ytdl_opts, info):
        self.download_dir = download_dir
        self.output_template = output_template
        vfmt, afmt = '', ''
        if format == 'mp4':
            vfmt, afmt = '[ext=mp4]', '[ext=m4a]'
        if quality == 'best':
            self.format = f'bestvideo{vfmt}+bestaudio{afmt}/best{vfmt}'
        elif quality in ('1440p', '1080p', '720p', '480p'):
            res = quality[:-1]
            self.format = f'bestvideo[height<={res}]{vfmt}+bestaudio{afmt}/best[height<={res}]{vfmt}'
        elif quality == 'audio':
            self.format = f'bestaudio{afmt}'
        elif quality.startswith('custom:'):
            self.format = quality[7:]
        else:
            raise Exception(f'unknown quality {quality}')
        self.ytdl_opts = ytdl_opts
        self.info = info
        self.canceled = False
        self.tmpfilename = None
        self.status_queue = None
        self.proc = None
        self.loop = None
        self.notifier = None

    def _download(self):
        try:
            def put_status(st):
                self.status_queue.put({k: v for k, v in st.items() if k in (
                    'tmpfilename',
                    'status',
                    'msg',
                    'total_bytes',
                    'total_bytes_estimate',
                    'downloaded_bytes',
                    'speed',
                    'eta',
                )})
            ret = yt_dlp.YoutubeDL(params={
                'quiet': True,
                'no_color': True,
                #'skip_download': True,
                'outtmpl': os.path.join(self.download_dir, self.output_template),
                'format': self.format,
                'cachedir': False,
                'socket_timeout': 30,
                'progress_hooks': [put_status],
                **self.ytdl_opts,
            }).download([self.info.url])
            self.status_queue.put({'status': 'finished' if ret == 0 else 'error'})
        except yt_dlp.utils.YoutubeDLError as exc:
            self.status_queue.put({'status': 'error', 'msg': str(exc)})

    async def start(self, notifier):
        if Download.manager is None:
            Download.manager = multiprocessing.Manager()
        self.status_queue = Download.manager.Queue()
        self.proc = multiprocessing.Process(target=self._download)
        self.proc.start()
        self.loop = asyncio.get_running_loop()
        self.notifier = notifier
        self.info.status = 'preparing'
        await self.notifier.updated(self.info)
        asyncio.ensure_future(self.update_status())
        return await self.loop.run_in_executor(None, self.proc.join)

    def cancel(self):
        if self.running():
            self.proc.kill()
        self.canceled = True

    def close(self):
        if self.started():
            self.proc.close()
            self.status_queue.put(None)

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
            await self.notifier.updated(self.info)

class DownloadQueue:
    def __init__(self, config, notifier):
        self.config = config
        self.notifier = notifier
        self.queue = OrderedDict()
        self.done = OrderedDict()
        self.event = asyncio.Event()
        asyncio.ensure_future(self.__download())

    def __extract_info(self, url):
        return yt_dlp.YoutubeDL(params={
            'quiet': True,
            'no_color': True,
            'extract_flat': True,
            **self.config.YTDL_OPTIONS,
        }).extract_info(url, download=False, process=False)

    async def __add_entry(self, entry, quality, format, already):
        etype = entry.get('_type') or 'video'
        if etype == 'playlist':
            entries = entry['entries']
            log.info(f'playlist detected with {len(entries)} entries')
            results = []
            for etr in entries:
                results.append(await self.__add_entry(etr, quality, format, already))
            if any(res['status'] == 'error' for res in results):
                return {'status': 'error', 'msg': ', '.join(res['msg'] for res in results if res['status'] == 'error' and 'msg' in res)}
            return {'status': 'ok'}
        elif etype == 'video' or etype.startswith('url') and 'id' in entry and 'title' in entry:
            if entry['id'] not in self.queue:
                dl = DownloadInfo(entry['id'], entry['title'], entry.get('webpage_url') or entry['url'], quality, format)
                dldirectory = self.config.DOWNLOAD_DIR if quality != 'audio' else self.config.AUDIO_DOWNLOAD_DIR
                self.queue[entry['id']] = Download(dldirectory, self.config.OUTPUT_TEMPLATE, quality, format, self.config.YTDL_OPTIONS, dl)
                self.event.set()
                await self.notifier.added(dl)
            return {'status': 'ok'}
        elif etype == 'url':
            return await self.add(entry['url'], quality, format, already)
        return {'status': 'error', 'msg': f'Unsupported resource "{etype}"'}

    async def add(self, url, quality, format, already=None):
        log.info(f'adding {url}')
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
        return await self.__add_entry(entry, quality, format, already)

    async def cancel(self, ids):
        for id in ids:
            if id not in self.queue:
                log.warn(f'requested cancel for non-existent download {id}')
                continue
            if self.queue[id].started():
                self.queue[id].cancel()
            else:
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
            await entry.start(self.notifier)
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
                if entry.canceled:
                    await self.notifier.canceled(id)
                else:
                    self.done[id] = entry
                    await self.notifier.completed(entry.info)
