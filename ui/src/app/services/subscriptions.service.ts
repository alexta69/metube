import { DestroyRef, inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { of, Subject } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MeTubeSocket } from './metube-socket.service';
import { SubscriptionRow } from '../interfaces/subscription';
import { Status } from '../interfaces';
import { AddDownloadPayload } from './downloads.service';

export interface SubscribePayload extends AddDownloadPayload {
  checkIntervalMinutes: number;
}

@Injectable({
  providedIn: 'root',
})
export class SubscriptionsService {
  private http = inject(HttpClient);
  private socket = inject(MeTubeSocket);
  private destroyRef = inject(DestroyRef);

  subscriptions = new Map<string, SubscriptionRow>();
  subscriptionsChanged = new Subject<void>();

  private publishList(rows: SubscriptionRow[]) {
    this.subscriptions.clear();
    for (const row of rows) {
      this.subscriptions.set(row.id, row);
    }
    this.subscriptionsChanged.next();
  }

  constructor() {
    this.socket
      .fromEvent('subscriptions_all')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((strdata: string) => {
        const data: SubscriptionRow[] = JSON.parse(strdata);
        this.publishList(data);
      });

    this.socket
      .fromEvent('subscription_added')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((strdata: string) => {
        const row: SubscriptionRow = JSON.parse(strdata);
        this.subscriptions.set(row.id, row);
        this.subscriptionsChanged.next();
      });

    this.socket
      .fromEvent('subscription_updated')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((strdata: string) => {
        const row: SubscriptionRow = JSON.parse(strdata);
        this.subscriptions.set(row.id, row);
        this.subscriptionsChanged.next();
      });

    this.socket
      .fromEvent('subscription_removed')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((strdata: string) => {
        const id: string = JSON.parse(strdata);
        this.subscriptions.delete(id);
        this.subscriptionsChanged.next();
      });
  }

  handleHTTPError(error: HttpErrorResponse) {
    const msg =
      error.error instanceof ErrorEvent
        ? error.error.message
        : typeof error.error === 'string'
          ? error.error
          : error.error?.msg || error.message || 'Request failed';
    return of({ status: 'error' as const, msg });
  }

  subscribe(payload: SubscribePayload) {
    return this.http
      .post<Status>('subscribe', {
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
        check_interval_minutes: payload.checkIntervalMinutes,
      })
      .pipe(catchError((err) => this.handleHTTPError(err)));
  }

  delete(ids: string[]) {
    return this.http.post('subscriptions/delete', { ids }).pipe(catchError((err) => this.handleHTTPError(err)));
  }

  update(id: string, changes: Partial<Pick<SubscriptionRow, 'enabled' | 'check_interval_minutes' | 'name'>>) {
    return this.http
      .post('subscriptions/update', { id, ...changes })
      .pipe(catchError((err) => this.handleHTTPError(err)));
  }

  checkNow(ids?: string[]) {
    return this.http
      .post('subscriptions/check', ids?.length ? { ids } : {})
      .pipe(catchError((err) => this.handleHTTPError(err)));
  }

  fetchList() {
    return this.http.get<SubscriptionRow[]>('subscriptions').pipe(catchError(() => of([])));
  }

  refreshList() {
    return this.http.get<SubscriptionRow[]>('subscriptions').pipe(
      tap((rows) => this.publishList(rows)),
      catchError((err) => this.handleHTTPError(err)),
    );
  }
}
