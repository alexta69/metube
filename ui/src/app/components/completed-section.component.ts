import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  inject,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import {
  faCheckCircle,
  faChevronDown,
  faChevronRight,
  faCopy,
  faDownload,
  faExternalLinkAlt,
  faRedoAlt,
  faShareNodes,
  faSortAmountDown,
  faSortAmountUp,
  faTimesCircle,
  faTrashAlt,
} from '@fortawesome/free-solid-svg-icons';
import { NgbTooltip } from '@ng-bootstrap/ng-bootstrap';
import { Observable, from, merge, mergeMap, tap } from 'rxjs';
import { actionError } from '../action-result';
import {
  catalogTypes,
  downloadTypeLabel,
  formatCodecLabel,
  formatQualityLabel,
} from '../catalog-labels';
import { Download, Status } from '../interfaces';
import { FileSizePipe } from '../pipes';
import { ADD_REQUEST_CONCURRENCY, DownloadsService } from '../services/downloads.service';
import { SettingsStore } from '../services/settings-store.service';
import { ToastService } from '../services/toast.service';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { ItemCheckboxComponent } from './slave-checkbox.component';

/**
 * The Completed section: finished and failed downloads, with their file
 * links, retry, share, error details and the clear/delete actions (which ask
 * about files on disk when DELETE_FILE_ON_TRASHCAN is 'ask').
 */
@Component({
  selector: 'app-completed-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    FontAwesomeModule,
    NgbTooltip,
    FileSizePipe,
    SelectAllCheckboxComponent,
    ItemCheckboxComponent,
  ],
  templateUrl: './completed-section.component.html',
  styleUrl: './completed-section.component.sass',
})
export class CompletedSectionComponent {
  readonly downloads = inject(DownloadsService);
  private toasts = inject(ToastService);
  private settings = inject(SettingsStore);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  collapsed = this.settings.get('metube_completed_collapsed') === 'true';
  sortAscending = this.settings.get('metube_sort_ascending') === 'true';
  selectedCount = 0;
  // Clear completed / Clear failed / Retry failed act on exactly these rows.
  hasCompletedDone = false;
  hasFailedDone = false;
  expandedErrors = new Set<string>();
  cachedSortedDone: [string, Download][] = [];
  // The done ids in rendered order, so a shift-click range follows the sort
  // the user is looking at rather than the map's insertion order.
  cachedSortedDoneIds: string[] = [];
  lastCopiedErrorId: string | null = null;
  readonly masterCheckbox = viewChild<SelectAllCheckboxComponent>('doneMasterCheckboxRef');

  readonly faCheckCircle = faCheckCircle;
  readonly faChevronDown = faChevronDown;
  readonly faChevronRight = faChevronRight;
  readonly faCopy = faCopy;
  readonly faDownload = faDownload;
  readonly faExternalLinkAlt = faExternalLinkAlt;
  readonly faRedoAlt = faRedoAlt;
  readonly faShareNodes = faShareNodes;
  readonly faSortAmountDown = faSortAmountDown;
  readonly faSortAmountUp = faSortAmountUp;
  readonly faTimesCircle = faTimesCircle;
  readonly faTrashAlt = faTrashAlt;

