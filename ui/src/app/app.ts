import { AsyncPipe, DatePipe, KeyValuePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { AfterViewInit, Component, ElementRef, viewChild, inject, OnInit } from '@angular/core';
import { Observable, map, distinctUntilChanged } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { NgbModule } from '@ng-bootstrap/ng-bootstrap';
import { NgSelectModule } from '@ng-select/ng-select';  
import { faTrashAlt, faCheckCircle, faTimesCircle, faRedoAlt, faSun, faMoon, faCheck, faCircleHalfStroke, faDownload, faExternalLinkAlt, faFileImport, faFileExport, faCopy, faClock, faTachometerAlt, faSortAmountDown, faSortAmountUp, faChevronRight, faChevronDown, faUpload } from '@fortawesome/free-solid-svg-icons';
import { faGithub } from '@fortawesome/free-brands-svg-icons';
import { CookieService } from 'ngx-cookie-service';
import { DownloadsService } from './services/downloads.service';
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
import { MasterCheckboxComponent , SlaveCheckboxComponent} from './components/';

@Component({
  selector: 'app-root',
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
        MasterCheckboxComponent,
        SlaveCheckboxComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.sass',
})
export class App implements AfterViewInit, OnInit {
  downloads = inject(DownloadsService);
  private cookieService = inject(CookieService);
  private http = inject(HttpClient);

  addUrl!: string;
  downloadTypes: Option[] = DOWNLOAD_TYPES;
  videoCodecs: Option[] = VIDEO_CODECS;
  videoFormats: Option[] = VIDEO_FORMATS;
  audioFormats: AudioFormatOption[] = AUDIO_FORMATS;
  captionFormats: Option[] = CAPTION_FORMATS;
  thumbnailFormats: Option[] = THUMBNAIL_FORMATS;
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

  // Download metrics
  activeDownloads = 0;
  queuedDownloads = 0;
  completedDownloads = 0;
  failedDownloads = 0;
  totalSpeed = 0;

  readonly queueMasterCheckbox = viewChild<MasterCheckboxComponent>('queueMasterCheckboxRef');
  readonly queueDelSelected = viewChild.required<ElementRef>('queueDelSelected');
  readonly queueDownloadSelected = viewChild.required<ElementRef>('queueDownloadSelected');
  readonly doneMasterCheckbox = viewChild<MasterCheckboxComponent>('doneMasterCheckboxRef');
  readonly doneDelSelected = viewChild.required<ElementRef>('doneDelSelected');
  readonly doneClearCompleted = viewChild.required<ElementRef>('doneClearCompleted');
  readonly doneClearFailed = viewChild.required<ElementRef>('doneClearFailed');
  readonly doneRetryFailed = viewChild.required<ElementRef>('doneRetryFailed');
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
    this.previousDownloadType = this.downloadType;
    this.saveSelection(this.downloadType);
    this.sortAscending = this.cookieService.get('metube_sort_ascending') === 'true';

    this.activeTheme = this.getPreferredTheme(this.cookieService);

    // Subscribe to download updates
    this.downloads.queueChanged.subscribe(() => {
      this.updateMetrics();
    });
    this.downloads.doneChanged.subscribe(() => {
      this.updateMetrics();
      this.rebuildSortedDone();
    });
    // Subscribe to real-time updates
    this.downloads.updated.subscribe(() => {
      this.updateMetrics();
    });
  }

  ngOnInit() {
    this.downloads.getCookieStatus().subscribe(data => {
      this.hasCookies = !!(data && typeof data === 'object' && 'has_cookies' in data && data.has_cookies);
    });
    this.getConfiguration();
    this.getYtdlOptionsUpdateTime();
    this.customDirs$ = this.getMatchingCustomDir();
    this.setTheme(this.activeTheme!);

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (this.activeTheme && this.activeTheme.id === 'auto') {
         this.setTheme(this.activeTheme);
      }
    });
  }

  ngAfterViewInit() {
    this.downloads.queueChanged.subscribe(() => {
      this.queueMasterCheckbox()?.selectionChanged();
    });
    this.downloads.doneChanged.subscribe(() => {
      this.doneMasterCheckbox()?.selectionChanged();
      let completed = 0, failed = 0;
      this.downloads.done.forEach(dl => {
        if (dl.status === 'finished')
          completed++;
        else if (dl.status === 'error')
          failed++;
      });
      this.doneClearCompleted().nativeElement.disabled = completed === 0;
      this.doneClearFailed().nativeElement.disabled = failed === 0;
      this.doneRetryFailed().nativeElement.disabled = failed === 0;
    });
    this.fetchVersionInfo();
  }

  // workaround to allow fetching of Map values in the order they were inserted
  //  https://github.com/angular/angular/issues/31420
    
   
      
  asIsOrder() {
    return 1;
  }

  qualityChanged() {
    this.cookieService.set('metube_quality', this.quality, { expires: 3650 });
    this.saveSelection(this.downloadType);
    // Re-trigger custom directory change
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
  }

  downloadTypeChanged() {
    this.saveSelection(this.previousDownloadType);
    this.restoreSelection(this.downloadType);
    this.cookieService.set('metube_download_type', this.downloadType, { expires: 3650 });
    this.normalizeSelectionsForType(false);
    this.setQualities();
    this.saveSelection(this.downloadType);
    this.previousDownloadType = this.downloadType;
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
  }

  codecChanged() {
    this.cookieService.set('metube_codec', this.codec, { expires: 3650 });
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
    this.downloads.ytdlOptionsChanged.subscribe({
       // eslint-disable-next-line @typescript-eslint/no-explicit-any
      next: (data:any) => {
        if (data['success']){
          const date = new Date(data['update_time'] * 1000);
          this.ytDlpOptionsUpdateTime=date.toLocaleString();
        }else{
          alert("Error reload yt-dlp options: "+data['msg']);
        }
      }
    });
  }
  getConfiguration() {
    this.downloads.configurationChanged.subscribe({
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
    this.cookieService.set('metube_theme', theme.id, { expires: 3650 });
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
    this.cookieService.set('metube_format', this.format, { expires: 3650 });
    this.setQualities();
    this.saveSelection(this.downloadType);
    // Re-trigger custom directory change
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
  }

  autoStartChanged() {
    this.cookieService.set('metube_auto_start', this.autoStart ? 'true' : 'false', { expires: 3650 });
  }

  splitByChaptersChanged() {
    this.cookieService.set('metube_split_chapters', this.splitByChapters ? 'true' : 'false', { expires: 3650 });
  }

  chapterTemplateChanged() {
    // Restore default if template is cleared - get from configuration
    if (!this.chapterTemplate || this.chapterTemplate.trim() === '') {
      this.chapterTemplate = this.downloads.configuration['OUTPUT_TEMPLATE_CHAPTER'];
    }
    this.cookieService.set('metube_chapter_template', this.chapterTemplate, { expires: 3650 });
  }

  subtitleLanguageChanged() {
    this.cookieService.set('metube_subtitle_language', this.subtitleLanguage, { expires: 3650 });
    this.saveSelection(this.downloadType);
  }

  subtitleModeChanged() {
    this.cookieService.set('metube_subtitle_mode', this.subtitleMode, { expires: 3650 });
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

  getFormatOptions() {
    if (this.downloadType === 'video') {
      return this.videoFormats;
    }
    if (this.downloadType === 'audio') {
      return this.audioFormats;
    }
    if (this.downloadType === 'captions') {
      return this.captionFormats;
    }
    return this.thumbnailFormats;
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
    this.cookieService.set('metube_format', this.format, { expires: 3650 });
    this.cookieService.set('metube_codec', this.codec, { expires: 3650 });
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
      { expires: 3650 }
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

  addDownload(
    url?: string,
    downloadType?: string,
    codec?: string,
    quality?: string,
    format?: string,
    folder?: string,
    customNamePrefix?: string,
    playlistItemLimit?: number,
    autoStart?: boolean,
    splitByChapters?: boolean,
    chapterTemplate?: string,
    subtitleLanguage?: string,
    subtitleMode?: string,
  ) {
    url = url ?? this.addUrl
    downloadType = downloadType ?? this.downloadType
    codec = codec ?? this.codec
    quality = quality ?? this.quality
    format = format ?? this.format
    folder = folder ?? this.folder
    customNamePrefix = customNamePrefix ?? this.customNamePrefix
    playlistItemLimit = playlistItemLimit ?? this.playlistItemLimit
    autoStart = autoStart ?? this.autoStart
    splitByChapters = splitByChapters ?? this.splitByChapters
    chapterTemplate = chapterTemplate ?? this.chapterTemplate
    subtitleLanguage = subtitleLanguage ?? this.subtitleLanguage
    subtitleMode = subtitleMode ?? this.subtitleMode

    // Validate chapter template if chapter splitting is enabled
    if (splitByChapters && !chapterTemplate.includes('%(section_number)')) {
      alert('Chapter template must include %(section_number)');
      return;
    }

    console.debug('Downloading: url=' + url + ' downloadType=' + downloadType + ' codec=' + codec + ' quality=' + quality + ' format=' + format + ' folder=' + folder + ' customNamePrefix=' + customNamePrefix + ' playlistItemLimit=' + playlistItemLimit + ' autoStart=' + autoStart + ' splitByChapters=' + splitByChapters + ' chapterTemplate=' + chapterTemplate + ' subtitleLanguage=' + subtitleLanguage + ' subtitleMode=' + subtitleMode);
    this.addInProgress = true;
    this.cancelRequested = false;
    this.downloads.add(url, downloadType, codec, quality, format, folder, customNamePrefix, playlistItemLimit, autoStart, splitByChapters, chapterTemplate, subtitleLanguage, subtitleMode).subscribe((status: Status) => {
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
    this.addDownload(
      download.url,
      download.download_type,
      download.codec,
      download.quality,
      download.format,
      download.folder,
      download.custom_name_prefix,
      download.playlist_item_limit,
      true,
      download.split_by_chapters,
      download.chapter_template,
      download.subtitle_language,
      download.subtitle_mode,
    );
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
      baseDir += download.folder + '/';
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
      baseDir += download.folder + '/';
    }

    return baseDir + encodeURIComponent(chapterFilename);
  }

  getChapterFileName(filepath: string) {
    // Extract just the filename from the path
    const parts = filepath.split('/');
    return parts[parts.length - 1];
  }

  isNumber(event: KeyboardEvent) {
    const charCode = +event.code || event.keyCode;
    if (charCode > 31 && (charCode  < 48 || charCode > 57)) {
      event.preventDefault();
    }
  }

  // Toggle inline batch panel (if you want to use an inline panel for export; not used for import modal)
  toggleBatchPanel(): void {
    this.showBatchPanel = !this.showBatchPanel;
  }

  // Open the Batch Import modal
  openBatchImportModal(): void {
    this.batchImportModalOpen = true;
    this.batchImportText = '';
    this.batchImportStatus = '';
    this.importInProgress = false;
    this.cancelImportFlag = false;
  }

  // Close the Batch Import modal
  closeBatchImportModal(): void {
    this.batchImportModalOpen = false;
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
      this.downloads.add(url, this.downloadType, this.codec, this.quality, this.format, this.folder, this.customNamePrefix,
        this.playlistItemLimit, this.autoStart, this.splitByChapters, this.chapterTemplate,
        this.subtitleLanguage, this.subtitleMode)
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
    this.cookieService.set('metube_sort_ascending', this.sortAscending ? 'true' : 'false', { expires: 3650 });
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
    this.activeDownloads = Array.from(this.downloads.queue.values()).filter(d => d.status === 'downloading' || d.status === 'preparing').length;
    this.queuedDownloads = Array.from(this.downloads.queue.values()).filter(d => d.status === 'pending').length;
    this.completedDownloads = Array.from(this.downloads.done.values()).filter(d => d.status === 'finished').length;
    this.failedDownloads = Array.from(this.downloads.done.values()).filter(d => d.status === 'error').length;
    
    // Calculate total speed from downloading items
    const downloadingItems = Array.from(this.downloads.queue.values())
      .filter(d => d.status === 'downloading');
    
    this.totalSpeed = downloadingItems.reduce((total, item) => total + (item.speed || 0), 0);
  }
}
