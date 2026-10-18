import { KeyValuePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  OnDestroy,
  inject,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import {
  faChevronDown,
  faChevronRight,
  faClock,
  faDownload,
  faExternalLinkAlt,
  faTrashAlt,
} from '@fortawesome/free-solid-svg-icons';
import { NgbProgressbar } from '@ng-bootstrap/ng-bootstrap';
import { merge } from 'rxjs';
import { actionError } from '../action-result';
import { catalogTypes, formatLabel } from '../catalog-labels';
import { Download } from '../interfaces';
import { EtaPipe, SpeedPipe } from '../pipes';
import { DownloadsService } from '../services/downloads.service';
import { SettingsStore } from '../services/settings-store.service';
import { ToastService } from '../services/toast.service';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { ItemCheckboxComponent } from './slave-checkbox.component';

/** The Downloading section: queued, pending, scheduled and running downloads. */
@Component({
  selector: 'app-downloading-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    KeyValuePipe,
    FontAwesomeModule,
    NgbProgressbar,
    EtaPipe,
    SpeedPipe,
    SelectAllCheckboxComponent,
    ItemCheckboxComponent,
  ],
  templateUrl: './downloading-section.component.html',
  styleUrl: './downloading-section.component.sass',
})
export class DownloadingSectionComponent implements OnDestroy {
  readonly downloads = inject(DownloadsService);
  private toasts = inject(ToastService);
  private settings = inject(SettingsStore);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  collapsed = this.settings.get('metube_downloading_collapsed') === 'true';
  selectedCount = 0;
  readonly masterCheckbox = viewChild<SelectAllCheckboxComponent>('queueMasterCheckboxRef');
  private liveCountdownTimer?: ReturnType<typeof setInterval>;

  readonly faChevronDown = faChevronDown;
  readonly faChevronRight = faChevronRight;
  readonly faClock = faClock;
  readonly faDownload = faDownload;
  readonly faExternalLinkAlt = faExternalLinkAlt;
  readonly faTrashAlt = faTrashAlt;

  constructor() {
    this.downloads.queueChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      // Undefined until the view exists; the first render reads the list itself.
      this.masterCheckbox()?.selectionChanged();
    });
    merge(this.downloads.queueChanged, this.downloads.updated, this.downloads.formatsChanged)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.syncLiveCountdownTimer();
        this.cdr.markForCheck();
      });
    this.syncLiveCountdownTimer();
  }

  ngOnDestroy() {
    if (this.liveCountdownTimer) {
      clearInterval(this.liveCountdownTimer);
    }
  }

  // keyvalue comparator that preserves insertion order (Angular's keyvalue
  // pipe sorts by key by default): https://github.com/angular/angular/issues/31420
  asIsOrder() {
    return 0;
  }

  formatLabel(download: Download): string {
    return formatLabel(download, catalogTypes(this.downloads.formats));
  }

  selectionChanged(checked: number) {
    this.selectedCount = checked;
  }

  toggleCollapsed() {
    this.collapsed = !this.collapsed;
    this.settings.set('metube_downloading_collapsed', this.collapsed ? 'true' : 'false');
  }

  downloadItemByKey(id: string) {
    this.downloads.startById([id]).subscribe((res) => this.report(res, 'Start download failed'));
  }

  startSelectedDownloads() {
    this.downloads
      .startByFilter('queue', (dl) => !!dl.checked)
      .subscribe((res) => this.report(res, 'Start download failed'));
  }

  delDownload(id: string) {
    this.cancel([id]);
  }

  delSelectedDownloads() {
    const ids: string[] = [];
    this.downloads.queue.forEach((dl, key) => {
      if (dl.checked) ids.push(key);
    });
    this.cancel(ids);
  }

  // Removing a queued download cancels it; there is no file to ask about.
  private cancel(ids: string[]) {
    this.downloads.delById('queue', ids).subscribe((res) => this.report(res, 'Delete failed'));
    this.cdr.markForCheck();
  }

  // 'preparing' (yt-dlp starting up) and 'postprocessing' (ffmpeg merging,
  // re-encoding or splitting once the bytes have landed) both have real work in
  // flight with no percentage to report, so the bar runs animated at full width
  // instead of showing a number that cannot move.
  isIndeterminate(download: Download): boolean {
    return download.status === 'preparing' || download.status === 'postprocessing';
  }

  liveCountdownSeconds(download: Download): number | null {
    const ts = download.live_release_timestamp;
    if (ts == null || download.status !== 'scheduled') {
      return null;
    }
    return Math.max(0, ts - Date.now() / 1000);
  }

  private syncLiveCountdownTimer() {
    const hasScheduled = Array.from(this.downloads.queue.values()).some(
      (download) => download.status === 'scheduled',
    );
    if (hasScheduled && !this.liveCountdownTimer) {
      this.liveCountdownTimer = setInterval(() => this.cdr.markForCheck(), 1000);
    } else if (!hasScheduled && this.liveCountdownTimer) {
      clearInterval(this.liveCountdownTimer);
      this.liveCountdownTimer = undefined;
    }
  }

  private report(res: unknown, fallbackMsg: string) {
    const error = actionError(res);
    if (error) {
      this.toasts.error(error || fallbackMsg);
    }
    this.cdr.markForCheck();
  }
}
