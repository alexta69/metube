import { Component, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { faTrashAlt, faCheckCircle, faTimesCircle } from '@fortawesome/free-regular-svg-icons';

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
    {id: "1080p", text: "1080p"},
    {id: "720p", text: "720p"},
    {id: "480p", text: "480p"}
  ];
  quality: string = "best";
  addInProgress = false;
  
  @ViewChild('queueMasterCheckbox', {static: false}) queueMasterCheckbox: MasterCheckboxComponent;
  @ViewChild('queueDelSelected', {static: false}) queueDelSelected: ElementRef;
  @ViewChild('doneMasterCheckbox', {static: false}) doneMasterCheckbox: MasterCheckboxComponent;
  @ViewChild('doneDelSelected', {static: false}) doneDelSelected: ElementRef;
  @ViewChild('doneClearCompleted', {static: false}) doneClearCompleted: ElementRef;
  @ViewChild('doneClearFailed', {static: false}) doneClearFailed: ElementRef;

  faTrashAlt = faTrashAlt;
  faCheckCircle = faCheckCircle;
  faTimesCircle = faTimesCircle;

  constructor(public downloads: DownloadsService) {
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

  queueSelectionChanged(checked: number) {
    this.queueDelSelected.nativeElement.disabled = checked == 0;
  }

  doneSelectionChanged(checked: number) {
    this.doneDelSelected.nativeElement.disabled = checked == 0;
  }

  addDownload() {
    this.addInProgress = true;
    this.downloads.add(this.addUrl, this.quality).subscribe((status: Status) => {
      if (status.status === 'error') {
        alert(`Error adding URL: ${status.msg}`);
      } else {
        this.addUrl = '';
      }
      this.addInProgress = false;
    });
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
