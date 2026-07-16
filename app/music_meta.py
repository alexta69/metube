"""Music metadata helpers: song lookups against public music databases and
audio-file tagging via mutagen.

Used by the music-tag feature: finished audio downloads can be tagged with
proper song metadata (title / artists / album / date / genres) and optionally
filed into an Artist/Album directory layout inside the audio download dir.
"""

import asyncio
import json
import logging
import os
import re
from urllib.parse import quote

import aiohttp
from mutagen import File as MutagenFile

log = logging.getLogger('music_meta')

# Extensions mutagen can reliably retag in place.
TAGGABLE_EXTS = {'.mp3', '.m4a', '.aac', '.opus', '.ogg', '.oga', '.flac', '.wav', '.wv', '.aif', '.aiff'}

LOOKUP_TIMEOUT = aiohttp.ClientTimeout(total=8)
USER_AGENT = 'metube (https://github.com/alexta69/metube)'


def split_artists(s):
    """Split a database artist string: "A & B feat. C" -> ['A', 'B', 'C'].

    Only for database-provided strings — user-typed fields go through
    split_list, where '&' must survive ("Hootie & the Blowfish", "R&B").
    """
    parts = re.split(r'\s*[,&;]\s*|\s+(?:featuring|feat\.?|ft\.?)\s+', str(s or ''), flags=re.IGNORECASE)
    return [p.strip() for p in parts if p and p.strip()]


def split_list(s):
    """Split a user-typed comma/semicolon-separated list."""
    return [p.strip() for p in re.split(r'\s*[,;]\s*', str(s or '')) if p.strip()]


def sanitize_part(name, fallback):
    """A path component safe on every filesystem, or the fallback."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', ' ', str(name or ''))
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().strip('.')[:80].strip()
    return cleaned or fallback


async def _fetch_json(session, url):
    async with session.get(url, headers={'User-Agent': USER_AGENT}) as resp:
        if resp.status != 200:
            raise RuntimeError(f'upstream {resp.status}')
        # Deezer serves JSON with a text/html content type on some endpoints.
        return json.loads(await resp.text())


async def search_candidates(query):
    """Song candidates for a free-text query from iTunes Search and Deezer
    (both keyless). Returns up to 10 dicts: {source, title, artists[], album,
    date, genres[], cover}. Either provider failing alone is fine.
    """
    out = []
    seen = set()

    def push(candidate):
        key = (','.join(candidate['artists']) + '|' + (candidate['title'] or '')).lower()
        if candidate['title'] and candidate['artists'] and key not in seen:
            seen.add(key)
            out.append(candidate)

    async with aiohttp.ClientSession(timeout=LOOKUP_TIMEOUT) as session:
        itunes, deezer = await asyncio.gather(
            _fetch_json(session, f'https://itunes.apple.com/search?media=music&entity=song&limit=6&term={quote(query)}'),
            _fetch_json(session, f'https://api.deezer.com/search?limit=4&q={quote(query)}'),
            return_exceptions=True,
        )

        if not isinstance(itunes, BaseException):
            for row in itunes.get('results') or []:
                push({
                    'source': 'itunes',
                    'title': row.get('trackName'),
                    'artists': split_artists(row.get('artistName')),
                    'album': row.get('collectionName'),
                    'date': str(row.get('releaseDate'))[:10] if row.get('releaseDate') else None,
                    'genres': [row['primaryGenreName']] if row.get('primaryGenreName') else [],
                    'cover': row.get('artworkUrl100'),
                })
        else:
            log.info(f'iTunes lookup failed: {itunes}')

        if not isinstance(deezer, BaseException):
            rows = deezer.get('data') or []
            # Deezer's search rows lack date/genres; the album lookup has both.
            albums = await asyncio.gather(
                *[
                    _fetch_json(session, f'https://api.deezer.com/album/{row["album"]["id"]}')
                    if row.get('album', {}).get('id') else _fail('no album')
                    for row in rows
                ],
                return_exceptions=True,
            )
            for row, album in zip(rows, albums):
                album = None if isinstance(album, BaseException) else album
                genres = []
                if album and isinstance(album.get('genres', {}).get('data'), list):
                    genres = [g.get('name') for g in album['genres']['data'] if g.get('name')]
                push({
                    'source': 'deezer',
                    'title': row.get('title'),
                    'artists': split_artists((row.get('artist') or {}).get('name')),
                    'album': (row.get('album') or {}).get('title'),
                    'date': (album or {}).get('release_date'),
                    'genres': genres,
                    'cover': (row.get('album') or {}).get('cover_medium'),
                })
        else:
            log.info(f'Deezer lookup failed: {deezer}')

    return out[:10]


async def _fail(msg):
    raise RuntimeError(msg)


def tag_audio_file(path, tags):
    """Rewrite the tags of an audio file in place via mutagen. Values: string,
    list (multi-value tag), '' / [] (clears the field) or None (leaves it
    alone). Mutagen edits tags without remuxing, so embedded cover art
    survives — ffmpeg's ogg muxer would drop it.
    """
    audio = MutagenFile(path, easy=True)
    if audio is None:
        raise ValueError('unsupported audio file')
    for key, value in tags.items():
        if value is None:
            continue
        try:
            if value == '' or value == []:
                if key in audio:
                    del audio[key]
            else:
                audio[key] = value
        except Exception:
            # Not every tag key exists in every container; skip what doesn't fit.
            pass
    audio.save()


def build_tags(title, artists, album, date, genres):
    """The tag dict for a song: the given fields plus clearing of the
    video-site leftovers (description, watch links) that yt-dlp's
    --embed-metadata writes — junk in a music library.
    """
    return {
        'title': title,
        'artist': artists,
        'albumartist': artists[0] if artists else None,
        'album': album,
        'date': date,
        'genre': genres,
        'synopsis': '',
        'description': '',
        'comment': '',
        'purl': '',
    }


def organized_rel_path(artists, album, date, title, ext):
    """Library layout: Artist/Album(Year)/Artist - Album(Year) - Title.ext.

    Artist + album repeat in the file name on purpose: the file stays
    traceable even when it ends up outside its folder.
    """
    year = str(date)[:4] if date else None
    artist_dir = sanitize_part(artists[0] if artists else None, 'Unknown Artist')
    album_dir = sanitize_part(album, 'Unknown Album') + (f'({year})' if year else '')
    file_name = f'{artist_dir} - {album_dir} - {sanitize_part(title, "Unknown")}{ext}'
    return os.path.join(artist_dir, album_dir, file_name)
