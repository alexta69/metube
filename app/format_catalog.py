"""The download options MeTube offers, as data: the one place they are defined.

Request validation, the yt-dlp mapping in ``dl_formats``, the web UI's form
(sent to every client on connect) and ``GET /formats`` all read this catalog.
Adding or relabelling an option is an edit here, plus its yt-dlp mapping in
``dl_formats`` when it is a new format, codec or quality; a test there fails
if an option has no mapping.

Every list is a *choice*: ``{"default": <id>, "options": [...]}``, keyed by
the ``/add`` field it describes. Each download type carries the fields that
apply to it, and each format carries its own ``quality`` choice, if it has
one. A field a type doesn't carry is forced to its fixed value (``codec``
``auto``, ``quality`` ``best``) instead of being validated.
"""

import copy
import re


def _choice(default: str, options: list[dict]) -> dict:
    assert any(o['id'] == default for o in options), default
    return {'default': default, 'options': options}


def _options(*pairs: tuple[str, str]) -> list[dict]:
    return [{'id': id_, 'text': text} for id_, text in pairs]


_VIDEO_QUALITY = _choice('best', _options(
    ('best', 'Best'),
    ('2160', '2160p'),
    ('1440', '1440p'),
    ('1080', '1080p'),
    ('720', '720p'),
    ('480', '480p'),
    ('360', '360p'),
    ('240', '240p'),
    ('worst', 'Worst'),
))

_BEST_ONLY = _choice('best', _options(('best', 'Best')))


def _video_format(id_: str, text: str) -> dict:
    return {'id': id_, 'text': text, 'quality': _VIDEO_QUALITY}


def _audio_format(id_: str, text: str, *bitrates: str, tags: bool = True) -> dict:
    quality = _choice('best', _options(('best', 'Best'), *((b, f'{b} kbps') for b in bitrates)))
    # tags: whether the audio chain can write tags and a cover into the format.
    return {'id': id_, 'text': text, 'quality': quality, 'tags': tags}


CATALOG: dict = {
    'download_type': _choice('video', [
        {
            'id': 'video',
            'text': 'Video',
            'codec': _choice('auto', _options(
                ('auto', 'Auto'),
                ('h264', 'H.264'),
                ('h265', 'H.265 (HEVC)'),
                ('av1', 'AV1'),
                ('vp9', 'VP9'),
            )),
            'format': _choice('any', [
                _video_format('any', 'Auto'),
                _video_format('mp4', 'MP4'),
                _video_format('ios', 'iOS Compatible'),
            ]),
        },
        {
            'id': 'audio',
            'text': 'Audio',
            # Auto is listed first, to match Video, but switching to Audio
            # still selects M4A, the default from before Auto existed.
            'format': _choice('m4a', [
                _audio_format('auto', 'Auto'),
                _audio_format('m4a', 'M4A', '192', '128'),
                _audio_format('mp3', 'MP3', '320', '192', '128'),
                _audio_format('opus', 'OPUS'),
                _audio_format('wav', 'WAV', tags=False),
                _audio_format('flac', 'FLAC'),
            ]),
            'audio_tags': _choice('with_cover', _options(
                ('with_cover', 'With cover'),
                ('no_cover', 'No cover'),
                ('none', 'None'),
            )),
        },
        {
            'id': 'captions',
            'text': 'Captions',
            'format': _choice('srt', _options(
                ('srt', 'SRT'),
                ('txt', 'TXT (Text only)'),
                ('vtt', 'VTT'),
                ('ttml', 'TTML'),
                ('sbv', 'SBV'),
                ('scc', 'SCC'),
                ('dfxp', 'DFXP'),
            )),
            'subtitle_mode': _choice('prefer_manual', _options(
                ('prefer_manual', 'Prefer Manual'),
                ('prefer_auto', 'Prefer Auto'),
                ('manual_only', 'Manual Only'),
                ('auto_only', 'Auto Only'),
            )),
            # Suggestions only: any tag matching SUBTITLE_LANGUAGE_RE is accepted.
            'subtitle_language': _choice('en', _options(
                ('en', 'English'),
                ('ar', 'Arabic'),
                ('bn', 'Bengali'),
                ('bg', 'Bulgarian'),
                ('ca', 'Catalan'),
                ('cs', 'Czech'),
                ('da', 'Danish'),
                ('nl', 'Dutch'),
                ('es', 'Spanish'),
                ('et', 'Estonian'),
                ('fi', 'Finnish'),
                ('fr', 'French'),
                ('de', 'German'),
                ('el', 'Greek'),
                ('he', 'Hebrew'),
                ('hi', 'Hindi'),
                ('hu', 'Hungarian'),
                ('id', 'Indonesian'),
                ('it', 'Italian'),
                ('lt', 'Lithuanian'),
                ('lv', 'Latvian'),
                ('ms', 'Malay'),
                ('no', 'Norwegian'),
                ('pl', 'Polish'),
                ('pt', 'Portuguese'),
                ('pt-BR', 'Portuguese (Brazil)'),
                ('ro', 'Romanian'),
                ('ru', 'Russian'),
                ('sk', 'Slovak'),
                ('sl', 'Slovenian'),
                ('sr', 'Serbian'),
                ('sv', 'Swedish'),
                ('ta', 'Tamil'),
                ('te', 'Telugu'),
                ('th', 'Thai'),
                ('tr', 'Turkish'),
                ('uk', 'Ukrainian'),
                ('ur', 'Urdu'),
                ('vi', 'Vietnamese'),
                ('ja', 'Japanese'),
                ('ko', 'Korean'),
                ('zh-Hans', 'Chinese (Simplified)'),
                ('zh-Hant', 'Chinese (Traditional)'),
            )),
        },
        {
            'id': 'thumbnail',
            'text': 'Thumbnail',
            'format': _choice('jpg', _options(('jpg', 'JPG'))),
        },
    ]),
}

