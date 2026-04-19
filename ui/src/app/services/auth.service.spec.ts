import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from './auth.service';
import { MeTubeSocket } from './metube-socket.service';

class MeTubeSocketStub {
  ioSocket = {
    connected: false,
    active: false,
    on: vi.fn(),
  };

  connect = vi.fn(() => {
    this.ioSocket.active = true;
  });

  disconnect = vi.fn(() => {
    this.ioSocket.active = false;
    this.ioSocket.connected = false;
  });

  connectIfNeeded() {
    if (!this.ioSocket.connected && !this.ioSocket.active) {
      this.connect();
    }
  }

  disconnectIfConnected() {
    if (this.ioSocket.connected || this.ioSocket.active) {
      this.disconnect();
    }
  }
}

describe('AuthService', () => {
  let socket: MeTubeSocketStub;
  let httpMock: HttpTestingController;
  let service: AuthService;

  beforeEach(async () => {
    socket = new MeTubeSocketStub();

    await TestBed.configureTestingModule({
      providers: [
        AuthService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MeTubeSocket, useValue: socket },
      ],
    }).compileComponents();

    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('loads auth status and connects the socket for authorized clients', () => {
    service.loadStatus().subscribe((response) => {
      expect(response).toEqual({ status: 'ok', enabled: true, authenticated: true });
    });

    const req = httpMock.expectOne('auth/status');
    expect(req.request.method).toBe('GET');
    req.flush({ status: 'ok', enabled: true, authenticated: true });

    expect(socket.connect).toHaveBeenCalled();
  });

  it('disconnects the socket when markUnauthorized is called', () => {
    socket.ioSocket.connected = true;
    service.markUnauthorized();
    expect(socket.disconnect).toHaveBeenCalled();
  });

  it('returns a typed error payload on login failure', () => {
    service.login('bad-password').subscribe((response) => {
      expect(response.status).toBe('error');
      expect(response.authenticated).toBe(false);
      expect(response.msg).toBe('Invalid password');
    });

    const req = httpMock.expectOne('auth/login');
    expect(req.request.method).toBe('POST');
    req.flush({ msg: 'Invalid password' }, { status: 401, statusText: 'Unauthorized' });

    expect(socket.disconnect).toHaveBeenCalled();
  });
});