import { Component, input } from '@angular/core';
import { MasterCheckboxComponent } from './master-checkbox.component';
import { Checkable } from '../interfaces';
import { FormsModule } from '@angular/forms';

@Component({
    selector: 'app-slave-checkbox',
    template: `
  <div class="form-check">
    <input type="checkbox" class="form-check-input" id="{{master().id()}}-{{id()}}-select" [(ngModel)]="checkable().checked" (change)="master().selectionChanged()">
    <label class="form-check-label" for="{{master().id()}}-{{id()}}-select"></label>
  </div>
`,
imports: [  
  FormsModule
]
})
export class SlaveCheckboxComponent {
  readonly id = input.required<string>();
  readonly master = input.required<MasterCheckboxComponent>();
  readonly checkable = input.required<Checkable>();
}