SUBTITLE_LANGUAGE_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{0,34}$')


class InvalidOption(ValueError):
    """A request named an option the catalog does not offer."""


def public_catalog() -> dict:
    """The catalog as sent to clients; a copy, so callers cannot alter it."""
    return copy.deepcopy(CATALOG)


def option_ids(choice: dict) -> list[str]:
    return [o['id'] for o in choice['options']]


def _find(choice: dict, id_: str):
    return next((o for o in choice['options'] if o['id'] == id_), None)


def download_types() -> list[str]:
    return option_ids(CATALOG['download_type'])


def download_type(type_id: str) -> dict:
    found = _find(CATALOG['download_type'], type_id)
    if found is None:
        raise KeyError(type_id)
    return found


def format_ids(type_id: str) -> list[str]:
    return option_ids(download_type(type_id)['format'])


def format_option(type_id: str, format_id: str):
    """The format's catalog entry, or None if *type_id* doesn't offer it."""
    return _find(download_type(type_id)['format'], format_id)


def choice_default(type_id: str, field: str) -> str:
    return download_type(type_id)[field]['default']


def choice_ids(type_id: str, field: str) -> list[str]:
    return option_ids(download_type(type_id)[field])


def format_supports_tags(type_id: str, format_id: str) -> bool:
    option = format_option(type_id, format_id)
    return bool(option and option.get('tags', False))


def _check(field: str, value: str, choice: dict, context: str = '') -> None:
    if value not in option_ids(choice):
        raise InvalidOption(f'{field} must be one of {sorted(option_ids(choice))}{context}')


def resolve_selection(download_type_id: str, codec: str, format_id: str, quality: str) -> tuple[str, str, str]:
    """Validate a download's type/codec/format/quality against the catalog.

    Returns ``(codec, format, quality)`` with the fields the type or format
    doesn't offer forced to their fixed values. Raises InvalidOption.
    """
    _check('download_type', download_type_id, CATALOG['download_type'])
    type_entry = download_type(download_type_id)
    if 'codec' in type_entry:
        _check('codec', codec, type_entry['codec'])
    else:
        codec = 'auto'
    _check('format', format_id, type_entry['format'], f' for {download_type_id}')
    format_entry = format_option(download_type_id, format_id)
    if 'quality' in format_entry:
        _check('quality', quality, format_entry['quality'], f' for format {format_id}')
    else:
        quality = 'best'
    return codec, format_id, quality


def check_audio_tags(audio_tags: str) -> None:
    _check('audio_tags', audio_tags, download_type('audio')['audio_tags'])


def check_subtitle_mode(subtitle_mode: str) -> None:
    _check('subtitle_mode', subtitle_mode, download_type('captions')['subtitle_mode'])


def check_subtitle_language(subtitle_language: str) -> None:
    if not SUBTITLE_LANGUAGE_RE.fullmatch(subtitle_language):
        raise InvalidOption('subtitle_language must match pattern [A-Za-z0-9-] and be at most 35 characters')
