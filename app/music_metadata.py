"""Conservative music metadata enrichment for audio downloads.

This module only consumes fields already supplied by yt-dlp or retained on
MeTube's queued playlist entry. It intentionally performs no external lookup
or site-specific album detection.
"""

from __future__ import annotations

from typing import Any, Optional

from yt_dlp.postprocessor.common import PostProcessor


def _has_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(_has_value(item) for item in value)
    return value is not None


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _track_position(value: Any) -> tuple[Optional[int], Optional[int]]:
    """Return a track number and optional total from a scalar or ``n/total``."""
    if isinstance(value, str) and '/' in value:
        number, total = value.split('/', 1)
        return _positive_int(number.strip()), _positive_int(total.strip())
    return _positive_int(value), None


def _first_positive_int(*values: Any) -> Optional[int]:
    return next((number for value in values if (number := _positive_int(value))), None)


def _has_album_signal(info: dict[str, Any], source_entry: dict[str, Any]) -> bool:
    """Use only extractor-owned fields to identify album-level metadata."""
    return any(
        _has_value(entry.get(key))
        for entry in (info, source_entry)
        for key in ('album', 'track_number')
    )


def _is_music_audio(info: dict[str, Any], source_entry: dict[str, Any]) -> bool:
    return _has_album_signal(info, source_entry) or any(
        _has_value(entry.get(key))
        for entry in (info, source_entry)
        for key in ('track', 'artists')
    )


def prefer_square_thumbnail(info: dict[str, Any]) -> None:
    """Move the largest known square thumbnail to yt-dlp's preferred slot."""
    thumbnails = info.get('thumbnails')
    if not isinstance(thumbnails, list) or len(thumbnails) < 2:
        return

    candidates: list[tuple[int, int]] = []
    for index, thumbnail in enumerate(thumbnails):
        if not isinstance(thumbnail, dict):
            continue
        width = _positive_int(thumbnail.get('width'))
        height = _positive_int(thumbnail.get('height'))
        if width is not None and width == height:
            candidates.append((width * height, index))
    if not candidates:
        return

    _, selected_index = max(candidates)
    selected = thumbnails.pop(selected_index)
    thumbnails.append(selected)
    if selected.get('url'):
        info['thumbnail'] = selected['url']


class MusicMetadataPreProcessor(PostProcessor):
    """Enrich extracted audio metadata using extractor-owned album signals."""

    def __init__(self, downloader=None, *, source_entry=None):
        super().__init__(downloader)
        self._source_entry = source_entry if isinstance(source_entry, dict) else {}

    def run(self, info):
        if _has_album_signal(info, self._source_entry):
            number, inline_total = _track_position(info.get('track_number'))
            if number is None:
                number, source_inline_total = _track_position(
                    self._source_entry.get('track_number')
                )
                inline_total = inline_total or source_inline_total
            if number is None:
                number = _positive_int(self._source_entry.get('playlist_index'))

            total = inline_total or _first_positive_int(
                info.get('track_count'),
                info.get('track_total'),
                self._source_entry.get('track_count'),
                self._source_entry.get('track_total'),
                self._source_entry.get('playlist_count'),
                self._source_entry.get('n_entries'),
            )
            if number is not None:
                info['track_number'] = f'{number}/{total}' if total is not None else number

            if not _has_value(info.get('album')):
                album = self._source_entry.get('album') or self._source_entry.get(
                    'playlist_title'
                )
                if isinstance(album, str) and album.strip():
                    info['album'] = album.strip()

        if _is_music_audio(info, self._source_entry):
            prefer_square_thumbnail(info)
        return [], info
