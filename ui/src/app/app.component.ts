import { Component, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { faTrashAlt, faCheckCircle, faTimesCircle } from '@fortawesome/free-regular-svg-icons';
import { faRedoAlt } from '@fortawesome/free-solid-svg-icons';
import { CookieService } from 'ngx-cookie-service';

import { DownloadsService, Status } from './downloads.service';
import { MasterCheckboxComponent } from './master-checkbox.component';
import { Formats, Format, Quality, getQualityById } from './formats';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.sass']
})
export class AppComponent implements AfterViewInit {
  addUrl: string;
  formats: Format[] = Formats;
  qualities: Quality[];
  quality: Quality;
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
    this.format = cookieService.get('metube_format') || 'any';
    // Needs to be set or qualities won't automatically be set
    this.setQualities()
    let qualityId = cookieService.get('metube_quality') || this.qualities[0].id
    this.quality = getQualityById(this.formats, qualityId);
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
    this.cookieService.set('metube_quality', this.quality.id, { expires: 3650 });
  }

  formatChanged() {
    this.cookieService.set('metube_format', this.format, { expires: 3650 });
    // Updates to use qualities available
    this.setQualities()
  }

  queueSelectionChanged(checked: number) {
    this.queueDelSelected.nativeElement.disabled = checked == 0;
  }

  doneSelectionChanged(checked: number) {
    this.doneDelSelected.nativeElement.disabled = checked == 0;
  }

  setQualities() {
    // qualities for specific format
    this.qualities = this.formats.find(el => el.id == this.format).qualities
    this.quality = this.qualities.find(el => el.value === "best")
  }

  addDownload(url?: string, quality?: string, format?: string) {
    url = url ?? this.addUrl
    quality = quality ?? this.quality.value
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
