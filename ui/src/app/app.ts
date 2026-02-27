import { AsyncPipe, KeyValuePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { AfterViewInit, Component, ElementRef, viewChild, inject, OnInit } from '@angular/core';
import { Observable, map, distinctUntilChanged } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { NgbModule } from '@ng-bootstrap/ng-bootstrap';
import { NgSelectModule } from '@ng-select/ng-select';  
import { faTrashAlt, faCheckCircle, faTimesCircle, faRedoAlt, faSun, faMoon, faCheck, faCircleHalfStroke, faDownload, faExternalLinkAlt, faFileImport, faFileExport, faCopy, faClock, faTachometerAlt } from '@fortawesome/free-solid-svg-icons';
import { faGithub } from '@fortawesome/free-brands-svg-icons';
import { CookieService } from 'ngx-cookie-service';
import { DownloadsService } from './services/downloads.service';
import { Themes } from './theme';
import { Download, Status, Theme , Quality, Format, Formats, State } from './interfaces';
import { EtaPipe, SpeedPipe, FileSizePipe } from './pipes';
import { MasterCheckboxComponent , SlaveCheckboxComponent} from './components/';

@Component({
  selector: 'app-root',
  imports: [
        FormsModule,
        KeyValuePipe,
        AsyncPipe,
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
  formats: Format[] = Formats;
  qualities!: Quality[];
  quality: string;
  format: string;
  folder!: string;
  customNamePrefix!: string;
  autoStart: boolean;
  playlistItemLimit!: number;
  splitByChapters: boolean;
  chapterTemplate: string;
  subtitleFormat: string;
  subtitleLanguage: string;
  subtitleMode: string;
  addInProgress = false;
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
  subtitleFormats = [
    { id: 'srt', text: 'SRT' },
    { id: 'txt', text: 'TXT (Text only)' },
    { id: 'vtt', text: 'VTT' },
    { id: 'ttml', text: 'TTML' }
  ];
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
    this.format = this.cookieService.get('metube_format') || 'any';
    // Needs to be set or qualities won't automatically be set
    this.setQualities()
    this.quality = this.cookieService.get('metube_quality') || 'best';
    this.autoStart = this.cookieService.get('metube_auto_start') !== 'false';
    this.splitByChapters = this.cookieService.get('metube_split_chapters') === 'true';
    // Will be set from backend configuration, use empty string as placeholder
    this.chapterTemplate = this.cookieService.get('metube_chapter_template') || '';
    this.subtitleFormat = this.cookieService.get('metube_subtitle_format') || 'srt';
    this.subtitleLanguage = this.cookieService.get('metube_subtitle_language') || 'en';
    this.subtitleMode = this.cookieService.get('metube_subtitle_mode') || 'prefer_manual';
    const allowedSubtitleFormats = new Set(this.subtitleFormats.map(fmt => fmt.id));
    const allowedSubtitleModes = new Set(this.subtitleModes.map(mode => mode.id));
    if (!allowedSubtitleFormats.has(this.subtitleFormat)) {
      this.subtitleFormat = 'srt';
    }
    if (!allowedSubtitleModes.has(this.subtitleMode)) {
      this.subtitleMode = 'prefer_manual';
    }

    this.activeTheme = this.getPreferredTheme(this.cookieService);

    // Subscribe to download updates
    this.downloads.queueChanged.subscribe(() => {
      this.updateMetrics();
    });
    this.downloads.doneChanged.subscribe(() => {
      this.updateMetrics();
    });
    // Subscribe to real-time updates
    this.downloads.updated.subscribe(() => {
      this.updateMetrics();
    });
  }

  ngOnInit() {
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
    // Re-trigger custom directory change
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
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
    return this.quality == 'audio' || this.format == 'mp3'  || this.format == 'm4a' || this.format == 'opus' || this.format == 'wav' || this.format == 'flac';
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
    // Updates to use qualities available
    this.setQualities()
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

  subtitleFormatChanged() {
    this.cookieService.set('metube_subtitle_format', this.subtitleFormat, { expires: 3650 });
  }

  subtitleLanguageChanged() {
    this.cookieService.set('metube_subtitle_language', this.subtitleLanguage, { expires: 3650 });
  }

  subtitleModeChanged() {
    this.cookieService.set('metube_subtitle_mode', this.subtitleMode, { expires: 3650 });
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
    // qualities for specific format
    const format = this.formats.find(el => el.id == this.format)
    if (format) {
      this.qualities = format.qualities
      const exists = this.qualities.find(el => el.id === this.quality)
      this.quality = exists ? this.quality : 'best'
  }
}

  addDownload(
    url?: string,
    quality?: string,
    format?: string,
    folder?: string,
    customNamePrefix?: string,
    playlistItemLimit?: number,
    autoStart?: boolean,
    splitByChapters?: boolean,
    chapterTemplate?: string,
    subtitleFormat?: string,
    subtitleLanguage?: string,
    subtitleMode?: string,
  ) {
    url = url ?? this.addUrl
    quality = quality ?? this.quality
    format = format ?? this.format
    folder = folder ?? this.folder
    customNamePrefix = customNamePrefix ?? this.customNamePrefix
    playlistItemLimit = playlistItemLimit ?? this.playlistItemLimit
    autoStart = autoStart ?? this.autoStart
    splitByChapters = splitByChapters ?? this.splitByChapters
    chapterTemplate = chapterTemplate ?? this.chapterTemplate
    subtitleFormat = subtitleFormat ?? this.subtitleFormat
    subtitleLanguage = subtitleLanguage ?? this.subtitleLanguage
    subtitleMode = subtitleMode ?? this.subtitleMode

    // Validate chapter template if chapter splitting is enabled
    if (splitByChapters && !chapterTemplate.includes('%(section_number)')) {
      alert('Chapter template must include %(section_number)');
      return;
    }

    console.debug('Downloading: url=' + url + ' quality=' + quality + ' format=' + format + ' folder=' + folder + ' customNamePrefix=' + customNamePrefix + ' playlistItemLimit=' + playlistItemLimit + ' autoStart=' + autoStart + ' splitByChapters=' + splitByChapters + ' chapterTemplate=' + chapterTemplate + ' subtitleFormat=' + subtitleFormat + ' subtitleLanguage=' + subtitleLanguage + ' subtitleMode=' + subtitleMode);
    this.addInProgress = true;
    this.downloads.add(url, quality, format, folder, customNamePrefix, playlistItemLimit, autoStart, splitByChapters, chapterTemplate, subtitleFormat, subtitleLanguage, subtitleMode).subscribe((status: Status) => {
      if (status.status === 'error') {
        alert(`Error adding URL: ${status.msg}`);
      } else {
        this.addUrl = '';
      }
      this.addInProgress = false;
    });
  }

  downloadItemByKey(id: string) {
    this.downloads.startById([id]).subscribe();
  }

  retryDownload(key: string, download: Download) {
    this.addDownload(
      download.url,
      download.quality,
      download.format,
      download.folder,
      download.custom_name_prefix,
      download.playlist_item_limit,
      true,
      download.split_by_chapters,
      download.chapter_template,
      download.subtitle_format,
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
    if (download.quality == 'audio' || download.filename.endsWith('.mp3')) {
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
    if (download.quality == 'audio' || chapterFilename.endsWith('.mp3')) {
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
      // Now pass the selected quality, format, folder, etc. to the add() method
      this.downloads.add(url, this.quality, this.format, this.folder, this.customNamePrefix,
        this.playlistItemLimit, this.autoStart, this.splitByChapters, this.chapterTemplate,
        this.subtitleFormat, this.subtitleLanguage, this.subtitleMode)
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
