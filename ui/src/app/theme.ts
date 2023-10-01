import { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import { faCircleHalfStroke, faMoon, faSun  } from "@fortawesome/free-solid-svg-icons";

export interface Theme {
  id: string;
  displayName: string;
  icon: IconDefinition;
}

export const Themes: Theme[] = [
  {
    id: 'light',
    displayName: 'Light',
    icon: faSun,
  },
  {
    id: 'dark',
    displayName: 'Dark',
    icon: faMoon,
  },
  {
    id: 'auto',
    displayName: 'Auto',
    icon: faCircleHalfStroke,
  },
];
