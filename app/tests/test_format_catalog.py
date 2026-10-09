"""Tests for ``format_catalog``: its shape, the rules it enforces, and that every
option it offers has a yt-dlp mapping in ``dl_formats``."""

from __future__ import annotations

import itertools
import json

import pytest

import dl_formats
import format_catalog
from format_catalog import CATALOG, InvalidOption, resolve_selection

_CHOICE_FIELDS = ('codec', 'format', 'audio_tags', 'subtitle_mode', 'subtitle_language')


def _choices():
    """Every choice in the catalog, with a readable path."""
    yield 'download_type', CATALOG['download_type']
    for t in CATALOG['download_type']['options']:
        for field in _CHOICE_FIELDS:
            if field in t:
                yield f"{t['id']}.{field}", t[field]
        for f in t['format']['options']:
            if 'quality' in f:
                yield f"{t['id']}.{f['id']}.quality", f['quality']


def _types():
    return CATALOG['download_type']['options']


@pytest.mark.parametrize('path,choice', list(_choices()), ids=lambda v: v if isinstance(v, str) else '')
def test_every_choice_is_well_formed(path, choice):
    ids = [o['id'] for o in choice['options']]
    assert ids, path
    assert len(ids) == len(set(ids)), f'{path} repeats an id'
    assert choice['default'] in ids, f'{path} default is not one of its options'
    for option in choice['options']:
        assert isinstance(option['id'], str) and option['id'] == option['id'].strip() and option['id']
        assert isinstance(option['text'], str) and option['text'].strip()


def test_types_carry_only_known_fields():
    for t in _types():
        assert set(t) - {'id', 'text'} <= set(_CHOICE_FIELDS), t['id']
        assert 'format' in t, t['id']
        for f in t['format']['options']:
            assert set(f) <= {'id', 'text', 'quality', 'tags'}, (t['id'], f['id'])


def test_audio_formats_say_whether_they_carry_tags():
    for f in format_catalog.download_type('audio')['format']['options']:
        assert isinstance(f.get('tags'), bool), f['id']
    assert not format_catalog.format_supports_tags('audio', 'wav')
    assert format_catalog.format_supports_tags('audio', 'mp3')


def test_ids_are_lowercase_like_the_request_parser_makes_them():
    # parse_download_options lowercases type, codec, format and quality.
    for t in _types():
        assert t['id'] == t['id'].lower()
        for field in ('codec', 'format'):
            for o in t.get(field, {'options': []})['options']:
                assert o['id'] == o['id'].lower(), (t['id'], field, o['id'])
        for f in t['format']['options']:
            for q in f.get('quality', {'options': []})['options']:
                assert q['id'] == q['id'].lower()


def test_public_catalog_is_json_and_a_copy():
    public = format_catalog.public_catalog()
    assert json.loads(json.dumps(public)) == CATALOG
    public['download_type']['options'][0]['format']['options'].clear()
    assert format_catalog.format_ids('video'), 'mutating the copy must not touch the catalog'


class TestResolveSelection:
    def test_returns_valid_values_unchanged(self):
        assert resolve_selection('video', 'h264', 'mp4', '1080') == ('h264', 'mp4', '1080')
        assert resolve_selection('audio', 'auto', 'mp3', '320') == ('auto', 'mp3', '320')

    def test_forces_codec_for_a_type_without_codecs(self):
        assert resolve_selection('audio', 'h265', 'flac', 'best') == ('auto', 'flac', 'best')
        assert resolve_selection('captions', 'whatever', 'vtt', 'best')[0] == 'auto'

    def test_forces_quality_for_a_format_without_qualities(self):
        assert resolve_selection('captions', 'auto', 'srt', '1080') == ('auto', 'srt', 'best')
        assert resolve_selection('thumbnail', 'auto', 'jpg', 'anything') == ('auto', 'jpg', 'best')

    def test_ios_takes_a_height_like_the_other_video_formats(self):
        # The selector honours it; the old UI only hid the dropdown.
        assert resolve_selection('video', 'auto', 'ios', '720') == ('auto', 'ios', '720')

    @pytest.mark.parametrize('args,field', [
        (('gif', 'auto', 'any', 'best'), 'download_type'),
        (('video', 'mpeg2', 'any', 'best'), 'codec'),
        (('video', 'auto', 'mkv', 'best'), 'format'),
        (('video', 'auto', 'mp3', 'best'), 'format'),
        (('video', 'auto', 'any', '320'), 'quality'),
        (('audio', 'auto', 'flac', '320'), 'quality'),
        (('audio', 'auto', 'm4a', '320'), 'quality'),
    ])
    def test_rejects_what_the_catalog_does_not_offer(self, args, field):
        with pytest.raises(InvalidOption, match=f'^{field} must be one of'):
            resolve_selection(*args)

    def test_the_message_lists_the_allowed_values(self):
        with pytest.raises(InvalidOption) as exc:
            resolve_selection('audio', 'auto', 'm4a', '320')
        assert str(exc.value) == "quality must be one of ['128', '192', 'best'] for format m4a"


