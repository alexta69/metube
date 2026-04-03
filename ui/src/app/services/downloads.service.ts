import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { of, Subject } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MeTubeSocket } from './metube-socket.service';
import { Download, Status, State } from '../interfaces';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

export interface WebhookSettings {
  enabled: boolean;
  endpoint: string;
  timeout_sec: number;
}

export interface WebhookTestResponse {
  status: string;
  message?: string;
  response?: unknown;
  status_code?: number;
}

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
  ytdlOptionsPreset: string;
  ytdlOptionsOverrides: string;
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
  private updateRefreshScheduled = false;
  private foregroundRefreshMs = 3000;
  private backgroundRefreshMs = 30000;

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
      data.checked = !!dl?.checked;
      data.deleting = !!dl?.deleting;
      this.queue.set(data.url, data);
      this.scheduleUpdatedRefresh();
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

  private scheduleUpdatedRefresh() {
    // Coalesce high-frequency download progress events into a capped refresh rate.
    // requestAnimationFrame (~60fps) is smooth but expensive remotely and on large queues.
    // We trade a little smoothness for much lower CPU:
    // - foreground: 1 per 3 seconds
    // - background: 1 per 30 seconds
    if (this.updateRefreshScheduled) {
      return;
    }
    this.updateRefreshScheduled = true;

    const flush = () => {
      this.updateRefreshScheduled = false;
      this.updated.next();
    };

    const delay = document.hidden
      ? this.backgroundRefreshMs
      : this.foregroundRefreshMs;
    setTimeout(() => flush(), delay);
  }

  setRefreshCadence(focusedMs: number, backgroundMs: number) {
    this.foregroundRefreshMs = focusedMs;
    this.backgroundRefreshMs = backgroundMs;
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
    return this.http.post<Status>('add', {
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
      ytdl_options_preset: payload.ytdlOptionsPreset,
      ytdl_options_overrides: payload.ytdlOptionsOverrides,
    }).pipe(
      catchError(this.handleHTTPError)
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

  getWebhookSettings() {
    return this.http.get<WebhookSettings>('webhook-settings').pipe(
      catchError(this.handleHTTPError)
    );
  }

  saveWebhookSettings(settings: WebhookSettings) {
    return this.http.post<{ status: string; msg?: string }>('webhook-settings', settings).pipe(
      catchError(this.handleHTTPError)
    );
  }

  testWebhookSettings(settings: Pick<WebhookSettings, 'endpoint' | 'timeout_sec'>) {
    return this.http.post<WebhookTestResponse>('webhook-settings/test', settings).pipe(
      catchError(this.handleHTTPError)
    );
  }
}
