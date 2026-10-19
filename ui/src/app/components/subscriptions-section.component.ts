import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import {
  faChevronDown,
  faChevronRight,
  faPause,
  faPlay,
  faRedoAlt,
  faTrashAlt,
} from '@fortawesome/free-solid-svg-icons';
import { NgbPopover, NgbTooltip } from '@ng-bootstrap/ng-bootstrap';
import { finalize } from 'rxjs';
import { actionError } from '../action-result';
import { SubscriptionRow } from '../interfaces/subscription';
import { DownloadsService } from '../services/downloads.service';
import { SettingsStore } from '../services/settings-store.service';
import { SubscriptionsService } from '../services/subscriptions.service';
import { ToastService } from '../services/toast.service';

/**
 * The Subscriptions section: the table of subscriptions with their inline
 * name and title-filter editors, check/pause/delete actions and selection.
 * Adding a subscription stays with the download form, which owns the options
 * a new subscription is created with.
 */
@Component({
  selector: 'app-subscriptions-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, FontAwesomeModule, NgbPopover, NgbTooltip],
  templateUrl: './subscriptions-section.component.html',
  styleUrl: './subscriptions-section.component.sass',
})
export class SubscriptionsSectionComponent {
  readonly downloads = inject(DownloadsService);
  private subscriptionsSvc = inject(SubscriptionsService);
  private toasts = inject(ToastService);
  private settings = inject(SettingsStore);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  readonly subscriptionNameMaxLength = 200;
  collapsed = this.settings.get('metube_subscriptions_collapsed') === 'true';
  cachedSubs: [string, SubscriptionRow][] = [];
  selectedSubscriptionIds = new Set<string>();
  checkingSubscriptionIds = new Set<string>();
  checkingAllSubscriptions = false;
  checkingSelectedSubscriptions = false;
  editingTitleRegexId: string | null = null;
  titleRegexEditDraft = '';
  editingNameId: string | null = null;
  nameEditDraft = '';

  readonly faChevronDown = faChevronDown;
  readonly faChevronRight = faChevronRight;
  readonly faPause = faPause;
  readonly faPlay = faPlay;
  readonly faRedoAlt = faRedoAlt;
  readonly faTrashAlt = faTrashAlt;

