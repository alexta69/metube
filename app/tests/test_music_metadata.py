"""Tests for conservative audio metadata enrichment and tag mappings."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mutagen.id3 import APIC, ID3, TPE1, TPE2, TRCK, TXXX

from music_metadata import (
    _ARTISTS_KEY,
    _TRACK_NUMBER_KEY,
    _TRACK_TOTAL_KEY,
    MusicMetadataPreProcessor,
    MusicMetadataWriterPostProcessor,
    _write_m4a,
    _write_vorbis,
    is_confirmed_music_album,
    structured_track_artists,
    write_music_tags,
)


def _preprocess(source_url, source_entry, info):
    processor = MusicMetadataPreProcessor(
        source_url=source_url,
        source_entry=source_entry,
    )
    _, result = processor.run(info)
    return result


def test_album_detection_requires_mpre_or_olak_signal():
    assert is_confirmed_music_album(
        'https://music.youtube.com/watch?v=track',
        {'playlist': 'OLAK5uy_example'},
    )
    assert is_confirmed_music_album(
        'https://music.youtube.com/browse/MPREb_example',
        {},
    )
    assert not is_confirmed_music_album(
        'https://music.youtube.com/playlist?list=PLexample',
        {'playlist': 'PLexample'},
    )
    assert not is_confirmed_music_album(
        'https://www.youtube.com/playlist?list=PLexample',
        {'playlist': 'PLexample'},
    )


def test_album_uses_existing_order_and_total_when_track_number_is_missing():
    result = _preprocess(
        'https://music.youtube.com/watch?v=track',
        {
            'playlist': 'OLAK5uy_example',
            'playlist_index': '03',
            'playlist_count': 12,
            'playlist_title': 'Example Album',
        },
        {'title': 'Track', 'artists': ['Artist One']},
    )

    assert result['track_number'] == 3
    assert result[_TRACK_NUMBER_KEY] == 3
    assert result[_TRACK_TOTAL_KEY] == 12
    assert result['album'] == 'Example Album'


def test_official_track_number_wins_over_album_order():
    result = _preprocess(
        'https://music.youtube.com/watch?v=track',
        {
            'playlist': 'OLAK5uy_example',
            'playlist_index': 3,
            'playlist_count': 12,
        },
        {'track_number': 7, 'album': 'Official Album'},
    )

    assert result['track_number'] == 7
    assert result[_TRACK_NUMBER_KEY] == 7
    assert result[_TRACK_TOTAL_KEY] == 12
    assert result['album'] == 'Official Album'


def test_inline_official_track_total_is_preserved():
    result = _preprocess(
        'https://music.youtube.com/watch?v=track',
        {'playlist': 'OLAK5uy_example', 'playlist_count': 12},
        {'track_number': '4/10', 'album': 'Official Album'},
    )

    assert result['track_number'] == '4/10'
    assert result[_TRACK_NUMBER_KEY] == 4
    assert result[_TRACK_TOTAL_KEY] == 10


def test_youtube_music_playlist_does_not_infer_album_or_track_number():
    result = _preprocess(
        'https://music.youtube.com/watch?v=track',
        {
            'playlist': 'PLexample',
            'playlist_index': 3,
            'playlist_count': 12,
            'playlist_title': 'Example Playlist',
        },
        {'title': 'Track'},
    )

    assert 'album' not in result
    assert 'track_number' not in result
    assert _TRACK_NUMBER_KEY not in result
    assert _TRACK_TOTAL_KEY not in result


def test_regular_youtube_playlist_and_video_are_not_changed():
    thumbnails = [
        {'url': 'square.jpg', 'width': 500, 'height': 500},
        {'url': 'landscape.jpg', 'width': 1280, 'height': 720},
    ]
    info = {'title': 'Regular Video', 'thumbnails': thumbnails.copy()}

    result = _preprocess(
        'https://www.youtube.com/watch?v=video',
        {'playlist': 'PLexample', 'playlist_index': 2, 'playlist_count': 5},
        info,
    )

    assert result['thumbnails'] == thumbnails
    assert 'album' not in result
    assert 'track_number' not in result


def test_music_audio_prefers_largest_existing_square_thumbnail():
    result = _preprocess(
        'https://music.youtube.com/watch?v=track',
        {'playlist': 'PLexample'},
        {
            'thumbnails': [
                {'url': 'small-square.jpg', 'width': 200, 'height': 200},
                {'url': 'large-square.jpg', 'width': 1000, 'height': 1000},
                {'url': 'landscape.jpg', 'width': 1280, 'height': 720},
            ],
        },
    )

    assert result['thumbnails'][-1]['url'] == 'large-square.jpg'
    assert result['thumbnail'] == 'large-square.jpg'


def test_landscape_only_music_artwork_keeps_existing_order():
    thumbnails = [
        {'url': 'small.jpg', 'width': 640, 'height': 360},
        {'url': 'large.jpg', 'width': 1280, 'height': 720},
    ]
    result = _preprocess(
        'https://music.youtube.com/watch?v=track',
        {'playlist': 'PLexample'},
        {'thumbnails': thumbnails.copy()},
    )

    assert result['thumbnails'] == thumbnails
    assert 'thumbnail' not in result


def test_structured_artists_split_only_spaced_middle_dot():
    assert structured_track_artists({
        'artists': ['Artist One \u00b7 Artist Two', 'Earth, Wind & Fire', 'half\u00b7alive'],
    }) == ['Artist One', 'Artist Two', 'Earth, Wind & Fire', 'half\u00b7alive']
    assert structured_track_artists({'artist': 'Artist One, Artist Two'}) == []


def test_preprocessor_retains_separate_structured_artists():
    result = _preprocess(
        'https://music.youtube.com/watch?v=track',
        {},
        {'artist': 'Artist One, Artist Two', 'artists': ['Artist One', 'Artist Two']},
    )

    assert result['artist'] == 'Artist One, Artist Two'
    assert result[_ARTISTS_KEY] == ['Artist One', 'Artist Two']


def test_mp3_mapping_uses_plural_artists_and_fractional_track():
    tags = MagicMock()
    with patch('music_metadata.ID3', return_value=tags):
        write_music_tags('track.mp3', 'mp3', ['Artist One', 'Artist Two'], 3, 12)

    artist_frame = tags.add.call_args.args[0]
    assert isinstance(artist_frame, TXXX)
    assert artist_frame.desc == 'Artists'
    assert artist_frame.text == ['Artist One', 'Artist Two']
    track_frame = tags.setall.call_args.args[1][0]
    assert isinstance(track_frame, TRCK)
    assert track_frame.text == ['3/12']
    tags.save.assert_called_once_with('track.mp3', v2_version=4)


def test_mp3_round_trip_preserves_display_artist_artwork_and_album_artist(tmp_path):
    path = tmp_path / 'track.mp3'
    initial = ID3()
    initial.add(TPE1(encoding=3, text=['Artist One, Artist Two']))
    initial.add(TPE2(encoding=3, text=['Existing Album Artist']))
    initial.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=b'cover'))
    initial.save(path)

    write_music_tags(str(path), 'mp3', ['Artist One', 'Artist Two'], 3, 12)

    result = ID3(path)
    assert result.getall('TPE1')[0].text == ['Artist One, Artist Two']
    assert result.getall('TPE2')[0].text == ['Existing Album Artist']
    assert result.getall('APIC')[0].data == b'cover'
    assert result.getall('TXXX:Artists')[0].text == ['Artist One', 'Artist Two']
    assert result.getall('TRCK')[0].text == ['3/12']


class _FakeM4A:
    def __init__(self):
        self.tags = {
            '\xa9ART': ['Artist One, Artist Two'],
            'covr': [b'cover'],
            'aART': ['Existing Album Artist'],
        }
        self.saved = False

    def add_tags(self):
        self.tags = {}

    def save(self):
        self.saved = True


def test_m4a_mapping_preserves_display_artist_artwork_and_album_artist():
    audio = _FakeM4A()
    with patch('music_metadata.MP4', return_value=audio):
        _write_m4a('track.m4a', ['Artist One', 'Artist Two'], 3, 12)

    assert audio.tags['\xa9ART'] == ['Artist One, Artist Two']
    assert audio.tags['covr'] == [b'cover']
    assert audio.tags['aART'] == ['Existing Album Artist']
    assert [
        bytes(value) for value in audio.tags['----:com.apple.iTunes:ARTISTS']
    ] == [b'Artist One', b'Artist Two']
    assert audio.tags['trkn'] == [(3, 12)]
    assert audio.saved


class _FakeVorbis(dict):
    def __init__(self):
        super().__init__({
            'ARTIST': ['Artist One, Artist Two'],
            'ALBUMARTIST': ['Existing Album Artist'],
            'METADATA_BLOCK_PICTURE': ['cover'],
        })
        self.saved = False

    def save(self):
        self.saved = True


def test_flac_mapping_preserves_singular_artist_artwork_and_album_artist():
    audio = _FakeVorbis()
    _write_vorbis(audio, ['Artist One', 'Artist Two'], 3, 12)

    assert audio['ARTIST'] == ['Artist One, Artist Two']
    assert audio['ALBUMARTIST'] == ['Existing Album Artist']
    assert audio['METADATA_BLOCK_PICTURE'] == ['cover']
    assert audio['ARTISTS'] == ['Artist One', 'Artist Two']
    assert audio['TRACKNUMBER'] == ['3']
    assert audio['TRACKTOTAL'] == ['12']
    assert audio['TOTALTRACKS'] == ['12']
    assert audio.saved


def test_after_move_writer_ignores_unsupported_and_empty_metadata():
    processor = MusicMetadataWriterPostProcessor()
    empty = {'filepath': 'track.mp3', 'ext': 'mp3'}
    unsupported = {
        'filepath': 'track.wav',
        'ext': 'wav',
        _TRACK_NUMBER_KEY: 3,
    }

    with patch('music_metadata.write_music_tags') as writer:
        processor.run(empty)
        processor.run(unsupported)

    writer.assert_not_called()


def test_after_move_writer_dispatches_enriched_metadata():
    processor = MusicMetadataWriterPostProcessor()
    info = {
        'filepath': 'track.flac',
        'ext': 'flac',
        _ARTISTS_KEY: ['Artist One', 'Artist Two'],
        _TRACK_NUMBER_KEY: 3,
        _TRACK_TOTAL_KEY: 12,
    }

    with patch('music_metadata.write_music_tags') as writer:
        processor.run(info)

    writer.assert_called_once_with(
        'track.flac', 'flac', ['Artist One', 'Artist Two'], 3, 12
    )
