import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { of, Subject, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MeTubeSocket } from './metube-socket.service';
import { Download, Status, State } from '../interfaces';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

export interface AddDownloadPayload {
  url: string;
  downloadType: string;
  codec: string;
  quality: string;
  format: string;
  folder: string;
  customNamePrefix: string;
  playlistItemLimit: number;
  autoStart: boolean;
  splitByChapters: boolean;
  chapterTemplate: string;
  subtitleLanguage: string;
  subtitleMode: string;
  ytdlOptionsPresets: string[];
  ytdlOptionsOverrides: string;
  clipStart?: string;
  clipEnd?: string;
}
@Injectable({
  providedIn: 'root'
})
export class DownloadsService {
  private http = inject(HttpClient);
  private socket = inject(MeTubeSocket);
  loading = true;
  queue = new Map<string, Download>();
  done = new Map<string, Download>();
  queueChanged = new Subject<void>();
  doneChanged = new Subject<void>();
  customDirsChanged = new Subject<Record<string, string[]>>();
  ytdlOptionsChanged = new Subject<Record<string, unknown>>();
  configurationChanged = new Subject<Record<string, unknown>>();
  updated = new Subject<void>();
  completedDownload = new Subject<Download>();

  configuration: Record<string, unknown> = {};
  customDirs: Record<string, string[]> = {};

  private getDownloadKey(download: Download): string {
    const maybeKey = (download as Download & { key?: string }).key;
    return maybeKey && maybeKey.length > 0 ? maybeKey : download.url;
  }

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
      this.queueChanged.next();
      this.doneChanged.next();
    });
    this.socket.fromEvent('added')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      const key = this.getDownloadKey(data);
      this.queue.set(key, data);
      this.queueChanged.next();
    });
    this.socket.fromEvent('updated')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      const key = this.getDownloadKey(data);
      const dl: Download | undefined  = this.queue.get(key);
      data.checked = !!dl?.checked;
      data.deleting = !!dl?.deleting;
      this.queue.set(key, data);
      this.updated.next();
    });
    this.socket.fromEvent('completed')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      const key = this.getDownloadKey(data);
      this.queue.delete(key);
      this.done.set(key, data);
      this.queueChanged.next();
      this.doneChanged.next();
      this.completedDownload.next(data);
    });
    this.socket.fromEvent('canceled')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: string = JSON.parse(strdata);
      this.queue.delete(data);
      this.queueChanged.next();
    });
    this.socket.fromEvent('cleared')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: string = JSON.parse(strdata);
      this.done.delete(data);
      this.doneChanged.next();
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
    const msg = error.error instanceof ErrorEvent
      ? error.error.message
      : (typeof error.error === 'string'
          ? error.error
          : (error.error?.msg || error.message || 'Request failed'));
    return of<Status>({ status: 'error', msg });
  }

  public add(payload: AddDownloadPayload) {
    const body: Record<string, unknown> = {
      url: payload.url,
      download_type: payload.downloadType,
      codec: payload.codec,
      quality: payload.quality,
      format: payload.format,
      folder: payload.folder,
      custom_name_prefix: payload.customNamePrefix,
      playlist_item_limit: payload.playlistItemLimit,
      auto_start: payload.autoStart,
      split_by_chapters: payload.splitByChapters,
      chapter_template: payload.chapterTemplate,
      subtitle_language: payload.subtitleLanguage,
      subtitle_mode: payload.subtitleMode,
      ytdl_options_presets: payload.ytdlOptionsPresets,
      ytdl_options_overrides: payload.ytdlOptionsOverrides,
    };
    const cs = payload.clipStart?.trim();
    const ce = payload.clipEnd?.trim();
    if (cs) body['clip_start'] = cs;
    if (ce) body['clip_end'] = ce;
    const visitId = typeof this.socket.getVisitId === 'function' ? this.socket.getVisitId() : '';
    const headers = visitId ? new HttpHeaders({ 'X-Visit-Id': visitId }) : undefined;
    return this.http.post<Status>('add', body, { headers }).pipe(
      catchError((error: HttpErrorResponse) => this.handleHTTPError(error))
    );
  }

  public getPresets() {
    return this.http.get<{ presets: string[] }>('presets').pipe(
      catchError(() => of({ presets: [] }))
    );
  }

  public startById(ids: string[]) {
    return this.http.post('start', {ids: ids});
  }

  public pauseById(ids: string[]) {
    return this.http.post('pause', {ids: ids});
  }

  public delById(where: State, ids: string[]) {
    const map = this[where];
    const touched: [string, Download, boolean | undefined][] = [];
    if (map) {
      for (const id of ids) {
        const obj = map.get(id);
        if (obj) {
          touched.push([id, obj, obj.deleting]);
          obj.deleting = true;
          if (where === 'done') {
            map.delete(id);
          }
        }
      }
      if (where === 'queue') {
        this.queueChanged.next();
      } else if (where === 'done') {
        this.doneChanged.next();
      }
    }
    return this.http.post('delete', {where: where, ids: ids}).pipe(
      catchError((error: HttpErrorResponse) => {
        if (map) {
          for (const [id, obj, deleting] of touched) {
            obj.deleting = deleting;
            if (where === 'done' && !map.has(id)) {
              map.set(id, obj);
            }
          }
          if (where === 'queue') {
            this.queueChanged.next();
          } else if (where === 'done') {
            this.doneChanged.next();
          }
        }
        return throwError(() => error);
      })
    );
  }

  public startByFilter(where: State, filter: (dl: Download) => boolean) {
    const ids: string[] = [];
    this[where].forEach((dl: Download) => { if (filter(dl)) ids.push(dl.url) });
    return this.startById(ids);
  }

  public delByFilter(where: State, filter: (dl: Download) => boolean) {
    const ids: string[] = [];
    this[where].forEach((dl: Download, key: string) => { if (filter(dl)) ids.push(key) });
    return this.delById(where, ids);
  }
  public cancelAdd() {
    return this.http.post<Status>('cancel-add', {}).pipe(
      catchError(this.handleHTTPError)
    );
  }

  uploadCookies(file: File) {
    const formData = new FormData();
    formData.append('cookies', file);
    return this.http.post<{ status: string; msg?: string }>('upload-cookies', formData).pipe(
      catchError(this.handleHTTPError)
    );
  }

  deleteCookies() {
    return this.http.post<{ status: string; msg?: string }>('delete-cookies', {}).pipe(
      catchError(this.handleHTTPError)
    );
  }

  getCookieStatus() {
    return this.http.get<{ status: string; has_cookies: boolean }>('cookie-status').pipe(
      catchError(this.handleHTTPError)
    );
  }
}
