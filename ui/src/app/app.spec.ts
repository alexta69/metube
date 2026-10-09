import { TestBed } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import { Subject, of } from 'rxjs';
import { App } from './app';
import { NgbModal, NgbModalRef } from '@ng-bootstrap/ng-bootstrap';
import { AddDownloadPayload, DownloadsService } from './services/downloads.service';
import { SubscriptionsService } from './services/subscriptions.service';
import { ToastService } from './services/toast.service';
import { CookieService } from 'ngx-cookie-service';
import { Download, FormatCatalog } from './interfaces';

const choice = (def: string, ...pairs: [string, string][]) => ({
  default: def,
  options: pairs.map(([id, text]) => ({ id, text })),
});

// Shaped like the catalog app/format_catalog.py sends; the tests rely on its
// shape and a few of its entries, not on it matching the real one.
function testCatalog(): FormatCatalog {
  const videoQuality = choice('best', ['best', 'Best'], ['1080', '1080p'], ['720', '720p'], ['worst', 'Worst']);
  const bestOnly = choice('best', ['best', 'Best']);
  return {
    download_type: {
      default: 'video',
      options: [
        {
          id: 'video',
          text: 'Video',
          codec: choice('auto', ['auto', 'Auto'], ['h264', 'H.264'], ['h265', 'H.265 (HEVC)']),
          format: {
            default: 'any',
            options: [
              { id: 'any', text: 'Auto', quality: videoQuality },
              { id: 'mp4', text: 'MP4', quality: videoQuality },
              { id: 'ios', text: 'iOS Compatible', quality: videoQuality },
            ],
          },
        },
        {
          id: 'audio',
          text: 'Audio',
          format: {
            default: 'm4a',
            options: [
              { id: 'auto', text: 'Auto', quality: bestOnly, tags: true },
              { id: 'm4a', text: 'M4A', quality: choice('best', ['best', 'Best'], ['192', '192 kbps']), tags: true },
              { id: 'mp3', text: 'MP3', quality: choice('best', ['best', 'Best'], ['320', '320 kbps']), tags: true },
              { id: 'wav', text: 'WAV', quality: bestOnly, tags: false },
              { id: 'flac', text: 'FLAC', quality: bestOnly, tags: true },
            ],
          },
          audio_tags: choice('with_cover', ['with_cover', 'With cover'], ['no_cover', 'No cover'], ['none', 'None']),
        },
        {
          id: 'captions',
          text: 'Captions',
          format: choice('srt', ['srt', 'SRT'], ['vtt', 'VTT'], ['dfxp', 'DFXP']),
          subtitle_mode: choice('prefer_manual', ['prefer_manual', 'Prefer Manual'], ['auto_only', 'Auto Only']),
          subtitle_language: choice('en', ['en', 'English'], ['de', 'German']),
        },
        {
          id: 'thumbnail',
          text: 'Thumbnail',
          format: choice('jpg', ['jpg', 'JPG']),
        },
      ],
    },
  };
}

class DownloadsServiceStub {
  loading = false;
  queue = new Map();
  done = new Map();
  configuration: Record<string, unknown> = { CUSTOM_DIRS: true, CREATE_CUSTOM_DIRS: true, ALLOW_YTDL_OPTIONS_OVERRIDES: false };
  customDirs = { download_dir: [], audio_download_dir: [] };
  queueChanged = new Subject<void>();
  doneChanged = new Subject<void>();
  configurationChanged = new Subject<Record<string, unknown>>();
  formats: FormatCatalog | null = testCatalog();
  formatsChanged = new Subject<FormatCatalog>();
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

  add(payload?: unknown) {
    void payload;
    return of({ status: 'ok' as const });
  }

