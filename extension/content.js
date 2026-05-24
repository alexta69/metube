const CLIPS_KEY = 'clipDraftByUrl';

let contextTeardownDone = false;
let navIntervalId = null;
let syncIntervalId = null;

/** After extension reload, old tabs must refresh (F5). */
function isExtensionContextValid() {
  try {
    return typeof chrome !== 'undefined' && !!chrome.runtime?.id;
  } catch {
    return false;
  }
}

function handleInvalidExtensionContext() {
  if (contextTeardownDone) {
    return true;
  }
  if (isExtensionContextValid()) {
    return false;
  }
  contextTeardownDone = true;
  if (navIntervalId != null) {
    clearInterval(navIntervalId);
    navIntervalId = null;
  }
  if (syncIntervalId != null) {
    clearInterval(syncIntervalId);
    syncIntervalId = null;
  }
  if (overlayRoot) {
    try {
      overlayRoot.remove();
    } catch {
      /* ignore */
    }
    overlayRoot = null;
  }
  if (!document.getElementById('metube-reload-hint')) {
    const hint = document.createElement('div');
    hint.id = 'metube-reload-hint';
    hint.textContent = 'MeTube extension updated — reload this page (F5)';
    hint.style.cssText =
      'position:fixed;bottom:12px;right:12px;z-index:2147483647;padding:10px 14px;' +
      'background:#b02a37;color:#fff;border-radius:8px;font:13px system-ui,sans-serif;' +
      'box-shadow:0 4px 12px rgba(0,0,0,.4);max-width:280px;';
    document.documentElement.appendChild(hint);
  }
  return true;
}

function isFiniteNum(x) {
  return typeof x === 'number' && x === x && x !== Infinity && x !== -Infinity;
}

/** chrome.storage.local — always via callback (content scripts). */
function mtStorageLocalGet(keys) {
  if (handleInvalidExtensionContext()) {
    return Promise.resolve({});
  }
  return new Promise((resolve) => {
    if (!chrome?.storage?.local) {
      resolve({});
      return;
    }
    try {
      chrome.storage.local.get(keys, (data) => {
        if (handleInvalidExtensionContext()) {
          resolve({});
          return;
        }
        resolve(chrome.runtime.lastError ? {} : data || {});
      });
    } catch {
      handleInvalidExtensionContext();
      resolve({});
    }
  });
}

function mtStorageLocalSet(items) {
  if (handleInvalidExtensionContext()) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    if (!chrome?.storage?.local) {
      resolve();
      return;
    }
    try {
      chrome.storage.local.set(items, () => {
        resolve();
      });
    } catch {
      handleInvalidExtensionContext();
      resolve();
    }
  });
}

function mtStorageLocalRemove(keys) {
  if (handleInvalidExtensionContext()) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    if (!chrome?.storage?.local) {
      resolve();
      return;
    }
    try {
      chrome.storage.local.remove(keys, () => {
        resolve();
      });
    } catch {
      handleInvalidExtensionContext();
      resolve();
    }
  });
}

function normalizeStorageKey(href) {
  try {
    const u = new URL(href);
    const host = u.hostname.replace(/^www\./, '').replace(/^m\./, '');
    if (host === 'youtu.be') {
      const id = u.pathname.split('/').filter(Boolean)[0];
      if (id) return `youtube:${id}`;
    }
    if (host === 'youtube.com' || host.endsWith('.youtube.com')) {
      const id = u.searchParams.get('v');
      if (id) return `youtube:${id}`;
    }
    u.hash = '';
    return `${u.origin}${u.pathname}${u.search}`;
  } catch {
    return href;
  }
}