  constructor() {
    this.rebuildCachedSubs();
    this.subscriptionsSvc.subscriptionsChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.rebuildCachedSubs();
      this.cdr.markForCheck();
    });
    // The Check/Delete buttons follow the connection state.
    this.downloads.queueChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.cdr.markForCheck();
    });
  }

  private rebuildCachedSubs() {
    this.cachedSubs = Array.from(this.subscriptionsSvc.subscriptions.entries());
    const validIds = new Set(this.cachedSubs.map(([id]) => id));
    for (const id of [...this.selectedSubscriptionIds]) {
      if (!validIds.has(id)) {
        this.selectedSubscriptionIds.delete(id);
      }
    }
  }

  private refreshSubscriptionsWithAlert() {
    this.subscriptionsSvc.refreshList().pipe(takeUntilDestroyed(this.destroyRef)).subscribe((refreshRes) => {
      const error = actionError(refreshRes);
      if (error) {
        this.toasts.error(error || 'Refresh subscriptions failed');
        return;
      }
      this.cdr.markForCheck();
    });
  }

  isSubSelected(id: string): boolean {
    return this.selectedSubscriptionIds.has(id);
  }

  toggleSubSelected(id: string) {
    if (this.selectedSubscriptionIds.has(id)) {
      this.selectedSubscriptionIds.delete(id);
    } else {
      this.selectedSubscriptionIds.add(id);
    }
    this.cdr.markForCheck();
  }

  toggleSubMaster(event: Event) {
    const checked = (event.target as HTMLInputElement).checked;
    this.selectedSubscriptionIds.clear();
    if (checked) {
      for (const [id] of this.cachedSubs) {
        this.selectedSubscriptionIds.add(id);
      }
    }
    this.cdr.markForCheck();
  }

  allSubsSelected(): boolean {
    if (this.cachedSubs.length === 0) {
      return false;
    }
    return this.cachedSubs.every(([id]) => this.selectedSubscriptionIds.has(id));
  }

  beginEditTitleRegex(id: string, current: string | undefined) {
    this.editingTitleRegexId = id;
    this.titleRegexEditDraft = current ?? '';
    this.cdr.markForCheck();
  }

  cancelEditTitleRegex() {
    this.editingTitleRegexId = null;
    this.titleRegexEditDraft = '';
    this.cdr.markForCheck();
  }

  saveTitleRegex(id: string) {
    const raw = (this.titleRegexEditDraft || '').trim();
    if (raw) {
      try {
        void RegExp(raw);
      } catch {
        this.toasts.error('Invalid subscription title filter (regex)');
        return;
      }
    }
    this.subscriptionsSvc.update(id, { title_regex: raw }).subscribe((res) => {
      const error = actionError(res);
      if (error) {
        this.toasts.error(error || 'Update subscription failed');
        return;
      }
      this.cancelEditTitleRegex();
    });
  }

  beginEditName(id: string, current: string | undefined) {
    this.editingNameId = id;
    this.nameEditDraft = current ?? '';
    this.cdr.markForCheck();
  }

  cancelEditName() {
    this.editingNameId = null;
    this.nameEditDraft = '';
    this.cdr.markForCheck();
  }

  saveName(id: string) {
    const name = (this.nameEditDraft || '').trim();
    if (!name) {
      this.toasts.error('Subscription name must not be empty');
      return;
    }
    this.subscriptionsSvc.update(id, { name }).subscribe((res) => {
      const error = actionError(res);
      if (error) {
        this.toasts.error(error || 'Update subscription failed');
        return;
      }
      this.cancelEditName();
    });
  }

  deleteSubscription(id: string) {
    this.subscriptionsSvc.delete([id]).subscribe((res) => {
      const error = actionError(res);
      if (error) {
        this.toasts.error(error || 'Delete subscription failed');
        return;
      }
      this.selectedSubscriptionIds.delete(id);
      this.cdr.markForCheck();
    });
  }

  deleteSelectedSubscriptions() {
    const ids = Array.from(this.selectedSubscriptionIds);
    if (!ids.length) {
      return;
    }
    this.subscriptionsSvc.delete(ids).subscribe((res) => {
      const error = actionError(res);
      if (error) {
        this.toasts.error(error || 'Delete subscriptions failed');
        return;
      }
      this.selectedSubscriptionIds.clear();
      this.cdr.markForCheck();
    });
  }

  checkSubscriptionNow(id: string) {
    if (this.checkingSubscriptionIds.has(id)) {
      return;
    }
    this.checkingSubscriptionIds.add(id);
    this.cdr.markForCheck();
    this.subscriptionsSvc
      .checkNow([id])
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => {
          this.checkingSubscriptionIds.delete(id);
          this.cdr.markForCheck();
        }),
      )
      .subscribe((res) => {
        const error = actionError(res);
        if (error) {
          this.toasts.error(error || 'Subscription check failed');
          return;
        }
        this.refreshSubscriptionsWithAlert();
      });
  }

  isSubscriptionChecking(id: string): boolean {
    return this.checkingSubscriptionIds.has(id);
  }

  private runBulkSubscriptionCheck(ids: string[] | undefined, mode: 'all' | 'selected') {
    const targetIds = ids ?? this.cachedSubs.filter(([, row]) => row.enabled).map(([id]) => id);
    if (!targetIds.length) {
      return;
    }

    const checkedIds = new Set(targetIds);
    for (const id of checkedIds) {
      this.checkingSubscriptionIds.add(id);
    }
    if (mode === 'all') {
      this.checkingAllSubscriptions = true;
    } else {
      this.checkingSelectedSubscriptions = true;
    }
    this.cdr.markForCheck();

    this.subscriptionsSvc
      .checkNow(ids)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => {
          for (const id of checkedIds) {
            this.checkingSubscriptionIds.delete(id);
          }
          if (mode === 'all') {
            this.checkingAllSubscriptions = false;
          } else {
            this.checkingSelectedSubscriptions = false;
          }
          this.cdr.markForCheck();
        }),
      )
      .subscribe((res) => {
        const error = actionError(res);
        if (error) {
          this.toasts.error(error || 'Subscription check failed');
          return;
        }
        this.refreshSubscriptionsWithAlert();
      });
  }

  checkSelectedSubscriptions() {
    const ids = Array.from(this.selectedSubscriptionIds);
    if (!ids.length) {
      return;
    }
    this.runBulkSubscriptionCheck(ids, 'selected');
  }

  checkAllSubscriptions() {
    this.runBulkSubscriptionCheck(undefined, 'all');
  }

  toggleSubscriptionEnabled(row: SubscriptionRow) {
    this.subscriptionsSvc.update(row.id, { enabled: !row.enabled }).subscribe((res) => {
      const error = actionError(res);
      if (error) {
        this.toasts.error(error || 'Update subscription failed');
      }
    });
  }

  toggleCollapsed() {
    this.collapsed = !this.collapsed;
    this.settings.set('metube_subscriptions_collapsed', this.collapsed ? 'true' : 'false');
  }
}
