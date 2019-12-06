import { Injectable } from '@angular/core';
import { Socket } from 'ngx-socket-io';

@Injectable()
export class MeTubeSocket extends Socket {
     constructor() {
        super({ url: '', options: {path: document.location.pathname + 'socket.io'} });
    }
}
