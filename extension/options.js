import { DEFAULT_SETTINGS, loadSettings, saveSettings } from './lib/storage.js';

const fields = ['metubeBaseUrl', 'downloadType', 'quality', 'codec', 'format', 'autoStart'];

async function init() {
  const s = await loadSettings();
  for (const key of fields) {
    const el = document.getElementById(key);
    if (!el) continue;
    const val = s[key];
    if (el.tagName === 'SELECT') {
      el.value = String(val);
    } else {
      el.value = String(val ?? DEFAULT_SETTINGS[key] ?? '');
    }
  }
}

document.getElementById('save').addEventListener('click', async () => {
  /** @type {Record<string, unknown>} */
  const patch = {};
  for (const key of fields) {
    const el = document.getElementById(key);
    if (!el) continue;
    if (key === 'autoStart') {
      patch[key] = el.value === 'true';
    } else {
      patch[key] = el.value;
    }
  }
  await saveSettings(patch);
  const saved = document.getElementById('saved');
  saved.hidden = false;
  setTimeout(() => { saved.hidden = true; }, 2000);
});

init();
