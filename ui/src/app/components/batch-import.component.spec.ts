import { TestBed } from '@angular/core/testing';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { Subject } from 'rxjs';
import { BatchImportComponent } from './batch-import.component';
import { AddDownloadPayload, DownloadsService } from '../services/downloads.service';
import { Status } from '../interfaces';

describe('BatchImportComponent', () => {
  let requests: { url: string; result: Subject<Status> }[];

  beforeEach(async () => {
    requests = [];
    const downloads = {
      add: (payload: AddDownloadPayload) => {
        const result = new Subject<Status>();
        requests.push({ url: payload.url, result });
        return result;
      },
    };
    await TestBed.configureTestingModule({
      imports: [BatchImportComponent],
      providers: [
        { provide: DownloadsService, useValue: downloads },
        { provide: NgbActiveModal, useValue: { close: vi.fn(), dismiss: vi.fn() } },
      ],
    }).compileComponents();
  });

  function create(text: string) {
    const fixture = TestBed.createComponent(BatchImportComponent);
    fixture.componentInstance.buildPayload = (url) => ({ url }) as AddDownloadPayload;
    fixture.componentInstance.text = text;
    fixture.detectChanges();
    return fixture.componentInstance;
  }

  const answer = (i: number, status: Status) => {
    requests[i].result.next(status);
    requests[i].result.complete();
  };

  it('queues each non-blank line with the form settings, four at a time', () => {
    const importer = create('a\n\n  b  \r\nc\nd\ne\nf\n');
    importer.start();

    expect(requests.map((r) => r.url)).toEqual(['a', 'b', 'c', 'd']);
    expect(importer.status).toBe('Importing 0 of 6 URLs...');

    answer(0, { status: 'ok' });
    answer(1, { status: 'error', msg: 'nope' });
    expect(requests.map((r) => r.url)).toEqual(['a', 'b', 'c', 'd', 'e', 'f']);
    for (let i = 2; i < 6; i++) {
      answer(i, { status: 'ok' });
    }

    expect(importer.inProgress).toBe(false);
    expect(importer.status).toBe('Finished importing 6 URLs. 1 failed.');
  });

  it('stops sending when cancelled', () => {
    const importer = create('a\nb\nc\nd\ne\nf');
    importer.start();
    answer(0, { status: 'ok' });

    importer.cancel();

    expect(importer.inProgress).toBe(false);
    expect(requests).toHaveLength(5);
    expect(importer.status).toBe('Import cancelled after 1 of 6 URLs.');
  });

  it('says so when there is nothing to import', () => {
    const importer = create(' \n \n');
    importer.start();
    expect(requests).toHaveLength(0);
    expect(importer.inProgress).toBe(false);
    expect(importer.status).toBe('No valid URLs found.');
  });
});
