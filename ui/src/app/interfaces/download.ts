
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
}
