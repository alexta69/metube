"""Conservative music metadata enrichment for audio downloads.

This module only consumes metadata already supplied by yt-dlp or retained on
MeTube's queued playlist entry. It intentionally performs no external lookup.
"""

from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlparse

from mutagen import MutagenError
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TRCK, TXXX
from mutagen.mp4 import AtomDataType, MP4, MP4FreeForm
from mutagen.oggopus import OggOpus
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import PostProcessingError


_ARTISTS_KEY = '__metube_track_artists'
_TRACK_NUMBER_KEY = '__metube_track_number'
_TRACK_TOTAL_KEY = '__metube_track_total'
_YOUTUBE_MUSIC_HOSTS = frozenset(('music.youtube.com', 'music.youtube-nocookie.com'))


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


def _is_youtube_music_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        return (urlparse(value).hostname or '').lower() in _YOUTUBE_MUSIC_HOSTS
    except ValueError:
        return False


def is_confirmed_music_album(source_url: Any, entry: Any) -> bool:
    """Recognize only strong YouTube Music album signals."""
    entry = entry if isinstance(entry, dict) else {}
    for key in ('playlist_id', 'playlist'):
        playlist_id = entry.get(key)
        if isinstance(playlist_id, str) and playlist_id.startswith('OLAK5uy_'):
            return True

    candidate_urls = (
        source_url,
        entry.get('original_url'),
        entry.get('webpage_url'),
        entry.get('url'),
    )
    for value in candidate_urls:
        if not _is_youtube_music_url(value):
            continue
        try:
            path = urlparse(value).path.rstrip('/')
        except ValueError:
            continue
        if path.startswith('/browse/MPRE'):
            return True
    return False


def _is_music_audio(info: dict[str, Any], source_url: Any, confirmed_album: bool) -> bool:
    if confirmed_album or _is_youtube_music_url(source_url):
        return True
    if (
        _is_youtube_music_url(info.get('webpage_url'))
        or _is_youtube_music_url(info.get('original_url'))
    ):
        return True
    return _has_value(info.get('track')) or (
        _has_value(info.get('album')) and _has_value(info.get('artists'))
    )


def structured_track_artists(info: dict[str, Any]) -> list[str]:
    """Return structured track artists without guessing at comma separators."""
    artists = info.get('artists')
    if not isinstance(artists, (list, tuple)):
        return []

    result: list[str] = []
    for value in artists:
        if not isinstance(value, str):
            continue
        # YouTube Music uses a *spaced* middle dot between artist credits.
        # Do not split unspaced names such as "half\u00b7alive".
        for artist in value.split(' \u00b7 '):
            artist = artist.strip()
            if artist and artist not in result:
                result.append(artist)
    return result


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
    """Enrich a fully extracted audio info-dict from its queued source entry."""

    def __init__(self, downloader=None, *, source_url=None, source_entry=None):
        super().__init__(downloader)
        self._source_url = source_url
        self._source_entry = source_entry if isinstance(source_entry, dict) else {}

    def run(self, info):
        confirmed_album = is_confirmed_music_album(self._source_url, self._source_entry)

        number, inline_total = _track_position(info.get('track_number'))
        total = inline_total
        if confirmed_album:
            if number is None:
                number = _positive_int(self._source_entry.get('playlist_index'))
                if number is not None:
                    info['track_number'] = number
            total = total or next((
                value for value in (
                    _positive_int(info.get('track_count')),
                    _positive_int(info.get('track_total')),
                    _positive_int(self._source_entry.get('playlist_count')),
                    _positive_int(self._source_entry.get('n_entries')),
                ) if value is not None
            ), None)
            if not _has_value(info.get('album')):
                album = self._source_entry.get('playlist_title')
                if isinstance(album, str) and album.strip():
                    info['album'] = album.strip()

        if number is not None:
            info[_TRACK_NUMBER_KEY] = number
            if total is not None:
                info[_TRACK_TOTAL_KEY] = total

        artists = structured_track_artists(info)
        if len(artists) > 1:
            info[_ARTISTS_KEY] = artists

        if _is_music_audio(info, self._source_url, confirmed_album):
            prefer_square_thumbnail(info)
        return [], info


def _write_mp3(path: str, artists: list[str], number: Optional[int], total: Optional[int]) -> None:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    if artists:
        tags.delall('TXXX:Artists')
        tags.delall('TXXX:ARTISTS')
        tags.add(TXXX(encoding=3, desc='Artists', text=artists))
    if number is not None:
        value = f'{number}/{total}' if total is not None else str(number)
        tags.setall('TRCK', [TRCK(encoding=3, text=[value])])
    tags.save(path, v2_version=4)


def _write_m4a(path: str, artists: list[str], number: Optional[int], total: Optional[int]) -> None:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    if artists:
        # A list under one key is serialized as one multi-value atom. Duplicate
        # atoms are intentionally avoided because TagLib reads only the first.
        audio.tags['----:com.apple.iTunes:ARTISTS'] = [
            MP4FreeForm(artist.encode('utf-8'), dataformat=AtomDataType.UTF8)
            for artist in artists
        ]
    if number is not None:
        audio.tags['trkn'] = [(number, total or 0)]
    audio.save()


def _write_vorbis(audio, artists: list[str], number: Optional[int], total: Optional[int]) -> None:
    if artists:
        audio['ARTISTS'] = artists
    if number is not None:
        audio['TRACKNUMBER'] = [str(number)]
    if total is not None:
        value = [str(total)]
        audio['TRACKTOTAL'] = value
        audio['TOTALTRACKS'] = value
    audio.save()


def write_music_tags(
    path: str,
    extension: str,
    artists: list[str],
    number: Optional[int],
    total: Optional[int],
) -> None:
    """Write only the supplemental tags needed for music library scanners."""
    extension = extension.lower()
    if extension == 'mp3':
        _write_mp3(path, artists, number, total)
    elif extension == 'm4a':
        _write_m4a(path, artists, number, total)
    elif extension == 'flac':
        _write_vorbis(FLAC(path), artists, number, total)
    elif extension == 'opus':
        _write_vorbis(OggOpus(path), artists, number, total)


class MusicMetadataWriterPostProcessor(PostProcessor):
    """Write supplemental tags after yt-dlp has moved the completed audio file."""

    _SUPPORTED_EXTENSIONS = frozenset(('mp3', 'm4a', 'flac', 'opus'))

    def run(self, info):
        artists = info.get(_ARTISTS_KEY)
        artists = artists if isinstance(artists, list) else []
        number = _positive_int(info.get(_TRACK_NUMBER_KEY))
        total = _positive_int(info.get(_TRACK_TOTAL_KEY))
        if not artists and number is None:
            return [], info

        path = info.get('filepath')
        extension = str(info.get('ext') or os.path.splitext(str(path))[1][1:]).lower()
        if not isinstance(path, str) or extension not in self._SUPPORTED_EXTENSIONS:
            return [], info
        try:
            write_music_tags(path, extension, artists, number, total)
        except (MutagenError, OSError, TypeError, ValueError) as error:
            raise PostProcessingError(
                f'Unable to write supplemental music metadata to "{path}": {error}'
            ) from error
        return [], info
