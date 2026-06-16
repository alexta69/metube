import { Injectable, signal } from '@angular/core';

export type ToastLevel = 'info' | 'success' | 'error';

export interface ToastAction {
  label: string;
  value: boolean;
  primary?: boolean;
}

export interface Toast {
  id: number;
  level: ToastLevel;
  message: string;
  actions?: ToastAction[];
  /** Resolver for confirm() toasts; resolved when the user picks an action or dismisses. */
  _resolve?: (value: boolean) => void;
}

/**
 * Lightweight non-blocking notification service. Replaces the blocking
 * window.alert()/confirm() dialogs that previously littered the app component.
 */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private counter = 0;
  readonly toasts = signal<Toast[]>([]);

  info(message: string): void {
    this.show('info', message, 4000);
  }

  success(message: string): void {
    this.show('success', message, 4000);
  }

  error(message: string): void {
    this.show('error', message, 8000);
  }

  /**
   * Show a confirmation toast with confirm/cancel actions. Resolves true when
   * confirmed, false when cancelled or auto-dismissed.
   */
  confirm(message: string, confirmLabel = 'OK', cancelLabel = 'Cancel'): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      const id = ++this.counter;
      this.toasts.update((list) => [
        ...list,
        {
          id,
          level: 'info',
          message,
          actions: [
            { label: cancelLabel, value: false },
            { label: confirmLabel, value: true, primary: true },
          ],
          _resolve: resolve,
        },
      ]);
    });
  }

  respond(id: number, value: boolean): void {
    const toast = this.toasts().find((t) => t.id === id);
    toast?._resolve?.(value);
    this.remove(id);
  }

  dismiss(id: number): void {
    const toast = this.toasts().find((t) => t.id === id);
    // A confirm toast dismissed without an explicit choice resolves to false.
    toast?._resolve?.(false);
    this.remove(id);
  }

  private remove(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }

  private show(level: ToastLevel, message: string, autoDismissMs: number): void {
    const id = ++this.counter;
    this.toasts.update((list) => [...list, { id, level, message }]);
    setTimeout(() => this.remove(id), autoDismissMs);
  }
}
