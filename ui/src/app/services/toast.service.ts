import { Injectable, signal } from '@angular/core';

export type ToastLevel = 'info' | 'success' | 'error';

export interface ToastAction {
  label: string;
  value: unknown;
  primary?: boolean;
}

export interface Toast {
  id: number;
  level: ToastLevel;
  message: string;
  actions?: ToastAction[];
  /** Resolver for choose()/confirm(); resolved when the user picks an action or dismisses. */
  _resolve?: (value: unknown) => void;
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
   * Show an info toast with custom action buttons. Resolves with the chosen
   * action's value, or null if the toast is dismissed without a choice.
   */
  choose<T>(
    message: string,
    actions: { label: string; value: T; primary?: boolean }[],
  ): Promise<T | null> {
    return new Promise<T | null>((resolve) => {
      const id = ++this.counter;
      this.toasts.update((list) => [
        ...list,
        {
          id,
          level: 'info',
          message,
          actions,
          _resolve: resolve as (value: unknown) => void,
        },
      ]);
    });
  }

  /**
   * Show a confirmation toast with confirm/cancel actions. Resolves true when
   * confirmed, false when cancelled or auto-dismissed.
   */
  confirm(message: string, confirmLabel = 'OK', cancelLabel = 'Cancel'): Promise<boolean> {
    return this.choose(message, [
      { label: cancelLabel, value: false },
      { label: confirmLabel, value: true, primary: true },
    ]).then((value) => value ?? false);
  }

  respond(id: number, value: unknown): void {
    const toast = this.toasts().find((t) => t.id === id);
    toast?._resolve?.(value);
    this.remove(id);
  }

  dismiss(id: number): void {
    const toast = this.toasts().find((t) => t.id === id);
    // A choose()/confirm() toast dismissed without an explicit choice resolves to null.
    toast?._resolve?.(null);
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