  browse() {
    return of({ status: 'ok' as const, title: '', entries: [] });
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

    const presetWrapper = root.querySelector('ng-select[name="ytdlOptionsPresets"]')?.parentElement
      ?.parentElement;
    expect(presetWrapper?.classList.contains('col-md-6')).toBe(true);

    const presetRow = root.querySelector('ng-select[name="ytdlOptionsPresets"]')?.closest('.row');
    expect(presetRow?.querySelector('input[name="checkIntervalMinutes"]')).toBeNull();
    expect(presetRow?.querySelector('input[name="videoPassword"]')).not.toBeNull();
  });

  it('shows manual override input when enabled', () => {
    downloads.configuration['ALLOW_YTDL_OPTIONS_OVERRIDES'] = true;

    const fixture = TestBed.createComponent(App);
    fixture.componentInstance.isAdvancedOpen = true;
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('input[name="ytdlOptionsOverrides"]')).not.toBeNull();

    const presetWrapper = root.querySelector('ng-select[name="ytdlOptionsPresets"]')?.parentElement
      ?.parentElement;
    expect(presetWrapper?.classList.contains('col-md-6')).toBe(true);

    // The JSON overrides get a full-width row of their own below presets + password.
    const overridesWrapper = root.querySelector('input[name="ytdlOptionsOverrides"]')?.parentElement
      ?.parentElement;
    expect(overridesWrapper?.classList.contains('col-12')).toBe(true);
    expect(overridesWrapper?.classList.contains('col-md-6')).toBe(false);

    const presetRow = root.querySelector('ng-select[name="ytdlOptionsPresets"]')?.closest('.row');
    expect(presetRow?.querySelector('input[name="checkIntervalMinutes"]')).toBeNull();
    expect(presetRow?.querySelector('input[name="videoPassword"]')).not.toBeNull();
    expect(presetRow?.querySelector('input[name="ytdlOptionsOverrides"]')).not.toBeNull();
  });

  it('does not submit manual overrides when disabled', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;

    app.ytdlOptionsOverrides = '{"exec":"echo hi"}';

    const payload = app['buildAddPayload']();

    expect(payload.ytdlOptionsOverrides).toBe('');
  });

  describe('browse a playlist and queue picked entries (#1030)', () => {
    const setup = (result: Promise<string[]>) => {
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      // App's imports bring their own NgbModal instance, so spy on the one it uses.
      const modal = app['modal'] as NgbModal;
      const componentInstance: { payload?: unknown } = {};
      const openSpy = vi
        .spyOn(modal, 'open')
        .mockReturnValue({ componentInstance, result } as unknown as NgbModalRef);
      const toasts = TestBed.inject(ToastService);
      const infoSpy = vi.spyOn(toasts, 'info');
      const errorSpy = vi.spyOn(toasts, 'error');
      const addSpy = vi.spyOn(downloads, 'add');
      app.addUrl = ' https://example.com/playlist ';
      return { app, openSpy, componentInstance, infoSpy, errorSpy, addSpy };
    };

    it('does nothing when the URL box is empty', () => {
      const { app, openSpy } = setup(Promise.resolve([]));
      app.addUrl = '   ';
      app.browsePlaylist();
      expect(openSpy).not.toHaveBeenCalled();
    });

    it('opens the browser with the payload built from the form', () => {
      downloads.configuration['ALLOW_YTDL_OPTIONS_OVERRIDES'] = true;
      const { app, openSpy, componentInstance } = setup(new Promise(() => undefined));
      app.playlistItemLimit = 7;
      app.ytdlOptionsPresets = ['Preset A'];
      app.ytdlOptionsOverrides = '{"a":1}';
      app.browsePlaylist();
      expect(openSpy).toHaveBeenCalledTimes(1);
      expect(componentInstance.payload).toEqual({
        url: 'https://example.com/playlist',
        playlistItemLimit: 7,
        ytdlOptionsPresets: ['Preset A'],
        ytdlOptionsOverrides: '{"a":1}',
      });
    });

    it('does not send manual overrides when they are not allowed', () => {
      const { app, componentInstance } = setup(new Promise(() => undefined));
      app.ytdlOptionsOverrides = '{"exec":"echo hi"}';
      app.browsePlaylist();
      const sent = componentInstance.payload as { ytdlOptionsOverrides: string };
      expect(sent.ytdlOptionsOverrides).toBe('');
    });

    it('refuses to open with invalid manual overrides', () => {
      downloads.configuration['ALLOW_YTDL_OPTIONS_OVERRIDES'] = true;
      const { app, openSpy, errorSpy } = setup(Promise.resolve([]));
      app.ytdlOptionsOverrides = '{nope';
      app.browsePlaylist();
      expect(openSpy).not.toHaveBeenCalled();
      expect(errorSpy).toHaveBeenCalledWith('Custom yt-dlp options must be valid JSON');
    });

    it('refuses to open when chapter splitting lacks a section number', () => {
      const { app, openSpy, errorSpy } = setup(Promise.resolve([]));
      app.splitByChapters = true;
      app.chapterTemplate = '%(title)s.%(ext)s';
      app.browsePlaylist();
      expect(openSpy).not.toHaveBeenCalled();
      expect(errorSpy).toHaveBeenCalledWith('Chapter template must include %(section_number)');
    });

    it('queues each picked url with the form settings and reports once', async () => {
      const { app, addSpy, infoSpy, errorSpy } = setup(
        Promise.resolve(['https://example.com/a', 'https://example.com/b']),
      );
      app.quality = '720';
      app.browsePlaylist();
      await vi.waitFor(() => expect(infoSpy).toHaveBeenCalled());
      expect(addSpy).toHaveBeenCalledTimes(2);
      expect(addSpy.mock.calls.map(([p]) => (p as AddDownloadPayload).url)).toEqual([
        'https://example.com/a',
        'https://example.com/b',
      ]);
      expect((addSpy.mock.calls[0][0] as AddDownloadPayload).quality).toBe('720');
      expect(infoSpy).toHaveBeenCalledTimes(1);
      expect(infoSpy).toHaveBeenCalledWith('Queued 2 items');
      expect(errorSpy).not.toHaveBeenCalled();
      // The URL box is left alone so the user can browse again.
      expect(app.addUrl).toBe(' https://example.com/playlist ');
    });

    it('uses the singular for one item', async () => {
      const { app, infoSpy } = setup(Promise.resolve(['https://example.com/a']));
      app.browsePlaylist();
      await vi.waitFor(() => expect(infoSpy).toHaveBeenCalledWith('Queued 1 item'));
    });

    it('reports partial failures with counts and the first error', async () => {
      const { app, addSpy, infoSpy, errorSpy } = setup(
        Promise.resolve([
          'https://example.com/a',
          'https://example.com/b',
          'https://example.com/c',
        ]),
      );
      addSpy.mockImplementation(((payload: AddDownloadPayload) =>
        of(
          payload.url.endsWith('/a')
            ? { status: 'ok' }
            : { status: 'error', msg: `bad ${payload.url.slice(-1)}` },
        )) as unknown as typeof downloads.add);
      app.browsePlaylist();
      await vi.waitFor(() => expect(errorSpy).toHaveBeenCalled());
      expect(errorSpy).toHaveBeenCalledTimes(1);
      expect(errorSpy).toHaveBeenCalledWith('Queued 1 of 3; 2 failed: bad b');
      expect(infoSpy).not.toHaveBeenCalled();
    });

    it('adds nothing when the modal is dismissed', async () => {
      const { app, addSpy, infoSpy, errorSpy } = setup(Promise.reject('dismissed'));
      app.browsePlaylist();
      await new Promise((resolve) => setTimeout(resolve));
      expect(addSpy).not.toHaveBeenCalled();
      expect(infoSpy).not.toHaveBeenCalled();
      expect(errorSpy).not.toHaveBeenCalled();
    });
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

  describe('download options come from the server catalog', () => {
    const fieldNames = (fixture: { nativeElement: HTMLElement }) =>
      Array.from(
        fixture.nativeElement.querySelectorAll<HTMLElement>(
          '[name=downloadType],[name=codec],[name=format],[name=quality],[name=audioTags],[name=subtitleLanguage],[name=subtitleMode]',
        ),
      ).map(el => el.getAttribute('name'));

    const select = (fixture: { nativeElement: HTMLElement }, name: string) =>
      fixture.nativeElement.querySelector<HTMLSelectElement>(`select[name=${name}]`);

    // ngModel writes values and disabled state in a microtask.
    const render = async (fixture: { detectChanges: () => void }) => {
      fixture.detectChanges();
      await Promise.resolve();
      fixture.detectChanges();
    };

    it('shows no options until the catalog arrives, then restores the remembered choices', async () => {
      downloads.formats = null;
      const cookies = TestBed.inject(CookieService);
      cookies.set('metube_download_type', 'audio');
      cookies.set('metube_format', 'mp3');
      cookies.set('metube_quality', '320');
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      await render(fixture);
      expect(fieldNames(fixture)).toEqual([]);

      downloads.formatsChanged.next(testCatalog());
      await render(fixture);

      expect(fieldNames(fixture)).toEqual(['downloadType', 'format', 'quality', 'audioTags']);
      expect([app.downloadType, app.format, app.quality]).toEqual(['audio', 'mp3', '320']);
      expect(select(fixture, 'format')?.selectedOptions[0]?.textContent?.trim()).toBe('MP3');
    });

    it('replaces remembered choices the catalog does not offer with its defaults', () => {
      const cookies = TestBed.inject(CookieService);
      cookies.set('metube_download_type', 'audio');
      cookies.set('metube_format', 'ogg');
      cookies.set('metube_quality', '999');
      cookies.set('metube_audio_tags', 'everything');
      cookies.set('metube_subtitle_mode', 'bogus');
      const app = TestBed.createComponent(App).componentInstance;

      expect([app.format, app.quality, app.audioTags, app.subtitleMode])
        .toEqual(['m4a', 'best', 'with_cover', 'prefer_manual']);
      expect(app.subtitleLanguage).toBe('en');

      TestBed.inject(CookieService).set('metube_download_type', 'gif');
      expect(TestBed.createComponent(App).componentInstance.downloadType).toBe('video');
    });

    it('keeps a free-form subtitle language the suggestions do not list', () => {
      TestBed.inject(CookieService).set('metube_subtitle_language', 'fil');
      const app = TestBed.createComponent(App).componentInstance;
      expect(app.subtitleLanguage).toBe('fil');
    });

    it('leaves the form alone when the same catalog is resent, and re-checks it when the catalog changes', () => {
      const app = TestBed.createComponent(App).componentInstance;
      // Mid-edit, not yet saved: a reconnect resending the same catalog must
      // not re-apply the remembered choices over it.
      app.quality = '720';

      downloads.formatsChanged.next(testCatalog());
      expect(app.quality).toBe('720');

      const changed = testCatalog();
      const video = changed.download_type.options[0];
      video.format.options = video.format.options.map(f => ({
        ...f,
        quality: { default: 'best', options: [{ id: 'best', text: 'Best' }, { id: '1080', text: '1080p' }] },
      }));
      downloads.formatsChanged.next(changed);
      expect(app.quality).toBe('best');
      expect(app.qualities.map(q => q.id)).toEqual(['best', '1080']);
    });

    it('shows the fields each type carries, in a fixed order', async () => {
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const expected: Record<string, string[]> = {
        video: ['downloadType', 'codec', 'format', 'quality'],
        audio: ['downloadType', 'format', 'quality', 'audioTags'],
        captions: ['downloadType', 'format', 'subtitleLanguage', 'subtitleMode'],
        thumbnail: ['downloadType', 'format'],
      };
      await render(fixture);
      for (const [type, names] of Object.entries(expected)) {
        // Picked in the Type dropdown, as a user would.
        const typeSelect = select(fixture, 'downloadType')!;
        typeSelect.selectedIndex = Array.from(typeSelect.options).findIndex(o => o.textContent?.trim().toLowerCase() === type);
        typeSelect.dispatchEvent(new Event('change'));
        await render(fixture);
        expect(app.downloadType).toBe(type);
        expect(fieldNames(fixture), type).toEqual(names);
      }
      expect(app.optionColumnClass()).toBe('col-md-6');
    });

    it('disables a list that has nothing to pick', async () => {
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      app.downloadType = 'audio';
      app.downloadTypeChanged();
      app.format = 'flac';
      app.formatChanged();
      await render(fixture);
      expect(select(fixture, 'quality')?.disabled).toBe(true);

      app.format = 'mp3';
      app.formatChanged();
      await render(fixture);
      expect(select(fixture, 'quality')?.disabled).toBe(false);

      app.downloadType = 'thumbnail';
      app.downloadTypeChanged();
      await render(fixture);
      expect(select(fixture, 'format')?.disabled).toBe(true);
      expect(select(fixture, 'format')?.selectedOptions[0]?.textContent?.trim()).toBe('JPG');
    });

    it('offers an option added to the catalog without any other change', () => {
      const catalog = testCatalog();
      catalog.download_type.options[1].format.options.push({
        id: 'aac',
        text: 'AAC',
        quality: { default: 'best', options: [{ id: 'best', text: 'Best' }, { id: '256', text: '256 kbps' }] },
        tags: true,
      });
      downloads.formats = catalog;
      const app = TestBed.createComponent(App).componentInstance;
      app.downloadType = 'audio';
      app.downloadTypeChanged();
      app.format = 'aac';
      app.formatChanged();
      app.quality = '256';
      app.qualityChanged();

      expect(app.formatOptions.map(f => f.text)).toContain('AAC');
      expect(app.qualities.map(q => q.text)).toEqual(['Best', '256 kbps']);
      const payload = app['buildAddPayload']();
      expect([payload.downloadType, payload.format, payload.quality]).toEqual(['audio', 'aac', '256']);
    });

    it('labels queued downloads from the catalog, under their own type', () => {
      const app = TestBed.createComponent(App).componentInstance;
      const dl = (fields: Partial<Download>) => ({ format: '', quality: '', ...fields }) as Download;

      expect(app.formatQualityLabel(dl({ download_type: 'video', format: 'any', quality: '1080' }))).toBe('1080p');
      expect(app.formatQualityLabel(dl({ download_type: 'audio', format: 'mp3', quality: '320' }))).toBe('320 kbps');
      expect(app.formatQualityLabel(dl({ download_type: 'captions', format: 'srt', quality: 'best' }))).toBe('-');
      expect(app.formatCodecLabel(dl({ download_type: 'video', codec: 'h265' }))).toBe('H.265 (HEVC)');
      expect(app.formatCodecLabel(dl({ download_type: 'audio', format: 'flac' }))).toBe('FLAC');
      expect(app.downloadTypeLabel(dl({ download_type: 'captions' }))).toBe('Captions');
      expect(app.formatLabel(dl({ download_type: 'audio', format: 'auto' }))).toBe('Auto');
      expect(app.formatLabel(dl({ download_type: 'captions', format: 'dfxp' }))).toBe('DFXP');
    });
  });

  describe('audio Auto format and Tags dropdown', () => {
    it('lists Auto first but still defaults a switch to Audio to M4A', () => {
      const app = TestBed.createComponent(App).componentInstance;

      app.downloadType = 'audio';
      app.downloadTypeChanged();

      expect(app.formatOptions[0].id).toBe('auto');
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

  // Issue #1012: in ask mode (DELETE_FILE_ON_TRASHCAN='ask') the server only
  // deletes a completed download's file when told to, so the UI must ask the
  // user whether to keep or delete it before removing the list entry.
  describe('Clear failed asks first (#1094)', () => {
    const failed = (url: string) => ({
      id: url, title: url, url, quality: 'best', format: 'any', folder: '', custom_name_prefix: '',
      playlist_item_limit: 0, status: 'error', msg: 'boom', percent: 0, speed: 0, eta: 0,
      filename: '', checked: false,
    }) as Download;

    it('clears nothing when cancelled', async () => {
      downloads.done.set('u1', failed('u1'));
      const app = TestBed.createComponent(App).componentInstance;
      vi.spyOn(TestBed.inject(ToastService), 'confirm').mockResolvedValue(false);
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.clearFailedDownloads();

      expect(delSpy).not.toHaveBeenCalled();
    });

    it('clears every failed row, and only those, when confirmed', async () => {
      downloads.done.set('u1', failed('u1'));
      downloads.done.set('u2', failed('u2'));
      downloads.done.set('ok', { ...failed('ok'), status: 'finished' });
      const app = TestBed.createComponent(App).componentInstance;
      const confirmSpy = vi.spyOn(TestBed.inject(ToastService), 'confirm').mockResolvedValue(true);
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.clearFailedDownloads();

      expect(confirmSpy).toHaveBeenCalledWith(
        'Clear 2 failed downloads? Their URLs are not kept anywhere else, so retrying later means finding them again.',
        'Clear',
        'Cancel',
      );
      expect(delSpy).toHaveBeenCalledWith('done', ['u1', 'u2'], undefined);
    });

    it('words the question for a single row', async () => {
      downloads.done.set('u1', failed('u1'));
      const app = TestBed.createComponent(App).componentInstance;
      const confirmSpy = vi.spyOn(TestBed.inject(ToastService), 'confirm').mockResolvedValue(false);

      await app.clearFailedDownloads();

      expect(confirmSpy.mock.calls[0][0]).toMatch(/^Clear the failed download\? Its URL is not kept/);
    });

    it('asks nothing when there is nothing to clear', async () => {
      const app = TestBed.createComponent(App).componentInstance;
      const confirmSpy = vi.spyOn(TestBed.inject(ToastService), 'confirm');

      await app.clearFailedDownloads();

      expect(confirmSpy).not.toHaveBeenCalled();
    });

    it('leaves Clear completed unprompted', async () => {
      downloads.done.set('ok', { ...failed('ok'), status: 'finished' });
      const app = TestBed.createComponent(App).componentInstance;
      const confirmSpy = vi.spyOn(TestBed.inject(ToastService), 'confirm');
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.clearCompletedDownloads();

      expect(confirmSpy).not.toHaveBeenCalled();
      expect(delSpy).toHaveBeenCalledWith('done', ['ok'], undefined);
    });
  });

  describe('delete confirmation in ask mode (#1012)', () => {
    const doneEntry = (over: Partial<Download>): Download => ({
      id: 'vid1',
      title: 'Test Video',
      url: 'u1',
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
      filename: 'video.mp4',
      checked: false,
      ...over,
    } as Download);

    it('prompts and forwards "Delete files" (true) to delById', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'ask';
      downloads.done.set('u1', doneEntry({ url: 'u1' }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      const chooseSpy = vi.spyOn(toasts, 'choose').mockResolvedValue(true);
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.delDownload('done', 'u1');

      expect(chooseSpy).toHaveBeenCalledTimes(1);
      expect(delSpy).toHaveBeenCalledWith('done', ['u1'], true);
    });

    it('prompts and forwards "Remove from list" (false) to delById', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'ask';
      downloads.done.set('u1', doneEntry({ url: 'u1' }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      vi.spyOn(toasts, 'choose').mockResolvedValue(false);
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.delDownload('done', 'u1');

      expect(delSpy).toHaveBeenCalledWith('done', ['u1'], false);
    });

    it('does not call delById when the prompt is cancelled', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'ask';
      downloads.done.set('u1', doneEntry({ url: 'u1' }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      vi.spyOn(toasts, 'choose').mockResolvedValue(null);
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.delDownload('done', 'u1');

      expect(delSpy).not.toHaveBeenCalled();
    });

    it('does not prompt when DELETE_FILE_ON_TRASHCAN is "true"', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'true';
      downloads.done.set('u1', doneEntry({ url: 'u1' }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      const chooseSpy = vi.spyOn(toasts, 'choose');
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.delDownload('done', 'u1');

      expect(chooseSpy).not.toHaveBeenCalled();
      expect(delSpy).toHaveBeenCalledWith('done', ['u1'], undefined);
    });

    it('does not prompt when DELETE_FILE_ON_TRASHCAN is "false"', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'false';
      downloads.done.set('u1', doneEntry({ url: 'u1' }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      const chooseSpy = vi.spyOn(toasts, 'choose');
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.delDownload('done', 'u1');

      expect(chooseSpy).not.toHaveBeenCalled();
      expect(delSpy).toHaveBeenCalledWith('done', ['u1'], undefined);
    });

    it('does not prompt for entries with nothing on disk (e.g. clearFailedDownloads)', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'ask';
      downloads.done.set('u1', doneEntry({ url: 'u1', status: 'error', filename: '' }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      // Clear failed's own confirmation (#1094), answered yes.
      const confirmSpy = vi.spyOn(toasts, 'confirm').mockResolvedValue(true);
      const chooseSpy = vi.spyOn(toasts, 'choose');
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.clearFailedDownloads();

      expect(confirmSpy).toHaveBeenCalledTimes(1);
      expect(chooseSpy).not.toHaveBeenCalled();
      expect(delSpy).toHaveBeenCalledWith('done', ['u1'], false);
    });

    it('prompts when a failed chapter-split download left chapter files behind', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'ask';
      downloads.done.set('u1', doneEntry({
        url: 'u1',
        status: 'error',
        filename: '',
        chapter_files: [{ filename: 'ch1.mp4', size: 1 }],
      }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      const confirmSpy = vi.spyOn(toasts, 'confirm');
      const chooseSpy = vi.spyOn(toasts, 'choose').mockResolvedValue(true);
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.clearFailedDownloads();

      // The file prompt has Cancel, so it is the only question asked.
      expect(confirmSpy).not.toHaveBeenCalled();
      expect(chooseSpy).toHaveBeenCalledTimes(1);
      expect(delSpy).toHaveBeenCalledWith('done', ['u1'], true);
    });

    it('does not prompt for queue deletions', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'ask';
      downloads.queue.set('u1', doneEntry({ url: 'u1', status: 'downloading' }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      const chooseSpy = vi.spyOn(toasts, 'choose');
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.delDownload('queue', 'u1');

      expect(chooseSpy).not.toHaveBeenCalled();
      expect(delSpy).toHaveBeenCalledWith('queue', ['u1'], undefined);
    });

    it('retryDownload does not prompt even in ask mode, and sends no flag', () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'ask';
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      const chooseSpy = vi.spyOn(toasts, 'choose');
      const delSpy = vi.spyOn(downloads, 'delById');
      const download = doneEntry({ url: 'u1', status: 'error' });

      app.retryDownload('u1', download);

      expect(chooseSpy).not.toHaveBeenCalled();
      expect(delSpy).toHaveBeenCalledWith('done', ['u1']);
    });

    it('prompts once with a count for multiple completed entries', async () => {
      downloads.configuration['DELETE_FILE_ON_TRASHCAN'] = 'ask';
      downloads.done.set('u1', doneEntry({ url: 'u1' }));
      downloads.done.set('u2', doneEntry({ url: 'u2', title: 'Second video' }));
      const fixture = TestBed.createComponent(App);
      const app = fixture.componentInstance;
      const toasts = TestBed.inject(ToastService);
      const chooseSpy = vi.spyOn(toasts, 'choose').mockResolvedValue(true);
      const delSpy = vi.spyOn(downloads, 'delById');

      await app.clearCompletedDownloads();

      expect(chooseSpy).toHaveBeenCalledTimes(1);
      expect(chooseSpy.mock.calls[0][0]).toContain('2 items');
      expect(delSpy).toHaveBeenCalledTimes(1);
      expect(delSpy).toHaveBeenCalledWith('done', ['u1', 'u2'], true);
    });
  });

});
