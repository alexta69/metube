import { Component, ElementRef, viewChild, output, input, ChangeDetectionStrategy } from "@angular/core";
import { Checkable } from "../interfaces";
import { FormsModule } from "@angular/forms";

@Component({
    selector: 'app-select-all-checkbox',
    template: `
  <div class="form-check">
    <input type="checkbox" class="form-check-input" id="{{id()}}-select-all" #masterCheckbox [(ngModel)]="selected" (change)="clicked()" [attr.aria-label]="'Select all ' + id() + ' items'">
    <label class="form-check-label visually-hidden" for="{{id()}}-select-all">Select all</label>
  </div>
`,
    // Shared Checkable objects are mutated in place; Eager preserves pre-v22 behavior.
    // eslint-disable-next-line @angular-eslint/prefer-on-push-component-change-detection
    changeDetection: ChangeDetectionStrategy.Eager,
    imports: [
  FormsModule
]
})
export class SelectAllCheckboxComponent {
  readonly id = input.required<string>();
  readonly list = input.required<Map<string, Checkable>>();
  // The ids in the order the rows are rendered. The done list is sorted for
  // display, so its order is not the map's insertion order, and a range
  // selection has to follow what the user sees. Left unset, the map order is
  // the rendered order.
  readonly orderedIds = input<string[] | null>(null);
  readonly changed = output<number>();

  readonly masterCheckbox = viewChild.required<ElementRef>('masterCheckbox');
  selected!: boolean;

  // The item a range extends from: the last one toggled on its own.
  private anchorId: string | null = null;

  clicked() {
    this.list().forEach(item => item.checked = this.selected);
    // Select-all is not a position, so there is nothing to extend from next.
    this.anchorId = null;
    this.selectionChanged();
  }

  selectionChanged(id?: string, extend = false) {
    if (id !== undefined) {
      if (extend && this.anchorId !== null && this.anchorId !== id) {
        this.applyRange(this.anchorId, id);
      }
      this.anchorId = id;
    }
    const masterCheckbox = this.masterCheckbox();
    if (!masterCheckbox)
      return;
    let checked = 0;
    this.list().forEach(item => { if(item.checked) checked++ });
    this.selected = checked > 0 && checked === this.list().size;
    masterCheckbox.nativeElement.indeterminate = checked > 0 && checked < this.list().size;
    this.changed.emit(checked);
  }

  // Everything between the anchor and the just-clicked row takes the state the
  // click produced, so shift-clicking a checked box clears the range and
  // shift-clicking an unchecked one fills it.
  private applyRange(fromId: string, toId: string) {
    const ids = this.orderedIds() ?? Array.from(this.list().keys());
    const from = ids.indexOf(fromId);
    const to = ids.indexOf(toId);
    // A row can disappear between two clicks (a download finishing moves it
    // from the queue to the done list); without both ends there is no range.
    if (from < 0 || to < 0) {
      return;
    }
    const target = this.list().get(toId)?.checked ?? false;
    const start = Math.min(from, to);
    const end = Math.max(from, to);
    for (let i = start; i <= end; i++) {
      const item = this.list().get(ids[i]);
      if (item) {
        item.checked = target;
      }
    }
  }
}
