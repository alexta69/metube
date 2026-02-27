import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { of, Subject } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MeTubeSocket } from './metube-socket.service';
import { Download, Status, State } from '../interfaces';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
@Injectable({
  providedIn: 'root'
})
export class DownloadsService {
  private http = inject(HttpClient);
  private socket = inject(MeTubeSocket);
  loading = true;
  queue = new Map<string, Download>();
  done = new Map<string, Download>();
  queueChanged = new Subject();
  doneChanged = new Subject();
  customDirsChanged = new Subject();
  ytdlOptionsChanged = new Subject();
  configurationChanged = new Subject();
  updated = new Subject();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  configuration: any = {};
  customDirs = {};

  constructor() {
    this.socket.fromEvent('all')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      this.loading = false;
      const data: [[[string, Download]], [[string, Download]]] = JSON.parse(strdata);
      this.queue.clear();
      data[0].forEach(entry => this.queue.set(...entry));
      this.done.clear();
      data[1].forEach(entry => this.done.set(...entry));
      this.queueChanged.next(null);
      this.doneChanged.next(null);
    });
    this.socket.fromEvent('added')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      this.queue.set(data.url, data);
      this.queueChanged.next(null);
    });
    this.socket.fromEvent('updated')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      const dl: Download | undefined  = this.queue.get(data.url);
      data.checked = !!dl?.checked;
      data.deleting = !!dl?.deleting;
      this.queue.set(data.url, data);
      this.updated.next(null);
    });
    this.socket.fromEvent('completed')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      this.queue.delete(data.url);
      this.done.set(data.url, data);
      this.queueChanged.next(null);
      this.doneChanged.next(null);
    });
    this.socket.fromEvent('canceled')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: string = JSON.parse(strdata);
      this.queue.delete(data);
      this.queueChanged.next(null);
    });
    this.socket.fromEvent('cleared')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: string = JSON.parse(strdata);
      this.done.delete(data);
      this.doneChanged.next(null);
    });
    this.socket.fromEvent('configuration')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data = JSON.parse(strdata);
      console.debug("got configuration:", data);
      this.configuration = data;
      this.configurationChanged.next(data);
    });
    this.socket.fromEvent('custom_dirs')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data = JSON.parse(strdata);
      console.debug("got custom_dirs:", data);
      this.customDirs = data;
      this.customDirsChanged.next(data);
    });
    this.socket.fromEvent('ytdl_options_changed')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data = JSON.parse(strdata);
      this.ytdlOptionsChanged.next(data);
    });
  }

  handleHTTPError(error: HttpErrorResponse) {
    const msg = error.error instanceof ErrorEvent ? error.error.message : error.error;
    return of({status: 'error', msg: msg})
  }

  public add(
    url: string,
    quality: string,
    format: string,
    folder: string,
    customNamePrefix: string,
    playlistItemLimit: number,
    autoStart: boolean,
    splitByChapters: boolean,
    chapterTemplate: string,
    subtitleFormat: string,
    subtitleLanguage: string,
    subtitleMode: string,
  ) {
    return this.http.post<Status>('add', {
      url: url,
      quality: quality,
      format: format,
      folder: folder,
      custom_name_prefix: customNamePrefix,
      playlist_item_limit: playlistItemLimit,
      auto_start: autoStart,
      split_by_chapters: splitByChapters,
      chapter_template: chapterTemplate,
      subtitle_format: subtitleFormat,
      subtitle_language: subtitleLanguage,
      subtitle_mode: subtitleMode
    }).pipe(
      catchError(this.handleHTTPError)
    );
  }

  public startById(ids: string[]) {
    return this.http.post('start', {ids: ids});
  }

  public delById(where: State, ids: string[]) {
    const map = this[where];
    if (map) {
      for (const id of ids) {
        const obj = map.get(id);
        if (obj) {
          obj.deleting = true;
        }
      }
    }
    return this.http.post('delete', {where: where, ids: ids});
  }

  public startByFilter(where: State, filter: (dl: Download) => boolean) {
    const ids: string[] = [];
    this[where].forEach((dl: Download) => { if (filter(dl)) ids.push(dl.url) });
    return this.startById(ids);
  }

  public delByFilter(where: State, filter: (dl: Download) => boolean) {
    const ids: string[] = [];
    this[where].forEach((dl: Download) => { if (filter(dl)) ids.push(dl.url) });
    return this.delById(where, ids);
  }
  public addDownloadByUrl(url: string): Promise<{
    response: Status} | {
    status: string;
    msg?: string;
  }> {
    const defaultQuality = 'best';
    const defaultFormat = 'mp4';
    const defaultFolder = ''; 
    const defaultCustomNamePrefix = '';
    const defaultPlaylistItemLimit = 0;
    const defaultAutoStart = true;
    const defaultSplitByChapters = false;
    const defaultChapterTemplate = this.configuration['OUTPUT_TEMPLATE_CHAPTER'];
    const defaultSubtitleFormat = 'srt';
    const defaultSubtitleLanguage = 'en';
    const defaultSubtitleMode = 'prefer_manual';

    return new Promise((resolve, reject) => {
      this.add(
        url,
        defaultQuality,
        defaultFormat,
        defaultFolder,
        defaultCustomNamePrefix,
        defaultPlaylistItemLimit,
        defaultAutoStart,
        defaultSplitByChapters,
        defaultChapterTemplate,
        defaultSubtitleFormat,
        defaultSubtitleLanguage,
        defaultSubtitleMode,
      )
        .subscribe({
          next: (response) => resolve(response),
          error: (error) => reject(error)
        });
    });
  }
  public exportQueueUrls(): string[] {
    return Array.from(this.queue.values()).map(download => download.url);
  }
  
  
}
