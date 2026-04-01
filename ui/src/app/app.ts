import { AsyncPipe, DatePipe, KeyValuePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { AfterViewInit, ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, ElementRef, viewChild, inject, OnDestroy, OnInit } from '@angular/core';
import { Observable, map, distinctUntilChanged, auditTime } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { NgbModule } from '@ng-bootstrap/ng-bootstrap';
import { NgSelectModule } from '@ng-select/ng-select';  
import { faTrashAlt, faCheckCircle, faTimesCircle, faRedoAlt, faSun, faMoon, faCheck, faCircleHalfStroke, faDownload, faExternalLinkAlt, faFileImport, faFileExport, faCopy, faClock, faTachometerAlt, faSortAmountDown, faSortAmountUp, faChevronRight, faChevronDown, faUpload } from '@fortawesome/free-solid-svg-icons';
import { faGithub } from '@fortawesome/free-brands-svg-icons';
import { CookieService } from 'ngx-cookie-service';
import { AddDownloadPayload, DownloadsService, HasharrSettings } from './services/downloads.service';
import { Themes } from './theme';
import {
  Download,
  Status,
  Theme,
  Quality,
  Option,
  AudioFormatOption,
  DOWNLOAD_TYPES,
  VIDEO_CODECS,
  VIDEO_FORMATS,
  VIDEO_QUALITIES,
  AUDIO_FORMATS,
  CAPTION_FORMATS,
  THUMBNAIL_FORMATS,
  State,
} from './interfaces';
import { EtaPipe, SpeedPipe, FileSizePipe } from './pipes';
import { SelectAllCheckboxComponent, ItemCheckboxComponent } from './components/';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
        FormsModule,
        KeyValuePipe,
        AsyncPipe,
        DatePipe,
        FontAwesomeModule,
        NgbModule,
        NgSelectModule,
        EtaPipe,
        SpeedPipe,
        FileSizePipe,
        SelectAllCheckboxComponent,
        ItemCheckboxComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.sass',
})
export class App implements AfterViewInit, OnInit, OnDestroy {
  downloads = inject(DownloadsService);
  private cookieService = inject(CookieService);
  private http = inject(HttpClient);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  addUrl!: string;
  downloadTypes: Option[] = DOWNLOAD_TYPES;
  videoCodecs: Option[] = VIDEO_CODECS;
  videoFormats: Option[] = VIDEO_FORMATS;
  audioFormats: AudioFormatOption[] = AUDIO_FORMATS;
  captionFormats: Option[] = CAPTION_FORMATS;
  thumbnailFormats: Option[] = THUMBNAIL_FORMATS;
  formatOptions: Option[] = [];
  qualities!: Quality[];
  downloadType: string;
  codec: string;
  quality: string;
  format: string;
  folder!: string;
  customNamePrefix!: string;
  autoStart: boolean;
  playlistItemLimit!: number;
  splitByChapters: boolean;
  chapterTemplate: string;
  subtitleLanguage: string;
  subtitleMode: string;
  addInProgress = false;
  cancelRequested = false;
  hasCookies = false;
  cookieUploadInProgress = false;
  themes: Theme[] = Themes;
  activeTheme: Theme | undefined;
  customDirs$!: Observable<string[]>;
  showBatchPanel = false; 
  batchImportModalOpen = false;
  batchImportText = '';
  batchImportStatus = '';
  importInProgress = false;
  cancelImportFlag = false;
  ytDlpOptionsUpdateTime: string | null = null;
  ytDlpVersion: string | null = null;
  metubeVersion: string | null = null;
  isAdvancedOpen = false;
  hasharrEnabled = false;
  hasharrUrl = 'http://hasharr:9995';
  hasharrServiceID = 1;
  hasharrTimeoutSec = 20;
  hasharrSettingsStatus = '';
  sortAscending = false;
  expandedErrors: Set<string> = new Set<string>();
  cachedSortedDone: [string, Download][] = [];
  lastCopiedErrorId: string | null = null;
  private previousDownloadType = 'video';
  private selectionsByType: Record<string, {
    codec: string;
    format: string;
    quality: string;
    subtitleLanguage: string;
    subtitleMode: string;
  }> = {};
  private readonly selectionCookiePrefix = 'metube_selection_';
  private readonly settingsCookieExpiryDays = 3650;
  private lastFocusedElement: HTMLElement | null = null;
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
  hasCompletedDone = false;
  hasFailedDone = false;

