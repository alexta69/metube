import { TestBed } from '@angular/core/testing';
import { ToastService } from './toast.service';

describe('ToastService', () => {
  let service: ToastService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [ToastService] });
    service = TestBed.inject(ToastService);
  });

  it('choose() resolves with the responded action value', async () => {
    const promise = service.choose('Pick one', [
      { label: 'A', value: 'a' },
      { label: 'B', value: 'b', primary: true },
    ]);
    const toast = service.toasts()[0];
    service.respond(toast.id, 'b');
    await expect(promise).resolves.toBe('b');
  });

  it('dismiss() on a choose() toast resolves null', async () => {
    const promise = service.choose('Pick one', [
      { label: 'A', value: 'a' },
      { label: 'B', value: 'b', primary: true },
    ]);
    const toast = service.toasts()[0];
    service.dismiss(toast.id);
    await expect(promise).resolves.toBeNull();
  });

  it('confirm() resolves true when the confirm action is chosen', async () => {
    const promise = service.confirm('Are you sure?');
    const toast = service.toasts()[0];
    const confirmAction = toast.actions?.find((a) => a.primary);
    service.respond(toast.id, confirmAction?.value);
    await expect(promise).resolves.toBe(true);
  });

  it('confirm() resolves false when the cancel action is chosen', async () => {
    const promise = service.confirm('Are you sure?');
    const toast = service.toasts()[0];
    const cancelAction = toast.actions?.find((a) => !a.primary);
    service.respond(toast.id, cancelAction?.value);
    await expect(promise).resolves.toBe(false);
  });

  it('confirm() resolves false when dismissed', async () => {
    const promise = service.confirm('Are you sure?');
    const toast = service.toasts()[0];
    service.dismiss(toast.id);
    await expect(promise).resolves.toBe(false);
  });

  it('removes the toast once responded to', () => {
    service.choose('Pick one', [{ label: 'A', value: 'a' }]);
    const toast = service.toasts()[0];
    service.respond(toast.id, 'a');
    expect(service.toasts()).toEqual([]);
  });
});
