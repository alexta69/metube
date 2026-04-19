import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';
import { MeTubeSocket } from './metube-socket.service';

export interface AuthResponse {
  status: string;
  enabled: boolean;
  authenticated: boolean;
  msg?: string;
}

export interface AuthState {
  enabled: boolean;
  authenticated: boolean;
  loading: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private http = inject(HttpClient);
  private socket = inject(MeTubeSocket);

  private stateSubject = new BehaviorSubject<AuthState>({
    enabled: false,
    authenticated: false,
    loading: true,
  });

  readonly state$ = this.stateSubject.asObservable();

  constructor() {
    this.socket.ioSocket.on('connect_error', (error: { message?: string }) => {
      if (error?.message === 'Authentication required') {
        this.markUnauthorized();
      }
    });
  }

  loadStatus(): Observable<AuthResponse> {
    return this.http.get<AuthResponse>('auth/status').pipe(
      tap((response) => this.applyResponse(response)),
      catchError((error) => of(this.handleError(error))),
    );
  }

  login(password: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>('auth/login', { password }).pipe(
      tap((response) => this.applyResponse(response)),
      catchError((error) => of(this.handleError(error))),
    );
  }

  logout(): Observable<AuthResponse> {
    return this.http.post<AuthResponse>('auth/logout', {}).pipe(
      tap((response) => this.applyResponse(response)),
      catchError((error) => of(this.handleError(error, { authenticated: false }))),
    );
  }

  markUnauthorized() {
    const current = this.stateSubject.value;
    this.stateSubject.next({
      ...current,
      authenticated: false,
      loading: false,
    });
    this.socket.disconnectIfConnected();
  }

  private applyResponse(response: AuthResponse) {
    this.stateSubject.next({
      enabled: !!response.enabled,
      authenticated: !!response.authenticated,
      loading: false,
    });

    if (!response.enabled || response.authenticated) {
      this.socket.connectIfNeeded();
      return;
    }

    this.socket.disconnectIfConnected();
  }

  private handleError(error: HttpErrorResponse, overrides: Partial<AuthState> = {}): AuthResponse {
    const current = this.stateSubject.value;
    const enabled = overrides.enabled ?? current.enabled;
    const authenticated = overrides.authenticated ?? false;

    this.stateSubject.next({
      enabled,
      authenticated,
      loading: false,
    });
    this.socket.disconnectIfConnected();

    const msg =
      error.error instanceof ErrorEvent
        ? error.error.message
        : typeof error.error === 'string'
          ? error.error
          : error.error?.msg || error.message || 'Request failed';

    return {
      status: 'error',
      enabled,
      authenticated,
      msg,
    };
  }
}