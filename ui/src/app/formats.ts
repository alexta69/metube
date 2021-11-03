export interface Format {
  id: string;
  text: string;
  qualities: Quality[];
}

export interface Quality {
  id: string;
  text: string;
  value: string;
  fmt?: string;
}

export const Formats: Format[] = [
  {
    id: 'any',
    text: 'Any',
    qualities: [],
  },
  {
    id: 'mp4',
    text: 'MP4',
    qualities: [
      { id: "1", value: 'best', text: 'Best MP4' },
      { id: "2", value: '1440', text: '1440p' },
      { id: "3", value: '1080', text: '1080p' },
      { id: "4", value: '720', text: '720p' },
      { id: "5", value: '480', text: '480p' },
    ],
  },
  {
    id: 'mp3',
    text: 'MP3',
    qualities: [
      { id: "6", value: 'best', text: 'Best MP3' },
      { id: "7", value: '128', text: '128 kbps' },
      { id: "8", value: '192', text: '192 kbps' },
      { id: "9", value: '320', text: '320 kbps' },
    ],
  },
];

export const fillQualities = (formats: Format[]): Format[] => {
  let allQualities: Quality[] = [];
  formats.forEach((fmt) => {
    fmt.qualities = fmt.qualities.map((ql) => ({ ...ql, fmt: fmt.id }));
    allQualities = allQualities.concat(fmt.qualities);
  });

  formats.find((format) => format.id === 'any').qualities = allQualities;
  return formats;
};

export const getQualityById = (formats: Format[], id: string): Quality => {
  return formats
    .find(ql => ql.qualities.find(el => el.id === id)).qualities
    .find(el => el.id === id)
}
