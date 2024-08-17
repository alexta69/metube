import os
import yt_dlp
from collections import OrderedDict
import shelve
import time
import asyncio
import logging
import re
from dl_formats import get_format, get_opts, AUDIO_FORMATS
from datetime import datetime

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
    def __init__(self, id, title, url, quality, format, folder, custom_name_prefix, error):
        self.id = id if len(custom_name_prefix) == 0 else f'{custom_name_prefix}.{id}'
        self.title = title if len(custom_name_prefix) == 0 else f'{custom_name_prefix}.{title}'
        self.url = url
        self.quality = quality
        self.format = format
        self.folder = folder
        self.custom_name_prefix = custom_name_prefix
        self.msg = self.percent = self.speed = self.eta = None
        self.status = "pending"
        self.size = None
        self.timestamp = time.time_ns()
        self.error = error

class Download:
    def __init__(self, download_dir, temp_dir, output_template, output_template_chapter, quality, format, ytdl_opts, info):
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.output_template = output_template
        self.output_template_chapter = output_template_chapter
        self.format = get_format(format, quality)
        self.ytdl_opts = get_opts(format, quality, ytdl_opts)
        self.info = info
        self.canceled = False
        self.tmpfilename = None

    async def start(self, notifier):
        self.info.status = 'preparing'
        await notifier.updated(self.info)
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(None, self._download)
            if result['status'] == 'finished':
                self.info.status = 'finished'
                self.info.filename = result.get('filename')
                self.info.size = os.path.getsize(result['filename']) if os.path.exists(result['filename']) else None
            else:
                self.info.status = 'error'
                self.info.msg = result.get('msg', 'Unknown error occurred')
        except Exception as e:
            self.info.status = 'error'
            self.info.msg = str(e)
        
        await notifier.updated(self.info)

    def _download(self):
        ydl_opts = {
            'quiet': True,
            'no_color': True,
            'paths': {"home": self.download_dir, "temp": self.temp_dir},
            'outtmpl': {"default": self.output_template, "chapter": self.output_template_chapter},
            'format': self.format,
            'socket_timeout': 30,
            'ignore_no_formats_error': True,
            **self.ytdl_opts,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.info.url, download=True)
                return {'status': 'finished', 'filename': ydl.prepare_filename(info)}
            except yt_dlp.utils.DownloadError as e:
                return {'status': 'error', 'msg': str(e)}

    def cancel(self):
        self.canceled = True

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
            self.dict[k] = Download(None, None, None, None, None, None, {}, v)

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
        key = value.info.url
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
        self.pending = PersistentQueue(self.config.STATE_DIR + '/pending')
        self.done.load()
        self.active_downloads = set()
        self.max_concurrent_downloads = 3  # Adjust this value as needed
        self.event = asyncio.Event()

    async def initialize(self):
        await self.__import_queue()

    async def run(self):
        while True:
            try:
                await self.__manage_downloads()
            except Exception as e:
                log.error(f"Error in download queue: {str(e)}")
                await asyncio.sleep(5)  # Wait a bit before retrying

    async def __import_queue(self):
        for k, v in self.queue.saved_items():
            await self.add(v.url, v.quality, v.format, v.folder, v.custom_name_prefix)

    def __extract_info(self, url):
        return yt_dlp.YoutubeDL(params={
            'quiet': True,
            'no_color': True,
            'extract_flat': True,
            'ignore_no_formats_error': True,
            'paths': {"home": self.config.DOWNLOAD_DIR, "temp": self.config.TEMP_DIR},
            **self.config.YTDL_OPTIONS,
        }).extract_info(url, download=False)

    def __calc_download_path(self, quality, format, folder):
        base_directory = self.config.DOWNLOAD_DIR if (quality != 'audio' and format not in AUDIO_FORMATS) else self.config.AUDIO_DOWNLOAD_DIR
        if folder:
            if not self.config.CUSTOM_DIRS:
                return None, {'status': 'error', 'msg': f'A folder for the download was specified but CUSTOM_DIRS is not true in the configuration.'}
            dldirectory = os.path.realpath(os.path.join(base_directory, folder))
            real_base_directory = os.path.realpath(base_directory)
            if not dldirectory.startswith(real_base_directory):
                return None, {'status': 'error', 'msg': f'Folder "{folder}" must resolve inside the base download directory "{real_base_directory}"'}
            if not os.path.isdir(dldirectory):
                if not self.config.CREATE_CUSTOM_DIRS:
                    return None, {'status': 'error', 'msg': f'Folder "{folder}" for download does not exist inside base directory "{real_base_directory}", and CREATE_CUSTOM_DIRS is not true in the configuration.'}
                os.makedirs(dldirectory, exist_ok=True)
        else:
            dldirectory = base_directory
        return dldirectory, None

    async def __add_entry(self, entry, quality, format, folder, custom_name_prefix, auto_start, already):
        if not entry:
            return {'status': 'error', 'msg': "Invalid/empty data was given."}

        error = None
        if "live_status" in entry and "release_timestamp" in entry and entry.get("live_status") == "is_upcoming":
            dt_ts = datetime.fromtimestamp(entry.get("release_timestamp")).strftime('%Y-%m-%d %H:%M:%S %z')
            error = f"Live stream is scheduled to start at {dt_ts}"
        else:
            if "msg" in entry:
                error = entry["msg"]

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
                results.append(await self.__add_entry(etr, quality, format, folder, custom_name_prefix, auto_start, already))
            if any(res['status'] == 'error' for res in results):
                return {'status': 'error', 'msg': ', '.join(res['msg'] for res in results if res['status'] == 'error' and 'msg' in res)}
            return {'status': 'ok'}
        elif etype == 'video' or etype.startswith('url') and 'id' in entry and 'title' in entry:
            if not self.queue.exists(entry['id']):
                dl = DownloadInfo(entry['id'], entry['title'], entry.get('webpage_url') or entry['url'], quality, format, folder, custom_name_prefix, error)
                dldirectory, error_message = self.__calc_download_path(quality, format, folder)
                if error_message is not None:
                    return error_message
                output = self.config.OUTPUT_TEMPLATE if len(custom_name_prefix) == 0 else f'{custom_name_prefix}.{self.config.OUTPUT_TEMPLATE}'
                output_chapter = self.config.OUTPUT_TEMPLATE_CHAPTER
                for property, value in entry.items():
                    if property.startswith("playlist"):
                        output = output.replace(f"%({property})s", str(value))
                if auto_start is True:
                    self.queue.put(Download(dldirectory, self.config.TEMP_DIR, output, output_chapter, quality, format, self.config.YTDL_OPTIONS, dl))
                    self.event.set()
                else:
                    self.pending.put(Download(dldirectory, self.config.TEMP_DIR, output, output_chapter, quality, format, self.config.YTDL_OPTIONS, dl))
                await self.notifier.added(dl)
            return {'status': 'ok'}
        elif etype.startswith('url'):
            return await self.add(entry['url'], quality, format, folder, custom_name_prefix, auto_start, already)
        return {'status': 'error', 'msg': f'Unsupported resource "{etype}"'}

    async def add(self, url, quality, format, folder, custom_name_prefix, auto_start=True, already=None):
        log.info(f'adding {url}: {quality=} {format=} {already=} {folder=} {custom_name_prefix=}')
        already = set() if already is None else already
        if url in already:
            log.info('recursion detected, skipping')
            return {'status': 'ok'}
        else:
            already.add(url)
        try:
            entry = await asyncio.get_event_loop().run_in_executor(None, self.__extract_info, url)
        except yt_dlp.utils.YoutubeDLError as exc:
            return {'status': 'error', 'msg': str(exc)}
        result = await self.__add_entry(entry, quality, format, folder, custom_name_prefix, auto_start, already)
        
        if result['status'] == 'ok' and auto_start:
            self.event.set()  # Signal that new items are available for download
        
        return result

    async def start_pending(self, ids):
        for id in ids:
            if not self.pending.exists(id):
                log.warn(f'requested start for non-existent download {id}')
                continue
            dl = self.pending.get(id)
            self.queue.put(dl)
            self.pending.delete(id)
            self.event.set()
        return {'status': 'ok'}

    async def cancel(self, ids):
        for id in ids:
            if self.pending.exists(id):
                self.pending.delete(id)
                await self.notifier.canceled(id)
                continue
            if not self.queue.exists(id):
                log.warn(f'requested cancel for non-existent download {id}')
                continue
            dl = self.queue.get(id)
            if isinstance(dl, Download):
                dl.cancel()
            self.queue.delete(id)
            await self.notifier.canceled(id)
        return {'status': 'ok'}

    async def clear(self, ids):
        for id in ids:
            if not self.done.exists(id):
                log.warn(f'requested delete for non-existent download {id}')
                continue
            if self.config.DELETE_FILE_ON_TRASHCAN:
                dl = self.done.get(id)
                try:
                    dldirectory, _ = self.__calc_download_path(dl.info.quality, dl.info.format, dl.info.folder)
                    os.remove(os.path.join(dldirectory, dl.info.filename))
                except Exception as e:
                    log.warn(f'deleting file for download {id} failed with error message {e!r}')
            self.done.delete(id)
            await self.notifier.cleared(id)
        return {'status': 'ok'}

    def get(self):
        return(list((k, v.info) for k, v in self.queue.items()) + list((k, v.info) for k, v in self.pending.items()),
               list((k, v.info) for k, v in self.done.items()))

    async def __manage_downloads(self):
        while True:
            while not self.queue.empty() and len(self.active_downloads) < self.max_concurrent_downloads:
                id, entry = self.queue.next()
                if id not in self.active_downloads:
                    self.active_downloads.add(id)
                    asyncio.create_task(self.__download(id, entry))
            await asyncio.sleep(1)  # Add a small delay to prevent busy waiting

    async def __download(self, id, entry):
        try:
            log.info(f'downloading {entry.info.title}')
            await entry.start(self.notifier)
            if entry.info.status != 'finished':
                if entry.tmpfilename and os.path.isfile(entry.tmpfilename):
                    try:
                        os.remove(entry.tmpfilename)
                    except:
                        pass
            if self.queue.exists(id):
                self.queue.delete(id)
                if entry.canceled:
                    await self.notifier.canceled(id)
                else:
                    self.done.put(entry)
                    await self.notifier.completed(entry.info)
        finally:
            self.active_downloads.remove(id)