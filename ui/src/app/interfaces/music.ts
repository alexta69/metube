export interface MusicCandidate {
  source: string;
  title: string | null;
  artists: string[];
  album: string | null;
  date: string | null;
  genres: string[];
  cover: string | null;
}

export interface MusicSource {
  status: string;
  msg?: string;
  title?: string;
  filename?: string;
  description?: string | null;
  music?: {
    artist?: string | null;
    track?: string | null;
    album?: string | null;
    release_year?: string | number | null;
    genre?: string | null;
  };
}

export interface MusicTagPayload {
  id: string;
  title: string;
  artists: string[];
  album: string;
  date: string | null;
  genres: string[];
  organize: boolean;
}
