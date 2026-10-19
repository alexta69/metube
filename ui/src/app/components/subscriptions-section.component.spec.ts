import { TestBed } from '@angular/core/testing';
import { Subject, of } from 'rxjs';
import { CookieService } from 'ngx-cookie-service';
import { SubscriptionsSectionComponent } from './subscriptions-section.component';
import { DownloadsService } from '../services/downloads.service';
import { SubscriptionsService } from '../services/subscriptions.service';
import { SettingsStore } from '../services/settings-store.service';
import { ToastService } from '../services/toast.service';
import { SubscriptionRow } from '../interfaces/subscription';

class SubscriptionsServiceStub {
  subscriptions = new Map<string, SubscriptionRow>();
  subscriptionsChanged = new Subject<void>();
  updateCalls: [string, unknown][] = [];
  deleteCalls: string[][] = [];
  checkCalls: (string[] | undefined)[] = [];

  update(id: string, changes: unknown) {
    this.updateCalls.push([id, changes]);
    return of({ status: 'ok' as const });
  }

  delete(ids: string[]) {
    this.deleteCalls.push(ids);
    return of({ status: 'ok' as const });
  }

  checkNow(ids?: string[]) {
    this.checkCalls.push(ids);
    return of({ status: 'ok' as const });
  }

  refreshList() {
    return of([]);
  }
}

const row = (id: string, overrides: Partial<SubscriptionRow> = {}): SubscriptionRow => ({
  id,
  name: `Sub ${id}`,
  url: `https://example.com/${id}`,
  enabled: true,
  check_interval_minutes: 60,
  download_type: 'video',
  codec: 'auto',
  format: 'any',
  quality: 'best',
  folder: '',
  last_checked: null,
  seen_count: 0,
  error: null,
  ...overrides,
});

describe('SubscriptionsSectionComponent', () => {
  let subs: SubscriptionsServiceStub;

  beforeEach(async () => {
    localStorage.clear();
    subs = new SubscriptionsServiceStub();
    await TestBed.configureTestingModule({
      imports: [SubscriptionsSectionComponent],
      providers: [
        { provide: SubscriptionsService, useValue: subs },
        { provide: DownloadsService, useValue: { loading: false, queueChanged: new Subject<void>() } },
        {
          provide: CookieService,
          useValue: { get: () => '', set: () => undefined, check: () => false, delete: () => undefined },
        },
      ],
    }).compileComponents();
  });

  function create() {
    const fixture = TestBed.createComponent(SubscriptionsSectionComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('renders the subscriptions the service holds and follows its changes', () => {
    subs.subscriptions.set('a', row('a'));
    const fixture = create();
    expect(fixture.nativeElement.textContent).toContain('Sub a');

    subs.subscriptions.set('b', row('b', { enabled: false }));
    subs.subscriptionsChanged.next();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Sub b');
    expect(fixture.nativeElement.textContent).toContain('Paused');
  });

  it('renames a subscription and closes the inline editor', () => {
    const section = create().componentInstance;

    section.beginEditName('sub1', 'Videos');
    expect(section.editingNameId).toBe('sub1');
    expect(section.nameEditDraft).toBe('Videos');

    section.nameEditDraft = '  Jane uploads  ';
    section.saveName('sub1');

    expect(subs.updateCalls).toEqual([['sub1', { name: 'Jane uploads' }]]);
    expect(section.editingNameId).toBeNull();
  });

  it('blocks renaming a subscription to an empty name', () => {
    const errorSpy = vi.spyOn(TestBed.inject(ToastService), 'error').mockImplementation(() => undefined);
    const section = create().componentInstance;

    section.beginEditName('sub1', 'Videos');
    section.nameEditDraft = '   ';
    section.saveName('sub1');

    expect(subs.updateCalls.length).toBe(0);
    expect(section.editingNameId).toBe('sub1');
    expect(errorSpy).toHaveBeenCalledWith('Subscription name must not be empty');
  });

  it('drops selections of subscriptions that are gone', () => {
    subs.subscriptions.set('a', row('a'));
    subs.subscriptions.set('b', row('b'));
    const section = create().componentInstance;
    section.toggleSubSelected('a');
    section.toggleSubSelected('b');

    subs.subscriptions.delete('a');
    subs.subscriptionsChanged.next();

    expect([...section.selectedSubscriptionIds]).toEqual(['b']);
  });

  it('checks all enabled subscriptions when asked to check all', () => {
    subs.subscriptions.set('a', row('a'));
    subs.subscriptions.set('b', row('b', { enabled: false }));
    const section = create().componentInstance;

    section.checkAllSubscriptions();

    expect(subs.checkCalls).toEqual([undefined]);
    expect(section.checkingAllSubscriptions).toBe(false);
    expect(section.checkingSubscriptionIds.size).toBe(0);
  });

  it('remembers whether the section is collapsed', () => {
    const section = create().componentInstance;
    expect(section.collapsed).toBe(false);

    section.toggleCollapsed();

    expect(TestBed.inject(SettingsStore).get('metube_subscriptions_collapsed')).toBe('true');
    expect(create().componentInstance.collapsed).toBe(true);
  });
});
