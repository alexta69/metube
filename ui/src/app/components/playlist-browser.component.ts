import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { BrowseEntry, BrowsePayload, DownloadsService } from '../services/downloads.service';
import { Checkable } from '../interfaces';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { ItemCheckboxComponent } from './slave-checkbox.component';

type BrowseRow = BrowseEntry & Checkable;

/**
 * Modal that lists the entries of a playlist or channel (a flat probe, no
 * downloading) and closes with the URLs the user ticked. The opener sets
 * `payload` on the component instance before the first change detection.
 */
@Component({
  selector: 'app-playlist-browser',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SelectAllCheckboxComponent, ItemCheckboxComponent],
  template: `
    <div class="modal-header">
      <h5 class="modal-title text-break">
        @if (loaded) {
          {{ playlistTitle || 'Browse' }}
          <small class="text-body-secondary fs-6 ms-1">
            ({{ rows.size }} {{ rows.size === 1 ? 'entry' : 'entries' }})
          </small>
        } @else {
          Browse
        }
      </h5>
      <button
        type="button"
        class="btn-close"
        aria-label="Close"
        (click)="activeModal.dismiss()"
      ></button>
    </div>
    <div class="modal-body">
      @if (loading) {
        <div class="d-flex align-items-center gap-2">
          <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
          <span>Loading entries…</span>
        </div>
      } @else if (errorMsg) {
        <div class="alert alert-danger mb-0" role="alert">{{ errorMsg }}</div>
      } @else if (rows.size === 0) {
        <p class="text-body-secondary mb-0">No entries found.</p>
      } @else {
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th scope="col" style="width: 1rem;">
                <app-select-all-checkbox
                  #browseMaster
                  [id]="'browse'"
                  [list]="rows"
                  (changed)="selectionChanged($event)"
                />
              </th>
              <th scope="col">Title</th>
              <th scope="col" class="text-end" style="width: 6rem;">Duration</th>
            </tr>
          </thead>
          <tbody>
            @for (row of rowList; track row[0]) {
              <tr>
                <td>
                  <app-item-checkbox [id]="row[0]" [master]="browseMaster" [checkable]="row[1]" />
                </td>
                <td class="text-break">
                  <a
                    [href]="row[1].url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-reset"
                    >{{ row[1].title || row[1].url }}</a
                  >
                  @if (isDownloaded(row[1])) {
                    <span class="badge bg-success ms-2">Downloaded</span>
                  }
                </td>
                <td class="text-end text-nowrap">{{ formatDuration(row[1].duration) }}</td>
              </tr>
            }
          </tbody>
        </table>
      }
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-outline-secondary" (click)="activeModal.dismiss()">
        Cancel
      </button>
      <button
        type="button"
        class="btn btn-primary"
        [disabled]="!loaded || selectedCount === 0"
        (click)="addSelected()"
      >
        Add selected ({{ selectedCount }})
      </button>
    </div>
  `,
})
export class PlaylistBrowserComponent implements OnInit {
  readonly activeModal = inject(NgbActiveModal);
  private downloads = inject(DownloadsService);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  // Set by the opener through NgbModalRef.componentInstance (which cannot
  // assign signal inputs).
  payload!: BrowsePayload;

  loading = true;
  loaded = false;
  errorMsg = '';
  playlistTitle = '';
  selectedCount = 0;
  // Keyed by list position, so entries that repeat a URL stay visible and the
  // checkbox DOM ids stay clean.
  rows = new Map<string, BrowseRow>();
  rowList: [string, BrowseRow][] = [];

  ngOnInit(): void {
    this.downloads
      .browse(this.payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((result) => {
        this.loading = false;
        if (result.status === 'error') {
          this.errorMsg = result.msg || 'Failed to load entries';
        } else {
          this.playlistTitle = result.title ?? '';
          this.rows = new Map(
            (result.entries ?? []).map((entry, index) => [
              String(index),
              { ...entry, checked: false },
            ]),
          );
          this.rowList = Array.from(this.rows);
          this.loaded = true;
        }
        this.cdr.markForCheck();
      });
  }

  selectionChanged(count: number): void {
    this.selectedCount = count;
    this.cdr.markForCheck();
  }

  isDownloaded(entry: BrowseEntry): boolean {
    return this.downloads.done.get(entry.url)?.status === 'finished';
  }

  formatDuration(seconds: number | null): string {
    if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
      return '';
    }
    const total = Math.round(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = String(total % 60).padStart(2, '0');
    return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
  }

  addSelected(): void {
    const urls = new Set<string>();
    this.rows.forEach((row) => {
      if (row.checked) {
        urls.add(row.url);
      }
    });
    this.activeModal.close(Array.from(urls));
  }
}
