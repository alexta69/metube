import { ChangeDetectionStrategy, ChangeDetectorRef, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { Subject, finalize, from, mergeMap, takeUntil, tap } from 'rxjs';
import { Status } from '../interfaces';
import {
  ADD_REQUEST_CONCURRENCY,
  AddDownloadPayload,
  DownloadsService,
} from '../services/downloads.service';

/**
 * Modal that queues a pasted list of URLs, one /add per line, with the form's
 * current settings. The opener sets `buildPayload` on the component instance.
 *
 * Closing the modal does not stop an import that is running: as before, it
 * carries on in the background, and Cancel Import is what stops it.
 */
@Component({
  selector: 'app-batch-import',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule],
  template: `
    <div class="modal-header">
      <h5 class="modal-title">Batch Import URLs</h5>
      <button type="button" class="btn-close" aria-label="Close" (click)="activeModal.close()"></button>
    </div>
    <div class="modal-body">
      <textarea
        id="batch-import-textarea"
        class="form-control"
        rows="6"
        style="resize: vertical"
        placeholder="Paste one video URL per line"
        [(ngModel)]="text"
        ngbAutofocus
      ></textarea>
      <div class="mt-2">
        @if (status) {
          <small>{{ status }}</small>
        }
        @if (total > 0) {
          <div class="progress mt-2" style="height: 20px;">
            <div
              class="progress-bar"
              role="progressbar"
              [class.bg-danger]="failures > 0"
              [style.width.%]="(count / total) * 100"
              [attr.aria-valuenow]="count"
              [attr.aria-valuemin]="0"
              [attr.aria-valuemax]="total"
            >
              {{ count }} / {{ total }}
            </div>
          </div>
        }
      </div>
    </div>
    <div class="modal-footer">
      @if (inProgress) {
        <button type="button" class="btn btn-danger me-auto" (click)="cancel()">Cancel Import</button>
      }
      <button type="button" class="btn btn-secondary" (click)="activeModal.close()">Close</button>
      <button type="button" class="btn btn-primary" [disabled]="inProgress" (click)="start()">
        Import URLs
      </button>
    </div>
  `,
})
export class BatchImportComponent {
  readonly activeModal = inject(NgbActiveModal);
  private downloads = inject(DownloadsService);
  private cdr = inject(ChangeDetectorRef);

  // Set by the opener through NgbModalRef.componentInstance.
  buildPayload!: (url: string) => AddDownloadPayload;

  text = '';
  status = '';
  count = 0;
  total = 0;
  failures = 0;
  inProgress = false;
  private cancel$ = new Subject<void>();

  start(): void {
    const urls = this.text
      .split(/\r?\n/)
      .map((url) => url.trim())
      .filter((url) => url.length > 0);
    if (urls.length === 0) {
      this.status = 'No valid URLs found.';
      return;
    }
    this.inProgress = true;
    this.count = 0;
    this.failures = 0;
    this.total = urls.length;
    this.updateStatus();

    from(urls)
      .pipe(
        mergeMap(
          (url) =>
            this.downloads.add(this.buildPayload(url)).pipe(
              // downloads.add() already catches HTTP errors and emits a single
              // Status value, so `tap` (not `finalize`) is the right place to
              // count: an in-flight request aborted by cancellation is not one.
              tap((status: Status) => {
                if (status.status === 'error') {
                  this.failures++;
                  console.error(`Error adding URL ${url}: ${status.msg}`);
                }
                this.count++;
                this.updateStatus();
                this.cdr.markForCheck();
              }),
            ),
          ADD_REQUEST_CONCURRENCY,
        ),
        takeUntil(this.cancel$),
        finalize(() => {
          this.inProgress = false;
          this.updateStatus(true);
          this.cdr.markForCheck();
        }),
      )
      .subscribe();
  }

  // Aborts in-flight and pending requests immediately.
  cancel(): void {
    if (this.inProgress) {
      this.cancel$.next();
    }
  }

  private updateStatus(done = false): void {
    const parts: string[] = [];
    if (done) {
      if (this.count < this.total) {
        parts.push(`Import cancelled after ${this.count} of ${this.total} URLs.`);
      } else {
        parts.push(`Finished importing ${this.total} URLs.`);
      }
    } else {
      parts.push(`Importing ${this.count} of ${this.total} URLs...`);
    }
    if (this.failures > 0) {
      parts.push(`${this.failures} failed.`);
    }
    this.status = parts.join(' ');
  }
}
