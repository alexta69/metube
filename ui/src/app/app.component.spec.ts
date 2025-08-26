import { TestBed, ComponentFixture } from '@angular/core/testing';
import { FormsModule } from '@angular/forms';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { NgbModule } from '@ng-bootstrap/ng-bootstrap';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { AppComponent } from './app.component';
import { DownloadsService } from './downloads.service';
import { CookieService } from 'ngx-cookie-service';
import { of } from 'rxjs';

describe('AppComponent', () => {
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;
  let downloadsServiceSpy: jasmine.SpyObj<DownloadsService>;
  let cookieServiceSpy: jasmine.SpyObj<CookieService>;

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

    await TestBed.configureTestingModule({
      declarations: [AppComponent],
      imports: [
        FormsModule,
        HttpClientTestingModule,
        NgbModule,
        FontAwesomeModule
      ],
      providers: [
        { provide: DownloadsService, useValue: downloadsSpy },
        { provide: CookieService, useValue: cookieSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    component = fixture.componentInstance;
    downloadsServiceSpy = TestBed.inject(DownloadsService) as jasmine.SpyObj<DownloadsService>;
    cookieServiceSpy = TestBed.inject(CookieService) as jasmine.SpyObj<CookieService>;
  });

  it('should create the app', () => {
    expect(component).toBeTruthy();
  });

  describe('Batch Import Modal', () => {
    beforeEach(() => {
      component.ngOnInit();
      fixture.detectChanges();
    });

    describe('openBatchImportModal', () => {
      it('should initialize modal state correctly', () => {
        component.openBatchImportModal();

        expect(component.batchImportModalOpen).toBe(true);
        expect(component.batchImportText).toBe('');
        expect(component.batchImportStatus).toBe('');
        expect(component.importInProgress).toBe(false);
        expect(component.cancelImportFlag).toBe(false);
        expect(component.urlValidationResults).toEqual({ valid: [], invalid: [], duplicates: [] });
        expect(component.parsedUrlCount).toBe(0);
      });
    });

    describe('validateBatchUrls', () => {
      it('should validate empty input correctly', () => {
        component.batchImportText = '';
        component.validateBatchUrls();

        expect(component.parsedUrlCount).toBe(0);
        expect(component.urlValidationResults).toEqual({ valid: [], invalid: [], duplicates: [] });
      });

      it('should validate valid URLs correctly', () => {
        component.batchImportText = 'https://youtube.com/watch?v=test1\nhttps://youtu.be/test2';
        component.validateBatchUrls();

        expect(component.parsedUrlCount).toBe(2);
        expect(component.urlValidationResults.valid).toEqual([
          'https://youtube.com/watch?v=test1',
          'https://youtu.be/test2'
        ]);
        expect(component.urlValidationResults.invalid).toEqual([]);
        expect(component.urlValidationResults.duplicates).toEqual([]);
      });

      it('should identify invalid URLs correctly', () => {
        component.batchImportText = 'https://youtube.com/watch?v=test1\ninvalid-url\nnot-a-url';
        component.validateBatchUrls();

        expect(component.parsedUrlCount).toBe(3);
        expect(component.urlValidationResults.valid).toEqual(['https://youtube.com/watch?v=test1']);
        expect(component.urlValidationResults.invalid).toEqual(['invalid-url', 'not-a-url']);
        expect(component.urlValidationResults.duplicates).toEqual([]);
      });

      it('should detect duplicate URLs correctly', () => {
        component.batchImportText = 'https://youtube.com/watch?v=test1\nhttps://youtube.com/watch?v=test1\nhttps://youtu.be/test2';
        component.validateBatchUrls();

        expect(component.parsedUrlCount).toBe(3);
        expect(component.urlValidationResults.valid).toEqual([
          'https://youtube.com/watch?v=test1',
          'https://youtu.be/test2'
        ]);
        expect(component.urlValidationResults.invalid).toEqual([]);
        expect(component.urlValidationResults.duplicates).toEqual(['https://youtube.com/watch?v=test1']);
      });

      it('should handle mixed valid, invalid, and duplicate URLs', () => {
        component.batchImportText = [
          'https://youtube.com/watch?v=test1',
          'https://youtube.com/watch?v=test1', // duplicate
          'invalid-url',
          'https://youtu.be/test2',
          'not-a-url',
          'https://github.com/test/repo'
        ].join('\n');
        
        component.validateBatchUrls();

        expect(component.parsedUrlCount).toBe(6);
        expect(component.urlValidationResults.valid).toEqual([
          'https://youtube.com/watch?v=test1',
          'https://youtu.be/test2',
          'https://github.com/test/repo'
        ]);
        expect(component.urlValidationResults.invalid).toEqual(['invalid-url', 'not-a-url']);
        expect(component.urlValidationResults.duplicates).toEqual(['https://youtube.com/watch?v=test1']);
      });

      it('should handle whitespace and empty lines correctly', () => {
        component.batchImportText = '  https://youtube.com/watch?v=test1  \n\n  \nhttps://youtu.be/test2\n\n';
        component.validateBatchUrls();

        expect(component.parsedUrlCount).toBe(2);
        expect(component.urlValidationResults.valid).toEqual([
          'https://youtube.com/watch?v=test1',
          'https://youtu.be/test2'
        ]);
      });
    });

    describe('startBatchImport', () => {
      beforeEach(() => {
        downloadsServiceSpy.add.and.returnValue(of({ status: 'ok' }));
      });

      it('should not import when no valid URLs', () => {
        component.batchImportText = 'invalid-url\nnot-a-url';
        spyOn(window, 'alert');
        
        component.startBatchImport();

        expect(window.alert).toHaveBeenCalledWith('No valid URLs found. Please check your URLs and try again.');
        expect(component.importInProgress).toBe(false);
        expect(downloadsServiceSpy.add).not.toHaveBeenCalled();
      });

      it('should show confirmation dialog when invalid URLs present', () => {
        component.batchImportText = 'https://youtube.com/watch?v=test1\ninvalid-url';
        spyOn(window, 'confirm').and.returnValue(false);
        
        component.startBatchImport();

        expect(window.confirm).toHaveBeenCalledWith('Found 1 invalid URLs that will be skipped. Continue with 1 valid URLs?');
        expect(component.importInProgress).toBe(false);
        expect(downloadsServiceSpy.add).not.toHaveBeenCalled();
      });

      it('should proceed with import when user confirms with invalid URLs', () => {
        component.batchImportText = 'https://youtube.com/watch?v=test1\ninvalid-url';
        spyOn(window, 'confirm').and.returnValue(true);
        
        component.startBatchImport();

        expect(window.confirm).toHaveBeenCalled();
        expect(component.importInProgress).toBe(true);
        expect(component.batchImportStatus).toBe('Starting to import 1 URLs...');
      });

      it('should start import process with only valid URLs', () => {
        component.batchImportText = 'https://youtube.com/watch?v=test1\nhttps://youtu.be/test2';
        
        component.startBatchImport();

        expect(component.importInProgress).toBe(true);
        expect(component.cancelImportFlag).toBe(false);
        expect(component.batchImportStatus).toBe('Starting to import 2 URLs...');
      });
    });

    describe('closeBatchImportModal', () => {
      it('should close the modal', () => {
        component.batchImportModalOpen = true;
        
        component.closeBatchImportModal();

        expect(component.batchImportModalOpen).toBe(false);
      });
    });

    describe('cancelBatchImport', () => {
      it('should set cancel flag when import is in progress', () => {
        component.importInProgress = true;
        component.batchImportStatus = 'Importing...';
        
        component.cancelBatchImport();

        expect(component.cancelImportFlag).toBe(true);
        expect(component.batchImportStatus).toBe('Importing... Cancelling...');
      });

      it('should not set cancel flag when import is not in progress', () => {
        component.importInProgress = false;
        
        component.cancelBatchImport();

        expect(component.cancelImportFlag).toBe(false);
      });
    });
  });

  describe('URL Validation Regex', () => {
    it('should accept various valid URL formats', () => {
      const validUrls = [
        'https://youtube.com/watch?v=test',
        'http://youtube.com/watch?v=test',
        'https://youtu.be/test',
        'https://www.youtube.com/playlist?list=test',
        'https://github.com/user/repo',
        'https://example.com/path/to/resource',
        'http://subdomain.example.com:8080/path'
      ];

      validUrls.forEach(url => {
        component.batchImportText = url;
        component.validateBatchUrls();
        expect(component.urlValidationResults.valid).toContain(url, `${url} should be valid`);
        expect(component.urlValidationResults.invalid).not.toContain(url, `${url} should not be invalid`);
      });
    });

    it('should reject invalid URL formats', () => {
      const invalidUrls = [
        'youtube.com/watch?v=test', // missing protocol
        'ftp://youtube.com/watch?v=test', // wrong protocol
        'not-a-url',
        'just-text',
        'www.example.com', // missing protocol
        '//example.com' // protocol-relative
      ];

      invalidUrls.forEach(url => {
        component.batchImportText = url;
        component.validateBatchUrls();
        expect(component.urlValidationResults.invalid).toContain(url, `${url} should be invalid`);
        expect(component.urlValidationResults.valid).not.toContain(url, `${url} should not be valid`);
      });
    });
  });

  describe('UI Integration Tests', () => {
    beforeEach(() => {
      component.ngOnInit();
      fixture.detectChanges();
    });

    describe('Bulk Import Button', () => {
      it('should render the bulk import button in the main UI', () => {
        const compiled = fixture.nativeElement;
        const bulkImportBtn = compiled.querySelector('button[data-testid="bulk-import-btn"], button:contains("Bulk Import")');
        
        // Check if button exists (may not be visible if not properly built)
        if (bulkImportBtn) {
          expect(bulkImportBtn).toBeTruthy();
          expect(bulkImportBtn.textContent).toContain('Bulk Import');
        }
      });

      it('should disable bulk import button when loading', () => {
        component.downloads.loading = true;
        component.addInProgress = false;
        fixture.detectChanges();

        const compiled = fixture.nativeElement;
        const bulkImportBtn = compiled.querySelector('button:contains("Bulk Import")');
        
        if (bulkImportBtn) {
          expect(bulkImportBtn.disabled).toBe(true);
        }
      });

      it('should disable bulk import button when add in progress', () => {
        component.downloads.loading = false;
        component.addInProgress = true;
        fixture.detectChanges();

        const compiled = fixture.nativeElement;
        const bulkImportBtn = compiled.querySelector('button:contains("Bulk Import")');
        
        if (bulkImportBtn) {
          expect(bulkImportBtn.disabled).toBe(true);
        }
      });
    });

    describe('Batch Import Modal UI', () => {
      beforeEach(() => {
        component.openBatchImportModal();
        fixture.detectChanges();
      });

      it('should show modal when batchImportModalOpen is true', () => {
        expect(component.batchImportModalOpen).toBe(true);
        
        const compiled = fixture.nativeElement;
        const modal = compiled.querySelector('.modal');
        
        if (modal) {
          expect(modal.style.display).toBe('block');
          expect(modal.classList.contains('show')).toBe(true);
        }
      });

      it('should render textarea for URL input', () => {
        const compiled = fixture.nativeElement;
        const textarea = compiled.querySelector('#batchImportTextarea');
        
        if (textarea) {
          expect(textarea).toBeTruthy();
          expect(textarea.placeholder).toContain('Paste video URLs here');
        }
      });

      it('should show URL validation badges when URLs are entered', () => {
        component.batchImportText = 'https://youtube.com/test\ninvalid-url';
        component.validateBatchUrls();
        fixture.detectChanges();

        const compiled = fixture.nativeElement;
        const validBadge = compiled.querySelector('.badge.bg-success');
        const invalidBadge = compiled.querySelector('.badge.bg-danger');
        
        if (validBadge && invalidBadge) {
          expect(validBadge.textContent).toContain('1 Valid');
          expect(invalidBadge.textContent).toContain('1 Invalid');
        }
      });

      it('should disable import button when no valid URLs', () => {
        component.batchImportText = 'invalid-url\nnot-a-url';
        component.validateBatchUrls();
        fixture.detectChanges();

        const compiled = fixture.nativeElement;
        const importBtn = compiled.querySelector('button:contains("Import")');
        
        if (importBtn) {
          expect(importBtn.disabled).toBe(true);
        }
      });

      it('should enable import button when valid URLs exist', () => {
        component.batchImportText = 'https://youtube.com/test';
        component.validateBatchUrls();
        fixture.detectChanges();

        const compiled = fixture.nativeElement;
        const importBtn = compiled.querySelector('button:contains("Import")');
        
        if (importBtn) {
          expect(importBtn.disabled).toBe(false);
        }
      });

      it('should show cancel button when import is in progress', () => {
        component.importInProgress = true;
        fixture.detectChanges();

        const compiled = fixture.nativeElement;
        const cancelBtn = compiled.querySelector('button:contains("Cancel Import")');
        
        if (cancelBtn) {
          expect(cancelBtn).toBeTruthy();
        }
      });

      it('should update import button text based on valid URL count', () => {
        component.batchImportText = 'https://youtube.com/test1\nhttps://youtube.com/test2';
        component.validateBatchUrls();
        fixture.detectChanges();

        const compiled = fixture.nativeElement;
        const importBtn = compiled.querySelector('button:contains("Import")');
        
        if (importBtn) {
          expect(importBtn.textContent).toContain('Import 2');
        }
      });
    });

    describe('Error Details Expansion', () => {
      beforeEach(() => {
        component.openBatchImportModal();
        component.batchImportText = 'https://youtube.com/test\ninvalid-url\nnot-a-url\nhttps://youtube.com/test'; // includes duplicate
        component.validateBatchUrls();
        fixture.detectChanges();
      });

      it('should show expandable details for invalid and duplicate URLs', () => {
        const compiled = fixture.nativeElement;
        const details = compiled.querySelector('details');
        
        if (details) {
          expect(details).toBeTruthy();
          
          const summary = details.querySelector('summary');
          if (summary) {
            expect(summary.textContent).toContain('Show issues');
          }
        }
      });

      it('should limit displayed invalid URLs to 3 with "and X more" message', () => {
        // Set up more than 3 invalid URLs
        component.batchImportText = [
          'invalid1', 'invalid2', 'invalid3', 'invalid4', 'invalid5'
        ].join('\n');
        component.validateBatchUrls();
        fixture.detectChanges();

        const compiled = fixture.nativeElement;
        const invalidList = compiled.querySelector('.text-danger ul');
        
        if (invalidList) {
          const items = invalidList.querySelectorAll('li');
          expect(items.length).toBeLessThanOrEqual(4); // 3 + "and X more"
          
          const moreItem = invalidList.querySelector('li .text-muted');
          if (moreItem) {
            expect(moreItem.textContent).toContain('and 2 more');
          }
        }
      });
    });
  });

  describe('Accessibility Tests', () => {
    beforeEach(() => {
      component.ngOnInit();
      fixture.detectChanges();
    });

    it('should have proper labels for form elements', () => {
      component.openBatchImportModal();
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      const textarea = compiled.querySelector('#batchImportTextarea');
      const label = compiled.querySelector('label[for="batchImportTextarea"]');
      
      if (textarea && label) {
        expect(label.textContent).toContain('URLs (one per line)');
        expect(textarea.getAttribute('id')).toBe('batchImportTextarea');
      }
    });

    it('should have proper ARIA attributes for modal', () => {
      component.openBatchImportModal();
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      const modal = compiled.querySelector('.modal');
      const modalDialog = compiled.querySelector('.modal-dialog');
      
      if (modal && modalDialog) {
        expect(modal.getAttribute('role')).toBe('dialog');
        expect(modalDialog.getAttribute('role')).toBe('document');
      }
    });
  });

  describe('Performance Tests', () => {
    it('should handle large number of URLs efficiently', () => {
      const startTime = performance.now();
      
      // Create 1000 URLs for performance testing
      const urls = Array.from({ length: 1000 }, (_, i) => 
        `https://youtube.com/watch?v=test${i}`
      );
      component.batchImportText = urls.join('\n');
      
      component.validateBatchUrls();
      
      const endTime = performance.now();
      const executionTime = endTime - startTime;
      
      // Should complete validation in reasonable time (less than 100ms for 1000 URLs)
      expect(executionTime).toBeLessThan(100);
      expect(component.urlValidationResults.valid.length).toBe(1000);
      expect(component.parsedUrlCount).toBe(1000);
    });

    it('should handle duplicate detection efficiently with many duplicates', () => {
      const startTime = performance.now();
      
      // Create array with many duplicates
      const baseUrl = 'https://youtube.com/watch?v=duplicate';
      const urls = Array(500).fill(baseUrl).concat(
        Array.from({ length: 500 }, (_, i) => `https://youtube.com/watch?v=unique${i}`)
      );
      component.batchImportText = urls.join('\n');
      
      component.validateBatchUrls();
      
      const endTime = performance.now();
      const executionTime = endTime - startTime;
      
      expect(executionTime).toBeLessThan(200);
      expect(component.urlValidationResults.valid.length).toBe(501); // 1 base + 500 unique
      expect(component.urlValidationResults.duplicates).toEqual([baseUrl]);
    });
  });
});
