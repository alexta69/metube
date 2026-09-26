import { TestBed } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import { Subject, of } from 'rxjs';
import { App } from './app';
import { DownloadsService } from './services/downloads.service';
import { SubscriptionsService } from './services/subscriptions.service';
import { ToastService } from './services/toast.service';
import { CookieService } from 'ngx-cookie-service';
import { Download } from './interfaces';

class DownloadsServiceStub {
  loading = false;
  queue = new Map();
  done = new Map();
  configuration: Record<string, unknown> = { CUSTOM_DIRS: true, CREATE_CUSTOM_DIRS: true, ALLOW_YTDL_OPTIONS_OVERRIDES: false };
  customDirs = { download_dir: [], audio_download_dir: [] };
  queueChanged = new Subject<void>();
  doneChanged = new Subject<void>();
  configurationChanged = new Subject<Record<string, unknown>>();
  customDirsChanged = new Subject<Record<string, string[]>>();
  ytdlOptionsChanged = new Subject<Record<string, unknown>>();
  updated = new Subject<void>();
  retryCalls: string[] = [];

  getCookieStatus() {
    return of({ status: 'ok', has_cookies: false });
  }

  getPresets() {
    return of({ presets: ['Preset A'] });
  }

  add() {
    return of({ status: 'ok' as const });
  }

  retry(id: string) {
    this.retryCalls.push(id);
    return of({ status: 'ok' as const });
  }

  cancelAdd() {
    return of({ status: 'ok' as const });
  }

  startById() {
    return of({});
  }

  delById() {
    return of({});
  }

  delByFilter() {
    return of({});
  }

  startByFilter() {
    return of({});
  }

  uploadCookies() {
    return of({ status: 'ok' });
  }

  deleteCookies() {
    return of({ status: 'ok' });
  }
}

class SubscriptionsServiceStub {
  subscriptions = new Map();
  subscriptionsChanged = new Subject<void>();
  subscribeCalls: unknown[] = [];

  subscribe(payload: unknown) {
    this.subscribeCalls.push(payload);
    return of({ status: 'ok' as const });
  }

  delete() {
    return of({});
  }

  updateCalls: [string, unknown][] = [];

  update(id: string, changes: unknown) {
    this.updateCalls.push([id, changes]);
    return of({ status: 'ok' as const });
  }

  refreshList() {
    return of([]);
  }
}

class CookieServiceStub {
  private cookies = new Map<string, string>();

  get(name: string) {
    return this.cookies.get(name) ?? '';
  }

  set(name: string, value: string) {
    this.cookies.set(name, value);
  }

  check(name: string) {
    return this.cookies.has(name);
  }
}

