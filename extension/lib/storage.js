import { normalizeStorageKey } from './page-key.js';

/** @typedef {object} ExtensionSettings
 * @property {string} metubeBaseUrl
 * @property {string} downloadType
 * @property {string} codec
 * @property {string} quality
 * @property {string} format
 * @property {string} folder
 * @property {string} customNamePrefix
 * @property {number} playlistItemLimit
 * @property {boolean} autoStart
 * @property {string} subtitleLanguage
 * @property {string} subtitleMode
 */

export const DEFAULT_SETTINGS = {
  metubeBaseUrl: 'http://localhost:8081/',
  downloadType: 'video',
  codec: 'auto',
  quality: 'best',
  format: 'any',
  folder: '',
  customNamePrefix: '',
  playlistItemLimit: 0,
  autoStart: true,
  subtitleLanguage: 'en',
  subtitleMode: 'prefer_manual',
};

/** @returns {Promise<ExtensionSettings>} */
export async function loadSettings() {
  const data = await chrome.storage.sync.get(DEFAULT_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...data };
}

/** @param {Partial<ExtensionSettings>} patch */
export async function saveSettings(patch) {
  await chrome.storage.sync.set(patch);
}

const CLIPS_KEY = 'clipDraftByUrl';

/** @param {string} pageUrlOrKey */
export function keyForPage(pageUrlOrKey) {
  if (pageUrlOrKey.startsWith('youtube:')) {
    return pageUrlOrKey;
  }
  return normalizeStorageKey(pageUrlOrKey);
}

/** @returns {Promise<Record<string, { start: string, end: string }[]>>} */
export async function loadAllClipDrafts() {
  const data = await chrome.storage.local.get(CLIPS_KEY);
  return data[CLIPS_KEY] || {};
}

/** @param {string} pageKey @param {{ start: string, end: string }[]} clips */
export async function saveClipDraft(pageKey, clips) {
  const all = await loadAllClipDrafts();
  all[pageKey] = clips;
  await chrome.storage.local.set({ [CLIPS_KEY]: all });
}

/** @param {string} pageKey */
export async function loadClipDraft(pageKey) {
  const all = await loadAllClipDrafts();
  return all[pageKey] ? [...all[pageKey]] : [];
}
