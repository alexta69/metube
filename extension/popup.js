import { loadSettings, saveClipDraft } from './lib/storage.js';

const statusEl = document.getElementById('status');
const pageUrlEl = document.getElementById('pageUrl');
const pendingEl = document.getElementById('pending');
const clipListEl = document.getElementById('clipList');
const btnStart = document.getElementById('btnStart');
const btnEnd = document.getElementById('btnEnd');
const btnQueueEach = document.getElementById('btnQueueEach');
const btnQueueMerge = document.getElementById('btnQueueMerge');
const btnCancelPending = document.getElementById('btnCancelPending');
const btnShowBar = document.getElementById('btnShowBar');
const optionsLink = document.getElementById('optionsLink');

let pageUrl = null;
let pageKey = null;
let clips = [];
let pendingStart = null;

optionsLink.href = chrome.runtime.getURL('options.html');
optionsLink.addEventListener('click', (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

function sendBg(action) {
  return chrome.runtime.sendMessage({ action });
}

function setStatus(text) {
  statusEl.textContent = text;
}

function renderClips() {
  clipListEl.innerHTML = '';
  clips.forEach((clip, index) => {
    const li = document.createElement('li');
    li.innerHTML = `<span>${clip.start} → ${clip.end}</span>`;
    const del = document.createElement('button');
    del.type = 'button';
    del.textContent = '×';
    del.addEventListener('click', async () => {
      clips.splice(index, 1);
      if (pageKey) await saveClipDraft(pageKey, clips);
      renderClips();
      updateButtons();
    });
    li.appendChild(del);
    clipListEl.appendChild(li);
  });
}

function updateButtons() {
  const hasClips = clips.length > 0;
  btnQueueEach.disabled = !pageUrl || !hasClips;
  btnQueueMerge.disabled = !pageUrl || clips.length < 2;
  if (btnCancelPending) {
    btnCancelPending.hidden = !pendingStart;
    btnCancelPending.disabled = !pendingStart;
  }
  if (btnEnd) btnEnd.disabled = !pendingStart;
  pendingEl.textContent = pendingStart ? `Start: ${pendingStart}` : '';
}

function applyFromState(state) {
  if (state?.pageUrl) {
    pageUrl = state.pageUrl;
    pageUrlEl.hidden = false;
    pageUrlEl.textContent = pageUrl;
  }
  if (state?.pageKey) pageKey = state.pageKey;
  if (state?.pendingStart) pendingStart = state.pendingStart;
  else if (state && 'pendingStart' in state) pendingStart = null;
  if (Array.isArray(state?.clips)) clips = [...state.clips];
}

async function refresh() {
  const state = await sendBg('getVideoState');

  if (state?.error === 'context_invalidated' || state?.hint === 'reload_tab') {
    setStatus('Extension wurde aktualisiert — diese Seite einmal neu laden (F5).');
    btnStart.disabled = true;
    btnEnd.disabled = true;
    return;
  }

  applyFromState(state);

  if (state?.ok) {
    setStatus(`Aktuell: ${state.formatted} — oder Leiste auf der Seite`);
    btnStart.disabled = false;
  } else if (pendingStart) {
    setStatus('Start saved — set end on the page bar or here');
    btnStart.disabled = false;
  } else if (clips.length) {
    setStatus(`${clips.length} clip(s) — queue below`);
    btnStart.disabled = false;
  } else {
    setStatus(state?.error === 'no_video' ? 'Kein Video — Seite neu laden' : 'Verbinde…');
    btnStart.disabled = !state?.pageUrl;
  }

  renderClips();
  updateButtons();
}

btnStart?.addEventListener('mousedown', (e) => {
  e.preventDefault();
  sendBg('markStart').then((res) => {
    if (res?.ok) applyFromState(res);
    else setStatus('Start fehlgeschlagen — Leiste unten rechts auf der Seite nutzen');
    updateButtons();
  });
});

btnEnd?.addEventListener('mousedown', (e) => {
  e.preventDefault();
  sendBg('markEnd').then((res) => {
    if (res?.ok) {
      if (res.clip) clips.push(res.clip);
      pendingStart = null;
      applyFromState(res);
      if (pageKey) saveClipDraft(pageKey, clips);
    }
    renderClips();
    updateButtons();
  });
});

btnCancelPending?.addEventListener('mousedown', (e) => {
  e.preventDefault();
  sendBg('clearPending').then(() => {
    pendingStart = null;
    updateButtons();
  });
});

btnShowBar?.addEventListener('click', () => {
  sendBg('showBar').then(() => setStatus('Leiste auf der Seite sollte sichtbar sein'));
});

btnQueueEach.addEventListener('click', () => sendQueue(false));
btnQueueMerge.addEventListener('click', () => sendQueue(true));

async function sendQueue(mergeClips) {
  const state = await sendBg('getVideoState');
  if (state?.pageUrl) pageUrl = state.pageUrl;
  if (Array.isArray(state?.clips) && state.clips.length) {
    clips = [...state.clips];
  }
  if (!pageUrl || !clips.length) {
    setStatus('No clips — set start/end first');
    return;
  }
  setStatus('Sende…');
  const result = await chrome.runtime.sendMessage({
    action: 'queueClips',
    pageUrl,
    clips,
    mergeClips,
  });
  setStatus(result?.ok ? 'Queued.' : `Error: ${result?.error || '?'}`);
}

refresh();
