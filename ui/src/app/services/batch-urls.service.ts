import { inject, Injectable } from '@angular/core';
import { DownloadsService } from './downloads.service';
import { ToastService } from './toast.service';

export type BatchUrlFilter = 'pending' | 'completed' | 'failed' | 'all';

/**
 * Encapsulates collecting download URLs by status and exporting/copying them.
 * Extracted from the main app component to keep it focused on view concerns.
 */
@Injectable({ providedIn: 'root' })
export class BatchUrlsService {
  private downloads = inject(DownloadsService);
  private toasts = inject(ToastService);

  collect(filter: BatchUrlFilter): string[] {
    const queueUrls = () => Array.from(this.downloads.queue.values()).map((dl) => dl.url);
    const doneUrls = (status?: string) =>
      Array.from(this.downloads.done.values())
        .filter((dl) => status === undefined || dl.status === status)
        .map((dl) => dl.url);
    switch (filter) {
      case 'pending':
        return queueUrls();
      case 'completed':
        return doneUrls('finished');
      case 'failed':
        return doneUrls('error');
      default:
        return [...queueUrls(), ...doneUrls()];
    }
  }

  export(filter: BatchUrlFilter): void {
    const urls = this.collect(filter);
    if (!urls.length) {
      this.toasts.info('No URLs found for the selected filter.');
      return;
    }
    const blob = new Blob([urls.join('\n')], { type: 'text/plain' });
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = 'metube_urls.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(downloadUrl);
  }

  copy(filter: BatchUrlFilter): void {
    const urls = this.collect(filter);
    if (!urls.length) {
      this.toasts.info('No URLs found for the selected filter.');
      return;
    }
    navigator.clipboard
      .writeText(urls.join('\n'))
      .then(() => this.toasts.success('URLs copied to clipboard.'))
      .catch(() => this.toasts.error('Failed to copy URLs.'));
  }
}
