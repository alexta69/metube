import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { of, Subject } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MeTubeSocket } from './metube-socket';

export interface Status {
  status: string;
  msg?: string;
}

interface Download {
  id: string;
  title: string;
  url: string,
  status: string;
  msg: string;
  filename: string;
  quality: string;
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
  queue = new Map<string, Download>();
  done = new Map<string, Download>();
  queueChanged = new Subject();
  doneChanged = new Subject();

  constructor(private http: HttpClient, private socket: MeTubeSocket) {
    socket.fromEvent('all').subscribe((strdata: string) => {
      this.loading = false;
      let data: [[[string, Download]], [[string, Download]]] = JSON.parse(strdata);
      this.queue.clear();
      data[0].forEach(entry => this.queue.set(...entry));
      this.done.clear();
      data[1].forEach(entry => this.done.set(...entry));
      this.queueChanged.next(null);
      this.doneChanged.next(null);
    });
    socket.fromEvent('added').subscribe((strdata: string) => {
      let data: Download = JSON.parse(strdata);
      this.queue.set(data.id, data);
      this.queueChanged.next(null);
    });
    socket.fromEvent('updated').subscribe((strdata: string) => {
      let data: Download = JSON.parse(strdata);
      let dl: Download = this.queue.get(data.id);
      data.checked = dl.checked;
      data.deleting = dl.deleting;
      this.queue.set(data.id, data);
    });
    socket.fromEvent('completed').subscribe((strdata: string) => {
      let data: Download = JSON.parse(strdata);
      this.queue.delete(data.id);
      this.done.set(data.id, data);
      this.queueChanged.next(null);
      this.doneChanged.next(null);
    });
    socket.fromEvent('canceled').subscribe((strdata: string) => {
      let data: string = JSON.parse(strdata);
      this.queue.delete(data);
      this.queueChanged.next(null);
    });
    socket.fromEvent('cleared').subscribe((strdata: string) => {
      let data: string = JSON.parse(strdata);
      this.done.delete(data);
      this.doneChanged.next(null);
    });
  }

  handleHTTPError(error: HttpErrorResponse) {
    var msg = error.error instanceof ErrorEvent ? error.error.message : error.error;
    return of({status: 'error', msg: msg})
  }

  public add(url: string, quality: string, format: string) {
    return this.http.post<Status>('add', {url: url, quality: quality, format: format}).pipe(
      catchError(this.handleHTTPError)
    );
  }

  public delById(where: string, ids: string[]) {
    ids.forEach(id => this[where].get(id).deleting = true);
    return this.http.post('delete', {where: where, ids: ids});
  }

  public delByFilter(where: string, filter: (dl: Download) => boolean) {
    let ids: string[] = [];
    this[where].forEach((dl: Download) => { if (filter(dl)) ids.push(dl.id) });
    return this.delById(where, ids);
  }
}
