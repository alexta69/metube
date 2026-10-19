import { TestBed } from '@angular/core/testing';
import { CookieService } from 'ngx-cookie-service';
import { SettingsStore } from './settings-store.service';

class CookieServiceStub {
  jar = new Map<string, string>();
  get(name: string) {
    return this.jar.get(name) ?? '';
  }
  set(name: string, value: string) {
    this.jar.set(name, value);
  }
  check(name: string) {
    return this.jar.has(name);
  }
  delete(name: string) {
    this.jar.delete(name);
  }
}

describe('SettingsStore', () => {
  let cookies: CookieServiceStub;

  function create(): SettingsStore {
    return TestBed.inject(SettingsStore);
  }

  beforeEach(() => {
    localStorage.clear();
    cookies = new CookieServiceStub();
    TestBed.configureTestingModule({
      providers: [{ provide: CookieService, useValue: cookies }],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('stores values in localStorage, not in cookies', () => {
    const store = create();
    store.set('metube_format', 'mp4');
    expect(localStorage.getItem('metube_format')).toBe('mp4');
    expect(cookies.check('metube_format')).toBe(false);
    expect(store.get('metube_format')).toBe('mp4');
    expect(store.has('metube_format')).toBe(true);
  });

  it('reports a missing key as absent and empty', () => {
    const store = create();
    expect(store.has('metube_codec')).toBe(false);
    expect(store.get('metube_codec')).toBe('');
  });

  it('moves a value saved as a cookie by an earlier version on first read', () => {
    cookies.set('metube_ytdl_options_overrides', '{"writesubtitles": true}');
    const store = create();

    expect(store.get('metube_ytdl_options_overrides')).toBe('{"writesubtitles": true}');
    expect(localStorage.getItem('metube_ytdl_options_overrides')).toBe('{"writesubtitles": true}');
    expect(cookies.check('metube_ytdl_options_overrides')).toBe(false);
  });

  it('drops a leftover cookie when the value is written', () => {
    cookies.set('metube_sort_ascending', 'true');
    create().set('metube_sort_ascending', 'false');
    expect(cookies.check('metube_sort_ascending')).toBe(false);
    expect(localStorage.getItem('metube_sort_ascending')).toBe('false');
  });

  it('prefers the stored value over a leftover cookie', () => {
    localStorage.setItem('metube_quality', '720');
    cookies.set('metube_quality', '1080');
    expect(create().get('metube_quality')).toBe('720');
  });

  it('falls back to cookies when localStorage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    const store = create();
    store.set('metube_format', 'mp4');
    expect(cookies.get('metube_format')).toBe('mp4');
    expect(store.get('metube_format')).toBe('mp4');
  });
});
