import { Component, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { faTrashAlt, faCheckCircle, faTimesCircle } from '@fortawesome/free-regular-svg-icons';
import { faRedoAlt } from '@fortawesome/free-solid-svg-icons';
import { CookieService } from 'ngx-cookie-service';

import { DownloadsService, Status } from './downloads.service';
import { MasterCheckboxComponent } from './master-checkbox.component';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.sass']
})
export class AppComponent implements AfterViewInit {
  addUrl: string;
  qualities: Array<Object> = [
    {id: "best", text: "Best"},
    {id: "1440p", text: "1440p"},
    {id: "1080p", text: "1080p"},
    {id: "720p", text: "720p"},
    {id: "480p", text: "480p"},
    {id: "audio", text: "Audio only"}
  ];
  quality: string;
  formats: Array<Object> = [
    {id: "any", text: "Any"},
    {id: "mp4", text: "MP4"}
  ];
  format: string;
  addInProgress = false;

  @ViewChild('queueMasterCheckbox') queueMasterCheckbox: MasterCheckboxComponent;
  @ViewChild('queueDelSelected') queueDelSelected: ElementRef;
  @ViewChild('doneMasterCheckbox') doneMasterCheckbox: MasterCheckboxComponent;
  @ViewChild('doneDelSelected') doneDelSelected: ElementRef;
  @ViewChild('doneClearCompleted') doneClearCompleted: ElementRef;
  @ViewChild('doneClearFailed') doneClearFailed: ElementRef;

  faTrashAlt = faTrashAlt;
  faCheckCircle = faCheckCircle;
  faTimesCircle = faTimesCircle;
  faRedoAlt = faRedoAlt;

  constructor(public downloads: DownloadsService, private cookieService: CookieService) {
    this.quality = cookieService.get('metube_quality') || 'best';
    this.format = cookieService.get('metube_format') || 'any';
  }

  ngAfterViewInit() {
    this.downloads.queueChanged.subscribe(() => {
      this.queueMasterCheckbox.selectionChanged();
    });
    this.downloads.doneChanged.subscribe(() => {
      this.doneMasterCheckbox.selectionChanged();
      let completed: number = 0, failed: number = 0;
      this.downloads.done.forEach(dl => {
        if (dl.status === 'finished')
          completed++;
        else if (dl.status === 'error')
          failed++;
      });
      this.doneClearCompleted.nativeElement.disabled = completed === 0;
      this.doneClearFailed.nativeElement.disabled = failed === 0;
    });
  }

  // workaround to allow fetching of Map values in the order they were inserted
  //  https://github.com/angular/angular/issues/31420
  asIsOrder(a, b) {
    return 1;
  }

  qualityChanged() {
    this.cookieService.set('metube_quality', this.quality, { expires: 3650 });
  }

  formatChanged() {
    this.cookieService.set('metube_format', this.format, { expires: 3650 });
  }

  queueSelectionChanged(checked: number) {
    this.queueDelSelected.nativeElement.disabled = checked == 0;
  }

  doneSelectionChanged(checked: number) {
    this.doneDelSelected.nativeElement.disabled = checked == 0;
  }

  addDownload(url?: string, quality?: string, format?: string) {
    url = url ?? this.addUrl
    quality = quality ?? this.quality
    format = format ?? this.format

    this.addInProgress = true;
    this.downloads.add(url, quality, format).subscribe((status: Status) => {
      if (status.status === 'error') {
        alert(`Error adding URL: ${status.msg}`);
      } else {
        this.addUrl = '';
      }
      this.addInProgress = false;
    });
  }

  retryDownload(key: string, quality: string, format: string) {
    this.addDownload(key, quality, format);
    this.downloads.delById('done', [key]).subscribe();
  }

  delDownload(where: string, id: string) {
    this.downloads.delById(where, [id]).subscribe();
  }

  delSelectedDownloads(where: string) {
    this.downloads.delByFilter(where, dl => dl.checked).subscribe();
  }

  clearCompletedDownloads() {
    this.downloads.delByFilter('done', dl => dl.status === 'finished').subscribe();
  }

  clearFailedDownloads() {
    this.downloads.delByFilter('done', dl => dl.status === 'error').subscribe();
  }
}
