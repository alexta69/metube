import { TestBed } from '@angular/core/testing';
import { provideHttpClient, HttpErrorResponse } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { Subject } from 'rxjs';
import { DownloadsService, AddDownloadPayload } from './downloads.service';
import { MeTubeSocket } from './metube-socket.service';
import { Download } from '../interfaces';

class MeTubeSocketStub {
  private subjects: Record<string, Subject<string>> = {};

  fromEvent(event: string) {
    if (!this.subjects[event]) {
      this.subjects[event] = new Subject<string>();
    }
    return this.subjects[event].asObservable();
  }

  emit(event: string, data: string) {
    if (!this.subjects[event]) {
      this.subjects[event] = new Subject<string>();
    }
    this.subjects[event].next(data);
  }
}

function basePayload(): AddDownloadPayload {
  return {
    url: 'https://example.com/v',
    downloadType: 'video',
    codec: 'auto',
    quality: 'best',
    format: 'any',
    folder: '',
    customNamePrefix: '',
    playlistItemLimit: 0,
    autoStart: true,
    splitByChapters: false,
    chapterTemplate: '',
    subtitleLanguage: 'en',
    subtitleMode: 'prefer_manual',
    ytdlOptionsPresets: [],
    ytdlOptionsOverrides: '',
  };
}

describe('DownloadsService', () => {
  let socket: MeTubeSocketStub;
  let httpMock: HttpTestingController;
  let service: DownloadsService;

  beforeEach(async () => {
    socket = new MeTubeSocketStub();
    await TestBed.configureTestingModule({
      providers: [
        DownloadsService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MeTubeSocket, useValue: socket },
      ],
    }).compileComponents();

    service = TestBed.inject(DownloadsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('add() posts snake_case fields matching backend', () => {
    service.add(basePayload()).subscribe();
    const req = httpMock.expectOne('add');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(
      expect.objectContaining({
        url: 'https://example.com/v',
        download_type: 'video',
        codec: 'auto',
        quality: 'best',
        format: 'any',
        playlist_item_limit: 0,
        auto_start: true,
        split_by_chapters: false,
        chapter_template: '',
        subtitle_language: 'en',
        subtitle_mode: 'prefer_manual',
        ytdl_options_presets: [],
        ytdl_options_overrides: '',
      }),
    );
    req.flush({ status: 'ok' });
  });

  it('getPresets() fetches configured preset names', () => {
    service.getPresets().subscribe((result) => {
      expect(result).toEqual({ presets: ['Preset A'] });
    });
    const req = httpMock.expectOne('presets');
    expect(req.request.method).toBe('GET');
    req.flush({ presets: ['Preset A'] });
  });

  it('cancelAdd posts to cancel-add', () => {
    service.cancelAdd().subscribe();
    const req = httpMock.expectOne('cancel-add');
    expect(req.request.method).toBe('POST');
    req.flush({ status: 'ok' });
  });

  it('startById posts ids', () => {
    service.startById(['a', 'b']).subscribe();
    const req = httpMock.expectOne('start');
    expect(req.request.body).toEqual({ ids: ['a', 'b'] });
    req.flush({});
  });

  it('delById marks items deleting and posts delete', () => {
    const dl: Download = {
      id: '1',
      title: 't',
      url: 'u1',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'finished',
      msg: '',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
      deleting: false,
    };
    service.queue.set('u1', dl);
    service.delById('queue', ['u1']).subscribe();
    expect(dl.deleting).toBe(true);
    const req = httpMock.expectOne('delete');
    expect(req.request.body).toEqual({ where: 'queue', ids: ['u1'] });
    req.flush({});
  });

  it('handleHTTPError extracts msg from object body', async () => {
    const err = new HttpErrorResponse({
      error: { msg: 'bad' },
      status: 400,
    });
    const res = await new Promise((resolve) => {
      service.handleHTTPError(err).subscribe(resolve);
    });
    expect((res as { status: string }).status).toBe('error');
    expect((res as { msg?: string }).msg).toBe('bad');
  });

  it('socket all updates queue and done', () => {
    const row: Download = {
      id: '1',
      title: 't',
      url: 'u1',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'pending',
      msg: '',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    };
    const q: [string, Download][] = [['u1', row]];
    const d: [string, Download][] = [];
    socket.emit('all', JSON.stringify([q, d]));
    expect(service.loading).toBe(false);
    expect(service.queue.has('u1')).toBe(true);
  });

  it('socket updated preserves checked and deleting', () => {
    service.queue.set('u1', {
      id: '1',
      title: 't',
      url: 'u1',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'pending',
      msg: '',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: true,
      deleting: true,
    });
    socket.emit(
      'updated',
      JSON.stringify({ url: 'u1', title: 't', status: 'downloading' }),
    );
    const updated = service.queue.get('u1');
    expect(updated?.checked).toBe(true);
    expect(updated?.deleting).toBe(true);
  });

  it('socket completed moves entry to done', () => {
    service.queue.set('u1', {
      id: '1',
      title: 't',
      url: 'u1',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'pending',
      msg: '',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    });
    socket.emit('completed', JSON.stringify({ url: 'u1', title: 't', status: 'finished' }));
    expect(service.queue.has('u1')).toBe(false);
    expect(service.done.has('u1')).toBe(true);
  });

  it('socket canceled removes from queue', () => {
    service.queue.set('u1', {
      id: '1',
      title: 't',
      url: 'u1',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'pending',
      msg: '',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    });
    socket.emit('canceled', JSON.stringify('u1'));
    expect(service.queue.has('u1')).toBe(false);
  });

  it('socket cleared removes from done', () => {
    service.done.set('u1', {
      id: '1',
      title: 't',
      url: 'u1',
      download_type: 'video',
      quality: 'best',
      format: 'any',
      folder: '',
      custom_name_prefix: '',
      playlist_item_limit: 0,
      status: 'finished',
      msg: '',
      percent: 0,
      speed: 0,
      eta: 0,
      filename: '',
      checked: false,
    });
    socket.emit('cleared', JSON.stringify('u1'));
    expect(service.done.has('u1')).toBe(false);
  });

  it('socket configuration updates configuration', () => {
    socket.emit('configuration', JSON.stringify({ CUSTOM_DIRS: true }));
    expect(service.configuration['CUSTOM_DIRS']).toBe(true);
  });

  it('socket custom_dirs updates customDirs', () => {
    socket.emit('custom_dirs', JSON.stringify({ download_dir: [''] }));
    expect(service.customDirs['download_dir']).toEqual(['']);
  });

  afterEach(() => {
    httpMock.verify();
  });
});
