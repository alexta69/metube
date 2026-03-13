import { Quality } from "./quality";

export interface Option {
  id: string;
  text: string;
}

export interface AudioFormatOption extends Option {
  qualities: Quality[];
}

export const DOWNLOAD_TYPES: Option[] = [
  { id: "video", text: "Video" },
  { id: "audio", text: "Audio" },
  { id: "captions", text: "Captions" },
  { id: "thumbnail", text: "Thumbnail" },
];

export const VIDEO_CODECS: Option[] = [
  { id: "auto", text: "Auto" },
  { id: "h264", text: "H.264" },
  { id: "h265", text: "H.265 (HEVC)" },
  { id: "av1", text: "AV1" },
  { id: "vp9", text: "VP9" },
];

export const VIDEO_FORMATS: Option[] = [
  { id: "any", text: "Auto" },
  { id: "mp4", text: "MP4" },
  { id: "ios", text: "iOS Compatible" },
];

export const VIDEO_QUALITIES: Quality[] = [
  { id: "best", text: "Best" },
  { id: "2160", text: "2160p" },
  { id: "1440", text: "1440p" },
  { id: "1080", text: "1080p" },
  { id: "720", text: "720p" },
  { id: "480", text: "480p" },
  { id: "360", text: "360p" },
  { id: "240", text: "240p" },
  { id: "worst", text: "Worst" },
];

export const AUDIO_FORMATS: AudioFormatOption[] = [
  {
    id: "m4a",
    text: "M4A",
    qualities: [
      { id: "best", text: "Best" },
      { id: "192", text: "192 kbps" },
      { id: "128", text: "128 kbps" },
    ],
  },
  {
    id: "mp3",
    text: "MP3",
    qualities: [
      { id: "best", text: "Best" },
      { id: "320", text: "320 kbps" },
      { id: "192", text: "192 kbps" },
      { id: "128", text: "128 kbps" },
    ],
  },
  { id: "opus", text: "OPUS", qualities: [{ id: "best", text: "Best" }] },
  { id: "wav", text: "WAV", qualities: [{ id: "best", text: "Best" }] },
  { id: "flac", text: "FLAC", qualities: [{ id: "best", text: "Best" }] },
];

export const CAPTION_FORMATS: Option[] = [
  { id: "srt", text: "SRT" },
  { id: "txt", text: "TXT (Text only)" },
  { id: "vtt", text: "VTT" },
  { id: "ttml", text: "TTML" },
];

export const THUMBNAIL_FORMATS: Option[] = [{ id: "jpg", text: "JPG" }];
