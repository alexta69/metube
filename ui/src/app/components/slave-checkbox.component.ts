import { Component, input } from '@angular/core';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { Checkable } from '../interfaces';
import { FormsModule } from '@angular/forms';

@Component({
    selector: 'app-item-checkbox',
    template: `
  <div class="form-check">
    <input type="checkbox" class="form-check-input" id="{{master().id()}}-{{id()}}-select" [(ngModel)]="checkable().checked" (change)="master().selectionChanged()" [attr.aria-label]="'Select item ' + id()">
    <label class="form-check-label visually-hidden" for="{{master().id()}}-{{id()}}-select">Select item</label>
  </div>
`,
imports: [  
  FormsModule
]
})
export class ItemCheckboxComponent {
  readonly id = input.required<string>();
  readonly master = input.required<SelectAllCheckboxComponent>();
  readonly checkable = input.required<Checkable>();
}
