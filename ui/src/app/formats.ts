export interface Format {
  id: string;
  text: string;
  qualities: Quality[];
}

export interface Quality {
  id: string;
  text: string;
}

export const Formats: Format[] = [
  {
    id: 'any',
    text: 'Any',
    qualities: [
      { id: 'best', text: 'Best' },
      { id: '1440', text: '1440p' },
      { id: '1080', text: '1080p' },
      { id: '720', text: '720p' },
      { id: '480', text: '480p' },
      { id: 'audio', text: 'Audio Only' },
    ],
  },
  {
    id: 'mp4',
    text: 'MP4',
    qualities: [
      { id: 'best', text: 'Best' },
      { id: '1440', text: '1440p' },
      { id: '1080', text: '1080p' },
      { id: '720', text: '720p' },
      { id: '480', text: '480p' },
    ],
  },
  {
    id: 'mp3',
    text: 'MP3',
    qualities: [
      { id: 'best', text: 'Best' },
      { id: '320', text: '320 kbps' },
      { id: '192', text: '192 kbps' },
      { id: '128', text: '128 kbps' },
    ],
  },
];
