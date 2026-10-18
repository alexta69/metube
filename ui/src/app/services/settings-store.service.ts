import { inject, Injectable } from '@angular/core';
import { CookieService } from 'ngx-cookie-service';

/**
 * The UI's remembered form choices and view state, kept in localStorage.
 *
 * These used to be cookies, which the browser attaches to every request to
 * MeTube, each file download included. Together they ran to a couple of
 * dozen values, two of them JSON (the per-type selections and the custom
 * yt-dlp options), and a long enough set pushed the request headers past the
 * server's 8 KiB limit, after which every request, the page itself included,
 * was refused with a 400. A value still in a cookie from an earlier version
 * is moved over the first time it is read.
 *
 * Where localStorage is unavailable (disabled, or a sandboxed frame) the
 * values stay in cookies, as before. The theme is not stored here: the server
 * reads that cookie to apply DEFAULT_THEME.
 */
@Injectable({ providedIn: 'root' })
export class SettingsStore {
  private cookies = inject(CookieService);
  private readonly storage = SettingsStore.openStorage();
  private static readonly COOKIE_EXPIRY_DAYS = 3650;

  get(key: string): string {
    return this.read(key) ?? '';
  }

  has(key: string): boolean {
    return this.read(key) !== null;
  }

  set(key: string, value: string): void {
    if (this.storage) {
      try {
        this.storage.setItem(key, value);
        // A cookie an earlier version left under this name would otherwise
        // ride along on every request for as long as it was never read.
        if (this.cookies.check(key)) {
          this.cookies.delete(key);
        }
        return;
      } catch {
        // Quota exceeded: fall back to the cookie rather than lose the value.
      }
    }
    this.cookies.set(key, value, { expires: SettingsStore.COOKIE_EXPIRY_DAYS });
  }

  private read(key: string): string | null {
    if (!this.storage) {
      return this.cookies.check(key) ? this.cookies.get(key) : null;
    }
    const stored = this.storage.getItem(key);
    if (stored !== null) {
      return stored;
    }
    if (!this.cookies.check(key)) {
      return null;
    }
    const legacy = this.cookies.get(key);
    try {
      this.storage.setItem(key, legacy);
      this.cookies.delete(key);
    } catch {
      // Keep reading the cookie; nothing is lost.
    }
    return legacy;
  }

  private static openStorage(): Storage | null {
    try {
      const storage = window.localStorage;
      const probe = '__metube_probe__';
      storage.setItem(probe, probe);
      storage.removeItem(probe);
      return storage;
    } catch {
      return null;
    }
  }
}
