/**
 * Stable key for clip drafts / pending start (URL bar may gain &t=, www/m., etc.).
 * @param {string} href
 */
export function normalizeStorageKey(href) {
  try {
    const u = new URL(href);
    const host = u.hostname.replace(/^www\./, '').replace(/^m\./, '');

    if (host === 'youtu.be') {
      const id = u.pathname.split('/').filter(Boolean)[0];
      if (id) {
        return `youtube:${id}`;
      }
    }
    if (host === 'youtube.com' || host.endsWith('.youtube.com')) {
      const id = u.searchParams.get('v');
      if (id) {
        return `youtube:${id}`;
      }
    }

    u.hash = '';
    return `${u.origin}${u.pathname}${u.search}`;
  } catch {
    return href;
  }
}

/** URL sent to MeTube (no hash; strip &t= on YouTube when we send explicit clips). */
export function pageUrlForMeTube(href) {
  try {
    const u = new URL(href);
    u.hash = '';
    const host = u.hostname.replace(/^www\./, '').replace(/^m\./, '');
    if (host === 'youtube.com' || host.endsWith('.youtube.com') || host === 'youtu.be') {
      u.searchParams.delete('t');
      u.searchParams.delete('start');
    }
    return u.toString();
  } catch {
    return href;
  }
}
