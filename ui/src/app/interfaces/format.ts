import { Quality } from "./quality";

export interface Format {
  id: string;
  text: string;
  qualities: Quality[];
}
