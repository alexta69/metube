import { TestBed, ComponentFixture } from '@angular/core/testing';
import { FormsModule } from '@angular/forms';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { NgbModule } from '@ng-bootstrap/ng-bootstrap';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { NgSelectModule } from '@ng-select/ng-select';
import { AppComponent } from './app.component';
import { DownloadsService } from './downloads.service';
import { CookieService } from 'ngx-cookie-service';
import { MeTubeSocket } from './metube-socket';
import { of } from 'rxjs';
import { 
  MockSpeedPipe, 
  MockEtaPipe, 
  MockFileSizePipe,
  MockMasterCheckboxComponent,
  MockSlaveCheckboxComponent 
} from './test-utils';

describe('Batch Import Functionality', () => {
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;
  let downloadsServiceSpy: jasmine.SpyObj<DownloadsService>;
  let cookieServiceSpy: jasmine.SpyObj<CookieService>;
  let socketSpy: jasmine.SpyObj<MeTubeSocket>;

  beforeEach(async () => {
    const downloadsSpy = jasmine.createSpyObj('DownloadsService', ['add'], {
      loading: false,
      queue: new Map(),
      done: new Map(),
      queueChanged: of(null),
      doneChanged: of(null),
      updated: of(null),
      configurationChanged: of({}),
      customDirsChanged: of({ download_dir: [], audio_download_dir: [] }),
      ytdlOptionsChanged: of({}),
      configuration: {}
    });
    const cookieSpy = jasmine.createSpyObj('CookieService', ['get', 'set', 'check']);
    const metubeSocketSpy = jasmine.createSpyObj('MeTubeSocket', ['fromEvent']);

    await TestBed.configureTestingModule({
      declarations: [
        AppComponent,
        MockSpeedPipe,
        MockEtaPipe,
        MockFileSizePipe,
        MockMasterCheckboxComponent,
        MockSlaveCheckboxComponent
      ],
      imports: [
        FormsModule,
        HttpClientTestingModule,
        NgbModule,
        FontAwesomeModule,
        NgSelectModule
      ],
      providers: [
        { provide: DownloadsService, useValue: downloadsSpy },
        { provide: CookieService, useValue: cookieSpy },
        { provide: MeTubeSocket, useValue: metubeSocketSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    component = fixture.componentInstance;
    downloadsServiceSpy = TestBed.inject(DownloadsService) as jasmine.SpyObj<DownloadsService>;
    cookieServiceSpy = TestBed.inject(CookieService) as jasmine.SpyObj<CookieService>;
    socketSpy = TestBed.inject(MeTubeSocket) as jasmine.SpyObj<MeTubeSocket>;

    // Set up socket mock returns
    socketSpy.fromEvent.and.returnValue(of({}));
  });

  describe('Core Batch Import Logic', () => {
    it('should create component successfully', () => {
      expect(component).toBeTruthy();
    });

    it('should initialize batch import properties', () => {
      expect(component.batchImportModalOpen).toBe(false);
      expect(component.batchImportText).toBe('');
      expect(component.batchImportStatus).toBe('');
      expect(component.importInProgress).toBe(false);
      expect(component.cancelImportFlag).toBe(false);
      expect(component.urlValidationResults).toEqual({ valid: [], invalid: [], duplicates: [] });
      expect(component.parsedUrlCount).toBe(0);
    });

    it('should open batch import modal correctly', () => {
      component.openBatchImportModal();

      expect(component.batchImportModalOpen).toBe(true);
      expect(component.batchImportText).toBe('');
      expect(component.batchImportStatus).toBe('');
      expect(component.importInProgress).toBe(false);
      expect(component.cancelImportFlag).toBe(false);
      expect(component.urlValidationResults).toEqual({ valid: [], invalid: [], duplicates: [] });
      expect(component.parsedUrlCount).toBe(0);
    });

    it('should validate URLs correctly', () => {
      const testUrls = [
        'https://youtube.com/watch?v=test1',
        'https://youtube.com/watch?v=test1', // duplicate
        'invalid-url',
        'https://youtu.be/test2'
      ].join('\n');
      
      component.batchImportText = testUrls;
      component.validateBatchUrls();

      expect(component.parsedUrlCount).toBe(4);
      expect(component.urlValidationResults.valid).toEqual([
        'https://youtube.com/watch?v=test1',
        'https://youtu.be/test2'
      ]);
      expect(component.urlValidationResults.invalid).toEqual(['invalid-url']);
      expect(component.urlValidationResults.duplicates).toEqual(['https://youtube.com/watch?v=test1']);
    });

    it('should handle empty URL input', () => {
      component.batchImportText = '';
      component.validateBatchUrls();

      expect(component.parsedUrlCount).toBe(0);
      expect(component.urlValidationResults).toEqual({ valid: [], invalid: [], duplicates: [] });
    });

    it('should handle whitespace and empty lines', () => {
      component.batchImportText = '  https://youtube.com/test  \n\n  \nhttps://youtu.be/test2\n\n';
      component.validateBatchUrls();

      expect(component.parsedUrlCount).toBe(2);
      expect(component.urlValidationResults.valid).toEqual([
        'https://youtube.com/test',
        'https://youtu.be/test2'
      ]);
    });

    it('should reject invalid URL formats', () => {
      const invalidUrls = [
        'youtube.com/watch?v=test', // missing protocol
        'ftp://youtube.com/test', // wrong protocol
        'not-a-url',
        'just-text'
      ];
      
      component.batchImportText = invalidUrls.join('\n');
      component.validateBatchUrls();

      expect(component.urlValidationResults.valid).toEqual([]);
      expect(component.urlValidationResults.invalid).toEqual(invalidUrls);
    });
  });

  describe('Import Process Logic', () => {
    beforeEach(() => {
      downloadsServiceSpy.add.and.returnValue(of({ status: 'ok' }));
    });

    it('should not start import with no valid URLs', () => {
      component.batchImportText = 'invalid-url\nnot-a-url';
      spyOn(window, 'alert');
      
      component.startBatchImport();

      expect(window.alert).toHaveBeenCalledWith('No valid URLs found. Please check your URLs and try again.');
      expect(component.importInProgress).toBe(false);
    });

    it('should show confirmation dialog with mixed URLs', () => {
      component.batchImportText = 'https://youtube.com/test\ninvalid-url';
      spyOn(window, 'confirm').and.returnValue(false);
      
      component.startBatchImport();

      expect(window.confirm).toHaveBeenCalledWith('Found 1 invalid URLs that will be skipped. Continue with 1 valid URLs?');
      expect(component.importInProgress).toBe(false);
    });

    it('should start import with valid URLs only', () => {
      component.batchImportText = 'https://youtube.com/test1\nhttps://youtube.com/test2';
      
      component.startBatchImport();

      expect(component.importInProgress).toBe(true);
      expect(component.batchImportStatus).toBe('Starting to import 2 URLs...');
    });

    it('should handle cancellation correctly', () => {
      component.importInProgress = true;
      component.batchImportStatus = 'Importing...';
      
      component.cancelBatchImport();

      expect(component.cancelImportFlag).toBe(true);
      expect(component.batchImportStatus).toBe('Importing... Cancelling...');
    });
  });

  describe('URL Validation Edge Cases', () => {
    it('should handle large number of URLs', () => {
      const urls = Array.from({ length: 100 }, (_, i) => `https://youtube.com/watch?v=test${i}`);
      component.batchImportText = urls.join('\n');
      
      const startTime = performance.now();
      component.validateBatchUrls();
      const endTime = performance.now();
      
      expect(endTime - startTime).toBeLessThan(50); // Should be fast
      expect(component.urlValidationResults.valid.length).toBe(100);
      expect(component.parsedUrlCount).toBe(100);
    });

    it('should detect multiple duplicates correctly', () => {
      const duplicateUrl = 'https://youtube.com/watch?v=duplicate';
      const urls = [duplicateUrl, duplicateUrl, duplicateUrl, 'https://youtube.com/watch?v=unique'];
      component.batchImportText = urls.join('\n');
      
      component.validateBatchUrls();

      expect(component.urlValidationResults.valid.length).toBe(2); // duplicate + unique
      expect(component.urlValidationResults.duplicates).toEqual([duplicateUrl]);
    });
  });
});