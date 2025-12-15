import { Injectable, inject } from '@angular/core';
import { ApplicationRef } from '@angular/core';
import { Socket } from 'ngx-socket-io';

@Injectable(
  { providedIn: 'root' }
)
export class MeTubeSocket extends Socket {

  constructor() {
    const appRef = inject(ApplicationRef);

    const path =
      document.location.pathname.replace(/share-target/, '') + 'socket.io';
    super({ url: '', options: { path } }, appRef);
  }
}
