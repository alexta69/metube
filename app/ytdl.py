import os
import yt_dlp
from collections import OrderedDict
import shelve
import time
import asyncio
import multiprocessing
import logging
from dl_formats import get_format, get_opts

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
        self.filename = None
        self.timestamp = time.time_ns()

class Download:
    manager = None

    def __init__(self, download_dir, output_template, output_template_chapter, quality, format, ytdl_opts, info):
        self.download_dir = download_dir
        self.output_template = output_template
        self.output_template_chapter = output_template_chapter
        self.format = get_format(format, quality)
        self.ytdl_opts = get_opts(format, quality, ytdl_opts)
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
                    self.status_queue.put({'status': 'finished', 'filename': d['info_dict']['filepath']})
            ret = yt_dlp.YoutubeDL(params={
                'quiet': True,
                'no_color': True,
                #'skip_download': True,
                'paths': {"home": self.download_dir},
                'outtmpl': { "default": self.output_template, "chapter": self.output_template_chapter },
                'format': self.format,
                'cachedir': False,
                'socket_timeout': 30,
                'progress_hooks': [put_status],
                'postprocessor_hooks': [put_status_postprocessor],
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
        asyncio.create_task(self.update_status())
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
            if 'filename' in status:
                self.info.filename = os.path.relpath(status.get('filename'), self.download_dir)
            self.info.status = status['status']
            self.info.msg = status.get('msg')
            if 'downloaded_bytes' in status:
                total = status.get('total_bytes') or status.get('total_bytes_estimate')
                if total:
                    self.info.percent = status['downloaded_bytes'] / total * 100
            self.info.speed = status.get('speed')
            self.info.eta = status.get('eta')
            await self.notifier.updated(self.info)

class PersistentQueue:
    def __init__(self, path):
        pdir = os.path.dirname(path)
        if not os.path.isdir(pdir):
            os.mkdir(pdir)
        with shelve.open(path, 'c'):
            pass
        self.path = path
        self.dict = OrderedDict()
    
    def load(self):
        for k, v in self.saved_items():
            self.dict[k] = Download(None, None, None, None, None, {}, v)

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
        key = value.info.id
        self.dict[key] = value
        with shelve.open(self.path, 'w') as shelf:
            shelf[key] = value.info
    
    def delete(self, key):
        del self.dict[key]
        with shelve.open(self.path, 'w') as shelf:
            shelf.pop(key)

    def next(self):
        k, v = next(iter(self.dict.items()))
        return k, v
    
    def empty(self):
        return not bool(self.dict)


class DownloadQueue:
    def __init__(self, config, notifier):
        self.config = config
        self.notifier = notifier
        self.queue = PersistentQueue(self.config.STATE_DIR + '/queue')
        self.done = PersistentQueue(self.config.STATE_DIR + '/completed')
        self.done.load()
    
    async def __import_queue(self):
        for k, v in self.queue.saved_items():
            await self.add(v.url, v.quality, v.format)

    async def initialize(self):
        self.event = asyncio.Event()
        asyncio.create_task(self.__download())
        asyncio.create_task(self.__import_queue())

    def __extract_info(self, url):
        return yt_dlp.YoutubeDL(params={
            'quiet': True,
            'no_color': True,
            'extract_flat': True,
            **self.config.YTDL_OPTIONS,
        }).extract_info(url, download=False)

    async def __add_entry(self, entry, quality, format, already):
        etype = entry.get('_type') or 'video'
        if etype == 'playlist':
            entries = entry['entries']
            log.info(f'playlist detected with {len(entries)} entries')
            playlist_index_digits = len(str(len(entries)))
            results = []
            for index, etr in enumerate(entries, start=1):
                etr["playlist"] = entry["id"]
                etr["playlist_index"] = '{{0:0{0:d}d}}'.format(playlist_index_digits).format(index)
                for property in ("id", "title", "uploader", "uploader_id"):
                    if property in entry:
                        etr[f"playlist_{property}"] = entry[property]
                results.append(await self.__add_entry(etr, quality, format, already))
            if any(res['status'] == 'error' for res in results):
                return {'status': 'error', 'msg': ', '.join(res['msg'] for res in results if res['status'] == 'error' and 'msg' in res)}
            return {'status': 'ok'}
        elif etype == 'video' or etype.startswith('url') and 'id' in entry and 'title' in entry:
            if not self.queue.exists(entry['id']):
                dl = DownloadInfo(entry['id'], entry['title'], entry.get('webpage_url') or entry['url'], quality, format)
                dldirectory = self.config.DOWNLOAD_DIR if (quality != 'audio' and format != 'mp3') else self.config.AUDIO_DOWNLOAD_DIR
                output = self.config.OUTPUT_TEMPLATE
                output_chapter = self.config.OUTPUT_TEMPLATE_CHAPTER
                for property, value in entry.items():
                    if property.startswith("playlist"):
                        output = output.replace(f"%({property})s", str(value))
                self.queue.put(Download(dldirectory, output, output_chapter, quality, format, self.config.YTDL_OPTIONS, dl))
                self.event.set()
                await self.notifier.added(dl)
            return {'status': 'ok'}
        elif etype.startswith('url'):
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
            self.done.delete(id)
            await self.notifier.cleared(id)
        return {'status': 'ok'}

    def get(self):
        return(list((k, v.info) for k, v in self.queue.items()),
               list((k, v.info) for k, v in self.done.items()))

    async def __download(self):
        while True:
            while self.queue.empty():
                log.info('waiting for item to download')
                await self.event.wait()
                self.event.clear()
            id, entry = self.queue.next()
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
            if self.queue.exists(id):
                self.queue.delete(id)
                if entry.canceled:
                    await self.notifier.canceled(id)
                else:
                    self.done.put(entry)
                    await self.notifier.completed(entry.info)
