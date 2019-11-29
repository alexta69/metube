import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { of, Subject } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { Socket } from 'ngx-socket-io';

export interface Status {
  status: string;
  msg?: string;
}

interface Download {
  id: string;
  title: string;
  url: string,
  status: string;
  percent: number;
  speed: number;
  eta: number;
  checked?: boolean;
  deleting?: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class DownloadsService {
  loading = true;
  downloads = new Map<string, Download>();
  dlChanges = new Subject();

  constructor(private http: HttpClient, private socket: Socket) {
    socket.fromEvent('queue').subscribe((strdata: string) => {
      this.loading = false;
      this.downloads.clear();
      let data: [[string, Download]] = JSON.parse(strdata);
      data.forEach(entry => this.downloads.set(...entry));
      this.dlChanges.next();
    });
    socket.fromEvent('added').subscribe((strdata: string) => {
      let data: Download = JSON.parse(strdata);
      this.downloads.set(data.id, data);
      this.dlChanges.next();
    });
    socket.fromEvent('updated').subscribe((strdata: string) => {
      let data: Download = JSON.parse(strdata);
      let dl: Download = this.downloads.get(data.id);
      data.checked = dl.checked;
      data.deleting = dl.deleting;
      this.downloads.set(data.id, data);
      this.dlChanges.next();
    });
    socket.fromEvent('deleted').subscribe((strdata: string) => {
      let data: string = JSON.parse(strdata);
      this.downloads.delete(data);
      this.dlChanges.next();
    });
  }

  empty() {
    return this.downloads.size == 0;
  }

  handleHTTPError(error: HttpErrorResponse) {
    var msg = error.error instanceof ErrorEvent ? error.error.message : error.error;
    return of({status: 'error', msg: msg})
  }

  public add(url: string) {
    return this.http.post<Status>('add', {url: url}).pipe(
      catchError(this.handleHTTPError)
    );
  }

  public del(ids: string[]) {
    ids.forEach(id => this.downloads.get(id).deleting = true);
    return this.http.post('delete', {ids: ids});
  }
}
