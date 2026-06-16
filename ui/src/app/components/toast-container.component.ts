import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { faCheckCircle, faTimesCircle, faInfoCircle, faXmark } from '@fortawesome/free-solid-svg-icons';
import { ToastService } from '../services/toast.service';

@Component({
  selector: 'app-toast-container',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FontAwesomeModule],
  template: `
<div class="toast-container position-fixed top-0 end-0 p-3" style="z-index: 1100;" aria-live="polite" aria-atomic="true">
  @for (toast of toasts.toasts(); track toast.id) {
    <div class="toast show align-items-center border-0 mb-2"
      [class.text-bg-danger]="toast.level === 'error'"
      [class.text-bg-success]="toast.level === 'success'"
      [class.text-bg-primary]="toast.level === 'info'"
      role="alert" aria-live="assertive" aria-atomic="true">
      <div class="d-flex">
        <div class="toast-body d-flex align-items-start gap-2">
          @if (toast.level === 'error') {
            <fa-icon [icon]="faTimesCircle" class="mt-1" />
          } @else if (toast.level === 'success') {
            <fa-icon [icon]="faCheckCircle" class="mt-1" />
          } @else {
            <fa-icon [icon]="faInfoCircle" class="mt-1" />
          }
          <span style="white-space: pre-line;">{{ toast.message }}</span>
        </div>
        @if (!toast.actions) {
          <button type="button" class="btn-close btn-close-white me-2 m-auto"
            aria-label="Close" (click)="toasts.dismiss(toast.id)"></button>
        }
      </div>
      @if (toast.actions) {
        <div class="d-flex justify-content-end gap-2 px-3 pb-2">
          @for (action of toast.actions; track action.label) {
            <button type="button"
              class="btn btn-sm"
              [class.btn-light]="!action.primary"
              [class.btn-outline-light]="action.primary"
              (click)="toasts.respond(toast.id, action.value)">
              {{ action.label }}
            </button>
          }
        </div>
      }
    </div>
  }
</div>
`,
})
export class ToastContainerComponent {
  protected readonly toasts = inject(ToastService);
  protected readonly faCheckCircle = faCheckCircle;
  protected readonly faTimesCircle = faTimesCircle;
  protected readonly faInfoCircle = faInfoCircle;
  protected readonly faXmark = faXmark;
}
