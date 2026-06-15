import { Injectable, inject } from '@angular/core';
import { ApplicationRef } from '@angular/core';
import { Socket } from 'ngx-socket-io';
import { CookieService } from 'ngx-cookie-service';

@Injectable(
  { providedIn: 'root' }
)
export class MeTubeSocket extends Socket {
  private static readonly VISIT_ID_COOKIE = 'metube_visit_id';
  private static readonly VISIT_ID_EXPIRY_DAYS = 365;

  private readonly visitId: string;

  getVisitId(): string {
    return this.visitId;
  }

  constructor() {
    const appRef = inject(ApplicationRef);
    const cookieService = inject(CookieService);

    const path =
      document.location.pathname.replace(/share-target/, '') + 'socket.io';

    let visitId = cookieService.get(MeTubeSocket.VISIT_ID_COOKIE);
    if (!visitId) {
      visitId = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
      cookieService.set(MeTubeSocket.VISIT_ID_COOKIE, visitId, {
        expires: MeTubeSocket.VISIT_ID_EXPIRY_DAYS,
        path: '/',
      });
    }

    super({ url: '', options: { path, query: { visit_id: visitId } } }, appRef);
    this.visitId = visitId;
  }
}