function pageUrlForMeTube(href) {
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

function safeVideoTime(video) {
  if (!video || !video.isConnected) {
    return 0;
  }
  if (typeof HTMLVideoElement !== 'undefined' && !(video instanceof HTMLVideoElement)) {
    return 0;
  }
  try {
    if (video.readyState < 1) {
      return 0;
    }
    const t = video.currentTime;
    return isFiniteNum(t) && t >= 0 ? t : 0;
  } catch {
    return 0;
  }
}

function formatClipTime(seconds) {
  const n = typeof seconds === 'number' ? seconds : parseFloat(String(seconds));
  if (!isFiniteNum(n) || n < 0) {
    return '0:00';
  }
  const total = Math.floor(n);
  const s = total % 60;
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${m}:${String(s).padStart(2, '0')}`;
}

function videoArea(v) {
  try {
    if (!v?.isConnected) return 0;
    return v.clientWidth * v.clientHeight;
  } catch {
    return 0;
  }
}

function getActiveVideo() {
  let candidates = [];
  try {
    candidates = Array.from(document.querySelectorAll('video')).filter((v) => {
      try {
        return v.isConnected && v.readyState >= 1;
      } catch {
        return false;
      }
    });
  } catch {
    return null;
  }
  if (!candidates.length) {
    return null;
  }
  return candidates.reduce((best, v) => (videoArea(v) > videoArea(best) ? v : best));
}

function shouldShowBar() {
  const v = getActiveVideo();
  if (!v) return false;
  try {
    if (window.top === window.self) return true;
  } catch {
    return true;
  }
  return v.clientWidth >= 240 && v.clientHeight >= 135;
}

let pendingStart = null;
let overlayRoot = null;
let sessionBarHidden = false;
/** @type {Record<string, { start: string, end: string }[]>} */
const sessionClipsByKey = {};

function storageKey() {
  return normalizeStorageKey(location.href);
}

function pendingStorageItemKey() {
  return `pending:${storageKey()}`;
}

function loadPendingFromStorage() {
  const key = pendingStorageItemKey();
  return mtStorageLocalGet(key).then((data) => {
    const value = data[key];
    return typeof value === 'string' && value ? value : null;
  });
}

function savePendingToStorage(value) {
  const key = pendingStorageItemKey();
  if (value) {
    return mtStorageLocalSet({ [key]: value });
  }
  return mtStorageLocalRemove(key);
}

function ensurePendingLoaded() {
  if (pendingStart) {
    return Promise.resolve(pendingStart);
  }
  return loadPendingFromStorage().then((stored) => {
    pendingStart = stored;
    return pendingStart;
  });
}

async function loadClipsForPage() {
  const key = storageKey();
  if (sessionClipsByKey[key]?.length) {
    return [...sessionClipsByKey[key]];
  }
  const data = await mtStorageLocalGet(CLIPS_KEY);
  const all = data[CLIPS_KEY] || {};
  const list = all[key] ? [...all[key]] : [];
  sessionClipsByKey[key] = list;
  return list;
}

async function appendClip(clip) {
  const key = storageKey();
  const list = sessionClipsByKey[key] ? [...sessionClipsByKey[key]] : [];
  list.push(clip);
  sessionClipsByKey[key] = list;
  const data = await mtStorageLocalGet(CLIPS_KEY);
  const all = data[CLIPS_KEY] || {};
  all[key] = list;
  await mtStorageLocalSet({ [CLIPS_KEY]: all });
  return list;
}

function updateOverlayUiNow() {
  if (!overlayRoot) return;
  const statusEl = overlayRoot.querySelector('[data-role="status"]');
  const btnEnd = overlayRoot.querySelector('[data-action="end"]');
  const btnClear = overlayRoot.querySelector('[data-action="clear"]');
  if (!statusEl || !btnEnd || !btnClear) return;
  btnEnd.disabled = !pendingStart;
  btnClear.hidden = !pendingStart;
  const key = storageKey();
  const clipCount = sessionClipsByKey[key]?.length ?? 0;
  if (pendingStart) {
    statusEl.textContent = `Start ${pendingStart} — seek to end, then End`;
  } else if (clipCount > 0) {
    statusEl.textContent = `${clipCount} clip(s) — open extension popup to queue`;
  } else {
    const v = getActiveVideo();
    statusEl.textContent = v ? `Jetzt: ${formatClipTime(safeVideoTime(v))}` : 'Kein Video';
  }
}

function doMarkStart() {
  const video = getActiveVideo();
  if (!video) {
    return Promise.resolve({ ok: false, error: 'no_video' });
  }
  pendingStart = formatClipTime(safeVideoTime(video));
  updateOverlayUiNow();
  return savePendingToStorage(pendingStart).then(() => {
    updateOverlayUiNow();
    syncOverlayState();
    return {
      ok: true,
      pendingStart,
      pageUrl: pageUrlForMeTube(location.href),
      pageKey: storageKey(),
    };
  });
}

function doMarkEnd() {
  return ensurePendingLoaded().then((start) => {
    const video = getActiveVideo();
    if (!video) {
      return { ok: false, error: 'no_video' };
    }
    if (!start) {
      return { ok: false, error: 'no_pending_start' };
    }
    const end = formatClipTime(safeVideoTime(video));
    const clip = { start, end };
    pendingStart = null;
    updateOverlayUiNow();
    return savePendingToStorage(null)
      .then(() => appendClip(clip))
      .then((clips) => {
        updateOverlayUiNow();
        syncOverlayState();
        return {
          ok: true,
          clip,
          clips,
          pageUrl: pageUrlForMeTube(location.href),
          pageKey: storageKey(),
        };
      });
  });
}

function doClearPending() {
  pendingStart = null;
  updateOverlayUiNow();
  return savePendingToStorage(null).then(() => {
    updateOverlayUiNow();
    return { ok: true };
  });
}

function getVideoStateResponse() {
  const pageUrl = pageUrlForMeTube(location.href);
  const pageKey = storageKey();
  return ensurePendingLoaded().then(async (pending) => {
    const clips = await loadClipsForPage();
    const video = getActiveVideo();
    if (!video) {
      return {
        ok: false,
        error: 'no_video',
        pageUrl,
        pageKey,
        pendingStart: pending,
        clips,
      };
    }
    return {
      ok: true,
      currentTime: safeVideoTime(video),
      duration: isFiniteNum(video.duration) ? video.duration : 0,
      formatted: formatClipTime(safeVideoTime(video)),
      pageUrl,
      pageKey,
      pendingStart: pending,
      clips,
    };
  });
}

function injectOverlayStyles() {
  if (document.getElementById('metube-clip-bar-style')) return;
  const style = document.createElement('style');
  style.id = 'metube-clip-bar-style';
  style.textContent = `
    #metube-clip-bar {
      position: fixed;
      right: 12px;
      bottom: 72px;
      z-index: 2147483647;
      isolation: isolate;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      max-width: min(420px, calc(100vw - 24px));
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(20, 20, 24, 0.92);
      color: #f2f2f2;
      font: 12px/1.3 system-ui, sans-serif;
      box-shadow: 0 4px 20px rgba(0,0,0,0.45);
      pointer-events: auto;
      user-select: none;
    }
    #metube-clip-bar button {
      cursor: pointer;
      border: 1px solid #555;
      border-radius: 6px;
      padding: 6px 10px;
      background: #2d2d35;
      color: #fff;
      font: inherit;
      pointer-events: auto;
      position: relative;
      z-index: 1;
    }
    #metube-clip-bar button:hover:not(:disabled) {
      background: #3d3d48;
    }
    #metube-clip-bar button:disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }
    #metube-clip-bar button.metube-primary {
      background: #0d6efd;
      border-color: #0d6efd;
    }
    #metube-clip-bar .metube-status {
      flex: 1 1 100%;
      color: #9ecbff;
      min-height: 1.2em;
    }
    #metube-clip-bar .metube-hide {
      padding: 4px 8px;
      font-size: 11px;
    }
  `;
  (document.head || document.documentElement).appendChild(style);
}

function ensureOverlay() {
  if (overlayRoot || !shouldShowBar()) return;
  injectOverlayStyles();
  const bar = document.createElement('div');
  bar.id = 'metube-clip-bar';
  bar.innerHTML = `
    <button type="button" class="metube-primary" data-action="start">Start</button>
    <button type="button" data-action="end" disabled>End</button>
    <button type="button" data-action="clear" hidden>Cancel</button>
    <span class="metube-status" data-role="status"></span>
    <button type="button" class="metube-hide" data-action="hide" title="Hide bar">✕</button>
  `;

  function bindBarButton(selector, handler) {
    const btn = bar.querySelector(selector);
    let busy = false;
    btn.addEventListener(
      'click',
      (e) => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        if (busy) return;
        busy = true;
        Promise.resolve(handler(e)).finally(() => {
          busy = false;
        });
      },
      true,
    );
  }

  bindBarButton('[data-action="start"]', () => {
    doMarkStart().catch(() => updateOverlayUiNow());
  });

  bindBarButton('[data-action="end"]', () => {
    doMarkEnd().catch(() => updateOverlayUiNow());
  });

  bindBarButton('[data-action="clear"]', () => {
    doClearPending().catch(() => updateOverlayUiNow());
  });

  bindBarButton('[data-action="hide"]', () => {
    sessionBarHidden = true;
    bar.remove();
    overlayRoot = null;
    mtStorageLocalSet({ metubeBarHidden: true });
  });

  document.documentElement.appendChild(bar);
  overlayRoot = bar;
  syncOverlayState();
}

function syncOverlayState() {
  if (!overlayRoot) return;
  try {
    const statusEl = overlayRoot.querySelector('[data-role="status"]');
    const btnEnd = overlayRoot.querySelector('[data-action="end"]');
    const btnClear = overlayRoot.querySelector('[data-action="clear"]');
    ensurePendingLoaded()
      .then(async (pending) => {
        const clips = await loadClipsForPage();
        btnEnd.disabled = !pending;
        btnClear.hidden = !pending;
        if (pending) {
          statusEl.textContent = `Start ${pending} — seek to end, then End`;
        } else if (clips.length) {
          statusEl.textContent = `${clips.length} clip(s) — open extension popup to queue`;
        } else {
          const v = getActiveVideo();
          statusEl.textContent = v
            ? `Jetzt: ${formatClipTime(safeVideoTime(v))}`
            : 'Kein Video';
        }
      })
      .catch(() => {
        if (statusEl) statusEl.textContent = 'Video nicht bereit';
      });
  } catch {
    /* ignore — some players break DOM access */
  }
}

function initBar() {
  if (sessionBarHidden) return;
  mtStorageLocalGet('metubeBarHidden').then((data) => {
    if (data.metubeBarHidden || sessionBarHidden) return;
    if (shouldShowBar()) {
      ensureOverlay();
      return;
    }
    const obs = new MutationObserver(() => {
      if (shouldShowBar()) {
        obs.disconnect();
        ensureOverlay();
      }
    });
    obs.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => obs.disconnect(), 60000);
  });
}

let lastHref = location.href;
navIntervalId = setInterval(() => {
  if (handleInvalidExtensionContext()) {
    return;
  }
  if (location.href !== lastHref) {
    lastHref = location.href;
    pendingStart = null;
    if (overlayRoot) syncOverlayState();
    else initBar();
  }
}, 800);

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (handleInvalidExtensionContext()) {
    sendResponse({ ok: false, error: 'context_invalidated', hint: 'reload_tab' });
    return true;
  }
  if (msg?.action === 'getVideoState') {
    getVideoStateResponse().then(sendResponse);
    return true;
  }
  if (msg?.action === 'markStart') {
    doMarkStart().then(sendResponse);
    return true;
  }
  if (msg?.action === 'markEnd') {
    doMarkEnd().then(sendResponse);
    return true;
  }
  if (msg?.action === 'clearPending') {
    doClearPending().then(sendResponse);
    return true;
  }
  if (msg?.action === 'showBar') {
    mtStorageLocalSet({ metubeBarHidden: false }).then(() => {
      initBar();
      sendResponse({ ok: true });
    });
    return true;
  }
  return false;
});

if (!handleInvalidExtensionContext()) {
  initBar();
}
syncIntervalId = setInterval(() => {
  if (handleInvalidExtensionContext()) {
    return;
  }
  if (!overlayRoot && shouldShowBar()) {
    mtStorageLocalGet('metubeBarHidden').then((d) => {
      if (!d.metubeBarHidden) ensureOverlay();
    });
  } else if (overlayRoot) {
    syncOverlayState();
  }
}, 2000);
