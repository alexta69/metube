export interface Format {
  id: string;
  text: string;
  qualities: Quality[];
}

export interface Quality {
  id: string;
  text: string;
  value: string;
}

export const Formats: Format[] = [
  {
    id: 'any',
    text: 'Any',
    qualities: [
      { id: '0', value: 'best', text: 'Best' },
      { id: '1', value: '1440', text: '1440p' },
      { id: '2', value: '1080', text: '1080p' },
      { id: '3', value: '720', text: '720p' },
      { id: '4', value: '480', text: '480p' },
      { id: '5', value: 'audio', text: 'Audio Only' },
    ],
  },
  {
    id: 'mp4',
    text: 'MP4',
    qualities: [
      { id: '6', value: 'best', text: 'Best' },
      { id: '7', value: '1440', text: '1440p' },
      { id: '8', value: '1080', text: '1080p' },
      { id: '9', value: '720', text: '720p' },
      { id: '10', value: '480', text: '480p' },
    ],
  },
  {
    id: 'mp3',
    text: 'MP3',
    qualities: [
      { id: '11', value: 'best', text: 'Best' },
      { id: '12', value: '128', text: '128 kbps' },
      { id: '13', value: '192', text: '192 kbps' },
      { id: '14', value: '320', text: '320 kbps' },
    ],
  },
];

export const getQualityById = (formats: Format[], id: string): Quality => {
  return formats
    .find((ql) => ql.qualities.find((el) => el.id === id))
    .qualities.find((el) => el.id === id);
};
