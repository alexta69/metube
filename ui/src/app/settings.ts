import { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import { faWrench  } from "@fortawesome/free-solid-svg-icons";

export interface Setting {
  id: string;
  displayName: string;
  icon: IconDefinition;
}

export const Settings: Setting[] = [
  {
    id: 'ytdl_options',
    displayName: 'yt-dlp Options',
    icon: faWrench,
  },
];