describe('App', () => {
  let downloads: DownloadsServiceStub;

  beforeEach(async () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      enumerable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    downloads = new DownloadsServiceStub();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        { provide: DownloadsService, useValue: downloads },
        { provide: SubscriptionsService, useClass: SubscriptionsServiceStub },
        { provide: CookieService, useClass: CookieServiceStub },
        {
          provide: HttpClient,
          useValue: {
            get: vi.fn().mockReturnValue(of({ 'yt-dlp': 'test', version: 'test' })),
          },
        },
      ],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('pre-fills the download folder from DEFAULT_FOLDER', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    downloads.configurationChanged.next({ DEFAULT_FOLDER: 'youtube' });

    expect(fixture.componentInstance.folder).toBe('youtube');
  });

  it('does not overwrite a folder the user already typed', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    fixture.componentInstance.folder = 'music';

    downloads.configurationChanged.next({ DEFAULT_FOLDER: 'youtube' });

    expect(fixture.componentInstance.folder).toBe('music');
  });

  it('collapses each section independently and remembers it (#1070)', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const app = fixture.componentInstance;
    const cookies = TestBed.inject(CookieService);

    expect(app.downloadingCollapsed).toBe(false);
    expect(app.completedCollapsed).toBe(false);
    expect(app.subscriptionsCollapsed).toBe(false);

    app.toggleCompletedCollapsed();

    expect(app.completedCollapsed).toBe(true);
    expect(app.downloadingCollapsed).toBe(false);
    expect(app.subscriptionsCollapsed).toBe(false);
    expect(cookies.get('metube_completed_collapsed')).toBe('true');

    // A fresh component picks the state back up from the cookie.
    const restored = TestBed.createComponent(App);
    restored.detectChanges();
    expect(restored.componentInstance.completedCollapsed).toBe(true);
    expect(restored.componentInstance.downloadingCollapsed).toBe(false);
    expect(restored.componentInstance.subscriptionsCollapsed).toBe(false);
  });

  it('asIsOrder returns a stable comparator value (insertion order preserved)', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app.asIsOrder()).toBe(0);
  });

  it('hides manual override input when disabled', () => {
    const fixture = TestBed.createComponent(App);
    fixture.componentInstance.isAdvancedOpen = true;
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('input[name="ytdlOptionsOverrides"]')).toBeNull();

    const presetWrapper = root.querySelector('ng-select[name="ytdlOptionsPresets"]')?.closest('.col-12');
    expect(presetWrapper?.classList.contains('col-md-6')).toBe(false);

    const presetRow = root.querySelector('ng-select[name="ytdlOptionsPresets"]')?.closest('.row');
    expect(presetRow?.querySelector('input[name="checkIntervalMinutes"]')).toBeNull();
  });

  it('shows manual override input when enabled', () => {
    downloads.configuration['ALLOW_YTDL_OPTIONS_OVERRIDES'] = true;

    const fixture = TestBed.createComponent(App);
    fixture.componentInstance.isAdvancedOpen = true;
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('input[name="ytdlOptionsOverrides"]')).not.toBeNull();

    const presetWrapper = root.querySelector('ng-select[name="ytdlOptionsPresets"]')?.closest('.col-12');
    expect(presetWrapper?.classList.contains('col-md-6')).toBe(true);

    const presetRow = root.querySelector('ng-select[name="ytdlOptionsPresets"]')?.closest('.row');
    expect(presetRow?.querySelector('input[name="checkIntervalMinutes"]')).toBeNull();
    expect(presetRow?.querySelector('input[name="ytdlOptionsOverrides"]')).not.toBeNull();
  });

  it('does not submit manual overrides when disabled', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;

    app.ytdlOptionsOverrides = '{"exec":"echo hi"}';

    const payload = app['buildAddPayload']();

    expect(payload.ytdlOptionsOverrides).toBe('');
  });

  it('shows waiting badge for scheduled live stream', () => {
    downloads.queue.set('https://example.com/live', {
      id: 'live1',
      title: 'Upcoming Stream',
      url: 'https://example.com/live',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'scheduled',
      live_status: 'is_upcoming',
      live_release_timestamp: Date.now() / 1000 + 3600,
      msg: '',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    });
    downloads.queueChanged.next();

    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('Waiting for stream');
    expect(root.textContent).toContain('starts in');
  });

  it('shows the queued format in the Downloading table', () => {
    downloads.queue.set('https://example.com/v', {
      id: 'v1',
      title: 'Some Video',
      url: 'https://example.com/v',
      download_type: 'audio',
      quality: 'best',
      format: 'flac',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'downloading',
      msg: '',
      percent: 10,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    });
    downloads.queueChanged.next();

    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    const row = (fixture.nativeElement as HTMLElement).querySelector('tbody tr');
    expect(row?.textContent).toContain('FLAC');
  });

  it('labels formats the way the form does, and copes with an unknown one', () => {
    const app = TestBed.createComponent(App).componentInstance;
    const base = { format: '' } as Download;

    expect(app.formatLabel({ ...base, format: 'any' })).toBe('Auto');
    expect(app.formatLabel({ ...base, format: 'mp4' })).toBe('MP4');
    expect(app.formatLabel({ ...base, format: 'srt' })).toBe('SRT');
    // A format from a record older than the option list still reads sensibly.
    expect(app.formatLabel({ ...base, format: 'mkv' })).toBe('MKV');
    expect(app.formatLabel(base)).toBe('-');
  });

  describe('audio Auto format and Tags dropdown', () => {
    it('lists Auto first but still defaults a switch to Audio to M4A', () => {
      const app = TestBed.createComponent(App).componentInstance;
      expect(app.audioFormats[0].id).toBe('auto');

      app.downloadType = 'audio';
      app.downloadTypeChanged();

      expect(app.format).toBe('m4a');
    });

    it('sends the remembered Tags choice with the download', () => {
      const cookies = TestBed.inject(CookieService);
      cookies.set('metube_audio_tags', 'none');
      const app = TestBed.createComponent(App).componentInstance;

      expect(app['buildAddPayload']().audioTags).toBe('none');
    });

    it('falls back to With cover for an unknown remembered choice', () => {
      TestBed.inject(CookieService).set('metube_audio_tags', 'everything');
      const app = TestBed.createComponent(App).componentInstance;

      expect(app.audioTags).toBe('with_cover');
    });

    it('shows None, disabled, for WAV without forgetting the choice', async () => {
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      app.downloadType = 'audio';
      app.downloadTypeChanged();
      app.audioTagsChanged('no_cover');
      app.format = 'wav';
      app.formatChanged();
      fixture.detectChanges();
      // ngModel writes the value and disabled state in a microtask.
      await Promise.resolve();
      fixture.detectChanges();

      const select = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
        'select[name=audioTags]',
      );
      expect(select?.disabled).toBe(true);
      expect(select?.selectedOptions[0]?.textContent?.trim()).toBe('None');

      app.format = 'mp3';
      app.formatChanged();
      expect(app.displayedAudioTags()).toBe('no_cover');
    });
  });

  it('includes titleRegex in subscribe payload', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const subs = TestBed.inject(SubscriptionsService) as unknown as SubscriptionsServiceStub;
    app.addUrl = 'https://example.com/channel';
    app.titleRegex = 'EPISODE';
    app.addSubscription();
    expect(subs.subscribeCalls.length).toBe(1);
    const payload = subs.subscribeCalls[0] as { titleRegex: string; skipSubscriberOnly: boolean };
    expect(payload.titleRegex).toBe('EPISODE');
    expect(payload.skipSubscriberOnly).toBe(false);
  });

  it('includes skipSubscriberOnly true when checked', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const subs = TestBed.inject(SubscriptionsService) as unknown as SubscriptionsServiceStub;
    app.addUrl = 'https://example.com/channel';
    app.skipSubscriberOnly = true;
    app.addSubscription();
    expect(subs.subscribeCalls.length).toBe(1);
    const payload = subs.subscribeCalls[0] as { skipSubscriberOnly: boolean };
    expect(payload.skipSubscriberOnly).toBe(true);
  });

  it('passes clip fields through to the subscribe payload', () => {
    // #1049: a subscription's options apply to all its future downloads, and
    // clip bounds used to be stripped out on the way.
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const subs = TestBed.inject(SubscriptionsService) as unknown as SubscriptionsServiceStub;
    app.addUrl = 'https://example.com/channel';
    app.clipStart = '1:00';
    app.clipEnd = '2:00';
    app.addSubscription();
    expect(subs.subscribeCalls.length).toBe(1);
    const payload = subs.subscribeCalls[0] as Record<string, unknown>;
    expect(payload['clipStart']).toBe('1:00');
    expect(payload['clipEnd']).toBe('2:00');
  });

  it('buildAddPayload includes clip times', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    app.clipStart = '0:10';
    app.clipEnd = '1:20';
    const payload = app['buildAddPayload']();
    expect(payload.clipStart).toBe('0:10');
    expect(payload.clipEnd).toBe('1:20');
  });

  it('retries a failed download by its server-side queue id', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const download = {
      id: 'vid1',
      title: 'Test Video',
      url: 'https://example.com/v',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'error',
      msg: 'temporary failure',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    };

    app.retryDownload(download.url, download);

    expect(downloads.retryCalls).toEqual([download.url]);
  });

  it('blocks subscribe with invalid title regex', () => {
    const toasts = TestBed.inject(ToastService);
    const errorSpy = vi.spyOn(toasts, 'error').mockImplementation(() => undefined);
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const subs = TestBed.inject(SubscriptionsService) as unknown as SubscriptionsServiceStub;
    app.addUrl = 'https://example.com/channel';
    app.titleRegex = '[';
    app.addSubscription();
    expect(subs.subscribeCalls.length).toBe(0);
    expect(errorSpy).toHaveBeenCalledWith('Invalid subscription title filter (regex)');
    errorSpy.mockRestore();
  });

  it('renames a subscription and closes the inline editor', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const subs = TestBed.inject(SubscriptionsService) as unknown as SubscriptionsServiceStub;

    app.beginEditName('sub1', 'Videos');
    expect(app.editingNameId).toBe('sub1');
    expect(app.nameEditDraft).toBe('Videos');

    app.nameEditDraft = '  Jane uploads  ';
    app.saveName('sub1');

    expect(subs.updateCalls).toEqual([['sub1', { name: 'Jane uploads' }]]);
    expect(app.editingNameId).toBeNull();
  });

  it('blocks renaming a subscription to an empty name', () => {
    const toasts = TestBed.inject(ToastService);
    const errorSpy = vi.spyOn(toasts, 'error').mockImplementation(() => undefined);
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const subs = TestBed.inject(SubscriptionsService) as unknown as SubscriptionsServiceStub;

    app.beginEditName('sub1', 'Videos');
    app.nameEditDraft = '   ';
    app.saveName('sub1');

    expect(subs.updateCalls.length).toBe(0);
    expect(app.editingNameId).toBe('sub1');
    expect(errorSpy).toHaveBeenCalledWith('Subscription name must not be empty');
    errorSpy.mockRestore();
  });
  // Issue #533: the server picks AUDIO_DOWNLOAD_DIR on download_type alone
  // (ytdl.py), so the UI's choice of URL base has to use the same rule. It used
  // to also treat any .mp3 as audio, which pointed the link at audio_download/
  // for files the server had written to DOWNLOAD_DIR.
  describe('download links follow the server directory rule (#533)', () => {
    const makeDownload = (over: Partial<Download>): Download => ({
      id: 'vid1',
      title: 'Test',
      url: 'https://example.com/v',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'finished',
      msg: '',
      percent: 100,
      speed: 0,
      eta: 0,
      filename: 'song.mp4',
      checked: false,
      ...over,
    } as Download);

    const appWithDirs = () => {
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const downloads = TestBed.inject(DownloadsService) as unknown as DownloadsServiceStub;
      downloads.configuration['PUBLIC_HOST_URL'] = 'download/';
      downloads.configuration['PUBLIC_HOST_AUDIO_URL'] = 'audio_download/';
      return app;
    };

    it('uses the audio base for an audio download', () => {
      const app = appWithDirs();
      const link = app.buildDownloadLink(makeDownload({ download_type: 'audio', filename: 'song.mp3' }));
      expect(link).toBe('audio_download/song.mp3');
    });

    it('uses the video base for an mp3 produced by a video download', () => {
      const app = appWithDirs();
      const link = app.buildDownloadLink(makeDownload({ download_type: 'video', filename: 'song.mp3' }));
      expect(link).toBe('download/song.mp3');
    });

    it('uses the video base for a video download', () => {
      const app = appWithDirs();
      const link = app.buildDownloadLink(makeDownload({ filename: 'clip.mp4' }));
      expect(link).toBe('download/clip.mp4');
    });

    it('applies the same rule to chapter links', () => {
      const app = appWithDirs();
      const dl = makeDownload({ download_type: 'video' });
      expect(app.buildChapterDownloadLink(dl, 'ch1.mp3')).toBe('download/ch1.mp3');
      const audio = makeDownload({ download_type: 'audio' });
      expect(app.buildChapterDownloadLink(audio, 'ch1.mp3')).toBe('audio_download/ch1.mp3');
    });
  });

  // Issue #424: ffmpeg work after the bytes land (merge, re-encode, split) used
  // to leave the row on a full, frozen bar with the item counted as neither
  // active nor queued.
  describe('post-processing is visible (#424)', () => {
    const queueEntry = (status: string): Download => ({
      id: 'vid1',
      title: 'Test',
      url: 'https://example.com/v',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status,
      msg: '',
      percent: 100,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    } as Download);

    it('runs the bar indeterminate while preparing or post-processing', () => {
      const app = TestBed.createComponent(App).componentInstance;
      expect(app.isIndeterminate(queueEntry('preparing'))).toBe(true);
      expect(app.isIndeterminate(queueEntry('postprocessing'))).toBe(true);
      expect(app.isIndeterminate(queueEntry('downloading'))).toBe(false);
      expect(app.isIndeterminate(queueEntry('pending'))).toBe(false);
    });

    it('labels the bar and counts the item as active', () => {
      // The component subscribes to queueChanged on construction, so the entry
      // has to be announced after it exists or updateMetrics never runs.
      const fixture = TestBed.createComponent(App);
      downloads.queue.set('https://example.com/v', queueEntry('postprocessing'));
      downloads.queueChanged.next();
      fixture.detectChanges();

      expect((fixture.nativeElement as HTMLElement).textContent).toContain('Post-processing');
      expect(fixture.componentInstance.activeDownloads).toBe(1);
      expect(fixture.componentInstance.queuedDownloads).toBe(0);
    });
  });

  // Issue #1081: a download waiting for a concurrency slot ('queued') starts on
  // its own, so it must not offer the Start button that a 'pending' row — one
  // added with auto-start off — legitimately has.
  describe('queued rows do not offer a dead Start button (#1081)', () => {
    const queueEntry = (status: string): Download => ({
      id: 'vid1',
      title: 'Test',
      url: 'https://example.com/v',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status,
      msg: '',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    } as Download);

    const render = (status: string) => {
      const fixture = TestBed.createComponent(App);
      downloads.queue.set('https://example.com/v', queueEntry(status));
      downloads.queueChanged.next();
      fixture.detectChanges();
      return fixture;
    };

    it('hides Start for a queued row but keeps it for a pending one', () => {
      const queued = render('queued');
      expect(
        (queued.nativeElement as HTMLElement).querySelector('[aria-label="Start download for Test"]')
      ).toBeNull();

      downloads.queue.clear();

      const pending = render('pending');
      expect(
        (pending.nativeElement as HTMLElement).querySelector('[aria-label="Start download for Test"]')
      ).not.toBeNull();
    });

    it('says why the row is idle and counts it as queued', () => {
      const fixture = render('queued');
      expect((fixture.nativeElement as HTMLElement).textContent).toContain('Queued');
      expect(fixture.componentInstance.queuedDownloads).toBe(1);
      expect(fixture.componentInstance.activeDownloads).toBe(0);
    });
  });

});
