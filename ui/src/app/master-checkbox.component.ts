import { Component, Input, ViewChild, ElementRef, Output, EventEmitter } from '@angular/core';

interface Checkable {
  checked: boolean;
}

@Component({
  selector: 'app-master-checkbox',
  template: `
  <div class="custom-control custom-checkbox">
    <input type="checkbox" class="custom-control-input" id="{{id}}-select-all" #masterCheckbox [(ngModel)]="selected" (change)="clicked()">
    <label class="custom-control-label" for="{{id}}-select-all"></label>
  </div>
`
})
export class MasterCheckboxComponent {
  @Input() id: string;
  @Input() list: Map<String, Checkable>;
  @Output() changed = new EventEmitter<number>();

  @ViewChild('masterCheckbox', {static: false}) masterCheckbox: ElementRef;
  selected: boolean;

  clicked() {
    this.list.forEach(item => item.checked = this.selected);
    this.selectionChanged();
  }

  selectionChanged() {
    if (!this.masterCheckbox)
      return;
    let checked: number = 0;
    this.list.forEach(item => { if(item.checked) checked++ });
    this.selected = checked > 0 && checked == this.list.size;
    this.masterCheckbox.nativeElement.indeterminate = checked > 0 && checked < this.list.size;
    this.changed.emit(checked);
  }
}

@Component({
  selector: 'app-slave-checkbox',
  template: `
  <div class="custom-control custom-checkbox">
    <input type="checkbox" class="custom-control-input" id="{{master.id}}-{{id}}-select" [(ngModel)]="checkable.checked" (change)="master.selectionChanged()">
    <label class="custom-control-label" for="{{master.id}}-{{id}}-select"></label>
  </div>
`
})
export class SlaveCheckboxComponent {
  @Input() id: string;
  @Input() master: MasterCheckboxComponent;
  @Input() checkable: Checkable;
}
