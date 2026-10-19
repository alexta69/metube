import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

export type UserRole = 'admin' | 'user';

export interface AuthUser {
  id: string;
  username: string;
  role: UserRole;
  active?: boolean;
  created_at?: number;
  updated_at?: number;
}

export interface AuthStatus {
  setup_required: boolean;
  authenticated: boolean;
  user: AuthUser | null;
}

export interface Invitation {
  id: string;
  role: UserRole;
  created_at?: number;
  expires_at: number;
  token?: string;
}

export interface ApiToken {
  id: string;
  name: string;
  prefix: string;
  created_at: number;
  last_used_at: number | null;
  token?: string;
}

function applicationBase(): string {
  const path = window.location.pathname;
  const route = /(?:login|onboarding|users|profile|invite)\/?$/.exec(path);
  return route ? path.slice(0, route.index) : path.replace(/[^/]*$/, '');
}

export function appUrl(path = ''): string {
  return `${applicationBase()}${path}`;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);

  status() {
    return this.http.get<AuthStatus>(appUrl('auth/status'));
  }

  onboarding(username: string, password: string) {
    return this.http.post<{ status: string; user: AuthUser }>(appUrl('auth/onboarding'), {
      username,
      password,
    });
  }

  login(username: string, password: string) {
    return this.http.post<{ status: string; user: AuthUser }>(appUrl('auth/login'), {
      username,
      password,
    });
  }

  logout() {
    return this.http.post<{ status: string }>(appUrl('auth/logout'), {});
  }

  invitation(token: string) {
    return this.http.get<Invitation>(appUrl(`auth/invite/${encodeURIComponent(token)}`));
  }

  acceptInvitation(token: string, username: string, password: string) {
    return this.http.post<{ status: string; user: AuthUser }>(
      appUrl(`auth/invite/${encodeURIComponent(token)}/accept`),
      { username, password },
    );
  }

  users() {
    return this.http.get<AuthUser[]>(appUrl('auth/users'));
  }

  updateUser(user: AuthUser) {
    return this.http.patch<{ status: string; user: AuthUser }>(
      appUrl(`auth/users/${user.id}`),
      { username: user.username, role: user.role, active: user.active },
    );
  }

  deleteUser(userId: string) {
    return this.http.delete<{ status: string }>(appUrl(`auth/users/${userId}`));
  }

  revokeUser(userId: string) {
    return this.http.post<{ status: string }>(appUrl(`auth/users/${userId}/revoke`), {});
  }

  invitations() {
    return this.http.get<Invitation[]>(appUrl('auth/invitations'));
  }

  createInvitation(role: UserRole) {
    return this.http.post<{ status: string; invitation: Invitation }>(
      appUrl('auth/invitations'),
      { role },
    );
  }

  revokeInvitation(invitationId: string) {
    return this.http.delete<{ status: string }>(
      appUrl(`auth/invitations/${invitationId}`),
    );
  }

  changePassword(currentPassword: string, newPassword: string) {
    return this.http.post<{ status: string }>(appUrl('auth/password'), {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  tokens() {
    return this.http.get<ApiToken[]>(appUrl('auth/tokens'));
  }

  createToken(name: string) {
    return this.http.post<{ status: string; token: ApiToken }>(appUrl('auth/tokens'), {
      name,
    });
  }

  revokeToken(tokenId: string) {
    return this.http.delete<{ status: string }>(appUrl(`auth/tokens/${tokenId}`));
  }
}

export const authInterceptor: HttpInterceptorFn = (request, next) =>
  next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      const isPublicAuthEndpoint = /\/auth\/(?:status|login|onboarding|invite\/)/.test(
        request.url,
      );
      if (error.status === 401 && !isPublicAuthEndpoint) {
        window.location.assign(appUrl('login'));
      }
      return throwError(() => error);
    }),
  );
