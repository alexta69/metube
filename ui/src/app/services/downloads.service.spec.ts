/* eslint-disable @typescript-eslint/no-explicit-any */
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { DownloadsService } from './downloads.service';
import { MeTubeSocket } from './metube-socket.service';
import { Download, Status } from '../interfaces';
import { of, Observable } from 'rxjs';

describe('DownloadsService', () => {
  let service: DownloadsService;
  let httpMock: HttpTestingController;
  let mockSocket: any;

  beforeEach(() => {
    // Create mock socket with proper typing
    const fromEventMock = <T = any>(event: string): Observable<T> => {
      // Return properly formatted data for different events
      if (event === 'all') {
        return of('[[],[]]' as any); // Empty queue and done arrays
      } else if (event === 'configuration') {
        return of('{}' as any); // Empty configuration object
      } else if (event === 'custom_dirs') {
        return of('{}' as any); // Empty custom dirs object
      }
      return of('[]' as any); // Default for other events
    };
    
    mockSocket = {
      fromEvent: fromEventMock,
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        DownloadsService,
        { provide: MeTubeSocket, useValue: mockSocket },
      ],
    });

    service = TestBed.inject(DownloadsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should have queue and done maps initialized', () => {
    // The service initializes with socket events, so we just verify the maps exist
    expect(service.queue).toBeInstanceOf(Map);
    expect(service.done).toBeInstanceOf(Map);
    expect(service.loading).toBe(false);
  });

  it('should add a download via HTTP POST', () => {
    const mockStatus: Status = { status: 'success' };
    const url = 'https://example.com/video';
    const quality = 'best';
    const format = 'mp4';

    service.add(url, quality, format, '', '', false, 0, true).subscribe((status) => {
      expect(status).toEqual(mockStatus);
    });

    const req = httpMock.expectOne('add');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      url,
      quality,
      format,
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      auto_start: true,
    });
    req.flush(mockStatus);
  });

  it('should start downloads by id', () => {
    const ids = ['url1', 'url2'];

    service.startById(ids).subscribe();

    const req = httpMock.expectOne('start');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ ids });
    req.flush({});
  });

  it('should delete downloads by id and mark them as deleting', () => {
    const mockDownload: Download = {
      id: 'id1',
      title: 'Test',
      url: 'url1',
      quality: 'best',
      format: 'mp4',
      status: 'finished',
      msg: '',
      filename: 'test.mp4',
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      percent: 100,
      speed: 0,
      eta: 0,
      checked: false,
    };
    service.done.set('url1', mockDownload);

    const ids = ['url1'];
    service.delById('done', ids).subscribe();

    expect(mockDownload.deleting).toBe(true);

    const req = httpMock.expectOne('delete');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ where: 'done', ids });
    req.flush({});
  });

  it('should start downloads by filter', () => {
    const mockDownload1: Download = {
      id: 'id1',
      title: 'Test 1',
      url: 'url1',
      quality: 'best',
      format: 'mp4',
      status: 'pending',
      msg: '',
      filename: 'test1.mp4',
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      percent: 0,
      speed: 0,
      eta: 0,
      checked: false,
    };
    const mockDownload2: Download = {
      id: 'id2',
      title: 'Test 2',
      url: 'url2',
      quality: 'best',
      format: 'mp4',
      status: 'downloading',
      msg: '',
      filename: 'test2.mp4',
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      percent: 50,
      speed: 1000,
      eta: 10,
      checked: false,
    };

    service.queue.set('url1', mockDownload1);
    service.queue.set('url2', mockDownload2);

    service.startByFilter('queue', (dl) => dl.status === 'pending').subscribe();

    const req = httpMock.expectOne('start');
    expect(req.request.body.ids).toEqual(['url1']);
    req.flush({});
  });

  it('should delete downloads by filter', () => {
    const mockDownload1: Download = {
      id: 'id1',
      title: 'Test 1',
      url: 'url1',
      quality: 'best',
      format: 'mp4',
      status: 'finished',
      msg: '',
      filename: 'test1.mp4',
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      percent: 100,
      speed: 0,
      eta: 0,
      checked: false,
    };
    const mockDownload2: Download = {
      id: 'id2',
      title: 'Test 2',
      url: 'url2',
      quality: 'best',
      format: 'mp4',
      status: 'error',
      msg: 'Failed',
      filename: 'test2.mp4',
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      percent: 0,
      speed: 0,
      eta: 0,
      checked: false,
    };

    service.done.set('url1', mockDownload1);
    service.done.set('url2', mockDownload2);

    service.delByFilter('done', (dl) => dl.status === 'error').subscribe();

    const req = httpMock.expectOne('delete');
    expect(req.request.body.ids).toEqual(['url2']);
    req.flush({});
  });

  it('should handle HTTP errors', () => {
    const url = 'https://example.com/video';

    service.add(url, 'best', 'mp4', '', '', false, 0, true).subscribe((response) => {
      expect(response.status).toBe('error');
    });

    const req = httpMock.expectOne('add');
    req.error(new ProgressEvent('error'), {
      status: 500,
      statusText: 'Server Error',
    });
  });

  it('should add download by URL with default values', async () => {
    const url = 'https://example.com/video';
    const mockStatus: Status = { status: 'success' };

    const promise = service.addDownloadByUrl(url);

    const req = httpMock.expectOne('add');
    expect(req.request.body).toEqual({
      url,
      quality: 'best',
      format: 'mp4',
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      auto_start: true,
    });
    req.flush(mockStatus);

    const result = await promise;
    expect(result).toEqual(mockStatus);
  });

  it('should export queue URLs', () => {
    const mockDownload1: Download = {
      id: 'id1',
      title: 'Test 1',
      url: 'https://example.com/video1',
      quality: 'best',
      format: 'mp4',
      status: 'pending',
      msg: '',
      filename: 'test1.mp4',
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      percent: 0,
      speed: 0,
      eta: 0,
      checked: false,
    };
    const mockDownload2: Download = {
      id: 'id2',
      title: 'Test 2',
      url: 'https://example.com/video2',
      quality: 'best',
      format: 'mp4',
      status: 'downloading',
      msg: '',
      filename: 'test2.mp4',
      folder: '',
      custom_name_prefix: '',
      playlist_strict_mode: false,
      playlist_item_limit: 0,
      percent: 50,
      speed: 1000,
      eta: 10,
      checked: false,
    };

    service.queue.set('url1', mockDownload1);
    service.queue.set('url2', mockDownload2);

    const urls = service.exportQueueUrls();
    expect(urls).toEqual(['https://example.com/video1', 'https://example.com/video2']);
  });
});
