// Labels for a queued or finished download, worded the way the form words
// them: looked up in the server's catalog (app/format_catalog.py) under the
// download's own type. A record whose type or option the catalog no longer
// lists still reads sensibly.
import { Download, DownloadTypeOption, FormatCatalog } from './interfaces';

export function catalogTypes(catalog: FormatCatalog | null | undefined): DownloadTypeOption[] {
  return catalog?.download_type.options ?? [];
}

function typeEntry(types: DownloadTypeOption[], type: string): DownloadTypeOption | undefined {
  return types.find((t) => t.id === type);
}

export function formatQualityLabel(download: Download, types: DownloadTypeOption[]): string {
  const q = download.quality;
  const type = typeEntry(types, download.download_type || '');
  const format = type?.format.options.find((f) => f.id === download.format);
  if (type && format && !format.quality) {
    return '-';
  }
  if (!q) return '';
  const label = format?.quality?.options.find((o) => o.id === q)?.text;
  return label ?? q.charAt(0).toUpperCase() + q.slice(1);
}

export function downloadTypeLabel(download: Download, types: DownloadTypeOption[]): string {
  const type = download.download_type || '';
  return typeEntry(types, type)?.text ?? type.charAt(0).toUpperCase() + type.slice(1);
}

export function formatLabel(download: Download, types: DownloadTypeOption[]): string {
  const format = (download.format || '').trim();
  if (!format) {
    return '-';
  }
  // Records without a type still find their label under any type.
  const options =
    typeEntry(types, download.download_type || '')?.format.options ??
    types.flatMap((t) => t.format.options);
  return options.find((o) => o.id === format)?.text ?? format.toUpperCase();
}

export function formatCodecLabel(download: Download, types: DownloadTypeOption[]): string {
  const type = typeEntry(types, download.download_type || '');
  if (type && !type.codec) {
    const format = (download.format || '').toUpperCase();
    return format || '-';
  }
  const codec = download.codec;
  if (!codec) return '-';
  return type?.codec?.options.find((c) => c.id === codec)?.text ?? codec;
}