  constructor() {
    this.refresh();
    this.downloads.doneChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.refresh();
      // Undefined until the view exists; the first render reads the list itself.
      this.masterCheckbox()?.selectionChanged();
      this.cdr.markForCheck();
    });
    // Labels come from the catalog, and links from the configuration.
    merge(this.downloads.formatsChanged, this.downloads.configurationChanged)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.cdr.markForCheck());
  }

  private refresh() {
    this.rebuildSortedDone();
    let completed = false;
    let failed = false;
    this.downloads.done.forEach((download) => {
      completed ||= download.status === 'finished';
      failed ||= download.status === 'error';
    });
    this.hasCompletedDone = completed;
    this.hasFailedDone = failed;
  }

  selectionChanged(checked: number) {
    this.selectedCount = checked;
  }

  formatQualityLabel(download: Download): string {
    return formatQualityLabel(download, catalogTypes(this.downloads.formats));
  }

  downloadTypeLabel(download: Download): string {
    return downloadTypeLabel(download, catalogTypes(this.downloads.formats));
  }

  formatCodecLabel(download: Download): string {
    return formatCodecLabel(download, catalogTypes(this.downloads.formats));
  }

  private report(res: unknown, fallbackMsg: string) {
    const error = actionError(res);
    if (error) {
      this.toasts.error(error || fallbackMsg);
    }
    this.cdr.markForCheck();
  }

  retryDownload(key: string, download: Download) {
    this.retryRequest(key, download).pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
  }

  private retryRequest(key: string, download: Download): Observable<Status> {
    // Only remove the done-list record once the retry is confirmed queued —
    // deleting it eagerly would silently lose history if the re-add fails.
    return this.downloads.retry(key).pipe(
      tap((status: Status) => {
        if (status.status === 'error') {
          this.toasts.error(`Error retrying ${download.title}: ${status.msg}`);
          this.cdr.markForCheck();
          return;
        }
        this.downloads.delById('done', [key]).subscribe();
      }),
    );
  }

  // In ask mode (DELETE_FILE_ON_TRASHCAN='ask'), completed entries may still have
  // a file on disk, so the user is asked whether to keep or delete it before the
  // list entry is removed. Returns undefined when no prompt is needed (send no
  // flag), false/true for the user's choice, or null when the user cancelled.
  private asksBeforeDeletingFiles(ids: string[]): boolean {
    return this.downloads.configuration['DELETE_FILE_ON_TRASHCAN'] === 'ask' &&
      ids.some((id) => {
        const dl = this.downloads.done.get(id);
        return !!dl?.filename || !!dl?.chapter_files?.length;
      });
  }

  private async confirmFileDeletion(ids: string[]): Promise<boolean | null | undefined> {
    if (
      this.downloads.configuration['DELETE_FILE_ON_TRASHCAN'] !== 'ask' ||
      ids.length === 0
    ) {
      return undefined;
    }
    if (!this.asksBeforeDeletingFiles(ids)) {
      return false;
    }
    const message = ids.length === 1
      ? `Remove "${this.downloads.done.get(ids[0])?.title ?? ids[0]}" from the list? You can also delete its file from disk.`
      : `Remove ${ids.length} items from the list? You can also delete their files from disk.`;
    return await this.toasts.choose<boolean | null>(message, [
      { label: 'Cancel', value: null },
      { label: 'Remove from list', value: false },
      { label: 'Delete files', value: true, primary: true },
    ]);
  }

  // ids are collected before the prompt is shown: the user's choice applies to
  // that snapshot, so entries that finish (or otherwise change) while the
  // prompt is open must not get swept into the delete along with it.
  private async removeDownloads(ids: string[], errorMsg: string) {
    const deleteFiles = await this.confirmFileDeletion(ids);
    if (deleteFiles === null) {
      return;
    }
    this.downloads.delById('done', ids, deleteFiles).subscribe((res) => this.report(res, errorMsg));
    this.cdr.markForCheck();
  }

  async delDownload(id: string) {
    await this.removeDownloads([id], 'Delete failed');
  }

  async delSelectedDownloads() {
    const ids: string[] = [];
    this.downloads.done.forEach((dl: Download, key: string) => { if (dl.checked) ids.push(key); });
    await this.removeDownloads(ids, 'Delete failed');
  }

  async clearCompletedDownloads() {
    const ids: string[] = [];
    this.downloads.done.forEach((dl, key) => { if (dl.status === 'finished') ids.push(key); });
    await this.removeDownloads(ids, 'Clear completed failed');
  }

  // A failed row holds the only copy of its URL, and Clear failed sits next to
  // Retry failed, so it asks first (#1094). When ask mode is about to prompt
  // for leftover files anyway, that prompt (which has Cancel) is the question.
  async clearFailedDownloads() {
    const ids: string[] = [];
    this.downloads.done.forEach((dl, key) => { if (dl.status === 'error') ids.push(key); });
    if (ids.length === 0) {
      return;
    }
    if (!this.asksBeforeDeletingFiles(ids)) {
      const count = ids.length === 1 ? 'the failed download' : `${ids.length} failed downloads`;
      const confirmed = await this.toasts.confirm(
        `Clear ${count}? ${ids.length === 1 ? 'Its URL is' : 'Their URLs are'} not kept anywhere else, ` +
        'so retrying later means finding them again.',
        'Clear',
        'Cancel',
      );
      if (!confirmed) {
        return;
      }
    }
    await this.removeDownloads(ids, 'Clear failed downloads failed');
  }

  // Each retry is a full yt-dlp extraction on the server, so a long failed
  // list goes out a few at a time rather than all at once.
  retryFailedDownloads() {
    const failed: [string, Download][] = [];
    this.downloads.done.forEach((dl, key) => {
      if (dl.status === 'error') {
        failed.push([key, dl]);
      }
    });
    from(failed).pipe(
      mergeMap(([key, dl]) => this.retryRequest(key, dl), ADD_REQUEST_CONCURRENCY),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe();
  }

  // Chromium-based browsers silently drop programmatic downloads beyond ~10 when
  // triggered in a tight loop. Trigger in batches with a short pause in between so
  // large selections download cleanly. See issue #1008.
  private static readonly DOWNLOAD_BATCH_SIZE = 10;
  private static readonly DOWNLOAD_BATCH_DELAY_MS = 1000;

  async downloadSelectedFiles() {
    const selected: Download[] = [];
    this.downloads.done.forEach((dl) => {
      if (dl.status === 'finished' && dl.checked) {
        selected.push(dl);
      }
    });

    for (let i = 0; i < selected.length; i++) {
      const dl = selected[i];
      const link = document.createElement('a');
      link.href = this.buildDownloadLink(dl);
      link.setAttribute('download', dl.filename);
      link.setAttribute('target', '_self');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      if (
        (i + 1) % CompletedSectionComponent.DOWNLOAD_BATCH_SIZE === 0 &&
        i + 1 < selected.length
      ) {
        await new Promise((resolve) =>
          setTimeout(resolve, CompletedSectionComponent.DOWNLOAD_BATCH_DELAY_MS),
        );
      }
    }
  }

  buildDownloadLink(download: Download) {
    let baseDir = this.downloads.configuration["PUBLIC_HOST_URL"];
    // Must match the server's directory rule exactly: ytdl.py writes to
    // AUDIO_DOWNLOAD_DIR on download_type alone. Treating any .mp3 as audio
    // sent the link to audio_download/ for mp3s produced under a video-type
    // download (a postprocessor, a preset, or a legacy record), which the
    // server had written to DOWNLOAD_DIR -- a 404 whenever the two differ.
    if (download.download_type === 'audio') {
      baseDir = this.downloads.configuration["PUBLIC_HOST_AUDIO_URL"];
    }

    if (download.folder) {
      baseDir += this.encodeFolderPath(download.folder);
    }

    return baseDir + encodeURIComponent(download.filename);
  }

  // Web Share API support — primarily for iOS Safari / Chrome, lets the user
  // hand the downloaded file off to the platform share sheet (Photos.app,
  // Files, third-party apps, AirDrop). Falls back silently to the standard
  // download flow on platforms without navigator.share / canShare.
  canShareDownloads(): boolean {
    // navigator.share alone is not enough — Desktop Safari implements
    // navigator.share but not canShare with files. We explicitly require
    // both, since we always intend to share a file (not a URL).
    return typeof navigator !== 'undefined'
      && typeof navigator.share === 'function'
      && typeof navigator.canShare === 'function';
  }

  // Conservative warning threshold for the share sheet — iOS' actual
  // refusal limit varies between ~50 MB (older versions) and ~150 MB
  // (recent ones). 80 MB warns the user before the time-wasting fetch+
  // copy of a too-large file that the platform will then reject.
  private static readonly SHARE_SIZE_WARN_BYTES = 80 * 1024 * 1024;

  async shareDownload(download: Download): Promise<void> {
    if (!this.canShareDownloads()) {
      return;
    }
    // Pre-flight size check: warn the user about the iOS share-sheet
    // soft-fail on large files, before we spend time fetching the whole
    // file into memory only to have navigator.canShare reject it.
    if (download.size && download.size > CompletedSectionComponent.SHARE_SIZE_WARN_BYTES) {
      const sizeMb = Math.round(download.size / 1024 / 1024);
      const proceed = await this.toasts.confirm(
        `This file is ${sizeMb} MB. iOS' share sheet often refuses files ` +
        `larger than ~100 MB and the share will silently fail. ` +
        `Try anyway? (Use the download button instead if it fails.)`,
        'Try anyway',
        'Cancel',
      );
      if (!proceed) return;
    }
    try {
      const response = await fetch(this.buildDownloadLink(download));
      if (!response.ok) {
        throw new Error(`HTTP ${response.status} fetching file for share`);
      }
      const blob = await response.blob();
      const file = new File([blob], download.filename, {
        type: blob.type || 'application/octet-stream',
      });
      const payload: ShareData = { files: [file], title: download.title };
      if (!navigator.canShare(payload)) {
        // The platform refused the payload — most commonly because the
        // file is too large for the iOS share sheet, or the MIME type
        // isn't accepted. Tell the user so they can fall back to the
        // download button right next to this one instead of staring at
        // a button that quietly did nothing.
        console.warn('navigator.canShare rejected payload for', download.filename);
        this.toasts.error(
          `Your device's share sheet doesn't accept this file ` +
          `(most likely because it's too large). ` +
          `Please use the download button instead.`
        );
        return;
      }
      await navigator.share(payload);
    } catch (err) {
      const e = err as { name?: string; message?: string };
      // AbortError = user dismissed the share sheet → silent no-op.
      if (e.name === 'AbortError') return;
      console.error('Share failed:', err);
      this.toasts.error(
        `Share failed: ${e.message || 'unknown error'}. ` +
        `Please use the download button instead.`
      );
    }
  }

  buildResultItemTooltip(download: Download) {
    const parts = [];
    if (download.msg) {
      parts.push(download.msg);
    }
    if (download.error) {
      parts.push(download.error);
    }
    return parts.join(' | ');
  }

  buildChapterDownloadLink(download: Download, chapterFilename: string) {
    let baseDir = this.downloads.configuration["PUBLIC_HOST_URL"];
    // Same server-side rule as buildDownloadLink above.
    if (download.download_type === 'audio') {
      baseDir = this.downloads.configuration["PUBLIC_HOST_AUDIO_URL"];
    }

    if (download.folder) {
      baseDir += this.encodeFolderPath(download.folder);
    }

    return baseDir + encodeURIComponent(chapterFilename);
  }

  private encodeFolderPath(folder: string): string {
    return folder
      .split('/')
      .filter(segment => segment.length > 0)
      .map(segment => encodeURIComponent(segment))
      .join('/') + '/';
  }

  getChapterFileName(filepath: string) {
    // Extract just the filename from the path
    const parts = filepath.split('/');
    return parts[parts.length - 1];
  }

  toggleSortOrder() {
    this.sortAscending = !this.sortAscending;
    this.settings.set('metube_sort_ascending', this.sortAscending ? 'true' : 'false');
    this.rebuildSortedDone();
  }

  toggleCollapsed() {
    this.collapsed = !this.collapsed;
    this.settings.set('metube_completed_collapsed', this.collapsed ? 'true' : 'false');
  }

  private rebuildSortedDone() {
    const result: [string, Download][] = [];
    this.downloads.done.forEach((dl, key) => {
      result.push([key, dl]);
    });
    if (!this.sortAscending) {
      result.reverse();
    }
    this.cachedSortedDone = result;
    this.cachedSortedDoneIds = result.map(([key]) => key);
  }

  toggleErrorDetail(id: string) {
    if (this.expandedErrors.has(id)) this.expandedErrors.delete(id);
    else this.expandedErrors.add(id);
  }

  copyErrorMessage(id: string, download: Download) {
    const parts: string[] = [];
    if (download.title) parts.push(`Title: ${download.title}`);
    if (download.url) parts.push(`URL: ${download.url}`);
    if (download.msg) parts.push(`Message: ${download.msg}`);
    if (download.error) parts.push(`Error: ${download.error}`);
    const text = parts.join('\n');
    if (!text.trim()) return;
    const done = () => {
      this.lastCopiedErrorId = id;
      this.cdr.markForCheck();
      setTimeout(() => {
        this.lastCopiedErrorId = null;
        this.cdr.markForCheck();
      }, 1500);
    };
    const fail = (err?: unknown) => {
      console.error('Clipboard write failed:', err);
      this.toasts.error('Failed to copy to clipboard. Your browser may require HTTPS for clipboard access.');
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(fail);
    } else {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        done();
      } catch (e) {
        fail(e);
      }
    }
  }

  isErrorExpanded(id: string): boolean {
    return this.expandedErrors.has(id);
  }
}
