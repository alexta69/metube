// The download options the server offers. The catalog is defined in
// app/format_catalog.py and sent to every client on connect; nothing here
// lists options of its own.

export interface Option {
  id: string;
  text: string;
}

// One list of options for an /add field, with the value to preselect.
export interface Choice<T extends Option = Option> {
  default: string;
  options: T[];
}

export interface FormatOption extends Option {
  // Absent when the format has no quality to pick.
  quality?: Choice;
  // Audio only: whether tags and a cover can be written into the format.
  tags?: boolean;
}

// Each type carries the fields that apply to it.
export interface DownloadTypeOption extends Option {
  format: Choice<FormatOption>;
  codec?: Choice;
  audio_tags?: Choice;
  subtitle_mode?: Choice;
  // Suggestions; any language tag is accepted.
  subtitle_language?: Choice;
}

export interface FormatCatalog {
  download_type: Choice<DownloadTypeOption>;
}