  readonly queueMasterCheckbox = viewChild<SelectAllCheckboxComponent>('queueMasterCheckboxRef');
  readonly queueDelSelected = viewChild.required<ElementRef>('queueDelSelected');
  readonly queueDownloadSelected = viewChild.required<ElementRef>('queueDownloadSelected');
  readonly doneMasterCheckbox = viewChild<SelectAllCheckboxComponent>('doneMasterCheckboxRef');
  readonly doneDelSelected = viewChild.required<ElementRef>('doneDelSelected');
  readonly doneDownloadSelected = viewChild.required<ElementRef>('doneDownloadSelected');

  faTrashAlt = faTrashAlt;
  faCheckCircle = faCheckCircle;
  faTimesCircle = faTimesCircle;
  faRedoAlt = faRedoAlt;
  faSun = faSun;
  faMoon = faMoon;
  faCheck = faCheck;
  faCircleHalfStroke = faCircleHalfStroke;
  faDownload = faDownload;
  faExternalLinkAlt = faExternalLinkAlt;
  faFileImport = faFileImport;
  faFileExport = faFileExport;
  faCopy = faCopy;
  faGithub = faGithub;
  faClock = faClock;
  faTachometerAlt = faTachometerAlt;
  faSortAmountDown = faSortAmountDown;
  faSortAmountUp = faSortAmountUp;
  faChevronRight = faChevronRight;
  faChevronDown = faChevronDown;
  faUpload = faUpload;
  subtitleLanguages = [
    { id: 'en', text: 'English' },
    { id: 'ar', text: 'Arabic' },
    { id: 'bn', text: 'Bengali' },
    { id: 'bg', text: 'Bulgarian' },
    { id: 'ca', text: 'Catalan' },
    { id: 'cs', text: 'Czech' },
    { id: 'da', text: 'Danish' },
    { id: 'nl', text: 'Dutch' },
    { id: 'es', text: 'Spanish' },
    { id: 'et', text: 'Estonian' },
    { id: 'fi', text: 'Finnish' },
    { id: 'fr', text: 'French' },
    { id: 'de', text: 'German' },
    { id: 'el', text: 'Greek' },
    { id: 'he', text: 'Hebrew' },
    { id: 'hi', text: 'Hindi' },
    { id: 'hu', text: 'Hungarian' },
    { id: 'id', text: 'Indonesian' },
    { id: 'it', text: 'Italian' },
    { id: 'lt', text: 'Lithuanian' },
    { id: 'lv', text: 'Latvian' },
    { id: 'ms', text: 'Malay' },
    { id: 'no', text: 'Norwegian' },
    { id: 'pl', text: 'Polish' },
    { id: 'pt', text: 'Portuguese' },
    { id: 'pt-BR', text: 'Portuguese (Brazil)' },
    { id: 'ro', text: 'Romanian' },
    { id: 'ru', text: 'Russian' },
    { id: 'sk', text: 'Slovak' },
    { id: 'sl', text: 'Slovenian' },
    { id: 'sr', text: 'Serbian' },
    { id: 'sv', text: 'Swedish' },
    { id: 'ta', text: 'Tamil' },
    { id: 'te', text: 'Telugu' },
    { id: 'th', text: 'Thai' },
    { id: 'tr', text: 'Turkish' },
    { id: 'uk', text: 'Ukrainian' },
    { id: 'ur', text: 'Urdu' },
    { id: 'vi', text: 'Vietnamese' },
    { id: 'ja', text: 'Japanese' },
    { id: 'ko', text: 'Korean' },
    { id: 'zh-Hans', text: 'Chinese (Simplified)' },
    { id: 'zh-Hant', text: 'Chinese (Traditional)' },
  ];
  subtitleModes = [
    { id: 'prefer_manual', text: 'Prefer Manual' },
    { id: 'prefer_auto', text: 'Prefer Auto' },
    { id: 'manual_only', text: 'Manual Only' },
    { id: 'auto_only', text: 'Auto Only' },
  ];
  constructor() {
    this.downloadType = this.cookieService.get('metube_download_type') || 'video';
    this.codec = this.cookieService.get('metube_codec') || 'auto';
    this.format = this.cookieService.get('metube_format') || 'any';
    this.quality = this.cookieService.get('metube_quality') || 'best';
    this.autoStart = this.cookieService.get('metube_auto_start') !== 'false';
    this.splitByChapters = this.cookieService.get('metube_split_chapters') === 'true';
    // Will be set from backend configuration, use empty string as placeholder
    this.chapterTemplate = this.cookieService.get('metube_chapter_template') || '';
    this.subtitleLanguage = this.cookieService.get('metube_subtitle_language') || 'en';
    this.subtitleMode = this.cookieService.get('metube_subtitle_mode') || 'prefer_manual';
    const allowedDownloadTypes = new Set(this.downloadTypes.map(t => t.id));
    const allowedVideoCodecs = new Set(this.videoCodecs.map(c => c.id));
    if (!allowedDownloadTypes.has(this.downloadType)) {
      this.downloadType = 'video';
    }
    if (!allowedVideoCodecs.has(this.codec)) {
      this.codec = 'auto';
    }
    const allowedSubtitleModes = new Set(this.subtitleModes.map(mode => mode.id));
    if (!allowedSubtitleModes.has(this.subtitleMode)) {
      this.subtitleMode = 'prefer_manual';
    }
    this.loadSavedSelections();
    this.restoreSelection(this.downloadType);
    this.normalizeSelectionsForType();
    this.setQualities();
    this.refreshFormatOptions();
    this.previousDownloadType = this.downloadType;
    this.saveSelection(this.downloadType);
    this.sortAscending = this.cookieService.get('metube_sort_ascending') === 'true';

    this.activeTheme = this.getPreferredTheme(this.cookieService);

    // Subscribe to download updates
    this.downloads.queueChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.updateMetrics();
      this.cdr.markForCheck();
    });
    this.downloads.doneChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.updateMetrics();
      this.rebuildSortedDone();
      this.cdr.markForCheck();
    });
    // Subscribe to real-time updates (throttled to reduce CPU on large queues).
    this.downloads.updated
    .pipe(
      auditTime(200),
      takeUntilDestroyed(this.destroyRef)
    )
    .subscribe(() => {
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
    this.loadHasharrSettings();
    this.getYtdlOptionsUpdateTime();
    this.customDirs$ = this.getMatchingCustomDir();
    this.setTheme(this.activeTheme!);

    this.colorSchemeMediaQuery.addEventListener('change', this.onColorSchemeChanged);
  }

  loadHasharrSettings() {
    this.downloads.getHasharrSettings().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        if (!data || typeof data !== 'object' || ('status' in data && data.status === 'error')) {
          this.hasharrSettingsStatus = 'Unable to load hasharr settings.';
          this.cdr.markForCheck();
          return;
        }
        const settings = data as HasharrSettings;
        this.hasharrEnabled = !!settings.enabled;
        this.hasharrUrl = String(settings.url || 'http://hasharr:9995');
        this.hasharrServiceID = Math.max(1, Number(settings.service_id || 1));
        this.hasharrTimeoutSec = Math.max(1, Number(settings.timeout_sec || 20));
        this.hasharrSettingsStatus = '';
        this.cdr.markForCheck();
      },
      error: () => {
        this.hasharrSettingsStatus = 'Unable to load hasharr settings.';
        this.cdr.markForCheck();
      },
    });
  }

  saveHasharrSettings() {
    const payload: HasharrSettings = {
      enabled: !!this.hasharrEnabled,
      url: String(this.hasharrUrl || '').trim(),
      service_id: Math.max(1, Number(this.hasharrServiceID || 1)),
      timeout_sec: Math.max(1, Number(this.hasharrTimeoutSec || 20)),
    };
    if (!payload.url) {
      this.hasharrSettingsStatus = 'Hasharr URL is required.';
      this.cdr.markForCheck();
      return;
    }
    this.downloads.saveHasharrSettings(payload).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (out) => {
        if (out && typeof out === 'object' && 'status' in out && out.status === 'ok') {
          this.hasharrSettingsStatus = 'Hasharr settings saved.';
        } else {
          this.hasharrSettingsStatus = 'Failed to save hasharr settings.';
        }
        this.cdr.markForCheck();
      },
      error: () => {
        this.hasharrSettingsStatus = 'Failed to save hasharr settings.';
        this.cdr.markForCheck();
      },
    });
  }

  ngAfterViewInit() {
    this.downloads.queueChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.queueMasterCheckbox()?.selectionChanged();
      this.cdr.markForCheck();
    });
    this.downloads.doneChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.doneMasterCheckbox()?.selectionChanged();
      this.updateDoneActionButtons();
      this.cdr.markForCheck();
    });
    // Initialize action button states for already-loaded entries.
    this.updateDoneActionButtons();
    this.fetchVersionInfo();
  }

  ngOnDestroy() {
    this.colorSchemeMediaQuery.removeEventListener('change', this.onColorSchemeChanged);
  }

  // workaround to allow fetching of Map values in the order they were inserted
  //  https://github.com/angular/angular/issues/31420
    
   
      
  asIsOrder() {
    return 1;
  }

  qualityChanged() {
    this.cookieService.set('metube_quality', this.quality, { expires: this.settingsCookieExpiryDays });
    this.saveSelection(this.downloadType);
    // Re-trigger custom directory change
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
  }

  downloadTypeChanged() {
    this.saveSelection(this.previousDownloadType);
    this.restoreSelection(this.downloadType);
    this.cookieService.set('metube_download_type', this.downloadType, { expires: this.settingsCookieExpiryDays });
    this.normalizeSelectionsForType(false);
    this.setQualities();
    this.refreshFormatOptions();
    this.saveSelection(this.downloadType);
    this.previousDownloadType = this.downloadType;
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
  }

  codecChanged() {
    this.cookieService.set('metube_codec', this.codec, { expires: this.settingsCookieExpiryDays });
    this.saveSelection(this.downloadType);
  }

  showAdvanced() {
    return this.downloads.configuration['CUSTOM_DIRS'];
  }

  allowCustomDir(tag: string) {
    if (this.downloads.configuration['CREATE_CUSTOM_DIRS']) {
      return tag;
    }
    return false;
  }

  isAudioType() {
    return this.downloadType === 'audio';
  }

  getMatchingCustomDir() : Observable<string[]> {
    return this.downloads.customDirsChanged.asObservable().pipe(
       // eslint-disable-next-line @typescript-eslint/no-explicit-any
      map((output: any) => {
        // Keep logic consistent with app/ytdl.py
        if (this.isAudioType()) {
          console.debug("Showing audio-specific download directories");
          return output["audio_download_dir"];
        } else {
          console.debug("Showing default download directories");
          return output["download_dir"];
        }
      }),
      distinctUntilChanged((prev, curr) => JSON.stringify(prev) === JSON.stringify(curr))
    );
  }

  getYtdlOptionsUpdateTime() {
    this.downloads.ytdlOptionsChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
       // eslint-disable-next-line @typescript-eslint/no-explicit-any
      next: (data:any) => {
        if (data['success']){
          const date = new Date(data['update_time'] * 1000);
          this.ytDlpOptionsUpdateTime=date.toLocaleString();
        }else{
          alert("Error reload yt-dlp options: "+data['msg']);
        }
        this.cdr.markForCheck();
      }
    });
  }
  getConfiguration() {
    this.downloads.configurationChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
       // eslint-disable-next-line @typescript-eslint/no-explicit-any
      next: (config: any) => {
        const playlistItemLimit = config['DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT'];
        if (playlistItemLimit !== '0') {
          this.playlistItemLimit = playlistItemLimit;
        }
        // Set chapter template from backend config if not already set by cookie
        if (!this.chapterTemplate) {
          this.chapterTemplate = config['OUTPUT_TEMPLATE_CHAPTER'];
        }
        this.cdr.markForCheck();
      }
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
    this.cookieService.set('metube_theme', theme.id, { expires: this.settingsCookieExpiryDays });
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
    this.cookieService.set('metube_format', this.format, { expires: this.settingsCookieExpiryDays });
    this.setQualities();
    this.saveSelection(this.downloadType);
    // Re-trigger custom directory change
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
  }

  autoStartChanged() {
    this.cookieService.set('metube_auto_start', this.autoStart ? 'true' : 'false', { expires: this.settingsCookieExpiryDays });
  }

  splitByChaptersChanged() {
    this.cookieService.set('metube_split_chapters', this.splitByChapters ? 'true' : 'false', { expires: this.settingsCookieExpiryDays });
  }

  chapterTemplateChanged() {
    // Restore default if template is cleared - get from configuration
    if (!this.chapterTemplate || this.chapterTemplate.trim() === '') {
      const configuredTemplate = this.downloads.configuration['OUTPUT_TEMPLATE_CHAPTER'];
      this.chapterTemplate = typeof configuredTemplate === 'string' ? configuredTemplate : '';
    }
    this.cookieService.set('metube_chapter_template', this.chapterTemplate, { expires: this.settingsCookieExpiryDays });
  }

  subtitleLanguageChanged() {
    this.cookieService.set('metube_subtitle_language', this.subtitleLanguage, { expires: this.settingsCookieExpiryDays });
    this.saveSelection(this.downloadType);
  }

  subtitleModeChanged() {
    this.cookieService.set('metube_subtitle_mode', this.subtitleMode, { expires: this.settingsCookieExpiryDays });
    this.saveSelection(this.downloadType);
  }

  isVideoType() {
    return this.downloadType === 'video';
  }

  formatQualityLabel(download: Download): string {
    if (download.download_type === 'captions' || download.download_type === 'thumbnail') {
      return '-';
    }
    const q = download.quality;
    if (!q) return '';
    if (/^\d+$/.test(q) && download.download_type === 'audio') return `${q} kbps`;
    if (/^\d+$/.test(q)) return `${q}p`;
    return q.charAt(0).toUpperCase() + q.slice(1);
  }

  downloadTypeLabel(download: Download): string {
    const type = download.download_type || 'video';
    return type.charAt(0).toUpperCase() + type.slice(1);
  }

  formatCodecLabel(download: Download): string {
    if (download.download_type !== 'video') {
      const format = (download.format || '').toUpperCase();
      return format || '-';
    }
    const codec = download.codec;
    if (!codec || codec === 'auto') return 'Auto';
    return this.videoCodecs.find(c => c.id === codec)?.text ?? codec;
  }

  queueSelectionChanged(checked: number) {
    this.queueDelSelected().nativeElement.disabled = checked == 0;
    this.queueDownloadSelected().nativeElement.disabled = checked == 0;
  }

  doneSelectionChanged(checked: number) {
    this.doneDelSelected().nativeElement.disabled = checked == 0;
    this.doneDownloadSelected().nativeElement.disabled = checked == 0;
  }

  private updateDoneActionButtons() {
    let completed = 0;
    let failed = 0;
    this.downloads.done.forEach((download) => {
      const isFailed = download.status === 'error';
      const isCompleted = !isFailed && (
        download.status === 'finished' ||
        download.status === 'completed' ||
        Boolean(download.filename)
      );
      if (isCompleted) {
        completed++;
      } else if (isFailed) {
        failed++;
      }
    });
    this.hasCompletedDone = completed > 0;
    this.hasFailedDone = failed > 0;
  }

  setQualities() {
    if (this.downloadType === 'video') {
      this.qualities = this.format === 'ios'
        ? [{ id: 'best', text: 'Best' }]
        : VIDEO_QUALITIES;
    } else if (this.downloadType === 'audio') {
      const selectedFormat = this.audioFormats.find(el => el.id === this.format);
      this.qualities = selectedFormat ? selectedFormat.qualities : [{ id: 'best', text: 'Best' }];
    } else {
      this.qualities = [{ id: 'best', text: 'Best' }];
    }
    const exists = this.qualities.find(el => el.id === this.quality);
    this.quality = exists ? this.quality : 'best';
  }

  refreshFormatOptions() {
    if (this.downloadType === 'video') {
      this.formatOptions = this.videoFormats;
      return;
    }
    if (this.downloadType === 'audio') {
      this.formatOptions = this.audioFormats;
      return;
    }
    if (this.downloadType === 'captions') {
      this.formatOptions = this.captionFormats;
      return;
    }
    this.formatOptions = this.thumbnailFormats;
  }

  showCodecSelector() {
    return this.downloadType === 'video';
  }

  showFormatSelector() {
    return this.downloadType !== 'thumbnail';
  }

  showQualitySelector() {
    if (this.downloadType === 'video') {
      return this.format !== 'ios';
    }
    return this.downloadType === 'audio';
  }

  private normalizeSelectionsForType(resetForTypeChange = false) {
    if (this.downloadType === 'video') {
      const allowedFormats = new Set(this.videoFormats.map(f => f.id));
      if (resetForTypeChange || !allowedFormats.has(this.format)) {
        this.format = 'any';
      }
      const allowedCodecs = new Set(this.videoCodecs.map(c => c.id));
      if (resetForTypeChange || !allowedCodecs.has(this.codec)) {
        this.codec = 'auto';
      }
    } else if (this.downloadType === 'audio') {
      const allowedFormats = new Set(this.audioFormats.map(f => f.id));
      if (resetForTypeChange || !allowedFormats.has(this.format)) {
        this.format = this.audioFormats[0].id;
      }
    } else if (this.downloadType === 'captions') {
      const allowedFormats = new Set(this.captionFormats.map(f => f.id));
      if (resetForTypeChange || !allowedFormats.has(this.format)) {
        this.format = 'srt';
      }
      this.quality = 'best';
    } else {
      this.format = 'jpg';
      this.quality = 'best';
    }
    this.cookieService.set('metube_format', this.format, { expires: this.settingsCookieExpiryDays });
    this.cookieService.set('metube_codec', this.codec, { expires: this.settingsCookieExpiryDays });
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
    this.cookieService.set(
      this.selectionCookiePrefix + type,
      JSON.stringify(selection),
      { expires: this.settingsCookieExpiryDays }
    );
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
      const key = this.selectionCookiePrefix + type;
      if (!this.cookieService.check(key)) continue;
      try {
        const raw = this.cookieService.get(key);
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
          this.selectionsByType[type] = {
            codec: String(parsed.codec ?? 'auto'),
            format: String(parsed.format ?? ''),
            quality: String(parsed.quality ?? 'best'),
            subtitleLanguage: String(parsed.subtitleLanguage ?? 'en'),
            subtitleMode: String(parsed.subtitleMode ?? 'prefer_manual'),
          };
        }
      } catch {
        // Ignore malformed cookie values.
      }
    }
  }

  private buildAddPayload(overrides: Partial<AddDownloadPayload> = {}): AddDownloadPayload {
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
      chapterTemplate: overrides.chapterTemplate ?? this.chapterTemplate,
      subtitleLanguage: overrides.subtitleLanguage ?? this.subtitleLanguage,
      subtitleMode: overrides.subtitleMode ?? this.subtitleMode,
    };
  }

  addDownload(overrides: Partial<AddDownloadPayload> = {}) {
    const payload = this.buildAddPayload(overrides);

    // Validate chapter template if chapter splitting is enabled
    if (payload.splitByChapters && !payload.chapterTemplate.includes('%(section_number)')) {
      alert('Chapter template must include %(section_number)');
      return;
    }

    console.debug('Downloading:', payload);
    this.addInProgress = true;
    this.cancelRequested = false;
    this.downloads.add(payload).subscribe((status: Status) => {
      if (status.status === 'error' && !this.cancelRequested) {
        alert(`Error adding URL: ${status.msg}`);
      } else if (status.status !== 'error') {
        this.addUrl = '';
      }
      this.addInProgress = false;
      this.cancelRequested = false;
    });
  }

  cancelAdding() {
    this.cancelRequested = true;
    this.downloads.cancelAdd().subscribe({
      error: (err) => {
        console.error('Failed to cancel adding:', err?.message || err);
      }
    });
  }

  downloadItemByKey(id: string) {
    this.downloads.startById([id]).subscribe();
  }

  retryDownload(key: string, download: Download) {
    this.addDownload({
      url: download.url,
      downloadType: download.download_type,
      codec: download.codec,
      quality: download.quality,
      format: download.format,
      folder: download.folder,
      customNamePrefix: download.custom_name_prefix,
      playlistItemLimit: download.playlist_item_limit,
      autoStart: true,
      splitByChapters: download.split_by_chapters,
      chapterTemplate: download.chapter_template,
      subtitleLanguage: download.subtitle_language,
      subtitleMode: download.subtitle_mode,
    });
    this.downloads.delById('done', [key]).subscribe();
  }

  delDownload(where: State, id: string) {
    this.downloads.delById(where, [id]).subscribe();
  }

  startSelectedDownloads(where: State){
    this.downloads.startByFilter(where, dl => !!dl.checked).subscribe();
  }

  delSelectedDownloads(where: State) {
    this.downloads.delByFilter(where, dl => !!dl.checked).subscribe();
  }

  clearCompletedDownloads() {
    this.downloads.delByFilter('done', dl => dl.status === 'finished').subscribe();
  }

  clearFailedDownloads() {
    this.downloads.delByFilter('done', dl => dl.status === 'error').subscribe();
  }

  retryFailedDownloads() {
    this.downloads.done.forEach((dl, key) => {
      if (dl.status === 'error') {
        this.retryDownload(key, dl);
      }
    });
  }

  downloadSelectedFiles() {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    this.downloads.done.forEach((dl, _) => {
      if (dl.status === 'finished' && dl.checked) {
        const link = document.createElement('a');
        link.href = this.buildDownloadLink(dl);
        link.setAttribute('download', dl.filename);
        link.setAttribute('target', '_self');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    });
  }

  buildDownloadLink(download: Download) {
    let baseDir = this.downloads.configuration["PUBLIC_HOST_URL"];
    if (download.download_type === 'audio' || download.filename.endsWith('.mp3')) {
      baseDir = this.downloads.configuration["PUBLIC_HOST_AUDIO_URL"];
    }

    if (download.folder) {
      baseDir += this.encodeFolderPath(download.folder);
    }

    return baseDir + encodeURIComponent(download.filename);
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
    if (download.download_type === 'audio' || chapterFilename.endsWith('.mp3')) {
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

  isNumber(event: KeyboardEvent) {
    const allowedControlKeys = ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'Tab', 'Home', 'End'];
    if (allowedControlKeys.includes(event.key)) {
      return;
    }

    if (!/^[0-9]$/.test(event.key)) {
      event.preventDefault();
    }
  }

  // Toggle inline batch panel (if you want to use an inline panel for export; not used for import modal)
  toggleBatchPanel(): void {
    this.showBatchPanel = !this.showBatchPanel;
  }

  // Open the Batch Import modal
  openBatchImportModal(): void {
    this.lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    this.batchImportModalOpen = true;
    this.batchImportText = '';
    this.batchImportStatus = '';
    this.importInProgress = false;
    this.cancelImportFlag = false;
    setTimeout(() => {
      const textarea = document.getElementById('batch-import-textarea');
      if (textarea instanceof HTMLTextAreaElement) {
        textarea.focus();
      }
    }, 0);
  }

  // Close the Batch Import modal
  closeBatchImportModal(): void {
    this.batchImportModalOpen = false;
    this.lastFocusedElement?.focus();
  }

  // Start importing URLs from the batch modal textarea
  startBatchImport(): void {
    const urls = this.batchImportText
      .split(/\r?\n/)
      .map(url => url.trim())
      .filter(url => url.length > 0);
    if (urls.length === 0) {
      alert('No valid URLs found.');
      return;
    }
    this.importInProgress = true;
    this.cancelImportFlag = false;
    this.batchImportStatus = `Starting to import ${urls.length} URLs...`;
    let index = 0;
    const delayBetween = 1000;
    const processNext = () => {
      if (this.cancelImportFlag) {
        this.batchImportStatus = `Import cancelled after ${index} of ${urls.length} URLs.`;
        this.importInProgress = false;
        return;
      }
      if (index >= urls.length) {
        this.batchImportStatus = `Finished importing ${urls.length} URLs.`;
        this.importInProgress = false;
        return;
      }
      const url = urls[index];
      this.batchImportStatus = `Importing URL ${index + 1} of ${urls.length}: ${url}`;
      // Pass current selection options to backend
      this.downloads.add(this.buildAddPayload({ url }))
        .subscribe({
          next: (status: Status) => {
            if (status.status === 'error') {
              alert(`Error adding URL ${url}: ${status.msg}`);
            }
            index++;
            setTimeout(processNext, delayBetween);
          },
          error: (err) => {
            console.error(`Error importing URL ${url}:`, err);
            index++;
            setTimeout(processNext, delayBetween);
          }
        });
    };
    processNext();
  }

  // Cancel the batch import process
  cancelBatchImport(): void {
    if (this.importInProgress) {
      this.cancelImportFlag = true;
      this.batchImportStatus += ' Cancelling...';
    }
  }

  // Export URLs based on filter: 'pending', 'completed', 'failed', or 'all'
  exportBatchUrls(filter: 'pending' | 'completed' | 'failed' | 'all'): void {
    let urls: string[];
    if (filter === 'pending') {
      urls = Array.from(this.downloads.queue.values()).map(dl => dl.url);
    } else if (filter === 'completed') {
      // Only finished downloads in the "done" Map
      urls = Array.from(this.downloads.done.values()).filter(dl => dl.status === 'finished').map(dl => dl.url);
    } else if (filter === 'failed') {
      // Only error downloads from the "done" Map
      urls = Array.from(this.downloads.done.values()).filter(dl => dl.status === 'error').map(dl => dl.url);
    } else {
      // All: pending + both finished and error in done
      urls = [
        ...Array.from(this.downloads.queue.values()).map(dl => dl.url),
        ...Array.from(this.downloads.done.values()).map(dl => dl.url)
      ];
    }
    if (!urls.length) {
      alert('No URLs found for the selected filter.');
      return;
    }
    const content = urls.join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = 'metube_urls.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(downloadUrl);
  }

  // Copy URLs to clipboard based on filter: 'pending', 'completed', 'failed', or 'all'
  copyBatchUrls(filter: 'pending' | 'completed' | 'failed' | 'all'): void {
    let urls: string[];
    if (filter === 'pending') {
      urls = Array.from(this.downloads.queue.values()).map(dl => dl.url);
    } else if (filter === 'completed') {
      urls = Array.from(this.downloads.done.values()).filter(dl => dl.status === 'finished').map(dl => dl.url);
    } else if (filter === 'failed') {
      urls = Array.from(this.downloads.done.values()).filter(dl => dl.status === 'error').map(dl => dl.url);
    } else {
      urls = [
        ...Array.from(this.downloads.queue.values()).map(dl => dl.url),
        ...Array.from(this.downloads.done.values()).map(dl => dl.url)
      ];
    }
    if (!urls.length) {
      alert('No URLs found for the selected filter.');
      return;
    }
    const content = urls.join('\n');
    navigator.clipboard.writeText(content)
      .then(() => alert('URLs copied to clipboard.'))
      .catch(() => alert('Failed to copy URLs.'));
  }

  fetchVersionInfo(): void {
    // eslint-disable-next-line no-useless-escape    
    const baseUrl = `${window.location.origin}${window.location.pathname.replace(/\/[^\/]*$/, '/')}`;
    const versionUrl = `${baseUrl}version`;
    this.http.get<{ 'yt-dlp': string, version: string }>(versionUrl)
      .subscribe({
        next: (data) => {
          this.ytDlpVersion = data['yt-dlp'];
          this.metubeVersion = data.version;
        },
        error: () => {
          this.ytDlpVersion = null;
          this.metubeVersion = null;
        }
      });
  }

  toggleAdvanced() {
    this.isAdvancedOpen = !this.isAdvancedOpen;
  }

  toggleSortOrder() {
    this.sortAscending = !this.sortAscending;
    this.cookieService.set('metube_sort_ascending', this.sortAscending ? 'true' : 'false', { expires: this.settingsCookieExpiryDays });
    this.rebuildSortedDone();
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
      setTimeout(() => { this.lastCopiedErrorId = null; }, 1500);
    };
    const fail = (err?: unknown) => {
      console.error('Clipboard write failed:', err);
      alert('Failed to copy to clipboard. Your browser may require HTTPS for clipboard access.');
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

  onCookieFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;
    this.cookieUploadInProgress = true;
    this.downloads.uploadCookies(input.files[0]).subscribe({
      next: (response) => {
        if (response?.status === 'ok') {
          this.hasCookies = true;
        } else {
          this.refreshCookieStatus();
          alert(`Error uploading cookies: ${this.formatErrorMessage(response?.msg)}`);
        }
        this.cookieUploadInProgress = false;
        input.value = '';
      },
      error: () => {
        this.refreshCookieStatus();
        this.cookieUploadInProgress = false;
        input.value = '';
        alert('Error uploading cookies.');
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
        alert(`Error deleting cookies: ${this.formatErrorMessage(response?.msg)}`);
      },
      error: () => {
        this.refreshCookieStatus();
        alert('Error deleting cookies.');
      }
    });
  }

  private refreshCookieStatus() {
    this.downloads.getCookieStatus().subscribe(data => {
      this.hasCookies = !!(data && typeof data === 'object' && 'has_cookies' in data && data.has_cookies);
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
      } else if (download.status === 'preparing') {
        active++;
      } else if (download.status === 'pending') {
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
