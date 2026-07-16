import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { of, Subject } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MeTubeSocket } from './metube-socket.service';
import { Download, Status, State, MusicCandidate, MusicSource, MusicTagPayload } from '../interfaces';
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

  configuration: Record<string, unknown> = {};
  customDirs: Record<string, string[]> = {};

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
      this.queue.set(data.url, data);
      this.queueChanged.next();
    });
    this.socket.fromEvent('updated')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      const dl: Download | undefined  = this.queue.get(data.url);
      // An 'added' event always precedes legitimate updates. If the row is
      // gone (canceled/completed already processed), this update is stale —
      // applying it would resurrect a ghost row until the next full refresh.
      if (!dl) {
        return;
      }
      data.checked = !!dl.checked;
      data.deleting = !!dl.deleting;
      this.queue.set(data.url, data);
      this.updated.next();
    });
    this.socket.fromEvent('completed')
    .pipe(takeUntilDestroyed())
    .subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      this.queue.delete(data.url);
      this.done.set(data.url, data);
      this.queueChanged.next();
      this.doneChanged.next();
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
    return of({ status: 'error', msg });
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
    return this.http.post<Status>('add', body).pipe(
      catchError(this.handleHTTPError)
    );
  }

  public musicMetaSearch(q: string) {
    return this.http.get<{ status: string; candidates: MusicCandidate[] }>('music-meta', { params: { q } }).pipe(
      catchError((err: HttpErrorResponse) => of({ status: 'error', candidates: [] as MusicCandidate[], msg: err.error?.msg || err.message }))
    );
  }

  public musicMetaSource(id: string) {
    return this.http.get<MusicSource>('music-meta/source', { params: { id } }).pipe(
      catchError((err: HttpErrorResponse) => of({ status: 'error', msg: err.error?.msg || err.message } as MusicSource))
    );
  }

  public musicTag(payload: MusicTagPayload) {
    return this.http.post<Status>('music-tag', payload).pipe(
      catchError(this.handleHTTPError)
    );
  }

  public getPresets() {
    return this.http.get<{ presets: string[] }>('presets').pipe(
      catchError(() => of({ presets: [] }))
    );
  }

  public startById(ids: string[]) {
    return this.http.post<Status>('start', {ids: ids}).pipe(
      catchError(this.handleHTTPError)
    );
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
    return this.http.post<Status>('delete', {where: where, ids: ids}).pipe(
      catchError((err: HttpErrorResponse) => {
        // Request failed — the rows would otherwise stay disabled forever
        // with no way to retry, since nothing ever clears `deleting`.
        if (map) {
          for (const id of ids) {
            const obj = map.get(id);
            if (obj) {
              obj.deleting = false;
            }
          }
        }
        (where === 'queue' ? this.queueChanged : this.doneChanged).next();
        return this.handleHTTPError(err);
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
    this[where].forEach((dl: Download) => { if (filter(dl)) ids.push(dl.url) });
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
