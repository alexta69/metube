
export interface Download {
  id: string;
  title: string;
  url: string;
  download_type: string;
  codec?: string;
  quality: string;
  format: string;
  folder: string;
  custom_name_prefix: string;
  playlist_item_limit: number;
  split_by_chapters?: boolean;
  chapter_template?: string;
  subtitle_language?: string;
  subtitle_mode?: string;
  ytdl_options_presets?: string[];
  ytdl_options_overrides?: Record<string, unknown>;
  clip_start?: number;
  clip_end?: number;
  live_status?: string;
  live_release_timestamp?: number;
  status: string;
  msg: string;
  percent: number;
  speed: number;
  eta: number;
  filename: string;
  checked: boolean;
  timestamp?: number;
  size?: number;
  error?: string;
  deleting?: boolean;
  chapter_files?: { filename: string, size: number }[];
  // Actual media properties resolved by yt-dlp at download time. Unlike
  // `quality`/`codec` (the user's request), these reflect what came out.
  // Optional because they're only populated for finished downloads of
  // video/audio (not captions/thumbnails) and old persisted entries
  // pre-dating the patch don't have them.
  width?: number;
  height?: number;
  fps?: number;
  vcodec_actual?: string;
  abr?: number;
}
