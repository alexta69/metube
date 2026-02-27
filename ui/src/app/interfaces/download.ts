
export interface Download {
  id: string;
  title: string;
  url: string;
  quality: string;
  format: string;
  folder: string;
  custom_name_prefix: string;
  playlist_item_limit: number;
  split_by_chapters?: boolean;
  chapter_template?: string;
  subtitle_format?: string;
  subtitle_language?: string;
  subtitle_mode?: string;
  status: string;
  msg: string;
  percent: number;
  speed: number;
  eta: number;
  filename: string;
  checked: boolean;
  size?: number;
  error?: string;
  deleting?: boolean;
  chapter_files?: Array<{ filename: string, size: number }>;
}
