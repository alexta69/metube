import { apiUrl, buildQueueBody } from './lib/metube-api.js';
import { loadSettings } from './lib/storage.js';

async function getActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.id;
}

async function sendToTab(tabId, payload) {
  try {
    return await chrome.tabs.sendMessage(tabId, payload);
  } catch (err) {
    const msg = String(err?.message || err);
    if (msg.includes('Receiving end does not exist')) {
      return { ok: false, error: 'no_content_script', hint: 'reload_tab' };
    }
    return { ok: false, error: msg };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.action === 'queueClips') {
    queueClips(msg.pageUrl, msg.clips, msg.mergeClips)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err?.message || err) }));
    return true;
  }

  const tabActions = ['getVideoState', 'markStart', 'markEnd', 'clearPending', 'showBar'];
  if (tabActions.includes(msg?.action)) {
    (async () => {
      const tabId = msg.tabId ?? (await getActiveTabId());
      if (!tabId) {
        sendResponse({ ok: false, error: 'no_tab' });
        return;
      }
      const result = await sendToTab(tabId, { action: msg.action });
      sendResponse(result);
    })();
    return true;
  }

  return false;
});

async function queueClips(pageUrl, clips, mergeClips) {
  if (!clips?.length) {
    return { ok: false, error: 'no_clips' };
  }
  const settings = await loadSettings();
  const { endpoint, body } = buildQueueBody(settings, pageUrl, clips, !!mergeClips);
  const url = apiUrl(settings.metubeBaseUrl, endpoint);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    return { ok: false, error: text || res.statusText };
  }
  return { ok: true, body: text };
}
