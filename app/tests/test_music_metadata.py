"""Tests for conservative audio metadata enrichment."""

from __future__ import annotations

from music_metadata import MusicMetadataPreProcessor


def _preprocess(source_entry, info):
    processor = MusicMetadataPreProcessor(source_entry=source_entry)
    _, result = processor.run(info)
    return result


def test_album_uses_existing_order_and_total_when_track_number_is_missing():
    result = _preprocess(
        {
            'playlist_index': '03',
            'playlist_count': 12,
            'playlist_title': 'Example Album',
        },
        {'title': 'Track', 'album': 'Example Album'},
    )

    assert result['track_number'] == '3/12'
    assert result['album'] == 'Example Album'


def test_official_track_number_wins_over_album_order():
    result = _preprocess(
        {'playlist_index': 3, 'playlist_count': 12},
        {'track_number': 7, 'album': 'Official Album'},
    )

    assert result['track_number'] == '7/12'
    assert result['album'] == 'Official Album'


def test_inline_official_track_total_is_preserved():
    result = _preprocess(
        {'playlist_count': 12},
        {'track_number': '4/10', 'album': 'Official Album'},
    )

    assert result['track_number'] == '4/10'


def test_source_track_number_and_total_are_retained_from_flat_extraction():
    result = _preprocess(
        {'track_number': 2, 'track_count': 9, 'playlist_index': 4},
        {'title': 'Track'},
    )

    assert result['track_number'] == '2/9'


def test_album_title_falls_back_to_source_playlist_title():
    result = _preprocess(
        {'playlist_title': 'Example Album'},
        {'track_number': 4},
    )

    assert result['album'] == 'Example Album'
    assert result['track_number'] == 4


def test_playlist_without_extractor_album_signals_is_not_changed():
    result = _preprocess(
        {
            'playlist_index': 3,
            'playlist_count': 12,
            'playlist_title': 'Example Playlist',
        },
        {'title': 'Track'},
    )

    assert 'album' not in result
    assert 'track_number' not in result


def test_regular_video_artwork_is_not_changed():
    thumbnails = [
        {'url': 'square.jpg', 'width': 500, 'height': 500},
        {'url': 'landscape.jpg', 'width': 1280, 'height': 720},
    ]
    result = _preprocess({}, {'title': 'Regular Video', 'thumbnails': thumbnails.copy()})

    assert result['thumbnails'] == thumbnails
    assert 'thumbnail' not in result


def test_music_audio_prefers_largest_existing_square_thumbnail():
    result = _preprocess(
        {},
        {
            'track': 'Track',
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
        {},
        {'track': 'Track', 'thumbnails': thumbnails.copy()},
    )

    assert result['thumbnails'] == thumbnails
    assert 'thumbnail' not in result
