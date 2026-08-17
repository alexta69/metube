import { Component, input, ChangeDetectionStrategy } from '@angular/core';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { Checkable } from '../interfaces';
import { FormsModule } from '@angular/forms';

@Component({
    selector: 'app-item-checkbox',
    template: `
  <div class="form-check">
    <input type="checkbox" class="form-check-input" id="{{master().id()}}-{{id()}}-select" [(ngModel)]="checkable().checked" (click)="clicked($event)" (change)="changed()" [attr.aria-label]="'Select item ' + id()">
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

  // click fires before change, so the modifier is recorded here and read once
  // ngModel has written the new state into the checkable. Keyboard activation
  // fires change without a click, which is a plain toggle.
  private extend = false;

  clicked(event: MouseEvent) {
    this.extend = event.shiftKey;
  }

  changed() {
    const extend = this.extend;
    this.extend = false;
    this.master().selectionChanged(this.id(), extend);
  }
}
