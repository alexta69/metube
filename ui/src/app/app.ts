import { NgTemplateOutlet } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { AfterViewInit, ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, viewChild, inject, OnDestroy, OnInit } from '@angular/core';
import { Observable, OperatorFunction, Subject, Subscription, from, map, merge, debounceTime, distinctUntilChanged, filter, finalize, mergeMap, tap } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { NgbModal, NgbModule, NgbTypeahead } from '@ng-bootstrap/ng-bootstrap';
import { NgSelectModule } from '@ng-select/ng-select';
import { faTrashAlt, faCheckCircle, faTimesCircle, faCheck, faDownload, faFileImport, faFileExport, faCopy, faClock, faTachometerAlt, faChevronRight, faChevronDown, faUpload } from '@fortawesome/free-solid-svg-icons';
import { faGithub } from '@fortawesome/free-brands-svg-icons';
import { CookieService } from 'ngx-cookie-service';
import { ADD_REQUEST_CONCURRENCY, AddDownloadPayload, DownloadsService } from './services/downloads.service';
import { MeTubeSocket } from './services/metube-socket.service';
import { SubscriptionsService } from './services/subscriptions.service';
import { ToastService } from './services/toast.service';
import { BatchUrlsService, BatchUrlFilter } from './services/batch-urls.service';
import { SettingsStore } from './services/settings-store.service';
import { Themes } from './theme';
import {
  Status,
  Theme,
  Option,
  Choice,
  DownloadTypeOption,
  FormatCatalog,
  FormatOption,
} from './interfaces';
import { SpeedPipe } from './pipes';
import {
  ToastContainerComponent,
  PlaylistBrowserComponent,
  SubscriptionsSectionComponent,
  BatchImportComponent,
  DownloadingSectionComponent,
  CompletedSectionComponent,
} from './components/';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
        FormsModule,
        NgTemplateOutlet,
        FontAwesomeModule,
        NgbModule,
        NgSelectModule,
        SpeedPipe,
        ToastContainerComponent,
        SubscriptionsSectionComponent,
        DownloadingSectionComponent,
        CompletedSectionComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.sass',
})
export class App implements AfterViewInit, OnInit, OnDestroy {
  downloads = inject(DownloadsService);
  subscriptionsSvc = inject(SubscriptionsService);
  private toasts = inject(ToastService);
  private batchUrls = inject(BatchUrlsService);
  private socket = inject(MeTubeSocket);
  private cookieService = inject(CookieService);
  private settings = inject(SettingsStore);
  private http = inject(HttpClient);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);
  private modal = inject(NgbModal);

  addUrl!: string;
  // The server's catalog of download options (app/format_catalog.py); the
  // form is not shown until it arrives. The lists below are the parts of it
  // the form is currently showing.
  catalog: FormatCatalog | null = null;
  downloadTypes: DownloadTypeOption[] = [];
  codecOptions: Option[] = [];
  formatOptions: FormatOption[] = [];
  qualities: Option[] = [];
  audioTagsOptions: Option[] = [];
  subtitleLanguages: Option[] = [];
  subtitleModes: Option[] = [];
  downloadType: string;
  codec: string;
  quality: string;
  format: string;
  folder!: string;
  customNamePrefix!: string;
  autoStart: boolean;
  playlistItemLimit!: number;
  splitByChapters: boolean;
  sponsorblock: boolean;
  audioTags: string;
  chapterTemplate: string;
  clipStart = '';
  clipEnd = '';
  videoPassword = '';
  subtitleLanguage: string;
  subtitleMode: string;
  ytdlOptionsPresets: string[] = [];
  ytdlOptionsOverrides: string;
  ytdlOptionPresetNames: string[] = [];
  addInProgress = false;
  cancelRequested = false;
  subscribeInProgress = false;
  checkIntervalMinutes = 60;
  titleRegex = '';
  skipSubscriberOnly = false;
  hasCookies = false;
  cookieUploadInProgress = false;
  themes: Theme[] = Themes;
  activeTheme: Theme | undefined;
  readonly folderTypeahead = viewChild<NgbTypeahead>('folderTypeahead');
  folderFocus$ = new Subject<string>();
  folderClick$ = new Subject<string>();
  ytDlpOptionsUpdateTime: string | null = null;
  ytDlpVersion: string | null = null;
  metubeVersion: string | null = null;
  isAdvancedOpen = false;
  private previousDownloadType = '';
  private addRequestSub?: Subscription;
  private selectionsByType: Record<string, {
    codec: string;
    format: string;
    quality: string;
    subtitleLanguage: string;
    subtitleMode: string;
  }> = {};
  private readonly selectionKeyPrefix = 'metube_selection_';
  // The theme is the one setting kept in a cookie: the server sets it to
  // DEFAULT_THEME on a first visit. Everything else is in SettingsStore.
  private static readonly THEME_COOKIE_EXPIRY_DAYS = 3650;
  private colorSchemeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  private onColorSchemeChanged = () => {
    if (this.activeTheme && this.activeTheme.id === 'auto') {
      this.setTheme(this.activeTheme);
    }
  };

  // Download metrics
  activeDownloads = 0;
  queuedDownloads = 0;
  completedDownloads = 0;
  failedDownloads = 0;
  totalSpeed = 0;


  faTrashAlt = faTrashAlt;
  faCheckCircle = faCheckCircle;
  faTimesCircle = faTimesCircle;
  faCheck = faCheck;
  faDownload = faDownload;
  faFileImport = faFileImport;
  faFileExport = faFileExport;
  faCopy = faCopy;
  faGithub = faGithub;
  faClock = faClock;
  faTachometerAlt = faTachometerAlt;
  faChevronRight = faChevronRight;
  faChevronDown = faChevronDown;
  faUpload = faUpload;
  constructor() {
    // Remembered choices are checked against the catalog when it arrives.
    this.downloadType = this.settings.get('metube_download_type');
    this.codec = this.settings.get('metube_codec');
    this.format = this.settings.get('metube_format');
    this.quality = this.settings.get('metube_quality');
    this.autoStart = this.settings.get('metube_auto_start') !== 'false';
    this.splitByChapters = this.settings.get('metube_split_chapters') === 'true';
    this.sponsorblock = this.settings.get('metube_sponsorblock') === 'true';
    this.audioTags = this.settings.get('metube_audio_tags');
    // Will be set from backend configuration, use empty string as placeholder
    this.chapterTemplate = this.settings.get('metube_chapter_template') || '';
    this.clipStart = this.settings.get('metube_clip_start') || '';
    this.clipEnd = this.settings.get('metube_clip_end') || '';
    this.subtitleLanguage = this.settings.get('metube_subtitle_language');
    this.subtitleMode = this.settings.get('metube_subtitle_mode');
    this.ytdlOptionsPresets = this.loadStoredYtdlOptionsPresets();
    this.ytdlOptionsOverrides = this.settings.get('metube_ytdl_options_overrides') || '';
    if (this.downloads.formats) {
      this.applyCatalog(this.downloads.formats);
    }
    this.downloads.formatsChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((catalog) => {
      this.applyCatalog(catalog);
      this.cdr.markForCheck();
    });

    const ci = parseInt(this.settings.get('metube_check_interval') || '', 10);
    if (!Number.isNaN(ci) && ci >= 1) {
      this.checkIntervalMinutes = ci;
    }
    this.activeTheme = this.getPreferredTheme(this.cookieService);

    // Subscribe to download updates
    this.downloads.queueChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.updateMetrics();
      this.cdr.markForCheck();
    });
    this.downloads.doneChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.updateMetrics();
      this.cdr.markForCheck();
    });
    // Subscribe to real-time updates
    this.downloads.updated.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.updateMetrics();
      this.cdr.markForCheck();
    });

  }

  ngOnInit() {
    this.downloads.getCookieStatus().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(data => {
      this.hasCookies = !!(data && typeof data === 'object' && 'has_cookies' in data && data.has_cookies);
      this.cdr.markForCheck();
    });
    this.getConfiguration();
    this.getYtdlOptionsUpdateTime();
    this.getYtdlOptionPresets();
    this.setTheme(this.activeTheme!);

    this.colorSchemeMediaQuery.addEventListener('change', this.onColorSchemeChanged);
  }

  ngAfterViewInit() {
    // Counts and action button states for already-loaded entries.
    this.updateMetrics();
    this.fetchVersionInfo();
    this.socket.fromEvent('connect')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.fetchVersionInfo());
  }

  ngOnDestroy() {
    this.addRequestSub?.unsubscribe();
    this.colorSchemeMediaQuery.removeEventListener('change', this.onColorSchemeChanged);
  }

  qualityChanged() {
    this.settings.set('metube_quality', this.quality);
    this.saveSelection(this.downloadType);
  }

  downloadTypeChanged() {
    this.saveSelection(this.previousDownloadType);
    this.restoreSelection(this.downloadType);
    this.settings.set('metube_download_type', this.downloadType);
    this.normalizeSelectionsForType();
    this.setQualities();
    this.refreshFormatOptions();
    this.saveSelection(this.downloadType);
    this.previousDownloadType = this.downloadType;
  }

  codecChanged() {
    this.settings.set('metube_codec', this.codec);
    this.saveSelection(this.downloadType);
  }

  showAdvanced() {
    return this.downloads.configuration['CUSTOM_DIRS'];
  }

  allowYtdlOptionsOverrides() {
    return this.downloads.configuration['ALLOW_YTDL_OPTIONS_OVERRIDES'] === true;
  }

  searchFolder: OperatorFunction<string, readonly string[]> = (text$: Observable<string>) => {
    const debouncedText$ = text$.pipe(debounceTime(150), distinctUntilChanged());
    const clicksWithClosedPopup$ = this.folderClick$.pipe(
      filter(() => !this.folderTypeahead()?.isPopupOpen()),
    );
    return merge(debouncedText$, this.folderFocus$, clicksWithClosedPopup$).pipe(
      map(term => {
        const dirs = this.isAudioType()
          ? (this.downloads.customDirs?.['audio_download_dir'] ?? [])
          : (this.downloads.customDirs?.['download_dir'] ?? []);
        const t = (term ?? '').toLowerCase();
        return (t === '' ? dirs : dirs.filter(d => d.toLowerCase().includes(t))).slice(0, 10);
      }),
    );
  };

  isAudioType() {
    return this.downloadType === 'audio';
  }

  getYtdlOptionsUpdateTime() {
    this.downloads.ytdlOptionsChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
       // eslint-disable-next-line @typescript-eslint/no-explicit-any
      next: (data:any) => {
        if (data['success']){
          const date = new Date(data['update_time'] * 1000);
          this.ytDlpOptionsUpdateTime=date.toLocaleString();
        }else{
          this.toasts.error("Error reloading yt-dlp options: " + data['msg']);
        }
        this.cdr.markForCheck();
      }
    });
  }
  getConfiguration() {
    this.downloads.configurationChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
       // eslint-disable-next-line @typescript-eslint/no-explicit-any
      next: (config: any) => {
        const playlistItemLimit = parseInt(String(config['DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT'] ?? '0'), 10);
        if (!Number.isNaN(playlistItemLimit) && playlistItemLimit > 0) {
          this.playlistItemLimit = playlistItemLimit;
        }
        // Pre-fill the download folder, unless the user has already typed one
        // this session. The server drops DEFAULT_FOLDER when CUSTOM_DIRS is
        // off, so there is nothing to guard against here.
        if (!this.folder) {
          this.folder = String(config['DEFAULT_FOLDER'] ?? '');
        }
        // Set chapter template from backend config if not already remembered
        if (!this.chapterTemplate) {
          this.chapterTemplate = config['OUTPUT_TEMPLATE_CHAPTER'];
        }
        if (!this.settings.has('metube_check_interval')) {
          const dci = parseInt(String(config['SUBSCRIPTION_DEFAULT_CHECK_INTERVAL'] ?? 60), 10);
          if (!Number.isNaN(dci) && dci >= 1) {
            this.checkIntervalMinutes = dci;
          }
        }
        this.cdr.markForCheck();
      }
    });
  }

  getYtdlOptionPresets() {
    this.downloads.getPresets().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        this.ytdlOptionPresetNames = Array.isArray(data?.presets)
          ? data.presets.filter((preset): preset is string => typeof preset === 'string')
          : [];
        if (this.ytdlOptionsPresets?.length) {
          const valid = new Set(this.ytdlOptionPresetNames);
          const filtered = this.ytdlOptionsPresets.filter((p) => valid.has(p));
          if (filtered.length !== this.ytdlOptionsPresets.length) {
            this.ytdlOptionsPresets = filtered;
            this.ytdlOptionsPresetsChanged();
          }
        }
        this.cdr.markForCheck();
      },
    });
  }

  private loadStoredYtdlOptionsPresets(): string[] {
    const stored = this.settings.get('metube_ytdl_options_presets');
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as unknown;
        if (Array.isArray(parsed)) {
          return parsed.filter((p): p is string => typeof p === 'string' && p.length > 0);
        }
      } catch {
        // fall through to the legacy single-preset value
      }
    }
    const legacy = this.settings.get('metube_ytdl_options_preset')?.trim();
    return legacy ? [legacy] : [];
  }

  private validateYtdlOptionsOverrides(value: string): boolean {
    if (!this.allowYtdlOptionsOverrides()) {
      return true;
    }
    const trimmed = value?.trim() || '';
    if (!trimmed) {
      return true;
    }
    try {
      const parsed = JSON.parse(trimmed);
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        this.toasts.error('Custom yt-dlp options must be a JSON object');
        return false;
      }
    } catch {
      this.toasts.error('Custom yt-dlp options must be valid JSON');
      return false;
    }
    return true;
  }

  checkIntervalChanged() {
    this.settings.set('metube_check_interval', String(this.checkIntervalMinutes));
  }

  addSubscription() {
    if (this.subscribeInProgress) {
      return;
    }
    const payload = this.buildAddPayload();
    if (!payload.url?.trim()) {
      this.toasts.error('Please enter a URL');
      return;
    }
    const tr = (this.titleRegex || '').trim();
    if (tr) {
      try {
        void RegExp(tr);
      } catch {
        this.toasts.error('Invalid subscription title filter (regex)');
        return;
      }
    }
    if (payload.splitByChapters && !payload.chapterTemplate.includes('%(section_number)')) {
      this.toasts.error('Chapter template must include %(section_number)');
      return;
    }
    if (!this.validateYtdlOptionsOverrides(payload.ytdlOptionsOverrides)) {
      return;
    }
    this.subscribeInProgress = true;
    this.subscriptionsSvc
      .subscribe({
        ...payload,
        checkIntervalMinutes: this.checkIntervalMinutes,
        titleRegex: tr,
        skipSubscriberOnly: this.skipSubscriberOnly,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => {
          this.subscribeInProgress = false;
          this.cdr.markForCheck();
        }),
      )
      .subscribe({
        next: (res) => {
          const r = res as { status?: string; msg?: string };
          if (r.status === 'error') {
            this.toasts.error(r.msg || 'Subscribe failed');
          } else {
            this.addUrl = '';
            this.titleRegex = '';
            this.skipSubscriberOnly = false;
          }
        },
      });
  }

  getPreferredTheme(cookieService: CookieService) {
    let theme = 'auto';
    if (cookieService.check('metube_theme')) {
      theme = cookieService.get('metube_theme');
    }

    return this.themes.find(x => x.id === theme) ?? this.themes.find(x => x.id === 'auto');
  }

  themeChanged(theme: Theme) {
    this.cookieService.set('metube_theme', theme.id, { expires: App.THEME_COOKIE_EXPIRY_DAYS });
    this.setTheme(theme);
  }

  setTheme(theme: Theme) {
    this.activeTheme = theme;
    if (theme.id === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.setAttribute('data-bs-theme', 'dark');
    } else {
      document.documentElement.setAttribute('data-bs-theme', theme.id);
    }
  }

  formatChanged() {
    this.settings.set('metube_format', this.format);
    this.setQualities();
    this.saveSelection(this.downloadType);
  }

  autoStartChanged() {
    this.settings.set('metube_auto_start', this.autoStart ? 'true' : 'false');
  }

  audioTagsChanged(value: string) {
    this.audioTags = value;
    this.settings.set('metube_audio_tags', this.audioTags);
  }

  // Whether the selected audio format can carry tags (the catalog's flag).
  tagsSupported(): boolean {
    return this.selectedFormat()?.tags !== false;
  }

  // A format that cannot carry tags shows None (disabled) without overwriting
  // the saved choice for the other formats.
  displayedAudioTags(): string {
    return this.tagsSupported() ? this.audioTags : 'none';
  }

  sponsorblockChanged() {
    this.settings.set('metube_sponsorblock', this.sponsorblock ? 'true' : 'false');
  }

  splitByChaptersChanged() {
    this.settings.set('metube_split_chapters', this.splitByChapters ? 'true' : 'false');
  }

  chapterTemplateChanged() {
    // Restore default if template is cleared - get from configuration
    if (!this.chapterTemplate || this.chapterTemplate.trim() === '') {
      const configuredTemplate = this.downloads.configuration['OUTPUT_TEMPLATE_CHAPTER'];
      this.chapterTemplate = typeof configuredTemplate === 'string' ? configuredTemplate : '';
    }
    this.settings.set('metube_chapter_template', this.chapterTemplate);
  }

  clipStartChanged() {
    this.settings.set('metube_clip_start', this.clipStart);
  }

  clipEndChanged() {
    this.settings.set('metube_clip_end', this.clipEnd);
  }

  subtitleLanguageChanged() {
    this.settings.set('metube_subtitle_language', this.subtitleLanguage);
    this.saveSelection(this.downloadType);
  }

  subtitleModeChanged() {
    this.settings.set('metube_subtitle_mode', this.subtitleMode);
    this.saveSelection(this.downloadType);
  }

  ytdlOptionsPresetsChanged() {
    this.settings.set('metube_ytdl_options_presets', JSON.stringify(this.ytdlOptionsPresets ?? []));
  }

  ytdlOptionsOverridesChanged() {
    this.settings.set('metube_ytdl_options_overrides', this.ytdlOptionsOverrides);
  }

  isVideoType() {
    return this.downloadType === 'video';
  }

  // Each choice list is the catalog's: the selected type's formats and codecs,
  // and the selected format's qualities (empty when it has none to pick).
  setQualities() {
    const choice = this.selectedFormat()?.quality;
    this.qualities = choice?.options ?? [];
    if (choice) {
      this.quality = this.pick(choice, this.quality);
    }
  }

  refreshFormatOptions() {
    const type = this.typeEntry(this.downloadType);
    this.formatOptions = type?.format.options ?? [];
    this.codecOptions = type?.codec?.options ?? [];
  }

  currentType(): DownloadTypeOption | undefined {
    return this.typeEntry(this.downloadType);
  }

  hasSubtitleSettings(): boolean {
    const type = this.currentType();
    return !!(type?.subtitle_mode || type?.subtitle_language);
  }

  // Four fields per row are too tight at ~768px for the longer values, so a
  // four-field type goes 2×2 from md to lg and one row from lg up.
  optionColumnClass(): string {
    const type = this.currentType();
    if (!type) {
      return 'col-md-6';
    }
    const fields = 2
      + (type.codec ? 1 : 0)
      + (this.qualities.length ? 1 : 0)
      + (type.audio_tags ? 1 : 0)
      + (type.subtitle_language ? 1 : 0)
      + (type.subtitle_mode ? 1 : 0);
    if (fields >= 4) {
      return 'col-12 col-md-6 col-lg-3';
    }
    return fields === 3 ? 'col-12 col-md-4' : 'col-md-6';
  }

  // A list with a single entry is shown, but there is nothing to pick.
  hasQualityChoice(): boolean {
    return this.qualities.length > 1;
  }

  hasFormatChoice(): boolean {
    return this.formatOptions.length > 1;
  }

  private typeEntry(type: string): DownloadTypeOption | undefined {
    return this.downloadTypes.find(t => t.id === type);
  }

  private selectedFormat(): FormatOption | undefined {
    return this.typeEntry(this.downloadType)?.format.options.find(f => f.id === this.format);
  }

  // The remembered value if the choice still offers it, else the default.
  private pick(choice: Choice, value: string): string {
    return choice.options.some(o => o.id === value) ? value : choice.default;
  }

  // Runs whenever the server sends its catalog (on every connect). A changed
  // catalog, e.g. after a server upgrade, re-checks every remembered choice.
  private applyCatalog(catalog: FormatCatalog) {
    if (this.catalog && JSON.stringify(this.catalog) === JSON.stringify(catalog)) {
      return;
    }
    this.catalog = catalog;
    this.downloadTypes = catalog.download_type.options;
    const audio = this.downloadTypes.find(t => t.audio_tags);
    const captions = this.downloadTypes.find(t => t.subtitle_mode || t.subtitle_language);
    this.audioTagsOptions = audio?.audio_tags?.options ?? [];
    this.subtitleLanguages = captions?.subtitle_language?.options ?? [];
    this.subtitleModes = captions?.subtitle_mode?.options ?? [];

    this.downloadType = this.pick(catalog.download_type, this.downloadType);
    this.loadSavedSelections();
    this.restoreSelection(this.downloadType);
    this.normalizeSelectionsForType();
    this.setQualities();
    this.refreshFormatOptions();
    this.previousDownloadType = this.downloadType;
    this.saveSelection(this.downloadType);
  }

  // Brings the form's values in line with what the catalog offers for the
  // selected type. Fields a type doesn't have are left as they are; the
  // server ignores them for that type.
  private normalizeSelectionsForType() {
    const type = this.typeEntry(this.downloadType);
    if (!type) {
      return;
    }
    this.format = this.pick(type.format, this.format);
    if (type.codec) {
      this.codec = this.pick(type.codec, this.codec);
    }
    // Audio tags and the subtitle settings are kept across types, so they are
    // checked against the types that define them.
    const audio = this.downloadTypes.find(t => t.audio_tags);
    if (audio?.audio_tags) {
      this.audioTags = this.pick(audio.audio_tags, this.audioTags);
    }
    const captions = this.downloadTypes.find(t => t.subtitle_mode || t.subtitle_language);
    if (captions?.subtitle_mode) {
      this.subtitleMode = this.pick(captions.subtitle_mode, this.subtitleMode);
    }
    if (captions?.subtitle_language && !this.subtitleLanguage?.trim()) {
      // Any language tag is accepted; only an empty one takes the default.
      this.subtitleLanguage = captions.subtitle_language.default;
    }
    this.settings.set('metube_format', this.format);
    this.settings.set('metube_codec', this.codec);
  }

  private saveSelection(type: string) {
    if (!type) return;
    const selection = {
      codec: this.codec,
      format: this.format,
      quality: this.quality,
      subtitleLanguage: this.subtitleLanguage,
      subtitleMode: this.subtitleMode,
    };
    this.selectionsByType[type] = selection;
    this.settings.set(this.selectionKeyPrefix + type, JSON.stringify(selection));
  }

  private restoreSelection(type: string) {
    const saved = this.selectionsByType[type];
    if (!saved) return;
    this.codec = saved.codec;
    this.format = saved.format;
    this.quality = saved.quality;
    this.subtitleLanguage = saved.subtitleLanguage;
    this.subtitleMode = saved.subtitleMode;
  }

  private loadSavedSelections() {
    for (const type of this.downloadTypes.map(t => t.id)) {
      const key = this.selectionKeyPrefix + type;
      if (!this.settings.has(key)) continue;
      try {
        const raw = this.settings.get(key);
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
          this.selectionsByType[type] = {
            codec: String(parsed.codec ?? ''),
            format: String(parsed.format ?? ''),
            quality: String(parsed.quality ?? ''),
            subtitleLanguage: String(parsed.subtitleLanguage ?? ''),
            subtitleMode: String(parsed.subtitleMode ?? ''),
          };
        }
      } catch {
        // Ignore malformed stored values.
      }
    }
  }

  private buildAddPayload(overrides: Partial<AddDownloadPayload> = {}): AddDownloadPayload {
    const allowYtdlOptionsOverrides = this.allowYtdlOptionsOverrides();
    return {
      url: overrides.url ?? this.addUrl,
      downloadType: overrides.downloadType ?? this.downloadType,
      codec: overrides.codec ?? this.codec,
      quality: overrides.quality ?? this.quality,
      format: overrides.format ?? this.format,
      folder: overrides.folder ?? this.folder,
      customNamePrefix: overrides.customNamePrefix ?? this.customNamePrefix,
      playlistItemLimit: overrides.playlistItemLimit ?? this.playlistItemLimit,
      autoStart: overrides.autoStart ?? this.autoStart,
      splitByChapters: overrides.splitByChapters ?? this.splitByChapters,
      sponsorblock: overrides.sponsorblock ?? this.sponsorblock,
      audioTags: overrides.audioTags ?? this.audioTags,
      chapterTemplate: overrides.chapterTemplate ?? this.chapterTemplate,
      subtitleLanguage: overrides.subtitleLanguage ?? this.subtitleLanguage,
      subtitleMode: overrides.subtitleMode ?? this.subtitleMode,
      ytdlOptionsPresets: overrides.ytdlOptionsPresets ?? [...this.ytdlOptionsPresets],
      ytdlOptionsOverrides: allowYtdlOptionsOverrides
        ? (overrides.ytdlOptionsOverrides ?? this.ytdlOptionsOverrides)
        : '',
      clipStart: overrides.clipStart ?? this.clipStart,
      clipEnd: overrides.clipEnd ?? this.clipEnd,
      videoPassword: overrides.videoPassword ?? this.videoPassword,
    };
  }

  addDownload(overrides: Partial<AddDownloadPayload> = {}) {
    const payload = this.buildAddPayload(overrides);
    if (!this.validateAddSettings(payload)) {
      return;
    }

    this.addInProgress = true;
    this.cancelRequested = false;
    this.addRequestSub?.unsubscribe();
    this.addRequestSub = this.downloads.add(payload).subscribe((status: Status) => {
      if (status.status === 'error' && !this.cancelRequested) {
        this.toasts.error(`Error adding URL: ${status.msg}`);
      } else if (status.status !== 'error') {
        // e.g. "Already in queue: ..." when the backend skipped a duplicate.
        if (status.msg) {
          this.toasts.info(status.msg);
        }
        this.addUrl = '';
        this.videoPassword = '';
      }
      this.resetAddState();
    });
  }

  // Settings checks shared by every path that queues downloads from the form.
  private validateAddSettings(payload: AddDownloadPayload): boolean {
    // Validate chapter template if chapter splitting is enabled
    if (payload.splitByChapters && !payload.chapterTemplate.includes('%(section_number)')) {
      this.toasts.error('Chapter template must include %(section_number)');
      return false;
    }
    return this.validateYtdlOptionsOverrides(payload.ytdlOptionsOverrides);
  }

  // Probe a playlist or channel URL and let the user pick which entries to
  // queue. The picked entries are added as single downloads with the form's
  // current settings.
  browsePlaylist() {
    const url = (this.addUrl ?? '').trim();
    if (!url) {
      return;
    }
    const template = this.buildAddPayload({ url });
    if (!this.validateAddSettings(template)) {
      return;
    }
    const ref = this.modal.open(PlaylistBrowserComponent, { size: 'lg', scrollable: true });
    ref.componentInstance.payload = {
      url,
      playlistItemLimit: template.playlistItemLimit,
      ytdlOptionsPresets: template.ytdlOptionsPresets,
      ytdlOptionsOverrides: template.ytdlOptionsOverrides,
    };
    ref.result.then(
      (urls: string[]) => this.queueBrowsedEntries(urls),
      () => { /* dismissed */ },
    );
  }

  private queueBrowsedEntries(urls: string[]) {
    if (!urls?.length) {
      return;
    }
    let queued = 0;
    let failed = 0;
    let firstError = '';
    from(urls).pipe(
      mergeMap(
        url => this.downloads.add(this.buildAddPayload({ url })).pipe(
          tap((status: Status) => {
            if (status.status === 'error') {
              failed++;
              firstError ||= status.msg || 'Unknown error';
            } else {
              queued++;
            }
          }),
        ),
        ADD_REQUEST_CONCURRENCY,
      ),
      takeUntilDestroyed(this.destroyRef),
      finalize(() => {
        if (failed > 0) {
          this.toasts.error(`Queued ${queued} of ${urls.length}; ${failed} failed: ${firstError}`);
        } else if (queued > 0) {
          this.toasts.info(`Queued ${queued} ${queued === 1 ? 'item' : 'items'}`);
        }
        this.cdr.markForCheck();
      }),
    ).subscribe();
  }

  cancelAdding() {
    this.cancelRequested = true;
    this.downloads.cancelAdd().subscribe({
      next: () => {
        this.addRequestSub?.unsubscribe();
        this.resetAddState();
      },
      error: (err) => {
        this.cancelRequested = false;
        console.error('Failed to cancel adding:', err?.message || err);
      }
    });
  }

  private resetAddState() {
    this.addRequestSub = undefined;
    this.addInProgress = false;
    this.cancelRequested = false;
    this.cdr.markForCheck();
  }

  // Keeps the non-negative integer fields to digits. Only a typed character
  // is filtered: named keys (Enter, Tab, arrows, Escape, F-keys) and anything
  // with a modifier pass, so Enter submits and Ctrl/Cmd+A/C/V/X/Z still work.
  // An allowlist of named keys used to block all of those.
  digitsOnly(event: KeyboardEvent) {
    if (event.ctrlKey || event.metaKey || event.altKey || event.key.length !== 1) {
      return;
    }
    if (!/^[0-9]$/.test(event.key)) {
      event.preventDefault();
    }
  }

  // Open the Batch Import modal; each URL is queued with the form's settings.
  openBatchImportModal(): void {
    const ref = this.modal.open(BatchImportComponent);
    ref.componentInstance.buildPayload = (url: string) => this.buildAddPayload({ url });
  }

  // Export URLs based on filter: 'pending', 'completed', 'failed', or 'all'
  exportBatchUrls(filter: BatchUrlFilter): void {
    this.batchUrls.export(filter);
  }

  // Copy URLs to clipboard based on filter: 'pending', 'completed', 'failed', or 'all'
  copyBatchUrls(filter: BatchUrlFilter): void {
    this.batchUrls.copy(filter);
  }

  fetchVersionInfo(): void {
    // Relative, like every other API call, so it follows URL_PREFIX.
    this.http.get<{ 'yt-dlp': string, version: string }>('version')
      .subscribe({
        next: (data) => {
          this.ytDlpVersion = data['yt-dlp'];
          this.metubeVersion = data.version;
          this.cdr.markForCheck();
        },
        error: () => {
          this.ytDlpVersion = null;
          this.metubeVersion = null;
          this.cdr.markForCheck();
        }
      });
  }

  toggleAdvanced() {
    this.isAdvancedOpen = !this.isAdvancedOpen;
  }

  onCookieFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;
    this.cookieUploadInProgress = true;
    this.cdr.markForCheck();
    this.downloads.uploadCookies(input.files[0]).subscribe({
      next: (response) => {
        if (response?.status === 'ok') {
          this.hasCookies = true;
        } else {
          this.refreshCookieStatus();
          this.toasts.error(`Error uploading cookies: ${this.formatErrorMessage(response?.msg)}`);
        }
        this.cookieUploadInProgress = false;
        input.value = '';
        this.cdr.markForCheck();
      },
      error: () => {
        this.refreshCookieStatus();
        this.cookieUploadInProgress = false;
        input.value = '';
        this.toasts.error('Error uploading cookies.');
        this.cdr.markForCheck();
      }
    });
  }

  private formatErrorMessage(error: unknown): string {
    if (typeof error === 'string') {
      return error;
    }
    if (error && typeof error === 'object') {
      const obj = error as Record<string, unknown>;
      for (const key of ['msg', 'reason', 'error', 'detail']) {
        const value = obj[key];
        if (typeof value === 'string' && value.trim()) {
          return value;
        }
      }
      try {
        return JSON.stringify(error);
      } catch {
        return 'Unknown error';
      }
    }
    return 'Unknown error';
  }

  deleteCookies() {
    this.downloads.deleteCookies().subscribe({
      next: (response) => {
        if (response?.status === 'ok') {
          this.refreshCookieStatus();
          return;
        }
        this.refreshCookieStatus();
        this.toasts.error(`Error deleting cookies: ${this.formatErrorMessage(response?.msg)}`);
      },
      error: () => {
        this.refreshCookieStatus();
        this.toasts.error('Error deleting cookies.');
      }
    });
  }

  private refreshCookieStatus() {
    this.downloads.getCookieStatus().subscribe(data => {
      this.hasCookies = !!(data && typeof data === 'object' && 'has_cookies' in data && data.has_cookies);
      this.cdr.markForCheck();
    });
  }

  private updateMetrics() {
    let active = 0;
    let queued = 0;
    let completed = 0;
    let failed = 0;
    let speed = 0;

    this.downloads.queue.forEach((download) => {
      if (download.status === 'downloading') {
        active++;
        speed += download.speed || 0;
      } else if (download.status === 'preparing' || download.status === 'postprocessing') {
        active++;
      } else if (download.status === 'queued' || download.status === 'pending' || download.status === 'scheduled') {
        queued++;
      }
    });

    this.downloads.done.forEach((download) => {
      if (download.status === 'finished') {
        completed++;
      } else if (download.status === 'error') {
        failed++;
      }
    });

    this.activeDownloads = active;
    this.queuedDownloads = queued;
    this.completedDownloads = completed;
    this.failedDownloads = failed;
    this.totalSpeed = speed;
  }
}
