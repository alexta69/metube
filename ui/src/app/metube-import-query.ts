export interface ImportClip {
  start: string;
  end: string;
}

export interface MetubeImportParams {
  url: string;
  clips: ImportClip[];
  mergeClips?: boolean;
}

/** Parse `?url=…&clips=…` from extension deep links. */
export function parseMetubeImportFromSearch(search: string): MetubeImportParams | null {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  if (!raw.trim()) {
    return null;
  }
  const params = new URLSearchParams(raw);
  const url = params.get('url')?.trim();
  if (!url) {
    return null;
  }
  const clips = parseClipsParam(params.get('clips'));
  const mergeRaw = params.get('merge')?.trim().toLowerCase();
  const mergeClips = mergeRaw === '1' || mergeRaw === 'true' || mergeRaw === 'yes';
  return { url, clips, mergeClips: mergeClips || undefined };
}

/** Parse `#mt=…` (base64url JSON) — preferred for extension handoff. */
export function parseMetubeImportFromHash(hash: string): MetubeImportParams | null {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const match = raw.match(/(?:^|&)mt=([^&]+)/);
  if (!match) {
    return null;
  }
  try {
    const b64 = match[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '==='.slice((b64.length + 3) % 4);
    const json = decodeURIComponent(
      Array.from(atob(padded), (c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join(''),
    );
    const data = JSON.parse(json) as Record<string, unknown>;
    const url = String(data['url'] ?? '').trim();
    if (!url) {
      return null;
    }
    const clips = parseClipsArray(data['clips']);
    const mergeClips = data['merge'] === true || data['merge'] === '1';
    return { url, clips, mergeClips: mergeClips || undefined };
  } catch {
    return null;
  }
}

export function parseMetubeImportFromLocation(search: string, hash: string): MetubeImportParams | null {
  return parseMetubeImportFromHash(hash) ?? parseMetubeImportFromSearch(search);
}

function parseClipsArray(raw: unknown): ImportClip[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .filter((item): item is Record<string, unknown> => item != null && typeof item === 'object')
    .map((item) => ({
      start: String(item['start'] ?? '').trim(),
      end: String(item['end'] ?? '').trim(),
    }))
    .filter((c) => c.start && c.end);
}

function parseClipsParam(raw: string | null): ImportClip[] {
  if (!raw?.trim()) {
    return [];
  }
  const trimmed = raw.trim();
  if (trimmed.startsWith('[')) {
    try {
      return parseClipsArray(JSON.parse(trimmed) as unknown);
    } catch {
      return [];
    }
  }
  return trimmed
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const dash = part.indexOf('-');
      if (dash <= 0) {
        return { start: '', end: '' };
      }
      return {
        start: part.slice(0, dash).trim(),
        end: part.slice(dash + 1).trim(),
      };
    })
    .filter((c) => c.start && c.end);
}

export function buildMetubeImportSearch(
  url: string,
  clips: ImportClip[],
  options?: { mergeClips?: boolean },
): string {
  const params = new URLSearchParams();
  params.set('url', url);
  if (clips.length) {
    params.set('clips', JSON.stringify(clips));
  }
  if (options?.mergeClips) {
    params.set('merge', '1');
  }
  return params.toString();
}

/** Build `#mt=…` fragment for extension → MeTube (survives service worker / long URLs). */
export function buildMetubeImportHash(
  url: string,
  clips: ImportClip[],
  options?: { mergeClips?: boolean },
): string {
  const payload = {
    url,
    clips,
    merge: options?.mergeClips ?? false,
  };
  const json = JSON.stringify(payload);
  const bytes = encodeURIComponent(json).replace(/%([0-9A-F]{2})/gi, (_, hex) =>
    String.fromCharCode(parseInt(hex, 16)),
  );
  const b64 = btoa(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  return `#mt=${b64}`;
}
