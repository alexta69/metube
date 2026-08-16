import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { Subject } from 'rxjs';
import { SubscriptionsService, SubscribePayload } from './subscriptions.service';
import { MeTubeSocket } from './metube-socket.service';

class MeTubeSocketStub {
  private subjects: Record<string, Subject<string>> = {};

  fromEvent(event: string) {
    if (!this.subjects[event]) {
      this.subjects[event] = new Subject<string>();
    }
    return this.subjects[event].asObservable();
  }
}

function basePayload(): SubscribePayload {
  return {
    url: 'https://example.com/channel',
    downloadType: 'video',
    codec: 'auto',
    quality: 'best',
    format: 'any',
    folder: '',
    customNamePrefix: '',
    playlistItemLimit: 0,
    autoStart: true,
    splitByChapters: false,
    sponsorblock: false,
    chapterTemplate: '',
    subtitleLanguage: 'en',
    subtitleMode: 'prefer_manual',
    ytdlOptionsPresets: [],
    ytdlOptionsOverrides: '',
    clipStart: '',
    clipEnd: '',
    checkIntervalMinutes: 60,
    titleRegex: '',
    skipSubscriberOnly: false,
  };
}

describe('SubscriptionsService', () => {
  let httpMock: HttpTestingController;
  let service: SubscriptionsService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      providers: [
        SubscriptionsService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MeTubeSocket, useValue: new MeTubeSocketStub() },
      ],
    }).compileComponents();

    service = TestBed.inject(SubscriptionsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('subscribe() carries the sponsorblock flag', () => {
    service.subscribe({ ...basePayload(), sponsorblock: true }).subscribe();
    const req = httpMock.expectOne('subscribe');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(expect.objectContaining({ sponsorblock: true }));
    req.flush({ status: 'ok' });
  });

  it('subscribe() sends the flag off by default', () => {
    service.subscribe(basePayload()).subscribe();
    const req = httpMock.expectOne('subscribe');
    expect(req.request.body).toEqual(expect.objectContaining({ sponsorblock: false }));
    req.flush({ status: 'ok' });
  });
});
