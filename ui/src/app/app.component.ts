import { Component, ViewChild, ElementRef } from '@angular/core';
import { faTrashAlt } from '@fortawesome/free-regular-svg-icons';

import { DownloadsService, Status } from './downloads.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.sass']
})
export class AppComponent {
  addUrl: string;
  addInProgress = false;
  faTrashAlt = faTrashAlt;
  masterSelected: boolean;
  @ViewChild('masterCheckbox', {static: false}) masterCheckbox: ElementRef;
  @ViewChild('delSelected', {static: false}) delSelected: ElementRef;

  constructor(public downloads: DownloadsService) {
    this.downloads.dlChanges.subscribe(() => this.selectionChanged());
  }

  // workaround to allow fetching of Map values in the order they were inserted
  //  https://github.com/angular/angular/issues/31420
  asIsOrder(a, b) {
    return 1;
  }

  checkUncheckAll() {
    this.downloads.downloads.forEach(dl => dl.checked = this.masterSelected);
    this.selectionChanged();
  }

  selectionChanged() {
    if (!this.masterCheckbox)
      return;
    let checked: number = 0;
    this.downloads.downloads.forEach(dl => { if(dl.checked) checked++ });
    this.masterSelected = checked > 0 && checked == this.downloads.downloads.size;
    this.masterCheckbox.nativeElement.indeterminate = checked > 0 && checked < this.downloads.downloads.size;
    this.delSelected.nativeElement.disabled = checked == 0;
  }

  addDownload() {
    this.addInProgress = true;
    this.downloads.add(this.addUrl).subscribe((status: Status) => {
      if (status.status === 'error') {
        alert(`Error adding URL: ${status.msg}`);
      } else {
        this.addUrl = '';
      }
      this.addInProgress = false;
    });
  }

  delDownload(id: string) {
    this.downloads.del([id]).subscribe();
  }

  delSelectedDownloads() {
    let ids: string[] = [];
    this.downloads.downloads.forEach(dl => { if(dl.checked) ids.push(dl.id) });
    this.downloads.del(ids).subscribe();
  }
}
