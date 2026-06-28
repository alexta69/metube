import { Component, input, ChangeDetectionStrategy } from '@angular/core';
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
    // Shared Checkable objects are mutated in place; Eager preserves pre-v22 behavior.
    // eslint-disable-next-line @angular-eslint/prefer-on-push-component-change-detection
    changeDetection: ChangeDetectionStrategy.Eager,
    imports: [  
  FormsModule
]
})
export class ItemCheckboxComponent {
  readonly id = input.required<string>();
  readonly master = input.required<SelectAllCheckboxComponent>();
  readonly checkable = input.required<Checkable>();
}