def test_per_field_checks():
    format_catalog.check_audio_tags('no_cover')
    format_catalog.check_subtitle_mode('auto_only')
    format_catalog.check_subtitle_language('zh-Hans')
    format_catalog.check_subtitle_language('fil')  # not in the suggestions, still a valid tag
    for check, value in (
        (format_catalog.check_audio_tags, 'all'),
        (format_catalog.check_subtitle_mode, 'whatever'),
        (format_catalog.check_subtitle_language, '-en'),
        (format_catalog.check_subtitle_language, 'x' * 36),
    ):
        with pytest.raises(InvalidOption):
            check(value)


# Every option the catalog offers must reach yt-dlp. A new codec, format or
# quality with no mapping in dl_formats fails here rather than at download time.

def _all_selections():
    for t in _types():
        codecs = [o['id'] for o in t['codec']['options']] if 'codec' in t else ['auto']
        for f in t['format']['options']:
            qualities = [o['id'] for o in f['quality']['options']] if 'quality' in f else ['best']
            for codec, quality in itertools.product(codecs, qualities):
                yield t['id'], codec, f['id'], quality


@pytest.mark.parametrize('selection', list(_all_selections()), ids=lambda s: '-'.join(s))
def test_every_selection_maps_to_ytdlp(selection):
    download_type, codec, fmt, quality = selection
    assert resolve_selection(download_type, codec, fmt, quality) == (codec, fmt, quality)
    selector = dl_formats.get_format(download_type, codec, fmt, quality)
    assert isinstance(selector, str) and selector
    opts = dl_formats.get_opts(download_type, codec, fmt, quality, {})
    assert isinstance(opts.get('postprocessors'), list)


def test_every_video_codec_has_a_filter():
    for codec in format_catalog.choice_ids('video', 'codec'):
        if codec == format_catalog.choice_default('video', 'codec'):
            continue
        assert codec in dl_formats.CODEC_FILTER_MAP, codec
        assert dl_formats.CODEC_FILTER_MAP[codec] in dl_formats.get_format('video', codec, 'any', 'best')


def test_every_numeric_video_quality_limits_the_height():
    for fmt in format_catalog.format_ids('video'):
        for quality in format_catalog.format_option('video', fmt)['quality']['options']:
            if quality['id'].isdigit():
                assert f"[height<={quality['id']}]" in dl_formats.get_format('video', 'auto', fmt, quality['id'])


def test_every_audio_format_is_extracted_and_tagged_as_the_catalog_says():
    for fmt in format_catalog.format_ids('audio'):
        opts = dl_formats.get_opts('audio', 'auto', fmt, 'best', {}, audio_tags='with_cover')
        keys = [pp['key'] for pp in opts['postprocessors']]
        assert keys[0] == 'FFmpegExtractAudio', fmt
        tagged = 'EmbedThumbnail' in keys and 'FFmpegMetadata' in keys
        assert tagged == format_catalog.format_supports_tags('audio', fmt), fmt


def test_every_numeric_audio_quality_is_passed_to_the_extractor():
    for fmt in format_catalog.format_ids('audio'):
        for quality in format_catalog.format_option('audio', fmt)['quality']['options']:
            opts = dl_formats.get_opts('audio', 'auto', fmt, quality['id'], {})
            expected = 0 if quality['id'] == 'best' else quality['id']
            assert opts['postprocessors'][0]['preferredquality'] == expected


def test_every_caption_format_is_requested_from_ytdlp():
    for fmt in format_catalog.format_ids('captions'):
        opts = dl_formats.get_opts('captions', 'auto', fmt, 'best', {})
        requested = 'srt' if fmt == 'txt' else fmt
        assert opts['subtitlesformat'] == f'{requested}/best'


def test_every_subtitle_mode_sets_the_subtitle_flags():
    for mode in format_catalog.choice_ids('captions', 'subtitle_mode'):
        opts = dl_formats.get_opts('captions', 'auto', 'srt', 'best', {}, subtitle_mode=mode)
        assert opts['writesubtitles'] or opts['writeautomaticsub'], mode


def test_unknown_values_fall_back_to_the_catalog_defaults():
    assert dl_formats._normalize_caption_mode('bogus') == format_catalog.choice_default('captions', 'subtitle_mode')
    assert dl_formats._normalize_subtitle_language('  ') == format_catalog.choice_default('captions', 'subtitle_language')
    opts = dl_formats.get_opts('audio', 'auto', 'mp3', 'best', {}, audio_tags='bogus')
    assert opts.get('writethumbnail') is True  # the default, With cover
