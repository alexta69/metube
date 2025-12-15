import { Component, ElementRef, viewChild, output, input } from "@angular/core";
import { Checkable } from "../interfaces";
import { FormsModule } from "@angular/forms";

@Component({
    selector: 'app-master-checkbox',
    template: `
  <div class="form-check">
    <input type="checkbox" class="form-check-input" id="{{id()}}-select-all" #masterCheckbox [(ngModel)]="selected" (change)="clicked()">
    <label class="form-check-label" for="{{id()}}-select-all"></label>
  </div>
`,
imports: [
  FormsModule
]
})
export class MasterCheckboxComponent {
  readonly id = input.required<string>();
  readonly list = input.required<Map<string, Checkable>>();
  readonly changed = output<number>();

  readonly masterCheckbox = viewChild.required<ElementRef>('masterCheckbox');
  selected!: boolean;

  clicked() {
    this.list().forEach(item => item.checked = this.selected);
    this.selectionChanged();
  }

  selectionChanged() {
    const masterCheckbox = this.masterCheckbox();
    if (!masterCheckbox)
      return;
    let checked = 0;
    this.list().forEach(item => { if(item.checked) checked++ });
    this.selected = checked > 0 && checked == this.list().size;
    masterCheckbox.nativeElement.indeterminate = checked > 0 && checked < this.list().size;
    this.changed.emit(checked);
  }
}
