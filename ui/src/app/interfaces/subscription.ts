export interface SubscriptionRow {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  check_interval_minutes: number;
  download_type: string;
  codec: string;
  format: string;
  quality: string;
  folder: string;
  last_checked: number | null;
  seen_count: number;
  error: string | null;
}
